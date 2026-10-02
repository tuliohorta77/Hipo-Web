"""
HIPO — Scorecard da reunião: orquestração (banco + IA).

As regras e a chamada à IA moram em services/avaliacao_roteiro.py; o
roteiro, em services/roteiro_scorecard.py. Aqui fica o que encosta no
banco: quem é elegível, gravar o resultado, o ajuste da gestão, o selo de
validação e a fila do timer.

QUANDO A AVALIAÇÃO RODA
  Na mesma passada do hipo-transcricoes.timer que trouxe a transcrição
  (scripts/coletar_transcricoes.py): coleta, resumo e, logo depois, a
  avaliação das reuniões de oportunidade que ficaram prontas. O botão
  "Buscar agora" da tela NÃO avalia na mesma requisição — a avaliação leva
  até dois minutos e a tela não pode ficar pendurada; ela sai na próxima
  passada (no máximo 15 minutos) ou pelo botão "Avaliar".

ESTE MÓDULO É O ÚNICO QUE ESCREVE EM reuniao_avaliacoes. É por isso que
`nota_total` pode ser guardada: toda escrita de item termina em
`_recalcular_total`, e o Monitor só lê o número.

DUAS AVALIAÇÕES DA MESMA REUNIÃO AO MESMO TEMPO
  O timer e o botão podem coincidir. Um advisory lock do Postgres por
  reunião (pg_try_advisory_lock) faz o segundo desistir com
  `EmAndamento`, em vez de pagar a IA duas vezes e gravar por cima.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from services import avaliacao_roteiro as aval
from services import roteiro_scorecard as sc
from services.tarefa import FUSO_OPERACAO, janela_utc

log = logging.getLogger("hipo.coleta_avaliacao")

# Status que não existem na tabela, só na resposta para a tela.
NAO_ELEGIVEL = "nao_elegivel"
NA_FILA = "na_fila"

# O timer tenta de novo uma avaliação com erro até este número de vezes.
# Depois disso, só pelo botão: erro que se repete três vezes é da
# transcrição ou da configuração, e insistir a cada 15 minutos é pagar a
# mesma resposta torta.
MAX_TENTATIVAS_TIMER = 3

# Avaliação em "aguardando" há mais que isto caiu no meio (processo morto
# durante a chamada). O timer pode pegar de novo.
AGUARDANDO_TRAVADA = timedelta(minutes=10)

# O timer só olha reuniões recentes. As antigas entram pelo script de
# backfill (scripts/avaliar_reunioes.py), que é decisão explícita — e não
# uma conta de IA que aparece sozinha no dia do deploy.
JANELA_TIMER = timedelta(days=3)


class AvaliacaoIndisponivel(Exception):
    """A reunião não pode ser avaliada (motivo em português)."""


class EmAndamento(Exception):
    """Outra avaliação desta reunião está rodando agora."""


_SELECT = """
    SELECT r.id AS reuniao_id, r.tarefa_id, r.desfecho,
           t.prazo AS inicio, t.cancelada_em, t.oportunidade_id, t.conta_id,
           t.responsavel_id,
           u.nome AS vendedor_nome, u.cargo AS vendedor_cargo,
           ag.nome AS agendado_por_nome,
           tr.nome AS tipo_nome,
           COALESCE(co.nome_fantasia, co.razao_social) AS empresa,
           o.fase AS oportunidade_fase,
           rt.status AS transcricao_status, rt.texto, rt.entradas,
           av.reuniao_id AS av_existe, av.versao_roteiro, av.status,
           av.nota_total, av.vendedor_id, av.fala_vendedor_pct,
           av.resumo, av.foco_proxima, av.pontos_fortes, av.pontos_melhorar,
           av.modelo, av.erro, av.tentativas, av.gerada_em,
           av.validada_em, av.atualizado_em,
           av_v.nome AS avaliado_nome,
           val.nome AS validada_por_nome
      FROM reunioes r
      JOIN tarefas t ON t.id = r.tarefa_id
      LEFT JOIN usuarios u        ON u.id = t.responsavel_id
      LEFT JOIN usuarios ag       ON ag.id = r.agendado_por
      LEFT JOIN tipos_reuniao tr  ON tr.id = r.tipo_id
      LEFT JOIN oportunidades o   ON o.id = t.oportunidade_id
      LEFT JOIN contas co         ON co.id = o.conta_id
      LEFT JOIN reuniao_transcricoes rt ON rt.reuniao_id = r.id
      LEFT JOIN reuniao_avaliacoes av   ON av.reuniao_id = r.id
      LEFT JOIN usuarios av_v     ON av_v.id = av.vendedor_id
      LEFT JOIN usuarios val      ON val.id = av.validada_por
