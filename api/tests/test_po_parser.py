"""
Testes do parser de POs (v2).
Reescrito para usar as colunas reais das planilhas da Omie identificadas após
análise das 4 planilhas de produção: Comissão V6, Comissão V6 Enabler,
Repasse de Treinamento e Incentivo.
"""
import pytest
import pandas as pd
from parsers.po_parser import (
    detectar_tipo,
    parse_po_arquivo,
    _parcela,
    _extrair_parcela,  # alias retrocompatível
)


# ── DETECÇÃO DE TIPO ────────────────────────────────────────────────

class TestDetectarTipo:
    def test_comissao_v6(self):
        tipo, enabler = detectar_tipo("Omie_Apuracao_ComissaoV6_2026_4_Abril.xlsx")
        assert tipo == "COMISSAO"
        assert enabler is False

    def test_enabler(self):
        tipo, enabler = detectar_tipo("Omie_Apuracao_ComissaoV6Enabler_2026_4_Abril.xlsx")
        assert tipo == "COMISSAO"
        assert enabler is True

    def test_incentivo(self):
        tipo, enabler = detectar_tipo("Omie_Apuracao_Incentivo_2026_4_Abril.xlsx")
        assert tipo == "INCENTIVO"
        assert enabler is False

    def test_repasse(self):
        tipo, enabler = detectar_tipo("Omie_Apuracao_Repasse_2026_4_Abril.xlsx")
        assert tipo == "REPASSE"
        assert enabler is False

    def test_nome_desconhecido_lanca_erro(self):
        with pytest.raises(ValueError):
            detectar_tipo("arquivo_desconhecido.xlsx")

    def test_case_insensitive(self):
        tipo, enabler = detectar_tipo("omie_apuracao_comissaov6_2026_4_abril.xlsx")
        assert tipo == "COMISSAO"


# ── EXTRAÇÃO DE PARCELA ─────────────────────────────────────────────

class TestExtrairParcela:
    def test_formato_x_barra_y(self):
        num, total = _parcela("2/5")
        assert num == 2
        assert total == 5

    def test_formato_com_espacos(self):
        num, total = _parcela("3 / 6")
        assert num == 3
        assert total == 6

    def test_formato_zero_padded(self):
        # Como vem nas planilhas reais: '004/010'
        num, total = _parcela("004/010")
        assert num == 4
        assert total == 10

    def test_valor_nulo(self):
        num, total = _parcela(None)
        assert num is None
        assert total is None

    def test_texto_sem_parcela(self):
        num, total = _parcela("sem parcela")
        assert num is None
        assert total is None

    def test_alias_retrocompativel(self):
        # _extrair_parcela é alias mantido para código antigo
        assert _extrair_parcela == _parcela


# ── PARSER COM PLANILHAS NO FORMATO REAL DA OMIE ────────────────────

def _criar_planilha_comissao(caminho, linhas, fundo=None, subtotal=None, com_enabler=False):
    """Monta uma planilha COMISSAO V6 (com ou sem Enabler) com as colunas reais."""
    rows = []
    for l in linhas:
        row = {
            "Aplicativo": l.get("aplicativo", "Teste App"),
            "Cliente": l["cliente"],
            "NFS-e": l.get("nfse", "1234567"),
            "Recebto.": l.get("recebto"),
            "Faturado R$": l["faturado"],
            "Impostos R$": l.get("impostos", round(l["faturado"] * 0.0755, 2)),
            "Comissão R$": l["comissao"],
            "Emissão": l.get("emissao"),
            "Referência do Aplicativo": l["ref"],
            "PO": l.get("po", 1500000000),
            "BPO": l.get("bpo", "Não"),
        }
        if com_enabler:
            row["Contador"] = l.get("contador", "* Sem Contador")
        rows.append(row)
    if fundo is not None:
        rows.append({
            "Cliente": "Fundo de Marketing (2,5%)",
            "Comissão R$": fundo,
            "PO": linhas[0].get("po", 1500000000),
        })
    if subtotal is not None:
        rows.append({"Comissão R$": subtotal})
    pd.DataFrame(rows).to_excel(caminho, index=False)


