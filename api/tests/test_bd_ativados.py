"""Testes do parser BD Ativados — valida a regra do MRR contra cenários conhecidos."""

from __future__ import annotations

import io
from decimal import Decimal

import pandas as pd
import pytest

from api.parsers.bd_ativados import (
    TAXA_LIQUIDO_POS_MKT,
    TAXA_REPASSE_FRANQUEADO,
    parse_bd_ativados,
)


def _build_xlsx(rows: list[dict]) -> bytes:
    """Constrói um XLSX com o layout da Omie (2 linhas de título + header)."""
    columns = [
        "Aplicativo", "Tipo", "Data de Ativação",
        "Situação em 24/04/2026 às 23:42:49", "Último Acesso",
        "Data do Cancelamento", "Contador", "Enquadramento Fiscal informado",
        "Valor Mensal - informado na ativação", "Valor Mensal - atual no contrato",
        "Tipo do Faturamento", "Dia do Faturamento", "Vencimento",
        "Certificado Concedido", "Com Treinamento On-line",
        "Razão Social", "CNPJ",
    ]

    titulo = pd.DataFrame([["Planilha de Clientes Ativados"] + [None] * (len(columns) - 1)])
    emitido = pd.DataFrame(
        [["Emitido por Integração em 24/04/2026 23:42"] + [None] * (len(columns) - 1)]
    )
    header = pd.DataFrame([columns])
    body = pd.DataFrame([[r.get(c) for c in columns] for r in rows])

    full = pd.concat([titulo, emitido, header, body], ignore_index=True)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        full.to_excel(w, index=False, header=False)
    return buf.getvalue()


def test_omie_completo_pega_valor_atual_direto():
    """Tipo != BPO usa val_atual sem dividir."""
    raw = _build_xlsx([
        {
            "Aplicativo": "Empresa A", "Tipo": "Omie completo",
            "Situação em 24/04/2026 às 23:42:49": "ACTIVE", "CNPJ": "11.111/0001-11",
            "Valor Mensal - atual no contrato": 500.00,
            "Valor Mensal - informado na ativação": 500.00,
            "Razão Social": "EMPRESA A LTDA",
        },
    ])
    r = parse_bd_ativados(raw)
    assert r.linhas_ativas == 1
    assert r.mrr_bruto == Decimal("500.00")


def test_bpo_divide_pelo_numero_de_linhas_ativas_do_mesmo_cnpj():
    """13 linhas BPO ACTIVE do mesmo CNPJ com val_atual=2676,86 → cada linha 205,91."""
    rows = [
        {
            "Aplicativo": f"App {i}", "Tipo": "BPO",
            "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
            "CNPJ": "53.274.508/0001-44",
            "Valor Mensal - atual no contrato": 2676.86,
            "Razão Social": "ALINE LTDA",
        }
        for i in range(13)
    ]
    r = parse_bd_ativados(_build_xlsx(rows))
    assert r.linhas_ativas == 13
    # Soma deve fechar com o val_atual (não inflar)
    assert r.mrr_bruto == Decimal("2676.86")
    # Cada linha vira val_atual/13
    for l in r.linhas:
        assert l["qtd_linhas_grupo"] == 13
        assert l["mrr_bruto"] == (Decimal("2676.86") / Decimal(13)).quantize(Decimal("0.01"))


def test_bpo_archived_nao_entra_na_contagem_nem_no_mrr():
    """Linhas BPO ARCHIVED do mesmo CNPJ não inflam contagem nem entram no MRR."""
    rows = [
        # 2 ACTIVE — devem dividir val_atual por 2
        {"Aplicativo": "A", "Tipo": "BPO",
         "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
         "CNPJ": "X", "Valor Mensal - atual no contrato": 1000.00,
         "Razão Social": "Z"},
        {"Aplicativo": "B", "Tipo": "BPO",
         "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
         "CNPJ": "X", "Valor Mensal - atual no contrato": 1000.00,
         "Razão Social": "Z"},
        # 5 ARCHIVED — ignoradas
        *[
            {"Aplicativo": f"C{i}", "Tipo": "BPO",
             "Situação em 24/04/2026 às 23:42:49": "ARCHIVED",
             "CNPJ": "X", "Valor Mensal - atual no contrato": 1000.00,
             "Razão Social": "Z"}
            for i in range(5)
        ],
    ]
    r = parse_bd_ativados(_build_xlsx(rows))
    assert r.linhas_ativas == 2
    # Soma das ACTIVE: 500 + 500 = 1000
    assert r.mrr_bruto == Decimal("1000.00")


def test_situacao_diferente_de_active_resulta_em_mrr_zero():
    rows = [
        {"Aplicativo": "A", "Tipo": "Omie completo",
         "Situação em 24/04/2026 às 23:42:49": "CANCELLED",
         "CNPJ": "X", "Valor Mensal - atual no contrato": 999.00,
         "Razão Social": "Z"},
        {"Aplicativo": "B", "Tipo": "Omie completo",
         "Situação em 24/04/2026 às 23:42:49": "PENDING",
         "CNPJ": "Y", "Valor Mensal - atual no contrato": 999.00,
         "Razão Social": "Z"},
    ]
    r = parse_bd_ativados(_build_xlsx(rows))
    assert r.linhas_ativas == 0
    assert r.mrr_bruto == Decimal("0")
    assert r.repasse_franqueado == Decimal("0")
    assert r.liquido_pos_mkt == Decimal("0")


def test_calculo_repasse_e_liquido():
    rows = [
        {"Aplicativo": "A", "Tipo": "Omie completo",
         "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
         "CNPJ": "X", "Valor Mensal - atual no contrato": 1000.00,
         "Razão Social": "Z"},
    ]
    r = parse_bd_ativados(_build_xlsx(rows))
    assert r.mrr_bruto == Decimal("1000.00")
    # 1000 * 0,3051 = 305,10
    assert r.repasse_franqueado == (Decimal("1000.00") * TAXA_REPASSE_FRANQUEADO).quantize(Decimal("0.01"))
    # 305,10 * 0,975 = 297,47
    expected_liq = (
        (Decimal("1000.00") * TAXA_REPASSE_FRANQUEADO).quantize(Decimal("0.01"))
        * TAXA_LIQUIDO_POS_MKT
    ).quantize(Decimal("0.01"))
    assert r.liquido_pos_mkt == expected_liq


def test_planilha_invalida_levanta_keyerror():
    # XLSX sem as colunas esperadas
    df = pd.DataFrame([{"foo": 1, "bar": 2}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    with pytest.raises((KeyError, Exception)):
        parse_bd_ativados(buf.getvalue())


def test_data_emissao_extraida_do_titulo():
    raw = _build_xlsx([
        {"Aplicativo": "A", "Tipo": "Omie completo",
         "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
         "CNPJ": "X", "Valor Mensal - atual no contrato": 100.00,
         "Razão Social": "Z"},
    ])
    r = parse_bd_ativados(raw)
    assert r.data_emissao == "24/04/2026 23:42"
