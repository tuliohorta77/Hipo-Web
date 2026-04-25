"""
HIPO — Parser do CROmie
Processa as 4 abas do Excel extraído do CROMie.
Faz auditoria de schema a cada upload — detecta colunas novas ou removidas.
"""
import pandas as pd
from datetime import date
from typing import Optional

# ── SCHEMAS DE REFERÊNCIA ─────────────────────────────────────────────────────
# Colunas esperadas em cada aba (baseado na estrutura atual conhecida).
# Usadas para auditoria — qualquer divergência é reportada.

SCHEMA_CLIENTE_FINAL = [
    "op_id", "empresa", "cnpj", "responsavel", "fase", "temperatura",
    "origem", "tarefa_futura", "temperatura_preenchida", "previsao_preenchida",
    "ticket_preenchido", "demo_realizada", "ticket", "previsao_fechamento",
    "usuario_responsavel", "contador_cnpj", "contador_nome",
    "data_criacao", "data_ganho", "data_perda", "motivo_perda",
]

SCHEMA_TAREFA_CLIENTE = [
    "op_id", "empresa", "tipo_tarefa", "finalidade", "resultado",
    "canal", "usuario_responsavel", "data_tarefa",
]

SCHEMA_CONTADOR = [
    "cnpj", "razao_social", "responsavel", "status_parceria", "temperatura",
    "dias_parado", "possui_tarefa", "status_tarefa", "sow_preenchido",
    "usuario_responsavel",
]

SCHEMA_TAREFA_CONTADOR = [
    "contador_cnpj", "contador_nome", "tipo_tarefa", "finalidade",
    "resultado", "canal", "usuario_responsavel", "data_tarefa",
]

# ── HELPERS ───────────────────────────────────────────────────────────────────

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

def _d(v) -> Optional[date]:
    if pd.isna(v): return None
    try: return pd.to_datetime(v).date()
    except: return None

def _b(v) -> bool:
    if pd.isna(v): return False
    s = str(v).strip().upper()
    return s in ("SIM", "S", "TRUE", "1", "X", "YES")

def _col(df: pd.DataFrame, nomes: list) -> Optional[str]:
    """Encontra coluna por variações de nome (case insensitive, parcial)."""
    for n in nomes:
        for c in df.columns:
            if n.lower() in c.lower():
                return c
    return None

def _auditar_schema(df: pd.DataFrame, schema_esperado: list, nome_aba: str) -> dict:
    """
    Compara as colunas do DataFrame com o schema esperado.
    Retorna: { colunas_reais, novas, removidas, alterado }
    """
    colunas_reais = list(df.columns)
    colunas_lower = [c.lower() for c in colunas_reais]
    esperadas_lower = [e.lower() for e in schema_esperado]
    novas = [c for c in colunas_reais if not any(e in c.lower() for e in esperadas_lower)]
    removidas = [e for e in schema_esperado if not any(e in c.lower() for c in colunas_reais)]
    return {
        "colunas_reais": colunas_reais,
        "novas": novas,
        "removidas": removidas,
        "alterado": bool(novas or removidas),
        "aba": nome_aba,
    }

# ── PARSERS POR ABA ───────────────────────────────────────────────────────────

def parse_cliente_final(df: pd.DataFrame) -> list[dict]:
    linhas = []
    for _, r in df.iterrows():
        linhas.append({
            "op_id":                    _s(r.get(_col(df, ["op", "id", "oportunidade"]))),
            "empresa":                  _s(r.get(_col(df, ["empresa", "razão social", "cliente"]))),
            "cnpj":                     _s(r.get(_col(df, ["cnpj"]))),
            "responsavel":              _s(r.get(_col(df, ["responsável", "responsavel", "contato"]))),
            "fase":                     _s(r.get(_col(df, ["fase", "etapa", "estágio"]))),
            "temperatura":              _s(r.get(_col(df, ["temperatura", "temp"]))),
            "origem":                   _s(r.get(_col(df, ["origem"]))),
            "tarefa_futura":            _b(r.get(_col(df, ["tarefa futura", "tarefa"]))),
            "temperatura_preenchida":   _b(r.get(_col(df, ["temperatura preenchida"]))),
            "previsao_preenchida":      _b(r.get(_col(df, ["previsão preenchida", "previsao preenchida"]))),
            "ticket_preenchido":        _b(r.get(_col(df, ["ticket preenchido"]))),
            "demo_realizada":           _b(r.get(_col(df, ["demo realizada", "apresentação realizada"]))),
            "ticket":                   _f(r.get(_col(df, ["ticket", "valor"]))),
            "previsao_fechamento":      _d(r.get(_col(df, ["previsão", "previsao", "fechamento"]))),
            "usuario_responsavel":      _s(r.get(_col(df, ["usuário", "usuario", "ec", "ev", "sdr"]))),
            "contador_cnpj":            _s(r.get(_col(df, ["cnpj contador", "cnpj parceiro"]))),
            "contador_nome":            _s(r.get(_col(df, ["contador", "parceiro"]))),
            "data_criacao":             _d(r.get(_col(df, ["criação", "criacao", "data cri"]))),
            "data_ganho":               _d(r.get(_col(df, ["ganho", "data ganho", "conquistado"]))),
            "data_perda":               _d(r.get(_col(df, ["perda", "data perda", "perdido"]))),
            "motivo_perda":             _s(r.get(_col(df, ["motivo", "motivo perda"]))),
        })
    return linhas


