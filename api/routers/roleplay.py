"""
HIPO — Carreira · Roleplay com IA (RP-1: sessão gravada; RP-2: nota).

O executivo treina por voz com uma IA no papel do cliente. A conversa vai
direto do navegador para o Gemini Live; aqui ficam:

  * a tela inteira (GET /carreira/roleplay): liberação, termo, próximo
    roleplay, cenários do cargo, histórico e números do mês;
  * a abertura da sessão, que confere quiz, termo, limite do dia e
    orçamento e devolve um TOKEN EFÊMERO com a persona travada;
  * o token novo de cada reconexão (a conexão do Live troca a cada ~10 min);
  * o encerramento: gravação para o S3, transcrição, tokens e custo;
  * a AVALIAÇÃO contra o Roteiro de Vendas (RP-2), em segundo plano logo
    depois do encerramento: mesma régua e mesma checagem de evidência do
    scorecard das reuniões, em tabelas próprias (não vaza para o Monitor).
    A gestão ajusta item a item e valida com selo.

Liberação: quiz final APROVADO da trilha de roteiro do cargo (EV hoje).
Gestão treina sem trava e fica fora das médias. Quem vê a sessão de outra
pessoa: só a gestão, em modo leitura — mesma regra da UC e do PDI.

CUSTO DE IA: só o Franqueado vê (gasto do mês e custo por sessão). Para o
resto do time a mensagem de orçamento esgotado é neutra.

Montado em main.py com prefixo /carreira e módulo 'crm', como o PDI:
ninguém precisa relogar.
Regras puras em services/roleplay.py; personas em roleplay_cenarios.py.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from config import settings
from database import get_conn
from routers.auth import usuario_atual
from routers.uc import _hoje, _pessoa_alvo, eh_gestao
from services import anexo as s3
from services import roleplay as regras
from services import roleplay_avaliacao as rav
from services import roteiro_scorecard as sc
from services.roleplay_cenarios import CENARIOS, ROTULO_BLOCO, cenarios_do_cargo, montar_instrucao
from services.tarefa import FUSO_OPERACAO

router = APIRouter()

FUSO = str(FUSO_OPERACAO)
log = logging.getLogger("hipo.roleplay")

# Avaliação em "aguardando" há mais que isto caiu no meio (processo
# reiniciado durante a chamada): a tela oferece avaliar de novo.
AGUARDANDO_TRAVADA = timedelta(minutes=5)


class NovaSessao(BaseModel):
    cenario_id: str


class NotaItem(BaseModel):
    nota: int | None = None


def ve_custo(user: dict) -> bool:
    """Custo de IA (por sessão e do mês) é assunto do Franqueado."""
    return user.get("cargo") == "Franqueado"


# ── Apoio ────────────────────────────────────────────────────────────

def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _erro(e: regras.RoleplayInvalido):
    raise HTTPException(e.status, str(e))


def _cenario_publico(cid: str, c: dict) -> dict:
    """O que o executivo pode ler. Nunca a persona."""
    return {
        "id": cid,
        "titulo": c["titulo"],
        "formato": c["formato"],
        "bloco": c["bloco"],
        "bloco_rotulo": ROTULO_BLOCO[c["bloco"]],
        "dificuldade": c["dificuldade"],
        "duracao_alvo_min": c["duracao_alvo_min"],
        "objetivo": c["objetivo"],
        "briefing": c["briefing"],
        "versao": c["versao"],
    }


def _json(valor):
    if isinstance(valor, str):
        return json.loads(valor)
    return valor


def _sessao_out(r: dict, completa: bool = False, custo: bool = False,
                diagnostico: bool = False) -> dict:
    c = CENARIOS.get(r["cenario_id"])
    out = {
        "id": str(r["id"]),
        "cenario_id": r["cenario_id"],
        "cenario_titulo": c["titulo"] if c else r["cenario_id"],
        "formato": c["formato"] if c else None,
        "bloco_rotulo": ROTULO_BLOCO[c["bloco"]] if c else None,
        "status": r["status"],
        "conta_media": r["conta_media"],
        "iniciada_em": r["iniciada_em"],
        "encerrada_em": r["encerrada_em"],
        "duracao_s": r["duracao_s"],
        "motivo_fim": r["motivo_fim"],
        "fala_executivo_pct": r["fala_executivo_pct"],
        "reconexoes": r["reconexoes"],
        "latencia_media_ms": r["latencia_media_ms"],
        "sem_resposta": r.get("sem_resposta") or 0,
        "custo_estimado_usd": (float(r["custo_estimado_usd"])
                               if custo and r["custo_estimado_usd"] is not None else None),
        "nota_total": float(r["nota_total"]) if r.get("nota_total") is not None else None,
        "avaliacao_status": r.get("avaliacao_status"),
        "tem_audio": bool(r["audio_s3_chave"]),
        "modelo_voz": r["modelo_voz"],
    }
    if completa:
        out["transcricao"] = _json(r["transcricao"]) or []
        out["tokens"] = _json(r["tokens"]) or {}
        # Diário da conexão: diagnóstico técnico, só para a gestão.
        out["eventos"] = (_json(r.get("eventos")) or []) if diagnostico else None
    return out


async def _marcar_abandonadas(conn, usuario_id) -> None:
    await conn.execute(
        """
        UPDATE roleplay_sessoes SET status = 'abandonada'
         WHERE usuario_id = $1 AND status = 'iniciada' AND iniciada_em < $2
        """,
        usuario_id, regras.limite_abandono(_agora(), settings.ROLEPLAY_DURACAO_MAX_MIN),
    )


async def _quiz_aprovado(conn, usuario_id, cargo) -> bool:
    trilha = regras.TRILHA_ROTEIRO_POR_CARGO.get(cargo or "")
    if trilha is None:
        return False
    return bool(await conn.fetchval(
        """
        SELECT 1 FROM uc_tentativas_trilha
         WHERE usuario_id = $1 AND trilha_id = $2 AND aprovada LIMIT 1
        """,
        usuario_id, trilha,
    ))


async def _consentiu(conn, usuario_id) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM roleplay_consentimentos WHERE usuario_id = $1 AND versao_termo = $2",
        usuario_id, regras.TERMO_VERSAO,
    ))


async def _sessoes_hoje(conn, usuario_id, hoje) -> int:
    return await conn.fetchval(
        f"""
        SELECT count(*) FROM roleplay_sessoes
         WHERE usuario_id = $1 AND (iniciada_em AT TIME ZONE '{FUSO}')::date = $2
        """,
        usuario_id, hoje,
    )


async def _gasto_mes(conn, hoje) -> float:
    valor = await conn.fetchval(
        f"""
        SELECT COALESCE(sum(custo_estimado_usd), 0) FROM roleplay_sessoes
         WHERE (iniciada_em AT TIME ZONE '{FUSO}')::date >= $1
        """,
        hoje.replace(day=1),
    )
    return float(valor or 0)


async def _sessao_do_dono(conn, sessao_id: UUID, user: dict) -> dict:
    r = await conn.fetchrow("SELECT * FROM roleplay_sessoes WHERE id = $1", sessao_id)
    if r is None:
        raise HTTPException(404, "Sessão não encontrada.")
    if r["usuario_id"] != user["id"]:
        raise HTTPException(403, "Essa sessão é de outra pessoa.")
    return dict(r)


async def _sessao_visivel(conn, sessao_id: UUID, user: dict) -> dict:
    r = await conn.fetchrow("SELECT * FROM roleplay_sessoes WHERE id = $1", sessao_id)
    if r is None:
        raise HTTPException(404, "Sessão não encontrada.")
    if r["usuario_id"] != user["id"] and not eh_gestao(user):
        raise HTTPException(403, "Só a gestão abre o roleplay de outra pessoa.")
    return dict(r)


async def _token(cenario: dict) -> str:
    setup = regras.setup_live(settings.ROLEPLAY_MODELO_VOZ, montar_instrucao(cenario), cenario["voz"])
    try:
        return await regras.emitir_token(setup)
    except regras.GeminiIndisponivel as e:
        if e.sem_saldo:
            raise HTTPException(503, "Roleplay pausado no momento. Avise a gestão.") from e
        raise HTTPException(503, f"Roleplay indisponível agora. {e}") from e


# ── Avaliação (RP-2) ─────────────────────────────────────────────────

async def _recalcular(conn, sessao_id) -> None:
    """nota_total = itens do foco (nota da gestão, senão da IA) reescalados para /20."""
    foco = await conn.fetchval("SELECT itens_foco FROM roleplay_avaliacoes WHERE sessao_id = $1", sessao_id)
    if foco is None:
        return
    rows = await conn.fetch(
        "SELECT item, COALESCE(nota_gestor, nota_ia) AS nota FROM roleplay_avaliacao_itens WHERE sessao_id = $1",
        sessao_id,
    )
    nota = rav.nota_reescalada({r["item"]: r["nota"] for r in rows}, tuple(foco))
    await conn.execute("UPDATE roleplay_avaliacoes SET nota_total = $2 WHERE sessao_id = $1", sessao_id, nota)


async def _marcar_aguardando(conn, sessao: dict) -> None:
    foco = list(rav.itens_do_cenario(CENARIOS.get(sessao["cenario_id"])))
    await conn.execute(
        """
        INSERT INTO roleplay_avaliacoes (sessao_id, status, versao_roteiro, itens_foco, iniciada_em)
        VALUES ($1, 'aguardando', $2, $3, NOW())
        ON CONFLICT (sessao_id) DO UPDATE
           SET status = 'aguardando', erro = NULL, iniciada_em = NOW(),
               versao_roteiro = EXCLUDED.versao_roteiro, itens_foco = EXCLUDED.itens_foco,
               validada_em = NULL, validada_por = NULL
        """,
        sessao["id"], sc.VERSAO, foco,
    )


async def avaliar_sessao(conn, sessao_id) -> str:
    """
    Avalia e grava. Devolve o status final. Um advisory lock por sessão
    impede duas avaliações simultâneas (encerrar + botão).
    """
    if not await conn.fetchval("SELECT pg_try_advisory_lock(hashtext('roleplay-aval:' || $1::text))",
                               str(sessao_id)):
        return "aguardando"
    try:
        s = await conn.fetchrow("SELECT * FROM roleplay_sessoes WHERE id = $1", sessao_id)
        if s is None:
            return "erro"
        cenario = CENARIOS.get(s["cenario_id"])
        await conn.execute(
            "UPDATE roleplay_avaliacoes SET tentativas = tentativas + 1 WHERE sessao_id = $1", sessao_id,
        )
        try:
            res = await rav.avaliar(_json(s["transcricao"]) or [], cenario)
        except rav.SemConteudo as e:
            await conn.execute(
                "UPDATE roleplay_avaliacoes SET status = 'sem_conteudo', erro = $2, gerada_em = NOW() WHERE sessao_id = $1",
                sessao_id, str(e),
            )
            return "sem_conteudo"
        except Exception as e:  # noqa: BLE001 - qualquer falha vira coluna, nunca 500
            log.warning("roleplay: avaliação da sessão %s falhou: %s", sessao_id, e)
            await conn.execute(
                "UPDATE roleplay_avaliacoes SET status = 'erro', erro = $2 WHERE sessao_id = $1",
                sessao_id, str(e)[:500] or type(e).__name__,
            )
            return "erro"
        a = res.avaliacao
        async with conn.transaction():
            await conn.execute("DELETE FROM roleplay_avaliacao_itens WHERE sessao_id = $1", sessao_id)
            await conn.executemany(
                """
                INSERT INTO roleplay_avaliacao_itens (sessao_id, item, nota_ia, evidencia,
                                                      justificativa, sugestao, descartado)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [(sessao_id, i.item, i.nota, i.evidencia, i.justificativa, i.sugestao, i.descartado)
                 for i in a.itens],
            )
            await conn.execute(
                """
                UPDATE roleplay_avaliacoes
                   SET status = 'pronta', erro = NULL, itens_foco = $2, resumo = $3, foco_proxima = $4,
                       pontos_fortes = $5::jsonb, pontos_melhorar = $6::jsonb, modelo = $7,
                       gerada_em = NOW(), validada_em = NULL, validada_por = NULL
                 WHERE sessao_id = $1
                """,
                sessao_id, list(res.itens_foco), a.resumo, a.foco_proxima,
                rav.json_pontos(a.pontos_fortes), rav.json_pontos(a.pontos_melhorar), a.modelo,
            )
            await _recalcular(conn, sessao_id)
        return "pronta"
    finally:
        await conn.execute("SELECT pg_advisory_unlock(hashtext('roleplay-aval:' || $1::text))", str(sessao_id))


