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
            # 042: rodapé do slide da tabela de preços.
            "{{TABELA_RODAPE}}",
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


# ══════════════════════════════════════════════════════════════════════
# 042 — vários CNPJs e tabela de preço por faixa
# ══════════════════════════════════════════════════════════════════════

TABELA = regras.normalizar_tabela(regras.TABELA_PADRAO)


def _item(vidas, mensalidade=None, cnpj="11222333000181", razao="ALFA LTDA"):
    d = {"cnpj": cnpj, "razao_social": razao, "vidas": vidas}
    if mensalidade is not None:
        d["mensalidade"] = Decimal(str(mensalidade))
    return d


class TestTabelaDePreco:
    @pytest.mark.parametrize("vidas,esperado", [
        (1, "180.00"), (5, "180.00"),      # borda de cima da 1ª faixa
        (6, "220.00"), (10, "220.00"),
        (11, "260.00"), (15, "260.00"),
        (16, "300.00"), (20, "300.00"),
        (21, "315.00"),                    # acima de 20: R$ 15 por vida, TODAS
        (23, "345.00"), (27, "405.00"),
    ])
    def test_valor_da_faixa(self, vidas, esperado):
        assert regras.valor_tabela(vidas, TABELA) == Decimal(esperado)

    def test_linhas_no_texto_do_material(self):
        assert regras.linhas_tabela(TABELA) == [
            "CNPJs até 05 funcionários registrados – R$ 180,00 mensais",
            "CNPJs entre 06 e 10 funcionários registrados – R$ 220,00 mensais",
            "CNPJs entre 11 e 15 funcionários registrados – R$ 260,00 mensais",
            "CNPJs entre 16 e 20 funcionários registrados – R$ 300,00 mensais",
            "CNPJs acima de 20 funcionários registrados – R$ 15,00 por funcionário/mês",
        ]

    def test_rodape_sai_da_faixa_aberta(self):
        """Reajuste da tabela tem que mudar o rodapé junto, sem editar slide."""
        tabela = regras.normalizar_tabela([
            {"vidas_ate": 30, "tipo": "fixo", "valor": "400"},
            {"vidas_ate": None, "tipo": "por_vida", "valor": "12.5"},
        ])
        rodape = regras.rodape_tabela(tabela)
        assert "limite de 30 funcionários" in rodape
        assert "R$ 12,50" in rodape
        assert "Para até 30 vidas" in rodape

    def test_normaliza_fora_de_ordem(self):
        tabela = regras.normalizar_tabela([
            {"vidas_ate": None, "tipo": "por_vida", "valor": 15},
            {"vidas_ate": 10, "tipo": "fixo", "valor": 220},
            {"vidas_ate": 5, "tipo": "fixo", "valor": 180},
        ])
        assert [f["vidas_ate"] for f in tabela] == [5, 10, None]

    def test_sem_faixa_aberta_e_recusada(self):
        with pytest.raises(regras.PropostaInvalida, match="sem limite"):
            regras.normalizar_tabela([{"vidas_ate": 5, "tipo": "fixo", "valor": 180}])

    def test_duas_abertas_e_recusada(self):
        with pytest.raises(regras.PropostaInvalida, match="sem limite"):
            regras.normalizar_tabela([
                {"vidas_ate": None, "tipo": "fixo", "valor": 180},
                {"vidas_ate": None, "tipo": "por_vida", "valor": 15},
            ])

    def test_limite_repetido_e_recusado(self):
        with pytest.raises(regras.PropostaInvalida, match="mesmo limite"):
            regras.normalizar_tabela([
                {"vidas_ate": 5, "tipo": "fixo", "valor": 180},
                {"vidas_ate": 5, "tipo": "fixo", "valor": 200},
                {"vidas_ate": None, "tipo": "por_vida", "valor": 15},
            ])

    def test_valor_zero_e_recusado(self):
        with pytest.raises(regras.PropostaInvalida, match="maior que zero"):
            regras.normalizar_tabela([{"vidas_ate": None, "tipo": "fixo", "valor": 0}])

    def test_json_ida_e_volta_sem_perder_centavo(self):
        volta = regras.tabela_de_json(regras.tabela_para_json(TABELA))
        assert volta == TABELA


