"""
HIPO — Roleplay · avaliação contra o Roteiro de Vendas (RP-2).

Mesma régua das reuniões reais (services/roteiro_scorecard.py, 10 itens de
0 a 2) e a mesma CHECAGEM DE EVIDÊNCIA (services/avaliacao_roteiro.py):
nota 1 ou 2 exige um trecho que exista na transcrição. O que muda:

  * a instrução diz que é um TREINO, qual bloco foi treinado e o que a
    persona escondia — o coach sabe o que dava para descobrir;
  * BLOCO conta só os itens do bloco (`itens_foco` do cenário), e a nota é
    reescalada para /20: 6 de 8 pontos no bloco de objeções vira 15,0. A
    reunião completa conta os 10 itens;
  * a transcrição do Live erra palavras ("ASUS" no lugar de ASO, "bien"):
    o coach é avisado e o trecho citado continua tendo de ser literal.

Puro: monta o pedido, lê a resposta e calcula a nota. A chamada à IA fica
num `chamar_ia` pequeno, o único pedaço que os testes dublam. A gravação
no banco é do router (routers/roleplay.py), dono das tabelas.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import httpx

from config import settings
from services import avaliacao_roteiro as aval
from services import ia
from services import roteiro_scorecard as sc

log = logging.getLogger("hipo.roleplay_avaliacao")

TIMEOUT_S = 150.0
MAX_TOKENS = 5000
# Conversa curta demais não tem o que avaliar: sem isto, um teste de
# microfone de 20 segundos viraria "nota 0" no histórico.
MIN_FALAS_EXECUTIVO = 3
MIN_PALAVRAS_EXECUTIVO = 40

TODOS = tuple(range(1, sc.QTD_ITENS + 1))


class SemConteudo(ValueError):
    """Conversa curta demais para avaliar (mensagem para a tela)."""


@dataclass(frozen=True)
class Resultado:
    avaliacao: aval.Avaliacao
    itens_foco: tuple[int, ...]


# ── Regras (puras) ───────────────────────────────────────────────────

def itens_do_cenario(cenario: dict | None) -> tuple[int, ...]:
    """Itens que contam na nota. Sem cenário (removido do código) → os 10."""
    foco = tuple(sorted(set((cenario or {}).get("itens_foco") or ())))
    return foco or TODOS


def nota_reescalada(notas: dict[int, int | None], itens_foco: tuple[int, ...]) -> Decimal | None:
    """
    Soma dos itens do foco reescalada para 0..20, uma casa. Item sem nota
    (descartado) conta zero. Sem item nenhum → None.

    >>> nota_reescalada({8: 2, 9: 1, 10: 1, 1: 2}, (8, 9, 10))
    Decimal('13.3')
    >>> nota_reescalada({n: 2 for n in range(1, 11)}, tuple(range(1, 11)))
    Decimal('20.0')
    >>> nota_reescalada({9: None}, (9,))
    Decimal('0.0')
    """
    if not itens_foco:
        return None
    soma = sum((notas.get(i) or 0) for i in itens_foco)
    maximo = sc.NOTA_MAXIMA_ITEM * len(itens_foco)
    valor = Decimal(soma) * Decimal(sc.NOTA_MAXIMA) / Decimal(maximo)
    return valor.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def conferir_conteudo(transcricao: list[dict]) -> None:
    """Levanta SemConteudo se o executivo quase não falou."""
    falas = [t for t in transcricao if t.get("quem") == "executivo"]
    palavras = sum(len((t.get("texto") or "").split()) for t in falas)
    if len(falas) < MIN_FALAS_EXECUTIVO or palavras < MIN_PALAVRAS_EXECUTIVO:
        raise SemConteudo("Conversa curta demais para avaliar: fale um pouco mais no próximo treino.")


def _relogio(t_ms: int) -> str:
    s = max(0, int(t_ms or 0)) // 1000
    return f"[{s // 60:02d}:{s % 60:02d}]"


def texto_da_transcricao(transcricao: list[dict]) -> str:
    """
    No formato das reuniões reais ("[mm:ss] Nome: fala"), para a checagem
    de evidência (avaliacao_roteiro.so_falas) tirar o prefixo de cada linha.

    >>> texto_da_transcricao([{"quem": "executivo", "texto": "Oi", "t_ms": 65000},
    ...                       {"quem": "cliente", "texto": "Olá", "t_ms": 70000}])
    '[01:05] Executivo: Oi\\n[01:10] Cliente: Olá'
    """
    return "\n".join(
        f"{_relogio(t.get('t_ms'))} {'Executivo' if t['quem'] == 'executivo' else 'Cliente'}: {t['texto']}"
        for t in transcricao
    )


INSTRUCAO = """Você é o coach comercial da Controller Med Seg, empresa de
medicina e segurança do trabalho que vende para empresas (PJ). Você avalia
um ROLEPLAY DE TREINO: o executivo conversou por voz com uma IA que fez o
papel do cliente. Quem lê a avaliação é o próprio executivo, logo depois do
treino, e a gestão dele.

