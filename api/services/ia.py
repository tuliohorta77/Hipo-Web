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
from services.validacao_numerica import (
    contexto, numeros_invalidos, numeros_permitidos,
)

log = logging.getLogger("hipo.ia")

URL_API = "https://api.anthropic.com/v1/messages"
VERSAO_API = "2023-06-01"
TIMEOUT_S = 45.0

INSTRUCAO = """Você analisa a telemetria diária do HIPO, o CRM de uma operação
de medicina e segurança ocupacional. Quem lê é o dono da operação.

Escreva 3 ou 4 parágrafos curtos, em português do Brasil:

1. O que precisa de ação no funil. Use `conteudo.precisa_de_acao`: cite as
   oportunidades pelo NÚMERO e pela CONTA, e repita o motivo que já vem em
   `motivos`. Comece pela primeira da lista — ela já vem ordenada por
   urgência.
2. O que está perto de fechar (`conteudo.perto_de_fechar`) e quem dá para
   acionar por indicação (`conteudo.parceiros_para_acionar`).
3. O que aconteceu no dia — uso do sistema e movimento da operação.
4. Uma recomendação concreta para amanhã, ligada a UM item específico
   daqueles que você citou.

Regras:
- NÃO invente número, nome ou tendência que não esteja no JSON.
- NOME DE EMPRESA, DE PESSOA E NÚMERO DE OPORTUNIDADE só podem sair do JSON,
  copiados exatamente como estão. Esta é a regra mais importante do texto:
  existe uma verificação automática dos NÚMEROS, e ela não olha nomes — um
  cliente inventado passaria direto e seria lido como verdade.
- As listas de `conteudo` já vêm cortadas nos cinco primeiros. Os campos
  `*_mais` dizem quantos ficaram de fora; se quiser mencioná-los, fale do
  total, nunca de itens que você não recebeu.
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
- NÃO DEDUZA o dia da semana a partir de uma data. Use `dia_semana` quando ele
  vier no JSON e, se não vier, cite só a data. O fechamento de 31/08 chamou
  28/08 de "segunda-feira" — era sexta. Nenhum número estava errado, então a
  verificação automática não pegou, e a frase inteira ficou falsa.
- Se adocao.disponivel for false, a captura de uso NÃO estava ativa nesse dia.
  Nesse caso não diga que ninguém acessou nem cite ausentes: diga que não há
  telemetria para o dia e comente apenas o bloco de operação.
- Se o dia foi vazio ou quase, diga isso em uma frase e pare. Dia parado não
  merece três parágrafos de análise.
- Sem saudação, sem despedida, sem markdown. Só os parágrafos.
- Cite nomes de pessoas quando for relevante para a ação.
"""


# Campos que o e-mail deixou de mostrar em 31/08 e que, por isso, a narrativa
# tambem nao pode citar.
_CAMPOS_OCULTOS = ("rotas_mais_usadas", "erros_por_rota")


def metricas_para_narrar(metricas: dict) -> dict:
    """
    Copia das metricas SEM o detalhe de rota.

    POR QUE ISTO PRECISA EXISTIR

    As tabelas "Telas mais usadas" e "Erros do dia" sairam do e-mail, mas os
    dados continuaram no payload -- e o modelo continuou narrando a partir
    deles. O fechamento de 31/08 saiu dizendo "consultou 117 vezes dados de
    contas especificas" e "a rota de vincular contatos mostrou 33 falhas":
    numeros corretos, verificaveis por ninguem, porque nao existe mais tabela
    onde conferi-los.

    O rodape do bloco promete "os numeros vem do banco" e aponta para os
    numeros ABAIXO. Numero citado que nao esta em lugar nenhum quebra essa
    promessa -- e e pior que numero inventado, porque parece conferivel.

    A regra que isto materializa: A NARRATIVA SO FALA DO QUE O LEITOR VE.

    Vale tambem para a guarda numerica, que passa a validar contra esta mesma
    copia: citar um numero de rota deixa de ser permitido e passa a descartar
    a narrativa, que e o comportamento certo.

    NAO MUTA a original. O dicionario recebido e o mesmo que vai para o
    `relatorio_render` depois; esvaziar as listas aqui apagaria dado de quem
    consulta a API.

    >>> m = {"adocao": {"acoes": 10, "rotas_mais_usadas": [1], "erros_por_rota": [2]}}
    >>> metricas_para_narrar(m)["adocao"]
    {'acoes': 10}
    >>> m["adocao"]["rotas_mais_usadas"]
    [1]
    """
    copia = dict(metricas)
    adocao = copia.get("adocao")
    if isinstance(adocao, dict):
        copia["adocao"] = {
            k: v for k, v in adocao.items() if k not in _CAMPOS_OCULTOS
        }
    return copia


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
                + json.dumps(metricas_para_narrar(metricas),
                             ensure_ascii=False, indent=2)
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
            # Valida contra a MESMA copia que o modelo recebeu: numero de
            # rota deixa de ser permitido, e citar um passa a descartar.
            inventados = numeros_invalidos(
                texto, numeros_permitidos(metricas_para_narrar(metricas)))
            if inventados:
                # ERROR, nao WARNING: se isto aparece direto no journal, o
                # relatorio esta saindo sem narrativa todo dia e ninguem viu.
                # O ajuste e na INSTRUCAO, nao na guarda.
                log.error(
                    "ia: narrativa descartada, numeros fora da telemetria (%s)",
                    ", ".join(inventados),
                )
                # A FRASE, e nao so o numero. O cabecalho de
                # validacao_numerica manda ajustar a INSTRUCAO quando isto
                # aparecer com frequencia -- e sem o trecho isso e impossivel:
                # "30" pode ser "30%", "ha 30 dias" ou "temperatura 30", e
                # cada um pede um ajuste diferente (o ultimo seria falso
                # positivo da guarda, nao erro do modelo). A narrativa e
                # descartada; se nao deixar rastro, o defeito fica invisivel
                # justamente quando esta acontecendo.
                for token in inventados[:5]:
                    log.error("ia:   %r em: %s", token, contexto(texto, token))
                return None, None
        return texto, settings.ANTHROPIC_MODEL
    except Exception as e:
        log.warning("ia: chamada falhou (%s: %s)", type(e).__name__, e)
        return None, None
