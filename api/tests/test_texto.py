"""
HIPO — Testes da normalização de texto das listas de domínio.

O slug é a chave de deduplicação das listas criadas livremente pelos usuários.
Se ele deixar passar variação de caixa, acento ou espaço, o banco acumula
"Metalúrgica", "metalurgica" e "Metalurgica " como três verticais distintas.
"""
import pytest

from services.texto import (
    email_unico_valido, limpar_nome, normalizar_emails, separar_emails, slugify,
)


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


class TestSepararEmails:
    @pytest.mark.parametrize("entrada", [
        "a@x.com; b@y.com",
        "a@x.com,b@y.com",
        "a@x.com , b@y.com",
        "a@x.com b@y.com",
        "a@x.com;\nb@y.com;",
    ])
    def test_separadores(self, entrada):
        assert separar_emails(entrada) == ["a@x.com", "b@y.com"]

    def test_repetido_por_caixa_sai(self):
        assert separar_emails("Ana@x.com; ana@X.com") == ["Ana@x.com"]

    def test_vazio(self):
        assert separar_emails("") == []
        assert separar_emails(None) == []
        assert separar_emails(" ; , ") == []


class TestNormalizarEmails:
    def test_um_endereco(self):
        assert normalizar_emails(" Maria@Empresa.COM ") == "maria@empresa.com"

    def test_dois_enderecos(self):
        assert normalizar_emails("a@x.com,B@y.com") == "a@x.com; b@y.com"

    def test_vazio_vira_none(self):
        assert normalizar_emails("") is None
        assert normalizar_emails(None) is None
        assert normalizar_emails(" ; ") is None

    @pytest.mark.parametrize("entrada", ["invalido", "a@x.com; sem-arroba", "a@x"])
    def test_invalido_levanta(self, entrada):
        with pytest.raises(ValueError):
            normalizar_emails(entrada)

    def test_email_unico_recusa_lista(self):
        assert email_unico_valido("a@x.com")
        assert not email_unico_valido("a@x.com; b@y.com")
