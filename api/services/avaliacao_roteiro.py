"""
HIPO — Avaliação da reunião contra o Roteiro de Vendas (scorecard).

A transcrição chega do Meet; a IA lê a conversa com o roteiro da casa na
mão (services/roteiro_scorecard.py) e devolve:

  * a nota de 0 a 2 de cada um dos 10 itens do scorecard, com o TRECHO
    LITERAL da conversa que justifica a nota e uma sugestão de uma frase;
  * o "resumo do coach": dois pontos fortes, dois pontos a melhorar e um
    foco para a próxima reunião, cada um ancorado num trecho.

O tempo de fala do vendedor NÃO vem da IA: é contado aqui, das falas.

── A IA SUGERE, A GESTÃO AJUSTA ────────────────────────────────────

Decisão do Tulio (02/10): a nota vale assim que sai — entra no Monitor e
na lista do APRE na hora. A gestão pode trocar a nota de qualquer item, e
aí vale a dela (COALESCE(nota_gestor, nota_ia)). Validar é um selo, não um
portão.

── A CHECAGEM DE EVIDÊNCIA ─────────────────────────────────────────

Equivalente à guarda numérica do resumo. Nota 1 ou 2 exige um trecho que
EXISTA na transcrição (normalizado: caixa, acento, pontuação, espaços). Se
o trecho não está lá, a nota daquele item é descartada (`nota = None`,
`descartado` com o motivo) e o item conta 0 até a gestão dar a nota à mão.
É o que impede um "2 em Implicação" baseado numa pergunta que ninguém fez.
Nos pontos fortes e a melhorar, o trecho que não confere some e o texto
fica — é comentário, não nota.

── FALHA VIRA COLUNA ───────────────────────────────────────────────

Sem chave, HTTP != 200, resposta fora do schema, item faltando ou
repetido: `Avaliacao.erro` em português e nenhuma exceção. Quem chama é o
coletor (timer) ou uma tela; nenhum dos dois pode morrer porque a IA
respondeu torto.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field

import httpx

from config import settings
from services import ia
from services import roteiro_scorecard as sc
from services.transcricao import recorte_para_ia

log = logging.getLogger("hipo.avaliacao_roteiro")

TIMEOUT_S = 150.0
MAX_TOKENS = 5000
MAX_PONTOS = 2
TAM_MINIMO_TRECHO = 6

NOME_FERRAMENTA = "registrar_avaliacao"

DESFECHOS_SEM_AVALIACAO = ("no_show", "cancelada")


# ── Elegibilidade (pura) ─────────────────────────────────────────────


def elegivel(alvo: str | None, transcricao_status: str | None,
             desfecho: str | None, cancelada: bool = False) -> bool:
    """
    A reunião entra no scorecard?

    Só reunião de OPORTUNIDADE (reunião de parceiro não é venda), com
    transcrição pronta, que não foi desmarcada nem no-show.

    >>> elegivel('oportunidade', 'pronta', 'realizada')
    True
    >>> elegivel('oportunidade', 'pronta', None)
    True
    >>> elegivel('parceiro', 'pronta', 'realizada')
    False
    >>> elegivel('oportunidade', 'aguardando', None)
    False
    >>> elegivel('oportunidade', 'pronta', 'no_show')
    False
    >>> elegivel('oportunidade', 'pronta', None, cancelada=True)
    False
    """
    if alvo != "oportunidade" or transcricao_status != "pronta":
        return False
    if cancelada or desfecho in DESFECHOS_SEM_AVALIACAO:
        return False
    return True


# ── Texto (puro) ─────────────────────────────────────────────────────


def normalizar(texto: str | None) -> str:
    """
    Caixa, acento, pontuação e espaço fora: o que sobra é a sequência de
    palavras. A transcrição do Meet e a citação da IA divergem nesses
    detalhes sem divergir no que foi dito.

    >>> normalizar("  Você  JÁ fez, a NR-1? ")
    'voce ja fez a nr 1'
    """
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^0-9a-z]+", " ", sem_acento.lower()).split())


def evidencia_confere(trecho: str | None, transcricao: str) -> bool:
    """
    O trecho citado existe na transcrição?

    Aceita reticências no meio ("quanto custa ... parado"): cada pedaço
    precisa existir, na ordem. Pedaço curto demais (menos de 6 caracteres
    normalizados) não prova nada e não conta como pedaço.

    >>> t = "[10:01] Bruno: E o que te incomoda hoje no fornecedor atual?"
    >>> evidencia_confere("o que te incomoda hoje", t)
    True
    >>> evidencia_confere("O QUE TE INCOMODA... fornecedor atual", t)
    True
    >>> evidencia_confere("quanto custa um dia parado", t)
    False
    >>> evidencia_confere("", t)
    False
    """
    alvo = normalizar(transcricao)
    pedacos = [
        normalizar(p) for p in re.split(r"\.{3,}|…|\[\.\.\.\]", trecho or "")
    ]
    pedacos = [p for p in pedacos if len(p) >= TAM_MINIMO_TRECHO]
    if not pedacos:
        return False
    posicao = 0
    for p in pedacos:
        achou = alvo.find(p, posicao)
        if achou < 0:
            return False
        posicao = achou + len(p)
    return True


def _tokens_nome(nome: str | None) -> list[str]:
    return normalizar(nome).split()


def mesmo_nome(participante: str | None, vendedor: str | None) -> bool:
    """
    O participante do Meet é o vendedor?

    O Meet escreve o nome da conta Google ("BRUNO GONÇALO"); o HIPO, o do
    cadastro ("Bruno Gonçalo"). Bate o primeiro nome e, quando os dois têm
    sobrenome, o último também. Primeiro nome sozinho só vale se um dos
    lados for nome único.

    >>> mesmo_nome("BRUNO GONÇALO", "Bruno Gonçalo")
    True
    >>> mesmo_nome("JAKELINE SANTANA", "Jakeline Santana Silva")
    True
    >>> mesmo_nome("Bruno Lima", "Bruno Gonçalo")
    False
    >>> mesmo_nome("Bruno", "Bruno Gonçalo")
    True
    >>> mesmo_nome("Cliente", "Bruno Gonçalo")
    False
    """
    p, v = _tokens_nome(participante), _tokens_nome(vendedor)
    if not p or not v or p[0] != v[0]:
        return False
    if len(p) == 1 or len(v) == 1:
        return True
    return p[-1] == v[-1] or p[1] == v[1]


def fala_vendedor_pct(entradas: list[dict] | None, vendedor: str | None) -> float | None:
    """
    Percentual das PALAVRAS da reunião ditas pelo vendedor.

    None quando não dá para saber (vendedor não identificado entre os
    participantes, ou reunião sem fala): a tela mostra "vendedor não
    identificado", nunca um número chutado.

    >>> e = [{"participante": "BRUNO GONÇALO", "texto": "um dois tres"},
    ...      {"participante": "Cliente", "texto": "quatro"}]
    >>> fala_vendedor_pct(e, "Bruno Gonçalo")
    75.0
    >>> fala_vendedor_pct(e, "Jakeline Santana") is None
    True
    >>> fala_vendedor_pct([], "Bruno") is None
    True
    """
    total = 0
    dele = 0
    for e in entradas or []:
        n = len((e.get("texto") or "").split())
        total += n
        if mesmo_nome(e.get("participante"), vendedor):
            dele += n
    if total == 0 or dele == 0:
        return None
    return round(dele * 100 / total, 1)


# ── Resultado ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ItemAvaliado:
    item: int
    nota: int | None
    evidencia: str | None
    justificativa: str | None
    sugestao: str | None
    descartado: str | None = None


@dataclass(frozen=True)
class Ponto:
    texto: str
    evidencia: str | None = None
    como_fazer: str | None = None


@dataclass(frozen=True)
class Avaliacao:
    itens: tuple[ItemAvaliado, ...] = ()
    pontos_fortes: tuple[Ponto, ...] = ()
    pontos_melhorar: tuple[Ponto, ...] = ()
    foco_proxima: str | None = None
    resumo: str | None = None
    modelo: str | None = None
    erro: str | None = None
    descartados: tuple[int, ...] = field(default_factory=tuple)


def total(notas: list[int | None]) -> int:
    """
    A nota da reunião: soma dos itens. Item sem nota (descartado e ainda
    não avaliado à mão) conta zero — a nota não sobe por falta de prova.

    >>> total([2, 1, None, 0])
    3
    """
    return sum(n for n in notas if n is not None)


# ── O schema da ferramenta (tool use) ────────────────────────────────


def _schema() -> dict:
    ponto = {
        "type": "object",
        "properties": {
            "texto": {"type": "string"},
            "evidencia": {"type": "string"},
        },
        "required": ["texto", "evidencia"],
    }
    melhorar = {
        "type": "object",
        "properties": {
            "texto": {"type": "string"},
            "evidencia": {"type": "string"},
            "como_fazer": {"type": "string"},
        },
        "required": ["texto", "evidencia", "como_fazer"],
    }
    return {
        "type": "object",
        "properties": {
            "itens": {
                "type": "array",
                "minItems": sc.QTD_ITENS,
                "maxItems": sc.QTD_ITENS,
                "items": {
                    "type": "object",
                    "properties": {
                        "item": {"type": "integer", "minimum": 1, "maximum": sc.QTD_ITENS},
                        "nota": {"type": "integer", "minimum": 0, "maximum": sc.NOTA_MAXIMA_ITEM},
                        "evidencia": {"type": "string"},
                        "justificativa": {"type": "string"},
                        "sugestao": {"type": "string"},
                    },
                    "required": ["item", "nota", "evidencia", "justificativa", "sugestao"],
                },
            },
            "pontos_fortes": {"type": "array", "maxItems": MAX_PONTOS, "items": ponto},
            "pontos_melhorar": {"type": "array", "maxItems": MAX_PONTOS, "items": melhorar},
            "foco_proxima": {"type": "string"},
            "resumo": {"type": "string"},
        },
        "required": ["itens", "pontos_fortes", "pontos_melhorar", "foco_proxima", "resumo"],
    }


INSTRUCAO = """Você é o coach comercial da Controller Med Seg, empresa de
medicina e segurança do trabalho que vende para empresas (PJ). Você avalia
UMA reunião comercial do vendedor, lendo a transcrição, contra o Roteiro de
Vendas da casa e o scorecard de 10 itens abaixo. Quem lê a sua avaliação é
o próprio vendedor, logo depois da reunião, e o gestor dele.

