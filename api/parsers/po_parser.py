"""
HIPO — Parser de POs (v2)

Reescrito após análise das planilhas reais da Omie. Os 4 tipos de PO seguem
o MESMO padrão estrutural:

  ┌─ Cabeçalho na linha 0
  ├─ N linhas de operações (clientes/transações)
  ├─ 1 linha "Fundo de Marketing (2,5%)" — valor negativo
  └─ 1 linha sem descrição = subtotal (soma operações + fundo)

A diferença entre tipos é só nos NOMES das colunas:

| Tipo       | col_base            | col_valor          | identificador no nome   |
|------------|---------------------|--------------------|-------------------------|
| COMISSAO   | Faturado R$         | Comissão R$        | ComissaoV6 (sem Enabler)|
| ENABLER    | Faturado R$         | Comissão R$        | ComissaoV6Enabler       |
| REPASSE    | Valor Faturado      | Valor do Repasse   | Repasse                 |
| INCENTIVO  | Valor Negociado R$  | Prêmio R$          | Incentivo               |

valor_a_receber = soma_operacoes(col_valor) + fundo_marketing
                ≈ subtotal_planilha   (validado, divergência marcada como warning)
"""
import re
import unicodedata
import pandas as pd
from datetime import date
from pathlib import Path
from typing import Optional


# ── DETECÇÃO DO TIPO ────────────────────────────────────────────────

def detectar_tipo(nome_arquivo: str) -> tuple[str, bool]:
    """
    Retorna (tipo, tem_enabler).
    tipo: COMISSAO | INCENTIVO | REPASSE
    tem_enabler: True quando é a variante Enabler da Comissão
    """
    nome = nome_arquivo.upper()
    # Ordem importa: testar Enabler antes de Comissão
    if "ENABLER" in nome:
        return "COMISSAO", True
    if "COMISSAOV6" in nome or "COMISSAO" in nome:
        return "COMISSAO", False
    if "INCENTIVO" in nome:
        return "INCENTIVO", False
    if "REPASSE" in nome:
        return "REPASSE", False
    raise ValueError(f"Tipo de PO não reconhecido pelo nome do arquivo: {nome_arquivo}")


def extrair_semana_ref(nome_arquivo: str) -> Optional[date]:
    """Extrai ano/mês do padrão '..._2026_4_Abril_...' → primeiro do mês."""
    m = re.search(r"_(\d{4})_(\d{1,2})_", nome_arquivo)
    if m:
        ano, mes = int(m.group(1)), int(m.group(2))
        try:
            return date(ano, mes, 1)
        except ValueError:
            return None
    return None


# ── HELPERS DE COERÇÃO ──────────────────────────────────────────────

def _norm(s) -> str:
    """Lowercase, sem acento, espaços normalizados."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s


def _s(v) -> Optional[str]:
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def _f(v) -> Optional[float]:
    """
    Float robusto. NÃO mexe em valores que já são int/float (o bug do parser
    antigo era fazer `.replace('.', '')` em strings, o que destruía floats).
    """
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("R$", "").strip()
    # Heurística para BR vs US: se tem vírgula E ponto, ponto é separador de milhar
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _i(v) -> Optional[int]:
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def _d(v) -> Optional[date]:
    if pd.isna(v):
        return None
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


def _parcela(v) -> tuple[Optional[int], Optional[int]]:
    """Extrai 'X/Y' de '004/010' ou similar."""
    if pd.isna(v):
        return None, None
    m = re.search(r"(\d+)\s*/\s*(\d+)", str(v))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _col(df: pd.DataFrame, padroes: list) -> Optional[str]:
    """
    Encontra coluna por padrões normalizados, na ordem fornecida.
    `padroes`: lista de tuplas (modo, valor):
      ('eq', 'cnpj')          → match exato após normalização
      ('contains', 'razao')   → substring após normalização
      ('regex', r'^...$')     → regex sobre o nome normalizado
    Retorna o nome ORIGINAL da coluna (pra usar em df[...]).
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


def _normalizar_cnpj(v) -> Optional[str]:
    """Tira pontuação, mantém só dígitos. None se vazio."""
    if pd.isna(v):
        return None
    s = re.sub(r"\D", "", str(v))
    return s or None


# ── LINHAS ESPECIAIS ────────────────────────────────────────────────