{roteiro}

SCORECARD (0 a 2 por item):

{itens}

O TREINO
- Bloco treinado: {bloco}. Objetivo do bloco: {objetivo}
- ITENS QUE CONTAM NESTE BLOCO: {foco}. Avalie esses com todo o rigor.
  Os outros itens: nota 0, evidência vazia e justificativa "Fora do bloco
  treinado." (eles não entram na nota).
- O que o executivo sabia antes (briefing): {briefing}
- O que o "cliente" escondia e só revelava com a pergunta certa (persona):
{persona}
  Use isso para julgar a descoberta: dor que existia e não foi perguntada é
  oportunidade perdida, e vale sugestão. Mas a NOTA continua sendo pelo que
  aconteceu na conversa, não pelo que poderia ter acontecido.

COMO AVALIAR
- Avalie só o executivo. As falas do cliente são da IA.
- Seja justo e literal com o critério. Não dê nota por boa intenção.
- Item 5 (Implicação): só conta PERGUNTA que faz o cliente dizer o custo do
  problema. Afirmar o risco não conta.
- Item 3 (Situação): conte as perguntas factuais antes da primeira pergunta
  de Problema. Sem pergunta de Problema, nota 0.
- Item 10: "vou te mandar a proposta" é nota 1 no máximo; 2 exige dia E hora
  aceitos pelo cliente.
- Preço dado antes de saber quem decide, conta errada de valores ou de
  horas (ex.: dizer um número e depois outro) são pontos a melhorar.

TRANSCRIÇÃO AUTOMÁTICA
- A transcrição erra palavras ("ASUS" no lugar de ASO, "Controlar" no lugar
  de Controller, palavras soltas como "bien"). Entenda o sentido, mas a
  EVIDÊNCIA continua tendo de ser copiada literalmente, com o erro e tudo.

EVIDÊNCIA (regra mais importante)
- Notas 1 e 2 EXIGEM em "evidencia" um trecho COPIADO LITERALMENTE da
  transcrição: só as palavras faladas, sem o horário e sem "Executivo:" ou
  "Cliente:", com 5 a 30 palavras. Pode usar "..." para pular um trecho.
- Existe verificação automática: trecho que não estiver na transcrição
  DESCARTA a nota daquele item. Não corrija, não resuma, não parafraseie.
- "justificativa": uma frase dizendo por que a nota é essa.
- "sugestao": UMA frase com o que fazer diferente no próximo treino, de
  preferência a fala do roteiro adaptada a ESTE cliente. Nota 2: o que manter.

RESUMO DO COACH (só sobre os itens do bloco)
- "pontos_fortes": até 2, cada um com trecho literal em "evidencia".
- "pontos_melhorar": até 2, os de maior impacto, com trecho literal e
  "como_fazer" (a fala ou ação concreta).
- "foco_proxima": UMA frase com o único comportamento a treinar no próximo
  roleplay.
- "resumo": 2 ou 3 frases com a leitura geral do treino.

