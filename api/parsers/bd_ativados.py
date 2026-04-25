"""
HIPO — Parser do BD Ativados (v2)

Mudanças vs v1:
  - Auto-detecta a linha de cabeçalho (a planilha do franqueador Omie tem
    título e timestamp nas linhas 0-1; o cabeçalho real começa na linha 2,
    mas isso pode mudar — então detectamos dinamicamente).
  - Matching de colunas com normalização (acentos/case/espaços) e busca por
    padrões mais específicos primeiro pra evitar match indevido (ex: a busca
    por "contador" não pode pegar "Contato Financeiro").
  - Mapeamento dos módulos batendo com os nomes reais da Omie:
      módulo_nfe        ← "NF-e"
      módulo_servicos   ← "NFS-e"
      módulo_financeiro ← "Lançamentos Conta Corrente"
      módulo_estoque    ← (não há na planilha; mantém False)
      módulo_vendas     ← "Contas a Receber"
      módulo_compras    ← "Contas a Pagar"
"""
import re
import unicodedata
import pandas as pd
from datetime import date
from typing import Optional


# ── Helpers de coerção ──────────────────────────────────────────────

def _s(v) -> Optional[str]:
    if pd.isna(v): return None
    s = str(v).strip()
    return s or None

def _f(v) -> Optional[float]:
    if pd.isna(v): return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try: return float(s)
    except Exception: return None

def _i(v) -> Optional[int]:
    # Tenta extrair só o número do texto (ex: "todo dia 23" → 23)
    if pd.isna(v): return None
    if isinstance(v, (int, float)): return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None

def _d(v) -> Optional[date]:
    if pd.isna(v): return None
    try: return pd.to_datetime(v).date()
    except Exception: return None

def _b(v) -> bool:
    """Booleano permissivo. Vazio/N/A/0/Não → False; resto → True."""
    if pd.isna(v): return False
    s = str(v).strip().upper()
    if s in ("", "NAO", "NÃO", "N", "FALSE", "0", "NONE", "NAN", "-"):
        return False
    return True


# ── Normalização de cabeçalhos ──────────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase, sem acentos, espaços colapsados."""
    if s is None: return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


def _find_header_row(caminho: str, max_scan: int = 15) -> int:
    """
    Detecta a linha de cabeçalho. Critério: primeira linha com pelo menos 10
    valores não-nulos, todos string-like, sem datas/booleanos óbvios.
    """
    raw = pd.read_excel(caminho, engine="openpyxl", header=None, nrows=max_scan)
    for i, row in raw.iterrows():
        valores = [v for v in row if pd.notna(v)]
        if len(valores) < 10:
            continue
        # Heurística: cabeçalho costuma ser composto de strings curtas, sem datas
        strings = [v for v in valores if isinstance(v, str)]
        if len(strings) >= len(valores) * 0.8:
            # Bate? Considera essa a linha de cabeçalho.
            return i
    return 0  # fallback


def _col(df: pd.DataFrame, padroes: list) -> Optional[str]:
    """
    Encontra coluna por padrões normalizados.
    `padroes` é uma lista de tuplas (modo, valor):
      ("eq", "cnpj")           → match exato após normalização
      ("contains", "razao")    → contém substring
      ("regex", r"...")        → regex
    Retorna o nome ORIGINAL da coluna (sem normalizar) pra usar em df[...].
    Procura na ordem dos padrões → mais específico primeiro.
    """
    cols_norm = {c: _norm(c) for c in df.columns}
    for modo, val in padroes:
        for c, cn in cols_norm.items():
            if modo == "eq" and cn == val:
                return c
            if modo == "contains" and val in cn:
                return c
            if modo == "regex" and re.search(val, cn):
                return c
    return None


# ── Parser principal ────────────────────────────────────────────────