def _criar_planilha_repasse(caminho, linhas, fundo=None, subtotal=None):
    """Monta uma planilha REPASSE com as colunas reais da Omie."""
    rows = []
    for l in linhas:
        rows.append({
            "Razão Social": l["razao"],
            "Fantasia": l.get("fantasia", l["razao"]),
            "NFS-e": l.get("nfse", "1234567"),
            "Parcela": l.get("parcela"),
            "Emissão": l.get("emissao"),
            "Recebto.": l.get("recebto"),
            "Valor Faturado": l["faturado"],
            "Impostos": l.get("impostos", round(l["faturado"] * 0.029, 2)),
            "Valor do Repasse": l["repasse"],
            "Aplicativo Ativado Por": l.get("ativado_por"),
            "Referência do Aplicativo": l.get("ref"),
            "PO": l.get("po", 1500000000),
        })
    if fundo is not None:
        rows.append({"Razão Social": "Fundo de Marketing (2,5%)", "Valor do Repasse": fundo})
    if subtotal is not None:
        rows.append({"Valor do Repasse": subtotal})
    pd.DataFrame(rows).to_excel(caminho, index=False)


def _criar_planilha_incentivo(caminho, linhas, fundo=None, subtotal=None):
    """Monta uma planilha INCENTIVO com as colunas reais da Omie."""
    rows = []
    for l in linhas:
        rows.append({
            "Contador": l.get("contador", "* Sem Contador"),
            "Aplicativo": l.get("aplicativo", "Teste App"),
            "Cliente": l["cliente"],
            "Ativação": l.get("ativacao"),
            "Recebto.": l.get("recebto"),
            "Valor Negociado R$": l["negociado"],
            "Abatimentos - Impostos R$": l.get("impostos", round(l["negociado"] * 0.0755, 2)),
            "Abatimentos - Comissão do Contador R$": l.get("com_contador", 0),
            "Abatimentos - Comissão da Franquia R$": l.get("com_franquia", 0),
            "Prêmio R$": l["premio"],
            "Ativado Por": l.get("ativado_por"),
            "Referência do Aplicativo": l["ref"],
            "PO": l.get("po", 1500000000),
        })
    if fundo is not None:
        rows.append({"Cliente": "Fundo de Marketing (2,5%)", "Prêmio R$": fundo})
    if subtotal is not None:
        rows.append({"Prêmio R$": subtotal})
    pd.DataFrame(rows).to_excel(caminho, index=False)


class TestParseComissao:
    def test_parse_basico(self, tmp_path):
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_comissao(arq, linhas=[
            {"ref": "app1", "cliente": "Empresa A", "faturado": 1000.0, "comissao": 300.0},
            {"ref": "app2", "cliente": "Empresa B", "faturado": 2000.0, "comissao": 600.0},
        ], fundo=-22.5, subtotal=877.5)

        r = parse_po_arquivo(arq)
        assert r["tipo"] == "COMISSAO"
        assert r["tem_enabler"] is False
        assert r["total"] == 2
        assert r["erros"] == []
        assert r["linhas"][0]["referencia_aplicativo"] == "app1"
        assert r["linhas"][0]["valor_liquido"] == 300.0
        assert r["linhas"][0]["razao_social"] == "Empresa A"

    def test_calculo_valor_a_receber(self, tmp_path):
        """Valida o cálculo central: valor_a_receber = soma_operacoes + fundo."""
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_comissao(arq, linhas=[
            {"ref": "a", "cliente": "X", "faturado": 1000.0, "comissao": 100.0},
            {"ref": "b", "cliente": "Y", "faturado": 2000.0, "comissao": 200.0},
        ], fundo=-7.5, subtotal=292.5)

        r = parse_po_arquivo(arq)
        assert r["soma_operacoes"] == 300.0
        assert r["fundo_marketing_total"] == -7.5
        assert r["valor_a_receber"] == 292.5
        assert r["tem_diferenca_calculo"] is False

    def test_marca_diferenca_quando_subtotal_nao_bate(self, tmp_path):
        """Subtotal mentiroso na planilha → tem_diferenca_calculo = True."""
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_comissao(arq, linhas=[
            {"ref": "a", "cliente": "X", "faturado": 1000.0, "comissao": 100.0},
        ], fundo=-2.5, subtotal=999.0)  # Subtotal MENTIROSO; correto seria 97.5

        r = parse_po_arquivo(arq)
        assert r["valor_a_receber"] == 97.5
        assert r["subtotal_planilha"] == 999.0
        assert r["tem_diferenca_calculo"] is True
        assert r["observacao_calculo"] is not None
        assert "97.5" in r["observacao_calculo"]
        assert "999" in r["observacao_calculo"]

    def test_enabler_com_contador(self, tmp_path):
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6Enabler_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_comissao(arq, com_enabler=True, linhas=[
            {"ref": "a", "cliente": "X", "faturado": 1000, "comissao": 300,
             "contador": "Silva Contabilidade"},
        ], fundo=-7.5, subtotal=292.5)

        r = parse_po_arquivo(arq)
        assert r["tem_enabler"] is True
        assert r["linhas"][0]["contador_nome"] == "Silva Contabilidade"

    def test_sem_contador_vira_none(self, tmp_path):
        """'* Sem Contador' deve virar None, não ser salvo como nome."""
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6Enabler_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_comissao(arq, com_enabler=True, linhas=[
            {"ref": "a", "cliente": "X", "faturado": 1000, "comissao": 300},
        ], fundo=-7.5, subtotal=292.5)

        r = parse_po_arquivo(arq)
        assert r["linhas"][0]["contador_nome"] is None

    def test_extrai_numero_po(self, tmp_path):
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_comissao(arq, linhas=[
            {"ref": "a", "cliente": "X", "faturado": 1000, "comissao": 100, "po": 1503521804},
            {"ref": "b", "cliente": "Y", "faturado": 2000, "comissao": 200, "po": 1503521804},
        ], fundo=-7.5, subtotal=292.5)

        r = parse_po_arquivo(arq)
        assert r["numero_po"] == "1503521804"

    def test_semana_ref_extraida_do_nome(self, tmp_path):
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_999.xlsx")
        _criar_planilha_comissao(arq, linhas=[
            {"ref": "a", "cliente": "X", "faturado": 1000, "comissao": 100},
        ])
        r = parse_po_arquivo(arq)
        assert r["semana_ref"] is not None
        assert r["semana_ref"].year == 2026
        assert r["semana_ref"].month == 4


