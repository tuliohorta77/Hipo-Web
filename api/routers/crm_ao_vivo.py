"""
HIPO — CRM: transcrição AO VIVO da reunião (prova de conceito).

Montado em /crm/agenda, módulo 'crm', como o resto da agenda. As regras
moram em services/ao_vivo.py (puras); aqui só orquestração.

O fluxo da tela "Reunião ao vivo":

  1. POST /tarefas/{tarefa_id}/ao-vivo      abre uma sessão de captura
  2. POST /ao-vivo/{sessao_id}/falas        lotes de falas, a cada ~10 s
  3. POST /ao-vivo/{sessao_id}/encerrar     o último lote e o fim
  4. GET  /tarefas/{tarefa_id}/ao-vivo      tudo o que foi captado, as
                                            métricas e a comparação com a
                                            transcrição do Meet

O áudio NUNCA chega aqui. Quem transcreve é o Chrome do vendedor; o
servidor só recebe texto. É o que mantém a EC2 fora do caminho do áudio e
o custo de transcrição em zero.

Por que um router próprio e não mais rotas em crm_agenda.py: aquele arquivo
já passa de 2 mil linhas, e a captura ao vivo é uma prova de conceito que
pode sair inteira se o reconhecimento do navegador não servir. Separada,
sai apagando um arquivo e uma linha do main.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status as http
from pydantic import BaseModel, Field, field_validator

from database import get_conn
from routers.auth import usuario_atual
from services import ao_vivo as regras
from services.permissao import eh_gestao

router = APIRouter()

Canal = Literal["vendedor", "cliente"]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# ── Modelos ──────────────────────────────────────────────────────────


class AbrirIn(BaseModel):
    canais: list[Canal] = Field(min_length=1, max_length=2)
    navegador: str | None = Field(default=None, max_length=120)

    @field_validator("canais")
    @classmethod
    def _sem_repetir(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


class FalaIn(BaseModel):
    seq: int = Field(ge=0)
    canal: Canal
    inicio: datetime
    fim: datetime | None = None
    texto: str = Field(max_length=regras.MAX_CARACTERES_FALA)
    confianca: float | None = Field(default=None, ge=0, le=1)


class ErroIn(BaseModel):
    canal: Canal | None = None
    erro: str = Field(max_length=200)
    em: datetime | None = None


class LoteIn(BaseModel):
    falas: list[FalaIn] = Field(default_factory=list, max_length=regras.MAX_FALAS_POR_LOTE)
    erros: list[ErroIn] = Field(default_factory=list, max_length=regras.MAX_ERROS_POR_LOTE)


class SessaoOut(BaseModel):
    id: UUID
    reuniao_id: UUID
    usuario_id: UUID
    usuario_nome: str | None = None
    iniciada_em: datetime
    encerrada_em: datetime | None
    navegador: str | None
    canais: list[str]
    erros: list[dict]
    falas: int = 0


class LoteOut(BaseModel):
    recebidas: int
    gravadas: int


class FalaOut(BaseModel):
    sessao_id: UUID
    seq: int
    canal: str
    inicio: datetime
    fim: datetime | None
    texto: str


class MetricasOut(BaseModel):
    falas: int
    palavras_vendedor: int
    palavras_cliente: int
    palavras_total: int
    proporcao_vendedor_pct: int | None


class ComparacaoOut(BaseModel):
    palavras_meet: int
    palavras_ao_vivo: int
    cobertura_pct: int


class AoVivoOut(BaseModel):
    tarefa_id: UUID
    reuniao_id: UUID
    titulo: str
    inicio: datetime
    duracao_min: int
    empresa: str | None
    google_link: str | None
    pode_capturar: bool
    motivo_bloqueio: str | None
    sessoes: list[SessaoOut]
    falas: list[FalaOut]
    metricas: MetricasOut
    comparacao: ComparacaoOut | None


# ── Leitura ──────────────────────────────────────────────────────────


async def _reuniao_ou_404(conn, tarefa_id: UUID):
    row = await conn.fetchrow(
        """
        SELECT r.id AS reuniao_id, r.modalidade, r.duracao_min, r.google_link,
               r.link_video,
               t.id AS tarefa_id, t.titulo, t.prazo AS inicio, t.cancelada_em,
               t.responsavel_id,
               COALESCE(c1.razao_social, c2.razao_social) AS empresa
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
          LEFT JOIN contas c1 ON c1.id = t.conta_id
          LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
          LEFT JOIN contas c2 ON c2.id = o.conta_id
         WHERE r.tarefa_id = $1
        """,
        tarefa_id,
    )
    if row is None:
        raise HTTPException(404, "Esta tarefa não é uma reunião da agenda.")
    return row


async def _pode_capturar(conn, row, user) -> bool:
    participantes = await conn.fetch(
        "SELECT usuario_id FROM reuniao_participantes WHERE reuniao_id = $1",
        row["reuniao_id"],
    )
    return regras.pode_capturar(
        usuario_id=user["id"],
        eh_gestao=eh_gestao(user.get("cargo")),
        anfitriao_id=row["responsavel_id"],
        participantes=[p["usuario_id"] for p in participantes],
    )


def _motivo(row, agora: datetime) -> str | None:
    return regras.motivo_para_nao_abrir(
        inicio=row["inicio"],
        duracao_min=row["duracao_min"],
        agora=agora,
        cancelada=row["cancelada_em"] is not None,
        modalidade=row["modalidade"],
    )


def _json_lista(valor) -> list:
    if valor is None:
        return []
    if isinstance(valor, str):
        valor = json.loads(valor)
    return list(valor) if isinstance(valor, list) else []


def _sessao(row, falas: int = 0) -> dict:
    return {
        "id": row["id"],
        "reuniao_id": row["reuniao_id"],
        "usuario_id": row["usuario_id"],
        "usuario_nome": row.get("usuario_nome") if hasattr(row, "get") else None,
        "iniciada_em": row["iniciada_em"],
        "encerrada_em": row["encerrada_em"],
        "navegador": row["navegador"],
        "canais": list(row["canais"] or []),
        "erros": _json_lista(row["erros"]),
        "falas": falas,
    }


async def _sessao_do_usuario_ou_404(conn, sessao_id: UUID, user, travar: bool = False):
    """
    A sessão só aceita texto de quem a abriu. De outro usuário devolve 404,
    e não 403: dizer "existe, mas não é sua" já é dizer demais.
    """
    sql = """
        SELECT s.*, NULL::text AS usuario_nome
          FROM reuniao_sessoes_ao_vivo s
         WHERE s.id = $1
    """
    if travar:
        sql += " FOR UPDATE"
    row = await conn.fetchrow(sql, sessao_id)
    if row is None or str(row["usuario_id"]) != str(user["id"]):
        raise HTTPException(404, "Sessão de captura não encontrada.")
    return row


async def _gravar_lote(conn, sessao, lote: LoteIn) -> LoteOut:
    """Grava falas (ignorando reenvio) e anexa os erros relatados."""
    falas = [
        (f, regras.limpar_texto(f.texto)) for f in lote.falas
    ]
    falas = [(f, t) for f, t in falas if t]
    gravadas = 0
    if falas:
        linhas = await conn.fetch(
            """
            INSERT INTO reuniao_falas_ao_vivo
                   (sessao_id, seq, canal, inicio, fim, texto, confianca)
            SELECT $1, x.seq, x.canal, x.inicio, x.fim, x.texto, x.confianca
              FROM unnest($2::int[], $3::text[], $4::timestamptz[],
                          $5::timestamptz[], $6::text[], $7::real[])
                   AS x(seq, canal, inicio, fim, texto, confianca)
            ON CONFLICT (sessao_id, seq) DO NOTHING
            RETURNING 1
            """,
            sessao["id"],
            [f.seq for f, _ in falas],
            [f.canal for f, _ in falas],
            [f.inicio for f, _ in falas],
            [f.fim for f, _ in falas],
            [t for _, t in falas],
            [f.confianca for f, _ in falas],
        )
        gravadas = len(linhas)
    if lote.erros:
        novos = [
            {
                "canal": e.canal,
                "erro": e.erro,
                "em": (e.em or _agora()).isoformat(),
            }
            for e in lote.erros
        ]
        juntos = regras.juntar_erros(_json_lista(sessao["erros"]), novos)
        await conn.execute(
            "UPDATE reuniao_sessoes_ao_vivo SET erros = $2::jsonb WHERE id = $1",
            sessao["id"], json.dumps(juntos, ensure_ascii=False),
        )
    return LoteOut(recebidas=len(lote.falas), gravadas=gravadas)


# ── Rotas ────────────────────────────────────────────────────────────


@router.get("/tarefas/{tarefa_id}/ao-vivo", response_model=AoVivoOut)
async def obter(
    tarefa_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Tudo o que foi captado nesta reunião, de todas as sessões, em ordem de
    horário. Mais as métricas da barra e, quando a transcrição do Meet já
    chegou, a comparação com ela.
    """
    row = await _reuniao_ou_404(conn, tarefa_id)
    agora = _agora()

    sessoes = await conn.fetch(
        """
        SELECT s.*, u.nome AS usuario_nome,
               (SELECT count(*) FROM reuniao_falas_ao_vivo f
                 WHERE f.sessao_id = s.id) AS qtd_falas
          FROM reuniao_sessoes_ao_vivo s
          JOIN usuarios u ON u.id = s.usuario_id
         WHERE s.reuniao_id = $1
         ORDER BY s.iniciada_em
        """,
        row["reuniao_id"],
    )
    falas = await conn.fetch(
        """
        SELECT f.sessao_id, f.seq, f.canal, f.inicio, f.fim, f.texto
          FROM reuniao_falas_ao_vivo f
          JOIN reuniao_sessoes_ao_vivo s ON s.id = f.sessao_id
         WHERE s.reuniao_id = $1
         ORDER BY f.inicio, f.sessao_id, f.seq
        """,
        row["reuniao_id"],
    )
    falas_d = [dict(f) for f in falas]

    comparacao = None
    entradas = await conn.fetchval(
        """
        SELECT entradas FROM reuniao_transcricoes
         WHERE reuniao_id = $1 AND status = 'pronta'
        """,
        row["reuniao_id"],
    )
    if entradas is not None:
        comparacao = regras.cobertura(
            [f["texto"] for f in falas_d],
            [e.get("texto") or "" for e in _json_lista(entradas) if isinstance(e, dict)],
        )

    motivo = _motivo(row, agora)
    return {
        "tarefa_id": row["tarefa_id"],
        "reuniao_id": row["reuniao_id"],
        "titulo": row["titulo"],
        "inicio": row["inicio"],
        "duracao_min": row["duracao_min"],
        "empresa": row["empresa"],
        "google_link": row["google_link"] or row["link_video"],
        "pode_capturar": motivo is None and await _pode_capturar(conn, row, user),
        "motivo_bloqueio": motivo,
        "sessoes": [
            {**_sessao(s, s["qtd_falas"]), "usuario_nome": s["usuario_nome"]}
            for s in sessoes
        ],
        "falas": falas_d,
        "metricas": regras.metricas(falas_d),
        "comparacao": comparacao,
    }


