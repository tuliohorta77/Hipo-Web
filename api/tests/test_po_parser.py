"""
Testes do parser de POs.
Testa detecção de tipo, parsing de cada formato e casos de borda.
"""
import io
import pytest
import pandas as pd
from parsers.po_parser import detectar_tipo, parse_po_arquivo, _extrair_parcela


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


class TestExtairParcela:
    def test_formato_x_barra_y(self):
        num, total = _extrair_parcela("2/5")
        assert num == 2
        assert total == 5

    def test_formato_com_espacos(self):
        num, total = _extrair_parcela("3 / 6")
        assert num == 3
        assert total == 6

    def test_valor_nulo(self):
        num, total = _extrair_parcela(None)
        assert num is None
        assert total is None

    def test_texto_sem_parcela(self):
        num, total = _extrair_parcela("sem parcela")
        assert num is None
        assert total is None


class TestParseComissao:
    def _criar_xlsx(self, dados: list[dict], caminho: str):
        df = pd.DataFrame(dados)
        df.to_excel(caminho, index=False)

    def test_parse_comissao_basico(self, tmp_path):
        caminho = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx")
        self._criar_xlsx([{
            "Referência Aplicativo": "APP001",
            "Razão Social": "Empresa Teste Ltda",
            "CNPJ": "12.345.678/0001-90",
            "Plano": "Omie ERP",
            "Valor Bruto": 2000.00,
            "Valor Líquido": 1800.00,
            "Impostos": 200.00,
        }], caminho)

        resultado = parse_po_arquivo(caminho)
        assert resultado["tipo"] == "COMISSAO"
        assert resultado["tem_enabler"] is False
        assert resultado["total"] == 1
        assert resultado["erros"] == []
        linha = resultado["linhas"][0]
        assert linha["referencia_aplicativo"] == "APP001"
        assert linha["valor_liquido"] == 1800.0
        assert linha["razao_social"] == "Empresa Teste Ltda"

    def test_parse_enabler_com_contador(self, tmp_path):
        caminho = str(tmp_path / "Omie_Apuracao_ComissaoV6Enabler_2026_4_Abril_test.xlsx")
        self._criar_xlsx([{
            "Referência Aplicativo": "APP002",
            "Razão Social": "Comércio ABC",
            "CNPJ": "98.765.432/0001-11",
            "Valor Líquido": 950.00,
            "Contador": "Escritório Silva Contabilidade",
            "CNPJ Contador": "11.222.333/0001-44",
            "Comissão Contador": 95.00,
        }], caminho)

        resultado = parse_po_arquivo(caminho)
        assert resultado["tem_enabler"] is True
        linha = resultado["linhas"][0]
        assert linha["contador_nome"] == "Escritório Silva Contabilidade"
        assert linha["comissao_contador"] == 95.0

    def test_parse_repasse_com_parcela(self, tmp_path):
        caminho = str(tmp_path / "Omie_Apuracao_Repasse_2026_4_Abril_test.xlsx")
        self._criar_xlsx([{
            "Referência Aplicativo": "APP003",
            "Razão Social": "Serviços XYZ",
            "Parcela": "2/5",
            "Valor": 375.00,
            "Ativado Por": "ep.silva@omie.com.vc",
        }], caminho)

        resultado = parse_po_arquivo(caminho)
        assert resultado["tipo"] == "REPASSE"
        linha = resultado["linhas"][0]
        assert linha["parcela_numero"] == 2
        assert linha["parcela_total"] == 5
        assert linha["ep_email"] == "ep.silva@omie.com.vc"

    def test_arquivo_vazio_retorna_lista_vazia(self, tmp_path):
        caminho = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_vazio.xlsx")
        pd.DataFrame().to_excel(caminho, index=False)
        resultado = parse_po_arquivo(caminho)
        assert resultado["linhas"] == []
        assert resultado["total"] == 0

    def test_linha_sem_referencia_e_ignorada(self, tmp_path):
        caminho = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_sem_ref.xlsx")
        self._criar_xlsx([
            {"Referência Aplicativo": "APP001", "Valor Líquido": 100},
            {"Referência Aplicativo": None, "Valor Líquido": 200},  # deve ser ignorada
            {"Referência Aplicativo": "APP003", "Valor Líquido": 300},
        ], caminho)
        resultado = parse_po_arquivo(caminho)
        assert resultado["total"] == 2

    def test_semana_ref_extraida_do_nome(self, tmp_path):
        caminho = str(tmp_path / "Omie_Apuracao_ComissaoV6_2026_4_Abril_123.xlsx")
        pd.DataFrame([{"Referência Aplicativo": "X", "Valor Líquido": 1}]).to_excel(caminho, index=False)
        resultado = parse_po_arquivo(caminho)
        assert resultado["semana_ref"] is not None
        assert resultado["semana_ref"].year == 2026
        assert resultado["semana_ref"].month == 4
