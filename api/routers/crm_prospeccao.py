"""
HIPO — CRM: Prospecção a partir da base da Receita (022).

O QUE ESTA TELA FAZ

O SDR fatia a base de Dados Abertos do CNPJ por UF, CNAE e cidade, vê quanto
daquela fatia já está no CRM e em que situação, e PUXA as empresas que quer
trabalhar. Puxar é, numa transação por CNPJ:

    1. criar a conta com os dados da Receita (ou reaproveitar a que existe);
    2. abrir a oportunidade em 'suspect', com o SDR como envolvido e a
       origem "Base da Receita";
    3. criar a tarefa de primeiro contato para o próprio SDR.

E depois da resposta, em segundo plano, o enriquecimento pela BrasilAPI
(QSA e CNAEs secundários) — o mesmo `services/enriquecimento` do botão
"Buscar na Receita", com o mesmo cache e as mesmas regras de sobrescrita.

POR QUE NÃO É IMPORTAÇÃO

A base da Receita é fonte de CONSULTA. Nada dela vira registro do CRM sem um
gesto de alguém autenticado, e o que vira carrega autor e data como qualquer
formulário: `contas.criado_por`, `oportunidades.criado_por`, o evento de
criação, a tarefa com responsável. O lote tem teto de 50 justamente para
continuar sendo escolha, e não carga.

POR QUE O ENRIQUECIMENTO VAI PARA SEGUNDO PLANO

A BrasilAPI não tem SLA e o timeout de cada fonte é 20 s. Cinquenta
consultas em série dentro da requisição passariam do limite do nginx, e o
SDR ficaria olhando um spinner para descobrir no fim que deu 504. A conta já
nasce útil com os dados da base; o enriquecimento só completa. Se ele
falhar, a conta fica com `enriquecida_em` vazio — exatamente a fila que o
resumo de enriquecimento já mostra.

PERMISSÃO

Módulo 'crm' + `requer_prospeccao` (SDR e gestão), no include_router. Ver
CARGOS_PROSPECCAO em routers/permissions.py.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import asyncpg
from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request,
)
from pydantic import BaseModel, Field, field_validator

from config import settings
from database import get_conn
from routers.auth import usuario_atual
from routers.crm_oportunidades import EnvolvidoIn, inserir_oportunidade
from routers.crm_tarefas import TarefaCriar, inserir_tarefa
from services import cnpj as cnpj_svc
from services import enriquecimento as enriq
from services import oportunidade as regras_opp
from services import prospeccao as regras
from services.prospeccao import FiltroInvalido, FiltrosFatia

log = logging.getLogger("hipo.prospeccao")

router = APIRouter()

# Teto de tempo das leituras da fatia. Uma fatia larga demais (divisão
# inteira de comércio no estado todo, com CNAE secundário) varre milhões de
# linhas; melhor devolver 422 pedindo recorte do que prender uma conexão do
# pool por um minuto.
TIMEOUT_FATIA = "15s"

# Pausa entre CNPJs no enriquecimento em segundo plano. A BrasilAPI responde
# 429 para quem a martela, e o lote não tem pressa: a conta já existe.
PAUSA_ENRIQUECIMENTO_S = 0.5

# Agregado das oportunidades da conta, para a situação de cada CNPJ. LEFT
# JOIN LATERAL com agregado sem GROUP BY devolve sempre uma linha — com
# NULL quando a conta não tem oportunidade nenhuma, que o SITUACAO_SQL lê
# com COALESCE.
FROM_FATIA = """
    FROM receita_estabelecimentos r
    LEFT JOIN contas c ON c.cnpj = r.cnpj
    LEFT JOIN LATERAL (
        SELECT bool_or(op.status IN ('ativa', 'suspensa')) AS aberta,
               bool_or(op.status = 'conquistado')          AS conquistada
          FROM oportunidades op
         WHERE op.conta_id = c.id
    ) o ON TRUE
