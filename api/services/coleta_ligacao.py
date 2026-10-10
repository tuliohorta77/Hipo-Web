"""
HIPO — Orquestração das ligações gravadas (entrega 056): banco + AWS + IA.

Quem chama:
  * routers/crm_ligacoes.py — o agente confirmou o upload (começa a
    transcrição na hora) e o botão "Atualizar" da tela;
  * scripts/coletar_ligacoes.py — o hipo-ligacoes.timer, a cada 2 minutos.

As duas portas fazem a MESMA coisa (`processar`), então o timer e o botão
nunca discordam sobre o estado de uma ligação.

ESTADOS (services/ligacao.STATUS):

    discando ──(gravação chega)──> enviando ──(upload confirmado)──> transcrevendo
       │                              │                                  │
       └─ 6 h sem gravação ─> sem_gravacao   2 h sem confirmar:          ├─> pronta
                                       confere o S3 ─> transcrevendo     ├─> sem_fala
                                                    └> erro              └─> erro

FALHA DA AWS = COLUNA, NÃO 500. `erro` recebe a frase em português e
`tentativas` sobe; o timer tenta de novo até MAX_TENTATIVAS. Uma queda do
Transcribe nunca derruba a tela de quem só queria ver a lista.

O RESUMO é o mesmo da reunião (services/resumo_reuniao), com instrução de
ligação e a mesma guarda numérica: número que não está na transcrição
descarta o resumo inteiro.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from config import settings
from services import ligacao as regras
from services import ligacao_aws as aws
from services import resumo_reuniao
from services.agenda import FUSO_OPERACAO

log = logging.getLogger("hipo.coleta_ligacao")

INSTRUCAO_LIGACAO = """Você lê a transcrição de uma LIGAÇÃO TELEFÔNICA comercial
de uma empresa que vende serviços de medicina e segurança do trabalho para
outras empresas. A transcrição tem dois lados: quem ligou (o executivo da
empresa) e o cliente. Quem vai ler o seu texto é o executivo, logo depois da
ligação, para registrar o que aconteceu e decidir a próxima ação.

Responda SOMENTE com um objeto JSON, sem markdown, neste formato:

{"resumo": "...", "proximos_passos": ["...", "..."]}

- "resumo": 2 a 5 frases em português do Brasil. Com quem falou (se o nome
  aparecer), o que o cliente disse sobre a necessidade dele, objeções ou
  dúvidas, e como a ligação terminou (agendou reunião, pediu retorno, não
  tem interesse, caiu na caixa postal, não atendeu).
