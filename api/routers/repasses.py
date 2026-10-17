"""
HIPO -- Contratos: recebimento do repasse Controller -> Spectre (043).

O cliente paga a mensalidade para a Controller; a Controller repassa para a
Spectre 100% no primeiro mes e 30% depois; desse repasse sai o imposto; o
que sobra (liquido) e o que entra de fato. A soma dos liquidos do mes,
menos os descontos, e a nota que a Spectre emite para a Controller.

Uma tela, dois movimentos:
  * o MES (painel): cada contrato vigente com o lancamento da competencia
    -- ou a sugestao, copiada do mes anterior --, os totais, os descontos,
    a nota e a "proxima acao" (lancar, emitir a NF, confirmar recebimento);
  * o CONTRATO: parametros (modalidade, percentuais, aliquota) e o
    historico de lancamentos.

Montado em main.py com prefixo /repasses e o modulo 'contratos' (Franqueado,
ADM e o cargo Financeiro -- a conta da administracao, que so ve isto).
Regras puras em services/repasse.py.

NAO confundir com routers/crm_contratos.py: aquele e o contrato assinado
na Autentique, dentro da oportunidade.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from services import cnpj as cnpj_svc
from services import repasse as regras

router = APIRouter()

TZ_SP = timezone(timedelta(hours=-3))

_CAMPOS_CONTRATO = """
    c.id, c.oportunidade_id, o.numero AS oportunidade_numero, c.conta_id,
    c.cnpj, c.razao_social, c.data_venda, c.modalidade, c.vidas,
    c.valor_por_vida, c.valor_fixo, c.percentual_repasse,
    c.percentual_primeiro_mes, c.primeira_competencia, c.imposto_percentual,
    c.status, c.encerrado_em, c.grupo, c.observacoes, c.criado_em,
    c.atualizado_em
