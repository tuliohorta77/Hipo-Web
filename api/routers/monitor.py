"""
HIPO — Monitor: o painel de parede da operacao.

Dez quadros com meta e resultado do MES CORRENTE e uma carinha em cada um.
Fica aberto numa TV e a tela se atualiza sozinha; aqui embaixo o que existe
e uma leitura so — `GET /monitor/painel` — que devolve o painel inteiro.

TRES DECISOES QUE ESTE MODULO MATERIALIZA

  * UM ENDPOINT PARA O PAINEL INTEIRO. Dez indicadores em dez chamadas
    fariam a TV disparar dez requests por minuto e, pior, permitiriam que
    metade da tela fosse de um instante e metade de outro. O painel e uma
    foto: ou tudo do mesmo segundo, ou nao serve para conferir nada.

  * O RECORTE E MTD, SEMPRE. Do dia 1o do mes ate HOJE, no fuso da
    operacao. Nao existe seletor de periodo: a pergunta do painel e "como
    estamos ESTE mes", e um seletor faria a TV mostrar setembro em
    novembro sem ninguem perceber.

  * A META ESPERADA E PROPORCIONAL AOS DIAS UTEIS CORRIDOS. Regra em
    services/monitor.py, dias uteis em services/dias_uteis.py, feriados na
    tabela `dia_nao_util` — que ganhou CRUD aqui para a gestao manter.

O PAINEL LE, NAO CALCULA DE NOVO

Cada numero sai da MESMA fonte que a tela dele usa: reuniao e desfecho vem
de `services/agenda.desfecho_efetivo`, o mesmo que a Agenda e o relatorio
de produtividade usam; a venda vem de `oportunidade_eventos`, a mesma
trilha que o funil le. Reimplementar qualquer um deles em SQL proprio daria
ao painel um numero que ninguem consegue conferir na tela de origem — e o
primeiro que nao batesse jogaria fora a confianca nos dez.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from routers.permissions import requer_gestao
from services import agenda as regras_agenda
from services import dias_uteis
from services import monitor as regras
from services.monitor import MonitorInvalido
from services.tarefa import FUSO_OPERACAO, janela_utc

router = APIRouter()

MESES = (
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


# ── Schemas ──────────────────────────────────────────────────────────

class IndicadorOut(BaseModel):
    chave: str
    sigla: str
    rotulo: str
    fonte: str
    natureza: str
    formato: str
    # None = nao ha o que medir ainda (indicador aberto). Zero e um
    # resultado; None e a ausencia dele, e os dois desenham diferente.
    resultado: float | None
    meta: float | None
    # A meta que valia para HOJE — proporcional aos dias uteis corridos nos
    # indicadores que acumulam.
    meta_mtd: float | None
    # Fracao: 1.0 = bateu a meta de hoje. E este numero que escolhe a carinha.
    atingimento: float | None
    # Quanto do MES INTEIRO ja foi feito. E a barra do quadro, e ela fala de
    # outra coisa: 25% do mes feito pode ser ritmo bom no dia 5.
    atingimento_mes: float | None
    carinha: str | None


class PainelOut(BaseModel):
    ano: int
    mes: int
    rotulo: str
    hoje: date
    dia_util_atual: int
    dias_uteis: int
    # Fracao do mes util ja corrida. A tela mostra como "dia 5 de 21".
    progresso: float
    # O instante da leitura. A TV mostra na barra: painel parado sem hora e
    # painel que mente sem avisar.
    atualizado_em: datetime
    indicadores: list[IndicadorOut]



class ItemDetalheOut(BaseModel):
    """
    Uma linha do que compoe o numero de um quadro. Os campos sao a uniao de
    reuniao e oportunidade: cada quadro preenche os seus e deixa o resto
    null, e a tela desenha as colunas pelo `tipo` do detalhe.
    """
    # Reuniao: a hora da reuniao (ou a hora em que foi marcada, em AGEND
    # MES). Lead e venda: a hora do evento que contou.
    data: datetime
    empresa: str | None
    oportunidade_id: UUID | None
    oportunidade_numero: str | None
    # So na reuniao de parceiro: a conta do parceiro, que e o alvo dela.
    conta_id: UUID | None = None
    reuniao_id: UUID | None = None
    tipo_sigla: str | None = None
    # Reuniao: o anfitriao. Lead e venda: quem registrou o evento.
    pessoa: str | None
    agendado_por_nome: str | None = None
    reuniao_inicio: datetime | None = None
    desfecho: str | None = None
    desfecho_rotulo: str | None = None
    valor: float | None = None
    # No % NOSHOW a lista e o DENOMINADOR (as fechadas) e `conta` marca o
    # numerador (os no-shows). Nos outros quadros toda linha conta.
    conta: bool = True


class DetalheOut(BaseModel):
    chave: str
    sigla: str
    rotulo: str
    fonte: str
    formato: str
    # 'reunioes' | 'oportunidades' | 'nenhum' — escolhe as colunas da tela.
    tipo: str
    ano: int
    mes: int
    rotulo_mes: str
    # O MESMO numero do quadro, calculado das mesmas linhas.
    resultado: float | None
    # Uma frase dizendo como a lista vira o numero: "3 no-shows em 27
    # reunioes fechadas", "soma de 4 mensalidades". Taxa e soma nao se
    # conferem contando linhas, e sem a frase a lista parece nao bater.
    resumo: str
    itens: list[ItemDetalheOut]

class MetaIn(BaseModel):
    indicador: str
    # None APAGA a meta do mes — é como se tira a cobranca de um indicador
    # sem deixar zero, que significa "meta zero".
    valor: float | None = Field(None, ge=0)


class MetasIn(BaseModel):
    ano: int = Field(..., ge=2020, le=2100)
    mes: int = Field(..., ge=1, le=12)
    metas: list[MetaIn]


class MetaOut(BaseModel):
    indicador: str
    sigla: str
    rotulo: str
    formato: str
    natureza: str
    valor: float | None
    atualizado_em: datetime | None
    atualizado_por_nome: str | None


class MetasOut(BaseModel):
    ano: int
    mes: int
    rotulo: str
    metas: list[MetaOut]


class FeriadoIn(BaseModel):
    data: date
    motivo: str = Field(..., min_length=1, max_length=200)


class FeriadoOut(BaseModel):
    id: int
    data: date
    motivo: str


# ── Tempo ────────────────────────────────────────────────────────────


def _hoje() -> date:
    return datetime.now(FUSO_OPERACAO).date()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _mes_pedido(ano: int | None, mes: int | None) -> tuple[int, int]:
    """
    O mes do painel. Sem parametro, o mes corrente — que e o caso da TV.

    Aceitar ano/mes existe para a gestao conferir um mes fechado e para o
    teste ser deterministico, nao para a TV: a tela nao oferece seletor.
    """
    hoje = _hoje()
    if ano is None and mes is None:
        return hoje.year, hoje.month
    if ano is None or mes is None:
        raise HTTPException(422, "Informe ano e mes juntos, ou nenhum dos dois.")
    return ano, mes


def _janela_mtd(ano: int, mes: int, hoje: date) -> tuple[datetime, datetime, date]:
    """
    O intervalo UTC do dia 1o do mes ate o fim de HOJE.

    Mes que ja passou vai ate o ultimo dia dele: o painel de agosto aberto
    em setembro mostra agosto inteiro, e nao agosto ate o dia 17.
    """
    primeiro = date(ano, mes, 1)
    ultimo = date(ano, mes, monthrange(ano, mes)[1])
    ate = min(hoje, ultimo) if hoje >= primeiro else primeiro
    inicio, fim = janela_utc(primeiro, ate)
    return inicio, fim, ate


# ── Fontes de cada indicador ─────────────────────────────────────────


# Cada indicador tem UMA funcao que devolve as LINHAS que ele conta. O
# painel conta essas linhas e o detalhe (o clique na carinha) as devolve
# inteiras. Sao as mesmas linhas pela mesma consulta: a lista aberta na TV
# nao tem como discordar do numero que estava no quadro.


async def _linhas_leads(conn, inicio: datetime, fim: datetime) -> list[dict]:
    """
    Leads novos: quem passou de Suspect para Lead na janela.

    Sai de `oportunidade_eventos`, e nao de "oportunidades hoje na fase
    lead": a fase de agora responde onde o negocio esta, nao quantos
    ENTRARAM no mes — e quem virou lead dia 3 e apresentacao dia 10 sumiria
    da conta.

    Uma linha por EVENTO, como o count(*) de antes: a oportunidade que
    voltou a suspect e virou lead de novo no mesmo mes conta duas vezes no
    quadro, e aparece duas vezes na lista.
    """
    rows = await conn.fetch(
        """
        SELECT e.criado_em AS data, o.id AS oportunidade_id,
               o.numero AS oportunidade_numero,
               COALESCE(c.nome_fantasia, c.razao_social) AS empresa,
               u.nome AS pessoa
          FROM oportunidade_eventos e
          JOIN oportunidades o ON o.id = e.oportunidade_id
          JOIN contas c        ON c.id = o.conta_id
          LEFT JOIN usuarios u ON u.id = e.usuario_id
         WHERE e.tipo = 'fase' AND e.de = 'suspect' AND e.para = 'lead'
           AND e.criado_em >= $1 AND e.criado_em < $2
         ORDER BY e.criado_em DESC
        """,
        inicio, fim,
    )
    return [dict(r) for r in rows]


# A mesma projecao para as duas janelas de reuniao. Empresa vem da conta da
# OPORTUNIDADE ou, na reuniao de parceiro, da conta do proprio alvo — o
# CHECK `ck_tarefa_alvo` garante que exatamente um dos dois existe.
_SELECT_REUNIOES = """
SELECT r.id AS reuniao_id, r.desfecho, r.duracao_min, r.criado_em AS agendada_em,
       t.prazo AS inicio, t.concluida_em, t.cancelada_em,
       t.conta_id, t.oportunidade_id,
       o.numero AS oportunidade_numero,
       COALESCE(c.nome_fantasia, c.razao_social) AS empresa,
       tr.sigla AS tipo_sigla,
       ua.nome AS pessoa,
       ag.nome AS agendado_por_nome
  FROM reunioes r
  JOIN tarefas t            ON t.id = r.tarefa_id
  LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
  LEFT JOIN contas c        ON c.id = COALESCE(o.conta_id, t.conta_id)
  LEFT JOIN tipos_reuniao tr ON tr.id = r.tipo_id
  LEFT JOIN usuarios ua     ON ua.id = t.responsavel_id
  LEFT JOIN usuarios ag     ON ag.id = r.agendado_por
