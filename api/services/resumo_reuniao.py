"""
HIPO — Resumo da reunião pela API da Anthropic.

Lê a transcrição e devolve duas coisas: um resumo curto do que foi
conversado e a lista de próximos passos que ficaram combinados.

O QUE A IA NÃO FAZ AQUI: registrar o desfecho, concluir a tarefa ou criar
a próxima. O resumo é SUGESTÃO para quem conduziu a reunião. "Concluir
exige agendar a próxima" continua valendo, e quem responde por ela é a
pessoa — um próximo passo inventado pela IA virando tarefa sozinho seria
um compromisso com o cliente que ninguém assumiu.

MESMA GUARDA NUMÉRICA DO FECHAMENTO. Em reunião comercial o número É o
conteúdo: quantidade de vidas, valor, prazo. Um "R$ 45 por vida" que
ninguém disse, lido no resumo por quem vai montar a proposta, custa
dinheiro. Todo número do resumo precisa aparecer escrito na transcrição
(ou na data da reunião); se não aparecer, o resumo é descartado e a tela
diz por quê, com um botão de gerar de novo. Ver services/validacao_numerica.

FALHA NÃO É SILENCIOSA AQUI, ao contrário de ia.narrar: quem chama é uma
tela (ou o coletor, que grava na linha), então o erro volta como texto para
a coluna `resumo_erro`.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

import httpx

from config import settings
from services import ia
from services.agenda import FUSO_OPERACAO
from services.transcricao import recorte_para_ia
from services.validacao_numerica import contexto, numeros_invalidos, numeros_permitidos

log = logging.getLogger("hipo.resumo_reuniao")

MAX_PASSOS = 8

INSTRUCAO = """Você lê a transcrição de uma reunião comercial de uma empresa
que vende serviços de medicina e segurança do trabalho para outras empresas.
Quem vai ler o seu texto é o vendedor que conduziu a reunião, logo depois
dela, para registrar o que aconteceu e decidir a próxima ação.

Responda SOMENTE com um objeto JSON, sem markdown, neste formato:

{"resumo": "...", "proximos_passos": ["...", "..."]}

- "resumo": 3 a 6 frases em português do Brasil. O que o cliente precisa, as
  objeções ou dúvidas que levantou, o que foi apresentado e em que pé a
  negociação ficou.
- "proximos_passos": as ações que ficaram COMBINADAS na conversa, uma por
  item, começando pelo verbo ("Enviar a proposta revisada para ...").
  No máximo 8. Lista vazia se nada foi combinado.

Regras:
- Use SÓ o que está na transcrição. Não invente nome, empresa, valor, prazo,
  quantidade ou compromisso.
- NÚMEROS: escreva exatamente como aparecem na transcrição. Se um número
  foi dito por extenso ("cinquenta vidas"), escreva por extenso. Não some,
  não converta, não calcule percentual. Existe uma verificação automática, e
  um número que não esteja escrito na transcrição descarta o resumo inteiro.
- Próximo passo é o que alguém DISSE que ia fazer. Não sugira ação que
  ninguém combinou, nem prazo que ninguém falou.
- A transcrição automática erra palavras. Se um trecho estiver incompreensível,
  ignore-o em vez de adivinhar.