"""


# ── Schemas ──────────────────────────────────────────────────────────

class ContratoNovo(BaseModel):
    razao_social: str = Field(..., min_length=1, max_length=200)
    cnpj: str | None = Field(None, max_length=20)
    data_venda: date
    modalidade: str = "por_vida"
    vidas: int | None = Field(None, ge=0)
    valor_por_vida: Decimal | None = None
    valor_fixo: Decimal | None = None
    percentual_repasse: Decimal = regras.PERCENTUAL_REPASSE_PADRAO
    percentual_primeiro_mes: Decimal = regras.PERCENTUAL_PRIMEIRO_MES_PADRAO
    imposto_percentual: Decimal = regras.IMPOSTO_PADRAO
    primeira_competencia: str | None = None
    grupo: str | None = Field(None, max_length=100)
    observacoes: str | None = None
    oportunidade_id: UUID | None = None
    conta_id: UUID | None = None


class ContratoPatch(BaseModel):
    razao_social: str | None = Field(None, min_length=1, max_length=200)
    cnpj: str | None = Field(None, max_length=20)
    data_venda: date | None = None
    modalidade: str | None = None
    vidas: int | None = Field(None, ge=0)
    valor_por_vida: Decimal | None = None
    valor_fixo: Decimal | None = None
    percentual_repasse: Decimal | None = None
    percentual_primeiro_mes: Decimal | None = None
    imposto_percentual: Decimal | None = None
    primeira_competencia: str | None = None
    grupo: str | None = Field(None, max_length=100)
    observacoes: str | None = None
    status: str | None = None
    encerrado_em: date | None = None


class LancamentoIn(BaseModel):
    vidas: int = Field(..., ge=0)
    # Um dos dois: por vida (K = vidas x valor) ou valor fixo do mes.
    valor_por_vida: Decimal | None = None
    valor_fixo: Decimal | None = None
    # Vazio = regra do contrato (100% no primeiro mes, 30% depois).
    percentual_repasse: Decimal | None = None
    imposto_percentual: Decimal | None = None
    pago: bool = False
    observacoes: str | None = Field(None, max_length=2000)


class LancarSugestoes(BaseModel):
    contrato_ids: list[UUID] | None = None


class CompetenciaIn(BaseModel):
    nf_numero: str | None = Field(None, max_length=40)
    nf_emitida_em: date | None = None
    recebido_em: date | None = None
    observacoes: str | None = Field(None, max_length=2000)


class DescontoIn(BaseModel):
    descricao: str = Field(..., min_length=1, max_length=200)
    valor: Decimal


class DaOportunidade(BaseModel):
    oportunidade_id: UUID


# ── Apoio ────────────────────────────────────────────────────────────

def _422(e: Exception):
    raise HTTPException(422, str(e))


def _competencia(texto: str) -> date:
    try:
        return regras.competencia_de_texto(texto)
    except regras.RepasseInvalido as e:
        _422(e)


def _competencia_opcional(texto: str | None) -> date | None:
    if texto is None or not str(texto).strip():
        return None
    return _competencia(texto)


def _hoje() -> date:
    return datetime.now(TZ_SP).date()


def _cnpj_ou_none(bruto: str | None) -> str | None:
    if bruto is None or not str(bruto).strip():
        return None
    num = cnpj_svc.normalizar(bruto)
    if not cnpj_svc.valido(num):
        raise HTTPException(422, "CNPJ inválido.")
    return num


def _contrato_json(row) -> dict:
    d = dict(row)
    d["cnpj_formatado"] = cnpj_svc.formatar(d["cnpj"]) if d.get("cnpj") else None
    if d.get("primeira_competencia"):
        d["primeira_competencia"] = regras.competencia_texto(d["primeira_competencia"])
    return d


def _lancamento_json(row) -> dict:
    d = dict(row)
    d["competencia"] = regras.competencia_texto(d["competencia"])
    return d


async def _contrato(conn, contrato_id: UUID) -> dict:
    row = await conn.fetchrow(
        f"""
        SELECT {_CAMPOS_CONTRATO}
          FROM repasse_contratos c
          LEFT JOIN oportunidades o ON o.id = c.oportunidade_id
         WHERE c.id = $1
        """,
        contrato_id,
    )
    if row is None:
        raise HTTPException(404, "Contrato não encontrado.")
    return dict(row)


async def _sugestao(conn, contrato: dict, competencia: date) -> dict:
    """
    O que o lancamento do mes seria se ninguem mexesse: os numeros do mes
    anterior (vidas e valor por vida, ou o valor fixo), ou os do contrato
    quando ainda nao ha mes anterior; percentual pela regra do primeiro mes.
    """
    anterior = await conn.fetchrow(
        """
        SELECT vidas, valor_por_vida, valor_contrato
          FROM repasse_lancamentos
         WHERE contrato_id = $1 AND competencia < $2
         ORDER BY competencia DESC
         LIMIT 1
        """,
        contrato["id"], competencia,
    )
    if anterior is not None:
        vidas = anterior["vidas"]
        if anterior["valor_por_vida"] is not None:
            vpv, fixo = anterior["valor_por_vida"], None
        else:
            vpv, fixo = None, anterior["valor_contrato"]
    else:
        vidas = contrato["vidas"] or 0
        if contrato["modalidade"] == "por_vida":
            vpv, fixo = contrato["valor_por_vida"], None
        else:
            vpv, fixo = None, contrato["valor_fixo"]

    primeiro = regras.eh_primeiro_mes(
        competencia, contrato["primeira_competencia"], anterior is not None,
    )
    pct = regras.percentual_do_mes(
        primeiro, contrato["percentual_repasse"], contrato["percentual_primeiro_mes"],
    )
    k = regras.valor_do_contrato(vidas, valor_por_vida=vpv, valor_fixo=fixo)
    calc = regras.calcular(k, pct, contrato["imposto_percentual"])
    return {
        "vidas": vidas,
        "valor_por_vida": vpv,
        "valor_fixo": fixo,
        "primeiro_mes": primeiro,
        **calc.como_dict(),
    }


def _vale_no_mes(contrato: dict, competencia: date) -> bool:
    return regras.contrato_vale_na_competencia(
        competencia, contrato["data_venda"], contrato["status"], contrato["encerrado_em"],
    )


async def _gravar_lancamento(
    conn, contrato: dict, competencia: date, payload: LancamentoIn, user: dict,
) -> dict:
    if not _vale_no_mes(contrato, competencia):
        raise HTTPException(
            422,
            f"{regras.rotulo_competencia(competencia)} está fora da vigência do contrato "
            f"(venda em {contrato['data_venda']:%d/%m/%Y}"
            + (f", encerrado em {contrato['encerrado_em']:%d/%m/%Y}" if contrato["encerrado_em"] else "")
            + ").",
        )

    try:
        k = regras.valor_do_contrato(
            payload.vidas,
            valor_por_vida=payload.valor_por_vida,
            valor_fixo=payload.valor_fixo,
        )
    except regras.RepasseInvalido as e:
        _422(e)

    tem_anterior = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM repasse_lancamentos WHERE contrato_id = $1 AND competencia < $2)",
        contrato["id"], competencia,
    )
    primeiro = regras.eh_primeiro_mes(competencia, contrato["primeira_competencia"], tem_anterior)
    pct = (
        payload.percentual_repasse
        if payload.percentual_repasse is not None
        else regras.percentual_do_mes(
            primeiro, contrato["percentual_repasse"], contrato["percentual_primeiro_mes"],
        )
    )
    imp = (
        payload.imposto_percentual
        if payload.imposto_percentual is not None
        else contrato["imposto_percentual"]
    )
    try:
        calc = regras.calcular(k, pct, imp)
    except regras.RepasseInvalido as e:
        _422(e)

    vpv = regras.dinheiro(payload.valor_por_vida) if payload.valor_por_vida is not None else None
    obs = (payload.observacoes or "").strip() or None

    row = await conn.fetchrow(
        """
        INSERT INTO repasse_lancamentos (
            contrato_id, competencia, vidas, valor_por_vida, valor_contrato,
            percentual_repasse, valor_repasse, imposto_percentual,
            valor_imposto, valor_liquido, primeiro_mes, pago, observacoes,
            lancado_por, atualizado_por
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $14)
        ON CONFLICT (contrato_id, competencia) DO UPDATE SET
            vidas = EXCLUDED.vidas,
            valor_por_vida = EXCLUDED.valor_por_vida,
            valor_contrato = EXCLUDED.valor_contrato,
            percentual_repasse = EXCLUDED.percentual_repasse,
            valor_repasse = EXCLUDED.valor_repasse,
            imposto_percentual = EXCLUDED.imposto_percentual,
            valor_imposto = EXCLUDED.valor_imposto,
            valor_liquido = EXCLUDED.valor_liquido,
            primeiro_mes = EXCLUDED.primeiro_mes,
            pago = EXCLUDED.pago,
            observacoes = EXCLUDED.observacoes,
            atualizado_por = EXCLUDED.atualizado_por,
            atualizado_em = NOW()
        RETURNING *
        """,
        contrato["id"], competencia, payload.vidas, vpv, calc.valor_contrato,
        calc.percentual_repasse, calc.valor_repasse, calc.imposto_percentual,
        calc.valor_imposto, calc.valor_liquido, primeiro, payload.pago, obs,
        user["id"],
    )

    # O primeiro lancamento do contrato fixa o mes do premio de venda.
    if primeiro and contrato["primeira_competencia"] is None:
        await conn.execute(
            "UPDATE repasse_contratos SET primeira_competencia = $1 WHERE id = $2",
            competencia, contrato["id"],
        )
    return _lancamento_json(row)


async def _contratos_do_mes(conn, competencia: date) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT {_CAMPOS_CONTRATO}
          FROM repasse_contratos c
          LEFT JOIN oportunidades o ON o.id = c.oportunidade_id
         WHERE date_trunc('month', c.data_venda)::date <= $1
           AND (c.status = 'ativo'
                OR date_trunc('month', c.encerrado_em)::date >= $1
                OR EXISTS (SELECT 1 FROM repasse_lancamentos l
                            WHERE l.contrato_id = c.id AND l.competencia = $1))
         ORDER BY o.numero NULLS LAST, c.grupo NULLS LAST, c.razao_social
        """,
        competencia,
    )
    return [dict(r) for r in rows]