async def _avaliar_em_segundo_plano(sessao_id) -> None:
    """Tarefa depois da resposta: conexão própria (a da request já voltou ao pool)."""
    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
    except Exception as e:  # noqa: BLE001
        log.warning("roleplay: sem conexão para avaliar %s: %s", sessao_id, e)
        return
    try:
        await avaliar_sessao(conn, sessao_id)
    finally:
        await conn.close()


def _travada(av: dict) -> bool:
    return av["status"] == "aguardando" and av["iniciada_em"] < _agora() - AGUARDANDO_TRAVADA


async def _avaliacao_out(conn, sessao: dict, user: dict) -> dict | None:
    av = await conn.fetchrow("SELECT * FROM roleplay_avaliacoes WHERE sessao_id = $1", sessao["id"])
    if av is None:
        return None
    av = dict(av)
    gestao = eh_gestao(user)
    dono = sessao["usuario_id"] == user["id"]
    foco = tuple(av["itens_foco"] or ())
    itens = {}
    if av["status"] == "pronta":
        for r in await conn.fetch(
            """
            SELECT i.*, u.nome AS ajustada_por_nome FROM roleplay_avaliacao_itens i
              LEFT JOIN usuarios u ON u.id = i.ajustada_por
             WHERE i.sessao_id = $1
            """,
            sessao["id"],
        ):
            itens[r["item"]] = dict(r)
    status = "erro" if _travada(av) else av["status"]
    validada = av["validada_em"] is not None
    nota = float(av["nota_total"]) if av["nota_total"] is not None else None
    return {
        "status": status,
        "nota_total": nota,
        "nota_maxima": sc.NOTA_MAXIMA,
        "faixa": sc.faixa(nota) if status == "pronta" else None,
        "erro": "A avaliação não terminou. Avalie de novo." if _travada(av) else av["erro"],
        "resumo": av["resumo"],
        "foco_proxima": av["foco_proxima"],
        "pontos_fortes": _json(av["pontos_fortes"]) or [],
        "pontos_melhorar": _json(av["pontos_melhorar"]) or [],
        "itens": [
            {
                **meta,
                "nota_ia": itens.get(meta["item"], {}).get("nota_ia"),
                "nota_gestor": itens.get(meta["item"], {}).get("nota_gestor"),
                "nota": (itens[meta["item"]]["nota_gestor"]
                         if itens.get(meta["item"], {}).get("nota_gestor") is not None
                         else itens.get(meta["item"], {}).get("nota_ia")),
                "evidencia": itens.get(meta["item"], {}).get("evidencia"),
                "justificativa": itens.get(meta["item"], {}).get("justificativa"),
                "sugestao": itens.get(meta["item"], {}).get("sugestao"),
                "descartado": itens.get(meta["item"], {}).get("descartado"),
                "ajustada_por": itens.get(meta["item"], {}).get("ajustada_por_nome"),
            }
            for meta in rav.itens_para_tela(foco)
        ] if status == "pronta" else [],
        "validada": validada,
        "validada_em": av["validada_em"],
        "pode_ajustar": gestao and status == "pronta" and not validada,
        "pode_validar": gestao and status == "pronta",
        "pode_reavaliar": (not validada) and (gestao or (dono and status in ("erro",))),
    }


