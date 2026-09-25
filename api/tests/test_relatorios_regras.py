"""
HIPO - Relatorios: regras puras (catalogo e montagem do SQL), sem banco.

Rodam no pytest local do Windows. O que so aparece com banco (recorte,
totais, drilldown, salvos) esta em test_crm_relatorios.py.

O teste que trava a seguranca do modulo e
`test_valor_do_usuario_nunca_entra_no_sql`: tudo o que vem do cliente vira
parametro ($n). Se cair, alguem montou SQL com texto do usuario.
"""
from datetime import date
from uuid import uuid4

import pytest

from services import relatorios as rel
from services.permissao import escopo_de_visao

P = {"inicio": date(2026, 9, 1), "fim": date(2026, 9, 30)}


def consulta(fonte="oportunidades", data_ref=None, **extra):
    f = rel.FONTES[fonte]
    base = {
        "fonte": fonte,
        "periodo": {"data_ref": data_ref or f.data_padrao, **P},
        "linhas": [], "colunas": [], "valores": [], "filtros": [],
    }
    base.update(extra)
    return base


# ── Escopo de visao ──────────────────────────────────────────────────

class TestEscopo:
    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM"])
    def test_gestao_ve_tudo(self, cargo):
        assert escopo_de_visao(cargo, "u1") is None

    @pytest.mark.parametrize("cargo", ["EC", "SDR", "EV", "EP"])
    def test_operacional_ve_o_seu(self, cargo):
        assert escopo_de_visao(cargo, "u1") == "u1"

    @pytest.mark.parametrize("cargo", ["Gerente", "Hunter", "Inventado", None, ""])
    def test_cargo_desconhecido_fica_no_lado_seguro(self, cargo):
        """Na duvida, recorte maximo -- nunca visao total."""
        assert escopo_de_visao(cargo, "u1") == "u1"


# ── Catalogo ─────────────────────────────────────────────────────────

class TestCatalogo:
    @pytest.mark.parametrize("fonte", list(rel.FONTES))
    def test_chaves_unicas_por_fonte(self, fonte):
        chaves = [c.chave for c in rel.FONTES[fonte].campos]
        assert len(chaves) == len(set(chaves)), sorted(k for k in chaves if chaves.count(k) > 1)

    @pytest.mark.parametrize("fonte", list(rel.FONTES))
    def test_rotulos_unicos_por_fonte(self, fonte):
        """Dois campos com o mesmo nome na lista e escolha no escuro."""
        rotulos = [c.rotulo for c in rel.FONTES[fonte].campos]
        assert len(rotulos) == len(set(rotulos)), sorted(r for r in rotulos if rotulos.count(r) > 1)

    @pytest.mark.parametrize("fonte", list(rel.FONTES))
    def test_data_padrao_e_referencia(self, fonte):
        f = rel.FONTES[fonte]
        c = f.campo(f.data_padrao)
        assert c.tipo == "data" and c.referencia

    @pytest.mark.parametrize("fonte", list(rel.FONTES))
    def test_colunas_do_drilldown_existem(self, fonte):
        f = rel.FONTES[fonte]
        for k in f.colunas_registro:
            f.campo(k)

    @pytest.mark.parametrize("fonte", list(rel.FONTES))
    def test_todo_join_pedido_existe(self, fonte):
        f = rel.FONTES[fonte]
        for c in f.campos:
            rel._resolver_joins(f, set(c.joins))
        rel._resolver_joins(f, set(f.joins_abrir) | set(f.joins_recorte))

    @pytest.mark.parametrize("fonte", list(rel.FONTES))
    def test_tipos_validos(self, fonte):
        for c in rel.FONTES[fonte].campos:
            assert c.tipo in rel.TIPOS, c.chave

    def test_rotulos_nao_expoem_nome_de_coluna(self):
        """Nome claro e requisito: nada de snake_case na tela."""
        for f in rel.FONTES.values():
            for c in f.campos:
                assert "_" not in c.rotulo, c.rotulo

    def test_catalogo_nao_vaza_sql(self):
        texto = repr(rel.catalogo())
        assert "SELECT" not in texto and "JOIN" not in texto and "::" not in texto

    def test_agregacoes_por_tipo(self):
        f = rel.OPORTUNIDADES
        assert "soma" in f.campo("mensalidade").agregacoes()
        assert "percentual" in f.campo("foi_conquistada").agregacoes()
        assert f.campo("fase").agregacoes() == ("contagem_distinta",)

    def test_campo_inexistente_explica(self):
        with pytest.raises(rel.ConsultaInvalida, match="não existe"):
            rel.OPORTUNIDADES.campo("nao_existe")


# ── Grouping sets ────────────────────────────────────────────────────