def _eh_linha_fundo(valor_descricao: str) -> bool:
    """Linha 'Fundo de Marketing (2,5%)' — variações de capitalização/acento."""
    if not valor_descricao:
        return False
    return "fundo" in _norm(valor_descricao) and "marketing" in _norm(valor_descricao)


def _separar_linhas(df: pd.DataFrame, col_base: str, col_descricao: str
                    ) -> tuple[pd.DataFrame, Optional[float], Optional[float]]:
    """
    Separa o DataFrame em:
      - operações (linhas com col_base preenchido)
      - fundo_marketing (valor da linha "Fundo de Marketing", negativo)
      - subtotal (valor da linha sem descrição = soma operações + fundo)

    Detecta as linhas especiais por estarem SEM col_base e por terem (ou não)
    a descrição de Fundo. A linha de subtotal é a única sem col_base que NÃO é
    o fundo.
    """
    sem_base = df[df[col_base].isna()]
    com_base = df[df[col_base].notna()]

    # Identifica fundo
    fundo_mask = sem_base[col_descricao].apply(
        lambda v: _eh_linha_fundo(_s(v))
    )
    fundo_rows = sem_base[fundo_mask]
    fundo_total = None
    if len(fundo_rows) > 0:
        # Pode haver múltiplas? Soma todas por segurança.
        fundo_total = float(fundo_rows.iloc[:, :].select_dtypes(include="number").sum().sum())
        # Mais preciso: pega da coluna de valor (passada externamente)
        # Aqui não temos col_valor — vamos retornar só linhas e o caller calcula.

    return com_base, fundo_rows, sem_base[~fundo_mask]


# ── PARSER GENÉRICO ─────────────────────────────────────────────────