- Nomes de pessoas: use como aparecem na transcrição.
"""


@dataclass(frozen=True)
class Resumo:
    resumo: str | None = None
    proximos_passos: tuple[str, ...] = ()
    modelo: str | None = None
    erro: str | None = None


def configurado() -> bool:
    return ia.configurada()


# ── Montagem e leitura (puras) ───────────────────────────────────────


def payload(texto: str, contexto_reuniao: dict) -> dict:
    """
    O corpo da chamada. `contexto_reuniao` leva empresa, tipo e data — o que
    ajuda a IA a entender a conversa sem ter de adivinhar de quem é.
    """
    cabecalho = json.dumps(contexto_reuniao, ensure_ascii=False, default=str)
    return {
        "model": settings.ANTHROPIC_MODEL,
        "max_tokens": 1500,
        "system": INSTRUCAO,
        "messages": [{
            "role": "user",
            "content": (
                f"Dados da reunião (JSON): {cabecalho}\n\n"
                "Transcrição:\n\n" + recorte_para_ia(texto)
            ),
        }],
    }


def ler_resposta(bruto: str | None) -> tuple[str | None, list[str]]:
    """
    Extrai (resumo, próximos passos) do texto do modelo.

    Tolera o JSON embrulhado em ```json``` ou com texto antes e depois —
    o modelo às vezes faz isso mesmo instruído a não fazer, e perder o
    resumo por uma cerca de markdown seria perder por formatação.

    >>> ler_resposta('{"resumo": "Ok.", "proximos_passos": ["Ligar"]}')
    ('Ok.', ['Ligar'])
    >>> ler_resposta('```json\\n{"resumo": "A", "proximos_passos": []}\\n```')
    ('A', [])
    >>> ler_resposta("sem json nenhum")
    (None, [])
    """
    if not bruto:
        return None, []
    achado = re.search(r"\{.*\}", bruto, re.S)
    if not achado:
        return None, []
    try:
        dados = json.loads(achado.group(0))
    except json.JSONDecodeError:
        return None, []
    if not isinstance(dados, dict):
        return None, []
    resumo = dados.get("resumo")
    resumo = " ".join(resumo.split()) if isinstance(resumo, str) and resumo.strip() else None
    passos_brutos = dados.get("proximos_passos") or []
    passos = [
        " ".join(p.split()) for p in passos_brutos
        if isinstance(p, str) and p.strip()
    ][:MAX_PASSOS] if isinstance(passos_brutos, list) else []
    return resumo, passos


def conferir_numeros(
    resumo: str | None, passos: list[str], texto: str, contexto_reuniao: dict,
) -> list[tuple[str, str]]:
    """
    Números do resumo que não estão na transcrição nem nos dados da reunião.

    Devolve pares (número, trecho) para o erro dizer ONDE: sem a frase,
    "número 30 fora da transcrição" não permite saber se foi o modelo que
    inventou ou a transcrição que escreveu por extenso.

    >>> conferir_numeros("São 50 vidas.", [], "temos 50 vidas", {})
    []
    >>> conferir_numeros("São 60 vidas.", [], "temos 50 vidas", {})[0][0]
    '60'
    """
    escrito = " ".join([resumo or "", *passos])
    permitidos = numeros_permitidos([texto, contexto_reuniao])
    return [(n, contexto(escrito, n)) for n in numeros_invalidos(escrito, permitidos)]


# ── A chamada ────────────────────────────────────────────────────────


async def resumir(texto: str, contexto_reuniao: dict) -> Resumo:
    """Gera o resumo. Nunca levanta: erro volta em `Resumo.erro`."""
    if not configurado():
        return Resumo(erro="ANTHROPIC_API_KEY não configurada — resumo desligado.")
    if not (texto or "").strip():
        return Resumo(erro="Transcrição vazia; nada para resumir.")

    cabecalhos = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": ia.VERSAO_API,
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=ia.TIMEOUT_S) as cliente:
            resp = await cliente.post(
                ia.URL_API, headers=cabecalhos, json=payload(texto, contexto_reuniao),
            )
    except Exception as e:
        log.warning("resumo_reuniao: chamada falhou (%s: %s)", type(e).__name__, e)
        return Resumo(erro=f"A chamada à IA falhou: {type(e).__name__}")

    if resp.status_code != 200:
        log.warning("resumo_reuniao: HTTP %s — %s", resp.status_code, resp.text[:300])
        return Resumo(erro=f"A IA respondeu HTTP {resp.status_code}.")

    bruto = ia._texto_da_resposta(resp.json())
    resumo, passos = ler_resposta(bruto)
    if not resumo:
        log.warning("resumo_reuniao: resposta fora do formato: %r", (bruto or "")[:300])
        return Resumo(erro="A IA respondeu fora do formato esperado.")

    fora = conferir_numeros(resumo, passos, texto, contexto_reuniao)
    if fora:
        for numero, trecho in fora[:5]:
            log.error("resumo_reuniao: %r fora da transcricao em: %s", numero, trecho)
        numeros = ", ".join(n for n, _ in fora[:5])
        return Resumo(
            erro=(
                f"Resumo descartado: citou número que não está na transcrição "
                f"({numeros})."
            ),
        )

    return Resumo(
        resumo=resumo, proximos_passos=tuple(passos), modelo=settings.ANTHROPIC_MODEL,
    )


def contexto_da_reuniao(
    empresa: str | None, tipo: str | None, inicio: datetime | None,
) -> dict:
    """O cabeçalho que vai junto da transcrição, sem campo vazio."""
    # A data no fuso da OPERACAO: 22h de segunda em Brasilia ja e terca em
    # UTC, e a guarda numerica liberaria o dia errado.
    dia = inicio.astimezone(FUSO_OPERACAO).date().isoformat() if inicio else None
    d = {"empresa": empresa, "tipo_de_reuniao": tipo, "data": dia}
    return {k: v for k, v in d.items() if v}
