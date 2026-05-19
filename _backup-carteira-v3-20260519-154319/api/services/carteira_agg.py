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


# ─────────────────────────────────────────────────────────────────
#  DASHBOARD por colaborador (Hunter / Farmer)
# ─────────────────────────────────────────────────────────────────
#
# Diferente do agregador por grupo (que tem 533 linhas), o dashboard
# colapsa tudo em UMA linha por colaborador. Estrutura pensada pro
# layout novo da tela Carteira (uma linha por colaborador, drilldown
# expande a lista de grupos/contadores dele).


def dashboard_hunter(
    grupos: list[dict],
    colaboradores: list[dict],
) -> list[dict]:
    """
    Sumariza por colaborador EC_HUNTER. Uma linha por colaborador.

    Retorna ordenado por compliance descendente (quem está em dia primeiro).

    Args:
      grupos: saída de agregar_grupos() — já tem 'funcao' e 'meta_atingida'.
      colaboradores: linhas de carteira_colaborador (precisa do 'id' UUID).

    Returns:
      Lista de dicts:
        - colaborador_id: str (UUID em texto)
        - nome: str
        - total_grupos: int
        - meta_atingida: int (quantos grupos atingiram a meta do mês)
        - tarefas_atrasadas: int (soma das atrasadas de todos os grupos)
        - sem_tarefa_futura: int (qtd de grupos sem tarefa futura)
        - leads_no_mes: int (soma)
        - compliance_pct: float (meta_atingida / total_grupos * 100)
    """
    # Mapa nome → id, só pra Hunter
    id_por_nome = {
        c["nome"]: str(c["id"])
        for c in colaboradores
        if c.get("funcao") == "EC_HUNTER"
    }

    # Agrupa grupos Hunter por nome do colaborador
    por_colab: dict[str, list[dict]] = {}
    for g in grupos:
        if g["funcao"] != "EC_HUNTER":
            continue
        nome = g.get("colaborador_nome")
        if not nome:
            continue
        por_colab.setdefault(nome, []).append(g)

    saida: list[dict] = []
    for nome, gs in por_colab.items():
        total = len(gs)
        metas_ok = sum(1 for g in gs if g["meta_atingida"])
        atrasadas = sum(g["tarefas_atrasadas"] for g in gs)
        sem_futura = sum(1 for g in gs if g["tarefas_futuras"] == 0)
        leads = sum(g["leads_no_mes"] for g in gs)
        saida.append({
            "colaborador_id": id_por_nome.get(nome),
            "nome": nome,
            "total_grupos": total,
            "meta_atingida": metas_ok,
            "tarefas_atrasadas": atrasadas,
            "sem_tarefa_futura": sem_futura,
            "leads_no_mes": leads,
            "compliance_pct": round((metas_ok / total) * 100, 1) if total else 0.0,
        })

    # Ordena por compliance desc; empate por total_grupos desc
    saida.sort(key=lambda x: (-x["compliance_pct"], -x["total_grupos"]))
    return saida