"""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _json(v):
    if isinstance(v, str):
        return json.loads(v)
    return v


async def _linha(conn, reuniao_id: UUID):
    return await conn.fetchrow(f"{_SELECT} WHERE r.id = $1", reuniao_id)


def _alvo(row) -> str:
    return "oportunidade" if row["oportunidade_id"] is not None else "parceiro"


def motivo_inelegivel(row) -> str | None:
    """
    Por que a reunião NÃO entra no scorecard, em português. None = entra.

    Mesma regra de `avaliacao_roteiro.elegivel`; aqui ela ganha a frase
    que a tela mostra.
    """
    if _alvo(row) != "oportunidade":
        return "Reunião de parceiro não entra no scorecard de vendas."
    if row["cancelada_em"] is not None or row["desfecho"] == "cancelada":
        return "Reunião desmarcada: não há conversa para avaliar."
    if row["desfecho"] == "no_show":
        return "No-show: não há conversa para avaliar."
    if row["transcricao_status"] != "pronta" or not row["texto"]:
        return "A avaliação sai quando a transcrição da reunião chegar."
    return None


async def _itens(conn, reuniao_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT i.item, i.nota_ia, i.nota_gestor, i.evidencia, i.justificativa,
               i.sugestao, i.descartado, i.ajustada_em, u.nome AS ajustada_por_nome
          FROM reuniao_avaliacao_itens i
          LEFT JOIN usuarios u ON u.id = i.ajustada_por
         WHERE i.reuniao_id = $1
         ORDER BY i.item
        """,
        reuniao_id,
    )
    itens = []
    for r in rows:
        meta = sc.POR_NUMERO.get(r["item"])
        nota = r["nota_gestor"] if r["nota_gestor"] is not None else r["nota_ia"]
        itens.append({
            "item": r["item"],
            "nome": meta.nome if meta else f"Item {r['item']}",
            "etapa": meta.etapa if meta else None,
            "o_que_procurar": meta.o_que_procurar if meta else None,
            "criterios": (
                [meta.criterio_0, meta.criterio_1, meta.criterio_2] if meta else []
            ),
            "nota": nota,
            "nota_ia": r["nota_ia"],
            "nota_gestor": r["nota_gestor"],
            "evidencia": r["evidencia"],
            "justificativa": r["justificativa"],
            "sugestao": r["sugestao"],
            "descartado": r["descartado"],
            "ajustada_por_nome": r["ajustada_por_nome"],
            "ajustada_em": r["ajustada_em"],
        })
    return itens


