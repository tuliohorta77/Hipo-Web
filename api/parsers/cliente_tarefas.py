"""
HIPO -- Parser da planilha de Tarefas de Clientes (módulo Clientes).

Lê o XLSX exportado do CRM Omie e devolve as linhas preparadas pra
inserir em cliente_tarefa. Importa TUDO (sem filtro).

Cabeçalhos esperados (18 colunas):
  Contagem, Tarefa ID, OP ID, CNPJ, Razão Social, Data Criação,
  Data Atualização, Data Agendamento, Fase Lead, Status, Finalidade,
  Resultado, Origem Lead, Usuário Atribuído, Usuário Criador, Canal,
  Situação Tarefa, Unidade
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

import pandas as pd


def _s(v: Any) -> str | None:
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def _bi(v: Any) -> int | None:
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        try:
            return int(v)
        except (ValueError, OverflowError):
            return None
    m = re.search(r"-?\d+", str(v))
    return int(m.group()) if m else None


def _dt(v: Any) -> datetime | None:
    if pd.isna(v):
        return None
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None
        if hasattr(ts, "to_pydatetime"):
            return ts.to_pydatetime()
        return ts
    except (ValueError, TypeError):
        return None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


HEADERS = {
    "contagem":          None,
    "tarefa id":         "tarefa_id",
    "op id":             "op_id",
    "cnpj":              "cnpj",
    "razao social":      "razao_social",
    "data criacao":      "data_criacao",
    "data atualizacao":  "data_atualizacao",
    "data agendamento":  "data_agendamento",
    "fase lead":         "fase_lead",
    "status":            "status",
    "finalidade":        "finalidade",
    "resultado":         "resultado",
    "origem lead":       "origem_lead",
    "usuario atribuido": "usuario_atribuido",
    "usuario criador":   "usuario_criador",
    "canal":             "canal",
    "situacao tarefa":   "situacao_tarefa",
    "unidade":           "unidade",
}


CONVERTERS = {
    "tarefa_id":         _bi,
    "op_id":             _bi,
    "cnpj":              _s,
    "razao_social":      _s,
    "data_criacao":      _dt,
    "data_atualizacao":  _dt,
    "data_agendamento":  _dt,
    "fase_lead":         _s,
    "status":            _s,
    "finalidade":        _s,
    "resultado":         _s,
    "origem_lead":       _s,
    "usuario_atribuido": _s,
    "usuario_criador":   _s,
    "canal":             _s,
    "situacao_tarefa":   _s,
    "unidade":           _s,
}


def _resolve_colunas(cols: list[str]) -> dict[str, str]:
    res: dict[str, str] = {}
    for c in cols:
        canon = HEADERS.get(_norm(c))
        if canon and canon not in res:
            res[canon] = c
    return res


def parse_tarefas_clientes_arquivo(caminho: str) -> dict:
    erros: list[str] = []
    try:
        df = pd.read_excel(caminho, engine="openpyxl")
    except Exception as e:
        return {
            "linhas": [], "total_linhas": 0, "total_validos": 0,
            "erros": [f"Falha ao ler XLSX: {e}"],
        }

    total_linhas = len(df)
    colmap = _resolve_colunas(list(df.columns))

    if "tarefa_id" not in colmap:
        return {
            "linhas": [], "total_linhas": total_linhas, "total_validos": 0,
            "erros": ["Coluna 'Tarefa ID' não encontrada na planilha."],
        }

    linhas: list[dict] = []
    for idx, row in df.iterrows():
        item: dict[str, Any] = {}
        for canon, real in colmap.items():
            conv = CONVERTERS.get(canon, _s)
            try:
                item[canon] = conv(row.get(real))
            except Exception as e:
                erros.append(f"Linha {idx+2}, coluna '{real}': {e}")
                item[canon] = None

        if item.get("tarefa_id") is None:
            continue

        linhas.append(item)

    return {
        "linhas": linhas,
        "total_linhas": total_linhas,
        "total_validos": len(linhas),
        "erros": erros,
    }