{roteiro}

SCORECARD (0 a 2 por item, máximo 20):

{itens}

COMO AVALIAR
- Avalie o lado da Controller na conversa. O responsável é o vendedor
  indicado nos dados da reunião; se um colega da Controller conduziu um
  trecho, ele conta para o item, mas a sugestão é dirigida ao vendedor.
- Seja justo e literal com o critério: o roteiro foi criado em 30/09/2026 e
  muitos vendedores ainda não foram treinados nele. Não dê nota por boa
  intenção; dê pelo que aconteceu na conversa.
- Item 5 (Implicação): só conta PERGUNTA que faz o cliente dizer o custo do
  problema. O vendedor contar uma história de multa ou de processo é
  afirmação, não pergunta: nota 0 nesse caso.
- Item 3 (Situação): conte as perguntas factuais antes da primeira pergunta
  de Problema. Sem pergunta de Problema na reunião inteira, nota 0.
- Item 10: "vou te mandar a proposta" ou "a gente vai conversando" é nota 1
  no máximo; 2 exige dia E hora aceitos pelo cliente.

EVIDÊNCIA (regra mais importante)
- Notas 1 e 2 EXIGEM em "evidencia" um trecho COPIADO LITERALMENTE da
  transcrição: só as palavras faladas, sem o horário e sem o nome de quem
  falou, com 5 a 30 palavras. Pode usar "..." para pular um trecho no meio.