class TestItens:
    def test_material_varios_cnpjs_fecha_1270(self):
        """
        O material "VARIOS CNPJs": 4, 5 e 11 vidas pela tabela; 23 e 27
        negociados (R$ 299 e R$ 351). Total R$ 1.270,00, 70 vidas.
        """
        itens = regras.calcular_itens(
            modalidade="tabela",
            itens=[_item(4), _item(5), _item(11), _item(23, 299), _item(27, 351)],
            valor_por_vida=None, faixas=TABELA,
        )
        assert [i["mensalidade"] for i in itens] == [
            Decimal("180.00"), Decimal("180.00"), Decimal("260.00"),
            Decimal("299.00"), Decimal("351.00"),
        ]
        assert regras.total_itens(itens) == Decimal("1270.00")
        assert regras.vidas_itens(itens) == 70

    def test_tabela_guarda_o_sugerido_mesmo_negociado(self):
        [item] = regras.calcular_itens(
            modalidade="tabela", itens=[_item(23, 299)],
            valor_por_vida=None, faixas=TABELA,
        )
        assert item["valor_tabela"] == Decimal("345.00")
        assert item["mensalidade"] == Decimal("299.00")

    def test_por_vida_ignora_valor_digitado(self):
        """Na modalidade por vida, a linha é derivada — o slide tem que fechar."""
        [item] = regras.calcular_itens(
            modalidade="por_vida", itens=[_item(10, 1)],
            valor_por_vida=Decimal("20"), faixas=None,
        )
        assert item["mensalidade"] == Decimal("200.00")
        assert item["valor_tabela"] is None

    def test_por_vida_sem_valor_por_vida(self):
        with pytest.raises(regras.PropostaInvalida, match="maior que zero"):
            regras.calcular_itens(modalidade="por_vida", itens=[_item(10)],
                                  valor_por_vida=None, faixas=None)

    @pytest.mark.parametrize("mensal,tabela,esperado", [
        ("299", "345", Decimal("13.3")),
        ("345", "345", None),     # na tabela
        ("400", "345", None),     # acima da tabela não é desconto
        ("100", None, None),      # modalidade por vida
    ])
    def test_desconto(self, mensal, tabela, esperado):
        t = Decimal(tabela) if tabela else None
        assert regras.desconto_percentual(Decimal(mensal), t) == esperado


class TestListaDoSlide:
    def test_linha_do_cnpj(self):
        item = {"cnpj": "11222333000181", "razao_social": "Metalurgica Alfa LTDA",
                "vidas": 4, "mensalidade": Decimal("180")}
        assert regras.linha_cnpj(item) == (
            "Metalurgica Alfa LTDA (11.222.333/0001-81) - 4 vidas - "
            "Mensalidade R$ 180,00"
        )

    def test_uma_vida_no_singular(self):
        item = {"cnpj": "11222333000181", "razao_social": "A", "vidas": 1,
                "mensalidade": Decimal("180")}
        assert "- 1 vida -" in regras.linha_cnpj(item)

    def test_razao_longa_e_cortada(self):
        item = {"cnpj": "11222333000181", "razao_social": "X" * 120, "vidas": 4,
                "mensalidade": Decimal("180")}
        assert len(regras.linha_cnpj(item)) < 90

    def test_um_cnpj_so_nao_lista_cnpj(self):
        """Com um CNPJ, a lista é só o escopo — como sempre foi."""
        itens = [{"cnpj": "1", "razao_social": "A", "vidas": 4, "mensalidade": 180}]
        assert regras.linhas_da_lista(modalidade="tabela", escopo=["PGR"],
                                      itens=itens) == ["PGR"]

    def test_varios_cnpjs_entram_depois_do_escopo(self):
        itens = [
            {"cnpj": "11222333000181", "razao_social": "A", "vidas": 4, "mensalidade": 180},
            {"cnpj": "11222333000262", "razao_social": "B", "vidas": 5, "mensalidade": 180},
        ]
        linhas = regras.linhas_da_lista(modalidade="tabela", escopo=["PGR"], itens=itens)
        assert linhas[0] == "PGR"
        assert linhas[1].startswith("A (") and linhas[2].startswith("B (")

    def test_proposta_por_cnpj_nao_lista_os_outros(self):
        itens = [
            {"cnpj": "11222333000181", "razao_social": "A", "vidas": 4, "mensalidade": 180},
            {"cnpj": "11222333000262", "razao_social": "B", "vidas": 5, "mensalidade": 180},
        ]
        assert regras.linhas_da_lista(modalidade="tabela", escopo=["PGR"], itens=itens,
                                      consolidada=False) == ["PGR"]

    def test_extras_viram_linha_na_tabela(self):
        """A modalidade tabela não tem o quadro de investimento."""
        itens = [{"cnpj": "1", "razao_social": "A", "vidas": 4, "mensalidade": 180}]
        linhas = regras.linhas_da_lista(modalidade="tabela", escopo=["PGR"], itens=itens,
                                        treinamentos=Decimal("500"))
        assert "Treinamentos - R$ 500,00" in linhas

    def test_extras_nao_viram_linha_por_vida(self):
        itens = [{"cnpj": "1", "razao_social": "A", "vidas": 4, "mensalidade": 80}]
        linhas = regras.linhas_da_lista(modalidade="por_vida", escopo=["PGR"], itens=itens,
                                        treinamentos=Decimal("500"))
        assert linhas == ["PGR"]


