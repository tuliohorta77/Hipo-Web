"""
HIPO — Parser de POs
Detecta o tipo pelo nome do arquivo e extrai os dados de cada formato.
"""
import re
import pandas as pd
from datetime import date
from typing import Optional
from pathlib import Path


def detectar_tipo(nome_arquivo: str) -> tuple[str, bool]:
    """
    Retorna (tipo, tem_enabler).
    tipo: COMISSAO | INCENTIVO | REPASSE
    tem_enabler: True quando é Enabler (tem contador vinculado)
    """
    nome = nome_arquivo.upper()
    if "ENABLER" in nome:
        return "COMISSAO", True
    if "COMISSAOV6" in nome or "COMISSAO" in nome:
        return "COMISSAO", False
    if "INCENTIVO" in nome:
        return "INCENTIVO", False
    if "REPASSE" in nome:
        return "REPASSE", False
    raise ValueError(f"Tipo de PO não reconhecido: {nome_arquivo}")


def extrair_semana_ref(nome_arquivo: str) -> Optional[date]:
    """
    Tenta extrair o ano e mês do nome do arquivo.
    Retorna o primeiro domingo do mês como semana_ref.
    Formato esperado: ..._2026_4_Abril_...
    """
    match = re.search(r'_(\d{4})_(\d{1,2})_', nome_arquivo)
    if match:
        ano, mes = int(match.group(1)), int(match.group(2))
        return date(ano, mes, 1)
    return None


def _limpar_valor(v) -> Optional[float]:
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(s)
    except Exception:
        return None


def _limpar_str(v) -> Optional[str]:
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s if s else None


def _limpar_data(v) -> Optional[date]:
    if pd.isna(v):
        return None
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


def _extrair_parcela(texto) -> tuple[Optional[int], Optional[int]]:
    """Extrai X e Y de 'X/Y' ou 'Parcela X de Y'."""
    if pd.isna(texto):
        return None, None
    s = str(texto)
    match = re.search(r'(\d+)\s*/\s*(\d+)', s)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


# ── PARSERS POR TIPO ──────────────────────────────────────────────────────────

def parse_comissao(df: pd.DataFrame, tem_enabler: bool) -> list[dict]:
    """
    Parser para Comissão V6 e Enabler.
    Tenta mapear colunas por variações de nome.
    """
    linhas = []

    def col(nomes: list) -> Optional[str]:
        """Retorna o nome real da coluna que corresponde a uma das variações."""
        for n in nomes:
            for c in df.columns:
                if n.lower() in c.lower():
                    return c
        return None

    col_ref      = col(["referência", "referencia", "aplicativo"])
    col_razao    = col(["razão social", "razao social", "cliente", "empresa"])
    col_cnpj     = col(["cnpj"])
    col_plano    = col(["plano", "produto"])
    col_bruto    = col(["valor bruto", "bruto", "faturado"])
    col_liquido  = col(["valor líquido", "valor liquido", "líquido", "liquido", "comissão", "comissao"])
    col_impostos = col(["imposto", "tributo"])
    col_fundo    = col(["fundo", "marketing", "cooperad"])
    col_ativacao = col(["ativação", "ativacao", "data ativ"])
    col_nfse     = col(["nf-e", "nfe", "nota fiscal"])
    # Enabler extras
    col_cont_nome  = col(["contador", "parceiro"]) if tem_enabler else None
    col_cont_cnpj  = col(["cnpj contador", "cnpj parceiro"]) if tem_enabler else None
    col_cont_com   = col(["comissão contador", "comissao contador"]) if tem_enabler else None

    for _, row in df.iterrows():
        ref = _limpar_str(row.get(col_ref)) if col_ref else None
        if not ref:
            continue
        linha = {
            "tipo": "COMISSAO",
            "tem_enabler": tem_enabler,
            "referencia_aplicativo": ref,
            "razao_social": _limpar_str(row.get(col_razao)) if col_razao else None,
            "cnpj": _limpar_str(row.get(col_cnpj)) if col_cnpj else None,
            "plano": _limpar_str(row.get(col_plano)) if col_plano else None,
            "valor_bruto": _limpar_valor(row.get(col_bruto)) if col_bruto else None,
            "valor_liquido": _limpar_valor(row.get(col_liquido)) if col_liquido else None,
            "impostos": _limpar_valor(row.get(col_impostos)) if col_impostos else None,
            "fundo_marketing": _limpar_valor(row.get(col_fundo)) if col_fundo else None,
            "data_ativacao": _limpar_data(row.get(col_ativacao)) if col_ativacao else None,
        }
        if tem_enabler:
            linha["contador_nome"] = _limpar_str(row.get(col_cont_nome)) if col_cont_nome else None
            linha["contador_cnpj"] = _limpar_str(row.get(col_cont_cnpj)) if col_cont_cnpj else None
            linha["comissao_contador"] = _limpar_valor(row.get(col_cont_com)) if col_cont_com else None
        linhas.append(linha)
    return linhas