"""


def _com_desfecho(rows) -> list[dict]:
    """
    Acrescenta o desfecho EFETIVO a cada reuniao.

    Calculado em Python por `services/agenda`, o mesmo que a grade e o
    relatorio de produtividade usam. Repetir a deducao em SQL daria ao
    painel um no-show diferente do da Agenda.
    """
    linhas = []
    for r in rows:
        d = dict(r)
        d["efetivo"] = regras_agenda.desfecho_efetivo(
            desfecho=d["desfecho"],
            concluida_em=d["concluida_em"],
            cancelada_em=d["cancelada_em"],
            inicio=d["inicio"],
        )
        linhas.append(d)
    return linhas


async def _linhas_reunioes(conn, inicio: datetime, fim: datetime) -> list[dict]:
    """
    As reunioes do mes pela DATA DA REUNIAO (`t.prazo`), cliente e parceiro
    juntos: quem separa e `_reunioes`, com a regra da ilha.
    """
    rows = await conn.fetch(
        _SELECT_REUNIOES
        + " WHERE t.prazo >= $1 AND t.prazo < $2 ORDER BY t.prazo DESC",
        inicio, fim,
    )
    return _com_desfecho(rows)


async def _linhas_agendadas(conn, inicio: datetime, fim: datetime) -> list[dict]:
    """
    Os agendamentos FEITOS no mes (`r.criado_em`), so de cliente.

    O JOIN com `tarefas` nao e enfeite: AGEND MES e o unico numero do painel
    que nao precisaria de `tarefas` para existir, e foi exatamente por isso
    que ele contava agendamento de parceria sem ninguem perceber.
    """
    rows = await conn.fetch(
        _SELECT_REUNIOES
        + """
         WHERE r.criado_em >= $1 AND r.criado_em < $2
           AND t.conta_id IS NULL
         ORDER BY r.criado_em DESC
        """,
        inicio, fim,
    )
    return _com_desfecho(rows)


def _separar_reunioes(linhas: list[dict]) -> dict[str, list[dict]]:
    """
    Distribui as reunioes do mes pelos quadros. E AQUI que mora a regra de
    cada quadro de reuniao — o painel conta estas listas e o detalhe as
    devolve, entao nao existe uma segunda copia da regra para divergir.

    PARCERIA E ILHA (decisao do Tulio, 21/09). Reuniao de parceiro — a que
    tem `tarefas.conta_id` — conta SO no quadro PARCERIAS. Nao entra em
    AGEN, nao entra em APRE e nao entra em nenhum dos dois lados do
    % NOSHOW. So a REALIZADA alimenta o quadro dela: parceiro que desmarcou
    nao e no-show de cliente nem reuniao perdida do mes.

    "Marcadas para o mes" (AGEN) exclui a DESMARCADA e mantem o no-show: o
    compromisso existiu, o cliente e que nao veio. Contar o no-show fora
    faria a taxa dele sair de um denominador menor que a realidade.

    `fechadas` e o denominador do % NOSHOW: realizada, desmarcada ou
    no-show. Reuniao sem desfecho ainda nao entra em nenhum lado.
    """
    grupos = {"agen": [], "apre": [], "reunioes_parceria": [], "fechadas": []}
    for r in linhas:
        efetivo = r["efetivo"]
        if r["conta_id"] is not None:
            if efetivo == "realizada":
                grupos["reunioes_parceria"].append(r)
            continue
        if efetivo != "cancelada":
            grupos["agen"].append(r)
        if efetivo == "realizada":
            grupos["apre"].append(r)
        if efetivo in ("realizada", "cancelada", "no_show"):
            grupos["fechadas"].append(r)
    return grupos


async def _reunioes(conn, inicio: datetime, fim: datetime) -> dict:
    """Tudo o que vem de reuniao, contado das mesmas listas do detalhe."""
    grupos = _separar_reunioes(await _linhas_reunioes(conn, inicio, fim))
    agendadas = await _linhas_agendadas(conn, inicio, fim)
    no_show = sum(1 for r in grupos["fechadas"] if r["efetivo"] == "no_show")
    return {
        "agen": len(grupos["agen"]),
        "apre": len(grupos["apre"]),
        "reunioes_parceria": len(grupos["reunioes_parceria"]),
        "agendamentos_mes": len(agendadas),
        "noshow": regras.taxa_percentual(no_show, len(grupos["fechadas"])),
    }


async def _linhas_vendas(conn, inicio: datetime, fim: datetime) -> list[dict]:
    """
    As oportunidades conquistadas no mes, pela data em que o ganho foi
    REGISTRADO.

    Sai do evento de status ('conquistado'), e nao de `atualizado_em` da
    oportunidade: qualquer edicao posterior mexe em `atualizado_em` e
    moveria uma venda de agosto para setembro sozinha.

    Uma linha por OPORTUNIDADE (DISTINCT ON): reabrir e ganhar de novo grava
    dois eventos, e uma venda so aconteceu uma vez. Fica o primeiro ganho do
    mes.
    """
    rows = await conn.fetch(
        """
        SELECT * FROM (
            SELECT DISTINCT ON (o.id)
                   e.criado_em AS data, o.id AS oportunidade_id,
                   o.numero AS oportunidade_numero,
                   COALESCE(c.nome_fantasia, c.razao_social) AS empresa,
                   o.valor_mensalidade AS valor,
                   u.nome AS pessoa
              FROM oportunidade_eventos e
              JOIN oportunidades o ON o.id = e.oportunidade_id
              JOIN contas c        ON c.id = o.conta_id
              LEFT JOIN usuarios u ON u.id = e.usuario_id
             WHERE e.tipo = 'status' AND e.para = 'conquistado'
               AND e.criado_em >= $1 AND e.criado_em < $2
             ORDER BY o.id, e.criado_em
        ) ganhas
        ORDER BY data DESC
        """,
        inicio, fim,
    )
    linhas = []
    for r in rows:
        d = dict(r)
        d["valor"] = float(d["valor"]) if d["valor"] is not None else None
        linhas.append(d)
    return linhas


def _somar_vendas(linhas: list[dict]) -> dict:
    contratos = len(linhas)
    nmrr = float(sum(l["valor"] or 0 for l in linhas))
    return {
        "contratos": contratos,
        "nmrr": nmrr,
        "ticket_medio": regras.media(nmrr, contratos),
    }


async def _vendas(conn, inicio: datetime, fim: datetime) -> dict:
    return _somar_vendas(await _linhas_vendas(conn, inicio, fim))


async def _metas_do_mes(conn, ano: int, mes: int) -> dict[str, float]:
    rows = await conn.fetch(
        "SELECT indicador, valor FROM monitor_metas WHERE ano = $1 AND mes = $2",
        ano, mes,
    )
    return {r["indicador"]: float(r["valor"]) for r in rows}


async def _dias_nao_uteis(conn, ano: int, mes: int) -> list[date]:
    ultimo = date(ano, mes, monthrange(ano, mes)[1])
    rows = await conn.fetch(
        "SELECT data FROM dia_nao_util WHERE data >= $1 AND data <= $2",
        date(ano, mes, 1), ultimo,
    )
    return [r["data"] for r in rows]


# ── O painel ─────────────────────────────────────────────────────────


@router.get("/painel", response_model=PainelOut)
async def painel(
    ano: int | None = Query(None, ge=2020, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    hoje: date | None = Query(None, description="So para teste deterministico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    O painel inteiro: os dez indicadores do mes, com meta MTD e carinha.

    Barato de propósito — a TV chama isto de minuto em minuto. Sao quatro
    consultas agregadas mais a leitura das metas e dos feriados do mes; o
    volume que atravessa Python e o das reunioes do mes, dezenas de linhas.
    """
    ano, mes = _mes_pedido(ano, mes)
    referencia = hoje or _hoje()
    inicio, fim, ate = _janela_mtd(ano, mes, referencia)

    nao_uteis = await _dias_nao_uteis(conn, ano, mes)
    primeiro = date(ano, mes, 1)
    uteis = dias_uteis.dias_uteis_no_mes(primeiro, nao_uteis)
    corridos = dias_uteis.dia_util_atual_no_mes(primeiro, nao_uteis, ate)

    resultados: dict[str, float | None] = {
        "lead": len(await _linhas_leads(conn, inicio, fim)),
    }
    resultados.update(await _reunioes(conn, inicio, fim))
    resultados.update(await _vendas(conn, inicio, fim))
    resultados["treinamento"] = None

    metas = await _metas_do_mes(conn, ano, mes)

    indicadores = []
    for ind in sorted(regras.INDICADORES, key=lambda i: i.ordem):
        meta = metas.get(ind.chave)
        resultado = resultados.get(ind.chave)
        alvo_hoje = regras.meta_mtd(meta, corridos, len(uteis), ind.natureza)
        indicadores.append({
            "chave": ind.chave,
            "sigla": ind.sigla,
            "rotulo": ind.rotulo,
            "fonte": ind.fonte,
            "natureza": ind.natureza,
            "formato": ind.formato,
            "resultado": resultado,
            "meta": meta,
            "meta_mtd": alvo_hoje,
            "atingimento": regras.atingimento(resultado, alvo_hoje, ind.natureza),
            # Contra a meta do MES INTEIRO: e a barra do quadro, e ela
            # responde "quanto do mes ja foi feito".
            "atingimento_mes": regras.atingimento(resultado, meta, ind.natureza),
            "carinha": regras.carinha(
                regras.atingimento(resultado, alvo_hoje, ind.natureza)
            ),
        })

    return {
        "ano": ano,
        "mes": mes,
        "rotulo": f"{MESES[mes - 1]} de {ano}",
        "hoje": ate,
        "dia_util_atual": corridos,
        "dias_uteis": len(uteis),
        "progresso": (corridos / len(uteis)) if uteis else 0.0,
        "atualizado_em": _agora(),
        "indicadores": indicadores,
    }