- Existe verificação automática: trecho que não estiver escrito na
  transcrição DESCARTA a nota daquele item. Não corrija o português da
  transcrição, não resuma, não parafraseie.
- Nota 0: "evidencia" pode ficar vazia ("").
- "justificativa": uma frase dizendo por que a nota é essa.
- "sugestao": UMA frase dizendo o que fazer diferente na próxima reunião,
  de preferência com a fala do roteiro adaptada a ESTE cliente. Nota 2:
  diga o que manter.

RESUMO DO COACH
- "pontos_fortes": até 2, o que o vendedor fez bem, cada um com trecho
  literal em "evidencia".
- "pontos_melhorar": até 2, os de maior impacto na venda, cada um com
  trecho literal em "evidencia" e "como_fazer" (a fala ou ação concreta).
- "foco_proxima": UMA frase com o único comportamento a treinar na
  próxima reunião.
- "resumo": 2 ou 3 frases com a leitura geral da reunião.

Regras gerais:
- Português do Brasil, direto, sem elogio vazio, sem markdown.
- Não invente nome, número, prazo ou fala. Use só o que está na transcrição.
- A transcrição automática erra palavras; trecho incompreensível não serve
  de evidência.
- Responda chamando a ferramenta registrar_avaliacao com os 10 itens.
"""


def instrucao() -> str:
    return INSTRUCAO.format(roteiro=sc.ROTEIRO, itens=sc.texto_dos_itens())


def payload(texto: str, contexto: dict) -> dict:
    """O corpo da chamada, com saída estruturada via tool use."""
    cabecalho = json.dumps(contexto, ensure_ascii=False, default=str)
    return {
        "model": modelo(),
        "max_tokens": MAX_TOKENS,
        "system": instrucao(),
        "tools": [{
            "name": NOME_FERRAMENTA,
            "description": "Registra a avaliação da reunião no scorecard do roteiro.",
            "input_schema": _schema(),
        }],
        "tool_choice": {"type": "tool", "name": NOME_FERRAMENTA},
        "messages": [{
            "role": "user",
            "content": (
                f"Dados da reunião (JSON): {cabecalho}\n\n"
                "Transcrição:\n\n" + recorte_para_ia(texto)
            ),
        }],
    }


# Modelo proprio porque o trabalho e outro: o resumo e uma leitura rapida;
# a avaliacao julga dez criterios e cita trecho literal de cada um. Fica
# AQUI, e nao em config.py, de proposito: config.py esta sendo mexido por
# outra entrega, e com `extra="forbid"` um campo novo no .env antes do
# campo existir derruba a API. Para trocar sem deploy, o campo
# ANTHROPIC_MODEL_AVALIACAO pode entrar em config.py depois -- `modelo()`
# ja o le se existir.
MODELO_PADRAO = "claude-sonnet-4-5"


def modelo() -> str:
    return (getattr(settings, "ANTHROPIC_MODEL_AVALIACAO", "") or "").strip() \
        or MODELO_PADRAO


# ── Leitura da resposta (pura) ───────────────────────────────────────


class RespostaInvalida(Exception):
    """A IA respondeu fora do schema. A mensagem vai para a coluna `erro`."""


def entrada_da_ferramenta(corpo: dict) -> dict | None:
    """O `input` do bloco tool_use da resposta da Messages API."""
    for bloco in corpo.get("content") or []:
        if bloco.get("type") == "tool_use" and bloco.get("name") == NOME_FERRAMENTA:
            entrada = bloco.get("input")
            return entrada if isinstance(entrada, dict) else None
    return None


def _str(v) -> str | None:
    return " ".join(v.split()) if isinstance(v, str) and v.strip() else None


def _pontos(lista, transcricao: str, com_como: bool) -> tuple[Ponto, ...]:
    pontos = []
    for p in (lista if isinstance(lista, list) else [])[:MAX_PONTOS]:
        if not isinstance(p, dict) or not _str(p.get("texto")):
            continue
        evidencia = _str(p.get("evidencia"))
        if evidencia and not evidencia_confere(evidencia, transcricao):
            evidencia = None
        pontos.append(Ponto(
            texto=_str(p["texto"]),
            evidencia=evidencia,
            como_fazer=_str(p.get("como_fazer")) if com_como else None,
        ))
    return tuple(pontos)


def ler_entrada(entrada: dict | None, transcricao: str) -> Avaliacao:
    """
    Valida a resposta e aplica a checagem de evidência.

    Levanta RespostaInvalida quando o formato não serve (item faltando,
    repetido, nota fora de 0..2). Evidência que não confere NÃO levanta:
    descarta a nota do item e segue.

    >>> itens = [{"item": n, "nota": 0, "evidencia": "", "justificativa": "j",
    ...           "sugestao": "s"} for n in range(1, 11)]
    >>> itens[3] = {"item": 4, "nota": 2, "evidencia": "o que te incomoda hoje",
    ...             "justificativa": "j", "sugestao": "s"}
    >>> itens[4] = {"item": 5, "nota": 1, "evidencia": "pergunta inventada aqui",
    ...             "justificativa": "j", "sugestao": "s"}
    >>> a = ler_entrada({"itens": itens, "pontos_fortes": [], "pontos_melhorar": [],
    ...                  "foco_proxima": "f", "resumo": "r"},
    ...                 "Bruno: o que te incomoda hoje?")
    >>> a.itens[3].nota, a.itens[4].nota, a.descartados
    (2, None, (5,))
    """
    if not isinstance(entrada, dict):
        raise RespostaInvalida("A IA não devolveu a avaliação no formato esperado.")
    brutos = entrada.get("itens")
    if not isinstance(brutos, list):
        raise RespostaInvalida("A IA não devolveu a lista de itens do scorecard.")

    vistos: dict[int, ItemAvaliado] = {}
    descartados = []
    for b in brutos:
        if not isinstance(b, dict):
            raise RespostaInvalida("Item do scorecard fora do formato.")
        numero, nota = b.get("item"), b.get("nota")
        if isinstance(numero, bool) or not isinstance(numero, int) \
                or numero not in sc.POR_NUMERO:
            raise RespostaInvalida(f"Item do scorecard inválido: {numero!r}.")
        if numero in vistos:
            raise RespostaInvalida(f"O item {numero} veio repetido.")
        if isinstance(nota, bool) or not isinstance(nota, int) \
                or not 0 <= nota <= sc.NOTA_MAXIMA_ITEM:
            raise RespostaInvalida(f"Nota inválida no item {numero}: {nota!r}.")

        evidencia = _str(b.get("evidencia"))
        descartado = None
        if nota > 0:
            if not evidencia:
                descartado = "Nota sem trecho da conversa que a justifique."
            elif not evidencia_confere(evidencia, transcricao):
                descartado = "Trecho citado não foi encontrado na transcrição."
            if descartado:
                descartados.append(numero)
        elif evidencia and not evidencia_confere(evidencia, transcricao):
            evidencia = None

        vistos[numero] = ItemAvaliado(
            item=numero,
            nota=None if descartado else nota,
            evidencia=evidencia,
            justificativa=_str(b.get("justificativa")),
            sugestao=_str(b.get("sugestao")),
            descartado=descartado,
        )

    faltando = sorted(set(sc.POR_NUMERO) - set(vistos))
    if faltando:
        raise RespostaInvalida(
            "A IA não avaliou os itens " + ", ".join(str(n) for n in faltando) + "."
        )

    return Avaliacao(
        itens=tuple(vistos[n] for n in sorted(vistos)),
        pontos_fortes=_pontos(entrada.get("pontos_fortes"), transcricao, False),
        pontos_melhorar=_pontos(entrada.get("pontos_melhorar"), transcricao, True),
        foco_proxima=_str(entrada.get("foco_proxima")),
        resumo=_str(entrada.get("resumo")),
        descartados=tuple(descartados),
    )


# ── A chamada ────────────────────────────────────────────────────────


def configurado() -> bool:
    return ia.configurada()


async def avaliar(texto: str, contexto: dict) -> Avaliacao:
    """Avalia a reunião. Nunca levanta: erro volta em `Avaliacao.erro`."""
    if not configurado():
        return Avaliacao(erro="ANTHROPIC_API_KEY não configurada — avaliação desligada.")
    if not (texto or "").strip():
        return Avaliacao(erro="Transcrição vazia; nada para avaliar.")

    cabecalhos = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": ia.VERSAO_API,
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
            resp = await cliente.post(ia.URL_API, headers=cabecalhos,
                                      json=payload(texto, contexto))
    except Exception as e:
        log.warning("avaliacao_roteiro: chamada falhou (%s: %s)", type(e).__name__, e)
        return Avaliacao(erro=f"A chamada à IA falhou: {type(e).__name__}.")

    if resp.status_code != 200:
        log.warning("avaliacao_roteiro: HTTP %s — %s", resp.status_code, resp.text[:300])
        return Avaliacao(erro=f"A IA respondeu HTTP {resp.status_code}.")

    try:
        resultado = ler_entrada(entrada_da_ferramenta(resp.json()), texto)
    except RespostaInvalida as e:
        log.warning("avaliacao_roteiro: %s", e)
        return Avaliacao(erro=str(e))

    if resultado.descartados:
        log.info("avaliacao_roteiro: itens sem evidência descartados: %s",
                 resultado.descartados)
    return Avaliacao(
        itens=resultado.itens,
        pontos_fortes=resultado.pontos_fortes,
        pontos_melhorar=resultado.pontos_melhorar,
        foco_proxima=resultado.foco_proxima,
        resumo=resultado.resumo,
        modelo=modelo(),
        descartados=resultado.descartados,
    )
