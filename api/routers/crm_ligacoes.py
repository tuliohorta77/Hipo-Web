"""
HIPO — Ligações pelo Vivo Voz Negócio (entrega 056): o lado da tela.

Módulo 'crm' (main.py): quem liga é todo cargo operacional, e módulo novo só
valeria depois de todo mundo relogar. O recorte de QUEM VÊ O QUÊ é por
linha, dentro das rotas (services/ligacao.pode_ver).

ROTAS
  POST   /crm/ligacoes                       o clique em "ligar" (antes de o
                                             softphone abrir)
  GET    /crm/ligacoes?oportunidade_id=...   aba Ligações (ou conta_id,
                                             tarefa_id), com os números do topo
  GET    /crm/ligacoes/sem-vinculo           gravações da pessoa que ainda
                                             não são de ninguém
  GET    /crm/ligacoes/{id}                  detalhe com a transcrição
  POST   /crm/ligacoes/{id}/vincular         dizer de qual oportunidade/
                                             parceiro é a gravação
  POST   /crm/ligacoes/{id}/atualizar        o "Atualizar" (mesma passada do
                                             timer)
  POST   /crm/ligacoes/{id}/resumo           refaz o resumo
  GET    /crm/ligacoes/{id}/audio            URL assinada para ouvir
  DELETE /crm/ligacoes/{id}                  descarta gravação SEM vínculo
                                             (ligação pessoal, engano)

  GET    /crm/ligacoes/gravadores            gravadores da pessoa (gestão:
                                             ?todos=true)
  POST   /crm/ligacoes/gravadores            gera o token de um gravador novo
  DELETE /crm/ligacoes/gravadores/{id}       revoga

O lado do agente (sem login, token do gravador) mora em
routers/ligacoes_gravador.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from services import coleta_ligacao as coleta
from services import ligacao as regras
from services import ligacao_aws as aws
from services import resumo_reuniao
from services.permissao import eh_gestao

log = logging.getLogger("hipo.ligacoes")
router = APIRouter()

# Dois cliques no mesmo número em menos que isto são o mesmo gesto (o
# duplo clique, o "não abriu, clica de novo"). Devolve a linha que já existe.
DEBOUNCE_CLIQUE = timedelta(seconds=20)


# ── Schemas ──────────────────────────────────────────────────────────


class CliqueIn(BaseModel):
    telefone: str = Field(..., min_length=1, max_length=40)
    contato_id: UUID | None = None
    oportunidade_id: UUID | None = None
    conta_id: UUID | None = None
    tarefa_id: UUID | None = None


class VincularIn(BaseModel):
    oportunidade_id: UUID | None = None
    conta_id: UUID | None = None
    contato_id: UUID | None = None
    tarefa_id: UUID | None = None


class GravadorIn(BaseModel):
    nome: str = Field(..., min_length=1, max_length=80)


# ── Apoio ────────────────────────────────────────────────────────────


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _gestao(user: dict) -> bool:
    return eh_gestao(user.get("cargo"))


def _json(valor):
    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except ValueError:
            return None
    return valor


def saida(lig: dict, completa: bool = False) -> dict:
    """A ligação como a tela lê. `completa` traz a conversa inteira."""
    d = {
        "id": lig["id"],
        "status": lig["status"],
        "status_rotulo": regras.ROTULO_STATUS.get(lig["status"], lig["status"]),
        "origem": lig["origem"],
        "telefone": lig.get("telefone"),
        "clicada_em": lig.get("clicada_em"),
        "inicio_em": lig.get("inicio_em"),
        "fim_em": lig.get("fim_em"),
        "duracao_s": lig.get("duracao_s"),
        "usuario_id": lig["usuario_id"],
        "usuario_nome": lig.get("usuario_nome"),
        "contato_id": lig.get("contato_id"),
        "contato_nome": lig.get("contato_nome"),
        "oportunidade_id": lig.get("oportunidade_id"),
        "oportunidade_numero": lig.get("oportunidade_numero"),
        "conta_id": lig.get("conta_id"),
        "empresa": lig.get("empresa"),
        "tarefa_id": lig.get("tarefa_id"),
        "vinculada": regras.vinculada(lig.get("oportunidade_id"), lig.get("conta_id")),
        "tem_audio": bool(lig.get("audio_s3_chave")) and lig["status"] not in ("enviando",),
        "audio_removido_em": lig.get("audio_removido_em"),
        "fala_usuario_pct": lig.get("fala_usuario_pct"),
        "transcrita_em": lig.get("transcrita_em"),
        "resumo": lig.get("resumo"),
        "proximos_passos": _json(lig.get("proximos_passos")) or [],
        "resumo_erro": lig.get("resumo_erro"),
        "erro": lig.get("erro"),
        "criado_em": lig["criado_em"],
    }
    if completa:
        d["transcricao"] = _json(lig.get("transcricao_entradas")) or []
    return d


async def _ligacao_visivel(conn, ligacao_id: UUID, user: dict) -> dict:
    lig = await coleta.linha(conn, ligacao_id)
    if lig is None or not regras.pode_ver(
        lig["usuario_id"], lig["oportunidade_id"], lig["conta_id"], user["id"], _gestao(user),
    ):
        # 404 também para "existe mas não é sua": a gravação sem vínculo de
        # outra pessoa não existe para quem não pode vê-la.
        raise HTTPException(404, "Ligação não encontrada.")
    return lig


async def _ligacao_alteravel(conn, ligacao_id: UUID, user: dict) -> dict:
    lig = await _ligacao_visivel(conn, ligacao_id, user)
    if not regras.pode_alterar(lig["usuario_id"], user["id"], _gestao(user)):
        raise HTTPException(403, "Só quem fez a ligação (ou a gestão) pode alterar.")
    return lig


async def _resolver_alvo(conn, *, oportunidade_id, conta_id, contato_id, tarefa_id) -> dict:
    """
    Confere as referências e completa o que a tarefa sabe.

    A tarefa manda: se veio tarefa, o alvo e o contato dela valem quando o
    pedido não trouxe outro. Oportunidade e conta juntas → fica a
    oportunidade (a conta dela vem pelo JOIN).
    """
    if tarefa_id is not None:
        t = await conn.fetchrow(
            "SELECT oportunidade_id, conta_id, contato_id FROM tarefas WHERE id = $1", tarefa_id,
        )
        if t is None:
            raise HTTPException(422, "Tarefa não encontrada.")
        if oportunidade_id is None and conta_id is None:
            oportunidade_id, conta_id = t["oportunidade_id"], t["conta_id"]
        elif (oportunidade_id or conta_id) not in (t["oportunidade_id"], t["conta_id"]):
            raise HTTPException(422, "A tarefa é de outra oportunidade.")
        contato_id = contato_id or t["contato_id"]
    if oportunidade_id is not None:
        conta_id = None
        if not await conn.fetchval("SELECT 1 FROM oportunidades WHERE id = $1", oportunidade_id):
            raise HTTPException(422, "Oportunidade não encontrada.")
    elif conta_id is not None:
        if not await conn.fetchval("SELECT 1 FROM contas WHERE id = $1", conta_id):
            raise HTTPException(422, "Conta não encontrada.")
    if contato_id is not None:
        if not await conn.fetchval("SELECT 1 FROM contatos WHERE id = $1", contato_id):
            raise HTTPException(422, "Contato não encontrado.")
    return {
        "oportunidade_id": oportunidade_id, "conta_id": conta_id,
        "contato_id": contato_id, "tarefa_id": tarefa_id,
    }


async def _gravador_online(conn, usuario_id) -> bool:
    ultimo = await conn.fetchval(
        """
        SELECT MAX(ultimo_contato_em) FROM ligacao_gravadores
         WHERE usuario_id = $1 AND revogado_em IS NULL
        """,
        usuario_id,
    )
    return regras.gravador_online(ultimo, _agora())


def _gravador_out(r: dict, agora: datetime) -> dict:
    return {
        "id": r["id"],
        "usuario_id": r["usuario_id"],
        "usuario_nome": r.get("usuario_nome"),
        "nome": r["nome"],
        "token_prefixo": r["token_prefixo"],
        "criado_em": r["criado_em"],
        "ultimo_contato_em": r["ultimo_contato_em"],
        "versao_agente": r["versao_agente"],
        "maquina": r["maquina"],
        "online": regras.gravador_online(r["ultimo_contato_em"], agora),
    }


# ── Gravadores (declarados ANTES de /{ligacao_id}) ───────────────────


@router.get("/gravadores")
async def listar_gravadores(
    todos: bool = False, conn=Depends(get_conn), user=Depends(usuario_atual),
):
    ver_todos = todos and _gestao(user)
    linhas = await conn.fetch(
        """
        SELECT g.*, u.nome AS usuario_nome
          FROM ligacao_gravadores g
          JOIN usuarios u ON u.id = g.usuario_id
         WHERE g.revogado_em IS NULL
           AND ($1::uuid IS NULL OR g.usuario_id = $1)
         ORDER BY u.nome, g.criado_em
        """,
        None if ver_todos else user["id"],
    )
    agora = _agora()
    return {
        "gravadores": [_gravador_out(dict(r), agora) for r in linhas],
        "disponivel": aws.disponivel(),
        "problemas": aws.problemas(),
    }


@router.post("/gravadores", status_code=http.HTTP_201_CREATED)
async def criar_gravador(body: GravadorIn, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    Gera o token de um gravador novo, para o usuário logado. O token em claro
    sai SÓ nesta resposta: a tela mostra uma vez para colar no instalador.
    """
    try:
        nome = regras.validar_nome_gravador(body.nome)
    except regras.LigacaoInvalida as e:
        raise HTTPException(422, str(e)) from None
    tok = regras.gerar_token()
    r = await conn.fetchrow(
        """
        INSERT INTO ligacao_gravadores (usuario_id, nome, token_hash, token_prefixo, criado_por)
        VALUES ($1, $2, $3, $4, $1)
        RETURNING *
        """,
        user["id"], nome, tok.hash, tok.prefixo,
    )
    d = dict(r)
    d["usuario_nome"] = user.get("nome")
    return {"gravador": _gravador_out(d, _agora()), "token": tok.token}