async def obter(conn, reuniao_id: UUID) -> dict:
    """O estado do scorecard para a tela."""
    row = await _linha(conn, reuniao_id)
    if row is None:
        raise LookupError("Reunião não encontrada.")

    motivo = motivo_inelegivel(row)
    tem_linha = row["av_existe"] is not None
    if tem_linha:
        status = row["status"]
    elif motivo:
        status = NAO_ELEGIVEL
    else:
        status = NA_FILA

    if status == NA_FILA:
        motivo_tela = (
            "Na fila: a avaliação sai na próxima passada do coletor."
            if aval.configurado()
            else "A IA não está configurada: a avaliação está desligada."
        )
    elif status == "aguardando":
        motivo_tela = "A IA está avaliando esta reunião."
    else:
        motivo_tela = motivo if status == NAO_ELEGIVEL else None

    itens = await _itens(conn, reuniao_id) if status == "pronta" else []
    total = row["nota_total"] if status == "pronta" else None
    fala = row["fala_vendedor_pct"]
    validada = row["validada_em"] is not None
    return {
        "reuniao_id": row["reuniao_id"],
        "tarefa_id": row["tarefa_id"],
        "status": status,
        "motivo": motivo_tela,
        "versao_roteiro": row["versao_roteiro"] or sc.VERSAO,
        "nota_total": total,
        "nota_maxima": sc.NOTA_MAXIMA,
        "faixa": sc.faixa(total),
        "meta": sc.META_PADRAO,
        "vendedor_nome": row["avaliado_nome"] or row["vendedor_nome"],
        "fala_vendedor_pct": float(fala) if fala is not None else None,
        "meta_fala_pct": sc.META_FALA_PCT,
        "resumo": row["resumo"],
        "foco_proxima": row["foco_proxima"],
        "pontos_fortes": list(_json(row["pontos_fortes"]) or []),
        "pontos_melhorar": list(_json(row["pontos_melhorar"]) or []),
        "modelo": row["modelo"],
        "erro": row["erro"],
        "tentativas": row["tentativas"] or 0,
        "gerada_em": row["gerada_em"],
        "validada": validada,
        "validada_por_nome": row["validada_por_nome"],
        "validada_em": row["validada_em"],
        "ajustada": any(i["nota_gestor"] is not None for i in itens),
        "itens": itens,
        "ia_configurada": aval.configurado(),
        # Gerar de novo: elegível, IA ligada, nada rodando e sem o selo — a
        # avaliação validada é registro da gestão e não se sobrescreve.
        "pode_gerar": (
            motivo is None
            and aval.configurado()
            and status != "aguardando"
            and not validada
        ),
    }


# ── A avaliação ──────────────────────────────────────────────────────


def contexto(row) -> dict:
    """O cabeçalho que vai junto da transcrição para a IA."""
    inicio = row["inicio"]
    participantes = []
    for e in _json(row["entradas"]) or []:
        nome = (e.get("participante") or "").strip()
        if nome and nome not in participantes:
            participantes.append(nome)
    d = {
        "empresa": row["empresa"],
        "tipo_de_reuniao": row["tipo_nome"],
        "data": inicio.astimezone(FUSO_OPERACAO).strftime("%Y-%m-%d %H:%M") if inicio else None,
        "vendedor_responsavel": row["vendedor_nome"],
        "cargo_do_vendedor": row["vendedor_cargo"],
        "agendada_por": row["agendado_por_nome"],
        "fase_da_oportunidade": row["oportunidade_fase"],
        "participantes_na_transcricao": participantes,
    }
    return {k: v for k, v in d.items() if v}


async def _tentar_trava(conn, reuniao_id: UUID) -> bool:
    return bool(await conn.fetchval(
        "SELECT pg_try_advisory_lock(hashtext('avaliacao:' || $1::text))",
        str(reuniao_id),
    ))


async def _soltar_trava(conn, reuniao_id: UUID) -> None:
    await conn.execute(
        "SELECT pg_advisory_unlock(hashtext('avaliacao:' || $1::text))",
        str(reuniao_id),
    )


async def _recalcular_total(conn, reuniao_id: UUID) -> None:
    await conn.execute(
        """
        UPDATE reuniao_avaliacoes
           SET nota_total = (
                 SELECT COALESCE(SUM(COALESCE(nota_gestor, nota_ia)), 0)
                   FROM reuniao_avaliacao_itens WHERE reuniao_id = $1
               ),
               atualizado_em = NOW()
         WHERE reuniao_id = $1
        """,
        reuniao_id,
    )


