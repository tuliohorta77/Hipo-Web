"""
HIPO — Regras puras da Prospecção (services/prospeccao.py).

Sem banco: rodam no pytest local do Windows. O que protegem:

  * a fatia nunca sai sem UF e sem CNAE (consulta que varre o estado);
  * prefixo de CNAE vira faixa exata — '41' pega 4120400 e não pega 4211101;
  * a prioridade das situações: bloqueada vence tudo, cliente vence aberta;
  * o lote não deixa o mesmo CNPJ entrar duas vezes.
"""
from datetime import date
from decimal import Decimal

import pytest

from services import prospeccao as p
from services.prospeccao import FiltroInvalido, FiltrosFatia


def _f(**kw):
    base = {"ufs": ("SP",), "cnaes": ("41",)}
    base.update(kw)
    return FiltrosFatia(**base)


class TestFaixaCnae:
    @pytest.mark.parametrize("prefixo,faixa", [
        ("41", ("4100000", "4199999")),
        ("412", ("4120000", "4129999")),
        ("4120400", ("4120400", "4120400")),
        ("01", ("0100000", "0199999")),
        ("41.20-4", ("4120400", "4120499")),
    ])
    def test_prefixo_vira_faixa(self, prefixo, faixa):
        assert p.faixa_cnae(prefixo) == faixa

    @pytest.mark.parametrize("ruim", ["4", "", "41204001", "abc"])
    def test_recusa_prefixo_ruim(self, ruim):
        with pytest.raises(FiltroInvalido):
            p.faixa_cnae(ruim)

    def test_faixa_e_exata_na_fronteira_da_divisao(self):
        lo, hi = p.faixa_cnae("41")
        assert lo <= "4120400" <= hi
        assert not (lo <= "4211101" <= hi)
        assert not (lo <= "3999999" <= hi)


class TestValidacao:
    def test_sem_uf_recusa(self):
        with pytest.raises(FiltroInvalido, match="UF"):
            _f(ufs=()).validar()

    def test_sem_cnae_recusa_com_o_motivo(self):
        with pytest.raises(FiltroInvalido, match="prospecção"):
            _f(cnaes=()).validar()

    def test_uf_minuscula_recusa(self):
        # O router normaliza; a regra garante que ninguém pule o router.
        with pytest.raises(FiltroInvalido):
            _f(ufs=("sp",)).validar()

    def test_limite_de_cnaes(self):
        with pytest.raises(FiltroInvalido, match="30"):
            _f(cnaes=tuple(str(10 + i) for i in range(31))).validar()

    @pytest.mark.parametrize("campo,valor", [
        ("municipios", ("123",)),
        ("portes", ("02",)),
        ("regime", "lucro_real"),
        ("idade_min", -1),
        ("capital_min", Decimal("-1")),
    ])
    def test_campos_invalidos(self, campo, valor):
        with pytest.raises(FiltroInvalido):
            _f(**{campo: valor}).validar()

    def test_filtro_completo_valido(self):
        f = _f(
            cnaes=("41", "4321500"), municipios=("6477",), portes=("03", "05"),
            regime="nao_simples", idade_min=2, capital_min=Decimal("100000"),
        )
        assert f.validar() is f


