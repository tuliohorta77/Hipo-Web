"""
HIPO - Parser da planilha Carteira

Filtra CNPJs com Tipo Cnae = 'CNAE Contábil' e devolve as linhas
preparadas para inserção em carteira_cnpj. A agregação por
ID Grupo de Empresas é responsabilidade da camada de serviço
(services/carteira_agg.py) — o parser entrega CNPJ por CNPJ.
"""
from __future__ import annotations

import re
import unicodedata
import pandas as pd
from datetime import date
from typing import Any


# └── Coerção

def _s(v: Any) -> str | None:
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def _i(v: Any) -> int | None:
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        try:
            return int(v)
        except (ValueError, OverflowError):
            return None
    m = re.search(r"-?\d+", str(v))
    return int(m.group()) if m else None


def _f(v: Any) -> float | None:
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _d(v: Any) -> date | None:
    if pd.isna(v):
        return None
    try:
        return pd.to_datetime(v).date()
    except (ValueError, TypeError):
        return None


# └── Normalização de cabeçalho

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


# Mapeia cabeçalho normalizado → chave canonica do parser.
HEADERS = {
    "id grupo de empresas":  "id_grupo",
    "grupo":                 "nome_grupo",
    "cnpj contador":         "cnpj_contador",
    "contabilidade":         "contabilidade",
    "bairro":                "bairro",
    "cidade/uf":             "cidade_uf",
    "parceria":              "parceria",
    "data parceria":         "data_parceria",
    "tipo cnae":             "tipo_cnae",
    "colaborador":           "colaborador_nome",
    "funcao":                "funcao_origem",
    "porte faturamento":     "porte_faturamento",
    "score rfm":             "score_rfm",
    "apps ativos":           "apps_ativos",
    "mrr ativo":             "mrr_ativo",
    "leads no mes":          "leads_no_mes",
    "status rf":             "status_rf",
}


def _resolve_colunas(cols: list[str]) -> dict[str, str]:
    """
    Retorna {chave_canonica: nome_real_da_coluna}.
    Levanta ValueError se 'Tipo Cnae' ou 'ID Grupo de Empresas' não existiren.
    """
    res: dict[str, str] = {}
    for c in cols:
        canon = HEADERS.get(_norm(c))
        if canon and canon not in res:
            res[canon] = c

    obrigatorias = ("id_grupo", "tipo_cnae")
    falt = [k for k in obrigatorias if k not in res]
    if falt:
        raise ValueError(
            f"Colunas obrigatórias ausentes na planilha de carteira: {falt}. "
            f"Encontradas: {list(cols)}"
        )
    return res


# └── Parser principal

def parse_carteira_arquivo(caminho: str) -> dict:
    """
    Lê o XLSX e devolve:
      {
        "linhas": [ {...}, ... ],
        "total_linhas": int,
        "total_validos": int,
        "colaboradores": [{...}, ...],
        "erros": [str, ...],
      }
    """
    erros: list[str] = []

    try:
        df = pd.read_excel(caminho, engine="openpyxl")
    except Exception as e:
        return {
            "linhas": [],
            "total_linhas": 0,
            "total_validos": 0,
            "colaboradores": [],
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
            "colaboradores": [],
            "erros": [str(e)],
        }

    # Filtro CNAE Contábil
    col_cnae = colmap["tipo_cnae"]
    df["_cnae_norm"] = df[col_cnae].astype(str).map(_norm)
    df_cont = df[df["_cnae_norm"] == "cnae contabil"].copy()

    linhas: list[dict] = []
    for _, row in df_cont.iterrows():
        item: dict[str, Any] = {}
        for canon, real in colmap.items():
            v = row.get(real)
            if canon == "data_parceria":
                item[canon] = _d(v)
            elif canon in ("apps_ativos", "leads_no_mes"):
                item[canon] = _i(v)
            elif canon == "mrr_ativo":
                item[canon] = _f(v)
            else:
                item[canon] = _s(v)

        if not item.get("id_grupo"):
            erros.append(f"Linha sem ID Grupo de Empresas: {item.get('cnpj_contador')}")
            continue

        linhas.append(item)

    # Lista de colaboradores única
    cols_unicas: dict[str, dict] = {}
    for ln in linhas:
        nm = ln.get("colaborador_nome")
        if not nm:
            continue
        if nm not in cols_unicas:
            cols_unicas[nm] = {
                "nome": nm,
                "funcao_origem": ln.get("funcao_origem"),
            }

    return {
        "linhas": linhas,
        "total_linhas": total_linhas,
        "total_validos": len(linhas),
        "colaboradores": sorted(cols_unicas.values(), key=lambda c: c["nome"].lower()),
        "erros": erros,
    }