def parse_incentivo(df: pd.DataFrame) -> list[dict]:
    linhas = []

    def col(nomes):
        for n in nomes:
            for c in df.columns:
                if n.lower() in c.lower():
                    return c
        return None

    col_ref      = col(["referência", "referencia", "aplicativo"])
    col_razao    = col(["razão social", "razao social", "cliente"])
    col_cnpj     = col(["cnpj"])
    col_contador = col(["contador", "parceiro"])
    col_ativacao = col(["ativação", "ativacao"])
    col_premio   = col(["prêmio", "premio", "valor"])
    col_ep       = col(["ativado por", "responsável", "ep"])

    for _, row in df.iterrows():
        ref = _limpar_str(row.get(col_ref)) if col_ref else None
        if not ref:
            continue
        linhas.append({
            "tipo": "INCENTIVO",
            "tem_enabler": False,
            "referencia_aplicativo": ref,
            "razao_social": _limpar_str(row.get(col_razao)) if col_razao else None,
            "cnpj": _limpar_str(row.get(col_cnpj)) if col_cnpj else None,
            "contador_nome": _limpar_str(row.get(col_contador)) if col_contador else None,
            "data_ativacao": _limpar_data(row.get(col_ativacao)) if col_ativacao else None,
            "premio": _limpar_valor(row.get(col_premio)) if col_premio else None,
            "valor_liquido": _limpar_valor(row.get(col_premio)) if col_premio else None,
            "ativado_por_email": _limpar_str(row.get(col_ep)) if col_ep else None,
        })
    return linhas


def parse_repasse(df: pd.DataFrame) -> list[dict]:
    linhas = []

    def col(nomes):
        for n in nomes:
            for c in df.columns:
                if n.lower() in c.lower():
                    return c
        return None

    col_ref     = col(["referência", "referencia", "aplicativo"])
    col_razao   = col(["razão social", "razao social", "cliente"])
    col_cnpj    = col(["cnpj"])
    col_parcela = col(["parcela"])
    col_valor   = col(["valor", "repasse", "líquido", "liquido"])
    col_ep      = col(["ativado por", "ep", "responsável"])

    for _, row in df.iterrows():
        ref = _limpar_str(row.get(col_ref)) if col_ref else None
        if not ref:
            continue
        num, total = _extrair_parcela(row.get(col_parcela)) if col_parcela else (None, None)
        valor = _limpar_valor(row.get(col_valor)) if col_valor else None
        linhas.append({
            "tipo": "REPASSE",
            "tem_enabler": False,
            "referencia_aplicativo": ref,
            "razao_social": _limpar_str(row.get(col_razao)) if col_razao else None,
            "cnpj": _limpar_str(row.get(col_cnpj)) if col_cnpj else None,
            "parcela_numero": num,
            "parcela_total": total,
            "valor_liquido": valor,
            "ep_email": _limpar_str(row.get(col_ep)) if col_ep else None,
        })
    return linhas


# ── ENTRADA PRINCIPAL ─────────────────────────────────────────────────────────

def parse_po_arquivo(caminho: str) -> dict:
    """
    Processa um arquivo de PO e retorna:
    {
        tipo: str,
        tem_enabler: bool,
        semana_ref: date | None,
        linhas: list[dict],
        total: int,
        erros: list[str]
    }
    """
    nome = Path(caminho).name
    tipo, tem_enabler = detectar_tipo(nome)
    semana_ref = extrair_semana_ref(nome)
    erros = []

    try:
        df = pd.read_excel(caminho, engine="openpyxl")
        # Remove linhas completamente vazias
        df = df.dropna(how="all")
        # Remove colunas sem nome
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    except Exception as e:
        return {"tipo": tipo, "tem_enabler": tem_enabler, "semana_ref": semana_ref,
                "linhas": [], "total": 0, "erros": [f"Erro ao ler arquivo: {e}"]}

    try:
        if tipo == "COMISSAO":
            linhas = parse_comissao(df, tem_enabler)
        elif tipo == "INCENTIVO":
            linhas = parse_incentivo(df)
        elif tipo == "REPASSE":
            linhas = parse_repasse(df)
        else:
            linhas = []
            erros.append(f"Tipo desconhecido: {tipo}")
    except Exception as e:
        return {"tipo": tipo, "tem_enabler": tem_enabler, "semana_ref": semana_ref,
                "linhas": [], "total": 0, "erros": [f"Erro no parser: {e}"]}

    return {
        "tipo": tipo,
        "tem_enabler": tem_enabler,
        "semana_ref": semana_ref,
        "linhas": linhas,
        "total": len(linhas),
        "erros": erros,
    }