- "proximos_passos": as ações que ficaram COMBINADAS na conversa, uma por
  item, começando pelo verbo ("Ligar de novo na quinta às 10h", "Enviar o
  e-mail com a apresentação para ..."). No máximo 8. Lista vazia se nada
  foi combinado.

Regras:
- Use SÓ o que está na transcrição. Não invente nome, empresa, valor, prazo,
  quantidade, data ou compromisso.
- NÚMEROS: escreva exatamente como aparecem na transcrição. Se um número
  foi dito por extenso, escreva por extenso. Não some, não converta, não
  calcule. Existe uma verificação automática, e um número que não esteja
  escrito na transcrição descarta o resumo inteiro.
- Próximo passo é o que alguém DISSE que ia fazer. Não sugira ação que
  ninguém combinou.
- A transcrição automática de telefone erra palavras. Se um trecho estiver
  incompreensível, ignore-o em vez de adivinhar.
"""

_SELECT = """
    SELECT l.*,
           u.nome  AS usuario_nome,
           ct.nome AS contato_nome,
           o.numero AS oportunidade_numero,
           COALESCE(co.razao_social, cc.razao_social) AS empresa
      FROM ligacoes l
      JOIN usuarios u       ON u.id = l.usuario_id
      LEFT JOIN contatos ct ON ct.id = l.contato_id
      LEFT JOIN oportunidades o ON o.id = l.oportunidade_id
      LEFT JOIN contas co   ON co.id = o.conta_id
      LEFT JOIN contas cc   ON cc.id = l.conta_id
"""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def linha(conn, ligacao_id: UUID) -> dict | None:
    r = await conn.fetchrow(f"{_SELECT} WHERE l.id = $1", ligacao_id)
    return dict(r) if r else None


async def _gravar(conn, ligacao_id: UUID, **campos) -> None:
    """UPDATE dos campos pedidos + atualizado_em. Nomes vêm do código, nunca do cliente."""
    if not campos:
        return
    nomes = list(campos)
    sets = ", ".join(f"{n} = ${i + 2}" for i, n in enumerate(nomes))
    await conn.execute(
        f"UPDATE ligacoes SET {sets}, atualizado_em = NOW() WHERE id = $1",
        ligacao_id, *[campos[n] for n in nomes],
    )


def _codigo_erro(e: Exception) -> str:
    resp = getattr(e, "response", None)
    if isinstance(resp, dict):
        return str((resp.get("Error") or {}).get("Code", ""))
    return ""


def _mensagem_aws(e: Exception) -> str:
    codigo = _codigo_erro(e)
    if codigo in ("AccessDeniedException", "AccessDenied", "UnrecognizedClientException"):
        return (
            "A AWS recusou a transcrição (permissão). A role do servidor precisa de "
            "transcribe:StartTranscriptionJob e transcribe:GetTranscriptionJob."
        )
    if codigo == "LimitExceededException":
        return "A AWS está com fila cheia de transcrições; tentando de novo em instantes."
    return f"A transcrição na AWS falhou ({codigo or type(e).__name__})."


# ── Transcrição ──────────────────────────────────────────────────────


async def iniciar(conn, lig: dict) -> dict:
    """
    Começa (ou recomeça) o job no Transcribe. Nunca levanta.

    Nome do job com o número da tentativa: o Transcribe não deixa reusar
    nome. Dois processos começando a MESMA tentativa ao mesmo tempo (o
    timer e o botão) esbarram em ConflictException no segundo — que é
    sucesso: o job existe.
    """
    if not aws.disponivel():
        await _gravar(conn, lig["id"], status="erro", erro="; ".join(aws.problemas()))
        return await linha(conn, lig["id"])
    tentativa = int(lig.get("tentativas") or 0) + 1
    if tentativa > regras.MAX_TENTATIVAS:
        await _gravar(
            conn, lig["id"], status="erro",
            erro=lig.get("erro") or "A transcrição falhou depois de várias tentativas.",
        )
        return await linha(conn, lig["id"])
    nome = regras.nome_job(lig["id"], tentativa)
    try:
        await asyncio.to_thread(aws.iniciar_transcricao, nome, lig["audio_s3_chave"])
    except Exception as e:  # noqa: BLE001 - erro da AWS vira coluna
        if _codigo_erro(e) != "ConflictException":
            log.warning("ligacao %s: start_transcription_job falhou: %s", lig["id"], e)
            await _gravar(
                conn, lig["id"], status="transcrevendo", transcricao_job=None,
                tentativas=tentativa, erro=_mensagem_aws(e),
            )
            return await linha(conn, lig["id"])
    await _gravar(
        conn, lig["id"], status="transcrevendo", transcricao_job=nome,
        transcricao_iniciada_em=_agora(), tentativas=tentativa, erro=None,
    )
    return await linha(conn, lig["id"])


async def _guardar_texto(conn, lig: dict, dados: dict) -> dict:
    trechos = regras.ler_transcribe(dados)
    if not trechos:
        await _gravar(
            conn, lig["id"], status="sem_fala", transcrita_em=_agora(), erro=None,
            transcricao_entradas=json.dumps([]), transcricao_texto="",
        )
        return await linha(conn, lig["id"])
    inicio = lig.get("inicio_em") or lig["criado_em"]
    usuario = regras.primeiro_nome(lig.get("usuario_nome"))
    cliente = regras.primeiro_nome(lig.get("contato_nome")) if lig.get("contato_nome") else "Cliente"
    if cliente == usuario:
        cliente = f"{cliente} (cliente)"
    await _gravar(
        conn, lig["id"],
        status="pronta",
        transcrita_em=_agora(),
        transcricao_entradas=json.dumps(
            regras.entradas(trechos, inicio, usuario, cliente), ensure_ascii=False,
        ),
        transcricao_texto=regras.texto(trechos, inicio, usuario, cliente),
        fala_usuario_pct=regras.fala_usuario_pct(trechos),
        erro=None,
    )
    return await linha(conn, lig["id"])


async def _falha_no_job(conn, lig: dict, agora: datetime, mensagem: str) -> dict:
    """
    Falha que NAO e a AWS dizendo "falhou" (rede, permissao, JSON estranho).
    Grava o motivo e, passada a janela de 3 h desde o inicio do job, desiste
    -- sem isto, a linha ficaria "transcrevendo" para sempre, olhada a cada
    passada do timer.
    """
    if regras.transcricao_expirada(lig.get("transcricao_iniciada_em"), agora):
        await _gravar(conn, lig["id"], status="erro", erro=mensagem)
    else:
        await _gravar(conn, lig["id"], erro=mensagem)
    return await linha(conn, lig["id"])


async def _conferir_job(conn, lig: dict, agora: datetime) -> dict:
    try:
        estado, url, motivo = await asyncio.to_thread(aws.estado_transcricao, lig["transcricao_job"])
    except Exception as e:  # noqa: BLE001
        log.warning("ligacao %s: get_transcription_job falhou: %s", lig["id"], e)
        return await _falha_no_job(conn, lig, agora, _mensagem_aws(e))

    if estado == "COMPLETED" and url:
        try:
            dados = await asyncio.to_thread(aws.baixar_transcricao, url)
            atual = await _guardar_texto(conn, lig, dados)
        except Exception as e:  # noqa: BLE001
            log.warning("ligacao %s: leitura do resultado falhou: %s", lig["id"], e)
            return await _falha_no_job(
                conn, lig, agora, f"Não foi possível ler a transcrição ({type(e).__name__}).",
            )
        await asyncio.to_thread(aws.apagar_job, lig["transcricao_job"])
        # Resumo na mesma passada: quem abrir a ligação já encontra o "o que
        # ficou combinado", sem esperar o próximo tique do timer.
        if atual["status"] == "pronta" and resumo_reuniao.configurado():
            atual = await resumir(conn, lig["id"])
        return atual

    if estado in ("FAILED", "NOT_FOUND"):
        log.warning("ligacao %s: job %s %s: %s", lig["id"], lig["transcricao_job"], estado, motivo)
        await _gravar(conn, lig["id"], erro=f"A AWS não transcreveu: {motivo or estado}.")
        return await iniciar(conn, await linha(conn, lig["id"]))

    if regras.transcricao_expirada(lig.get("transcricao_iniciada_em"), agora):
        await _gravar(conn, lig["id"], status="erro", erro="A transcrição travou na AWS por mais de 3 horas.")
    return await linha(conn, lig["id"])


async def resumir(conn, ligacao_id: UUID) -> dict:
    """Gera (ou refaz) o resumo. Nunca levanta: o erro vai para `resumo_erro`."""
    lig = await linha(conn, ligacao_id)
    if not lig or lig["status"] != "pronta" or not (lig.get("transcricao_texto") or "").strip():
        return lig
    dia = (lig.get("inicio_em") or lig["criado_em"]).astimezone(FUSO_OPERACAO).date().isoformat()
    contexto = {k: v for k, v in {
        "empresa": lig.get("empresa"),
        "contato": lig.get("contato_nome"),
        "data": dia,
    }.items() if v}
    r = await resumo_reuniao.resumir(
        lig["transcricao_texto"], contexto, instrucao=INSTRUCAO_LIGACAO, rotulo="ligação",
    )
    await _gravar(
        conn, ligacao_id,
        resumo=r.resumo,
        proximos_passos=json.dumps(list(r.proximos_passos), ensure_ascii=False) if r.resumo else None,
        resumo_modelo=r.modelo,
        resumo_em=_agora() if r.resumo else None,
        resumo_erro=r.erro,
    )
    return await linha(conn, ligacao_id)


# ── A passada ────────────────────────────────────────────────────────


def _chave_trava(ligacao_id: UUID) -> int:
    """Inteiro de 63 bits para o advisory lock, estável por ligação."""
    return UUID(str(ligacao_id)).int & 0x7FFF_FFFF_FFFF_FFFF


async def processar(conn, ligacao_id: UUID, agora: datetime | None = None) -> dict | None:
    """
    Faz andar UMA ligação o que der agora. Idempotente: chamar duas vezes
    seguidas não começa dois jobs nem grava duas vezes o texto.

    UM DE CADA VEZ POR LIGAÇÃO. O timer e o botão "Atualizar" podem pegar a
    mesma ligação no mesmo segundo; sem trava, o segundo leria o job que o
    primeiro acabou de apagar, tomaria isso por falha e começaria outro em
    cima de uma transcrição pronta. Quem não consegue a trava devolve o
    estado como está — o outro já está cuidando.
    """
    agora = agora or _agora()
    chave = _chave_trava(ligacao_id)
    if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", chave):
        return await linha(conn, ligacao_id)
    try:
        return await _processar(conn, ligacao_id, agora)
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", chave)


async def _processar(conn, ligacao_id: UUID, agora: datetime) -> dict | None:
    lig = await linha(conn, ligacao_id)
    if lig is None:
        return None
    status = lig["status"]

    if status in ("discando", "sem_gravacao"):
        if status == "discando" and regras.clique_expirado(lig["clicada_em"], agora):
            # Condicional: a gravação pode ter casado com este clique no
            # mesmo instante (a rota do gravador trava a linha com FOR
            # UPDATE); aí o status já não é 'discando' e nada muda aqui.
            await conn.execute(
                """
                UPDATE ligacoes SET status = 'sem_gravacao', atualizado_em = NOW()
                 WHERE id = $1 AND status = 'discando'
                """,
                lig["id"],
            )
            return await linha(conn, lig["id"])
        return lig

    if status == "enviando":
        if not regras.envio_expirado(lig["atualizado_em"], agora):
            return lig
        if not aws.disponivel():
            return lig
        try:
            tamanho = await asyncio.to_thread(aws.tamanho_no_s3, lig["audio_s3_chave"])
        except Exception as e:  # noqa: BLE001
            await _gravar(conn, lig["id"], erro=_mensagem_aws(e))
            return await linha(conn, lig["id"])
        if not tamanho:
            await _gravar(
                conn, lig["id"], status="erro", audio_s3_chave=None,
                erro="A gravação não chegou ao servidor (o gravador não terminou o envio).",
            )
            return await linha(conn, lig["id"])
        await _gravar(conn, lig["id"], audio_bytes=tamanho)
        return await iniciar(conn, await linha(conn, lig["id"]))

    if status == "transcrevendo":
        if not lig.get("transcricao_job"):
            return await iniciar(conn, lig)
        return await _conferir_job(conn, lig, agora)

    if status == "pronta" and lig.get("resumo") is None and lig.get("resumo_erro") is None:
        if resumo_reuniao.configurado():
            return await resumir(conn, lig["id"])
    return lig


async def pendentes(conn) -> list[UUID]:
    """O que a passada do timer olha: em andamento + prontas sem resumo recentes."""
    linhas = await conn.fetch(
        """
        SELECT id FROM ligacoes
         WHERE status IN ('enviando', 'transcrevendo')
            -- Clique só entra quando já venceu: os que ainda esperam a
            -- gravação não têm nada a fazer e encheriam o lote.
            OR (status = 'discando' AND clicada_em < NOW() - $1::interval)
            OR (status = 'pronta' AND resumo IS NULL AND resumo_erro IS NULL
                AND transcrita_em > NOW() - INTERVAL '3 days')
         ORDER BY atualizado_em
         LIMIT 200
        """,
        regras.EXPIRA_CLIQUE,
    )
    return [r["id"] for r in linhas]


async def reter(conn, agora: datetime | None = None, retencao_dias: int | None = None) -> int:
    """
    Apaga do S3 o áudio que passou da retenção. A transcrição fica.

    Também tem a regra de ciclo de vida no bucket (prefixo ligacoes/), mas
    aqui é onde o banco fica sabendo: sem isto, a tela ofereceria "Ouvir"
    para um arquivo que não existe mais.
    """
    agora = agora or _agora()
    dias = settings.LIGACOES_RETENCAO_DIAS if retencao_dias is None else retencao_dias
    if dias <= 0 or not aws.disponivel():
        return 0
    linhas = await conn.fetch(
        """
        SELECT id, audio_s3_chave, inicio_em, criado_em FROM ligacoes
         WHERE audio_s3_chave IS NOT NULL
           AND status NOT IN ('enviando', 'transcrevendo')
           AND COALESCE(inicio_em, criado_em) < $1::timestamptz - make_interval(days => $2)
         LIMIT 500
        """,
        agora, dias,
    )
    feitas = 0
    for r in linhas:
        if not regras.audio_vencido(r["inicio_em"], r["criado_em"], agora, dias):
            continue
        try:
            await asyncio.to_thread(aws.remover, r["audio_s3_chave"])
        except Exception as e:  # noqa: BLE001
            log.warning("ligacao %s: remocao do audio falhou: %s", r["id"], e)
            continue
        await _gravar(conn, r["id"], audio_s3_chave=None, audio_removido_em=agora)
        feitas += 1
    return feitas


async def passada(conn, agora: datetime | None = None) -> dict:
    """Uma passada do timer. Uma ligação com problema não para as outras."""
    agora = agora or _agora()
    contagem: dict[str, int] = {}
    falhas = 0
    for lid in await pendentes(conn):
        try:
            atual = await processar(conn, lid, agora)
        except Exception:
            falhas += 1
            log.exception("ligacao %s: falha inesperada", lid)
            continue
        if atual:
            contagem[atual["status"]] = contagem.get(atual["status"], 0) + 1
    removidos = await reter(conn, agora)
    return {"status": contagem, "falhas": falhas, "audios_removidos": removidos}
