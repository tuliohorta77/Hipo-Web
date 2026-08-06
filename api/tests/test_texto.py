"""
HIPO — Testes da normalização de texto das listas de domínio.

O slug é a chave de deduplicação das listas criadas livremente pelos usuários.
Se ele deixar passar variação de caixa, acento ou espaço, o banco acumula
"Metalúrgica", "metalurgica" e "Metalurgica " como três verticais distintas.
"""
import pytest

from services.texto import limpar_nome, slugify


class TestSlugify:
    @pytest.mark.parametrize("entrada", [
        "Metalúrgica",
        "metalurgica",
        "METALÚRGICA",
        "  Metalúrgica  ",
        "Metalúrgica.",
    ])
    def test_variacoes_geram_o_mesmo_slug(self, entrada):
        assert slugify(entrada) == "metalurgica"

    def test_espacos_internos_viram_hifen_unico(self):
        assert slugify("Metalúrgica   Pesada") == "metalurgica-pesada"

    def test_pontuacao_vira_separador(self):
        assert slugify("Construção Civil / Obras") == "construcao-civil-obras"

    def test_nao_deixa_hifen_nas_pontas(self):
        assert slugify("  / Saúde /  ") == "saude"

    def test_cedilha_e_til(self):
        assert slugify("Alimentação e Serviços") == "alimentacao-e-servicos"

    def test_numeros_sao_preservados(self):
        assert slugify("Setor 4.0") == "setor-4-0"

    def test_vazio(self):
        assert slugify("") == ""

    def test_none(self):
        assert slugify(None) == ""

    def test_so_pontuacao_vira_vazio(self):
        """O router usa isso para recusar nomes sem nenhum caractere útil."""
        assert slugify("///") == ""
        assert slugify("   ") == ""


class TestLimparNome:
    def test_colapsa_espacos_e_apara_pontas(self):
        assert limpar_nome("  Metalúrgica   Pesada ") == "Metalúrgica Pesada"

    def test_preserva_acento_e_caixa(self):
        assert limpar_nome("Construção CIVIL") == "Construção CIVIL"

    def test_vazio(self):
        assert limpar_nome("") == ""

    def test_none(self):
        assert limpar_nome(None) == ""