def parse_tarefa_cliente(df: pd.DataFrame) -> list[dict]:
    linhas = []
    for _, r in df.iterrows():
        linhas.append({
            "op_id":                _s(r.get(_col(df, ["op", "id", "oportunidade"]))),
            "empresa":              _s(r.get(_col(df, ["empresa", "cliente"]))),
            "tipo_tarefa":          _s(r.get(_col(df, ["tipo"]))),
            "finalidade":           _s(r.get(_col(df, ["finalidade"]))),
            "resultado":            _s(r.get(_col(df, ["resultado"]))),
            "canal":                _s(r.get(_col(df, ["canal"]))),
            "usuario_responsavel":  _s(r.get(_col(df, ["usuário", "usuario", "responsável"]))),
            "data_tarefa":          _d(r.get(_col(df, ["data", "quando"]))),
        })
    return linhas


def parse_contador(df: pd.DataFrame) -> list[dict]:
    linhas = []
    for _, r in df.iterrows():
        linhas.append({
            "cnpj":                 _s(r.get(_col(df, ["cnpj"]))),
            "razao_social":         _s(r.get(_col(df, ["razão social", "razao social", "nome"]))),
            "responsavel":          _s(r.get(_col(df, ["responsável", "contato"]))),
            "status_parceria":      _s(r.get(_col(df, ["status", "situação", "parceria"]))),
            "temperatura":          _s(r.get(_col(df, ["temperatura", "temp"]))),
            "dias_parado":          int(_f(r.get(_col(df, ["dias parado", "parado"]))) or 0),
            "possui_tarefa":        _b(r.get(_col(df, ["possui tarefa", "tem tarefa"]))),
            "status_tarefa":        _s(r.get(_col(df, ["status tarefa"]))),
            "sow_preenchido":       _b(r.get(_col(df, ["sow", "carteira mapeada", "mapeado"]))),
            "usuario_responsavel":  _s(r.get(_col(df, ["usuário", "usuario", "ec", "responsável"]))),
        })
    return linhas


def parse_tarefa_contador(df: pd.DataFrame) -> list[dict]:
    linhas = []
    for _, r in df.iterrows():
        linhas.append({
            "contador_cnpj":        _s(r.get(_col(df, ["cnpj"]))),
            "contador_nome":        _s(r.get(_col(df, ["contador", "parceiro", "nome"]))),
            "tipo_tarefa":          _s(r.get(_col(df, ["tipo"]))),
            "finalidade":           _s(r.get(_col(df, ["finalidade"]))),
            "resultado":            _s(r.get(_col(df, ["resultado"]))),
            "canal":                _s(r.get(_col(df, ["canal"]))),
            "usuario_responsavel":  _s(r.get(_col(df, ["usuário", "usuario", "responsável"]))),
            "data_tarefa":          _d(r.get(_col(df, ["data", "quando"]))),
        })
    return linhas

# ── ENTRADA PRINCIPAL ─────────────────────────────────────────────────────────

ABA_MAP = {
    "cliente final":    ("cliente_final",    parse_cliente_final,    SCHEMA_CLIENTE_FINAL),
    "tarefa cliente":   ("tarefa_cliente",   parse_tarefa_cliente,   SCHEMA_TAREFA_CLIENTE),
    "contador":         ("contador",         parse_contador,         SCHEMA_CONTADOR),
    "tarefa contador":  ("tarefa_contador",  parse_tarefa_contador,  SCHEMA_TAREFA_CONTADOR),
}

def parse_cromie_arquivo(caminho: str) -> dict:
    """
    Processa o Excel do CROmie com as 4 abas.
    Retorna:
    {
        abas: {
            cliente_final: { linhas, auditoria },
            tarefa_cliente: { linhas, auditoria },
            contador: { linhas, auditoria },
            tarefa_contador: { linhas, auditoria },
        },
        schema_alterado: bool,
        erros: list[str]
    }
    """
    try:
        xls = pd.ExcelFile(caminho, engine="openpyxl")
    except Exception as e:
        return {"abas": {}, "schema_alterado": False, "erros": [f"Erro ao abrir arquivo: {e}"]}

    resultado = {"abas": {}, "schema_alterado": False, "erros": []}

    for sheet_name in xls.sheet_names:
        chave_normalizada = sheet_name.strip().lower()
        # Encontra a aba correspondente no mapa
        aba_key = next(
            (k for k in ABA_MAP if k in chave_normalizada),
            None
        )
        if not aba_key:
            continue  # Ignora abas desconhecidas

        nome_interno, parser_fn, schema_ref = ABA_MAP[aba_key]

        try:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            df = df.dropna(how="all")
            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

            auditoria = _auditar_schema(df, schema_ref, sheet_name)
            if auditoria["alterado"]:
                resultado["schema_alterado"] = True

            linhas = parser_fn(df)
            resultado["abas"][nome_interno] = {
                "linhas": linhas,
                "total": len(linhas),
                "auditoria": auditoria,
            }
        except Exception as e:
            resultado["erros"].append(f"Erro na aba '{sheet_name}': {e}")

    return resultado
