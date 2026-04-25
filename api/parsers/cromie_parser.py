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
    Usa busca bidirecional: coluna real contém termo esperado OU termo esperado contém coluna real.
    Retorna: { colunas_reais, novas, removidas, alterado }
    """
    colunas_reais = list(df.columns)

    def _matched(col_real: str, termos_esperados: list) -> bool:
        c = col_real.lower().replace(" ", "_").replace("-", "_")
        for e in termos_esperados:
            e_norm = e.lower().replace(" ", "_").replace("-", "_")
            if e_norm in c or c in e_norm:
                return True
        return False

    novas = [c for c in colunas_reais if not _matched(c, schema_esperado)]
    removidas = [e for e in schema_esperado if not _matched(e, [c for c in colunas_reais])]
    return {
        "colunas_reais": colunas_reais,
        "novas": novas,
        "removidas": removidas,
        "alterado": bool(novas or removidas),
        "aba": nome_aba,
    }

# ── PARSERS POR ABA ───────────────────────────────────────────────────────────

def parse_cliente_final(df: pd.DataFrame) -> list[dict]:
    # Resolve nomes de colunas uma vez (fora do loop) — performance
    col_op_id          = _col(df, ["op", "id", "oportunidade"])
    col_empresa        = _col(df, ["empresa", "razão social", "cliente"])
    col_cnpj           = _col(df, ["cnpj"])
    col_responsavel    = _col(df, ["responsável", "responsavel", "contato"])
    col_fase           = _col(df, ["fase", "etapa", "estágio"])
    col_temperatura    = _col(df, ["temperatura", "temp"])
    col_origem         = _col(df, ["origem"])
    col_tarefa_futura  = _col(df, ["tarefa futura", "tarefa"])
    col_temp_preench   = _col(df, ["temperatura preenchida"])
    col_prev_preench   = _col(df, ["previsão preenchida", "previsao preenchida"])
    col_ticket_preench = _col(df, ["ticket preenchido"])
    col_demo_real      = _col(df, ["demo realizada", "apresentação realizada"])
    # NMRR — duas colunas com regra dependente de fase:
    #   - "Proposta NMRR (R$)" é o valor padrão do ticket
    #   - "Previsão (R$)" é fallback quando fase está em "03. Qualificação"
    col_proposta_nmrr  = _col(df, ["proposta nmrr", "nmrr (r$)", "nmrr proposta"])
    col_previsao_rs    = _col(df, ["previsão (r$)", "previsao (r$)", "previsão r$", "previsao r$"])
    # Fallback genérico se planilha vier com nome legado (ticket / valor)
    col_ticket_legacy  = _col(df, ["ticket", "valor"])
    col_previsao_fech  = _col(df, ["previsão", "previsao", "fechamento"])
    col_usuario_resp   = _col(df, ["usuário", "usuario", "ec", "ev", "sdr"])
    col_contador_cnpj  = _col(df, ["cnpj contador", "cnpj parceiro"])
    col_contador_nome  = _col(df, ["contador", "parceiro"])
    col_data_criacao   = _col(df, ["criação", "criacao", "data cri"])
    col_data_ganho     = _col(df, ["ganho", "data ganho", "conquistado"])
    col_data_perda     = _col(df, ["perda", "data perda", "perdido"])
    col_motivo_perda   = _col(df, ["motivo", "motivo perda"])

    linhas = []
    for _, r in df.iterrows():
        fase = _s(r.get(col_fase)) if col_fase else None

        # Regra de ticket (Proposta NMRR ou Previsão R$ em Qualificação)
        proposta = _f(r.get(col_proposta_nmrr)) if col_proposta_nmrr else None
        previsao = _f(r.get(col_previsao_rs)) if col_previsao_rs else None
        ticket_legado = _f(r.get(col_ticket_legacy)) if col_ticket_legacy else None
        if fase and "qualif" in fase.lower():
            ticket = previsao if previsao is not None else proposta
        else:
            ticket = proposta if proposta is not None else previsao
        if ticket is None:
            ticket = ticket_legado  # último recurso

        linhas.append({
            "op_id":                    _s(r.get(col_op_id)) if col_op_id else None,
            "empresa":                  _s(r.get(col_empresa)) if col_empresa else None,
            "cnpj":                     _s(r.get(col_cnpj)) if col_cnpj else None,
            "responsavel":              _s(r.get(col_responsavel)) if col_responsavel else None,
            "fase":                     fase,
            "temperatura":              _s(r.get(col_temperatura)) if col_temperatura else None,
            "origem":                   _s(r.get(col_origem)) if col_origem else None,
            "tarefa_futura":            _b(r.get(col_tarefa_futura)) if col_tarefa_futura else False,
            "temperatura_preenchida":   _b(r.get(col_temp_preench)) if col_temp_preench else False,
            "previsao_preenchida":      _b(r.get(col_prev_preench)) if col_prev_preench else False,
            "ticket_preenchido":        _b(r.get(col_ticket_preench)) if col_ticket_preench else False,
            "demo_realizada":           _b(r.get(col_demo_real)) if col_demo_real else False,
            "ticket":                   ticket,
            "previsao_fechamento":      _d(r.get(col_previsao_fech)) if col_previsao_fech else None,
            "usuario_responsavel":      _s(r.get(col_usuario_resp)) if col_usuario_resp else None,
            "contador_cnpj":            _s(r.get(col_contador_cnpj)) if col_contador_cnpj else None,
            "contador_nome":            _s(r.get(col_contador_nome)) if col_contador_nome else None,
            "data_criacao":             _d(r.get(col_data_criacao)) if col_data_criacao else None,
            "data_ganho":               _d(r.get(col_data_ganho)) if col_data_ganho else None,
            "data_perda":               _d(r.get(col_data_perda)) if col_data_perda else None,
            "motivo_perda":             _s(r.get(col_motivo_perda)) if col_motivo_perda else None,
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
            (k for k in sorted(ABA_MAP.keys(), key=len, reverse=True)
             if k in chave_normalizada),
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