async def _requer_gestao(user: dict) -> None:
    if not eh_gestao(user):
        raise HTTPException(403, "Só a gestão ajusta e valida a nota do roleplay.")


# ── Rotas ────────────────────────────────────────────────────────────

@router.get("/roleplay")
async def tela(
    usuario_id: UUID | None = Query(None),
    hoje: date | None = Query(None, description="Só para teste determinístico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    pessoa, leitura = await _pessoa_alvo(conn, user, usuario_id)
    dia = hoje or _hoje()
    await _marcar_abandonadas(conn, pessoa["id"])

    cargo = pessoa.get("cargo")
    gestao_pessoa = cargo in regras.CARGOS_GESTAO
    lib = regras.liberacao(cargo, await _quiz_aprovado(conn, pessoa["id"], cargo))
    cenarios = cenarios_do_cargo(cargo, gestao=gestao_pessoa)

    rows = [dict(r) for r in await conn.fetch(
        """
        SELECT s.*, a.nota_total, a.status AS avaliacao_status
          FROM roleplay_sessoes s
          LEFT JOIN roleplay_avaliacoes a ON a.sessao_id = s.id
         WHERE s.usuario_id = $1
         ORDER BY s.iniciada_em DESC LIMIT 200
        """,
        pessoa["id"],
    )]
    encerradas = [r for r in rows if r["status"] == "encerrada"]
    por_cenario: dict[str, list[dict]] = {}
    for r in encerradas:
        por_cenario.setdefault(r["cenario_id"], []).append(r)
    inicio_mes = dia.replace(day=1)
    do_mes = [r for r in encerradas if r["iniciada_em"].astimezone(FUSO_OPERACAO).date() >= inicio_mes]
    sessoes_hoje = await _sessoes_hoje(conn, pessoa["id"], dia)
    gasto = await _gasto_mes(conn, dia)
    orcamento = settings.ROLEPLAY_ORCAMENTO_MES_USD
    proximo = regras.proximo_cenario(cenarios, set(por_cenario))
    custo = ve_custo(user)
    notas_mes = [float(r["nota_total"]) for r in do_mes
                 if r["conta_media"] and r["avaliacao_status"] == "pronta" and r["nota_total"] is not None]
    notas_recentes = [float(r["nota_total"]) for r in encerradas
                      if r["avaliacao_status"] == "pronta" and r["nota_total"] is not None][:5]

    return {
        "pessoa": {"id": str(pessoa["id"]), "nome": pessoa["nome"], "cargo": cargo},
        "modo_leitura": leitura,
        "liberado": lib.liberado,
        "motivo": lib.motivo,
        "trilha_id": str(lib.trilha_id) if lib.trilha_id else None,
        "pode_treinar": lib.liberado and not leitura,
        "disponivel": regras.disponivel() and (orcamento <= 0 or gasto < orcamento),
        "indisponivel_motivo": (
            "Roleplay desligado no servidor (falta a chave do Gemini)." if not regras.disponivel()
            else ("O orçamento de IA do roleplay deste mês acabou." if custo
                  else "O roleplay está pausado neste mês.")
            if orcamento > 0 and gasto >= orcamento
            else None
        ),
        "consentimento_pendente": not leitura and not await _consentiu(conn, pessoa["id"]),
        "termo": {"versao": regras.TERMO_VERSAO, "texto": regras.TERMO_TEXTO},
        "proximo": _cenario_publico(proximo, CENARIOS[proximo]) if proximo else None,
        "cenarios": [
            {**_cenario_publico(k, c),
             "tentativas": len(por_cenario.get(k, [])),
             "ultima_em": por_cenario[k][0]["iniciada_em"] if k in por_cenario else None,
             "melhor_nota": max((float(r["nota_total"]) for r in por_cenario.get(k, [])
                                 if r["avaliacao_status"] == "pronta" and r["nota_total"] is not None),
                                default=None)}
            for k, c in cenarios
        ],
        "resumo": {
            "sessoes_mes": len(do_mes),
            "minutos_mes": round(sum((r["duracao_s"] or 0) for r in do_mes) / 60),
            "sessoes_hoje": sessoes_hoje,
            "limite_dia": 0 if gestao_pessoa else settings.ROLEPLAY_LIMITE_DIA,
            "ultima_em": encerradas[0]["iniciada_em"] if encerradas else None,
            # Média /20 das avaliações prontas do mês que contam na média.
            "media_mes": round(sum(notas_mes) / len(notas_mes), 1) if notas_mes else None,
            "avaliadas_mes": len(notas_mes),
            "ultimas_notas": notas_recentes,
            "nota_maxima": sc.NOTA_MAXIMA,
        },
        "historico": [_sessao_out(r, custo=custo) for r in rows if r["status"] != "iniciada"][:20],
        # Gasto global do mês: só o Franqueado vê.
        "orcamento": ({"gasto_mes_usd": round(gasto, 2), "orcamento_mes_usd": orcamento}
                      if custo else None),
        "duracao_max_min": settings.ROLEPLAY_DURACAO_MAX_MIN,
    }


@router.post("/roleplay/consentimento")
async def consentir(conn=Depends(get_conn), user=Depends(usuario_atual)):
    await conn.execute(
        """
        INSERT INTO roleplay_consentimentos (usuario_id, versao_termo)
        VALUES ($1, $2)
        ON CONFLICT (usuario_id) DO UPDATE
           SET versao_termo = EXCLUDED.versao_termo, aceito_em = NOW()
        """,
        user["id"], regras.TERMO_VERSAO,
    )
    return {"versao": regras.TERMO_VERSAO}


@router.post("/roleplay/sessoes", status_code=201)
async def abrir(body: NovaSessao, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    Abre a sessão e devolve o primeiro token. Ordem das travas: cenário do
    cargo → quiz → termo → sessão aberta → limite do dia → orçamento →
    Gemini. O registro só nasce depois do token: se o Google recusar, não
    fica sessão fantasma contando no limite do dia.
    """
    cargo = user.get("cargo")
    gestao = cargo in regras.CARGOS_GESTAO
    cenario = CENARIOS.get(body.cenario_id)
    if cenario is None:
        raise HTTPException(404, "Cenário não encontrado.")
    if body.cenario_id not in dict(cenarios_do_cargo(cargo, gestao=gestao)):
        raise HTTPException(403, "Esse cenário é de outro cargo.")
    lib = regras.liberacao(cargo, await _quiz_aprovado(conn, user["id"], cargo))
    if not lib.liberado:
        raise HTTPException(403, lib.motivo)
    if not await _consentiu(conn, user["id"]):
        raise HTTPException(409, "Aceite o termo de gravação antes de começar.")

    agora = _agora()
    hoje = _hoje()
    async with conn.transaction():
        # Dois cliques em "Começar" não abrem duas sessões.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('roleplay:' || $1::text))", str(user["id"]))
        await _marcar_abandonadas(conn, user["id"])
        aberta = await conn.fetchval(
            "SELECT id FROM roleplay_sessoes WHERE usuario_id = $1 AND status = 'iniciada' LIMIT 1",
            user["id"],
        )
        if aberta:
            raise HTTPException(409, "Você já tem um roleplay em andamento. Encerre-o antes de começar outro.")
        try:
            regras.checar_limites(
                sessoes_hoje=await _sessoes_hoje(conn, user["id"], hoje),
                limite_dia=settings.ROLEPLAY_LIMITE_DIA,
                gasto_mes_usd=await _gasto_mes(conn, hoje),
                orcamento_mes_usd=settings.ROLEPLAY_ORCAMENTO_MES_USD,
                gestao=gestao,
            )
        except regras.RoleplayInvalido as e:
            _erro(e)
        token = await _token(cenario)
        sessao_id = await conn.fetchval(
            """
            INSERT INTO roleplay_sessoes (usuario_id, cenario_id, cenario_versao, conta_media,
                                          modelo_voz, iniciada_em)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            user["id"], body.cenario_id, cenario["versao"], lib.conta_media,
            settings.ROLEPLAY_MODELO_VOZ, agora,
        )
    return {
        "sessao_id": str(sessao_id),
        "token": token,
        "ws_url": regras.URL_WS,
        "modelo": settings.ROLEPLAY_MODELO_VOZ,
        "duracao_max_s": settings.ROLEPLAY_DURACAO_MAX_MIN * 60,
        "cenario": _cenario_publico(body.cenario_id, cenario),
    }


@router.post("/roleplay/sessoes/{sessao_id}/token")
async def novo_token(sessao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """Token da reconexão. Só o dono, só com a sessão em andamento e no prazo."""
    s = await _sessao_do_dono(conn, sessao_id, user)
    if s["status"] != "iniciada":
        raise HTTPException(409, "Essa sessão já foi encerrada.")
    if s["iniciada_em"] < regras.limite_abandono(_agora(), settings.ROLEPLAY_DURACAO_MAX_MIN):
        raise HTTPException(409, "Essa sessão passou do tempo máximo.")
    if s["tokens_emitidos"] >= regras.MAX_TOKENS_POR_SESSAO:
        raise HTTPException(429, "Reconexões demais nesta sessão. Encerre e comece de novo.")
    cenario = CENARIOS.get(s["cenario_id"])
    if cenario is None:
        raise HTTPException(409, "O cenário desta sessão não existe mais.")
    token = await _token(cenario)
    await conn.execute(
        "UPDATE roleplay_sessoes SET tokens_emitidos = tokens_emitidos + 1 WHERE id = $1", sessao_id,
    )
    return {"token": token, "ws_url": regras.URL_WS, "modelo": s["modelo_voz"]}


@router.post("/roleplay/sessoes/{sessao_id}/encerrar")
async def encerrar(
    sessao_id: UUID,
    tarefas: BackgroundTasks,
    dados: str = Form(...),
    audio: UploadFile | None = File(None),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Fecha a sessão com o que o navegador juntou. Idempotente: encerrar de
    novo devolve a mesma sessão. Sessão marcada como abandonada ainda
    aceita o encerramento (a gravação não se perde por um relógio).

    Ordem: valida tudo → sobe a gravação → grava no banco. Sem S3
    configurado, a sessão fecha sem áudio em vez de falhar.
    """
    s = await _sessao_do_dono(conn, sessao_id, user)
    if s["status"] == "encerrada":
        return {**_sessao_out(s, completa=True, custo=ve_custo(user), diagnostico=eh_gestao(user)),
                "avaliacao": await _avaliacao_out(conn, s, user)}
    try:
        bruto = json.loads(dados)
    except ValueError:
        raise HTTPException(422, "Dados do encerramento em formato inválido.") from None
    if not isinstance(bruto, dict):
        raise HTTPException(422, "Dados do encerramento em formato inválido.")
    agora = _agora()
    try:
        transcricao = regras.validar_transcricao(bruto.get("transcricao"))
        tokens = regras.normalizar_tokens(bruto.get("tokens"))
        motivo = regras.validar_motivo(bruto.get("motivo_fim"))
        duracao = regras.duracao_s(
            s["iniciada_em"], agora,
            regras.validar_inteiro(bruto.get("duracao_s"), "duracao_s"),
            settings.ROLEPLAY_DURACAO_MAX_MIN,
        )
        reconexoes = regras.validar_inteiro(bruto.get("reconexoes"), "reconexoes", 0, 1000)
        latencia = regras.validar_inteiro(bruto.get("latencia_media_ms"), "latencia_media_ms", 0, 600_000)
        eventos = regras.validar_eventos(bruto.get("eventos"))
        chave, tamanho, conteudo, tipo = None, None, None, None
        if audio is not None:
            conteudo = await audio.read()
            tipo = (audio.content_type or "").split(";")[0].strip().lower()
            if conteudo:
                ext = regras.validar_audio(audio.content_type, len(conteudo))
                if s3.disponivel():
                    chave = regras.chave_audio(user["id"], sessao_id, ext)
                    tamanho = len(conteudo)
    except regras.RoleplayInvalido as e:
        _erro(e)

    if chave:
        try:
            s3.subir(chave, conteudo, tipo)
        except Exception as e:  # noqa: BLE001 - erro do boto vira mensagem
            raise HTTPException(502, f"Não foi possível guardar a gravação ({type(e).__name__}). Tente de novo.") from e

    r = await conn.fetchrow(
        """
        UPDATE roleplay_sessoes
           SET status = 'encerrada', encerrada_em = $2, duracao_s = $3, motivo_fim = $4,
               transcricao = $5::jsonb, fala_executivo_pct = $6, tokens = $7::jsonb,
               custo_estimado_usd = $8, reconexoes = $9, latencia_media_ms = $10,
               audio_s3_chave = COALESCE($11, audio_s3_chave), audio_bytes = COALESCE($12, audio_bytes),
               eventos = $13::jsonb, sem_resposta = $14
         WHERE id = $1
        RETURNING *
        """,
        sessao_id, agora, duracao, motivo,
        json.dumps(transcricao, ensure_ascii=False), regras.fala_executivo_pct(transcricao),
        json.dumps(tokens), regras.custo_estimado(s["modelo_voz"], tokens),
        reconexoes, latencia, chave, tamanho,
        json.dumps(eventos, ensure_ascii=False), regras.contar_sem_resposta(eventos),
    )
    s = dict(r)
    # A nota sai em segundo plano, depois da resposta: a tela de resultado
    # mostra "avaliando" e consulta de novo.
    await _marcar_aguardando(conn, s)
    tarefas.add_task(_avaliar_em_segundo_plano, sessao_id)
    return {**_sessao_out(s, completa=True, custo=ve_custo(user), diagnostico=eh_gestao(user)),
            "avaliacao": await _avaliacao_out(conn, s, user)}


@router.get("/roleplay/sessoes/{sessao_id}")
async def detalhe(sessao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    s = await _sessao_visivel(conn, sessao_id, user)
    return {**_sessao_out(s, completa=True, custo=ve_custo(user), diagnostico=eh_gestao(user)),
            "modo_leitura": s["usuario_id"] != user["id"],
            "avaliacao": await _avaliacao_out(conn, s, user)}


@router.post("/roleplay/sessoes/{sessao_id}/avaliar")
async def reavaliar(sessao_id: UUID, tarefas: BackgroundTasks,
                    conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    Avaliar de novo: a gestão quando quiser (antes do selo); o dono só se a
    avaliação falhou. Roda em segundo plano, como no encerramento.
    """
    s = await _sessao_visivel(conn, sessao_id, user)
    if s["status"] != "encerrada":
        raise HTTPException(409, "Só dá para avaliar um roleplay encerrado.")
    atual = await _avaliacao_out(conn, s, user)
    if atual and atual["validada"]:
        raise HTTPException(409, "A nota já foi validada. Tire a validação antes de avaliar de novo.")
    if not eh_gestao(user) and not (atual is None or atual["status"] == "erro"):
        raise HTTPException(403, "Só a gestão pede uma nova avaliação.")
    if atual and atual["status"] == "aguardando":
        raise HTTPException(409, "A avaliação já está em andamento.")
    await _marcar_aguardando(conn, s)
    tarefas.add_task(_avaliar_em_segundo_plano, sessao_id)
    return {**_sessao_out(s, completa=True, custo=ve_custo(user), diagnostico=eh_gestao(user)),
            "modo_leitura": s["usuario_id"] != user["id"],
            "avaliacao": await _avaliacao_out(conn, s, user)}


@router.patch("/roleplay/sessoes/{sessao_id}/itens/{item}")
async def ajustar_item(sessao_id: UUID, item: int, body: NotaItem,
                       conn=Depends(get_conn), user=Depends(usuario_atual)):
    """Gestão troca a nota de um item (0..2), ou volta para a da IA (null)."""
    await _requer_gestao(user)
    s = await _sessao_visivel(conn, sessao_id, user)
    av = await _avaliacao_out(conn, s, user)
    if av is None or av["status"] != "pronta":
        raise HTTPException(409, "A avaliação ainda não está pronta.")
    if av["validada"]:
        raise HTTPException(409, "A nota já foi validada. Tire a validação para ajustar.")
    if item not in [i["item"] for i in av["itens"]]:
        raise HTTPException(422, "Esse item não conta neste roleplay.")
    if body.nota is not None and not 0 <= body.nota <= sc.NOTA_MAXIMA_ITEM:
        raise HTTPException(422, "Nota de 0 a 2.")
    await conn.execute(
        """
        INSERT INTO roleplay_avaliacao_itens (sessao_id, item, nota_gestor, ajustada_por, ajustada_em)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (sessao_id, item) DO UPDATE
           SET nota_gestor = EXCLUDED.nota_gestor,
               ajustada_por = CASE WHEN EXCLUDED.nota_gestor IS NULL THEN NULL ELSE EXCLUDED.ajustada_por END,
               ajustada_em = CASE WHEN EXCLUDED.nota_gestor IS NULL THEN NULL ELSE NOW() END
        """,
        sessao_id, item, body.nota, user["id"],
    )
    await _recalcular(conn, sessao_id)
    return {**_sessao_out(s, completa=True, custo=ve_custo(user), diagnostico=eh_gestao(user)),
            "modo_leitura": s["usuario_id"] != user["id"],
            "avaliacao": await _avaliacao_out(conn, s, user)}


@router.post("/roleplay/sessoes/{sessao_id}/validar")
async def validar(sessao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    await _requer_gestao(user)
    s = await _sessao_visivel(conn, sessao_id, user)
    av = await _avaliacao_out(conn, s, user)
    if av is None or av["status"] != "pronta":
        raise HTTPException(409, "A avaliação ainda não está pronta.")
    await conn.execute(
        "UPDATE roleplay_avaliacoes SET validada_em = NOW(), validada_por = $2 WHERE sessao_id = $1",
        sessao_id, user["id"],
    )
    return {**_sessao_out(s, completa=True, custo=ve_custo(user), diagnostico=eh_gestao(user)),
            "modo_leitura": s["usuario_id"] != user["id"],
            "avaliacao": await _avaliacao_out(conn, s, user)}


@router.delete("/roleplay/sessoes/{sessao_id}/validar")
async def tirar_validacao(sessao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    await _requer_gestao(user)
    s = await _sessao_visivel(conn, sessao_id, user)
    await conn.execute(
        "UPDATE roleplay_avaliacoes SET validada_em = NULL, validada_por = NULL WHERE sessao_id = $1",
        sessao_id,
    )
    return {**_sessao_out(s, completa=True, custo=ve_custo(user), diagnostico=eh_gestao(user)),
            "modo_leitura": s["usuario_id"] != user["id"],
            "avaliacao": await _avaliacao_out(conn, s, user)}


@router.get("/roleplay/sessoes/{sessao_id}/audio")
async def audio_url(sessao_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    s = await _sessao_visivel(conn, sessao_id, user)
    if not s["audio_s3_chave"]:
        raise HTTPException(404, "Essa sessão não tem gravação.")
    if not s3.disponivel():
        raise HTTPException(503, "Gravações indisponíveis: S3 não configurado no servidor.")
    return {"url": s3.url_temporaria(s["audio_s3_chave"]), "expira_em_s": s3.URL_VALIDA_SEGUNDOS}
