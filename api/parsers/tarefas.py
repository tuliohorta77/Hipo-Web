"""
HIPO — Parser da planilha de Tarefas

Decisão arquitetural travada:
  - Janela de meta (semana/mês) usa `data_efetiva`:
      data_efetiva = Data Agendamento se existir, senão Data Criação.

  - 'Reunião' (meta semanal do Farmer) é detectada por
      Tarefa Canal == 'Reunião'  (verbatim na planilha)
"""
from __future__ import annotations

import re
import unicodedata
import pandas as pd
from datetime import datetime
from typing import Any


# ── Coerção ──────────────────────────────────────────────────────

def _s(v: Any) -> str | None:
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def _dt(v: Any) -> datetime | None:
    if pd.isna(v):
        return None
    try:
        return pd.to_datetime(v).to_pydatetime()
    except (ValueError, TypeError):
        return None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


# ── Mapeamento de cabeçalhos ─────────────────────────────────────

HEADERS = {
    "tarefa_id":          "tarefa_id_origem",
    "cnpj contador":      "cnpj_contador",
    "contabilidade":      "contabilidade",
    "executivo de contas":"executivo_nome",
    "situacao da tarefa": "situacao_raw",
    "status da tarefa":   "status",
    "tarefa canal":       "tarefa_canal",
    "tipo da tarefa":     "tipo_tarefa",
    "resultado":          "resultado",
    "data criacao":       "data_criacao",
    "data agendamento":   "data_agendamento",
}


def _resolve_colunas(cols: list[str]) -> dict[str, str]:
    res: dict[str, str] = {}
    for c in cols:
        canon = HEADERS.get(_norm(c))
        if canon and canon not in res:
            res[canon] = c

    obrigatorias = ("situacao_raw", "executivo_nome")
    falt = [k for k in obrigatorias if k not in res]
    if falt:
        raise ValueError(
            f"Colunas obrigatórias ausentes na planilha de tarefas: {falt}. "
            f"Encontradas: {list(cols)}"
        )
    return res


def _mapear_situacao(raw: str | None) -> str:
    """
    Mapeia 'Situação da Tarefa' do CRM Omie → enum interno do banco.

    CRM diz:               Enum interno:
      'Tarefa em dia'    →  EM_DIA
      'Tarefa futura'    →  FUTURA
      'Tarefa atrasada'  →  ATRASADA
      qualquer outra     →  DESCONHECIDA
    """
    if not raw:
        return "DESCONHECIDA"
    n = _norm(raw)
    if "atrasada" in n:
        return "ATRASADA"
    if "futura" in n:
        return "FUTURA"
    if "em dia" in n:
        return "EM_DIA"
    return "DESCONHECIDA"


# ── Parser principal ─────────────────────────────────────────────

def parse_tarefas_arquivo(caminho: str) -> dict:
    """
    Lê o XLSX e devolve:
      {
        "linhas": [ {dict_tarefa}, ... ],
        "total_linhas": int,
        "total_validos": int,
        "erros": [str, ...],
      }
    """
    try:
        df = pd.read_excel(caminho, engine="openpyxl")
    except Exception as e:
        return {
            "linhas": [],
            "total_linhas": 0,
            "total_validos": 0,
            "erros": [f"Falha ao ler XLSX: {e}"],
        }

    total_linhas = len(df)

    try:
        colmap = _resolve_colunas(list(df.columns))
    except ValueError as e:
        return {
            "linhas": [],
            "total_linhas": total_linhas,
            "total_validos": 0,
            "erros": [str(e)],
        }

    linhas: list[dict] = []
    erros: list[str] = []

    for _, row in df.iterrows():
        item: dict[str, Any] = {}
        for canon, real in colmap.items():
            v = row.get(real)
            if canon in ("data_criacao", "data_agendamento"):
                item[canon] = _dt(v)
            else:
                item[canon] = _s(v)

        # Mapeia situação para enum
        item["situacao"] = _mapear_situacao(item.pop("situacao_raw", None))

        # Pula linhas totalmente vazias (e.g. rodapés da planilha)
        if not item.get("executivo_nome") and not item.get("cnpj_contador"):
            continue

        # data_efetiva = Data Agendamento ?: Data Criação
        item["data_efetiva"] = item.get("data_agendamento") or item.get("data_criacao")

        linhas.append(item)

    return {
        "linhas": linhas,
        "total_linhas": total_linhas,
        "total_validos": len(linhas),
        "erros": erros,
    }
