"""
HIPO — Narrativa do dia pela API da Anthropic.

O que a IA faz aqui: ler as métricas já calculadas e escrever três ou quatro
parágrafos apontando o que mudou e o que merece ação amanhã.

O que ela NÃO faz: calcular. Todo número do relatório vem do Postgres e é
renderizado direto do JSON. O texto do modelo é comentário sobre números que
já existem — se ele errar, erra na leitura, não no dado. Essa separação é
deliberada: um relatório em que a IA soma é um relatório que não dá para usar
sem conferir, e um relatório que precisa ser conferido não economiza tempo
de ninguém.

FALHA É SILENCIOSA POR DESIGN. Sem chave, com timeout, com 429 ou com a API
fora do ar, `narrar()` devolve None e o fechamento segue. O e-mail sai com
todos os números e sem a narrativa. O contrário — segurar o relatório porque
o texto de apoio falhou — troca a parte essencial pela acessória.

O QUE A GUARDA NUMÉRICA NÃO PEGA — e é o limite dela, não um defeito.
`validacao_numerica` confere NÚMEROS, não AFIRMAÇÕES. Na primeira narrativa
gerada em produção (28/08), o modelo escreveu "as tarefas atrasadas
cresceram" num dia em que `comparativo.disponivel` era false: o "22" estava
certo, o "cresceram" era inventado, e a guarda deixou passar porque todo
número da frase existia na telemetria. Alegação de tendência e explicação de
causa só podem ser barradas na INSTRUCAO — que ganhou duas regras dedicadas a
isso. Se voltarem a aparecer, o ajuste é lá, não aqui.
"""
from __future__ import annotations

import json
import logging

import httpx

from config import settings
from services.validacao_numerica import numeros_invalidos, numeros_permitidos

log = logging.getLogger("hipo.ia")

URL_API = "https://api.anthropic.com/v1/messages"
VERSAO_API = "2023-06-01"
TIMEOUT_S = 45.0

INSTRUCAO = """Você analisa a telemetria diária do HIPO, o CRM de uma operação
de medicina e segurança ocupacional. Quem lê é o dono da operação.

Escreva 3 ou 4 parágrafos curtos, em português do Brasil, sobre o dia:

1. O que aconteceu de fato — volume de uso e o que andou na operação.
2. O que destoa: alguém que não entrou, erro repetido, número que chama
   atenção pelo tamanho.
3. Uma recomendação concreta para amanhã, ligada a um número específico.

Regras:
- NÃO invente número, nome ou tendência que não esteja no JSON.
- NÃO repita a tabela: quem lê já vê os números acima do seu texto.
- MOVIMENTO SÓ COM COMPARATIVO. Os contadores do JSON são fotografias do dia,
  não séries históricas. Só diga que algo subiu, caiu, cresceu ou vem
  acumulando quando comparativo.disponivel for true E o número estiver lá.
  Sem isso, descreva o ESTADO ("22 tarefas em atraso") e nunca o MOVIMENTO
  ("as tarefas em atraso cresceram") — você não tem como saber qual era o
  número ontem.
- NÃO EXPLIQUE A CAUSA de um número. O JSON diz o que aconteceu, não por quê.
  "Seis pessoas não acessaram" é observação; "por isso o atraso cresceu" é
  invenção — e é o tipo de invenção que passa batido, porque cada número
  citado na frase está correto.
- Refira-se ao dia pela data ou pelo dia da semana, nunca como "ontem" ou
  "hoje". O fechamento pode ser gerado dias depois do dia que ele descreve, e
  aí "ontem" aponta para o dia errado.
- Se adocao.disponivel for false, a captura de uso NÃO estava ativa nesse dia.
  Nesse caso não diga que ninguém acessou nem cite ausentes: diga que não há
  telemetria para o dia e comente apenas o bloco de operação.
- Se o dia foi vazio ou quase, diga isso em uma frase e pare. Dia parado não
  merece três parágrafos de análise.
- Sem saudação, sem despedida, sem markdown. Só os parágrafos.
- Cite nomes de pessoas quando for relevante para a ação.
"""


def configurada() -> bool:
    """True se há chave de API. O fechamento usa isso para nem tentar."""
    return bool(getattr(settings, "ANTHROPIC_API_KEY", "").strip())


def _payload(metricas: dict) -> dict:
    return {
        "model": settings.ANTHROPIC_MODEL,
        "max_tokens": 1200,
        "system": INSTRUCAO,
        "messages": [{
            "role": "user",
            "content": (
                "Telemetria do dia (JSON):\n\n"
                + json.dumps(metricas, ensure_ascii=False, indent=2)
            ),
        }],
    }


def _texto_da_resposta(corpo: dict) -> str | None:
    blocos = corpo.get("content") or []
    partes = [b.get("text", "") for b in blocos if b.get("type") == "text"]
    texto = "\n".join(p for p in partes if p).strip()
    return texto or None


async def narrar(metricas: dict) -> tuple[str | None, str | None]:
    """
    Devolve (narrativa, modelo). Ambos None quando a IA não entrou.

    Nunca levanta exceção: o chamador é um cron noturno sem ninguém olhando,
    e um traceback ali significa relatório não enviado.
    """
    if not configurada():
        log.info("ia: ANTHROPIC_API_KEY não configurada, relatório sai sem narrativa")
        return None, None

    cabecalhos = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": VERSAO_API,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
            resp = await cliente.post(URL_API, headers=cabecalhos, json=_payload(metricas))
        if resp.status_code != 200:
            # O corpo do erro traz o motivo (chave inválida, crédito, modelo
            # inexistente). Truncado: não vale poluir o log com a resposta
            # inteira de um 500 da outra ponta.
            log.warning("ia: HTTP %s — %s", resp.status_code, resp.text[:300])
            return None, None
        texto = _texto_da_resposta(resp.json())
        if texto:
            # A INSTRUCAO pede que o modelo nao invente numero; isto
            # verifica. Pedido em prompt nao e garantia, e este e o unico
            # ponto do fechamento onde um defeito produz saida plausivel e
            # errada em vez de erro.
            inventados = numeros_invalidos(texto, numeros_permitidos(metricas))
            if inventados:
                # ERROR, nao WARNING: se isto aparece direto no journal, o
                # relatorio esta saindo sem narrativa todo dia e ninguem viu.
                # O ajuste e na INSTRUCAO, nao na guarda.
                log.error(
                    "ia: narrativa descartada, numeros fora da telemetria (%s)",
                    ", ".join(inventados),
                )
                return None, None
        return texto, settings.ANTHROPIC_MODEL
    except Exception as e:
        log.warning("ia: chamada falhou (%s: %s)", type(e).__name__, e)
        return None, None