async def avaliar(conn, reuniao_id: UUID, usuario_id: UUID | None = None) -> dict:
    """
    Avalia (ou reavalia) a reunião e grava. Devolve o estado para a tela.

    Levanta AvaliacaoIndisponivel (não elegível, validada) e EmAndamento
    (outra avaliação rodando). Falha da IA NÃO levanta: vira `erro`.

    Reavaliar uma avaliação pronta que falha mantém a anterior: a nota que
    já estava no Monitor não some porque a segunda chamada caiu.
    """
    row = await _linha(conn, reuniao_id)
    if row is None:
        raise LookupError("Reunião não encontrada.")
    motivo = motivo_inelegivel(row)
    if motivo:
        raise AvaliacaoIndisponivel(motivo)
    if row["validada_em"] is not None:
        raise AvaliacaoIndisponivel(
            "Avaliação validada pela gestão: tire a validação antes de avaliar de novo."
        )
    if not aval.configurado():
        raise AvaliacaoIndisponivel("A IA não está configurada: a avaliação está desligada.")

    if not await _tentar_trava(conn, reuniao_id):
        raise EmAndamento("Esta reunião já está sendo avaliada. Aguarde um instante.")
    try:
        ja_pronta = row["status"] == "pronta"
        await conn.execute(
            """
            INSERT INTO reuniao_avaliacoes (reuniao_id, versao_roteiro, status, tentativas)
            VALUES ($1, $2, 'aguardando', 1)
            ON CONFLICT (reuniao_id) DO UPDATE
               SET status = CASE WHEN reuniao_avaliacoes.status = 'pronta'
                                 THEN 'pronta' ELSE 'aguardando' END,
                   tentativas = reuniao_avaliacoes.tentativas + 1,
                   atualizado_em = NOW()
            """,
            reuniao_id, sc.VERSAO,
        )

        resultado = await aval.avaliar(row["texto"], contexto(row))

        if resultado.erro:
            await conn.execute(
                """
                UPDATE reuniao_avaliacoes
                   SET status = CASE WHEN $3 THEN 'pronta' ELSE 'erro' END,
                       erro = $2, atualizado_em = NOW()
                 WHERE reuniao_id = $1
                """,
                reuniao_id, resultado.erro, ja_pronta,
            )
            log.warning("coleta_avaliacao: reuniao %s: %s", reuniao_id, resultado.erro)
            return await obter(conn, reuniao_id)

        entradas = _json(row["entradas"]) or []
        fala = aval.fala_vendedor_pct(entradas, row["vendedor_nome"])
        fortes = [
            {"texto": p.texto, "evidencia": p.evidencia} for p in resultado.pontos_fortes
        ]
        melhorar = [
            {"texto": p.texto, "evidencia": p.evidencia, "como_fazer": p.como_fazer}
            for p in resultado.pontos_melhorar
        ]
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM reuniao_avaliacao_itens WHERE reuniao_id = $1", reuniao_id,
            )
            await conn.executemany(
                """
                INSERT INTO reuniao_avaliacao_itens
                       (reuniao_id, item, nota_ia, evidencia, justificativa,
                        sugestao, descartado)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (reuniao_id, i.item, i.nota, i.evidencia, i.justificativa,
                     i.sugestao, i.descartado)
                    for i in resultado.itens
                ],
            )
            await conn.execute(
                """
                UPDATE reuniao_avaliacoes
                   SET status = 'pronta', versao_roteiro = $2,
                       nota_total = $3, vendedor_id = $4, fala_vendedor_pct = $5,
                       resumo = $6, foco_proxima = $7,
                       pontos_fortes = $8::jsonb, pontos_melhorar = $9::jsonb,
                       modelo = $10, erro = NULL, gerada_em = NOW(),
                       gerada_por = $11, validada_em = NULL, validada_por = NULL,
                       atualizado_em = NOW()
                 WHERE reuniao_id = $1
                """,
                reuniao_id, sc.VERSAO,
                aval.total([i.nota for i in resultado.itens]),
                row["responsavel_id"], fala,
                resultado.resumo, resultado.foco_proxima,
                json.dumps(fortes, ensure_ascii=False),
                json.dumps(melhorar, ensure_ascii=False),
                resultado.modelo, usuario_id,
            )
        log.info("coleta_avaliacao: reuniao %s avaliada", reuniao_id)
        return await obter(conn, reuniao_id)
    finally:
        await _soltar_trava(conn, reuniao_id)


# ── A gestão ─────────────────────────────────────────────────────────


async def _exigir_pronta(conn, reuniao_id: UUID) -> None:
    status = await conn.fetchval(
        "SELECT status FROM reuniao_avaliacoes WHERE reuniao_id = $1", reuniao_id,
    )
    if status != "pronta":
        raise AvaliacaoIndisponivel("Esta reunião ainda não tem avaliação pronta.")


async def ajustar_item(
    conn, reuniao_id: UUID, item: int, nota: int | None, usuario_id: UUID,
) -> dict:
    """
    A gestão dá a nota de um item. `nota=None` desfaz o ajuste e volta a
    valer a da IA.
    """
    if item not in sc.POR_NUMERO:
        raise AvaliacaoIndisponivel(f"Item inválido: {item}.")
    if nota is not None and not 0 <= nota <= sc.NOTA_MAXIMA_ITEM:
        raise AvaliacaoIndisponivel("A nota de um item vai de 0 a 2.")
    await _exigir_pronta(conn, reuniao_id)
    async with conn.transaction():
        await conn.execute(
            """
            UPDATE reuniao_avaliacao_itens
               SET nota_gestor = $3,
                   ajustada_por = CASE WHEN $3::smallint IS NULL THEN NULL ELSE $4::uuid END,
                   ajustada_em  = CASE WHEN $3::smallint IS NULL THEN NULL ELSE NOW() END
             WHERE reuniao_id = $1 AND item = $2
            """,
            reuniao_id, item, nota, usuario_id,
        )
        await _recalcular_total(conn, reuniao_id)
    return await obter(conn, reuniao_id)


async def validar(conn, reuniao_id: UUID, usuario_id: UUID | None, validada: bool = True) -> dict:
    """Põe (ou tira) o selo da gestão. Não muda nenhuma nota."""
    await _exigir_pronta(conn, reuniao_id)
    await conn.execute(
        """
        UPDATE reuniao_avaliacoes
           SET validada_em  = CASE WHEN $2 THEN NOW() ELSE NULL END,
               validada_por = CASE WHEN $2 THEN $3::uuid ELSE NULL END,
               atualizado_em = NOW()
         WHERE reuniao_id = $1
        """,
        reuniao_id, validada, usuario_id,
    )
    return await obter(conn, reuniao_id)


# ── Filas ────────────────────────────────────────────────────────────


_ELEGIVEIS = """
    SELECT r.id
      FROM reunioes r
      JOIN tarefas t ON t.id = r.tarefa_id
      JOIN reuniao_transcricoes rt ON rt.reuniao_id = r.id
      LEFT JOIN reuniao_avaliacoes av ON av.reuniao_id = r.id
     WHERE t.oportunidade_id IS NOT NULL
       AND t.cancelada_em IS NULL
       AND (r.desfecho IS NULL OR r.desfecho = 'realizada')
       AND rt.status = 'pronta' AND rt.texto IS NOT NULL
"""


async def pendentes(conn, agora: datetime | None = None) -> list[UUID]:
    """
    O que o timer avalia nesta passada: reuniões recentes (JANELA_TIMER)
    sem avaliação, com erro e ainda dentro das tentativas, ou travadas em
    "aguardando" (processo caiu no meio).
    """
    agora = agora or _agora()
    rows = await conn.fetch(
        _ELEGIVEIS + """
       AND t.prazo >= $1
       AND (av.reuniao_id IS NULL
            OR (av.status = 'erro' AND av.tentativas < $2)
            OR (av.status = 'aguardando' AND av.atualizado_em < $3))
     ORDER BY t.prazo
        """,
        agora - JANELA_TIMER, MAX_TENTATIVAS_TIMER, agora - AGUARDANDO_TRAVADA,
    )
    return [r["id"] for r in rows]


async def elegiveis_desde(conn, desde: date, refazer: bool = False) -> list[UUID]:
    """
    Para o backfill: as reuniões elegíveis desde `desde` (no fuso da
    operação). Sem `refazer`, só as que ainda não têm avaliação pronta; com
    `refazer`, também as prontas — mas nunca as validadas.
    """
    inicio, _ = janela_utc(desde, desde)
    filtro = (
        "AND (av.reuniao_id IS NULL OR av.validada_em IS NULL)"
        if refazer else
        "AND (av.reuniao_id IS NULL OR av.status <> 'pronta')"
    )
    rows = await conn.fetch(
        _ELEGIVEIS + f" AND t.prazo >= $1 {filtro} ORDER BY t.prazo",
        inicio,
    )
    return [r["id"] for r in rows]
