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


async def _leads(conn, inicio: datetime, fim: datetime) -> int:
    """
    Leads novos: quem passou de Suspect para Lead na janela.

    Sai de `oportunidade_eventos`, e nao de "oportunidades hoje na fase
    lead": a fase de agora responde onde o negocio esta, nao quantos
    ENTRARAM no mes — e quem virou lead dia 3 e apresentacao dia 10 sumiria
    da conta.
    """
    return await conn.fetchval(
        """
        SELECT count(*) FROM oportunidade_eventos
         WHERE tipo = 'fase' AND de = 'suspect' AND para = 'lead'
           AND criado_em >= $1 AND criado_em < $2
        """,
        inicio, fim,
    )


async def _reunioes(conn, inicio: datetime, fim: datetime) -> dict:
    """
    Tudo o que vem de reuniao, numa consulta e com UMA regra de desfecho.

    O desfecho efetivo (o registrado, ou o deduzido de uma tarefa fechada
    por outra tela) e calculado em Python por `services/agenda`, o mesmo
    que a grade e o relatorio de produtividade usam. Repetir a deducao em
    SQL daria ao painel um no-show diferente do da Agenda.

    PARCERIA E ILHA (decisao do Tulio, 21/09). Reuniao de parceiro — a que
    tem `tarefas.conta_id` — conta SO no quadro PARCERIAS. Nao entra em
    AGEN, nao entra em APRE, nao entra em AGEND MES e nao entra em nenhum
    dos dois lados do % NOSHOW.

    Antes disso a mesma reuniao aparecia duas vezes na mesma TV: dentro de
    APRE e ao lado dele, em PARCERIAS. Os quadros comerciais medem o esforco
    sobre CLIENTE, e parceria tem ritmo, meta e dono proprios — somar os
    dois inflava o funil com um trabalho que nao gera proposta.

    O CHECK `ck_tarefa_alvo` (`num_nonnulls(oportunidade_id, conta_id) = 1`)
    garante alvo unico por tarefa, entao `conta_id IS NULL` e a definicao
    exata de "reuniao comercial": nao existe terceiro caso.

    A janela e pela DATA DA REUNIAO (`t.prazo`), menos em `agendadas_no_mes`,
    que e pela data em que ela foi MARCADA (`r.criado_em`) — sao perguntas
    diferentes e o Tulio quer as duas: "reunioes deste mes" e "agendamentos
    que a equipe fez neste mes".
    """
    rows = await conn.fetch(
        """
        SELECT r.desfecho, r.duracao_min, t.prazo AS inicio,
               t.concluida_em, t.cancelada_em, t.conta_id
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
         WHERE t.prazo >= $1 AND t.prazo < $2
        """,
        inicio, fim,
    )
    # O JOIN aqui nao e enfeite: AGEND MES e o unico numero do painel que
    # nao precisaria de `tarefas` para existir, e foi exatamente por isso
    # que ele contava agendamento de parceria sem ninguem perceber.
    agendadas_no_mes = await conn.fetchval(
        """
        SELECT count(*)
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
         WHERE r.criado_em >= $1 AND r.criado_em < $2
           AND t.conta_id IS NULL
        """,
        inicio, fim,
    )

    realizadas = canceladas = no_show = marcadas = parcerias = 0
    for r in rows:
        efetivo = regras_agenda.desfecho_efetivo(
            desfecho=r["desfecho"],
            concluida_em=r["concluida_em"],
            cancelada_em=r["cancelada_em"],
            inicio=r["inicio"],
        )
        if r["conta_id"] is not None:
            # Parceria sai do funil comercial aqui, antes de qualquer
            # contagem. So a REALIZADA alimenta o quadro dela: parceiro
            # que desmarcou nao e no-show de cliente nem reuniao perdida
            # do mes — e assunto da carteira de parceiros.
            if efetivo == "realizada":
                parcerias += 1
            continue
        # "Marcadas para o mes" exclui a DESMARCADA e mantem o no-show: o
        # compromisso existiu, o cliente e que nao veio. Contar o no-show
        # fora faria a taxa dele sair de um denominador menor que a
        # realidade.
        if efetivo != "cancelada":
            marcadas += 1
        if efetivo == "realizada":
            realizadas += 1
        elif efetivo == "cancelada":
            canceladas += 1
        elif efetivo == "no_show":
            no_show += 1

    fechadas = realizadas + canceladas + no_show
    return {
        "agen": marcadas,
        "apre": realizadas,
        "reunioes_parceria": parcerias,
        "agendamentos_mes": agendadas_no_mes,
        "noshow": regras.taxa_percentual(no_show, fechadas),
    }


async def _vendas(conn, inicio: datetime, fim: datetime) -> dict:
    """
    Contratos e NMRR do mes, pela data em que o ganho foi REGISTRADO.

    Sai do evento de status ('conquistado'), e nao de `atualizado_em` da
    oportunidade: qualquer edicao posterior mexe em `atualizado_em` e
    moveria uma venda de agosto para setembro sozinha.

    DISTINCT porque reabrir e ganhar de novo grava dois eventos, e uma
    venda so aconteceu uma vez.
    """
    row = await conn.fetchrow(
        """
        SELECT count(*) AS contratos,
               COALESCE(sum(valor_mensalidade), 0) AS nmrr
          FROM (
            SELECT DISTINCT o.id, o.valor_mensalidade
              FROM oportunidade_eventos e
              JOIN oportunidades o ON o.id = e.oportunidade_id
             WHERE e.tipo = 'status' AND e.para = 'conquistado'
               AND e.criado_em >= $1 AND e.criado_em < $2
          ) ganhas
        """,
        inicio, fim,
    )
    contratos = row["contratos"]
    nmrr = float(row["nmrr"])
    return {
        "contratos": contratos,
        "nmrr": nmrr,
        "ticket_medio": regras.media(nmrr, contratos),
    }


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

    resultados: dict[str, float | None] = {"lead": await _leads(conn, inicio, fim)}
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
