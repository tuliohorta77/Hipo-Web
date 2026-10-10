"""
HIPO — Ligações: o lado do GRAVADOR (agente Windows), entrega 056.

SEM LOGIN DE USUÁRIO. Quem prova quem é o token do gravador, gerado na
tela do HIPO (POST /crm/ligacoes/gravadores) e colado uma vez no
instalador. No banco fica só o SHA-256 do token; revogar é uma linha na
tela. O token é de UMA pessoa: tudo que esse gravador manda vira ligação
dela — o agente não escolhe em nome de quem grava.

Endereço público: https://hipogestao.com.br/api/ligacoes/gravador/... (o
nginx corta o /api).

ROTAS
  POST /ligacoes/gravador/pulso                      "estou ligado" a cada
                                                     ~2 min; devolve se o
                                                     servidor aceita gravação
  POST /ligacoes/gravador/gravacoes                  terminou uma chamada:
                                                     casa com o clique e
                                                     devolve a URL de upload
  POST /ligacoes/gravador/gravacoes/{id}/concluir    subiu: confere no S3 e
                                                     começa a transcrição

O ÁUDIO NÃO PASSA POR AQUI: vai direto para o S3 pela URL assinada (ver o
cabeçalho de services/ligacao_aws.py).

RESPOSTAS DE ERRO QUE O AGENTE ENTENDE
  401  token ausente, errado ou revogado — o agente para e avisa na bandeja;
  422  gravação recusada (curta demais, formato) — o agente descarta;
  503  servidor sem S3 — o agente guarda o arquivo e tenta depois;
  409  concluir sem o arquivo no S3 — o agente sobe de novo.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from database import get_conn
from routers.permissions import modulos_do_cargo
from services import coleta_ligacao as coleta
from services import ligacao as regras
from services import ligacao_aws as aws

log = logging.getLogger("hipo.ligacoes_gravador")
router = APIRouter()


class PulsoIn(BaseModel):
    versao: str | None = Field(None, max_length=20)
    maquina: str | None = Field(None, max_length=120)


class GravacaoIn(BaseModel):
    # ISO 8601 no relógio da máquina; `agora` é o relógio da máquina no
    # momento do envio, para o servidor corrigir o desvio.
    inicio: str
    fim: str
    agora: str | None = None
    duracao_s: float
    tamanho_bytes: int
    formato: str = "flac"
    id_local: str = Field(..., min_length=8, max_length=64)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def gravador_atual(request: Request, conn=Depends(get_conn)) -> dict:
    token = regras.token_do_header(request.headers.get("authorization"))
    if not token:
        raise HTTPException(401, "Token do gravador ausente.")
    r = await conn.fetchrow(
        """
        SELECT g.*, u.nome AS usuario_nome, u.cargo AS usuario_cargo, u.ativo AS usuario_ativo
          FROM ligacao_gravadores g
          JOIN usuarios u ON u.id = g.usuario_id
         WHERE g.token_hash = $1 AND g.revogado_em IS NULL
        """,
        regras.hash_token(token),
    )
    if r is None:
        raise HTTPException(401, "Token do gravador inválido ou revogado.")
    g = dict(r)
    # Quem saiu da empresa (inativo) ou perdeu o CRM não grava mais, mesmo
    # com o token no notebook.
    if not g["usuario_ativo"] or "crm" not in modulos_do_cargo(g["usuario_cargo"]):
        raise HTTPException(401, "O usuário deste gravador não está mais ativo no HIPO.")
    return g


@router.post("/pulso")
async def pulso(body: PulsoIn, conn=Depends(get_conn), g=Depends(gravador_atual)):
    await conn.execute(
        """
        UPDATE ligacao_gravadores
           SET ultimo_contato_em = NOW(),
               versao_agente = COALESCE($2, versao_agente),
               maquina = COALESCE($3, maquina)
         WHERE id = $1
        """,
        g["id"], body.versao, body.maquina,
    )
    return {
        "ok": True,
        "usuario": g["usuario_nome"],
        "gravador": g["nome"],
        "aceita_gravacao": aws.disponivel(),
        "problemas": aws.problemas(),
        "agora": _agora().isoformat(),
    }


@router.post("/gravacoes")
async def nova_gravacao(body: GravacaoIn, conn=Depends(get_conn), g=Depends(gravador_atual)):
    if not aws.disponivel():
        raise HTTPException(503, "Servidor sem armazenamento de gravações: " + "; ".join(aws.problemas()))
    try:
        dur, tam, tipo, ext = regras.validar_gravacao(body.duracao_s, body.tamanho_bytes, body.formato)
        inicio, fim = regras.corrigir_relogio(
            regras.ler_data(body.inicio), regras.ler_data(body.fim),
            regras.ler_data(body.agora), _agora(),
        )
    except regras.LigacaoInvalida as e:
        raise HTTPException(422, str(e)) from None

    usuario_id = g["usuario_id"]

    # Reenvio da MESMA gravação (o agente caiu entre pedir a URL e subir).
    ja = await conn.fetchrow(
        "SELECT id, status, audio_s3_chave FROM ligacoes WHERE usuario_id = $1 AND gravacao_local_id = $2",
        usuario_id, body.id_local,
    )
    if ja is not None:
        # Sobe de novo só o que não chegou: ainda "enviando", ou o coletor
        # já desistiu do upload (erro sem áudio). O resto já está no S3.
        reenviar = ja["status"] == "enviando" or (ja["status"] == "erro" and not ja["audio_s3_chave"])
        if not reenviar:
            return {"ligacao_id": ja["id"], "ja_recebida": True}
        chave = regras.chave_audio(usuario_id, ja["id"], ext)
        await conn.execute(
            """
            UPDATE ligacoes SET status = 'enviando', audio_s3_chave = $2, erro = NULL,
                                atualizado_em = NOW()
             WHERE id = $1
            """,
            ja["id"], chave,
        )
        url = await asyncio.to_thread(aws.url_upload, chave, tipo)
        return {"ligacao_id": ja["id"], "upload_url": url, "content_type": tipo,
                "vinculada": None, "ja_recebida": False}

    async with conn.transaction():
        cliques = await conn.fetch(
            """
            SELECT id, clicada_em FROM ligacoes
             WHERE usuario_id = $1 AND status IN ('discando', 'sem_gravacao')
               AND clicada_em BETWEEN $2::timestamptz - $3::interval AND $2::timestamptz + $4::interval
             FOR UPDATE
            """,
            usuario_id, inicio, regras.JANELA_ANTES, regras.JANELA_DEPOIS,
        )
        # 'sem_gravacao' também casa: a gravação feita offline e enviada
        # horas depois encontra o clique que o timer já tinha dado por
        # perdido, e o reabre.
        dono = regras.casar([(r["id"], r["clicada_em"]) for r in cliques], inicio)
        if dono is not None:
            lid = dono
            await conn.execute(
                """
                UPDATE ligacoes
                   SET gravador_id = $2, inicio_em = $3, fim_em = $4, duracao_s = $5,
                       audio_s3_chave = $6, audio_bytes = $7, status = 'enviando',
                       gravacao_local_id = $8, atualizado_em = NOW()
                 WHERE id = $1
                """,
                lid, g["id"], inicio, fim, dur,
                regras.chave_audio(usuario_id, lid, ext), tam, body.id_local,
            )
        else:
            lid = await conn.fetchval(
                """
                INSERT INTO ligacoes (usuario_id, origem, gravador_id, inicio_em, fim_em,
                                      duracao_s, audio_bytes, status, gravacao_local_id)
                VALUES ($1, 'gravador', $2, $3, $4, $5, $6, 'enviando', $7)
                RETURNING id
                """,
                usuario_id, g["id"], inicio, fim, dur, tam, body.id_local,
            )
            await conn.execute(
                "UPDATE ligacoes SET audio_s3_chave = $2 WHERE id = $1",
                lid, regras.chave_audio(usuario_id, lid, ext),
            )
        await conn.execute(
            "UPDATE ligacao_gravadores SET ultimo_contato_em = NOW() WHERE id = $1", g["id"],
        )

    chave = regras.chave_audio(usuario_id, lid, ext)
    url = await asyncio.to_thread(aws.url_upload, chave, tipo)
    return {
        "ligacao_id": lid,
        "upload_url": url,
        "content_type": tipo,
        "vinculada": dono is not None,
        "ja_recebida": False,
    }


@router.post("/gravacoes/{ligacao_id}/concluir")
async def concluir(ligacao_id: UUID, conn=Depends(get_conn), g=Depends(gravador_atual)):
    lig = await coleta.linha(conn, ligacao_id)
    if lig is None or lig["usuario_id"] != g["usuario_id"]:
        raise HTTPException(404, "Gravação não encontrada.")
    if lig["status"] != "enviando":
        return {"ligacao_id": ligacao_id, "status": lig["status"]}
    try:
        tamanho = await asyncio.to_thread(aws.tamanho_no_s3, lig["audio_s3_chave"])
    except Exception as e:  # noqa: BLE001
        log.warning("ligacao %s: head_object falhou: %s", ligacao_id, e)
        raise HTTPException(503, "Não foi possível conferir o arquivo no S3. Tente de novo.") from e
    if not tamanho:
        raise HTTPException(409, "O arquivo ainda não está no servidor. Suba de novo.")
    await conn.execute(
        """
        UPDATE ligacoes SET audio_bytes = $2, status = 'transcrevendo', atualizado_em = NOW()
         WHERE id = $1 AND status = 'enviando'
        """,
        ligacao_id, tamanho,
    )
    # Pela mesma porta do timer (com a trava por ligação): a transcrição
    # começa agora, e nunca duas vezes.
    atual = await coleta.processar(conn, ligacao_id)
    return {"ligacao_id": ligacao_id, "status": atual["status"]}