# ── O detalhe de um quadro ───────────────────────────────────────────

TIPO_DO_DETALHE = {
    "lead": "oportunidades",
    "agen": "reunioes",
    "apre": "reunioes",
    "reunioes_parceria": "reunioes",
    "agendamentos_mes": "reunioes",
    "noshow": "reunioes",
    "nmrr": "oportunidades",
    "ticket_medio": "oportunidades",
    "contratos": "oportunidades",
    "treinamento": "nenhum",
}


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _item_reuniao(r: dict, *, pela_marcacao: bool = False, conta: bool = True) -> dict:
    return {
        "data": r["agendada_em"] if pela_marcacao else r["inicio"],
        "empresa": r["empresa"],
        "oportunidade_id": r["oportunidade_id"],
        "oportunidade_numero": r["oportunidade_numero"],
        "conta_id": r["conta_id"],
        "reuniao_id": r["reuniao_id"],
        "tipo_sigla": r["tipo_sigla"],
        "pessoa": r["pessoa"],
        "agendado_por_nome": r["agendado_por_nome"],
        "reuniao_inicio": r["inicio"],
        "desfecho": r["efetivo"],
        "desfecho_rotulo": (
            regras_agenda.ROTULO_DESFECHO.get(r["efetivo"]) if r["efetivo"]
            else "Sem desfecho"
        ),
        "conta": conta,
    }