def parse_bd_ativados_arquivo(caminho: str) -> dict:
    """
    Processa o BD Ativados.
    Retorna: { linhas, total, erros }
    """
    erros = []
    try:
        header_row = _find_header_row(caminho)
        df = pd.read_excel(caminho, engine="openpyxl", header=header_row)
        df = df.dropna(how="all")
        df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed", regex=True)]
    except Exception as e:
        return {"linhas": [], "total": 0, "erros": [f"Erro ao ler arquivo: {e}"]}

    if df.empty:
        return {"linhas": [], "total": 0,
                "erros": ["Planilha vazia após remover linhas em branco."]}

    # ── Mapeamento de colunas (mais específico primeiro) ──
    col_ref      = _col(df, [("eq", "referencia do aplicativo"),
                             ("contains", "referencia do aplicativo"),
                             ("contains", "referencia aplicativo"),
                             ("eq", "aplicativo")])
    col_razao    = _col(df, [("eq", "razao social"), ("contains", "razao social")])
    col_cnpj     = _col(df, [("eq", "cnpj")])
    col_situacao = _col(df, [("contains", "situacao em "),    # "Situação em DD/MM..."
                             ("eq", "situacao"),
                             ("eq", "status")])
    col_saude    = _col(df, [("contains", "saude do paciente"),
                             ("contains", "saude")])
    col_dia_fat  = _col(df, [("eq", "dia do faturamento"),
                             ("contains", "dia do faturamento"),
                             ("contains", "dia faturamento")])
    col_venc     = _col(df, [("eq", "vencimento"),
                             ("regex", r"^vencimento$")])
    col_tipo_fat = _col(df, [("eq", "tipo do faturamento"),
                             ("contains", "tipo do faturamento"),
                             ("contains", "tipo faturamento")])
    # Valor da mensalidade — preferência pelo "atual no contrato"
    col_mensal   = _col(df, [("contains", "valor mensal - atual"),
                             ("contains", "valor mensal atual"),
                             ("contains", "valor mensal - informado"),
                             ("contains", "valor mensal"),
                             ("contains", "mensalidade")])
    col_integ    = _col(df, [("contains", "integracao contabil"),
                             ("contains", "integracao")])
    col_acesso   = _col(df, [("eq", "ultimo acesso"),
                             ("contains", "ultimo acesso")])
    # Módulos — nomes reais da Omie
    col_mod_fin  = _col(df, [("eq", "lancamentos conta corrente"),
                             ("contains", "lancamentos conta corrente"),
                             ("contains", "modulo financeiro"),
                             ("eq", "financeiro")])
    col_mod_nfe  = _col(df, [("eq", "nf-e"), ("eq", "nfe"),
                             ("regex", r"^nf-?e$")])
    col_mod_ser  = _col(df, [("eq", "nfs-e"), ("eq", "nfse"),
                             ("regex", r"^nfs-?e$"),
                             ("contains", "servicos")])
    col_mod_est  = _col(df, [("eq", "estoque"), ("contains", "estoque")])
    col_mod_ven  = _col(df, [("eq", "contas a receber"),
                             ("contains", "contas a receber"),
                             ("eq", "vendas")])
    col_mod_com  = _col(df, [("eq", "contas a pagar"),
                             ("contains", "contas a pagar"),
                             ("eq", "compras")])
    col_at_email = _col(df, [("eq", "ativado por"),
                             ("contains", "ativado por")])
    # Contador — match exato pra não pegar "Contato Financeiro"
    col_cnt_cnpj = _col(df, [("contains", "cnpj contador"),
                             ("contains", "cnpj parceiro"),
                             ("contains", "cnpj do contador")])
    col_cnt_nome = _col(df, [("eq", "contador"),
                             ("eq", "parceiro contabil"),
                             ("eq", "parceiro")])
    col_data_at  = _col(df, [("eq", "data de ativacao"),
                             ("contains", "data de ativacao"),
                             ("contains", "data ativacao"),
                             ("contains", "ativado em")])
    col_data_can = _col(df, [("eq", "data do cancelamento"),
                             ("contains", "data do cancelamento"),
                             ("contains", "cancelamento"),
                             ("contains", "cancelado em")])

    if not col_ref:
        erros.append(
            "Coluna 'Referência do Aplicativo' não encontrada. "
            f"Colunas disponíveis: {list(df.columns)[:20]}..."
        )
        return {"linhas": [], "total": 0, "erros": erros}

    # ── Itera linhas ──
    linhas = []
    for _, r in df.iterrows():
        ref = _s(r.get(col_ref))
        if not ref:
            continue
        # "Sem Contador" → trata como ausente, não como nome de contador
        contador_raw = _s(r.get(col_cnt_nome)) if col_cnt_nome else None
        if contador_raw and "sem contador" in contador_raw.lower():
            contador_raw = None

        linhas.append({
            "referencia_aplicativo": ref,
            "razao_social":          _s(r.get(col_razao)) if col_razao else None,
            "cnpj":                  _s(r.get(col_cnpj)) if col_cnpj else None,
            "situacao":              _s(r.get(col_situacao)) if col_situacao else None,
            "saude_paciente":        _s(r.get(col_saude)) if col_saude else None,
            "dia_faturamento":       _i(r.get(col_dia_fat)) if col_dia_fat else None,
            "vencimento":            _i(r.get(col_venc)) if col_venc else None,
            "tipo_faturamento":      _s(r.get(col_tipo_fat)) if col_tipo_fat else None,
            "valor_mensalidade":     _f(r.get(col_mensal)) if col_mensal else None,
            "integracao_contabil":   _b(r.get(col_integ)) if col_integ else False,
            "ultimo_acesso":         _d(r.get(col_acesso)) if col_acesso else None,
            "modulo_financeiro":     _b(r.get(col_mod_fin)) if col_mod_fin else False,
            "modulo_nfe":            _b(r.get(col_mod_nfe)) if col_mod_nfe else False,
            "modulo_estoque":        _b(r.get(col_mod_est)) if col_mod_est else False,
            "modulo_vendas":         _b(r.get(col_mod_ven)) if col_mod_ven else False,
            "modulo_servicos":       _b(r.get(col_mod_ser)) if col_mod_ser else False,
            "modulo_compras":        _b(r.get(col_mod_com)) if col_mod_com else False,
            "ativado_por_email":     _s(r.get(col_at_email)) if col_at_email else None,
            "contador_cnpj":         _s(r.get(col_cnt_cnpj)) if col_cnt_cnpj else None,
            "contador_nome":         contador_raw,
            "data_ativacao":         _d(r.get(col_data_at)) if col_data_at else None,
            "data_cancelamento":     _d(r.get(col_data_can)) if col_data_can else None,
        })

    return {"linhas": linhas, "total": len(linhas), "erros": erros}
