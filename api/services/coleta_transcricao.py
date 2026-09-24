"""
HIPO — Coleta da transcrição: banco + Google Meet + IA.

A orquestração que o timer (scripts/coletar_transcricoes.py) e o botão
"Buscar agora" da tela compartilham. Uma implementação só: duas cópias do
"quando desistir" divergiriam, e a tela diria uma coisa enquanto o timer
fazia outra.

As regras (esperar, coletar, desistir) são puras e moram em
services/transcricao.py. O I/O com o Google em services/google_meet.py. O
resumo em services/resumo_reuniao.py. Aqui só a costura e o que vai para a
linha de `reuniao_transcricoes`.

NUNCA LEVANTA POR CAUSA DO GOOGLE OU DA IA. Toda falha de terceiro vira
coluna (`erro`, `resumo_erro`) e a função devolve o estado atual — mesma
regra da agenda. Quem chama é uma tela ou um timer; nenhum dos dois pode
morrer porque o Google estava fora do ar.

NENHUMA CHAMADA DE REDE COM TRANSAÇÃO ABERTA. As gravações aqui são
UPSERTs avulsos, cada um atômico por si; o Google é consultado entre eles.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services import google_meet, resumo_reuniao
from services import transcricao as regras
from services.agenda import fim_de

log = logging.getLogger("hipo.coleta_transcricao")

# O que a tela recebe quando a reunião não tem sala do Meet. Não é erro:
# reunião presencial ou por Zoom simplesmente não tem transcrição.
SEM_MEET = "sem_meet"
# Tem sala, mas ninguém procurou ainda (a reunião não acabou).
NAO_INICIADA = "nao_iniciada"

_SELECT = """
    SELECT r.id AS reuniao_id, r.tarefa_id, r.duracao_min,
           r.google_link, r.link_video, r.google_calendar_id,
           r.transcricao_auto_em, r.transcricao_auto_erro,
           r.desfecho,
           t.prazo AS inicio, t.cancelada_em,
           u.email AS anfitriao_email,
           tr.nome AS tipo_nome,
           COALESCE(cp.razao_social, co.razao_social) AS conta_razao_social,
           rt.reuniao_id AS rt_existe,
           rt.status, rt.motivo, rt.erro, rt.tentativas, rt.ultima_tentativa_em,
           rt.conferencias, rt.documento_url, rt.idioma, rt.entradas,
           rt.texto, rt.coletada_em, rt.resumo, rt.proximos_passos,
           rt.resumo_modelo, rt.resumo_em, rt.resumo_erro
      FROM reunioes r
      JOIN tarefas t ON t.id = r.tarefa_id
      LEFT JOIN usuarios u       ON u.id = t.responsavel_id
      LEFT JOIN tipos_reuniao tr ON tr.id = r.tipo_id
      LEFT JOIN oportunidades o  ON o.id = t.oportunidade_id
      LEFT JOIN contas co        ON co.id = o.conta_id
      LEFT JOIN contas cp        ON cp.id = t.conta_id
      LEFT JOIN reuniao_transcricoes rt ON rt.reuniao_id = r.id
