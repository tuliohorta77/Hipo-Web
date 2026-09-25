"""
HIPO - Relatorios: tabela dinamica sobre a base do CRM + relatorios salvos.

O catalogo de campos e a montagem do SQL moram em services/relatorios.py,
como funcoes puras. Aqui: validacao de entrada, execucao, e o CRUD dos
relatorios salvos.

DECISOES

  * Modulo 'crm' (todo cargo valido), e nao um modulo proprio. O que muda
    de um cargo para outro e o RECORTE, e o recorte e do servidor
    (services/permissao.escopo_de_visao): gestao ve a base inteira,
    operacional ve so o que e seu. Modulo novo so valeria depois de todo
    mundo relogar, em troca de nenhuma separacao que o recorte ja nao faca.

  * A consulta e POST porque o corpo (linhas, colunas, valores, filtros) nao
    cabe com dignidade numa query string. Continua sendo LEITURA: roda em
    transacao READ ONLY, com statement_timeout, e fica na lista de
    IGNORADAS de services/atividade.py -- montar relatorio nao e producao
    comercial.

  * Relatorio salvo e do dono. Compartilhar deixa os outros VEREM e
    DUPLICAREM, nunca editarem: um relatorio que muda sozinho porque o
    colega mexeu nele e um numero em que ninguem confia. E os dados de um
    relatorio compartilhado continuam passando pelo recorte de quem ABRE,
    nao de quem criou -- compartilhar a montagem nao compartilha a visao.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status as http
from pydantic import BaseModel, Field, field_validator

from database import get_conn
from routers.auth import usuario_atual
from services import relatorios as rel
from services.permissao import escopo_de_visao

router = APIRouter()

TIMEOUT_CONSULTA = "20s"
MAX_BYTES_CONFIG = 20_000


# ── Schemas ──────────────────────────────────────────────────────────

class RefCampo(BaseModel):
    campo: str = Field(..., min_length=1, max_length=60)
    granularidade: str | None = Field(None, max_length=20)


class RefMedida(BaseModel):
    campo: str = Field(..., min_length=1, max_length=60)
    agregacao: str = Field("contagem", max_length=30)


class FiltroIn(BaseModel):
    campo: str = Field(..., min_length=1, max_length=60)
    granularidade: str | None = Field(None, max_length=20)
    operador: str = Field("em", max_length=10)
    valores: list[str | None] = Field(default_factory=list)
    minimo: str | None = Field(None, max_length=40)
    maximo: str | None = Field(None, max_length=40)
    texto: str | None = Field(None, max_length=200)


class PeriodoIn(BaseModel):
    data_ref: str = Field(..., min_length=1, max_length=60)
    inicio: date
    fim: date


class ConsultaIn(BaseModel):
    fonte: str = Field(..., min_length=1, max_length=40)
    periodo: PeriodoIn
    linhas: list[RefCampo] = Field(default_factory=list)
    colunas: list[RefCampo] = Field(default_factory=list)
    valores: list[RefMedida] = Field(default_factory=list)
    filtros: list[FiltroIn] = Field(default_factory=list)


class CelulaRef(BaseModel):
    campo: str = Field(..., min_length=1, max_length=60)
    granularidade: str | None = Field(None, max_length=20)
    valor: str | None = None


class RegistrosIn(ConsultaIn):
    celula: list[CelulaRef] = Field(default_factory=list)
    limite: int = Field(100, ge=1, le=rel.MAX_REGISTROS_PAGINA)
    deslocamento: int = Field(0, ge=0)


class ValoresIn(ConsultaIn):
    campo: str = Field(..., min_length=1, max_length=60)
    granularidade: str | None = Field(None, max_length=20)
    busca: str | None = Field(None, max_length=100)


class SalvoIn(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    descricao: str | None = Field(None, max_length=500)
    config: dict
    compartilhado: bool = False

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Dê um nome ao relatório.")
        return v

    @field_validator("descricao")
    @classmethod
    def _descricao(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class DuplicarIn(BaseModel):
    nome: str | None = Field(None, max_length=120)


# ── Execucao ─────────────────────────────────────────────────────────

def _consulta_dict(payload: ConsultaIn) -> dict:
    return {
        "fonte": payload.fonte,
        "periodo": payload.periodo.model_dump(),
        "linhas": [x.model_dump() for x in payload.linhas],
        "colunas": [x.model_dump() for x in payload.colunas],
        "valores": [x.model_dump() for x in payload.valores],
        "filtros": [x.model_dump() for x in payload.filtros],
    }


def _num(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


async def _executar(conn, sql: str, params: list) -> list:
    """
    Leitura isolada: READ ONLY e com teto de tempo. Relatorio e a unica
    tela em que o usuario escolhe o formato da consulta, entao e a unica
    que precisa de freio proprio.
    """
    try:
        async with conn.transaction(readonly=True):
            await conn.execute(f"SET LOCAL statement_timeout = '{TIMEOUT_CONSULTA}'")
            return await conn.fetch(sql, *params)
    except asyncpg.QueryCanceledError:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "A consulta demorou demais. Reduza o período ou acrescente um filtro.",
        )


def _invalida(e: rel.ConsultaInvalida) -> HTTPException:
    return HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ── Catalogo e consulta ──────────────────────────────────────────────

@router.get("/catalogo")
async def catalogo(user=Depends(usuario_atual)):
    """Fontes, campos com nome claro, agregacoes e limites. Sem SQL."""
    return rel.catalogo()


@router.post("/consulta")
async def consultar(
    payload: ConsultaIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    consulta = _consulta_dict(payload)
    escopo = escopo_de_visao(user.get("cargo"), user["id"])
    try:
        sql, params, meta = rel.montar_consulta(consulta, escopo)
    except rel.ConsultaInvalida as e:
        raise _invalida(e)

    linhas = await _executar(conn, sql, params)
    n_l, n_c = len(meta["linhas"]), len(meta["colunas"])
    n_d = n_l + n_c

    if len(linhas) > rel.MAX_CELULAS:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "O resultado ficou grande demais para uma tabela. Use menos campos em "
            "linhas, um agrupamento de data maior (mês em vez de dia) ou um filtro.",
        )

    celulas = []
    total = 0
    for r in linhas:
        g = [bool(r[f"g{i}"]) for i in range(n_d)]
        cel = {
            "d": [r[f"d{i}"] for i in range(n_d)],
            "g": g,
            "n": r["n"],
            "v": [_num(r[f"m{j}"]) for j in range(len(meta["medidas"]))],
        }
        if all(g):
            total = r["n"]
        celulas.append(cel)

    combinacoes = rel.contar_combinacoes_coluna(celulas, n_l, n_c)
    if combinacoes > rel.MAX_COMBINACOES_COLUNA:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"A tabela teria {combinacoes} colunas (o limite é "
            f"{rel.MAX_COMBINACOES_COLUNA}). Mova um campo de "
            f"colunas para linhas, ou filtre os valores.",
        )

    return {
        **rel.descrever_resultado(meta, consulta),
        "celulas": celulas,
        "total_registros": total,
    }


@router.post("/registros")
async def registros(
    payload: RegistrosIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Drilldown: os registros que compoem uma celula da tabela. Cada linha
    traz o que abrir (oportunidade ou conta), para a tela levar direto ao
    registro -- o numero agregado vira acao.
    """
    consulta = _consulta_dict(payload)
    escopo = escopo_de_visao(user.get("cargo"), user["id"])
    try:
        sql, params, meta = rel.montar_registros(
            consulta, escopo, [c.model_dump() for c in payload.celula],
            payload.limite, payload.deslocamento,
        )
    except rel.ConsultaInvalida as e:
        raise _invalida(e)

    linhas = await _executar(conn, sql, params)
    n_cols = len(meta["colunas"])
    itens = []
    for r in linhas:
        abrir = None
        for i, tipo in enumerate(meta["abrir"]):
            if r[f"a{i}"]:
                abrir = {"tipo": tipo, "id": r[f"a{i}"]}
                break
        itens.append({
            "valores": [r[f"r{i}"] for i in range(n_cols)],
            "abrir": abrir,
        })
    return {
        "colunas": meta["colunas"],
        "total": linhas[0]["total"] if linhas else 0,
        "itens": itens,
    }