async def _fechamento(conn, competencia: date) -> tuple[dict, list[dict]]:
    comp = await conn.fetchrow(
        """
        SELECT c.nf_numero, c.nf_emitida_em, c.recebido_em, c.observacoes,
               c.atualizado_em, u.nome AS atualizado_por_nome
          FROM repasse_competencias c
          LEFT JOIN usuarios u ON u.id = c.atualizado_por
         WHERE c.competencia = $1
        """,
        competencia,
    )
    descontos = await conn.fetch(
        """
        SELECT d.id, d.descricao, d.valor, d.criado_em, u.nome AS criado_por_nome
          FROM repasse_descontos d
          LEFT JOIN usuarios u ON u.id = d.criado_por
         WHERE d.competencia = $1
         ORDER BY d.criado_em
        """,
        competencia,
    )
    fechamento = dict(comp) if comp else {
        "nf_numero": None, "nf_emitida_em": None, "recebido_em": None,
        "observacoes": None, "atualizado_em": None, "atualizado_por_nome": None,
    }
    return fechamento, [dict(d) for d in descontos]


async def _garantir_competencia(conn, competencia: date, user: dict) -> None:
    await conn.execute(
        """
        INSERT INTO repasse_competencias (competencia, atualizado_por)
        VALUES ($1, $2)
        ON CONFLICT (competencia) DO NOTHING
        """,
        competencia, user["id"],
    )