"""


# ── Schemas ──────────────────────────────────────────────────────────

class BaseOut(BaseModel):
    carregada: bool
    referencia: str | None = None
    ufs: list[str] = []
    estabelecimentos: int | None = None
    concluida_em: datetime | None = None


class CnaeOut(BaseModel):
    codigo: str
    descricao: str


class MunicipioOut(BaseModel):
    codigo: str
    nome: str
    uf: str


class ResumoFatia(BaseModel):
    total: int
    puxaveis: int
    novas: int
    conta_sem_negocio: int
    em_negociacao: int
    clientes: int
    bloqueadas: int
    inativas: int
    # O placar do próprio SDR: o que ele já puxou e ainda está na boca do
    # funil. Puxar mais com 200 suspects parados é encher a agenda de
    # tarefa que ninguém vai fazer — o número fica ao lado do botão.
    meus_suspects_abertos: int
    minhas_puxadas_no_mes: int


class ItemFatia(BaseModel):
    cnpj: str
    cnpj_formatado: str
    razao_social: str
    nome_fantasia: str | None = None
    matriz: bool
    cnae_principal: str
    cnae_descricao: str | None = None
    porte: str | None = None
    simples: bool | None = None
    capital_social: Decimal | None = None
    data_abertura: date | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str
    telefone: str | None = None
    email: str | None = None
    situacao: str
    conta_id: UUID | None = None


class ListaFatia(BaseModel):
    itens: list[ItemFatia]
    total: int
    limit: int
    offset: int


class PuxarIn(BaseModel):
    cnpjs: list[str] = Field(..., min_length=1, max_length=regras.LIMITE_LOTE)
    # Quando o primeiro contato deve acontecer. Vazio = agora, e a tarefa
    # entra como "hoje" na fila do SDR.
    prazo: datetime | None = None
    temperatura: int = regras.TEMPERATURA_PADRAO

    @field_validator("temperatura")
    @classmethod
    def _temperatura(cls, v: int) -> int:
        if v not in regras_opp.TEMPERATURAS:
            raise ValueError("Temperatura deve ser múltiplo de 10 entre 0 e 90.")
        return v


class Puxada(BaseModel):
    cnpj: str
    razao_social: str
    conta_id: UUID
    conta_nova: bool
    oportunidade_id: UUID
    oportunidade_numero: str
    tarefa_id: UUID


class Pulada(BaseModel):
    cnpj: str
    razao_social: str | None = None
    motivo: str
    mensagem: str
    conta_id: UUID | None = None


class PuxarOut(BaseModel):
    puxadas: list[Puxada]
    puladas: list[Pulada]
    enriquecimento_em_segundo_plano: int


# ── Dependências ─────────────────────────────────────────────────────

def filtros_fatia(
    uf: list[str] = Query(default=[]),
    cnae: list[str] = Query(default=[]),
    secundarios: bool = False,
    municipio: list[str] = Query(default=[]),
    porte: list[str] = Query(default=[]),
    regime: str | None = None,
    idade_min: int | None = None,
    capital_min: Decimal | None = None,
    com_telefone: bool = False,
    com_email: bool = False,
    so_matriz: bool = False,
    q: str | None = None,
    situacao: str = Query("puxaveis", pattern="^(puxaveis|todas)$"),
) -> FiltrosFatia:
    try:
        return FiltrosFatia(
            ufs=tuple(u.strip().upper() for u in uf if u.strip()),
            cnaes=tuple(c.strip() for c in cnae if c.strip()),
            secundarios=secundarios,
            municipios=tuple(m.strip() for m in municipio if m.strip()),
            portes=tuple(p.strip() for p in porte if p.strip()),
            regime=regime or None,
            idade_min=idade_min,
            capital_min=capital_min,
            com_telefone=com_telefone,
            com_email=com_email,
            so_matriz=so_matriz,
            q=q,
            so_puxaveis=(situacao == "puxaveis"),
        ).validar()
    except FiltroInvalido as e:
        raise HTTPException(422, str(e)) from e


# ── Helpers ──────────────────────────────────────────────────────────

def _hoje() -> date:
    return datetime.now(timezone.utc).date()


async def _ler_fatia(conn, metodo: str, sql: str, *params):
    """
    Leitura da fatia com teto de tempo. Estourou -> 422 pedindo recorte.

    `SET LOCAL` só vale dentro de transação, e some sozinho no fim dela — a
    conexão volta ao pool sem o teto, que é o que se quer.
    """
    try:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL statement_timeout = '{TIMEOUT_FATIA}'")
            return await getattr(conn, metodo)(sql, *params)
    except asyncpg.exceptions.QueryCanceledError as e:
        raise HTTPException(
            422,
            "A fatia ficou grande demais para consultar de uma vez. "
            "Refine por cidade, por CNAE mais específico ou por porte.",
        ) from e


async def _origem_base(conn) -> int:
    """
    Id da origem "Base da Receita", criando-a na primeira puxada.

    A origem é o que permite medir, no funil e nos relatórios, quanto do que
    a base gera vira negócio — a pergunta que decide se a carga mensal vale
    o trabalho.
    """
    return await conn.fetchval(
        """
        INSERT INTO origens (nome, slug)
        VALUES ($1, $2)
        ON CONFLICT (slug) DO UPDATE SET nome = origens.nome
        RETURNING id
        """,
        regras.ORIGEM_NOME, regras.ORIGEM_SLUG,
    )


# ── Leitura ──────────────────────────────────────────────────────────

@router.get("/base", response_model=BaseOut)
async def base(conn=Depends(get_conn), user=Depends(usuario_atual)):
    """A última carga concluída. A tela diz de quando é o dado."""
    row = await conn.fetchrow(
        """
        SELECT referencia, ufs, estabelecimentos, concluida_em
          FROM receita_cargas
         WHERE status = 'concluida'
         ORDER BY concluida_em DESC
         LIMIT 1
        """
    )
    if row is None:
        return {"carregada": False}
    return {
        "carregada": True,
        "referencia": row["referencia"],
        "ufs": [u for u in row["ufs"].split(",") if u],
        "estabelecimentos": row["estabelecimentos"],
        "concluida_em": row["concluida_em"],
    }


@router.get("/cnaes", response_model=list[CnaeOut])
async def cnaes(
    q: str = Query(..., min_length=2, max_length=80),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Busca de CNAE para o filtro: por código (prefixo) ou por descrição.

    A descrição é comparada sem acento dos dois lados — quem digita
    "fabricacao" precisa achar "Fabricação".
    """
    termo = q.strip()
    digitos = "".join(c for c in termo if c not in ".-/ ")
    if digitos.isdigit():
        rows = await conn.fetch(
            """
            SELECT codigo, descricao FROM receita_cnaes
             WHERE codigo LIKE $1
             ORDER BY codigo LIMIT 30
            """,
            digitos + "%",
        )
    else:
        rows = await conn.fetch(
            """
            SELECT codigo, descricao FROM receita_cnaes
             WHERE translate(lower(descricao),
                             'áàâãäéèêëíìîïóòôõöúùûüç',
                             'aaaaaeeeeiiiiooooouuuuc')
                   LIKE '%' || translate(lower($1),
                             'áàâãäéèêëíìîïóòôõöúùûüç',
                             'aaaaaeeeeiiiiooooouuuuc') || '%'
             ORDER BY codigo LIMIT 30
            """,
            termo,
        )
    return [dict(r) for r in rows]


