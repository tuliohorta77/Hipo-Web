"""
HIPO — Parser do BD Ativados
Estrutura estável (10 anos, só 3 colunas adicionadas).
"""
import pandas as pd
from datetime import date
from typing import Optional


def _s(v) -> Optional[str]:
    if pd.isna(v): return None
    s = str(v).strip()
    return s or None

def _f(v) -> Optional[float]:
    if pd.isna(v): return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).replace("R$","").replace(".","").replace(",",".").strip()
    try: return float(s)
    except: return None

def _i(v) -> Optional[int]:
    f = _f(v)
    return int(f) if f is not None else None

def _d(v) -> Optional[date]:
    if pd.isna(v): return None
    try: return pd.to_datetime(v).date()
    except: return None

def _b(v) -> bool:
    if pd.isna(v): return False
    s = str(v).strip().upper()
    return s in ("SIM", "S", "TRUE", "1", "X", "YES", "ATIVO", "ACTIVE")

def _col(df: pd.DataFrame, nomes: list) -> Optional[str]:
    """Encontra coluna por variações de nome."""
    for n in nomes:
        for c in df.columns:
            if n.lower() in c.lower():
                return c
    return None


def parse_bd_ativados_arquivo(caminho: str) -> dict:
    """
    Processa o BD Ativados.
    Retorna: { linhas, total, erros }
    """
    try:
        df = pd.read_excel(caminho, engine="openpyxl")
        df = df.dropna(how="all")
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    except Exception as e:
        return {"linhas": [], "total": 0, "erros": [f"Erro ao ler arquivo: {e}"]}

    # Mapeia colunas conhecidas
    col_ref      = _col(df, ["referência aplicativo", "referencia aplicativo", "aplicativo"])
    col_razao    = _col(df, ["razão social", "razao social"])
    col_cnpj     = _col(df, ["cnpj"])
    col_situacao = _col(df, ["situação", "situacao", "status"])
    col_saude    = _col(df, ["saúde", "saude", "paciente"])
    col_dia_fat  = _col(df, ["dia faturamento", "dia do faturamento"])
    col_venc     = _col(df, ["vencimento"])
    col_tipo_fat = _col(df, ["tipo faturamento", "tipo de faturamento"])
    col_mensal   = _col(df, ["mensalidade", "valor mensal"])
    col_integ    = _col(df, ["integração contábil", "integracao contabil"])
    col_acesso   = _col(df, ["último acesso", "ultimo acesso"])
    col_mod_fin  = _col(df, ["módulo financeiro", "modulo financeiro", "financeiro"])
    col_mod_nfe  = _col(df, ["nfe", "nf-e", "nota fiscal"])
    col_mod_est  = _col(df, ["estoque"])
    col_mod_ven  = _col(df, ["vendas"])
    col_mod_ser  = _col(df, ["serviços", "servicos"])
    col_mod_com  = _col(df, ["compras"])
    col_at_email = _col(df, ["ativado por", "responsável", "responsavel"])
    col_cnt_cnpj = _col(df, ["cnpj contador", "cnpj parceiro"])
    col_cnt_nome = _col(df, ["contador", "parceiro"])
    col_data_at  = _col(df, ["data ativação", "data ativacao", "ativado em"])
    col_data_can = _col(df, ["cancelamento", "cancelado em"])

    linhas = []
    for _, r in df.iterrows():
        ref = _s(r.get(col_ref)) if col_ref else None
        if not ref:
            continue
        linhas.append({
            "referencia_aplicativo": ref,
            "razao_social":          _s(r.get(col_razao)) if col_razao else None,
            "cnpj":                  _s(r.get(col_cnpj)) if col_cnpj else None,
            "situacao":              _s(r.get(col_situacao)) if col_situacao else None,
            "saude_paciente":        _s(r.get(col_saude)) if col_saude else None,
            "dia_faturamento":       _i(r.get(col_dia_fat)) if col_dia_fat else None,
            "vencimento":            _i(r.get(col_venc)) if col_venc else None,
            "tipo_faturamento":      _s(r.get(col_tipo_fat)) if col_tipo_fat else None,
            "valor_mensalidade":    _f(r.get(col_mensal)) if col_mensal else None,
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
            "contador_nome":         _s(r.get(col_cnt_nome)) if col_cnt_nome else None,
            "data_ativacao":         _d(r.get(col_data_at)) if col_data_at else None,
            "data_cancelamento":     _d(r.get(col_data_can)) if col_data_can else None,
        })

    return {"linhas": linhas, "total": len(linhas), "erros": []}
