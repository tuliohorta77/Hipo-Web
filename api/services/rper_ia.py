"""
HIPO — RPeR: os textos analíticos pela API da Anthropic.

Decisão do Tulio (29/09): os blocos de leitura do RPeR — a leitura do mês
de cada squad, o comentário por pessoa, as ações do mês, o foco das
negociações — saem da IA.

AS MESMAS TRÊS REGRAS DA NARRATIVA DO FECHAMENTO DIÁRIO (services/ia.py)

  1. A IA NÃO CALCULA. Todo número vem pronto no JSON, já formatado como
     sai no slide ("R$ 18.908", "94%"). Percentual que o texto precise
     citar (concentração do pipeline, peso das duas maiores negociações)
     é calculado em services/rper.py e entregue pronto.
  2. A GUARDA NUMÉRICA é a mesma (`validacao_numerica`), estrita de
     propósito. Aqui ela age POR CAMPO, e não no texto inteiro: um número
     inventado no comentário do Bruno troca só aquele comentário pelo texto
     padrão, e o resto do RPeR fica com a IA. No fechamento diário a
     narrativa é um bloco só; aqui são dezenas de caixas independentes.
  3. FALHA É SILENCIOSA. Sem chave, com timeout ou com resposta que não é
     JSON, o RPeR sai inteiro com o texto padrão (`rper.textos_padrao`).
     O PPT da reunião não pode deixar de sair porque o texto de apoio
     falhou.

TAMANHO É GUARDA TAMBÉM. Cada caixa do slide tem espaço fixo. Texto acima
do limite volta para o padrão em vez de ser cortado: frase cortada no meio
é pior do que frase simples inteira.
"""
from __future__ import annotations

import json
import logging

import httpx

from config import settings
from services import ia as ia_base
from services import rper as regras
from services.validacao_numerica import contexto, numeros_invalidos, numeros_permitidos

log = logging.getLogger("hipo.rper")

TIMEOUT_S = 60.0

# Caracteres por caixa. Medidos no slide em Poppins 11pt: acima disso a
# caixa transborda.
LIMITES = {
    "leitura": 330,
    "pessoa": 230,
    "acao": 75,
    "foco": 120,
    "pipeline": 260,
}
MAX_ACOES = 5

INSTRUCAO = """Você escreve os textos de apoio do RPeR (Reunião de Planejamento
e Resultados) do time comercial de uma operação de medicina e segurança
ocupacional. Os números do mês já estão nos slides; o seu texto é a LEITURA
deles, para a reunião de planejamento.

Você recebe um JSON com os três squads (EC, SDR, EV). Para cada squad:
- `total`: indicadores do squad no mês fechado (realizado, meta, atingimento).
- `pessoas`: os mesmos indicadores por pessoa, mais pendências em aberto.
- No EV: `negociacoes` (as maiores negociações abertas) e `pipeline_por_pessoa`.

Responda SOMENTE com um objeto JSON, sem markdown, neste formato:

{
  "EC":  {"leitura": "...", "pessoas": {"<nome exato>": "..."}, "acoes": ["...", "..."]},
  "SDR": {"leitura": "...", "pessoas": {"<nome exato>": "..."}, "acoes": ["..."]},
  "EV":  {"leitura": "...", "pessoas": {"<nome exato>": "..."}, "acoes": ["..."],
          "foco": "...", "pipeline": "..."}
}

O que vai em cada campo:
- leitura: 2 frases sobre o squad no mês. O que se destacou e o que ficou
  abaixo da meta (quando houver meta). Máximo 300 caracteres.
- pessoas: 1 ou 2 frases por pessoa, usando a chave = `nome` exatamente
  como está no JSON. Aponte o ponto forte e o ponto de atenção dela.
  Máximo 220 caracteres cada.
- acoes: de 2 a 5 ações para o mês novo, cada uma com no máximo 70
  caracteres, começando por verbo no infinitivo ("Zerar...", "Priorizar...").
  Cada ação é sobre um ITEM que está no JSON: uma pendência, uma
  negociação, um indicador abaixo da meta.
- foco (só EV): 1 frase sobre as negociações que mais pesam. Use
  `negociacoes.dois_maiores` e `negociacoes.dois_maiores_pct` quando
  existirem. Máximo 110 caracteres.
- pipeline (só EV): 1 ou 2 frases comparando o pipeline entre os
  executivos. Máximo 240 caracteres.

Regras:
- NÃO INVENTE NÚMERO. Todo número do texto tem de estar no JSON, escrito
  como está lá ("R$ 18.908", "94%", "11"). Existe verificação automática:
  campo com número que não está no JSON é descartado.
- NÃO SOME, NÃO SUBTRAIA, NÃO CALCULE PERCENTUAL NEM DIFERENÇA. Se o número
  que você quer citar não vem pronto, descreva sem ele.
- NOMES de pessoas e de empresas só do JSON, copiados exatamente.
- NÃO EXPLIQUE CAUSA. O JSON diz o que aconteceu, não por quê.
- NÃO CRIE META, PRAZO NEM REGRA. "Até sexta", "no mínimo 10 ligações" são
  políticas que ninguém definiu. A meta do mês novo é decidida na reunião.
- Indicador com `posicao: true` é posição no momento da geração, não
  resultado do mês — não diga que ele "cresceu" ou "caiu".
- Sem meta (campo vazio), não fale em "bater" ou "ficar abaixo" da meta.
- Squad sem pessoas: `pessoas` vazio e leitura de uma frase dizendo isso.
- Português do Brasil, tom direto, sem elogio vazio, sem emoji.
"""