class TestGroupingSets:
    def test_so_linhas(self):
        assert rel.grouping_sets(2, 0) == [(), (0,), (0, 1)]

    def test_linhas_e_colunas(self):
        assert rel.grouping_sets(2, 1) == [(2,), (), (0, 2), (0,), (0, 1, 2), (0, 1)]

    def test_so_colunas(self):
        assert rel.grouping_sets(0, 2) == [(0, 1), ()]

    def test_combinacoes_de_coluna(self):
        celulas = [
            {"g": [True, False]},   # total da coluna A
            {"g": [True, False]},   # total da coluna B
            {"g": [True, True]},    # total geral
            {"g": [False, False]},  # celula
        ]
        assert rel.contar_combinacoes_coluna(celulas, 1, 1) == 2
        assert rel.contar_combinacoes_coluna(celulas, 1, 0) == 0


# ── Montagem ─────────────────────────────────────────────────────────

class TestMontagem:
    def test_valor_do_usuario_nunca_entra_no_sql(self):
        malicioso = "x'); DROP TABLE usuarios; --"
        q = consulta(filtros=[
            {"campo": "empresa", "operador": "em", "valores": [malicioso]},
            {"campo": "empresa_cidade", "operador": "contem", "texto": malicioso},
        ])
        sql, params, _ = rel.montar_consulta(q, None)
        assert "DROP" not in sql
        assert [malicioso] in params
        assert f"%{malicioso}%" in params

    @pytest.mark.parametrize("fonte", list(rel.FONTES))
    def test_escopo_sempre_e_o_primeiro_parametro(self, fonte):
        uid = uuid4()
        sql, params, _ = rel.montar_consulta(consulta(fonte), uid)
        assert params[0] == uid
        assert "$1::uuid" in sql
        assert ":escopo" not in sql

    def test_sem_valores_conta_registros(self):
        _, _, meta = rel.montar_consulta(consulta(), None)
        assert meta["medidas"][0][:2] == ("*", "contagem")

    def test_data_ganha_granularidade_padrao(self):
        q = consulta(linhas=[{"campo": "data_criacao"}])
        sql, _, meta = rel.montar_consulta(q, None)
        assert meta["linhas"][0][1] == "mes"
        assert "date_trunc('month'" in sql

    def test_granularidade_em_texto_e_erro(self):
        with pytest.raises(rel.ConsultaInvalida, match="não é data"):
            rel.montar_consulta(consulta(linhas=[{"campo": "fase", "granularidade": "mes"}]), None)

    def test_campo_repetido(self):
        q = consulta(linhas=[{"campo": "fase"}], colunas=[{"campo": "fase"}])
        with pytest.raises(rel.ConsultaInvalida, match="duas vezes"):
            rel.montar_consulta(q, None)

    def test_mesma_data_em_granularidades_diferentes_pode(self):
        q = consulta(linhas=[{"campo": "data_criacao", "granularidade": "ano"}],
                     colunas=[{"campo": "data_criacao", "granularidade": "mes"}])
        rel.montar_consulta(q, None)

    def test_limite_de_linhas(self):
        campos = ["fase", "situacao", "origem", "ev", "sdr"]
        with pytest.raises(rel.ConsultaInvalida, match="linhas"):
            rel.montar_consulta(consulta(linhas=[{"campo": c} for c in campos]), None)

    def test_agregacao_incompativel(self):
        q = consulta(valores=[{"campo": "fase", "agregacao": "soma"}])
        with pytest.raises(rel.ConsultaInvalida, match="não aceita"):
            rel.montar_consulta(q, None)

    def test_contagem_so_de_registros(self):
        with pytest.raises(rel.ConsultaInvalida):
            rel.montar_consulta(consulta(valores=[{"campo": "*", "agregacao": "soma"}]), None)

    def test_periodo_invertido(self):
        q = consulta()
        q["periodo"]["inicio"], q["periodo"]["fim"] = date(2026, 9, 30), date(2026, 9, 1)
        with pytest.raises(rel.ConsultaInvalida, match="depois"):
            rel.montar_consulta(q, None)

    def test_periodo_longo_demais(self):
        q = consulta()
        q["periodo"]["inicio"] = date(2000, 1, 1)
        with pytest.raises(rel.ConsultaInvalida, match="10 anos"):
            rel.montar_consulta(q, None)

    def test_data_ref_precisa_ser_data_de_referencia(self):
        with pytest.raises(rel.ConsultaInvalida, match="período"):
            rel.montar_consulta(consulta(data_ref="fase"), None)

    def test_periodo_com_hora_usa_faixa_no_fuso(self):
        sql, _, _ = rel.montar_consulta(consulta(), None)
        assert "AT TIME ZONE 'America/Sao_Paulo'" in sql
        assert "($3::date + 1)" in sql

    def test_periodo_de_coluna_date_usa_between(self):
        sql, _, _ = rel.montar_consulta(consulta(data_ref="data_previsao"), None)
        assert "BETWEEN $2::date AND $3::date" in sql

    def test_so_junta_o_que_precisa(self):
        sql, _, _ = rel.montar_consulta(consulta(linhas=[{"campo": "fase"}]), None)
        assert "motivos_desfecho" not in sql
        assert "propostas" not in sql
        sql, _, _ = rel.montar_consulta(consulta(linhas=[{"campo": "motivo_desfecho"}]), None)
        assert "motivos_desfecho" in sql

    def test_dependencia_de_join_e_resolvida(self):
        sql, _, _ = rel.montar_consulta(consulta("tarefas", linhas=[{"campo": "empresa_vertical"}]), None)
        assert sql.index("oportunidades o") < sql.index("contas c") < sql.index("verticais v")