"""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def _linha(conn, reuniao_id: UUID):
    return await conn.fetchrow(f"{_SELECT} WHERE r.id = $1", reuniao_id)


async def reuniao_da_tarefa(conn, tarefa_id: UUID) -> UUID | None:
    return await conn.fetchval("SELECT id FROM reunioes WHERE tarefa_id = $1", tarefa_id)


# ── Estado para a tela ───────────────────────────────────────────────


def estado(row, agora: datetime | None = None) -> dict:
    """
    O que a tela precisa saber, a partir da linha do banco. Puro.

    `status` ganha dois valores que não existem na tabela — `sem_meet` e
    `nao_iniciada` — porque a tela precisa distinguir "não tem como ter
    transcrição" de "ainda não é hora", e nenhum dos dois merece linha.
    """
    agora = agora or _agora()
    codigo = regras.codigo_meet(row["google_link"], row["link_video"])
    fim = fim_de(row["inicio"], row["duracao_min"])

    if row["rt_existe"] is not None:
        status = row["status"]
        motivo = row["motivo"]
    elif codigo is None:
        status = SEM_MEET
        motivo = "Esta reunião não tem sala do Google Meet."
    else:
        status = NAO_INICIADA
        motivo = (
            "A transcrição é buscada automaticamente depois que a reunião termina."
            if not regras.pode_procurar(fim, agora)
            else "Na fila: a próxima passada do coletor busca esta reunião."
        )

    passos = row["proximos_passos"]
    if isinstance(passos, str):
        passos = json.loads(passos)
    entradas = row["entradas"]
    if isinstance(entradas, str):
        entradas = json.loads(entradas)

    return {
        "reuniao_id": row["reuniao_id"],
        "tarefa_id": row["tarefa_id"],
        "status": status,
        "rotulo": regras.ROTULO_STATUS.get(status),
        "motivo": motivo,
        "erro": row["erro"],
        "tentativas": row["tentativas"] or 0,
        "ultima_tentativa_em": row["ultima_tentativa_em"],
        "tem_meet": codigo is not None,
        "documento_url": row["documento_url"],
        "idioma": row["idioma"],
        "texto": row["texto"],
        "falas": len(entradas or []),
        "coletada_em": row["coletada_em"],
        "resumo": row["resumo"],
        "proximos_passos": list(passos or []),
        "resumo_modelo": row["resumo_modelo"],
        "resumo_em": row["resumo_em"],
        "resumo_erro": row["resumo_erro"],
        "transcricao_auto_em": row["transcricao_auto_em"],
        "transcricao_auto_erro": row["transcricao_auto_erro"],
        "google_configurado": google_meet.configurado(),
        "ia_configurada": resumo_reuniao.configurado(),
        # O botão "Buscar agora" só faz sentido com sala, depois do fim,
        # dentro dos 30 dias da API, e antes de já ter o texto.
        "pode_buscar": (
            codigo is not None
            and row["cancelada_em"] is None
            and status != "pronta"
            and regras.pode_procurar(fim, agora)
            and regras.dentro_do_limite_da_api(fim, agora)
        ),
        "pode_resumir": status == "pronta" and bool(row["texto"]),
    }


async def obter(conn, reuniao_id: UUID, agora: datetime | None = None) -> dict:
    return estado(await _linha(conn, reuniao_id), agora)


# ── Gravação ─────────────────────────────────────────────────────────


async def _gravar(conn, reuniao_id: UUID, **campos) -> None:
    """
    UPSERT da linha, contando a tentativa.

    `conferencias` e `entradas` entram serializados; o resto passa direto.
    Coluna não mencionada fica como estava — um "aguardando" não pode
    apagar um resumo que outra passada já gravou.
    """
    colunas = list(campos)
    valores = [campos[c] for c in colunas]
    marcadores = []
    for i, c in enumerate(colunas, start=2):
        marcadores.append(f"${i}::jsonb" if c in ("entradas", "proximos_passos") else f"${i}")
    lista = ", ".join(colunas)
    insere = ", ".join(marcadores)
    atualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in colunas)
    await conn.execute(
        f"""
        INSERT INTO reuniao_transcricoes (reuniao_id, {lista}, tentativas, ultima_tentativa_em)
        VALUES ($1, {insere}, 1, NOW())
        ON CONFLICT (reuniao_id) DO UPDATE
           SET {atualiza},
               tentativas = reuniao_transcricoes.tentativas + 1,
               ultima_tentativa_em = NOW(),
               atualizado_em = NOW()
        """,
        reuniao_id, *valores,
    )


# ── A coleta ─────────────────────────────────────────────────────────


async def coletar(
    conn, reuniao_id: UUID, agora: datetime | None = None, manual: bool = False,
) -> dict:
    """
    Uma passada sobre uma reunião. Devolve o estado para a tela.

    `manual=True` é o botão da tela: reavalia também o que já tinha
    desistido (a pessoa pode ter acabado de ligar o escopo no Admin
    Console) e pode ir até o limite de 30 dias da API.
    """
    agora = agora or _agora()
    row = await _linha(conn, reuniao_id)
    if row is None:
        raise LookupError("Reunião não encontrada.")

    codigo = regras.codigo_meet(row["google_link"], row["link_video"])
    fim = fim_de(row["inicio"], row["duracao_min"])

    if (
        codigo is None
        or row["cancelada_em"] is not None
        or row["status"] == "pronta"
        or (row["status"] == "indisponivel" and not manual)
        or not regras.pode_procurar(fim, agora)
    ):
        return estado(row, agora)

    if not regras.dentro_do_limite_da_api(fim, agora):
        await _gravar(
            conn, reuniao_id, status="indisponivel", erro=None,
            motivo="Passaram-se 30 dias: o Google já apagou as falas desta reunião.",
        )
        return await obter(conn, reuniao_id, agora)

    email = row["google_calendar_id"] or row["anfitriao_email"]
    if not email:
        await _gravar(
            conn, reuniao_id, status="aguardando",
            motivo=None, erro="O anfitrião não tem e-mail cadastrado.",
        )
        return await obter(conn, reuniao_id, agora)

    lev = await google_meet.levantar(email, codigo)
    if lev.erro:
        await _gravar(conn, reuniao_id, status="aguardando", erro=lev.erro,
                      motivo="Não foi possível consultar o Google Meet.")
        return await obter(conn, reuniao_id, agora)

    decisao = regras.decidir(lev.conferencias, row["inicio"], fim, agora)
    if decisao.acao == "aguardar":
        await _gravar(conn, reuniao_id, status="aguardando", erro=None,
                      motivo=decisao.motivo)
        return await obter(conn, reuniao_id, agora)
    if decisao.acao == "desistir":
        await _gravar(conn, reuniao_id, status="indisponivel", erro=None,
                      motivo=decisao.motivo)
        return await obter(conn, reuniao_id, agora)

    baixado = await google_meet.baixar(email, decisao.conferencias)
    if baixado.erro:
        await _gravar(conn, reuniao_id, status="aguardando", erro=baixado.erro,
                      motivo="A transcrição existe, mas o download falhou.")
        return await obter(conn, reuniao_id, agora)

    texto = regras.texto_corrido(list(baixado.falas))
    if not texto.strip():
        await _gravar(
            conn, reuniao_id, status="indisponivel", erro=None,
            motivo="A transcrição foi gerada, mas veio sem nenhuma fala.",
            conferencias=list(baixado.conferencias),
            documento_url=baixado.documento_url,
        )
        return await obter(conn, reuniao_id, agora)

    await _gravar(
        conn, reuniao_id,
        status="pronta", motivo=None, erro=None,
        conferencias=list(baixado.conferencias),
        documento_url=baixado.documento_url,
        idioma=baixado.idioma,
        entradas=json.dumps(regras.entradas_json(list(baixado.falas)), ensure_ascii=False),
        texto=texto,
        coletada_em=agora,
    )
    log.info("coleta_transcricao: reuniao %s pronta (%d caracteres)", reuniao_id, len(texto))

    if resumo_reuniao.configurado():
        await resumir(conn, reuniao_id)
    return await obter(conn, reuniao_id, agora)


async def resumir(conn, reuniao_id: UUID) -> dict:
    """
    Gera (ou regera) o resumo de uma transcrição pronta.

    Separado da coleta porque tem vida própria: a chave da IA pode entrar
    no .env depois, e um resumo descartado pela guarda numérica merece um
    "gerar de novo" sem buscar a transcrição outra vez.
    """
    row = await _linha(conn, reuniao_id)
    if row is None:
        raise LookupError("Reunião não encontrada.")
    if row["status"] != "pronta" or not row["texto"]:
        return estado(row)

    r = await resumo_reuniao.resumir(
        row["texto"],
        resumo_reuniao.contexto_da_reuniao(
            row["conta_razao_social"], row["tipo_nome"], row["inicio"],
        ),
    )
    if r.erro:
        await conn.execute(
            """
            UPDATE reuniao_transcricoes
               SET resumo_erro = $2, atualizado_em = NOW()
             WHERE reuniao_id = $1
            """,
            reuniao_id, r.erro,
        )
    else:
        await conn.execute(
            """
            UPDATE reuniao_transcricoes
               SET resumo = $2, proximos_passos = $3::jsonb, resumo_modelo = $4,
                   resumo_em = NOW(), resumo_erro = NULL, atualizado_em = NOW()
             WHERE reuniao_id = $1
            """,
            reuniao_id, r.resumo,
            json.dumps(list(r.proximos_passos), ensure_ascii=False), r.modelo,
        )
    return await obter(conn, reuniao_id)


# ── Para o timer ─────────────────────────────────────────────────────


async def pendentes(conn, agora: datetime | None = None) -> list[UUID]:
    """
    As reuniões que o timer deve olhar nesta passada.

    Terminou (com a margem), terminou há no máximo JANELA_TIMER, tem link
    do Meet, não foi cancelada nem marcada como cancelada/no-show, e ainda
    não tem transcrição definitiva. O filtro fino (código válido) é refeito
    em `coletar` pela mesma função pura que a tela usa.
    """
    agora = agora or _agora()
    rows = await conn.fetch(
        """
        SELECT r.id
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
          LEFT JOIN reuniao_transcricoes rt ON rt.reuniao_id = r.id
         WHERE t.cancelada_em IS NULL
           AND (r.desfecho IS NULL OR r.desfecho = 'realizada')
           AND (r.google_link ILIKE '%meet.google.com/%'
                OR r.link_video ILIKE '%meet.google.com/%')
           AND t.prazo + make_interval(mins => r.duracao_min) <= $1
           AND t.prazo + make_interval(mins => r.duracao_min) >= $2
           AND (rt.reuniao_id IS NULL OR rt.status = 'aguardando')
         ORDER BY t.prazo
        """,
        agora - regras.MARGEM_POS_FIM,
        agora - regras.JANELA_TIMER,
    )
    return [r["id"] for r in rows]


async def sem_resumo(conn) -> list[UUID]:
    """
    Prontas sem resumo e sem erro de resumo: a chave da IA entrou depois,
    ou a coleta foi interrompida entre o texto e o resumo. As que têm
    `resumo_erro` NÃO voltam sozinhas — um resumo descartado pela guarda
    seria descartado de novo a cada 15 minutos, pagando a chamada toda vez.
    """
    rows = await conn.fetch(
        """
        SELECT reuniao_id FROM reuniao_transcricoes
         WHERE status = 'pronta' AND resumo IS NULL AND resumo_erro IS NULL
           AND coletada_em >= NOW() - INTERVAL '3 days'
        """
    )
    return [r["reuniao_id"] for r in rows]


# ── Ligar a transcrição automática na sala ───────────────────────────


async def ligar_na_sala(conn, reuniao_id: UUID, email: str, link: str | None) -> None:
    """
    Liga a transcrição automática da sala recém-criada e grava o resultado.

    Chamada pela agenda logo depois de o Google criar o evento com Meet.
    Só age uma vez por reunião: `transcricao_auto_em` preenchido encerra.
    Falha vira `transcricao_auto_erro` e a reunião segue — a transcrição
    ainda pode ser ligada à mão na call, e a coleta pega do mesmo jeito.
    """
    codigo = regras.codigo_meet(link)
    if codigo is None or not google_meet.configurado():
        return
    ja = await conn.fetchval(
        "SELECT transcricao_auto_em FROM reunioes WHERE id = $1", reuniao_id,
    )
    if ja is not None:
        return
    r = await google_meet.ligar_transcricao(email, codigo)
    if r.ok:
        await conn.execute(
            """
            UPDATE reunioes SET transcricao_auto_em = NOW(),
                   transcricao_auto_erro = NULL, atualizado_em = NOW()
             WHERE id = $1
            """,
            reuniao_id,
        )
    else:
        await conn.execute(
            "UPDATE reunioes SET transcricao_auto_erro = $2, atualizado_em = NOW() WHERE id = $1",
            reuniao_id, r.erro,
        )


# Reexportado para os testes e o script não precisarem conhecer o módulo
# de regras só para uma constante.
JANELA_TIMER: timedelta = regras.JANELA_TIMER