@router.post("/valores")
async def valores_distintos(
    payload: ValoresIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Os valores que um campo assume no periodo, para montar o filtro."""
    consulta = _consulta_dict(payload)
    escopo = escopo_de_visao(user.get("cargo"), user["id"])
    try:
        sql, params = rel.montar_valores(
            consulta, escopo, payload.campo, payload.granularidade, payload.busca,
        )
    except rel.ConsultaInvalida as e:
        raise _invalida(e)
    linhas = await _executar(conn, sql, params)
    return {
        "itens": [{"valor": r["valor"], "n": r["n"]} for r in linhas[: rel.MAX_VALORES_DISTINTOS]],
        "truncado": len(linhas) > rel.MAX_VALORES_DISTINTOS,
    }


# ── Relatorios salvos ────────────────────────────────────────────────

_SELECT_SALVO = """
    SELECT s.id, s.usuario_id, u.nome AS dono_nome, s.nome, s.descricao,
           s.fonte, s.config, s.compartilhado, s.criado_em, s.atualizado_em
      FROM relatorios_salvos s
      JOIN usuarios u ON u.id = s.usuario_id
"""


def _serializar(r, usuario_id) -> dict:
    cfg = r["config"]
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    f = rel.FONTES.get(r["fonte"])
    return {
        "id": str(r["id"]),
        "nome": r["nome"],
        "descricao": r["descricao"],
        "fonte": r["fonte"],
        "fonte_rotulo": f.rotulo if f else "Fonte removida",
        "config": cfg,
        "compartilhado": r["compartilhado"],
        "dono_id": str(r["usuario_id"]),
        "dono_nome": r["dono_nome"],
        "eh_meu": r["usuario_id"] == usuario_id,
        "criado_em": r["criado_em"].isoformat(),
        "atualizado_em": r["atualizado_em"].isoformat(),
    }


def _validar_config(config: dict) -> str:
    try:
        rel.validar_config_salva(config)
    except rel.ConsultaInvalida as e:
        raise _invalida(e)
    bruto = json.dumps(config, ensure_ascii=False)
    if len(bruto.encode("utf-8")) > MAX_BYTES_CONFIG:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "Configuração do relatório grande demais.")
    return bruto


async def _visivel(conn, relatorio_id: UUID, usuario_id):
    """O relatorio, se for do usuario ou compartilhado. None se nao existir PARA ELE."""
    return await conn.fetchrow(
        _SELECT_SALVO + " WHERE s.id = $1 AND (s.usuario_id = $2 OR s.compartilhado)",
        relatorio_id, usuario_id,
    )


async def _do_dono(conn, relatorio_id: UUID, usuario_id):
    r = await _visivel(conn, relatorio_id, usuario_id)
    if r is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Relatório não encontrado.")
    if r["usuario_id"] != usuario_id:
        raise HTTPException(
            http.HTTP_403_FORBIDDEN,
            "Só quem criou pode alterar este relatório. Use 'Duplicar' para ter a sua cópia.",
        )
    return r


def _conflito_nome(nome: str) -> HTTPException:
    return HTTPException(http.HTTP_409_CONFLICT, f"Você já tem um relatório chamado '{nome}'.")


@router.get("/salvos")
async def listar_salvos(conn=Depends(get_conn), user=Depends(usuario_atual)):
    """Os meus primeiro, depois os compartilhados pelos colegas."""
    linhas = await conn.fetch(
        _SELECT_SALVO
        + " WHERE s.usuario_id = $1 OR s.compartilhado"
        + " ORDER BY (s.usuario_id = $1) DESC, lower(s.nome)",
        user["id"],
    )
    return [_serializar(r, user["id"]) for r in linhas]


@router.post("/salvos", status_code=http.HTTP_201_CREATED)
async def criar_salvo(payload: SalvoIn, conn=Depends(get_conn), user=Depends(usuario_atual)):
    bruto = _validar_config(payload.config)
    try:
        novo_id = await conn.fetchval(
            """
            INSERT INTO relatorios_salvos (usuario_id, nome, descricao, fonte, config, compartilhado)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            RETURNING id
            """,
            user["id"], payload.nome, payload.descricao, payload.config["fonte"],
            bruto, payload.compartilhado,
        )
    except asyncpg.UniqueViolationError:
        raise _conflito_nome(payload.nome)
    return _serializar(await _visivel(conn, novo_id, user["id"]), user["id"])


@router.put("/salvos/{relatorio_id}")
async def atualizar_salvo(
    relatorio_id: UUID, payload: SalvoIn, conn=Depends(get_conn), user=Depends(usuario_atual),
):
    await _do_dono(conn, relatorio_id, user["id"])
    bruto = _validar_config(payload.config)
    try:
        await conn.execute(
            """
            UPDATE relatorios_salvos
               SET nome = $2, descricao = $3, fonte = $4, config = $5::jsonb,
                   compartilhado = $6, atualizado_em = NOW()
             WHERE id = $1
            """,
            relatorio_id, payload.nome, payload.descricao, payload.config["fonte"],
            bruto, payload.compartilhado,
        )
    except asyncpg.UniqueViolationError:
        raise _conflito_nome(payload.nome)
    return _serializar(await _visivel(conn, relatorio_id, user["id"]), user["id"])


@router.delete("/salvos/{relatorio_id}", status_code=http.HTTP_204_NO_CONTENT)
async def excluir_salvo(relatorio_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    await _do_dono(conn, relatorio_id, user["id"])
    await conn.execute("DELETE FROM relatorios_salvos WHERE id = $1", relatorio_id)


@router.post("/salvos/{relatorio_id}/duplicar", status_code=http.HTTP_201_CREATED)
async def duplicar_salvo(
    relatorio_id: UUID, payload: DuplicarIn | None = None,
    conn=Depends(get_conn), user=Depends(usuario_atual),
):
    """
    Copia um relatorio visivel (meu ou compartilhado) para o meu perfil. A
    copia nasce privada: quem duplicou decide se quer compartilhar.
    """
    origem = await _visivel(conn, relatorio_id, user["id"])
    if origem is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Relatório não encontrado.")

    pedido = " ".join((payload.nome if payload and payload.nome else "").split())
    base = pedido or f"{origem['nome']} (cópia)"
    existentes = {
        r["n"] for r in await conn.fetch(
            "SELECT lower(btrim(nome)) AS n FROM relatorios_salvos WHERE usuario_id = $1",
            user["id"],
        )
    }
    if pedido and pedido.lower() in existentes:
        raise _conflito_nome(pedido)
    nome, i = base[:120], 2
    while nome.lower() in existentes:
        sufixo = f" ({i})"
        nome = base[: 120 - len(sufixo)] + sufixo
        i += 1

    cfg = origem["config"]
    bruto = cfg if isinstance(cfg, str) else json.dumps(cfg, ensure_ascii=False)
    novo_id = await conn.fetchval(
        """
        INSERT INTO relatorios_salvos (usuario_id, nome, descricao, fonte, config, compartilhado)
        VALUES ($1, $2, $3, $4, $5::jsonb, FALSE)
        RETURNING id
        """,
        user["id"], nome, origem["descricao"], origem["fonte"], bruto,
    )
    return _serializar(await _visivel(conn, novo_id, user["id"]), user["id"])