def _parse_po_generico(
    df: pd.DataFrame,
    *,
    tipo: str,
    tem_enabler: bool,
    col_base: str,
    col_valor: str,
    col_ref: str,
    col_descricao: str,
    extrator_linha,  # callable(row) → dict com campos da linha de operação
) -> dict:
    """
    Parser genérico aplicado pelos 4 tipos.
    Retorna dict com:
      linhas_operacao     — lista de dicts, 1 por cliente/operação
      linha_fundo         — dict ou None
      linha_subtotal      — dict ou None
      soma_operacoes      — Σ col_valor das operações
      fundo_marketing     — valor (negativo) ou 0.0
      subtotal_planilha   — valor lido da linha de subtotal ou None
      valor_a_receber     — soma_operacoes + fundo_marketing
      tem_diferenca       — True se valor_a_receber ≠ subtotal_planilha (>1c)
      observacao_calculo  — descrição da divergência ou None
      numero_po           — extraído da coluna PO
    """
    linhas_operacao = []
    soma_operacoes = 0.0
    numero_po_set = set()

    # Itera linhas com col_base preenchido = operações reais
    com_base = df[df[col_base].notna()]
    linhas_sem_ref = 0
    for _, row in com_base.iterrows():
        ref = _s(row.get(col_ref))
        # Operações sem referência são processadas mesmo assim (acontece em
        # Repasse quando o cliente foi cadastrado sem ref) — só contamos pra warning.
        if not ref:
            linhas_sem_ref += 1
        valor = _f(row.get(col_valor))
        soma_operacoes += valor or 0.0
        # Extrai número da PO da própria linha
        if "PO" in df.columns:
            n = _f(row.get("PO"))
            if n is not None:
                numero_po_set.add(int(n))
        linha = extrator_linha(row)
        linha.update({
            "tipo": tipo,
            "tem_enabler": tem_enabler,
            "referencia_aplicativo": ref,
            "valor_liquido": valor,
            "eh_linha_especial": False,
        })
        linhas_operacao.append(linha)

    # Linhas sem col_base = especiais
    sem_base = df[df[col_base].isna()]

    # Identifica linha de Fundo
    linha_fundo_dict = None
    fundo_marketing = 0.0
    fundo_mask = sem_base[col_descricao].apply(lambda v: _eh_linha_fundo(_s(v)))
    fundo_rows = sem_base[fundo_mask]
    if len(fundo_rows) > 0:
        fundo_marketing = sum((_f(v) or 0.0) for v in fundo_rows[col_valor])
        linha_fundo_dict = {
            "tipo": tipo,
            "tem_enabler": tem_enabler,
            "referencia_aplicativo": None,
            "razao_social": "Fundo de Marketing (2,5%)",
            "valor_liquido": fundo_marketing,
            "eh_linha_especial": True,
            "tipo_linha_especial": "FUNDO_MARKETING",
        }

    # Linha de subtotal = sem col_base e que NÃO é fundo
    outras = sem_base[~fundo_mask]
    linha_subtotal_dict = None
    subtotal_planilha = None
    if len(outras) > 0:
        # Pega a primeira (em geral é única)
        valor_sub = _f(outras.iloc[0].get(col_valor))
        if valor_sub is not None:
            subtotal_planilha = valor_sub
            linha_subtotal_dict = {
                "tipo": tipo,
                "tem_enabler": tem_enabler,
                "referencia_aplicativo": None,
                "razao_social": "Subtotal (a receber)",
                "valor_liquido": valor_sub,
                "eh_linha_especial": True,
                "tipo_linha_especial": "SUBTOTAL",
            }

    # Cálculo final + validação
    valor_a_receber = round(soma_operacoes + fundo_marketing, 2)

    tem_diferenca = False
    observacao = None
    if subtotal_planilha is not None:
        diff = round(abs(valor_a_receber - subtotal_planilha), 2)
        if diff > 0.01:
            tem_diferenca = True
            observacao = (
                f"Cálculo do parser (R$ {valor_a_receber:.2f}) difere do subtotal "
                f"da planilha (R$ {subtotal_planilha:.2f}) em R$ {diff:.2f}."
            )
    else:
        # Sem subtotal não tem como validar — registra mas não bloqueia
        observacao = "Planilha sem linha de subtotal — valor calculado não validado."

    numero_po = str(next(iter(numero_po_set))) if len(numero_po_set) == 1 else None
    if len(numero_po_set) > 1:
        observacao = (observacao or "") + (
            f" | Múltiplos números de PO encontrados: {sorted(numero_po_set)}."
        )
    if linhas_sem_ref > 0:
        aviso = f"{linhas_sem_ref} operação(ões) sem 'Referência do Aplicativo' (ainda processadas)."
        observacao = f"{observacao} | {aviso}" if observacao else aviso

    return {
        "linhas_operacao": linhas_operacao,
        "linha_fundo": linha_fundo_dict,
        "linha_subtotal": linha_subtotal_dict,
        "soma_operacoes": round(soma_operacoes, 2),
        "fundo_marketing_total": round(fundo_marketing, 2),
        "subtotal_planilha": subtotal_planilha,
        "valor_a_receber": valor_a_receber,
        "tem_diferenca_calculo": tem_diferenca,
        "observacao_calculo": observacao,
        "numero_po": numero_po,
    }


# ── PARSERS POR TIPO ────────────────────────────────────────────────

def _parse_comissao_ou_enabler(df: pd.DataFrame, tem_enabler: bool) -> dict:
    """COMISSAO V6 (com ou sem Enabler)."""
    col_base  = _col(df, [("eq", "faturado r$"), ("contains", "faturado")])
    col_valor = _col(df, [("eq", "comissao r$"), ("contains", "comissao")])
    col_ref   = _col(df, [("eq", "referencia do aplicativo"),
                          ("contains", "referencia do aplicativo")])
    col_desc  = _col(df, [("eq", "cliente"), ("contains", "cliente")])
    col_app   = _col(df, [("eq", "aplicativo")])
    col_nfse  = _col(df, [("eq", "nfs-e"), ("eq", "nfse")])
    col_imp   = _col(df, [("eq", "impostos r$"), ("contains", "imposto")])
    col_emis  = _col(df, [("eq", "emissao")])
    col_receb = _col(df, [("eq", "recebto."), ("contains", "recebto")])
    col_cont  = _col(df, [("eq", "contador")]) if tem_enabler else None
    col_bpo   = _col(df, [("eq", "bpo")])

    if not (col_base and col_valor and col_ref):
        raise ValueError(
            f"Colunas essenciais não encontradas. Colunas disponíveis: {list(df.columns)}"
        )

    def extrator(row):
        contador_raw = _s(row.get(col_cont)) if col_cont else None
        if contador_raw and "sem contador" in contador_raw.lower():
            contador_raw = None
        return {
            "razao_social":    _s(row.get(col_desc)) if col_desc else None,
            "plano":           _s(row.get(col_app)) if col_app else None,
            "valor_bruto":     _f(row.get(col_base)),
            "impostos":        _f(row.get(col_imp)) if col_imp else None,
            "data_ativacao":   _d(row.get(col_emis)) if col_emis else None,
            "nfse_numero":     _s(row.get(col_nfse)) if col_nfse else None,
            "nfse_data":       _d(row.get(col_receb)) if col_receb else None,
            "contador_nome":   contador_raw,
        }

    return _parse_po_generico(
        df, tipo="COMISSAO", tem_enabler=tem_enabler,
        col_base=col_base, col_valor=col_valor,
        col_ref=col_ref, col_descricao=col_desc,
        extrator_linha=extrator,
    )