def dashboard_farmer(
    cnpjs: list[dict],
    tarefas: list[dict],
    colaboradores: list[dict],
    ref_date: date | None = None,
) -> list[dict]:
    """
    Sumariza por colaborador EC_FARMER. Uma linha por colaborador, com
    coluna de bolinhas por semana (com_reuniao / sem_reuniao / pendente)
    indicando quantos CNPJs caem em cada bucket por semana ISO do mês.

    Importante: a unidade contada por semana é o CNPJ_CONTADOR (o "contador"
    individual), não o grupo. Cada CNPJ que tem pelo menos 1 reunião na
    semana entra em 'com_reuniao'; os demais entram em 'sem_reuniao' (se
    a semana já passou) ou 'pendente' (semana corrente).

    Args:
      cnpjs: linhas de carteira_cnpj.
      tarefas: linhas de carteira_tarefa.
      colaboradores: linhas de carteira_colaborador.
      ref_date: data de referência (default = hoje).

    Returns:
      Lista de dicts:
        - colaborador_id, nome
        - total_contadores: int
        - semanas: list de {key, label, com_reuniao, sem_reuniao, pendente}
        - tarefas_atrasadas, tarefas_futuras, leads_no_mes
    """
    if ref_date is None:
        ref_date = date.today()

    inicio_mes, fim_mes = _ref_mes(ref_date)
    semanas_mes = _semanas_iso_do_mes(inicio_mes, fim_mes)
    iso_hoje = ref_date.isocalendar()

    # Mapa nome → função e id
    fn_por_nome = {c["nome"]: c["funcao"] for c in colaboradores}
    id_por_nome = {c["nome"]: str(c["id"]) for c in colaboradores}

    # CNPJs por colaborador Farmer; mantemos a lista de CNPJs por colab
    cnpjs_por_colab: dict[str, list[str]] = {}
    leads_por_colab: dict[str, int] = {}
    for c in cnpjs:
        nome = c.get("colaborador_nome")
        if not nome:
            continue
        if fn_por_nome.get(nome) != "EC_FARMER":
            continue
        cnpj_key = (c.get("cnpj_contador") or "").strip()
        if not cnpj_key:
            continue
        cnpjs_por_colab.setdefault(nome, []).append(cnpj_key)
        leads_por_colab[nome] = leads_por_colab.get(nome, 0) + int(c.get("leads_no_mes") or 0)

    # Tarefas no mês por CNPJ, separadas em reuniões por semana ISO
    # Estrutura: reunioes[cnpj][(ano, semana)] = count
    reunioes_por_cnpj_sem: dict[str, dict[tuple[int, int], int]] = {}

    # Atrasadas/futuras por CNPJ (snapshot todo)
    atrasadas_por_cnpj: dict[str, int] = {}
    futuras_por_cnpj: dict[str, int] = {}

    for t in tarefas:
        cnpj_key = (t.get("cnpj_contador") or "").strip()
        if not cnpj_key:
            continue

        if t.get("situacao") == "ATRASADA":
            atrasadas_por_cnpj[cnpj_key] = atrasadas_por_cnpj.get(cnpj_key, 0) + 1
        if t.get("situacao") == "FUTURA":
            futuras_por_cnpj[cnpj_key] = futuras_por_cnpj.get(cnpj_key, 0) + 1

        ef = t.get("data_efetiva")
        if not ef:
            continue
        d = ef.date() if isinstance(ef, datetime) else ef
        if not (inicio_mes <= d < fim_mes):
            continue
        if not _is_reuniao(t.get("tarefa_canal")):
            continue

        chave_sem = _semana_iso_de(d)
        d_cnpj = reunioes_por_cnpj_sem.setdefault(cnpj_key, {})
        d_cnpj[chave_sem] = d_cnpj.get(chave_sem, 0) + 1

    saida: list[dict] = []
    for nome, cnpj_lista in cnpjs_por_colab.items():
        # Deduplicar mantendo ordem (um colaborador pode aparecer 2x num
        # mesmo CNPJ se ele cobre vários grupos com o mesmo CNPJ)
        seen: set[str] = set()
        cnpjs_unicos: list[str] = []
        for c in cnpj_lista:
            if c not in seen:
                seen.add(c)
                cnpjs_unicos.append(c)

        total_contadores = len(cnpjs_unicos)

        semanas_saida = []
        for idx, (ano, sem) in enumerate(semanas_mes, start=1):
            com_reuniao = 0
            for cnpj in cnpjs_unicos:
                cnt = reunioes_por_cnpj_sem.get(cnpj, {}).get((ano, sem), 0)
                if cnt >= 1:
                    com_reuniao += 1
            falta = total_contadores - com_reuniao

            eh_corrente = (iso_hoje.year, iso_hoje.week) == (ano, sem)
            eh_futura = (ano, sem) > (iso_hoje.year, iso_hoje.week)

            if eh_corrente:
                pendente = falta
                sem_reuniao = 0
            elif eh_futura:
                # Semana ainda nem começou — não conta como falha
                pendente = falta
                sem_reuniao = 0
            else:
                # Semana já passou
                pendente = 0
                sem_reuniao = falta

            semanas_saida.append({
                "key": f"{ano}-W{sem:02d}",
                "label": f"S{idx}",
                "com_reuniao": com_reuniao,
                "sem_reuniao": sem_reuniao,
                "pendente": pendente,
            })

        atrasadas = sum(atrasadas_por_cnpj.get(c, 0) for c in cnpjs_unicos)
        futuras = sum(futuras_por_cnpj.get(c, 0) for c in cnpjs_unicos)
        leads = leads_por_colab.get(nome, 0)

        saida.append({
            "colaborador_id": id_por_nome.get(nome),
            "nome": nome,
            "total_contadores": total_contadores,
            "semanas": semanas_saida,
            "tarefas_atrasadas": atrasadas,
            "tarefas_futuras": futuras,
            "leads_no_mes": leads,
        })

    # Ordena por compliance semanal das semanas passadas (quem reuniu
    # mais semanas com 100% vem primeiro); empate por total_contadores desc.
    def _score_compliance(item: dict) -> tuple:
        passadas = [s for s in item["semanas"] if s["sem_reuniao"] > 0 or (s["com_reuniao"] > 0 and s["pendente"] == 0)]
        if not passadas:
            return (0.0, -item["total_contadores"])
        total_ok = sum(1 for s in passadas if s["sem_reuniao"] == 0)
        return (-total_ok / len(passadas), -item["total_contadores"])

    saida.sort(key=_score_compliance)
    return saida


def grupos_do_colaborador(
    grupos: list[dict],
    nome_colaborador: str,
) -> list[dict]:
    """
    Drilldown: retorna os grupos atribuídos a um colaborador específico.

    Mantém o mesmo formato de saída de `agregar_grupos`, só filtra por
    colaborador_nome. Útil para o drilldown na UI: clicou no colaborador
    → carrega a lista dele.
    """
    return [g for g in grupos if g.get("colaborador_nome") == nome_colaborador]
