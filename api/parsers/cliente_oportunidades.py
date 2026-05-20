"""
HIPO -- Parser da planilha de Oportunidades (módulo Clientes).

Lê o XLSX exportado do CRM Omie e devolve as linhas preparadas pra
inserir em cliente_oportunidade. Importa TUDO (sem filtro de Unidade,
Status ou data — decisão de produto).

Cabeçalhos esperados (50 colunas):
  Contagem, OP ID, CNPJ, Razão Social, Data Criação, Data Agendamento,
  Data Atualização, Origem CRM, Origem Macro, Proposta NMRR (R$),
  Proposta Pack (R$), Previsão (R$), Previsão (Data), Status, Temperatura,
  Fase, Motivo de Perda, CNAE, CNAE BIM, Seção, Setor, Faixa de Faturamento,
  Últ/Próx. Tarefa, Fase Suspect, Fase Cadência, Fase Qualificação,
  Fase Apresentação, Fase Proposta, Fase Conquistado, Unidade,
  CNPJ Contador, Razão Contador, Executivo de Contas, SDR - FR, SDR - GD,
  Executivo de Vendas, Executivo de Vendas - GD, Tipo Produto,
  Tipo Treinamento, Última Demo Realizada, Última tarefa (tipo),
  Última tarefa (dias), Dias Parado, Previsão Preenchido,
  Ticket Preenchido, Lead Trabalhado, Lead Agendado, Tarefa Futura,
  Demo Agendada, Demo Realizada
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

import pandas as pd


# ── Coerção ──────────────────────────────────────────────────────

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


def _bi(v: Any) -> int | None:
    """BIGINT — mesma coisa que _i mas usado pra clareza semântica."""
    return _i(v)


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


def _dt(v: Any) -> datetime | None:
    """Parse pra TIMESTAMPTZ. Aceita Timestamp/datetime/string."""
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


# ── Normalização de cabeçalho ────────────────────────────────────

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


# Mapeia cabeçalho normalizado → chave canônica.
# Atenção: a normalização remove acentos e converte pra minúsculas,
# então "Razão Social" vira "razao social".
HEADERS = {
    "contagem":                    None,  # ignorado
    "op id":                       "op_id",
    "cnpj":                        "cnpj",
    "razao social":                "razao_social",
    "data criacao":                "data_criacao",
    "data agendamento":            "data_agendamento",
    "data atualizacao":            "data_atualizacao",
    "origem crm":                  "origem_crm",
    "origem macro":                "origem_macro",
    "proposta nmrr (r$)":          "proposta_nmrr",
    "proposta pack (r$)":          "proposta_pack",
    "previsao (r$)":               "previsao_valor",
    "previsao (data)":             "previsao_data",
    "status":                      "status",
    "temperatura":                 "temperatura",
    "fase":                        "fase",
    "motivo de perda":             "motivo_perda",
    "cnae":                        "cnae",
    "cnae bim":                    "cnae_bim",
    "secao":                       "secao",
    "setor":                       "setor",
    "faixa de faturamento":        "faixa_faturamento",
    "ult/prox. tarefa":            "ult_prox_tarefa",
    "fase suspect":                "fase_suspect",
    "fase cadencia":               "fase_cadencia",
    "fase qualificacao":           "fase_qualificacao",
    "fase apresentacao":           "fase_apresentacao",
    "fase proposta":               "fase_proposta",
    "fase conquistado":            "fase_conquistado",
    "unidade":                     "unidade",
    "cnpj contador":               "cnpj_contador",
    "razao contador":              "razao_contador",
    "executivo de contas":         "executivo_contas",
    "sdr - fr":                    "sdr_fr",
    "sdr - gd":                    "sdr_gd",
    "executivo de vendas":         "executivo_vendas",
    "executivo de vendas - gd":    "executivo_vendas_gd",
    "tipo produto":                "tipo_produto",
    "tipo treinamento":            "tipo_treinamento",
    "ultima demo realizada":       "ultima_demo_realizada",
    "ultima tarefa (tipo)":        "ultima_tarefa_tipo",
    "ultima tarefa (dias)":        "ultima_tarefa_dias",
    "dias parado":                 "dias_parado",
    "previsao preenchido":         "previsao_preenchido",
    "ticket preenchido":           "ticket_preenchido",
    "lead trabalhado":             "lead_trabalhado",
    "lead agendado":               "lead_agendado",
    "tarefa futura":               "tarefa_futura",
    "demo agendada":               "demo_agendada",
    "demo realizada":              "demo_realizada",
}


# Conversores por campo canônico
CONVERTERS = {
    "op_id":                _bi,
    "cnpj":                 _s,
    "razao_social":         _s,
    "data_criacao":         _dt,
    "data_agendamento":     _s,   # string mesmo (formato variado)
    "data_atualizacao":     _dt,
    "ult_prox_tarefa":      _dt,
    "origem_crm":           _s,
    "origem_macro":         _s,
    "status":               _s,
    "fase":                 _s,
    "motivo_perda":         _s,
    "temperatura":          _f,
    "proposta_nmrr":        _f,
    "proposta_pack":        _f,
    "previsao_valor":       _f,
    "previsao_data":        _dt,
    "cnae":                 _bi,
    "cnae_bim":             _s,
    "secao":                _s,
    "setor":                _s,
    "faixa_faturamento":    _s,
    "fase_suspect":         _dt,
    "fase_cadencia":        _dt,
    "fase_qualificacao":    _dt,
    "fase_apresentacao":    _dt,
    "fase_proposta":        _dt,
    "fase_conquistado":     _dt,
    "unidade":              _s,
    "cnpj_contador":        _s,
    "razao_contador":       _s,
    "executivo_contas":     _s,
    "sdr_fr":               _s,
    "sdr_gd":               _s,
    "executivo_vendas":     _s,
    "executivo_vendas_gd":  _s,
    "tipo_produto":         _s,
    "tipo_treinamento":     _s,
    "ultima_demo_realizada": _dt,
    "ultima_tarefa_tipo":   _s,
    "ultima_tarefa_dias":   _i,
    "dias_parado":          _i,
    "previsao_preenchido":  _s,
    "ticket_preenchido":    _s,
    "lead_trabalhado":      _s,
    "lead_agendado":        _s,
    "tarefa_futura":        _i,
    "demo_agendada":        _s,
    "demo_realizada":       _s,
}


def _resolve_colunas(cols: list[str]) -> dict[str, str]:
    """{chave_canonica: nome_real}. Não levanta erro — colunas faltantes
    apenas resultam em campo NULL na inserção."""
    res: dict[str, str] = {}
    for c in cols:
        canon = HEADERS.get(_norm(c))
        if canon and canon not in res:
            res[canon] = c
    return res


def parse_oportunidades_arquivo(caminho: str) -> dict:
    """
    Lê o XLSX e devolve:
      {
        "linhas": [ {campo_canonico: valor, ...}, ... ],
        "total_linhas": int,
        "total_validos": int,
        "erros": [str, ...],
      }
    """
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

    # Pelo menos OP ID precisa existir
    if "op_id" not in colmap:
        return {
            "linhas": [], "total_linhas": total_linhas, "total_validos": 0,
            "erros": ["Coluna 'OP ID' não encontrada na planilha."],
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

        # OP ID obrigatório
        if item.get("op_id") is None:
            continue

        linhas.append(item)

    return {
        "linhas": linhas,
        "total_linhas": total_linhas,
        "total_validos": len(linhas),
        "erros": erros,
    }