def _parse_repasse(df: pd.DataFrame) -> dict:
    """REPASSE de Treinamento."""
    col_base  = _col(df, [("eq", "valor faturado"), ("contains", "valor faturado")])
    col_valor = _col(df, [("eq", "valor do repasse"), ("contains", "valor do repasse")])
    col_ref   = _col(df, [("contains", "referencia do aplicativo")])
    col_desc  = _col(df, [("eq", "razao social"), ("contains", "razao social"), ("eq", "fantasia")])
    col_fant  = _col(df, [("eq", "fantasia")])
    col_nfse  = _col(df, [("eq", "nfs-e")])
    col_imp   = _col(df, [("eq", "impostos"), ("contains", "imposto")])
    col_parc  = _col(df, [("eq", "parcela")])
    col_emis  = _col(df, [("eq", "emissao")])
    col_receb = _col(df, [("eq", "recebto."), ("contains", "recebto")])
    col_ep    = _col(df, [("contains", "aplicativo ativado por"), ("contains", "ativado por")])

    if not (col_base and col_valor and col_ref):
        raise ValueError(
            f"Colunas essenciais não encontradas. Colunas disponíveis: {list(df.columns)}"
        )

    def extrator(row):
        num, total = _parcela(row.get(col_parc)) if col_parc else (None, None)
        return {
            "razao_social":    _s(row.get(col_desc)) if col_desc else _s(row.get(col_fant)) if col_fant else None,
            "valor_bruto":     _f(row.get(col_base)),
            "impostos":        _f(row.get(col_imp)) if col_imp else None,
            "parcela_numero":  num,
            "parcela_total":   total,
            "data_ativacao":   _d(row.get(col_emis)) if col_emis else None,
            "nfse_numero":     _s(row.get(col_nfse)) if col_nfse else None,
            "nfse_data":       _d(row.get(col_receb)) if col_receb else None,
            "ep_email":        _s(row.get(col_ep)) if col_ep else None,
        }

    return _parse_po_generico(
        df, tipo="REPASSE", tem_enabler=False,
        col_base=col_base, col_valor=col_valor,
        col_ref=col_ref, col_descricao=col_desc,
        extrator_linha=extrator,
    )


def _parse_incentivo(df: pd.DataFrame) -> dict:
    """INCENTIVO / Premiação."""
    col_base  = _col(df, [("eq", "valor negociado r$"), ("contains", "valor negociado")])
    col_valor = _col(df, [("eq", "premio r$"), ("contains", "premio")])
    col_ref   = _col(df, [("contains", "referencia do aplicativo")])
    col_desc  = _col(df, [("eq", "cliente"), ("contains", "cliente")])
    col_app   = _col(df, [("eq", "aplicativo")])
    col_imp   = _col(df, [("contains", "abatimentos - impostos"),
                          ("contains", "imposto")])
    col_com_c = _col(df, [("contains", "comissao do contador"),
                          ("contains", "comissao contador")])
    col_com_f = _col(df, [("contains", "comissao da franquia"),
                          ("contains", "comissao franquia")])
    col_ativ  = _col(df, [("eq", "ativacao"), ("contains", "ativacao")])
    col_receb = _col(df, [("eq", "recebto."), ("contains", "recebto")])
    col_cont  = _col(df, [("eq", "contador")])
    col_ep    = _col(df, [("contains", "ativado por")])

    if not (col_base and col_valor and col_ref):
        raise ValueError(
            f"Colunas essenciais não encontradas. Colunas disponíveis: {list(df.columns)}"
        )

    def extrator(row):
        contador_raw = _s(row.get(col_cont)) if col_cont else None
        if contador_raw and "sem contador" in contador_raw.lower():
            contador_raw = None
        return {
            "razao_social":      _s(row.get(col_desc)) if col_desc else None,
            "plano":             _s(row.get(col_app)) if col_app else None,
            "valor_bruto":       _f(row.get(col_base)),
            "impostos":          _f(row.get(col_imp)) if col_imp else None,
            "comissao_contador": _f(row.get(col_com_c)) if col_com_c else None,
            "premio":            _f(row.get(col_valor)),
            "data_ativacao":     _d(row.get(col_ativ)) if col_ativ else None,
            "nfse_data":         _d(row.get(col_receb)) if col_receb else None,
            "contador_nome":     contador_raw,
            "ep_email":          _s(row.get(col_ep)) if col_ep else None,
        }

    return _parse_po_generico(
        df, tipo="INCENTIVO", tem_enabler=False,
        col_base=col_base, col_valor=col_valor,
        col_ref=col_ref, col_descricao=col_desc,
        extrator_linha=extrator,
    )


