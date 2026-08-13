"""
HIPO — CRM: carteira de parceiros indicadores (Sprint 6).

O parceiro NÃO é entidade nova: é uma `conta` com `eh_finder = true`. Sempre
uma empresa — contador autônomo entra com o CNPJ dele. Não existe tabela
`parceiros` e não existe indicador pessoa física.

Decisões que este módulo materializa:

  * MÓDULO PRÓPRIO ('parceiros'), não 'crm'. Cultivar a relação com quem
    indica é trabalho do EC; SDR, EV e EP não têm o que fazer aqui. É a
    diretriz "uma tela por função" aplicada à permissão, não só ao layout.

  * A SITUAÇÃO DA RELAÇÃO É DERIVADA, e derivada em Python. A regra
    (ativo / esfriando / dormente) vive em services/parceiro.py; escrevê-la
    também em SQL criaria duas fontes de verdade que divergem no primeiro
    ajuste — mesma decisão já tomada para a situação das tarefas.

    Consequência: o filtro por situação e o `total` são calculados sobre o
    conjunto inteiro, em memória, antes de paginar. Isso é aceitável porque
    a carteira de parceiros é da ordem de dezenas — não de milhares. O teto
    de CAP_PARCEIROS existe para essa premissa falhar alto se um dia deixar
    de valer, em vez de a tela ficar lenta em silêncio.

  * A ÚLTIMA INDICAÇÃO IGNORA O PERÍODO. As métricas respeitam o recorte
    escolhido na tela; a situação, não. Filtrar as duas pelo mesmo período
    faria um parceiro de três anos aparecer como "sem indicação" toda vez
    que alguém olhasse os últimos 90 dias.

  * TODA MEXIDA NA CARTEIRA VIRA EVENTO, na mesma transação. Sem isso, "de
    quem era essa carteira em março" não tem resposta — e esse dado não dá
    para reconstruir depois. Transferência em massa grava uma linha POR
    PARCEIRO: o que interessa é a história de cada um, não a do clique.

  * NÃO EXISTE CÁLCULO DE COMISSÃO AQUI. Existe contrapartida ao parceiro,
    mas o cálculo e o pagamento acontecem fora do HIPO. O papel desta tela é
    dizer quantas indicações converteram e com que ticket.

  * O FAROL E O MINI-FUNIL SÃO DUAS PERGUNTAS OPOSTAS, e é de propósito que
    fiquem lado a lado na mesma linha. O farol mede o que NÓS fizemos pelo
    parceiro (cadência de contato, semana a semana); o mini-funil mede o que
    ELE nos deu e em que pé está. Parceiro sem indicação com quatro semanas
    verdes é problema de produto ou de mercado; parceiro sem indicação com
    quatro semanas vermelhas é abandono — e a ação é outra. Uma coluna só
    nunca separaria os dois casos.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from routers.permissions import CARGOS_COM_PARCEIROS
from services import cnpj as cnpj_svc
from services import oportunidade as regras_opp
from services import parceiro as regras
from services.tarefa import FUSO_OPERACAO

router = APIRouter()

# O fuso vai para o SQL como parâmetro para que o corte de semana do banco
# seja EXATAMENTE o mesmo que services/parceiro.inicio_da_semana() faz em
# Python. Deixar o Postgres usar o TimeZone da sessão faria o farol mudar de
# resposta conforme a configuração do servidor.
_NOME_FUSO = FUSO_OPERACAO.key

# Teto de leitura da carteira. Ver o comentário do módulo: a paginação e o
# filtro por situação acontecem em memória, e isso só é honesto enquanto a
# carteira couber confortavelmente. Bater neste número é sinal de que a
# premissa mudou e o filtro precisa descer para o SQL.
CAP_PARCEIROS = 2000

ORDENACOES = {
    "indicacoes": "ind.indicacoes",
    "convertidas": "ind.convertidas",
    "ticket_indicado": "ind.ticket_indicado",
    "ticket_convertido": "ind.ticket_convertido",
    "ultima_indicacao": "ult.ultima_indicacao_em",
    "razao_social": "c.razao_social",
}

# Ordenar por situação é a única que não desce para o SQL — a regra é Python.
ORDENACAO_SITUACAO = "situacao"


# ── Schemas ──────────────────────────────────────────────────────────

class SemanaFarol(BaseModel):
    """Uma casa da trilha do farol. A regra da cor está em services."""
    inicio: date
    fim: date
    cor: str
    concluidas: int
    agendadas: int
    corrente: bool


class FaseFunil(BaseModel):
    qtd: int
    ticket: Decimal


class FunilParceiro(BaseModel):
    """
    O estoque aberto que este parceiro indicou, por fase.

    Modelo fechado com as cinco fases abertas, e não um dicionário livre: a
    tela desenha cinco faixas sempre, inclusive as zeradas. Fase ausente do
    payload viraria faixa que some da linha e volta — e um mini-funil que
    muda de largura conforme o conteúdo não dá para comparar entre linhas.

    'finalizado' fica fora. É fluxo, não estoque — mesma decisão da visão de
    funil da tela de Oportunidades.
    """
    suspect: FaseFunil
    lead: FaseFunil
    qualificacao: FaseFunil
    apresentacao: FaseFunil
    negociacao: FaseFunil


class ParceiroResumo(BaseModel):
    id: UUID
    razao_social: str
    nome_fantasia: str | None
    cnpj: str
    cnpj_formatado: str
    cidade: str | None
    uf: str | None
    telefone: str | None
    email: str | None
    ativo: bool
    # Vem no payload porque o PATCH pode DESMARCAR o parceiro: o front
    # precisa saber que a linha saiu da carteira, e um 204 mudo obrigaria a
    # tela a adivinhar.
    eh_finder: bool
    ec_responsavel_id: UUID | None
    ec_responsavel_nome: str | None
    indicacoes: int
    convertidas: int
    perdidas: int
    canceladas: int
    em_aberto: int
    ticket_indicado: Decimal
    ticket_convertido: Decimal
    ultima_indicacao_em: date | None
    situacao: str
    situacao_rotulo: str
    # None (e não 0.0) quando não há denominador — ver services/parceiro.py.
    taxa_conversao: float | None
    taxa_cancelamento: float | None

    # ── O que nós fizemos por ele ────────────────────────────────────
    farol: list[SemanaFarol]
    semanas_sem_contato: int
    sem_contato: bool
    tarefas_abertas: int
    # A menor data entre as tarefas em aberto. É o embrião da "próxima
    # tarefa" da Etapa 5 — a tela já mostra QUANDO é o próximo toque, sem
    # ainda decidir por ninguém qual fazer primeiro.
    proxima_tarefa_em: datetime | None

    # ── O que ele nos deu, e em que pé está ──────────────────────────
    funil: FunilParceiro


class EventoCarteira(BaseModel):
    tipo: str
    de_nome: str | None
    para_nome: str | None
    autor_nome: str | None
    criado_em: datetime


class ParceiroDetalhe(ParceiroResumo):
    eventos: list[EventoCarteira]


class ParceiroLista(BaseModel):
    total: int
    limit: int
    offset: int
    periodo: str
    itens: list[ParceiroResumo]


class Indicacao(BaseModel):
    id: UUID
    numero: str
    conta_id: UUID
    conta_razao_social: str
    fase: str
    status: str
    valor_mensalidade: Decimal | None
    criado_em: datetime
    atualizado_em: datetime


class ResumoCarteira(BaseModel):
    parceiros: int
    sem_ec: int
    indicacoes: int
    convertidas: int
    canceladas: int
    ticket_convertido: Decimal
    taxa_conversao: float | None
    periodo: str
    por_situacao: list[dict]
    por_ec: list[dict]
    # Quantos parceiros estão vermelhos NESTA semana — nem contato feito nem
    # tarefa marcada. É o KPI que existe para ser zerado toda sexta.
    sem_contato_semana: int
    # Distribuição das cores da semana corrente, para a leitura de rebanho:
    # 3 vermelhos em 5 parceiros é uma conversa; 3 em 80 é ruído.
    por_cor_semana: list[dict]


class ParceiroEditar(BaseModel):
    """
    Patch parcial. `model_fields_set` distingue "não mandei o campo" de
    "mandei null" — sem isso não dá para remover o EC responsável.
    """
    eh_finder: bool | None = None
    ec_responsavel_id: UUID | None = None


class TransferenciaCarteira(BaseModel):
    """
    Reatribuição em massa.

    `de_usuario_id` nulo significa "os parceiros sem responsável" — é o que
    permite usar a mesma tela para distribuir os órfãos, e não só para
    esvaziar a carteira de quem está saindo.

    `para_usuario_id` nulo significa "deixar sem responsável".

    `conta_ids` vazio ou ausente = todos os parceiros da origem.
    """
    de_usuario_id: UUID | None = None
    para_usuario_id: UUID | None = None
    conta_ids: list[UUID] = Field(default_factory=list)


class TransferenciaResultado(BaseModel):
    transferidos: int
    conta_ids: list[UUID]


# ── SQL compartilhado ────────────────────────────────────────────────
#
# $1 é SEMPRE a data de início do período (ou NULL para 'sempre'). Os filtros
# opcionais começam em $2. Amarrar a posição do período aqui é o que permite
# manter uma única forma da consulta.
#
# São dois LATERAL de propósito. O primeiro respeita o recorte de período; o
# segundo, o da última indicação, varre a história inteira — é ele que
# alimenta a situação da relação. Juntar os dois num só faria o parceiro
# antigo virar "sem indicação" sempre que a tela recortasse os últimos meses.

_SELECT_PARCEIRO = """
    SELECT c.id, c.razao_social, c.nome_fantasia, c.cnpj, c.cidade, c.uf,
           c.telefone, c.email, c.ativo, c.eh_finder,
           c.ec_responsavel_id, u.nome AS ec_responsavel_nome,
           ind.indicacoes, ind.convertidas, ind.perdidas, ind.canceladas,
           ind.em_aberto, ind.ticket_indicado, ind.ticket_convertido,
           ult.ultima_indicacao_em
      FROM contas c
      LEFT JOIN usuarios u ON u.id = c.ec_responsavel_id
      LEFT JOIN LATERAL (
          SELECT count(*)                                                 AS indicacoes,
                 count(*) FILTER (WHERE o.status = 'conquistado')         AS convertidas,
                 count(*) FILTER (WHERE o.status = 'perdido')             AS perdidas,
                 count(*) FILTER (WHERE o.status = 'cancelado')           AS canceladas,
                 count(*) FILTER (WHERE o.status IN ('ativa','suspensa')) AS em_aberto,
                 COALESCE(sum(o.valor_mensalidade), 0)                    AS ticket_indicado,
                 COALESCE(sum(o.valor_mensalidade)
                          FILTER (WHERE o.status = 'conquistado'), 0)     AS ticket_convertido
            FROM oportunidades o
           WHERE o.finder_conta_id = c.id
             AND ($1::date IS NULL OR o.criado_em >= $1::date)
      ) ind ON TRUE
      LEFT JOIN LATERAL (
          SELECT max(o.criado_em)::date AS ultima_indicacao_em
            FROM oportunidades o
           WHERE o.finder_conta_id = c.id
      ) ult ON TRUE