def _linhas_para_ia(linhas: list[dict]) -> list[dict]:
    return [
        {
            "indicador": l["rotulo"],
            "realizado": l["realizado_txt"],
            "meta": l["meta_txt"] or None,
            "atingimento": l["atingimento_txt"] or None,
            "posicao": l["posicao"],
        }
        for l in linhas
    ]


def payload_para_ia(rper: dict) -> dict:
    """
    O que o modelo recebe. Só texto já formatado e nenhum id: um UUID no
    JSON liberaria na guarda numérica os dígitos soltos dele.
    """
    saida = {
        "mes_fechado": rper["rotulo_fechado"],
        "mes_novo": rper["rotulo_novo"],
        "squads": {},
    }
    for squad, s in rper["squads"].items():
        item = {
            "total": _linhas_para_ia(s["total"]),
            "pessoas": [
                {
                    "nome": p["nome"],
                    "indicadores": _linhas_para_ia(p["indicadores"]),
                    "tarefas_atrasadas_em_aberto":
                        s["pendencias"][str(p["id"])]["tarefas_atrasadas"],
                    "reunioes_sem_desfecho":
                        s["pendencias"][str(p["id"])]["reunioes_sem_desfecho"],
                    **({"maior_oportunidade_pct_do_pipeline": p["concentracao_pct"]}
                       if p.get("concentracao_pct") is not None else {}),
                }
                for p in s["pessoas"]
            ],
        }
        if squad == "EV":
            neg = s["negociacoes"]
            item["negociacoes"] = {
                "abertas": neg["abertas"],
                "soma_das_maiores": regras.formatar(neg["soma_top"], "moeda"),
                "dois_maiores": neg["dois_maiores"],
                "dois_maiores_pct": neg["dois_maiores_pct"],
                "maiores": [
                    {
                        "empresa": o["empresa"],
                        "executivo": o["executivo"],
                        "ticket_mensal": regras.formatar(o["valor"], "moeda"),
                    }
                    for o in neg["top"]
                ],
            }
            item["pipeline_por_pessoa"] = [
                {"nome": p["nome"],
                 "pipeline": regras.formatar(p["bruto"]["pipeline"], "moeda")}
                for p in s["pessoas"]
            ]
        saida["squads"][squad] = item
    return saida


def _json_da_resposta(texto: str) -> dict | None:
    """Tolera o modelo embrulhar o JSON em ```; qualquer outra coisa é None."""
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    ini, fim = t.find("{"), t.rfind("}")
    if ini < 0 or fim <= ini:
        return None
    try:
        dado = json.loads(t[ini:fim + 1])
    except ValueError:
        return None
    return dado if isinstance(dado, dict) else None


def _aceitar(texto_ia, limite: int, permitidos: set[str], onde: str) -> str | None:
    """O texto da IA se ele passar nas guardas; None para cair no padrão."""
    if not isinstance(texto_ia, str):
        return None
    t = " ".join(texto_ia.split())
    if not t:
        return None
    if len(t) > limite:
        log.warning("rper: %s descartado, %d caracteres (limite %d)", onde, len(t), limite)
        return None
    inventados = numeros_invalidos(t, permitidos)
    if inventados:
        log.error("rper: %s descartado, números fora dos dados (%s)",
                  onde, ", ".join(inventados))
        for token in inventados[:3]:
            log.error("rper:   %r em: %s", token, contexto(t, token))
        return None
    return t