# ── ENTRADA PRINCIPAL ───────────────────────────────────────────────

def parse_po_arquivo(caminho: str) -> dict:
    """
    Processa um arquivo de PO.
    Retorna dict no formato:
      {
        tipo, tem_enabler, semana_ref, numero_po,
        linhas_operacao, linha_fundo, linha_subtotal,
        soma_operacoes, fundo_marketing_total,
        subtotal_planilha, valor_a_receber,
        tem_diferenca_calculo, observacao_calculo,
        total, erros
      }
    """
    nome = Path(caminho).name
    erros = []
    try:
        tipo, tem_enabler = detectar_tipo(nome)
    except ValueError as e:
        return _retorno_erro(nome, str(e))

    semana_ref = extrair_semana_ref(nome)

    try:
        df = pd.read_excel(caminho, engine="openpyxl")
        df = df.dropna(how="all")
        df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed", regex=True)]
    except Exception as e:
        return _retorno_erro(nome, f"Erro ao ler arquivo: {e}", tipo, tem_enabler, semana_ref)

    if df.empty:
        return _retorno_erro(nome, "Planilha vazia.", tipo, tem_enabler, semana_ref)

    try:
        if tipo == "COMISSAO":
            r = _parse_comissao_ou_enabler(df, tem_enabler)
        elif tipo == "REPASSE":
            r = _parse_repasse(df)
        elif tipo == "INCENTIVO":
            r = _parse_incentivo(df)
        else:
            return _retorno_erro(nome, f"Tipo desconhecido: {tipo}", tipo, tem_enabler, semana_ref)
    except Exception as e:
        return _retorno_erro(nome, f"Erro no parser: {e}", tipo, tem_enabler, semana_ref)

    return {
        "tipo": tipo,
        "tem_enabler": tem_enabler,
        "semana_ref": semana_ref,
        "numero_po": r["numero_po"],
        "linhas_operacao": r["linhas_operacao"],
        "linha_fundo": r["linha_fundo"],
        "linha_subtotal": r["linha_subtotal"],
        "soma_operacoes": r["soma_operacoes"],
        "fundo_marketing_total": r["fundo_marketing_total"],
        "subtotal_planilha": r["subtotal_planilha"],
        "valor_a_receber": r["valor_a_receber"],
        "tem_diferenca_calculo": r["tem_diferenca_calculo"],
        "observacao_calculo": r["observacao_calculo"],
        "total": len(r["linhas_operacao"]),
        "erros": erros,
    }


def _retorno_erro(nome: str, msg: str, tipo=None, tem_enabler=False, semana_ref=None) -> dict:
    return {
        "tipo": tipo, "tem_enabler": tem_enabler, "semana_ref": semana_ref,
        "numero_po": None,
        "linhas_operacao": [], "linha_fundo": None, "linha_subtotal": None,
        "soma_operacoes": 0.0, "fundo_marketing_total": 0.0,
        "subtotal_planilha": None, "valor_a_receber": 0.0,
        "tem_diferenca_calculo": False, "observacao_calculo": None,
        "total": 0, "erros": [msg],
    }