"""


def _linha(row, hoje: date | None = None) -> dict:
    d = dict(row)
    d["cnpj_formatado"] = cnpj_svc.formatar(d["cnpj"])
    sit = regras.situacao(d["ultima_indicacao_em"], hoje)
    d["situacao"] = sit
    d["situacao_rotulo"] = regras.ROTULOS_SITUACAO[sit]
    d["taxa_conversao"] = regras.taxa_conversao(d["convertidas"], d["perdidas"])
    d["taxa_cancelamento"] = regras.taxa_cancelamento(d["canceladas"], d["indicacoes"])
    return d


def _inicio(periodo: str, hoje: date | None) -> date | None:
    try:
        return regras.inicio_do_periodo(periodo, hoje)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


# ── Farol semanal e mini-funil ───────────────────────────────────────
#
# Dois agregados, duas consultas, ambas por LOTE de conta_ids. Consultar por
# parceiro dentro do laço seria N+1 — 50 parceiros na tela viram 100 idas ao
# banco, e a tela que existe para ser aberta o dia inteiro é a pior candidata
# a isso.
#
# Os dois rodam sobre o CONJUNTO INTEIRO, antes de paginar, pelo mesmo motivo
# que a situação: o farol é filtrável, e filtrar por um campo calculado só na
# página visível daria contagem errada na primeira troca de página. Vale sob a
# mesma premissa declarada em CAP_PARCEIROS.

# O verde olha `concluida_em` e o amarelo olha `prazo` — são datas
# diferentes de propósito (ver services/parceiro.cor_do_farol), e é por isso
# que são dois SELECT unidos e não um GROUP BY só. Cancelada não conta nem
# como agendada: cancelar é dizer que aquilo não deveria ter sido marcado.
_SQL_FAROL = """
    SELECT conta_id, semana,
           sum(concluidas)::int AS concluidas,
           sum(agendadas)::int  AS agendadas
      FROM (
          SELECT t.conta_id,
                 date_trunc('week', t.concluida_em AT TIME ZONE $2::text)::date AS semana,
                 1 AS concluidas, 0 AS agendadas
            FROM tarefas t
           WHERE t.conta_id = ANY($1::uuid[])
             AND t.concluida_em IS NOT NULL
             AND (t.concluida_em AT TIME ZONE $2::text)::date BETWEEN $3 AND $4
          UNION ALL
          SELECT t.conta_id,
                 date_trunc('week', t.prazo AT TIME ZONE $2::text)::date AS semana,
                 0 AS concluidas, 1 AS agendadas
            FROM tarefas t
           WHERE t.conta_id = ANY($1::uuid[])
             AND t.concluida_em IS NULL
             AND t.cancelada_em IS NULL
             AND (t.prazo AT TIME ZONE $2::text)::date BETWEEN $3 AND $4
      ) x
     GROUP BY conta_id, semana