@router.post(
    "/tarefas/{tarefa_id}/ao-vivo",
    response_model=SessaoOut,
    status_code=http.HTTP_201_CREATED,
)
async def abrir(
    tarefa_id: UUID,
    payload: AbrirIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Liga a captura. Encerra, na mesma transação, a sessão que o MESMO
    usuário tivesse deixado aberta nesta reunião (aba fechada, navegador
    que travou): duas sessões vivas da mesma pessoa gravariam a mesma fala
    duas vezes.
    """
    row = await _reuniao_ou_404(conn, tarefa_id)
    motivo = _motivo(row, _agora())
    if motivo:
        raise HTTPException(422, motivo)
    if not await _pode_capturar(conn, row, user):
        raise HTTPException(
            403,
            "Só o anfitrião, um participante da reunião ou a gestão podem "
            "ligar a transcrição ao vivo.",
        )

    async with conn.transaction():
        await conn.execute(
            """
            UPDATE reuniao_sessoes_ao_vivo
               SET encerrada_em = GREATEST(NOW(), iniciada_em)
             WHERE reuniao_id = $1 AND usuario_id = $2 AND encerrada_em IS NULL
            """,
            row["reuniao_id"], user["id"],
        )
        sessao = await conn.fetchrow(
            """
            INSERT INTO reuniao_sessoes_ao_vivo
                   (reuniao_id, usuario_id, navegador, canais)
            VALUES ($1, $2, $3, $4)
            RETURNING *, NULL::text AS usuario_nome
            """,
            row["reuniao_id"], user["id"], payload.navegador, payload.canais,
        )
    return {**_sessao(sessao), "usuario_nome": user.get("nome")}


@router.post("/ao-vivo/{sessao_id}/falas", response_model=LoteOut)
async def gravar_falas(
    sessao_id: UUID,
    payload: LoteIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Um lote de falas. Reenvio do mesmo lote não duplica (seq único por
    sessão). Sessão encerrada recusa com 409: o último lote viaja no
    próprio encerrar.
    """
    async with conn.transaction():
        sessao = await _sessao_do_usuario_ou_404(conn, sessao_id, user, travar=True)
        if sessao["encerrada_em"] is not None:
            raise HTTPException(409, "Esta sessão de captura já foi encerrada.")
        return await _gravar_lote(conn, sessao, payload)


@router.post("/ao-vivo/{sessao_id}/encerrar", response_model=SessaoOut)
async def encerrar(
    sessao_id: UUID,
    payload: LoteIn | None = None,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Grava o último lote e fecha a sessão. Encerrar de novo é inofensivo:
    devolve a sessão como está, sem mexer no horário do primeiro
    encerramento.
    """
    async with conn.transaction():
        sessao = await _sessao_do_usuario_ou_404(conn, sessao_id, user, travar=True)
        if sessao["encerrada_em"] is None:
            if payload is not None:
                await _gravar_lote(conn, sessao, payload)
            await conn.execute(
                """
                UPDATE reuniao_sessoes_ao_vivo
                   SET encerrada_em = GREATEST(NOW(), iniciada_em)
                 WHERE id = $1
                """,
                sessao_id,
            )
        atual = await conn.fetchrow(
            "SELECT *, NULL::text AS usuario_nome FROM reuniao_sessoes_ao_vivo WHERE id = $1",
            sessao_id,
        )
        qtd = await conn.fetchval(
            "SELECT count(*) FROM reuniao_falas_ao_vivo WHERE sessao_id = $1", sessao_id,
        )
    return {**_sessao(atual, qtd), "usuario_nome": user.get("nome")}