Regras gerais: português do Brasil, direto, sem elogio vazio, sem markdown.
Não invente fala. Responda chamando a ferramenta registrar_avaliacao com os
10 itens.
"""


def instrucao(cenario: dict | None, itens_foco: tuple[int, ...]) -> str:
    c = cenario or {}
    nomes = ", ".join(f"{i} ({sc.POR_NUMERO[i].nome})" for i in itens_foco)
    return INSTRUCAO.format(
        roteiro=sc.ROTEIRO,
        itens=sc.texto_dos_itens(),
        bloco=c.get("titulo") or "reunião completa",
        objetivo=c.get("objetivo") or "conduzir a reunião inteira.",
        foco=nomes,
        briefing=" ".join((c.get("briefing") or "").split()),
        persona=c.get("persona") or "(não disponível)",
    )


def modelo() -> str:
    return aval.modelo()


def payload(transcricao_txt: str, cenario: dict | None, itens_foco: tuple[int, ...]) -> dict:
    return {
        "model": modelo(),
        "max_tokens": MAX_TOKENS,
        "system": instrucao(cenario, itens_foco),
        "tools": [{
            "name": aval.NOME_FERRAMENTA,
            "description": "Registra a avaliação do roleplay no scorecard do roteiro.",
            "input_schema": aval._schema(),
        }],
        "tool_choice": {"type": "tool", "name": aval.NOME_FERRAMENTA},
        "messages": [{"role": "user", "content": "Transcrição do roleplay:\n\n" + transcricao_txt}],
    }


def ler_resposta(corpo: dict, transcricao_txt: str) -> aval.Avaliacao:
    """Valida a resposta (10 itens, notas 0..2) e aplica a checagem de evidência."""
    resultado = aval.ler_entrada(aval.entrada_da_ferramenta(corpo), transcricao_txt)
    return aval.Avaliacao(
        itens=resultado.itens,
        pontos_fortes=resultado.pontos_fortes,
        pontos_melhorar=resultado.pontos_melhorar,
        foco_proxima=resultado.foco_proxima,
        resumo=resultado.resumo,
        modelo=modelo(),
        descartados=resultado.descartados,
    )


# ── A chamada ────────────────────────────────────────────────────────

async def chamar_ia(corpo: dict) -> dict:
    """POST na Messages API. Levanta RuntimeError com mensagem em português."""
    cabecalhos = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": ia.VERSAO_API,
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
            resp = await cliente.post(ia.URL_API, headers=cabecalhos, json=corpo)
    except Exception as e:  # noqa: BLE001 - qualquer falha de rede vira mensagem
        raise RuntimeError(f"A chamada à IA falhou: {type(e).__name__}.") from e
    if resp.status_code != 200:
        log.warning("roleplay_avaliacao: HTTP %s — %s", resp.status_code, resp.text[:300])
        raise RuntimeError(f"A IA respondeu HTTP {resp.status_code}.")
    return resp.json()


async def avaliar(transcricao: list[dict], cenario: dict | None) -> Resultado:
    """
    Avalia o roleplay. Levanta SemConteudo (conversa curta) ou RuntimeError
    (sem chave, rede, resposta fora do formato) — quem chama grava o motivo.
    """
    conferir_conteudo(transcricao)
    if not ia.configurada():
        raise RuntimeError("ANTHROPIC_API_KEY não configurada: avaliação desligada.")
    foco = itens_do_cenario(cenario)
    texto = texto_da_transcricao(transcricao)
    corpo = await chamar_ia(payload(texto, cenario, foco))
    try:
        return Resultado(ler_resposta(corpo, texto), foco)
    except aval.RespostaInvalida as e:
        raise RuntimeError(str(e)) from e


def itens_para_tela(itens_foco: tuple[int, ...]) -> list[dict]:
    """Nome, etapa e critérios dos itens do foco, para a tela explicar a nota."""
    return [
        {"item": i, "nome": sc.POR_NUMERO[i].nome, "etapa": sc.POR_NUMERO[i].etapa,
         "criterio_2": sc.POR_NUMERO[i].criterio_2}
        for i in itens_foco
    ]


def json_pontos(pontos) -> str:
    return json.dumps(
        [{"texto": p.texto, "evidencia": p.evidencia, "como_fazer": p.como_fazer} for p in pontos],
        ensure_ascii=False,
    )