@router.delete("/gravadores/{gravador_id}")
async def revogar_gravador(gravador_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    r = await conn.fetchrow(
        "SELECT usuario_id FROM ligacao_gravadores WHERE id = $1 AND revogado_em IS NULL",
        gravador_id,
    )
    if r is None or not regras.pode_alterar(r["usuario_id"], user["id"], _gestao(user)):
        raise HTTPException(404, "Gravador não encontrado.")
    await conn.execute(
        "UPDATE ligacao_gravadores SET revogado_em = NOW() WHERE id = $1", gravador_id,
    )
    return {"ok": True}


# ── O clique ─────────────────────────────────────────────────────────


@router.post("", status_code=http.HTTP_201_CREATED)
async def registrar_clique(body: CliqueIn, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    O "ligar" no telefone do contato. A tela chama isto e, sem esperar,
    deixa o navegador abrir o tel: no softphone — a ligação não pode
    depender de o HIPO responder.
    """
    telefone = regras.normalizar_telefone(body.telefone)
    if not telefone:
        raise HTTPException(422, "Telefone sem número.")
    alvo = await _resolver_alvo(
        conn, oportunidade_id=body.oportunidade_id, conta_id=body.conta_id,
        contato_id=body.contato_id, tarefa_id=body.tarefa_id,
    )
    agora = _agora()
    repetido = await conn.fetchval(
        """
        SELECT id FROM ligacoes
         WHERE usuario_id = $1 AND status = 'discando' AND telefone = $2
           AND clicada_em >= $3
         ORDER BY clicada_em DESC LIMIT 1
        """,
        user["id"], telefone, agora - DEBOUNCE_CLIQUE,
    )
    if repetido:
        return saida(await coleta.linha(conn, repetido))
    lid = await conn.fetchval(
        """
        INSERT INTO ligacoes (usuario_id, oportunidade_id, conta_id, contato_id, tarefa_id,
                              telefone, origem, clicada_em, status)
        VALUES ($1, $2, $3, $4, $5, $6, 'clique', $7, 'discando')
        RETURNING id
        """,
        user["id"], alvo["oportunidade_id"], alvo["conta_id"], alvo["contato_id"],
        alvo["tarefa_id"], telefone, agora,
    )
    return saida(await coleta.linha(conn, lid))


# ── Listas ───────────────────────────────────────────────────────────


@router.get("")
async def listar(
    oportunidade_id: UUID | None = None,
    conta_id: UUID | None = None,
    tarefa_id: UUID | None = None,
    limite: int = Query(100, ge=1, le=500),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    filtros = [(c, v) for c, v in (
        ("oportunidade_id", oportunidade_id), ("conta_id", conta_id), ("tarefa_id", tarefa_id),
    ) if v is not None]
    if len(filtros) != 1:
        raise HTTPException(422, "Informe exatamente um entre oportunidade_id, conta_id e tarefa_id.")
    coluna, valor = filtros[0]
    linhas = await conn.fetch(
        f"{coleta._SELECT} WHERE l.{coluna} = $1 ORDER BY COALESCE(l.inicio_em, l.clicada_em, l.criado_em) DESC LIMIT $2",
        valor, limite,
    )
    lista = [dict(r) for r in linhas]
    return {
        "ligacoes": [saida(r) for r in lista],
        "kpis": regras.resumo_kpis(lista),
        "gravacao": {
            "disponivel": aws.disponivel(),
            "gravador_online": await _gravador_online(conn, user["id"]),
        },
    }


@router.get("/sem-vinculo")
async def sem_vinculo(
    usuario_id: UUID | None = None, conn=Depends(get_conn), user=Depends(usuario_atual),
):
    """
    Gravações que ainda não são de nenhuma oportunidade. Da própria pessoa;
    a gestão pode pedir as de alguém (?usuario_id=).
    """
    alvo = usuario_id if (usuario_id and _gestao(user)) else user["id"]
    linhas = await conn.fetch(
        f"""{coleta._SELECT}
         WHERE l.usuario_id = $1 AND l.oportunidade_id IS NULL AND l.conta_id IS NULL
           AND l.status NOT IN ('discando', 'sem_gravacao')
         ORDER BY l.criado_em DESC LIMIT 50""",
        alvo,
    )
    return {
        "ligacoes": [saida(dict(r)) for r in linhas],
        "gravador_online": await _gravador_online(conn, alvo),
    }


# ── Uma ligação ──────────────────────────────────────────────────────


@router.get("/{ligacao_id}")
async def detalhe(ligacao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    lig = await _ligacao_visivel(conn, ligacao_id, user)
    return {**saida(lig, completa=True), "pode_alterar": regras.pode_alterar(
        lig["usuario_id"], user["id"], _gestao(user))}


@router.post("/{ligacao_id}/vincular")
async def vincular(
    ligacao_id: UUID, body: VincularIn, conn=Depends(get_conn), user=Depends(usuario_atual),
):
    lig = await _ligacao_alteravel(conn, ligacao_id, user)
    if body.oportunidade_id is None and body.conta_id is None and body.tarefa_id is None:
        raise HTTPException(422, "Diga de qual oportunidade (ou parceiro) é a ligação.")
    if lig["status"] == "discando":
        raise HTTPException(409, "Essa ligação ainda não tem gravação; o vínculo já veio do clique.")
    alvo = await _resolver_alvo(
        conn, oportunidade_id=body.oportunidade_id, conta_id=body.conta_id,
        contato_id=body.contato_id, tarefa_id=body.tarefa_id,
    )
    await conn.execute(
        """
        UPDATE ligacoes
           SET oportunidade_id = $2, conta_id = $3, contato_id = $4, tarefa_id = $5,
               vinculada_por = $6, vinculada_em = NOW(), atualizado_em = NOW()
         WHERE id = $1
        """,
        ligacao_id, alvo["oportunidade_id"], alvo["conta_id"], alvo["contato_id"],
        alvo["tarefa_id"], user["id"],
    )
    return saida(await coleta.linha(conn, ligacao_id), completa=True)


@router.post("/{ligacao_id}/atualizar")
async def atualizar(ligacao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """O botão "Atualizar": a mesma passada do timer, só para esta ligação."""
    await _ligacao_visivel(conn, ligacao_id, user)
    atual = await coleta.processar(conn, ligacao_id)
    return saida(atual, completa=True)


@router.post("/{ligacao_id}/resumo")
async def refazer_resumo(ligacao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    lig = await _ligacao_alteravel(conn, ligacao_id, user)
    if lig["status"] != "pronta":
        raise HTTPException(409, "A ligação ainda não tem transcrição para resumir.")
    if not resumo_reuniao.configurado():
        raise HTTPException(503, "Resumo desligado: ANTHROPIC_API_KEY não configurada.")
    return saida(await coleta.resumir(conn, ligacao_id), completa=True)


@router.get("/{ligacao_id}/audio")
async def audio(ligacao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    lig = await _ligacao_visivel(conn, ligacao_id, user)
    if not lig.get("audio_s3_chave") or lig["status"] == "enviando":
        if lig.get("audio_removido_em"):
            raise HTTPException(410, "O áudio desta ligação já passou do prazo de guarda.")
        raise HTTPException(404, "Essa ligação não tem gravação.")
    if not aws.disponivel():
        raise HTTPException(503, "Gravações indisponíveis: S3 não configurado no servidor.")
    url = await asyncio.to_thread(aws.url_leitura, lig["audio_s3_chave"])
    return {"url": url, "expira_em_s": aws.URL_LEITURA_SEGUNDOS}


@router.delete("/{ligacao_id}")
async def descartar(ligacao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    Descarta uma gravação SEM vínculo: a ligação pessoal que o gravador
    pegou, o engano. Apaga o áudio e a linha. Ligação vinculada é histórico
    da negociação e não sai por aqui.
    """
    lig = await _ligacao_alteravel(conn, ligacao_id, user)
    if regras.vinculada(lig["oportunidade_id"], lig["conta_id"]):
        raise HTTPException(409, "Ligação vinculada a uma negociação não pode ser descartada.")
    if lig["status"] == "enviando":
        # O gravador está no meio do envio: apagar agora faria o reenvio
        # dele recriar a linha. Espera chegar e descarta depois.
        raise HTTPException(409, "A gravação ainda está chegando. Tente de novo em instantes.")
    if lig.get("audio_s3_chave") and aws.disponivel():
        try:
            await asyncio.to_thread(aws.remover, lig["audio_s3_chave"])
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Não foi possível apagar o áudio ({type(e).__name__}).") from e
    if lig.get("transcricao_job"):
        await asyncio.to_thread(aws.apagar_job, lig["transcricao_job"])
    await conn.execute("DELETE FROM ligacoes WHERE id = $1", ligacao_id)
    return {"ok": True}