async def _historico(conn, ate: date, meses: int = 6) -> list[dict]:
    inicio = regras.somar_meses(ate, -(meses - 1))
    rows = await conn.fetch(
        """
        SELECT l.competencia,
               SUM(l.valor_contrato) AS valor_contrato,
               SUM(l.valor_repasse)  AS valor_repasse,
               SUM(l.valor_liquido)  AS valor_liquido,
               COUNT(*)              AS contratos
          FROM repasse_lancamentos l
         WHERE l.competencia BETWEEN $1 AND $2
         GROUP BY l.competencia
        """,
        inicio, ate,
    )
    por_mes = {r["competencia"]: dict(r) for r in rows}
    descontos = await conn.fetch(
        """
        SELECT competencia, SUM(valor) AS total
          FROM repasse_descontos
         WHERE competencia BETWEEN $1 AND $2
         GROUP BY competencia
        """,
        inicio, ate,
    )
    desc = {r["competencia"]: r["total"] for r in descontos}
    saida = []
    for i in range(meses):
        c = regras.somar_meses(inicio, i)
        r = por_mes.get(c, {})
        liquido = regras.dinheiro(r.get("valor_liquido"))
        saida.append({
            "competencia": regras.competencia_texto(c),
            "rotulo": regras.rotulo_competencia(c),
            "valor_contrato": regras.dinheiro(r.get("valor_contrato")),
            "valor_repasse": regras.dinheiro(r.get("valor_repasse")),
            "valor_liquido": liquido,
            "valor_nf": liquido - regras.dinheiro(desc.get(c)),
            "contratos": int(r.get("contratos") or 0),
        })
    return saida


# ── Painel do mes ────────────────────────────────────────────────────

@router.get("/painel")
async def painel(
    competencia: str | None = Query(None, description="AAAA-MM; vazio = mês corrente"),
    conn=Depends(get_conn),
):
    comp = _competencia(competencia) if competencia else regras.competencia_de_data(_hoje())
    contratos = await _contratos_do_mes(conn, comp)

    lancs = await conn.fetch(
        """
        SELECT l.*, u.nome AS atualizado_por_nome
          FROM repasse_lancamentos l
          LEFT JOIN usuarios u ON u.id = l.atualizado_por
         WHERE l.competencia = $1
        """,
        comp,
    )
    por_contrato = {r["contrato_id"]: _lancamento_json(r) for r in lancs}

    linhas = []
    pendentes = 0
    for c in contratos:
        lanc = por_contrato.get(c["id"])
        sugestao = None
        if lanc is None:
            if _vale_no_mes(c, comp):
                pendentes += 1
            sugestao = await _sugestao(conn, c, comp)
        linhas.append({
            "contrato": _contrato_json(c),
            "lancamento": lanc,
            "sugestao": sugestao,
        })

    fechamento, descontos = await _fechamento(conn, comp)
    tot = regras.totais(list(por_contrato.values()), descontos)
    return {
        "competencia": regras.competencia_texto(comp),
        "rotulo": regras.rotulo_competencia(comp),
        "anterior": regras.competencia_texto(regras.somar_meses(comp, -1)),
        "seguinte": regras.competencia_texto(regras.somar_meses(comp, 1)),
        "linhas": linhas,
        "lancados": len(por_contrato),
        "pendentes": pendentes,
        "totais": tot,
        "descontos": descontos,
        "fechamento": fechamento,
        "proximo_passo": regras.proximo_passo(
            comp, pendentes, tot["valor_nf"], fechamento["nf_numero"], fechamento["recebido_em"],
        ),
        "historico": await _historico(conn, comp),
    }


# ── Lancamentos ──────────────────────────────────────────────────────

@router.put("/contratos/{contrato_id}/lancamentos/{competencia}")
async def gravar_lancamento(
    contrato_id: UUID,
    competencia: str,
    payload: LancamentoIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    comp = _competencia(competencia)
    async with conn.transaction():
        contrato = await _contrato(conn, contrato_id)
        return await _gravar_lancamento(conn, contrato, comp, payload, user)


@router.delete("/contratos/{contrato_id}/lancamentos/{competencia}", status_code=204)
async def apagar_lancamento(
    contrato_id: UUID,
    competencia: str,
    conn=Depends(get_conn),
):
    comp = _competencia(competencia)
    async with conn.transaction():
        contrato = await _contrato(conn, contrato_id)
        apagado = await conn.fetchval(
            "DELETE FROM repasse_lancamentos WHERE contrato_id = $1 AND competencia = $2 RETURNING id",
            contrato_id, comp,
        )
        if apagado is None:
            raise HTTPException(404, "Lançamento não encontrado.")
        # Sem lancamento nenhum, o contrato volta a esperar o primeiro mes.
        if contrato["primeira_competencia"] == comp:
            resta = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM repasse_lancamentos WHERE contrato_id = $1)",
                contrato_id,
            )
            if not resta:
                await conn.execute(
                    "UPDATE repasse_contratos SET primeira_competencia = NULL WHERE id = $1",
                    contrato_id,
                )


