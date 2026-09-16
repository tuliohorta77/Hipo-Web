"""
HIPO - Reunioes do dia no fechamento: quem recebeu, o que aconteceu.

Funcao pura (sem banco): recebe as linhas ja lidas e o `agora`, devolve o
bloco `reunioes` das metricas.

A REGRA DO DESFECHO NAO E REPETIDA AQUI. Quem decide se a reuniao foi
realizada, cancelada ou no-show e `services.agenda.desfecho_efetivo`, o
mesmo que alimenta a tela da Agenda e o relatorio de produtividade. Uma
segunda regra no e-mail produziria o pior tipo de divergencia: o e-mail
dizendo 3 no-show e a tela dizendo 2, os dois "certos".

DOIS EIXOS DE DATA, como em /crm/agenda/produtividade:
  - reunioes do dia  -> pelo dia em que a reuniao ACONTECEU (tarefas.prazo)
  - agendamentos     -> pelo dia em que o SDR MARCOU (reunioes.criado_em)
"""
from __future__ import annotations

from datetime import datetime

from services import agenda as regras

ROTULO_SITUACAO = {
    "realizada": "Realizada",
    "cancelada": "Cancelada",
    "no_show": "No-show",
    "pendente": "Sem desfecho",
    "agendada": "Agendada",
}

_ORDEM_SITUACAO = ("realizada", "no_show", "cancelada", "pendente", "agendada")


def situacao(linha: dict, agora: datetime) -> str:
    """
    realizada | cancelada | no_show | pendente | agendada.

    `pendente` = ja terminou e ninguem disse o que aconteceu. `agendada` so
    aparece se o fechamento rodar antes de a reuniao terminar (reprocesso no
    mesmo dia); no fluxo do timer, de madrugada, toda reuniao do dia anterior
    ja acabou.
    """
    efetivo = regras.desfecho_efetivo(
        desfecho=linha["desfecho"], concluida_em=linha["concluida_em"],
        cancelada_em=linha["cancelada_em"], inicio=linha["prazo"],
    )
    if efetivo:
        return efetivo
    if regras.pendente_de_desfecho(
        desfecho=linha["desfecho"], concluida_em=linha["concluida_em"],
        cancelada_em=linha["cancelada_em"], inicio=linha["prazo"],
        duracao_min=linha["duracao_min"], agora=agora,
    ):
        return "pendente"
    return "agendada"


def _molde(nome, cargo) -> dict:
    return {"nome": nome, "cargo": cargo, "total": 0, "realizadas": 0,
            "canceladas": 0, "no_show": 0, "pendentes": 0}


_CAMPO = {"realizada": "realizadas", "cancelada": "canceladas",
          "no_show": "no_show", "pendente": "pendentes"}


def montar(linhas: list[dict], agendamentos: list[dict], agora: datetime) -> dict:
    """
    `linhas`: uma por reuniao com prazo no dia -- prazo, duracao_min,
      desfecho, concluida_em, cancelada_em, anfitriao, anfitriao_cargo,
      agendado_por, empresa, tipo_sigla, tipo_nome, modalidade.
    `agendamentos`: ja agrupados -- nome, cargo, qtd.
    """
    itens = []
    por_anfitriao: dict[str, dict] = {}
    totais = _molde(None, None)

    for r in sorted(linhas, key=lambda x: (x["prazo"], x["anfitriao"] or "")):
        sit = situacao(r, agora)
        chave = r["anfitriao"] or "(sem anfitrião)"
        pessoa = por_anfitriao.setdefault(chave, _molde(chave, r["anfitriao_cargo"]))
        for alvo in (pessoa, totais):
            alvo["total"] += 1
            if sit in _CAMPO:
                alvo[_CAMPO[sit]] += 1
        itens.append({
            "hora": regras.no_fuso(r["prazo"]).strftime("%H:%M"),
            "anfitriao": chave,
            "empresa": r["empresa"] or "—",
            "tipo": (f'{r["tipo_sigla"]} · {r["tipo_nome"]}'
                     if r.get("tipo_sigla") else "—"),
            "modalidade": regras.ROTULO_MODALIDADE.get(r.get("modalidade"), "—"),
            "agendado_por": r["agendado_por"] or "—",
            "situacao": sit,
            "situacao_rotulo": ROTULO_SITUACAO[sit],
        })

    fechadas = totais["realizadas"] + totais["canceladas"] + totais["no_show"]
    return {
        "total": totais["total"],
        "realizadas": totais["realizadas"],
        "canceladas": totais["canceladas"],
        "no_show": totais["no_show"],
        "pendentes": totais["pendentes"],
        # Mesmo denominador da tela de produtividade: so o que ja tem
        # desfecho. None, e nao 0, quando nao ha denominador.
        "taxa_realizacao_pct": (round(totais["realizadas"] * 100 / fechadas, 1)
                                if fechadas else None),
        "por_anfitriao": sorted(por_anfitriao.values(),
                                key=lambda p: (-p["total"], p["nome"])),
        "itens": itens,
        "agendamentos_total": sum(int(a["qtd"]) for a in agendamentos),
        "agendamentos_por_pessoa": sorted(
            [{"nome": a["nome"] or "(sem autor)", "cargo": a["cargo"],
              "qtd": int(a["qtd"])} for a in agendamentos],
            key=lambda a: (-a["qtd"], a["nome"]),
        ),
    }