class TestParseRepasse:
    def test_parse_com_parcela(self, tmp_path):
        arq = str(tmp_path / "Omie_Apuracao_Repasse_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_repasse(arq, linhas=[
            {"ref": "app1", "razao": "Cliente XYZ", "faturado": 500.0, "repasse": 340.0,
             "parcela": "2/5", "ativado_por": "vendedor@omie.com.vc"},
        ], fundo=-8.5, subtotal=331.5)

        r = parse_po_arquivo(arq)
        assert r["tipo"] == "REPASSE"
        assert r["linhas"][0]["parcela_numero"] == 2
        assert r["linhas"][0]["parcela_total"] == 5
        assert r["linhas"][0]["ep_email"] == "vendedor@omie.com.vc"

    def test_aceita_linhas_sem_referencia(self, tmp_path):
        """No Repasse real, algumas linhas vêm sem 'Referência do Aplicativo'.
        Devem ser processadas mesmo assim, com aviso."""
        arq = str(tmp_path / "Omie_Apuracao_Repasse_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_repasse(arq, linhas=[
            {"ref": "app1", "razao": "OK", "faturado": 100.0, "repasse": 70.0},
            {"ref": None,    "razao": "SEM_REF", "faturado": 200.0, "repasse": 140.0},
        ], fundo=-5.25, subtotal=204.75)

        r = parse_po_arquivo(arq)
        assert r["total"] == 2  # processou ambas
        assert r["soma_operacoes"] == 210.0
        assert r["observacao_calculo"] is not None
        assert "sem 'Referência" in r["observacao_calculo"]


class TestParseIncentivo:
    def test_parse_basico(self, tmp_path):
        arq = str(tmp_path / "Omie_Apuracao_Incentivo_2026_4_Abril_1500000000.xlsx")
        _criar_planilha_incentivo(arq, linhas=[
            {"ref": "app1", "cliente": "X", "negociado": 500.0, "premio": 250.0,
             "contador": "Contadora XPTO", "ativado_por": "vend@omie.com.vc"},
        ], fundo=-6.25, subtotal=243.75)

        r = parse_po_arquivo(arq)
        assert r["tipo"] == "INCENTIVO"
        assert r["linhas"][0]["premio"] == 250.0
        assert r["linhas"][0]["contador_nome"] == "Contadora XPTO"
        assert r["linhas"][0]["ep_email"] == "vend@omie.com.vc"


class TestEdgeCases:
    def test_arquivo_com_colunas_essenciais_faltando(self, tmp_path):
        """Planilha sem 'Faturado R$' / 'Comissão R$' → erro registrado, sem crash."""
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_1500000000.xlsx")
        pd.DataFrame([{"foo": "bar"}]).to_excel(arq, index=False)
        r = parse_po_arquivo(arq)
        assert r["total"] == 0
        assert len(r["erros"]) > 0

    def test_arquivo_vazio(self, tmp_path):
        arq = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_1500000000.xlsx")
        pd.DataFrame().to_excel(arq, index=False)
        r = parse_po_arquivo(arq)
        assert r["linhas"] == []
        assert r["total"] == 0