def mesclar(rper: dict, padrao: dict, resposta: dict | None) -> tuple[dict, dict]:
    """
    Parte do texto padrão e troca, campo a campo, pelo que a IA escreveu
    e passou nas guardas. Devolve (textos, estatística).

    Função pura: é testável sem rede, com a `resposta` escrita à mão.
    """
    textos = json.loads(json.dumps(padrao))  # cópia profunda de str/list/dict
    stats = {"ia": resposta is not None, "aceitos": 0, "descartados": 0}
    if not resposta:
        return textos, stats
    permitidos = numeros_permitidos(payload_para_ia(rper))

    def usar(valor, limite, onde):
        # Campo que a IA não mandou não é descarte: fica o padrão, e o
        # contador que vai para a tela só mede texto recusado pelas guardas.
        if valor is None:
            return None
        aceito = _aceitar(valor, limite, permitidos, onde)
        stats["aceitos" if aceito else "descartados"] += 1
        return aceito

    for squad, s in rper["squads"].items():
        r = resposta.get(squad)
        if not isinstance(r, dict):
            continue
        alvo = textos[squad]
        if (t := usar(r.get("leitura"), LIMITES["leitura"], f"{squad}.leitura")):
            alvo["leitura"] = t
        pessoas_ia = r.get("pessoas") if isinstance(r.get("pessoas"), dict) else {}
        for p in s["pessoas"]:
            if p["nome"] not in pessoas_ia:
                continue
            if (t := usar(pessoas_ia[p["nome"]], LIMITES["pessoa"],
                          f"{squad}.pessoas.{p['nome']}")):
                alvo["pessoas"][str(p["id"])] = t
        acoes_ia = r.get("acoes")
        if isinstance(acoes_ia, list) and acoes_ia:
            aceitas = [
                t for i, a in enumerate(acoes_ia[:MAX_ACOES])
                if (t := usar(a, LIMITES["acao"], f"{squad}.acoes[{i}]"))
            ]
            # Lista de ações é um conjunto: se metade caiu, a outra metade
            # sozinha pode ler como se o mês só tivesse aquilo a fazer.
            # Só troca se sobrou pelo menos duas.
            if len(aceitas) >= 2:
                alvo["acoes"] = aceitas
        if squad == "EV":
            for campo in ("foco", "pipeline"):
                if (t := usar(r.get(campo), LIMITES[campo], f"EV.{campo}")):
                    alvo[campo] = t
    return textos, stats


async def escrever(rper: dict, padrao: dict) -> tuple[dict, dict]:
    """
    Os textos do RPeR: IA onde ela passou nas guardas, padrão no resto.
    Nunca levanta exceção.
    """
    if not ia_base.configurada():
        log.info("rper: ANTHROPIC_API_KEY não configurada, textos padrão")
        return mesclar(rper, padrao, None)

    corpo = {
        "model": settings.ANTHROPIC_MODEL,
        "max_tokens": 3000,
        "system": INSTRUCAO,
        "messages": [{
            "role": "user",
            "content": "Dados do RPeR (JSON):\n\n" + json.dumps(
                payload_para_ia(rper), ensure_ascii=False, indent=2,
            ),
        }],
    }
    cabecalhos = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": ia_base.VERSAO_API,
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
            resp = await cliente.post(ia_base.URL_API, headers=cabecalhos, json=corpo)
        if resp.status_code != 200:
            log.warning("rper: IA HTTP %s — %s", resp.status_code, resp.text[:300])
            return mesclar(rper, padrao, None)
        texto = ia_base._texto_da_resposta(resp.json())
        dado = _json_da_resposta(texto or "")
        if dado is None:
            log.error("rper: resposta da IA não é JSON: %s", (texto or "")[:200])
        return mesclar(rper, padrao, dado)
    except Exception as e:  # noqa: BLE001 -- o PPT sai de qualquer jeito
        log.warning("rper: chamada à IA falhou (%s: %s)", type(e).__name__, e)
        return mesclar(rper, padrao, None)