@router.post("/competencias/{competencia}/lancar-sugestoes")
async def lancar_sugestoes(
    competencia: str,
    payload: LancarSugestoes,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Confirma de uma vez os contratos pendentes do mes com a sugestao (os
    numeros do mes anterior). Sem `contrato_ids`, todos os pendentes.
    Lancamento que ja existe nao e tocado.
    """
    comp = _competencia(competencia)
    filtro = set(payload.contrato_ids) if payload.contrato_ids else None
    gravados = []
    async with conn.transaction():
        for c in await _contratos_do_mes(conn, comp):
            if filtro is not None and c["id"] not in filtro:
                continue
            if not _vale_no_mes(c, comp):
                continue
            existe = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM repasse_lancamentos WHERE contrato_id = $1 AND competencia = $2)",
                c["id"], comp,
            )
            if existe:
                continue
            s = await _sugestao(conn, c, comp)
            gravados.append(await _gravar_lancamento(
                conn, c, comp,
                LancamentoIn(
                    vidas=s["vidas"], valor_por_vida=s["valor_por_vida"],
                    valor_fixo=s["valor_fixo"],
                ),
                user,
            ))
    return {"lancados": len(gravados), "lancamentos": gravados}


# ── Fechamento: nota e descontos ─────────────────────────────────────

@router.put("/competencias/{competencia}")
async def gravar_competencia(
    competencia: str,
    payload: CompetenciaIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    comp = _competencia(competencia)
    nf = (payload.nf_numero or "").strip() or None
    if payload.nf_emitida_em and not nf:
        raise HTTPException(422, "Informe o número da nota junto com a data de emissão.")
    if payload.recebido_em and not nf:
        raise HTTPException(422, "Recebimento só depois da nota emitida.")
    await conn.execute(
        """
        INSERT INTO repasse_competencias
            (competencia, nf_numero, nf_emitida_em, recebido_em, observacoes, atualizado_por)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (competencia) DO UPDATE SET
            nf_numero = EXCLUDED.nf_numero,
            nf_emitida_em = EXCLUDED.nf_emitida_em,
            recebido_em = EXCLUDED.recebido_em,
            observacoes = EXCLUDED.observacoes,
            atualizado_por = EXCLUDED.atualizado_por,
            atualizado_em = NOW()
        """,
        comp, nf, payload.nf_emitida_em, payload.recebido_em,
        (payload.observacoes or "").strip() or None, user["id"],
    )
    fechamento, _ = await _fechamento(conn, comp)
    return fechamento


@router.post("/competencias/{competencia}/descontos", status_code=201)
async def novo_desconto(
    competencia: str,
    payload: DescontoIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    comp = _competencia(competencia)
    valor = regras.dinheiro(payload.valor)
    if valor <= 0:
        raise HTTPException(422, "Desconto precisa ser maior que zero.")
    descricao = payload.descricao.strip()
    if not descricao:
        raise HTTPException(422, "Descreva o desconto.")
    async with conn.transaction():
        await _garantir_competencia(conn, comp, user)
        row = await conn.fetchrow(
            """
            INSERT INTO repasse_descontos (competencia, descricao, valor, criado_por)
            VALUES ($1, $2, $3, $4)
            RETURNING id, descricao, valor, criado_em
            """,
            comp, descricao, valor, user["id"],
        )
    return dict(row)


@router.delete("/descontos/{desconto_id}", status_code=204)
async def apagar_desconto(desconto_id: UUID, conn=Depends(get_conn)):
    apagado = await conn.fetchval(
        "DELETE FROM repasse_descontos WHERE id = $1 RETURNING id", desconto_id,
    )
    if apagado is None:
        raise HTTPException(404, "Desconto não encontrado.")


# ── Contratos ────────────────────────────────────────────────────────

@router.get("/contratos")
async def listar_contratos(
    status: str | None = Query(None),
    q: str | None = Query(None, max_length=120),
    conn=Depends(get_conn),
):
    if status is not None and status not in regras.STATUS:
        raise HTTPException(422, "Status deve ser 'ativo' ou 'encerrado'.")
    texto = (q or "").strip()
    digitos = cnpj_svc.normalizar(texto)
    rows = await conn.fetch(
        f"""
        SELECT {_CAMPOS_CONTRATO},
               ul.competencia     AS ultima_competencia,
               ul.vidas           AS ultimas_vidas,
               ul.valor_contrato  AS ultimo_valor_contrato,
               ul.valor_liquido   AS ultimo_valor_liquido
          FROM repasse_contratos c
          LEFT JOIN oportunidades o ON o.id = c.oportunidade_id
          LEFT JOIN LATERAL (
                SELECT l.competencia, l.vidas, l.valor_contrato, l.valor_liquido
                  FROM repasse_lancamentos l
                 WHERE l.contrato_id = c.id
                 ORDER BY l.competencia DESC
                 LIMIT 1
          ) ul ON TRUE
         WHERE ($1::text IS NULL OR c.status = $1)
           AND ($2::text IS NULL
                OR c.razao_social ILIKE $2
                OR c.grupo ILIKE $2
                OR o.numero ILIKE $2
                OR ($3::text IS NOT NULL AND c.cnpj LIKE $3))
         ORDER BY c.status, o.numero NULLS LAST, c.grupo NULLS LAST, c.razao_social
        """,
        status,
        f"%{texto}%" if texto else None,
        f"%{digitos}%" if len(digitos) >= 3 else None,
    )
    saida = []
    for r in rows:
        d = _contrato_json(r)
        if d.get("ultima_competencia"):
            d["ultima_competencia"] = regras.competencia_texto(d["ultima_competencia"])
        saida.append(d)
    return saida


@router.get("/contratos/{contrato_id}")
async def obter_contrato(contrato_id: UUID, conn=Depends(get_conn)):
    contrato = await _contrato(conn, contrato_id)
    lancs = await conn.fetch(
        """
        SELECT l.*, u.nome AS atualizado_por_nome
          FROM repasse_lancamentos l
          LEFT JOIN usuarios u ON u.id = l.atualizado_por
         WHERE l.contrato_id = $1
         ORDER BY l.competencia DESC
        """,
        contrato_id,
    )
    lista = [_lancamento_json(l) for l in lancs]
    return {
        **_contrato_json(contrato),
        "lancamentos": lista,
        "totais": regras.totais(lista),
    }


async def _checar_cnpj_livre(conn, cnpj: str | None, ignorar_id: UUID | None = None) -> None:
    if cnpj is None:
        return
    outro = await conn.fetchrow(
        """
        SELECT id, razao_social FROM repasse_contratos
         WHERE cnpj = $1 AND status = 'ativo' AND ($2::uuid IS NULL OR id <> $2)
        """,
        cnpj, ignorar_id,
    )
    if outro:
        raise HTTPException(
            409,
            f"Já existe contrato ativo para o CNPJ {cnpj_svc.formatar(cnpj)} "
            f"({outro['razao_social']}).",
        )


@router.post("/contratos", status_code=201)
async def criar_contrato(
    payload: ContratoNovo,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    cnpj = _cnpj_ou_none(payload.cnpj)
    primeira = _competencia_opcional(payload.primeira_competencia)
    try:
        regras.validar_contrato(
            payload.modalidade, payload.valor_por_vida, payload.valor_fixo,
            payload.percentual_repasse, payload.percentual_primeiro_mes,
            payload.imposto_percentual,
        )
    except regras.RepasseInvalido as e:
        _422(e)

    async with conn.transaction():
        await _checar_cnpj_livre(conn, cnpj)
        if payload.oportunidade_id is not None:
            existe = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM oportunidades WHERE id = $1)", payload.oportunidade_id,
            )
            if not existe:
                raise HTTPException(422, "Oportunidade não encontrada.")
        conta_id = payload.conta_id
        if conta_id is None and cnpj is not None:
            conta_id = await conn.fetchval("SELECT id FROM contas WHERE cnpj = $1", cnpj)
        novo = await conn.fetchval(
            """
            INSERT INTO repasse_contratos (
                oportunidade_id, conta_id, cnpj, razao_social, data_venda,
                modalidade, vidas, valor_por_vida, valor_fixo,
                percentual_repasse, percentual_primeiro_mes, primeira_competencia,
                imposto_percentual, grupo, observacoes, criado_por, atualizado_por
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $16)
            RETURNING id
            """,
            payload.oportunidade_id, conta_id, cnpj, payload.razao_social.strip(),
            payload.data_venda, payload.modalidade, payload.vidas,
            regras.dinheiro(payload.valor_por_vida) if payload.valor_por_vida is not None else None,
            regras.dinheiro(payload.valor_fixo) if payload.valor_fixo is not None else None,
            regras.percentual(payload.percentual_repasse),
            regras.percentual(payload.percentual_primeiro_mes),
            primeira,
            regras.percentual(payload.imposto_percentual),
            (payload.grupo or "").strip() or None,
            (payload.observacoes or "").strip() or None,
            user["id"],
        )
    return _contrato_json(await _contrato(conn, novo))


@router.patch("/contratos/{contrato_id}")
async def editar_contrato(
    contrato_id: UUID,
    payload: ContratoPatch,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    campos = payload.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(422, "Nada para alterar.")

    async with conn.transaction():
        atual = await _contrato(conn, contrato_id)
        novo = {**atual}
        if "cnpj" in campos:
            novo["cnpj"] = _cnpj_ou_none(campos["cnpj"])
        if "primeira_competencia" in campos:
            novo["primeira_competencia"] = _competencia_opcional(campos["primeira_competencia"])
        for k in ("razao_social", "data_venda", "modalidade", "vidas", "valor_por_vida",
                  "valor_fixo", "percentual_repasse", "percentual_primeiro_mes",
                  "imposto_percentual", "grupo", "observacoes", "status", "encerrado_em"):
            if k in campos:
                novo[k] = campos[k]

        if novo["razao_social"] is None or not str(novo["razao_social"]).strip():
            raise HTTPException(422, "Razão social não pode ficar vazia.")
        if novo["data_venda"] is None:
            raise HTTPException(422, "Data da venda não pode ficar vazia.")
        if novo["status"] not in regras.STATUS:
            raise HTTPException(422, "Status deve ser 'ativo' ou 'encerrado'.")
        if novo["status"] == "encerrado":
            novo["encerrado_em"] = novo["encerrado_em"] or _hoje()
            if novo["encerrado_em"] < novo["data_venda"]:
                raise HTTPException(422, "Encerramento antes da data da venda.")
        else:
            novo["encerrado_em"] = None
        try:
            regras.validar_contrato(
                novo["modalidade"], novo["valor_por_vida"], novo["valor_fixo"],
                novo["percentual_repasse"], novo["percentual_primeiro_mes"],
                novo["imposto_percentual"],
            )
        except regras.RepasseInvalido as e:
            _422(e)
        if novo["status"] == "ativo":
            await _checar_cnpj_livre(conn, novo["cnpj"], ignorar_id=contrato_id)

        conta_id = atual["conta_id"]
        if "cnpj" in campos and novo["cnpj"] and novo["cnpj"] != atual["cnpj"]:
            conta_id = await conn.fetchval("SELECT id FROM contas WHERE cnpj = $1", novo["cnpj"])

        await conn.execute(
            """
            UPDATE repasse_contratos SET
                cnpj = $2, razao_social = $3, data_venda = $4, modalidade = $5,
                vidas = $6, valor_por_vida = $7, valor_fixo = $8,
                percentual_repasse = $9, percentual_primeiro_mes = $10,
                primeira_competencia = $11, imposto_percentual = $12,
                grupo = $13, observacoes = $14, status = $15, encerrado_em = $16,
                conta_id = $17, atualizado_por = $18, atualizado_em = NOW()
             WHERE id = $1
            """,
            contrato_id, novo["cnpj"], str(novo["razao_social"]).strip(),
            novo["data_venda"], novo["modalidade"], novo["vidas"],
            regras.dinheiro(novo["valor_por_vida"]) if novo["valor_por_vida"] is not None else None,
            regras.dinheiro(novo["valor_fixo"]) if novo["valor_fixo"] is not None else None,
            regras.percentual(novo["percentual_repasse"]),
            regras.percentual(novo["percentual_primeiro_mes"]),
            novo["primeira_competencia"],
            regras.percentual(novo["imposto_percentual"]),
            (novo["grupo"] or "").strip() or None,
            (novo["observacoes"] or "").strip() or None,
            novo["status"], novo["encerrado_em"], conta_id, user["id"],
        )
    return _contrato_json(await _contrato(conn, contrato_id))


# ── A partir da oportunidade conquistada ─────────────────────────────

async def _data_da_conquista(conn, oportunidade_id: UUID) -> date | None:
    quando = await conn.fetchval(
        """
        SELECT MAX(criado_em) FROM oportunidade_eventos
         WHERE oportunidade_id = $1 AND tipo = 'status' AND para = 'conquistado'
        """,
        oportunidade_id,
    )
    return quando.astimezone(TZ_SP).date() if quando else None


async def _itens_da_ultima_proposta(conn, oportunidade_id: UUID) -> list[dict]:
    """
    CNPJs da proposta que valeu: a ultima aprovada, ou a ultima versao.
    """
    proposta_id = await conn.fetchval(
        """
        SELECT id FROM propostas
         WHERE oportunidade_id = $1
         ORDER BY (aprovada_em IS NOT NULL) DESC, versao DESC
         LIMIT 1
        """,
        oportunidade_id,
    )
    if proposta_id is None:
        return []
    rows = await conn.fetch(
        """
        SELECT conta_id, cnpj, razao_social, vidas, mensalidade
          FROM proposta_itens
         WHERE proposta_id = $1
         ORDER BY ordem
        """,
        proposta_id,
    )
    return [dict(r) for r in rows]


@router.get("/oportunidades")
async def oportunidades_conquistadas(
    q: str | None = Query(None, max_length=120),
    conn=Depends(get_conn),
):
    """
    Oportunidades conquistadas com algum CNPJ da proposta ainda sem
    contrato ativo -- de onde nasce o contrato novo, sem redigitar.
    """
    texto = (q or "").strip()
    rows = await conn.fetch(
        """
        SELECT o.id, o.numero, c.razao_social, c.cnpj, o.valor_mensalidade
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
         WHERE o.status = 'conquistado'
           AND ($1::text IS NULL OR o.numero ILIKE $1 OR c.razao_social ILIKE $1)
         ORDER BY o.atualizado_em DESC
         LIMIT 50
        """,
        f"%{texto}%" if texto else None,
    )
    ativos = {
        r["cnpj"] for r in await conn.fetch(
            "SELECT cnpj FROM repasse_contratos WHERE status = 'ativo' AND cnpj IS NOT NULL"
        )
    }
    saida = []
    for r in rows:
        itens = await _itens_da_ultima_proposta(conn, r["id"]) or [{
            "conta_id": None, "cnpj": r["cnpj"], "razao_social": r["razao_social"],
            "vidas": None, "mensalidade": r["valor_mensalidade"],
        }]
        livres = [i for i in itens if i["cnpj"] not in ativos]
        if not livres:
            continue
        saida.append({
            "id": r["id"],
            "numero": r["numero"],
            "razao_social": r["razao_social"],
            "cnpj_formatado": cnpj_svc.formatar(r["cnpj"]),
            "data_conquista": await _data_da_conquista(conn, r["id"]),
            "cnpjs_sem_contrato": [
                {**i, "cnpj_formatado": cnpj_svc.formatar(i["cnpj"])} for i in livres
            ],
        })
    return saida


@router.post("/contratos/da-oportunidade", status_code=201)
async def contratos_da_oportunidade(
    payload: DaOportunidade,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Um contrato por CNPJ da proposta da oportunidade conquistada, em valor
    fixo (a mensalidade da proposta) e com as vidas dela. CNPJ que ja tem
    contrato ativo fica de fora.
    """
    async with conn.transaction():
        opp = await conn.fetchrow(
            """
            SELECT o.id, o.status, o.conta_id, o.valor_mensalidade, c.cnpj, c.razao_social
              FROM oportunidades o JOIN contas c ON c.id = o.conta_id
             WHERE o.id = $1
            """,
            payload.oportunidade_id,
        )
        if opp is None:
            raise HTTPException(404, "Oportunidade não encontrada.")
        if opp["status"] != "conquistado":
            raise HTTPException(422, "Só oportunidade conquistada vira contrato.")
        data_venda = await _data_da_conquista(conn, opp["id"]) or _hoje()
        itens = await _itens_da_ultima_proposta(conn, opp["id"]) or [{
            "conta_id": opp["conta_id"], "cnpj": opp["cnpj"],
            "razao_social": opp["razao_social"], "vidas": None,
            "mensalidade": opp["valor_mensalidade"] or Decimal("0"),
        }]
        criados = []
        for it in itens:
            ja = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM repasse_contratos WHERE cnpj = $1 AND status = 'ativo')",
                it["cnpj"],
            )
            if ja:
                continue
            conta_id = it["conta_id"] or await conn.fetchval(
                "SELECT id FROM contas WHERE cnpj = $1", it["cnpj"],
            )
            novo = await conn.fetchval(
                """
                INSERT INTO repasse_contratos (
                    oportunidade_id, conta_id, cnpj, razao_social, data_venda,
                    modalidade, vidas, valor_fixo, criado_por, atualizado_por
                )
                VALUES ($1, $2, $3, $4, $5, 'valor_fixo', $6, $7, $8, $8)
                RETURNING id
                """,
                opp["id"], conta_id, it["cnpj"], it["razao_social"], data_venda,
                it["vidas"], regras.dinheiro(it["mensalidade"]), user["id"],
            )
            criados.append(_contrato_json(await _contrato(conn, novo)))
    if not criados:
        raise HTTPException(409, "Todos os CNPJs desta oportunidade já têm contrato ativo.")
    return {"criados": criados}