"""

# Tarefas em aberto e a data da próxima. Sem recorte de janela: uma tarefa
# marcada para daqui a dois meses continua sendo a próxima, e escondê-la
# faria a tela dizer "sem próximo passo" para quem tem um.
_SQL_TAREFAS_ABERTAS = """
    SELECT t.conta_id,
           count(*)::int AS abertas,
           min(t.prazo)  AS proxima_em
      FROM tarefas t
     WHERE t.conta_id = ANY($1::uuid[])
       AND t.concluida_em IS NULL
       AND t.cancelada_em IS NULL
     GROUP BY t.conta_id
"""

# Estoque aberto por fase. Respeita o período da barra, como todo agregado
# desta tela: "das que ele indicou nos últimos 90 dias, onde estão".
# Só status aberto — e como o CHECK do funil amarra `finalizado` aos status
# de desfecho, filtrar por status aberto já devolve exatamente as 5 fases.
_SQL_FUNIL = """
    SELECT o.finder_conta_id AS conta_id, o.fase,
           count(*)::int                         AS qtd,
           COALESCE(sum(o.valor_mensalidade), 0) AS ticket
      FROM oportunidades o
     WHERE o.finder_conta_id = ANY($1::uuid[])
       AND o.status IN ('ativa', 'suspensa')
       AND ($2::date IS NULL OR o.criado_em >= $2::date)
     GROUP BY o.finder_conta_id, o.fase
