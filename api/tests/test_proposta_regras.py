"""
HIPO — Regras da proposta comercial, sem banco.

Rodam no pytest local do Windows: tudo aqui é função pura. O que estes
testes seguram é o que o cliente lê no slide — número formatado errado ou
conta que não fecha viram desconto que ninguém aprovou.
"""
from datetime import date
from decimal import Decimal

import pytest

from services import proposta as regras


class TestMoeda:
    def test_formato_brasileiro(self):
        assert regras.moeda(Decimal("1000")) == "R$ 1.000,00"
        assert regras.moeda(Decimal("20")) == "R$ 20,00"
        assert regras.moeda(Decimal("4000")) == "R$ 4.000,00"

    def test_milhar_e_milhao(self):
        assert regras.moeda(Decimal("1234567.89")) == "R$ 1.234.567,89"

    def test_centavos_sempre_com_duas_casas(self):
        assert regras.moeda(Decimal("1500.5")) == "R$ 1.500,50"
        assert regras.moeda(Decimal("0.1")) == "R$ 0,10"

    def test_arredonda_meio_para_cima(self):
        assert regras.moeda(Decimal("10.005")) == "R$ 10,01"

    def test_none_vira_zero(self):
        """Campo opcional em branco não pode virar 'R$ None' no slide."""
        assert regras.moeda(None) == "R$ 0,00"

    def test_aceita_int_e_float(self):
        assert regras.moeda(20) == "R$ 20,00"
        assert regras.moeda(20.0) == "R$ 20,00"


class TestDatas:
    def test_extenso(self):
        assert regras.data_extenso(date(2026, 8, 26)) == "26 de agosto de 2026"

    def test_extenso_em_marco(self):
        """março tem cedilha e til — se o arquivo perder o encoding, quebra aqui."""
        assert regras.data_extenso(date(2026, 3, 1)) == "1 de março de 2026"

    def test_curta_com_zero_a_esquerda(self):
        assert regras.data_curta(date(2026, 9, 5)) == "05/09/2026"

    def test_validade_padrao_sao_dias_corridos(self):
        assert regras.validade_padrao(date(2026, 8, 26)) == date(2026, 9, 5)

    def test_validade_atravessa_o_mes(self):
        assert regras.validade_padrao(date(2026, 12, 28), 10) == date(2027, 1, 7)


class TestCalculo:
    def test_mensalidade_e_vidas_vezes_valor(self):
        assert regras.mensalidade(50, Decimal("20")) == Decimal("1000.00")

    def test_mensalidade_com_centavos(self):
        assert regras.mensalidade(37, Decimal("18.90")) == Decimal("699.30")

    def test_investimento_soma_as_tres_parcelas(self):
        mensal = regras.mensalidade(50, Decimal("20"))
        total = regras.investimento(mensal, Decimal("2000"), Decimal("1000"))
        assert total == Decimal("4000.00")

    def test_investimento_sem_extras(self):
        assert regras.investimento(Decimal("1000")) == Decimal("1000.00")

    def test_investimento_aceita_none_nos_extras(self):
        assert regras.investimento(Decimal("1000"), None, None) == Decimal("1000.00")


class TestValidacao:
    def _valido(self, **troca):
        base = dict(
            vidas=50, valor_por_vida=Decimal("20"),
            treinamentos=Decimal("0"), laudos=Decimal("0"),
            escopo=["PGR"], data_proposta=date(2026, 8, 26),
            validade=date(2026, 9, 5),
        )
        base.update(troca)
        return base

    def test_proposta_valida_passa(self):
        regras.validar(**self._valido())

    def test_sem_vidas(self):
        with pytest.raises(regras.PropostaInvalida, match="pelo menos 1 vida"):
            regras.validar(**self._valido(vidas=0))

    def test_valor_por_vida_zero(self):
        with pytest.raises(regras.PropostaInvalida, match="maior que zero"):
            regras.validar(**self._valido(valor_por_vida=Decimal("0")))

    def test_extra_negativo(self):
        with pytest.raises(regras.PropostaInvalida, match="negativo"):
            regras.validar(**self._valido(treinamentos=Decimal("-1")))

    def test_escopo_vazio(self):
        with pytest.raises(regras.PropostaInvalida, match="item de escopo"):
            regras.validar(**self._valido(escopo=["   ", ""]))

    def test_escopo_longo_demais_para_o_slide(self):
        """
        O quadro do escopo tem altura fixa. Vinte itens já espremem; mais do
        que isso sai por baixo da caixa e ninguém vê antes de enviar.
        """
        with pytest.raises(regras.PropostaInvalida, match="até 20 itens"):
            regras.validar(**self._valido(escopo=[f"Item {i}" for i in range(25)]))

    def test_validade_anterior_a_proposta(self):
        with pytest.raises(regras.PropostaInvalida, match="anterior"):
            regras.validar(**self._valido(validade=date(2026, 8, 25)))

    def test_validade_no_mesmo_dia_e_permitida(self):
        """Proposta que vence no dia é ruim de negócio, não erro de sistema."""
        regras.validar(**self._valido(validade=date(2026, 8, 26)))


