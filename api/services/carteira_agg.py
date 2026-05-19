"""
HIPO — Serviço de agregação da Carteira

Responsável por transformar os snapshots de:
  - carteira_cnpj
  - carteira_tarefa
  - carteira_colaborador

em um modelo agregado por GRUPO DE EMPRESAS, que é a unidade de
trabalho real do EC Hunter/Farmer.

Regras (travadas com o franqueado):
  - Aba 'HUNTER':  grupos cujo colaborador majoritário é EC_HUNTER.
                   Meta: ≥1 tarefa por MÊS (data_efetiva no mês corrente).
  - Aba 'FARMER':  grupos cujo colaborador majoritário é EC_FARMER.
                   Meta: ≥1 tarefa com `tarefa_canal = 'Reunião'`
                   POR SEMANA do mês corrente (semanas ISO).
  - Aba 'OUTROS':  todos os outros — usado para detectar bagunça
                   (grupos cujo colaborador não foi mapeado como Hunter
                   ou Farmer).

  - 'data_efetiva' já vem pronta do parser de tarefas
    (data_agendamento ?: data_criacao).
  - 'Reunião' é estritamente Tarefa Canal == 'Reunião' (case-insensitive).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Iterable


# ── Helpers de tempo ─────────────────────────────────────────────

def _ref_mes(d: date | None = None) -> tuple[date, date]:
    """Devolve (primeiro_dia_mes, primeiro_dia_mes_seguinte)."""
    if d is None:
        d = date.today()
    inicio = d.replace(day=1)
    if inicio.month == 12:
        fim = inicio.replace(year=inicio.year + 1, month=1)
    else:
        fim = inicio.replace(month=inicio.month + 1)
    return inicio, fim


def _semanas_iso_do_mes(inicio: date, fim: date) -> list[tuple[int, int]]:
    """
    Devolve as semanas ISO (ano, semana) tocadas por [inicio, fim).
    Usamos ISO porque é o padrão de calendário comercial brasileiro.
    """
    semanas: list[tuple[int, int]] = []
    cursor = inicio
    while cursor < fim:
        iso = cursor.isocalendar()
        chave = (iso.year, iso.week)
        if chave not in semanas:
            semanas.append(chave)
        cursor += timedelta(days=1)
    return semanas


def _semana_iso_de(dt: datetime | date) -> tuple[int, int]:
    if isinstance(dt, datetime):
        dt = dt.date()
    iso = dt.isocalendar()
    return (iso.year, iso.week)


# ── Modelo de saída ──────────────────────────────────────────────
#
# Cada grupo agregado é um dict com:
#   id_grupo: str
#   nome_grupo: str
#   qtd_cnpj: int
#   parceria: 'Parceiro' | 'Não Parceiro' | None (majoritária)
#   contabilidade_principal: str
#   cidade_uf: str
#   colaborador_nome: str (majoritário entre os CNPJs do grupo)
#   colaboradores_multiplos: bool
#   funcao: 'EC_HUNTER' | 'EC_FARMER' | 'OUTROS'
#   leads_no_mes: int (SOMA dos leads_no_mes dos CNPJs do grupo)
#   tarefas_mes_total: int (tarefas com data_efetiva no mês corrente)
#   tarefas_atrasadas: int
#   tarefas_futuras: int
#   reunioes_mes: int (tarefa_canal = 'Reunião' no mês corrente)
#   timeline: list[ {key, label, status, count} ]
#       - Para HUNTER: 1 célula = o mês (status verde/vermelho).
#       - Para FARMER: 1 célula por semana ISO do mês (cada semana
#         precisa de ≥1 reunião).
#       - Para OUTROS: timeline do mês (status verde se teve QUALQUER
#         tarefa, vermelho se zero — para diagnóstico).
#   meta_atingida: bool
#   score: int | None  (placeholder — calculado em v2)


def _maior_freq(it: Iterable[Any]) -> Any | None:
    vals = [v for v in it if v is not None]
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]


def _is_reuniao(canal: str | None) -> bool:
    if not canal:
        return False
    return canal.strip().lower() == "reuniao" or canal.strip().lower() == "reunião"


def agregar_grupos(
    cnpjs: list[dict],
    tarefas: list[dict],
    colaboradores: list[dict],
    ref_date: date | None = None,
) -> list[dict]:
    """
    Roda toda a agregação a partir das 3 listas em memória.

    Args:
      cnpjs: linhas de carteira_cnpj (já filtradas CNAE Contábil).
      tarefas: linhas de carteira_tarefa.
      colaboradores: linhas de carteira_colaborador com 'nome' e 'funcao'.
      ref_date: data de referência para o "mês corrente" (default = hoje).
    """
    inicio_mes, fim_mes = _ref_mes(ref_date)
    semanas_mes = _semanas_iso_do_mes(inicio_mes, fim_mes)

    # mapa colaborador → função
    fn_por_nome = {c["nome"]: c["funcao"] for c in colaboradores}

    # tarefas por CNPJ (chave normalizada)
    tarefas_por_cnpj: dict[str, list[dict]] = {}
    for t in tarefas:
        k = (t.get("cnpj_contador") or "").strip()
        if not k:
            continue
        tarefas_por_cnpj.setdefault(k, []).append(t)

    # agrupa CNPJs por id_grupo
    grupos: dict[str, list[dict]] = {}
    for c in cnpjs:
        gid = c.get("id_grupo")
        if not gid:
            continue
        grupos.setdefault(gid, []).append(c)

    saida: list[dict] = []
    for gid, lista in grupos.items():
        nomes_colab = [l.get("colaborador_nome") for l in lista if l.get("colaborador_nome")]
        colab_majoritario = _maior_freq(nomes_colab)
        colab_multiplos = len({n for n in nomes_colab if n}) > 1

        funcao = fn_por_nome.get(colab_majoritario, "OUTROS") if colab_majoritario else "OUTROS"

        # Coleta as tarefas de todos os CNPJs do grupo
        cnpj_keys = [(l.get("cnpj_contador") or "").strip() for l in lista]
        tarefas_grupo: list[dict] = []
        for k in cnpj_keys:
            if k:
                tarefas_grupo.extend(tarefas_por_cnpj.get(k, []))

        # Tarefas no mês corrente
        def _no_mes(t: dict) -> bool:
            ef = t.get("data_efetiva")
            if not ef:
                return False
            d = ef.date() if isinstance(ef, datetime) else ef
            return inicio_mes <= d < fim_mes

        tarefas_mes = [t for t in tarefas_grupo if _no_mes(t)]
        reunioes_mes = [t for t in tarefas_mes if _is_reuniao(t.get("tarefa_canal"))]

        # Atrasadas e futuras (do snapshot inteiro — independente do mês)
        atrasadas = sum(1 for t in tarefas_grupo if t.get("situacao") == "ATRASADA")
        futuras   = sum(1 for t in tarefas_grupo if t.get("situacao") == "FUTURA")

        # Timeline + meta_atingida por função
        if funcao == "EC_FARMER":
            # 1 célula por semana ISO; precisa de ≥1 reunião na semana
            sem_count: Counter = Counter()
            for t in reunioes_mes:
                sem_count[_semana_iso_de(t["data_efetiva"])] += 1
            timeline = []
            for idx, (ano, sem) in enumerate(semanas_mes, start=1):
                count = sem_count.get((ano, sem), 0)
                # 'futura' se a semana ainda não começou (todas têm reuniões com
                # data >= hoje) — simplificação: se count==0 e a semana inteira
                # está no passado, é vermelho; senão, é azul.
                status = _status_semana(count, ano, sem, ref_date)
                timeline.append({
                    "key": f"{ano}-W{sem:02d}",
                    "label": f"S{idx}",
                    "status": status,
                    "count": count,
                })
            meta = all(c["status"] == "ok" for c in timeline if c["status"] != "future")

        elif funcao == "EC_HUNTER":
            count = len(tarefas_mes)
            status = "ok" if count >= 1 else "miss"
            timeline = [{
                "key": inicio_mes.strftime("%Y-%m"),
                "label": inicio_mes.strftime("%b/%y").capitalize(),
                "status": status,
                "count": count,
            }]
            meta = count >= 1

        else:  # OUTROS
            count = len(tarefas_mes)
            status = "ok" if count >= 1 else "miss"
            timeline = [{
                "key": inicio_mes.strftime("%Y-%m"),
                "label": inicio_mes.strftime("%b/%y").capitalize(),
                "status": status,
                "count": count,
            }]
            meta = False  # OUTROS nunca está "ok" — é uma fila de correção

        # Agregados de carteira
        nome_grupo  = _maior_freq(l.get("nome_grupo") for l in lista) or "—"
        parceria    = _maior_freq(l.get("parceria") for l in lista)
        contab_p    = _maior_freq(l.get("contabilidade") for l in lista) or ""
        cidade_uf   = _maior_freq(l.get("cidade_uf") for l in lista) or ""
        leads_mes   = sum(int(l.get("leads_no_mes") or 0) for l in lista)

        saida.append({
            "id_grupo": gid,
            "nome_grupo": nome_grupo,
            "qtd_cnpj": len(lista),
            "parceria": parceria,
            "contabilidade_principal": contab_p,
            "cidade_uf": cidade_uf,
            "colaborador_nome": colab_majoritario,
            "colaboradores_multiplos": colab_multiplos,
            "funcao": funcao,
            "leads_no_mes": leads_mes,
            "tarefas_mes_total": len(tarefas_mes),
            "tarefas_atrasadas": atrasadas,
            "tarefas_futuras": futuras,
            "reunioes_mes": len(reunioes_mes),
            "timeline": timeline,
            "meta_atingida": meta,
            "score": None,  # v2
        })

    return saida


def _status_semana(count: int, ano: int, sem: int, ref_date: date | None) -> str:
    """
    Devolve status de uma célula semanal:
      'ok'     → teve ≥1 reunião nessa semana
      'miss'   → semana já passou e teve 0 reuniões
      'future' → semana ainda não começou (não conta para a meta)
      'now'    → semana corrente sem reuniões ainda (amarelo no front)
    """
    if count >= 1:
        return "ok"

    hoje = ref_date or date.today()
    iso_hoje = hoje.isocalendar()
    if (iso_hoje.year, iso_hoje.week) == (ano, sem):
        return "now"
    if (ano, sem) > (iso_hoje.year, iso_hoje.week):
        return "future"
    return "miss"


# ── Filtros usados pelo router ───────────────────────────────────

def aplicar_filtros(
    grupos: list[dict],
    funcao: str | None = None,
    tarefa_atrasada: bool = False,
    sem_tarefa_futura: bool = False,
    busca: str | None = None,
) -> list[dict]:
    out = grupos
    if funcao:
        out = [g for g in out if g["funcao"] == funcao]
    if tarefa_atrasada:
        out = [g for g in out if g["tarefas_atrasadas"] > 0]
    if sem_tarefa_futura:
        out = [g for g in out if g["tarefas_futuras"] == 0]
    if busca:
        n = busca.strip().lower()
        out = [
            g for g in out
            if n in (g.get("nome_grupo") or "").lower()
            or n in (g.get("contabilidade_principal") or "").lower()
            or n in (g.get("colaborador_nome") or "").lower()
        ]
    return out


# ── KPIs do topo (cards) ─────────────────────────────────────────

def kpis_por_funcao(grupos: list[dict], funcao: str) -> dict:
    sub = [g for g in grupos if g["funcao"] == funcao]
    total = len(sub)
    metas_ok = sum(1 for g in sub if g["meta_atingida"])
    atrasadas = sum(1 for g in sub if g["tarefas_atrasadas"] > 0)
    sem_futura = sum(1 for g in sub if g["tarefas_futuras"] == 0)
    leads = sum(g["leads_no_mes"] for g in sub)
    return {
        "total_grupos": total,
        "meta_atingida": metas_ok,
        "compliance_pct": round((metas_ok / total) * 100, 1) if total else 0.0,
        "com_tarefa_atrasada": atrasadas,
        "sem_tarefa_futura": sem_futura,
        "leads_no_mes": leads,
    }