"""


def _funil_vazio() -> dict:
    return {f: {"qtd": 0, "ticket": Decimal(0)} for f in regras_opp.FASES_ABERTAS}


async def _enriquecer(conn, itens: list[dict], hoje: date | None,
                      inicio: date | None) -> list[dict]:
    """
    Acrescenta farol, tarefas em aberto e mini-funil às linhas já montadas.

    Três consultas em lote, independentemente de quantos parceiros. Sai daqui
    com tudo que a linha da tela desenha.
    """
    if not itens:
        return itens

    ids = [i["id"] for i in itens]
    referencia = hoje or date.today()
    semanas = regras.semanas_do_farol(referencia)
    primeira, ultima = semanas[0][0], semanas[-1][1]

    linhas_farol = await conn.fetch(_SQL_FAROL, ids, _NOME_FUSO, primeira, ultima)
    linhas_tarefas = await conn.fetch(_SQL_TAREFAS_ABERTAS, ids)
    linhas_funil = await conn.fetch(_SQL_FUNIL, ids, inicio)

    contagens: dict[UUID, dict[date, dict]] = {}
    for r in linhas_farol:
        contagens.setdefault(r["conta_id"], {})[r["semana"]] = {
            "concluidas": r["concluidas"], "agendadas": r["agendadas"],
        }

    tarefas = {r["conta_id"]: r for r in linhas_tarefas}

    funis: dict[UUID, dict] = {}
    for r in linhas_funil:
        alvo = funis.setdefault(r["conta_id"], _funil_vazio())
        # Guarda contra fase fora das cinco abertas. Não deveria acontecer —
        # o CHECK do funil impede —, mas um KeyError aqui derrubaria a tela
        # inteira por causa de uma linha.
        if r["fase"] in alvo:
            alvo[r["fase"]] = {"qtd": r["qtd"], "ticket": r["ticket"]}

    for item in itens:
        trilha = regras.farol(contagens.get(item["id"], {}), referencia)
        item["farol"] = trilha
        item["sem_contato"] = regras.sem_contato_na_semana(trilha)
        item["semanas_sem_contato"] = regras.semanas_sem_contato(trilha)

        t = tarefas.get(item["id"])
        item["tarefas_abertas"] = t["abertas"] if t else 0
        item["proxima_tarefa_em"] = t["proxima_em"] if t else None

        item["funil"] = funis.get(item["id"]) or _funil_vazio()

    return itens


async def _conta_ou_404(conn, conta_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT id, razao_social, eh_finder, ec_responsavel_id FROM contas WHERE id = $1",
        conta_id,
    )
    if not row:
        raise HTTPException(404, "Conta não encontrada.")
    return dict(row)


async def _validar_ec(conn, usuario_id: UUID | None) -> None:
    """
    O responsável precisa ser um usuário ATIVO com cargo que trabalha
    carteira. CHECK de banco não enxerga cargo, então a regra é aqui — e
    precisa ser aqui, senão a tela permitiria pendurar a carteira num SDR e o
    filtro "parceiros do EC" nunca mais fecharia com a realidade.
    """
    if usuario_id is None:
        return
    row = await conn.fetchrow(
        "SELECT nome, cargo, ativo FROM usuarios WHERE id = $1", usuario_id
    )
    if not row:
        raise HTTPException(422, "Usuário responsável não encontrado.")
    if not row["ativo"]:
        raise HTTPException(422, f"{row['nome']} está inativo e não pode receber carteira.")
    if row["cargo"] not in CARGOS_COM_PARCEIROS:
        raise HTTPException(
            422,
            f"Cargo '{row['cargo'] or 'sem cargo'}' não trabalha carteira de parceiro. "
            f"Use: {', '.join(sorted(CARGOS_COM_PARCEIROS))}.",
        )


async def _registrar(conn, conta_id: UUID, tipo: str, autor,
                     de: UUID | None = None, para: UUID | None = None) -> None:
    await conn.execute(
        """
        INSERT INTO parceiro_eventos
            (conta_id, tipo, de_usuario_id, para_usuario_id, usuario_id)
        VALUES ($1, $2, $3, $4, $5)
        """,
        conta_id, tipo, de, para, autor,
    )


def _evento_de_troca(atual: UUID | None, novo: UUID | None) -> str | None:
    """Nome do evento para uma mudança de responsável. None se nada mudou."""
    if atual == novo:
        return None
    if atual is None:
        return "atribuido"
    if novo is None:
        return "removido"
    return "transferido"


async def _detalhe(conn, conta_id: UUID, periodo: str, hoje: date | None) -> dict:
    """
    Linha do parceiro + trilha da carteira.

    NÃO checa `eh_finder` de propósito: o PATCH que desmarca o parceiro
    precisa devolver o registro logo depois de ele deixar de ser um. Quem
    exige parceiro é o GET, que checa antes de chamar.
    """
    inicio = _inicio(periodo, hoje)
    row = await conn.fetchrow(f"{_SELECT_PARCEIRO} WHERE c.id = $2", inicio, conta_id)
    if not row:
        raise HTTPException(404, "Conta não encontrada.")

    eventos = await conn.fetch(
        """
        SELECT e.tipo, e.criado_em,
               du.nome AS de_nome, pu.nome AS para_nome, au.nome AS autor_nome
          FROM parceiro_eventos e
          LEFT JOIN usuarios du ON du.id = e.de_usuario_id
          LEFT JOIN usuarios pu ON pu.id = e.para_usuario_id
          LEFT JOIN usuarios au ON au.id = e.usuario_id
         WHERE e.conta_id = $1
         ORDER BY e.criado_em DESC, e.id DESC
         LIMIT 50
        """,
        conta_id,
    )
    linha = _linha(row, hoje)
    await _enriquecer(conn, [linha], hoje, inicio)
    return {**linha, "eventos": [dict(e) for e in eventos]}


# ── Leitura ──────────────────────────────────────────────────────────
#
# ATENÇÃO À ORDEM: /resumo e /carteira/transferir precisam vir ANTES de
# /{conta_id}. O FastAPI casa por ordem de declaração, e com o path
# parametrizado na frente "resumo" seria interpretado como um UUID e
# devolveria 422.


@router.get("/resumo", response_model=ResumoCarteira)
async def resumo(
    periodo: str = Query("sempre"),
    hoje: date | None = Query(None, description="Só para teste determinístico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    KPIs do topo da tela. Cada número tem filtro equivalente na listagem — é
    o que permite o drilldown.

    'sem_ec' é o KPI que existe para ser zerado: parceiro sem responsável é
    relação que ninguém está cultivando.
    """
    inicio = _inicio(periodo, hoje)

    rows = await conn.fetch(
        f"{_SELECT_PARCEIRO} WHERE c.eh_finder LIMIT {CAP_PARCEIROS}", inicio
    )
    itens = await _enriquecer(conn, [_linha(r, hoje) for r in rows], hoje, inicio)

    convertidas = sum(i["convertidas"] for i in itens)
    perdidas = sum(i["perdidas"] for i in itens)

    por_situacao = {s: 0 for s in regras.SITUACOES}
    for i in itens:
        por_situacao[i["situacao"]] += 1

    # Cor da semana CORRENTE. A trilha tem quatro casas; o KPI olha só a
    # última — a pergunta do topo da tela é sobre esta semana, e a leitura
    # histórica é a trilha na linha de cada parceiro.
    por_cor = {c: 0 for c in regras.CORES}
    for i in itens:
        corrente = next((s for s in i["farol"] if s["corrente"]), None)
        if corrente:
            por_cor[corrente["cor"]] += 1

    # Carteira por EC. Só quem tem parceiro aparece — a lista existe para
    # comparar carteiras, não para mostrar todo mundo com zero.
    por_ec: dict[str, dict] = {}
    for i in itens:
        if i["ec_responsavel_id"] is None:
            continue
        chave = str(i["ec_responsavel_id"])
        alvo = por_ec.setdefault(chave, {
            "usuario_id": chave,
            "nome": i["ec_responsavel_nome"],
            "parceiros": 0,
            "indicacoes": 0,
            "convertidas": 0,
        })
        alvo["parceiros"] += 1
        alvo["indicacoes"] += i["indicacoes"]
        alvo["convertidas"] += i["convertidas"]

    return {
        "parceiros": len(itens),
        "sem_ec": sum(1 for i in itens if i["ec_responsavel_id"] is None),
        "indicacoes": sum(i["indicacoes"] for i in itens),
        "convertidas": convertidas,
        "canceladas": sum(i["canceladas"] for i in itens),
        "ticket_convertido": sum(i["ticket_convertido"] for i in itens),
        "taxa_conversao": regras.taxa_conversao(convertidas, perdidas),
        "periodo": periodo,
        "por_situacao": [
            {"situacao": s, "rotulo": regras.ROTULOS_SITUACAO[s], "quantidade": por_situacao[s]}
            for s in regras.SITUACOES
        ],
        "por_ec": sorted(por_ec.values(), key=lambda x: (-x["parceiros"], x["nome"] or "")),
        "sem_contato_semana": sum(1 for i in itens if i["sem_contato"]),
        "por_cor_semana": [
            {"cor": c, "rotulo": regras.ROTULOS_COR[c], "quantidade": por_cor[c]}
            for c in regras.CORES
        ],
    }