def _item_oportunidade(l: dict) -> dict:
    return {
        "data": l["data"],
        "empresa": l["empresa"],
        "oportunidade_id": l["oportunidade_id"],
        "oportunidade_numero": l["oportunidade_numero"],
        "pessoa": l["pessoa"],
        "valor": l.get("valor"),
    }


@router.get("/detalhe/{chave}", response_model=DetalheOut)
async def detalhe(
    chave: str,
    ano: int | None = Query(None, ge=2020, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    hoje: date | None = Query(None, description="So para teste deterministico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    O que compoe o numero de UM quadro: o clique na carinha.

    Mesma janela MTD e mesmas funcoes de linha do painel — o painel CONTA
    as linhas que este endpoint DEVOLVE. E isso que garante que a lista
    aberta na TV confere com o numero que estava no quadro; uma consulta
    propria aqui seria a segunda regra que um dia diverge.

    Leitura aberta a quem ve o painel: a TV fica na sala, e quem olha o
    numero tem o direito de ver de onde ele vem. Agir sobre a linha (abrir
    a reuniao, registrar desfecho) passa pelas permissoes da tela de origem.
    """
    try:
        regras.validar_indicador(chave)
    except MonitorInvalido as e:
        raise HTTPException(404, str(e))

    ind = regras.POR_CHAVE[chave]
    ano, mes = _mes_pedido(ano, mes)
    inicio, fim, _ate = _janela_mtd(ano, mes, hoje or _hoje())

    itens: list[dict] = []
    resultado: float | None = None
    resumo = ""

    if chave == "lead":
        linhas = await _linhas_leads(conn, inicio, fim)
        itens = [_item_oportunidade(l) for l in linhas]
        resultado = len(linhas)
        resumo = _plural(resultado, "passagem de Suspect para Lead", "passagens de Suspect para Lead")

    elif chave in ("agen", "apre", "reunioes_parceria", "noshow"):
        grupos = _separar_reunioes(await _linhas_reunioes(conn, inicio, fim))
        if chave == "noshow":
            fechadas = grupos["fechadas"]
            no_show = sum(1 for r in fechadas if r["efetivo"] == "no_show")
            # No-shows primeiro: sao eles que o quadro mede. O resto da
            # lista e o denominador, e fica abaixo para quem quer conferir.
            ordenadas = (
                [r for r in fechadas if r["efetivo"] == "no_show"]
                + [r for r in fechadas if r["efetivo"] != "no_show"]
            )
            itens = [
                _item_reuniao(r, conta=r["efetivo"] == "no_show") for r in ordenadas
            ]
            resultado = regras.taxa_percentual(no_show, len(fechadas))
            resumo = (
                f"{_plural(no_show, 'no-show', 'no-shows')} em "
                f"{_plural(len(fechadas), 'reunião de cliente fechada', 'reuniões de cliente fechadas')}"
            )
        else:
            linhas = grupos[chave]
            itens = [_item_reuniao(r) for r in linhas]
            resultado = len(linhas)
            singular, plural = {
                "agen": ("reunião de cliente no mês", "reuniões de cliente no mês"),
                "apre": ("reunião de cliente realizada", "reuniões de cliente realizadas"),
                "reunioes_parceria": (
                    "reunião de parceiro realizada", "reuniões de parceiro realizadas",
                ),
            }[chave]
            resumo = _plural(resultado, singular, plural)
            if chave == "agen":
                resumo += ", sem as desmarcadas"

    elif chave == "agendamentos_mes":
        linhas = await _linhas_agendadas(conn, inicio, fim)
        itens = [_item_reuniao(r, pela_marcacao=True) for r in linhas]
        resultado = len(linhas)
        resumo = _plural(
            resultado, "reunião de cliente marcada no mês",
            "reuniões de cliente marcadas no mês",
        )

    elif chave in ("contratos", "nmrr", "ticket_medio"):
        linhas = await _linhas_vendas(conn, inicio, fim)
        itens = [_item_oportunidade(l) for l in linhas]
        somas = _somar_vendas(linhas)
        resultado = somas[chave]
        n = somas["contratos"]
        resumo = {
            "contratos": _plural(n, "oportunidade conquistada", "oportunidades conquistadas"),
            "nmrr": f"soma da mensalidade de {_plural(n, 'contrato', 'contratos')}",
            "ticket_medio": f"NMRR dividido por {_plural(n, 'contrato', 'contratos')}",
        }[chave]

    else:  # treinamento: quadro reservado, sem fonte
        resumo = "Quadro reservado: ainda não há fonte de dado."

    return {
        "chave": ind.chave,
        "sigla": ind.sigla,
        "rotulo": ind.rotulo,
        "fonte": ind.fonte,
        "formato": ind.formato,
        "tipo": TIPO_DO_DETALHE[chave],
        "ano": ano,
        "mes": mes,
        "rotulo_mes": f"{MESES[mes - 1]} de {ano}",
        "resultado": resultado,
        "resumo": resumo,
        "itens": itens,
    }


# ── Metas ────────────────────────────────────────────────────────────


@router.get("/metas", response_model=MetasOut)
async def listar_metas(
    ano: int | None = Query(None, ge=2020, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    As metas de um mes, com TODOS os indicadores na lista — inclusive os que
    ainda nao tem meta, com `valor: null`.

    Devolver so o que existe obrigaria a tela a cruzar duas listas para
    montar o formulario, e o indicador novo (o dia em que entrar um) sumiria
    da tela de metas sem ninguem notar.
    """
    ano, mes = _mes_pedido(ano, mes)
    rows = await conn.fetch(
        """
        SELECT m.indicador, m.valor, m.atualizado_em, u.nome AS atualizado_por_nome
          FROM monitor_metas m
          LEFT JOIN usuarios u ON u.id = m.atualizado_por
         WHERE m.ano = $1 AND m.mes = $2
        """,
        ano, mes,
    )
    gravadas = {r["indicador"]: r for r in rows}
    return {
        "ano": ano,
        "mes": mes,
        "rotulo": f"{MESES[mes - 1]} de {ano}",
        "metas": [
            {
                "indicador": ind.chave,
                "sigla": ind.sigla,
                "rotulo": ind.rotulo,
                "formato": ind.formato,
                "natureza": ind.natureza,
                "valor": (
                    float(gravadas[ind.chave]["valor"])
                    if ind.chave in gravadas else None
                ),
                "atualizado_em": (
                    gravadas[ind.chave]["atualizado_em"]
                    if ind.chave in gravadas else None
                ),
                "atualizado_por_nome": (
                    gravadas[ind.chave]["atualizado_por_nome"]
                    if ind.chave in gravadas else None
                ),
            }
            for ind in sorted(regras.INDICADORES, key=lambda i: i.ordem)
        ],
    }


@router.put("/metas", response_model=MetasOut)
async def gravar_metas(
    payload: MetasIn,
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    """
    Grava as metas do mes de uma vez.

    UM PUT COM A LISTA, e nao um PUT por indicador: quem abre a tela de
    metas ajusta varias e salva uma vez, e dez chamadas deixariam o mes
    metade novo e metade velho se a rede caisse no meio. Aqui e uma
    transacao.

    `valor: null` APAGA a meta daquele indicador. Zero e diferente: zero e
    "este mes nao se cobra isso" e mantem o quadro com carinha.
    """
    for m in payload.metas:
        try:
            regras.validar_indicador(m.indicador)
        except MonitorInvalido as e:
            raise HTTPException(422, str(e))

    async with conn.transaction():
        for m in payload.metas:
            if m.valor is None:
                await conn.execute(
                    "DELETE FROM monitor_metas WHERE indicador = $1 AND ano = $2 AND mes = $3",
                    m.indicador, payload.ano, payload.mes,
                )
                continue
            await conn.execute(
                """
                INSERT INTO monitor_metas (indicador, ano, mes, valor, atualizado_por)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (indicador, ano, mes) DO UPDATE
                   SET valor = EXCLUDED.valor,
                       atualizado_por = EXCLUDED.atualizado_por,
                       atualizado_em = NOW()
                """,
                m.indicador, payload.ano, payload.mes, m.valor, user["id"],
            )

    return await listar_metas(payload.ano, payload.mes, conn=conn, user=user)


@router.post("/metas/copiar", response_model=MetasOut)
async def copiar_metas(
    ano: int = Query(..., ge=2020, le=2100),
    mes: int = Query(..., ge=1, le=12),
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    """
    Copia para `ano/mes` as metas do mes ANTERIOR a ele.

    Existe porque a meta muda pouco de um mes para o outro, e redigitar dez
    numeros todo dia 1o e o caminho mais curto para o painel virar o mes sem
    meta nenhuma — que e o mesmo que sem carinha nenhuma.

    NAO sobrescreve o que ja foi definido para o mes destino: quem ja
    ajustou a meta nova nao pode perde-la para um clique de conveniencia.
    """
    anterior_ano, anterior_mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    await conn.execute(
        """
        INSERT INTO monitor_metas (indicador, ano, mes, valor, atualizado_por)
        SELECT indicador, $1, $2, valor, $5
          FROM monitor_metas WHERE ano = $3 AND mes = $4
        ON CONFLICT (indicador, ano, mes) DO NOTHING
        """,
        ano, mes, anterior_ano, anterior_mes, user["id"],
    )
    return await listar_metas(ano, mes, conn=conn, user=user)


# ── Feriados ─────────────────────────────────────────────────────────


@router.get("/feriados", response_model=list[FeriadoOut])
async def listar_feriados(
    ano: int | None = Query(None, ge=2020, le=2100),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Os dias sem expediente do ano. E o calendario que define o ritmo
    esperado do painel — um mes com tres feriados cobra menos por dia.
    """
    alvo = ano or _hoje().year
    rows = await conn.fetch(
        """
        SELECT id, data, motivo FROM dia_nao_util
         WHERE data >= $1 AND data <= $2 ORDER BY data
        """,
        date(alvo, 1, 1), date(alvo, 12, 31),
    )
    return [dict(r) for r in rows]


@router.post("/feriados", response_model=FeriadoOut, status_code=http.HTTP_201_CREATED)
async def criar_feriado(
    payload: FeriadoIn,
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    """
    Marca um dia como sem expediente. Repetir a mesma data ATUALIZA o motivo
    em vez de dar erro: a intencao de quem manda a mesma data duas vezes e
    corrigir o texto, nao ver um 409.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO dia_nao_util (data, motivo, criado_por_usuario_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (data) DO UPDATE SET motivo = EXCLUDED.motivo
        RETURNING id, data, motivo
        """,
        payload.data, payload.motivo.strip(), user["id"],
    )
    return dict(row)


@router.post("/feriados/nacionais", response_model=list[FeriadoOut])
async def semear_feriados_nacionais(
    ano: int = Query(..., ge=2020, le=2100),
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    """
    Carrega os feriados nacionais do ano (fixos e os moveis da Pascoa).

    Digitar treze datas a mao todo comeco de ano e o tipo de tarefa que nao
    se faz — e feriado faltando na tabela vira meta esperada mais alta do
    que o mes permite. Ponto facultativo NAO entra: a gestao decide caso a
    caso, acrescentando a mao.

    Idempotente: rodar duas vezes nao duplica nem reescreve o motivo de um
    dia que a gestao ja ajustou.
    """
    for data, motivo in dias_uteis.feriados_nacionais_br(ano):
        await conn.execute(
            """
            INSERT INTO dia_nao_util (data, motivo, criado_por_usuario_id)
            VALUES ($1, $2, $3) ON CONFLICT (data) DO NOTHING
            """,
            data, motivo, user["id"],
        )
    return await listar_feriados(ano, conn=conn, user=user)


@router.delete("/feriados/{feriado_id}", status_code=http.HTTP_204_NO_CONTENT)
async def apagar_feriado(
    feriado_id: int,
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    apagou = await conn.fetchval(
        "DELETE FROM dia_nao_util WHERE id = $1 RETURNING id", feriado_id
    )
    if apagou is None:
        raise HTTPException(404, "Dia nao util nao encontrado.")
    return None