class TestFiltros:
    def test_em_com_em_branco(self):
        q = consulta(filtros=[{"campo": "origem", "operador": "em", "valores": ["Site", None]}])
        sql, params, _ = rel.montar_consulta(q, None)
        assert "IS NULL" in sql and ["Site"] in params

    def test_nao_em_mantem_em_branco(self):
        q = consulta(filtros=[{"campo": "origem", "operador": "nao_em", "valores": ["Site"]}])
        sql, _, _ = rel.montar_consulta(q, None)
        assert "IS NULL OR NOT" in sql

    def test_filtro_sem_valor(self):
        with pytest.raises(rel.ConsultaInvalida, match="sem nenhum valor"):
            rel.montar_consulta(consulta(filtros=[{"campo": "fase", "operador": "em", "valores": []}]), None)

    def test_entre_numero(self):
        q = consulta(filtros=[{"campo": "mensalidade", "operador": "entre", "minimo": "100,50"}])
        _, params, _ = rel.montar_consulta(q, None)
        from decimal import Decimal
        assert Decimal("100.50") in params

    def test_entre_em_texto_e_erro(self):
        with pytest.raises(rel.ConsultaInvalida, match="não é número"):
            rel.montar_consulta(consulta(filtros=[{"campo": "fase", "operador": "entre", "minimo": "1"}]), None)

    def test_entre_valor_invalido(self):
        q = consulta(filtros=[{"campo": "data_previsao", "operador": "entre", "minimo": "ontem"}])
        with pytest.raises(rel.ConsultaInvalida, match="inválido"):
            rel.montar_consulta(q, None)

    def test_operador_desconhecido(self):
        with pytest.raises(rel.ConsultaInvalida, match="Operador"):
            rel.montar_consulta(consulta(filtros=[{"campo": "fase", "operador": "like"}]), None)

    def test_limite_de_filtros(self):
        f = [{"campo": "fase", "operador": "em", "valores": ["lead"]}] * (rel.MAX_FILTROS + 1)
        with pytest.raises(rel.ConsultaInvalida, match="Filtros demais"):
            rel.montar_consulta(consulta(filtros=f), None)


class TestRegistrosEValores:
    def test_celula_vira_filtro(self):
        sql, params, meta = rel.montar_registros(
            consulta(), None, [{"campo": "fase", "granularidade": None, "valor": "lead"}], 50, 0,
        )
        assert ["lead"] in params
        assert meta["abrir"] == ["oportunidade"]
        assert [c["campo"] for c in meta["colunas"]] == list(rel.OPORTUNIDADES.colunas_registro)

    def test_limite_do_drilldown(self):
        _, params, _ = rel.montar_registros(consulta(), None, [], 10_000, 0)
        assert rel.MAX_REGISTROS_PAGINA in params

    def test_valores_ignoram_o_filtro_do_proprio_campo(self):
        q = consulta(filtros=[
            {"campo": "fase", "operador": "em", "valores": ["lead"]},
            {"campo": "origem", "operador": "em", "valores": ["Site"]},
        ])
        _, params = rel.montar_valores(q, None, "fase", None, None)
        assert ["lead"] not in params
        assert ["Site"] in params


class TestConfigSalva:
    def cfg(self, **troca):
        base = {
            "fonte": "oportunidades",
            "periodo": {"tipo": "relativo", "preset": "mes_atual", "data_ref": "data_criacao"},
            "linhas": [{"campo": "fase"}],
            "colunas": [],
            "valores": [{"campo": "*", "agregacao": "contagem"}],
            "filtros": [],
        }
        base.update(troca)
        return base

    def test_relativo_valido(self):
        assert rel.validar_config_salva(self.cfg())["fonte"] == "oportunidades"

    def test_fixo_valido(self):
        per = {"tipo": "fixo", "inicio": "2026-01-01", "fim": "2026-06-30", "data_ref": "data_criacao"}
        rel.validar_config_salva(self.cfg(periodo=per))

    def test_preset_desconhecido(self):
        per = {"tipo": "relativo", "preset": "semestre_que_vem", "data_ref": "data_criacao"}
        with pytest.raises(rel.ConsultaInvalida, match="relativo"):
            rel.validar_config_salva(self.cfg(periodo=per))

    def test_tipo_de_periodo_obrigatorio(self):
        with pytest.raises(rel.ConsultaInvalida):
            rel.validar_config_salva(self.cfg(periodo={"data_ref": "data_criacao"}))

    def test_campo_inexistente(self):
        with pytest.raises(rel.ConsultaInvalida, match="não existe"):
            rel.validar_config_salva(self.cfg(linhas=[{"campo": "sumiu"}]))

    def test_fonte_inexistente(self):
        with pytest.raises(rel.ConsultaInvalida, match="Fonte"):
            rel.validar_config_salva(self.cfg(fonte="pex"))