@router.post("/carteira/transferir", response_model=TransferenciaResultado)
async def transferir_carteira(
    payload: TransferenciaCarteira,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Reatribuição em massa — a resposta para "o EC saiu, e agora?".

    Sem esta rota, desligar alguém com 40 parceiros vira 40 cliques; e o que
    acontece na prática é que ninguém faz, e a carteira passa a mentir.

    Grava um evento POR PARCEIRO. O lote não é a unidade de história.
    """
    if payload.de_usuario_id is not None and payload.de_usuario_id == payload.para_usuario_id:
        raise HTTPException(422, "Origem e destino são a mesma pessoa.")

    await _validar_ec(conn, payload.para_usuario_id)

    async with conn.transaction():
        if payload.conta_ids:
            alvos = await conn.fetch(
                """
                SELECT id, ec_responsavel_id FROM contas
                 WHERE id = ANY($1::uuid[]) AND eh_finder
                   AND ec_responsavel_id IS NOT DISTINCT FROM $2
                   FOR UPDATE
                """,
                payload.conta_ids, payload.de_usuario_id,
            )
        else:
            alvos = await conn.fetch(
                """
                SELECT id, ec_responsavel_id FROM contas
                 WHERE eh_finder AND ec_responsavel_id IS NOT DISTINCT FROM $1
                   FOR UPDATE
                """,
                payload.de_usuario_id,
            )

        if not alvos:
            return {"transferidos": 0, "conta_ids": []}

        ids = [r["id"] for r in alvos]
        await conn.execute(
            "UPDATE contas SET ec_responsavel_id = $1, atualizado_em = NOW() "
            "WHERE id = ANY($2::uuid[])",
            payload.para_usuario_id, ids,
        )

        tipo = _evento_de_troca(payload.de_usuario_id, payload.para_usuario_id)
        if tipo:
            for conta_id in ids:
                await _registrar(
                    conn, conta_id, tipo, user["id"],
                    de=payload.de_usuario_id, para=payload.para_usuario_id,
                )

    return {"transferidos": len(ids), "conta_ids": ids}


@router.get("", response_model=ParceiroLista)
async def listar(
    q: str | None = Query(None, max_length=200),
    ec_responsavel_id: UUID | None = None,
    sem_ec: bool = False,
    situacao: str | None = Query(None),
    sem_contato: bool = False,
    periodo: str = Query("sempre"),
    apenas_ativas: bool = True,
    ordenar_por: str = Query("indicacoes"),
    desc: bool = True,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    hoje: date | None = Query(None, description="Só para teste determinístico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    if ordenar_por not in ORDENACOES and ordenar_por != ORDENACAO_SITUACAO:
        raise HTTPException(
            422, f"ordenar_por inválido. Use: {sorted([*ORDENACOES, ORDENACAO_SITUACAO])}"
        )
    if situacao is not None:
        try:
            regras.validar_situacao(situacao)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    inicio = _inicio(periodo, hoje)
    params: list = [inicio]
    where = ["c.eh_finder"]

    def add(clausula: str, valor) -> None:
        params.append(valor)
        where.append(clausula.format(n=len(params)))

    if q:
        add(
            "(c.razao_social ILIKE ${n} OR c.nome_fantasia ILIKE ${n} OR c.cnpj LIKE ${n})",
            f"%{q.strip()}%",
        )
    if sem_ec:
        where.append("c.ec_responsavel_id IS NULL")
    elif ec_responsavel_id is not None:
        add("c.ec_responsavel_id = ${n}", ec_responsavel_id)
    if apenas_ativas:
        where.append("c.ativo")

    # A ordenação por situação não desce para o SQL: a regra é Python, e
    # duplicá-la aqui seria a segunda fonte de verdade que o módulo evita.
    ordem = (
        "c.razao_social"
        if ordenar_por == ORDENACAO_SITUACAO
        else ORDENACOES[ordenar_por]
    )
    direcao = "DESC" if desc else "ASC"

    rows = await conn.fetch(
        f"""
        {_SELECT_PARCEIRO}
        WHERE {' AND '.join(where)}
        ORDER BY {ordem} {direcao} NULLS LAST, c.razao_social
        LIMIT {CAP_PARCEIROS}
        """,
        *params,
    )

    itens = await _enriquecer(conn, [_linha(r, hoje) for r in rows], hoje, inicio)
    if situacao:
        itens = [i for i in itens if i["situacao"] == situacao]
    if sem_contato:
        # Vermelho da semana corrente: nem contato feito nem tarefa marcada.
        # Amarelo fica fora de propósito — já tem alguém com ele. Ver
        # services/parceiro.sem_contato_na_semana.
        itens = [i for i in itens if i["sem_contato"]]
    if ordenar_por == ORDENACAO_SITUACAO:
        # ORDEM_SITUACAO é uma ordem de ATENÇÃO (sem_indicacao primeiro, ativo
        # por último), então o padrão da tela — desc=True — precisa percorrê-la
        # crescendo. Invertido, a lista abriria mostrando quem está bem.
        itens.sort(key=lambda i: regras.ORDEM_SITUACAO[i["situacao"]], reverse=not desc)

    return {
        "total": len(itens),
        "limit": limit,
        "offset": offset,
        "periodo": periodo,
        "itens": itens[offset:offset + limit],
    }


@router.get("/{conta_id}", response_model=ParceiroDetalhe)
async def obter(
    conta_id: UUID,
    periodo: str = Query("sempre"),
    hoje: date | None = Query(None, description="Só para teste determinístico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    conta = await _conta_ou_404(conn, conta_id)
    if not conta["eh_finder"]:
        raise HTTPException(404, f"{conta['razao_social']} não é um parceiro.")
    return await _detalhe(conn, conta_id, periodo, hoje)


@router.get("/{conta_id}/indicacoes", response_model=list[Indicacao])
async def indicacoes(
    conta_id: UUID,
    periodo: str = Query("sempre"),
    limit: int = Query(100, ge=1, le=200),
    hoje: date | None = Query(None, description="Só para teste determinístico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    As oportunidades que este parceiro indicou — o drilldown do painel.

    Endpoint próprio, e não um filtro em /crm/oportunidades, para a tela ser
    inteira do módulo 'parceiros': o dia em que a lista de oportunidades
    ganhar o recorte por envolvimento (Sprint 7), o EC continuaria precisando
    ver a indicação que ele não trabalha.

    Traz os três desfechos junto com o que está em aberto: a leitura aqui é
    "o que esse parceiro me deu", e o que virou nada faz parte da resposta.
    """
    conta = await _conta_ou_404(conn, conta_id)
    if not conta["eh_finder"]:
        raise HTTPException(404, f"{conta['razao_social']} não é um parceiro.")

    inicio = _inicio(periodo, hoje)
    rows = await conn.fetch(
        """
        SELECT o.id, o.numero, o.conta_id, c.razao_social AS conta_razao_social,
               o.fase, o.status, o.valor_mensalidade, o.criado_em, o.atualizado_em
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
         WHERE o.finder_conta_id = $1
           AND ($2::date IS NULL OR o.criado_em >= $2::date)
         ORDER BY o.criado_em DESC
         LIMIT $3
        """,
        conta_id, inicio, limit,
    )
    return [dict(r) for r in rows]


# ── Escrita ──────────────────────────────────────────────────────────


@router.patch("/{conta_id}", response_model=ParceiroDetalhe)
async def editar(
    conta_id: UUID,
    payload: ParceiroEditar,
    periodo: str = Query("sempre"),
    hoje: date | None = Query(None, description="Só para teste determinístico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Marca/desmarca o parceiro e define o EC responsável.

    Marcar à mão é o que permite prospectar um contador antes da primeira
    indicação — sem isso, a tela só mostra parceiro que já deu fruto, e
    parceiro que ainda não deu é justamente quem precisa de ação.

    Desmarcar LIMPA o responsável na mesma transação. Não é gentileza com o
    CHECK do banco: manter o dono de uma parceria que deixou de existir
    faria a carteira dele contar um parceiro que não é mais parceiro.
    """
    enviados = payload.model_fields_set
    if not enviados:
        raise HTTPException(422, "Nada para alterar.")

    conta = await _conta_ou_404(conn, conta_id)
    eh_finder = conta["eh_finder"]
    ec_atual = conta["ec_responsavel_id"]

    novo_finder = payload.eh_finder if "eh_finder" in enviados else eh_finder
    if novo_finder is None:
        raise HTTPException(422, "eh_finder não aceita nulo.")

    pediu_ec = "ec_responsavel_id" in enviados
    novo_ec = payload.ec_responsavel_id if pediu_ec else ec_atual

    if not novo_finder:
        # Pedir responsável para quem não é (ou deixou de ser) parceiro é
        # contradição, e tem que FALHAR. A versão anterior deste bloco zerava
        # o campo em silêncio e devolvia 200: a tela achava que tinha salvo,
        # o banco discordava, e ninguém ficava sabendo.
        if pediu_ec and payload.ec_responsavel_id is not None:
            raise HTTPException(
                422,
                "Só parceiro pode ter EC responsável. Marque como parceiro primeiro.",
            )
        # Desmarcar, esse sim, zera o responsável — e de propósito.
        novo_ec = None

    await _validar_ec(conn, novo_ec)

    async with conn.transaction():
        await conn.execute(
            "UPDATE contas SET eh_finder = $1, ec_responsavel_id = $2, "
            "atualizado_em = NOW() WHERE id = $3",
            novo_finder, novo_ec, conta_id,
        )
        if novo_finder != eh_finder:
            await _registrar(
                conn, conta_id, "marcado" if novo_finder else "desmarcado", user["id"]
            )
        tipo = _evento_de_troca(ec_atual, novo_ec)
        if tipo:
            await _registrar(conn, conta_id, tipo, user["id"], de=ec_atual, para=novo_ec)

    # Devolve o registro mesmo quando acabou de ser desmarcado: `eh_finder`
    # vem no payload, e é por ele que a tela sabe tirar a linha da carteira.
    return await _detalhe(conn, conta_id, periodo, hoje)