@router.get("/municipios", response_model=list[MunicipioOut])
async def municipios(
    uf: list[str] = Query(default=[]),
    q: str = Query("", max_length=80),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    ufs = [u.strip().upper() for u in uf if u.strip()]
    rows = await conn.fetch(
        """
        SELECT codigo, nome, uf FROM receita_municipios
         WHERE (cardinality($1::text[]) = 0 OR uf = ANY($1::text[]))
           AND translate(lower(nome),
                         'áàâãäéèêëíìîïóòôõöúùûüç',
                         'aaaaaeeeeiiiiooooouuuuc')
               LIKE translate(lower($2),
                         'áàâãäéèêëíìîïóòôõöúùûüç',
                         'aaaaaeeeeiiiiooooouuuuc') || '%'
         ORDER BY nome LIMIT 30
        """,
        ufs, q.strip(),
    )
    return [dict(r) for r in rows]


@router.get("/resumo", response_model=ResumoFatia)
async def resumo(
    f: FiltrosFatia = Depends(filtros_fatia),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Os números do topo da tela. Ignoram o filtro de situação de propósito:
    o resumo é justamente onde se vê quanto da fatia JÁ está no CRM.
    """
    where, params = regras.montar_where(f, _hoje())
    row = await _ler_fatia(
        conn, "fetchrow",
        f"""
        SELECT count(*)                                         AS total,
               count(*) FILTER (WHERE sit = 'nova')              AS novas,
               count(*) FILTER (WHERE sit = 'conta_sem_negocio') AS conta_sem_negocio,
               count(*) FILTER (WHERE sit = 'em_negociacao')     AS em_negociacao,
               count(*) FILTER (WHERE sit = 'cliente')           AS clientes,
               count(*) FILTER (WHERE sit = 'bloqueada')         AS bloqueadas,
               count(*) FILTER (WHERE sit = 'inativa')           AS inativas
          FROM (
            SELECT {regras.SITUACAO_SQL} AS sit
            {FROM_FATIA}
             WHERE {where}
          ) x
        """,
        *params,
    )
    meus = await conn.fetchrow(
        """
        SELECT count(*) FILTER (
                   WHERE o.status = 'ativa' AND o.fase = 'suspect'
               ) AS abertos,
               count(*) FILTER (
                   WHERE o.criado_em >= date_trunc('month', NOW())
               ) AS no_mes
          FROM oportunidades o
          JOIN origens og ON og.id = o.origem_id AND og.slug = $2
         WHERE o.criado_por = $1
        """,
        user["id"], regras.ORIGEM_SLUG,
    )
    d = dict(row)
    d["puxaveis"] = d["novas"] + d["conta_sem_negocio"]
    d["meus_suspects_abertos"] = meus["abertos"]
    d["minhas_puxadas_no_mes"] = meus["no_mes"]
    return d


@router.get("", response_model=ListaFatia)
async def listar(
    f: FiltrosFatia = Depends(filtros_fatia),
    ordem: str = Query("capital", pattern="^(capital|abertura|razao)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    where, params = regras.montar_where(f, _hoje())
    if f.so_puxaveis:
        where += f" AND ({regras.SITUACAO_SQL}) IN ('nova', 'conta_sem_negocio')"

    total = await _ler_fatia(
        conn, "fetchval", f"SELECT count(*) {FROM_FATIA} WHERE {where}", *params
    )
    n = len(params)
    rows = await _ler_fatia(
        conn, "fetch",
        f"""
        SELECT r.cnpj, r.razao_social, r.nome_fantasia, r.matriz,
               r.cnae_principal, rc.descricao AS cnae_descricao,
               r.porte, r.simples, r.capital_social, r.data_abertura,
               r.bairro, m.nome AS municipio, r.uf, r.telefone, r.email,
               {regras.SITUACAO_SQL} AS situacao,
               c.id AS conta_id
          {FROM_FATIA}
          LEFT JOIN receita_cnaes rc     ON rc.codigo = r.cnae_principal
          LEFT JOIN receita_municipios m ON m.codigo  = r.municipio_codigo
         WHERE {where}
         ORDER BY {regras.ORDENACOES[ordem]}
         LIMIT ${n + 1} OFFSET ${n + 2}
        """,
        *params, limit, offset,
    )
    itens = []
    for r in rows:
        d = dict(r)
        d["cnpj_formatado"] = cnpj_svc.formatar(d["cnpj"])
        d["porte"] = regras.PORTES.get(d["porte"] or "") if d["porte"] else None
        itens.append(d)
    return {"itens": itens, "total": total, "limit": limit, "offset": offset}


# ── Puxar ────────────────────────────────────────────────────────────

async def _puxar_um(conn, cnpj: str, user, origem_id: int, prazo: datetime,
                    temperatura: int) -> dict:
    """
    Um CNPJ, numa transação própria. Devolve {'puxada': ...} ou {'pulada': ...}.

    O `FOR UPDATE` na conta serializa dois SDRs puxando a mesma empresa ao
    mesmo tempo: o segundo espera o primeiro terminar, vê a oportunidade
    aberta e é pulado — em vez de abrir uma segunda.
    """
    async with conn.transaction():
        base = await conn.fetchrow(
            """
            SELECT r.*, rc.descricao AS cnae_descricao, m.nome AS municipio_nome
              FROM receita_estabelecimentos r
              LEFT JOIN receita_cnaes rc     ON rc.codigo = r.cnae_principal
              LEFT JOIN receita_municipios m ON m.codigo  = r.municipio_codigo
             WHERE r.cnpj = $1
            """,
            cnpj,
        )
        if base is None:
            return {"pulada": {"cnpj": cnpj, "motivo": "fora_da_base"}}

        conta = await conn.fetchrow(
            """
            SELECT id, razao_social, ativo, nao_prospectar, enriquecida_em
              FROM contas WHERE cnpj = $1 FOR UPDATE
            """,
            cnpj,
        )
        conta_nova = False
        if conta is None:
            cnae = await enriq.garantir_cnae(
                conn, base["cnae_principal"], base["cnae_descricao"]
            )
            dados = regras.conta_da_base(dict(base), base["municipio_nome"])
            dados["vertical_id"] = (cnae or {}).get("vertical_id")
            dados["criado_por"] = user["id"]
            colunas = list(dados.keys())
            marcadores = ", ".join(f"${i}" for i in range(1, len(colunas) + 1))
            conta_id = await conn.fetchval(
                f"""
                INSERT INTO contas ({', '.join(colunas)}) VALUES ({marcadores})
                ON CONFLICT (cnpj) DO NOTHING
                RETURNING id
                """,
                *dados.values(),
            )
            if conta_id is None:
                # Outro SDR criou a conta entre o SELECT e o INSERT. Segue
                # pelo caminho da conta existente, já travada.
                conta = await conn.fetchrow(
                    """
                    SELECT id, razao_social, ativo, nao_prospectar, enriquecida_em
                      FROM contas WHERE cnpj = $1 FOR UPDATE
                    """,
                    cnpj,
                )
            else:
                conta_nova = True
                razao = dados["razao_social"]
                enriquecer = True

        if not conta_nova:
            conta_id = conta["id"]
            razao = conta["razao_social"]
            enriquecer = conta["enriquecida_em"] is None
            agregado = await conn.fetchrow(
                """
                SELECT COALESCE(bool_or(status IN ('ativa', 'suspensa')), FALSE) AS aberta,
                       COALESCE(bool_or(status = 'conquistado'), FALSE)          AS conquistada
                  FROM oportunidades WHERE conta_id = $1
                """,
                conta_id,
            )
            sit = regras.situacao(
                existe=True,
                ativa=conta["ativo"],
                nao_prospectar=conta["nao_prospectar"],
                tem_conquistada=agregado["conquistada"],
                tem_aberta=agregado["aberta"],
            )
            if sit not in regras.PUXAVEIS:
                return {"pulada": {
                    "cnpj": cnpj, "razao_social": razao, "motivo": sit,
                    "conta_id": conta_id,
                }}

        oportunidade_id = await inserir_oportunidade(
            conn,
            conta_id=conta_id,
            fase="suspect",
            temperatura=temperatura,
            origem_id=origem_id,
            envolvidos=[EnvolvidoIn(usuario_id=user["id"], papel="SDR")],
            criado_por=user["id"],
        )
        tarefa = TarefaCriar(
            tipo=regras.TIPO_TAREFA,
            titulo=regras.titulo_primeiro_contato(razao, base["nome_fantasia"]),
            responsavel_id=user["id"],
            prazo=prazo,
            oportunidade_id=oportunidade_id,
        )
        tarefa_id = await inserir_tarefa(
            conn, tarefa, oportunidade_id, None, user["id"], None
        )
        numero = await conn.fetchval(
            "SELECT numero FROM oportunidades WHERE id = $1", oportunidade_id
        )
    return {
        "puxada": {
            "cnpj": cnpj,
            "razao_social": razao,
            "conta_id": conta_id,
            "conta_nova": conta_nova,
            "oportunidade_id": oportunidade_id,
            "oportunidade_numero": numero,
            "tarefa_id": tarefa_id,
        },
        "enriquecer": enriquecer,
    }


async def enriquecer_contas(pool, alvos: list[tuple[UUID, str]], user_id) -> None:
    """
    Enriquecimento pela BrasilAPI depois da resposta. Nunca levanta exceção.

    Conexão própria: a da requisição já voltou ao pool quando isto roda. Com
    pool (produção), pega uma dele; sem pool (suíte, ou pool que não subiu no
    boot), abre uma direta — o mesmo fallback de `database.get_conn`.
    """
    if not alvos:
        return
    try:
        if pool is not None:
            async with pool.acquire() as conn:
                await _enriquecer_em(conn, alvos, user_id)
        else:
            conn = await asyncpg.connect(settings.DATABASE_URL)
            try:
                await _enriquecer_em(conn, alvos, user_id)
            finally:
                await conn.close()
    except Exception:  # pragma: no cover - blindagem de tarefa em segundo plano
        log.exception("prospeccao: enriquecimento em segundo plano falhou")


async def _enriquecer_em(conn, alvos: list[tuple[UUID, str]], user_id) -> None:
    for i, (conta_id, cnpj) in enumerate(alvos):
        if i:
            await asyncio.sleep(PAUSA_ENRIQUECIMENTO_S)
        try:
            dados, avisos = await enriq.consultar(
                conn, cnpj, user_id=user_id, conta_id=conta_id
            )
            if dados is None:
                log.info("prospeccao: %s sem enriquecimento (%s)", cnpj, "; ".join(avisos))
                continue
            async with conn.transaction():
                await enriq.aplicar(conn, conta_id, dados, user_id)
        except Exception:
            log.exception("prospeccao: falha ao enriquecer %s", cnpj)


@router.post("/puxar", response_model=PuxarOut)
async def puxar(
    payload: PuxarIn,
    request: Request,
    background: BackgroundTasks,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Puxa até 50 CNPJs da base para o CRM. Ver o cabeçalho do módulo.

    Cada CNPJ é independente: o que não pode entrar é devolvido em `puladas`
    com o motivo, e não derruba o resto do lote.
    """
    validos, pulados_lote = regras.preparar_lote(payload.cnpjs)
    prazo = payload.prazo or datetime.now(timezone.utc)
    origem_id = await _origem_base(conn)

    puxadas: list[dict] = []
    puladas: list[dict] = list(pulados_lote)
    alvos: list[tuple[UUID, str]] = []

    for cnpj in validos:
        try:
            r = await _puxar_um(conn, cnpj, user, origem_id, prazo, payload.temperatura)
        except asyncpg.PostgresError as e:
            log.exception("prospeccao: falha ao puxar %s", cnpj)
            puladas.append({
                "cnpj": cnpj, "motivo": "erro",
                "mensagem": f"Não foi possível puxar ({type(e).__name__}).",
            })
            continue
        if "pulada" in r:
            puladas.append(r["pulada"])
            continue
        puxadas.append(r["puxada"])
        if r["enriquecer"]:
            alvos.append((r["puxada"]["conta_id"], cnpj))

    for p in puladas:
        p.setdefault("mensagem", regras.MOTIVOS_PULO.get(p["motivo"], p["motivo"]))

    if alvos:
        background.add_task(
            enriquecer_contas, getattr(request.app.state, "pool", None),
            alvos, user["id"],
        )

    return {
        "puxadas": puxadas,
        "puladas": puladas,
        "enriquecimento_em_segundo_plano": len(alvos),
    }
