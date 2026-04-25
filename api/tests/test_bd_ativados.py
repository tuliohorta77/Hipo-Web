"""
Testes do parser BD Ativados — valida a regra do MRR contra cenários conhecidos.

Regra implementada (validada contra planilha oficial de produção — match 100%):

    mrr_bruto_linha =
        - 0 se Situação != ACTIVE
        - (Valor Mensal atual no contrato) / N se Tipo == 'BPO'
            onde N = nº de linhas com mesmo Tipo+Situação+CNPJ
        - (Valor Mensal atual no contrato) caso contrário
"""
import io
import os
import tempfile
import pytest
import pandas as pd

from parsers.bd_ativados import parse_bd_ativados_arquivo


def _build_xlsx(rows: list[dict]) -> str:
    """Constrói um XLSX no formato Omie (2 linhas de título + header) e retorna o caminho."""
    columns = [
        "Aplicativo", "Tipo", "Data de Ativação",
        "Situação em 24/04/2026 às 23:42:49", "Último Acesso",
        "Data do Cancelamento", "Contador", "Enquadramento Fiscal informado",
        "Valor Mensal - informado na ativação", "Valor Mensal - atual no contrato",
        "Tipo do Faturamento", "Dia do Faturamento", "Vencimento",
        "Certificado Concedido", "Com Treinamento On-line",
        "Razão Social", "CNPJ", "Referência do Aplicativo",
    ]

    titulo = pd.DataFrame([["Planilha de Clientes Ativados"] + [None] * (len(columns) - 1)])
    emitido = pd.DataFrame(
        [["Emitido por Integração em 24/04/2026 23:42"] + [None] * (len(columns) - 1)]
    )
    header = pd.DataFrame([columns])
    body = pd.DataFrame([[r.get(c) for c in columns] for r in rows])

    full = pd.concat([titulo, emitido, header, body], ignore_index=True)

    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        full.to_excel(w, index=False, header=False)
    return path


def _ref(i: int) -> str:
    """Gera uma referência de aplicativo única (campo obrigatório no parser)."""
    return f"APP_TESTE_{i:05d}"


# ─── Testes ─────────────────────────────────────────────────────────


class TestRegraMRR:
    def test_omie_completo_pega_valor_atual_direto(self):
        """Tipo != BPO usa valor_atual sem dividir."""
        path = _build_xlsx([{
            "Referência do Aplicativo": _ref(1),
            "Aplicativo": "Empresa A",
            "Tipo": "Omie completo",
            "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
            "CNPJ": "11.111.111/0001-11",
            "Valor Mensal - atual no contrato": 500.00,
            "Razão Social": "EMPRESA A LTDA",
        }])
        try:
            r = parse_bd_ativados_arquivo(path)
        finally:
            os.unlink(path)

        assert r["erros"] == []
        assert r["linhas_ativas"] == 1
        assert r["mrr_bruto"] == 500.00

    def test_bpo_divide_pelo_numero_de_linhas_ativas_do_mesmo_cnpj(self):
        """13 linhas BPO ACTIVE com val_atual=2676,86 → soma agregada == val_atual (não infla)."""
        path = _build_xlsx([
            {
                "Referência do Aplicativo": _ref(i),
                "Aplicativo": f"App {i}",
                "Tipo": "BPO",
                "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
                "CNPJ": "53.274.508/0001-44",
                "Valor Mensal - atual no contrato": 2676.86,
                "Razão Social": "ALINE LTDA",
            }
            for i in range(13)
        ])
        try:
            r = parse_bd_ativados_arquivo(path)
        finally:
            os.unlink(path)

        assert r["linhas_ativas"] == 13
        # Soma deve fechar com val_atual original (não inflar) — exatamente o bug que motivou a correção
        assert r["mrr_bruto"] == 2676.86

    def test_bpo_archived_nao_entra_na_contagem_nem_no_mrr(self):
        """Linhas BPO ARCHIVED do mesmo CNPJ não inflam contagem nem entram no MRR."""
        rows = [
            # 2 ACTIVE — devem dividir val_atual por 2 (não por 7)
            {
                "Referência do Aplicativo": _ref(1),
                "Aplicativo": "A", "Tipo": "BPO",
                "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
                "CNPJ": "X", "Valor Mensal - atual no contrato": 1000.00,
                "Razão Social": "Z",
            },
            {
                "Referência do Aplicativo": _ref(2),
                "Aplicativo": "B", "Tipo": "BPO",
                "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
                "CNPJ": "X", "Valor Mensal - atual no contrato": 1000.00,
                "Razão Social": "Z",
            },
        ]
        # 5 ARCHIVED — ignoradas
        for i in range(5):
            rows.append({
                "Referência do Aplicativo": _ref(10 + i),
                "Aplicativo": f"C{i}", "Tipo": "BPO",
                "Situação em 24/04/2026 às 23:42:49": "ARCHIVED",
                "CNPJ": "X", "Valor Mensal - atual no contrato": 1000.00,
                "Razão Social": "Z",
            })

        path = _build_xlsx(rows)
        try:
            r = parse_bd_ativados_arquivo(path)
        finally:
            os.unlink(path)

        assert r["linhas_ativas"] == 2
        # Soma das ACTIVE: 500 + 500 = 1000 (val_atual / 2)
        assert r["mrr_bruto"] == 1000.00

    def test_situacao_diferente_de_active_resulta_em_mrr_zero(self):
        path = _build_xlsx([
            {
                "Referência do Aplicativo": _ref(1),
                "Aplicativo": "A", "Tipo": "Omie completo",
                "Situação em 24/04/2026 às 23:42:49": "CANCELLED",
                "CNPJ": "X", "Valor Mensal - atual no contrato": 999.00,
                "Razão Social": "Z",
            },
            {
                "Referência do Aplicativo": _ref(2),
                "Aplicativo": "B", "Tipo": "Omie completo",
                "Situação em 24/04/2026 às 23:42:49": "PENDING",
                "CNPJ": "Y", "Valor Mensal - atual no contrato": 999.00,
                "Razão Social": "Z",
            },
        ])
        try:
            r = parse_bd_ativados_arquivo(path)
        finally:
            os.unlink(path)

        assert r["linhas_ativas"] == 0
        assert r["mrr_bruto"] == 0
        assert r["repasse_franqueado"] == 0
        assert r["liquido_pos_mkt"] == 0


