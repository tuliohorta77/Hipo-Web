"""
HIPO — Serviço de Relacionamento (Hunter → Farmer via Bastão)

Quando um Hunter passa um contador para um Farmer via Bastão (v1.2.0),
ele mantém visibilidade do desempenho do Farmer naquele contador. Essa
é a "sub-aba Relacionamento" do Hunter.

Este módulo concentra o CRUZAMENTO bastão ↔ grupo Farmer — lógica que
antes vivia no frontend (BastaoLista.jsx) e que a v1.3.0 traz para o
backend, para que o endpoint /dashboard/farmer possa ser filtrado por
usuário sem quebrar o Relacionamento.

Regras (espelham o que o BastaoLista.jsx fazia):
  - Só bastões com status 'APROVADO' contam.
  - Um grupo Farmer "casa" com o Relacionamento do Hunter se PELO MENOS
    UM dos CNPJs do grupo veio de um bastão aprovado desse Hunter.
  - CNPJs são comparados por dígitos apenas (blinda contra máscara).
  - Bastões aprovados cujo CNPJ não aparece em nenhum grupo Farmer
    entram numa lista de aviso (não somem silenciosamente) — são
    contadores ainda não atribuídos na carteira / CROmie desatualizado.
"""
from __future__ import annotations

import re
from typing import Any


def _so_digitos(cnpj: str | None) -> str:
    """Reduz o CNPJ a dígitos — imune a máscara, espaço, etc."""
    return re.sub(r"\D", "", cnpj or "")


def cruzar_bastoes_com_grupos(
    bastoes: list[dict],
    grupos_farmer: list[dict],
) -> dict[str, Any]:
    """
    Cruza os bastões de um Hunter com os grupos Farmer agregados.

    Args:
      bastoes: saída de services.bastao.listar_bastoes_do_hunter() —
               todos os status; aqui só os 'APROVADO' contam.
      grupos_farmer: grupos com funcao == 'EC_FARMER' vindos de
               services.carteira_agg.agregar_grupos(). Cada grupo já
               traz 'cnpjs' (lista de CNPJs do grupo), 'timeline',
               'tarefas_atrasadas', 'tarefas_futuras', 'leads_no_mes'.

    Returns:
      dict com:
        - grupos: list[dict] — os grupos Farmer que casaram, cada um
          com a chave extra '_farmer_nome' (colaborador responsável).
        - bastoes_sem_grupo: list[dict] — bastões aprovados cujo CNPJ
          não apareceu em nenhum grupo Farmer.
        - kpis: dict — total_grupos, com_atrasada, com_futura, leads.
    """
    # Set de CNPJs (dígitos) com bastão APROVADO.
    cnpjs_aprovados: set[str] = set()
    for b in bastoes:
        if b.get("status") == "APROVADO":
            d = _so_digitos(b.get("cnpj_contador"))
            if d:
                cnpjs_aprovados.add(d)

    grupos_casados: list[dict] = []
    cnpjs_com_grupo: set[str] = set()

    if cnpjs_aprovados:
        vistos: set[str] = set()
        for g in grupos_farmer:
            gid = g.get("id_grupo")
            if gid in vistos:
                continue
            cnpjs_do_grupo = [_so_digitos(c) for c in (g.get("cnpjs") or [])]
            casa = any(c in cnpjs_aprovados for c in cnpjs_do_grupo)
            if casa:
                vistos.add(gid)
                grupo_out = dict(g)
                grupo_out["_farmer_nome"] = g.get("colaborador_nome")
                grupos_casados.append(grupo_out)
                for c in cnpjs_do_grupo:
                    if c:
                        cnpjs_com_grupo.add(c)

    # Bastões aprovados cujo CNPJ não casou com grupo nenhum.
    bastoes_sem_grupo: list[dict] = [
        b for b in bastoes
        if b.get("status") == "APROVADO"
        and _so_digitos(b.get("cnpj_contador")) not in cnpjs_com_grupo
    ]

    kpis = {
        "total_grupos": len(grupos_casados),
        "com_atrasada": sum(
            1 for g in grupos_casados if (g.get("tarefas_atrasadas") or 0) > 0
        ),
        "com_futura": sum(
            1 for g in grupos_casados if (g.get("tarefas_futuras") or 0) > 0
        ),
        "leads": sum(int(g.get("leads_no_mes") or 0) for g in grupos_casados),
    }

    # Ordena os grupos: meta_atingida=False primeiro, leads desc.
    grupos_casados.sort(
        key=lambda g: (g.get("meta_atingida", False), -int(g.get("leads_no_mes") or 0))
    )

    return {
        "grupos": grupos_casados,
        "bastoes_sem_grupo": bastoes_sem_grupo,
        "kpis": kpis,
    }