class TestEscala:
    def test_cabe_sem_reduzir(self):
        assert regras.escala_da_lista(["curto"] * 12, 12) == Decimal("1.00")

    def test_reduz_quando_passa(self):
        escala = regras.escala_da_lista(["curto"] * 16, 12)
        assert regras.ESCALA_MINIMA <= escala < 1

    def test_nao_cabe_nem_no_minimo(self):
        assert regras.escala_da_lista(["curto"] * 40, 12) is None

    def test_linha_longa_conta_dobrado(self):
        longa = "x" * (regras.CARACTERES_POR_LINHA + 10)
        assert regras.escala_da_lista([longa] * 12, 12) < 1


class TestValidarItens:
    def _ok(self, **troca):
        base = dict(modalidade="tabela", itens=[_item(4, 180)], valor_por_vida=None,
                    escopo=["PGR"])
        base.update(troca)
        return regras.validar_itens(**base)

    def test_valido(self):
        self._ok()

    def test_sem_cnpj(self):
        with pytest.raises(regras.PropostaInvalida, match="pelo menos um CNPJ"):
            self._ok(itens=[])

    def test_cnpj_repetido(self):
        with pytest.raises(regras.PropostaInvalida, match="duas vezes"):
            self._ok(itens=[_item(4, 180), _item(5, 180)])

    def test_total_zero(self):
        with pytest.raises(regras.PropostaInvalida, match="maior que zero"):
            self._ok(itens=[_item(4, 0)])

    def test_cortesia_em_um_cnpj_e_permitida(self):
        """Um CNPJ a R$ 0 é negociação; a proposta inteira a zero não."""
        self._ok(itens=[_item(4, 180), _item(5, 0, cnpj="11222333000262")])

    def test_nao_cabe_no_slide(self):
        itens = [_item(4, 180, cnpj=f"{i:014d}") for i in range(28)]
        with pytest.raises(regras.PropostaInvalida, match="por CNPJ"):
            self._ok(itens=itens, escopo=regras.ESCOPO_PADRAO)


class TestNomeDoArquivoPorCnpj:
    def test_cnpj_no_nome(self):
        nome = regras.nome_do_arquivo("OPP-1", "Filial LTDA", 3, "pdf",
                                      cnpj="11222333000181")
        assert nome == "OPP-1_Filial_LTDA_v3_11222333000181.pdf"


class TestSubstituicoesPorCnpj:
    def _subs(self, **troca):
        base = dict(
            cliente="A", vidas=4, valor_por_vida=None,
            treinamentos=Decimal("2000"), laudos=Decimal("1000"),
            executivo_nome="B", executivo_email="b@x", executivo_telefone="1",
            data_proposta=date(2026, 9, 4), validade=date(2026, 9, 25),
            mensal=Decimal("180"),
        )
        base.update(troca)
        return regras.substituicoes(**base)

    def test_mensal_informado_vale(self):
        assert self._subs()["{{MENSALIDADE}}"] == "R$ 180,00"

    def test_sem_valor_por_vida_vira_travessao(self):
        assert self._subs()["{{VALOR_VIDA}}"] == "—"

    def test_sem_extras_nao_soma_treinamento(self):
        s = self._subs(sem_extras=True)
        assert s["{{TREINAMENTOS}}"] == "—"
        assert s["{{INVESTIMENTO}}"] == "R$ 180,00"