class TestAgregados:
    def test_calculo_repasse_e_liquido_a_partir_do_bruto(self):
        path = _build_xlsx([{
            "Referência do Aplicativo": _ref(1),
            "Aplicativo": "A", "Tipo": "Omie completo",
            "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
            "CNPJ": "X", "Valor Mensal - atual no contrato": 1000.00,
            "Razão Social": "Z",
        }])
        try:
            r = parse_bd_ativados_arquivo(path)
        finally:
            os.unlink(path)

        # 1000 * 0,3051 = 305,10
        assert r["mrr_bruto"] == 1000.00
        assert r["repasse_franqueado"] == 305.10
        # 305,10 * 0,975 = 297,4725 → 297,47
        assert r["liquido_pos_mkt"] == 297.47

    def test_data_emissao_extraida_do_titulo(self):
        path = _build_xlsx([{
            "Referência do Aplicativo": _ref(1),
            "Aplicativo": "A", "Tipo": "Omie completo",
            "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
            "CNPJ": "X", "Valor Mensal - atual no contrato": 100.00,
            "Razão Social": "Z",
        }])
        try:
            r = parse_bd_ativados_arquivo(path)
        finally:
            os.unlink(path)

        assert r["data_emissao"] == "24/04/2026 23:42"


class TestEstrutura:
    def test_retorno_contem_campos_esperados(self):
        path = _build_xlsx([{
            "Referência do Aplicativo": _ref(1),
            "Aplicativo": "A", "Tipo": "Omie completo",
            "Situação em 24/04/2026 às 23:42:49": "ACTIVE",
            "CNPJ": "X", "Valor Mensal - atual no contrato": 100.00,
            "Razão Social": "Z",
        }])
        try:
            r = parse_bd_ativados_arquivo(path)
        finally:
            os.unlink(path)

        # Campos do retorno
        assert set(r.keys()) >= {
            "linhas", "total", "linhas_ativas",
            "mrr_bruto", "repasse_franqueado", "liquido_pos_mkt",
            "data_emissao", "erros",
        }
        # Campos novos por linha
        assert "tipo" in r["linhas"][0]
        assert "mrr_bruto" in r["linhas"][0]
        assert "valor_mensal_informado" in r["linhas"][0]