class TestEscopo:
    def test_padrao_tem_os_seis_itens_do_modelo(self):
        assert len(regras.ESCOPO_PADRAO) == 6
        assert any("PGR" in i for i in regras.ESCOPO_PADRAO)
        assert any("eSocial" in i for i in regras.ESCOPO_PADRAO)

    def test_limpar_tira_vazios_e_espacos(self):
        assert regras.limpar_escopo(["  PGR  ", "", "   ", "LTCAT"]) == ["PGR", "LTCAT"]

    def test_limpar_preserva_a_ordem(self):
        assert regras.limpar_escopo(["C", "A", "B"]) == ["C", "A", "B"]


class TestSubstituicoes:
    def _subs(self, **troca):
        base = dict(
            cliente="SOLAR DOS PAMPAS COMERCIO ALIMENTICIO LTDA",
            vidas=50, valor_por_vida=Decimal("20"),
            treinamentos=Decimal("2000"), laudos=Decimal("1000"),
            executivo_nome="Bruno Gonçalo",
            executivo_email="bruno.goncalo@controllermedseg.com",
            executivo_telefone="+55 (11) 9 9571-3682",
            data_proposta=date(2026, 8, 26), validade=date(2026, 9, 5),
        )
        base.update(troca)
        return regras.substituicoes(**base)

    def test_reproduz_o_modelo_original(self):
        """
        Os números do .pptx que veio do marketing. Se esta linha mudar, a
        conta do slide mudou junto — e é para doer.
        """
        s = self._subs()
        assert s["{{VIDAS}}"] == "50"
        assert s["{{VALOR_VIDA}}"] == "R$ 20,00"
        assert s["{{MENSALIDADE}}"] == "R$ 1.000,00"
        assert s["{{TREINAMENTOS}}"] == "R$ 2.000,00"
        assert s["{{LAUDOS}}"] == "R$ 1.000,00"
        assert s["{{INVESTIMENTO}}"] == "R$ 4.000,00"
        assert s["{{DATA_EXTENSO}}"] == "26 de agosto de 2026"
        assert s["{{VALIDADE}}"] == "05/09/2026"
        assert s["{{CIDADE}}"] == "Guarulhos"

    def test_tudo_e_string(self):
        """python-pptx escreve texto: número solto viraria TypeError no render."""
        assert all(isinstance(v, str) for v in self._subs().values())

    def test_telefone_vazio_vira_travessao(self):
        """
        Rótulo 'Telefone:' com o lado direito em branco parece defeito de
        geração; o travessão parece o que é — o cadastro não tem o número.
        """
        assert self._subs(executivo_telefone=None)["{{EXECUTIVO_TELEFONE}}"] == "—"
        assert self._subs(executivo_telefone="   ")["{{EXECUTIVO_TELEFONE}}"] == "—"

    def test_cidade_pode_ser_outra(self):
        assert self._subs(cidade="São Paulo")["{{CIDADE}}"] == "São Paulo"

    def test_cobre_todos_os_marcadores_do_modelo(self):
        """
        Marcador sem valor no mapa fica literal no slide: o cliente recebe
        '{{MENSALIDADE}}' no lugar do preço.
        """
        esperados = {
            "{{CLIENTE}}", "{{VIDAS}}", "{{VALOR_VIDA}}", "{{MENSALIDADE}}",
            "{{TREINAMENTOS}}", "{{LAUDOS}}", "{{INVESTIMENTO}}",
            "{{EXECUTIVO_NOME}}", "{{EXECUTIVO_EMAIL}}", "{{EXECUTIVO_TELEFONE}}",
            "{{CIDADE}}", "{{DATA_EXTENSO}}", "{{VALIDADE}}",
        }
        assert set(self._subs()) == esperados


class TestNomeDoArquivo:
    def test_comeca_pelo_numero_da_oportunidade(self):
        nome = regras.nome_do_arquivo("OPP-2026-00001", "Metalurgica Alfa LTDA", 2, "pptx")
        assert nome == "OPP-2026-00001_Metalurgica_Alfa_LTDA_v2.pptx"

    def test_tira_caractere_que_o_windows_recusa(self):
        nome = regras.nome_do_arquivo("OPP-1", "A/B \\ C: D?", 1, "pdf")
        for proibido in '/\\:?*"<>|':
            assert proibido not in nome

    def test_nome_gigante_e_cortado(self):
        nome = regras.nome_do_arquivo("OPP-1", "X" * 200, 1, "pptx")
        assert len(nome) < 90
