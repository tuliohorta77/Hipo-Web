"""
HIPO — Testes do validador de CNPJ.

Funções puras: rodam no Windows sem Postgres.
"""
import pytest

from services.cnpj import formatar, normalizar, valido


# CNPJs reais de empresas públicas — servem de âncora contra uma
# implementação que "passa nos próprios exemplos" mas erra no mundo real.
CNPJS_VALIDOS = [
    "11.222.333/0001-81",
    "34.028.316/0001-03",   # Correios
    "47.960.950/0001-21",   # Magazine Luiza
    "33.000.167/0001-01",   # Petrobras
    "60.746.948/0001-12",   # Bradesco
]


class TestNormalizar:
    def test_remove_pontuacao(self):
        assert normalizar("11.222.333/0001-81") == "11222333000181"

    def test_ja_normalizado_nao_muda(self):
        assert normalizar("11222333000181") == "11222333000181"

    def test_none_vira_string_vazia(self):
        assert normalizar(None) == ""

    def test_vazio_vira_string_vazia(self):
        assert normalizar("") == ""

    def test_remove_espacos_e_letras(self):
        assert normalizar(" 11 222 333/0001-81 ") == "11222333000181"


class TestValido:
    @pytest.mark.parametrize("cnpj", CNPJS_VALIDOS)
    def test_cnpjs_reais_sao_validos(self, cnpj):
        assert valido(cnpj)

    @pytest.mark.parametrize("cnpj", CNPJS_VALIDOS)
    def test_aceita_sem_pontuacao(self, cnpj):
        assert valido(normalizar(cnpj))

    def test_digito_verificador_errado(self):
        assert not valido("11222333000182")

    def test_penultimo_digito_errado(self):
        assert not valido("11222333000171")

    @pytest.mark.parametrize("cnpj", [str(d) * 14 for d in range(10)])
    def test_digitos_repetidos_sao_invalidos(self, cnpj):
        """Passam no cálculo do DV mas não existem — precisam ser barrados."""
        assert not valido(cnpj)

    def test_curto_demais(self):
        assert not valido("1122233300018")

    def test_longo_demais(self):
        assert not valido("112223330001811")

    def test_vazio(self):
        assert not valido("")

    def test_none(self):
        assert not valido(None)

    def test_so_letras(self):
        assert not valido("abcdefghijklmn")


class TestFormatar:
    def test_formata_com_pontuacao(self):
        assert formatar("11222333000181") == "11.222.333/0001-81"

    def test_entrada_ja_formatada(self):
        assert formatar("11.222.333/0001-81") == "11.222.333/0001-81"

    def test_entrada_invalida_volta_normalizada_sem_erro(self):
        """Formatar é para exibição — não é lugar de levantar exceção."""
        assert formatar("123") == "123"

    def test_none(self):
        assert formatar(None) == ""

    def test_ida_e_volta(self):
        for cnpj in CNPJS_VALIDOS:
            assert normalizar(formatar(normalizar(cnpj))) == normalizar(cnpj)