class TestMontarWhere:
    def test_parametros_numerados_em_ordem(self):
        where, params = p.montar_where(_f(cnaes=("41", "43")), date(2026, 10, 2))
        assert params == [["SP"], "4100000", "4199999", "4300000", "4399999"]
        for i in range(1, len(params) + 1):
            assert f"${i}" in where
        assert f"${len(params) + 1}" not in where

    def test_secundarios_usa_a_tabela_de_cnaes(self):
        where, _ = p.montar_where(_f(secundarios=True), date(2026, 10, 2))
        assert "cnaes_secundarios &&" in where
        assert "receita_cnaes" in where

    def test_idade_minima_vira_data(self):
        _, params = p.montar_where(_f(idade_min=3), date(2026, 10, 2))
        assert date(2023, 10, 2) in params

    def test_busca_por_cnpj_vai_pela_raiz(self):
        where, params = p.montar_where(_f(q="11.222.333/0001"), date(2026, 10, 2))
        assert "r.cnpj LIKE" in where
        assert "112223330001%" in params

    def test_busca_por_nome(self):
        where, params = p.montar_where(_f(q="acme"), date(2026, 10, 2))
        assert "ILIKE" in where
        assert "%acme%" in params

    def test_regimes(self):
        w1, _ = p.montar_where(_f(regime="simples"), date(2026, 10, 2))
        w2, _ = p.montar_where(_f(regime="nao_simples"), date(2026, 10, 2))
        assert "r.simples IS TRUE" in w1
        # IS NOT TRUE, e não `= FALSE`: empresa sem linha no arquivo do
        # Simples (NULL) também não é optante.
        assert "r.simples IS NOT TRUE" in w2


class TestSituacao:
    def test_ordem_de_prioridade(self):
        assert p.situacao(existe=False) == "nova"
        assert p.situacao(existe=True) == "conta_sem_negocio"
        assert p.situacao(existe=True, tem_aberta=True) == "em_negociacao"
        assert p.situacao(existe=True, tem_conquistada=True, tem_aberta=True) == "cliente"
        assert p.situacao(existe=True, ativa=False, tem_conquistada=True) == "inativa"
        assert p.situacao(existe=True, nao_prospectar=True, ativa=False) == "bloqueada"

    def test_so_duas_sao_puxaveis(self):
        assert p.PUXAVEIS == {"nova", "conta_sem_negocio"}

    def test_toda_situacao_nao_puxavel_tem_mensagem(self):
        for s in set(p.SITUACOES) - p.PUXAVEIS:
            assert s in p.MOTIVOS_PULO

    def test_sql_cobre_todas_as_situacoes(self):
        for s in p.SITUACOES:
            assert f"'{s}'" in p.SITUACAO_SQL


class TestLote:
    def test_repetido_e_invalido_sao_pulados(self):
        validos, pulados = p.preparar_lote(
            ["11.222.333/0001-81", "11222333000181", "11222333000182"]
        )
        assert validos == ["11222333000181"]
        assert [x["motivo"] for x in pulados] == ["repetido", "cnpj_invalido"]

    def test_preserva_ordem(self):
        validos, _ = p.preparar_lote(["34028316000103", "11222333000181"])
        assert validos == ["34028316000103", "11222333000181"]


class TestContaDaBase:
    BASE = {
        "cnpj": "11222333000181", "razao_social": "ACME LTDA",
        "nome_fantasia": "ACME", "cnae_principal": "2511000", "porte": "05",
        "data_abertura": date(2010, 1, 1), "capital_social": Decimal("100000.00"),
        "cep": "07010000", "logradouro": "RUA X", "numero": "1",
        "complemento": None, "bairro": "CENTRO", "uf": "SP",
        "telefone": "1123456789", "telefone_2": None, "email": "a@b.com",
    }

    def test_porte_e_situacao_no_texto_da_brasilapi(self):
        d = p.conta_da_base(self.BASE, "GUARULHOS")
        assert d["porte"] == "DEMAIS"
        assert d["situacao_cadastral"] == "ATIVA"
        assert d["cidade"] == "GUARULHOS"

    def test_capital_que_nao_cabe_na_conta_fica_vazio(self):
        d = p.conta_da_base({**self.BASE, "capital_social": Decimal("50000000000000")}, None)
        assert d["capital_social"] is None
        assert d["cidade"] is None

    def test_porte_nao_informado_fica_vazio(self):
        assert p.conta_da_base({**self.BASE, "porte": "00"}, None)["porte"] is None

    def test_titulo_usa_fantasia_e_cabe_na_coluna(self):
        assert p.titulo_primeiro_contato("X" * 300, None).startswith("Primeiro contato")
        assert len(p.titulo_primeiro_contato("X" * 300, None)) == 200
