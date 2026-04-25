"""
Testes do catálogo PEX.
Validações estruturais do manual oficial v8.01/2026.
"""
from services.pex_catalogo import (
    CATALOGO, CLUSTERS,
    PILAR_RESULTADO, PILAR_GESTAO, PILAR_ENGAJAMENTO,
    indicadores_editaveis, indicadores_por_pilar, meta_para_cluster,
    get_indicador,
)


class TestEstruturaCatalogo:
    def test_total_30_indicadores(self):
        assert len(CATALOGO) == 30

    def test_pesos_por_pilar(self):
        # Manual: Resultado=60, Gestão=20, Engajamento=20, total=100
        soma_resultado = sum(i["pts"] for i in indicadores_por_pilar(PILAR_RESULTADO))
        soma_gestao = sum(i["pts"] for i in indicadores_por_pilar(PILAR_GESTAO))
        soma_engajamento = sum(i["pts"] for i in indicadores_por_pilar(PILAR_ENGAJAMENTO))
        assert soma_resultado == 60
        assert soma_gestao == 20
        assert soma_engajamento == 20
        assert soma_resultado + soma_gestao + soma_engajamento == 100

    def test_contagem_por_pilar(self):
        # Manual: Resultado 17, Gestão 7, Engajamento 6
        assert len(indicadores_por_pilar(PILAR_RESULTADO)) == 17
        assert len(indicadores_por_pilar(PILAR_GESTAO)) == 7
        assert len(indicadores_por_pilar(PILAR_ENGAJAMENTO)) == 6

    def test_codigos_unicos(self):
        codigos = [i["codigo"] for i in CATALOGO]
        assert len(codigos) == len(set(codigos))

    def test_todo_indicador_tem_campos_obrigatorios(self):
        for i in CATALOGO:
            assert "codigo" in i
            assert "pilar" in i
            assert "nome" in i
            assert "pts" in i
            assert "tipo" in i


class TestIndicadoresEditaveis:
    def test_apenas_5_editaveis_pelo_adm(self):
        """Manual: NMRR, Demos Outbound, Integração Contábil, Headcount, Eventos"""
        editaveis = {i["codigo"] for i in indicadores_editaveis()}
        assert editaveis == {
            "nmrr", "demos_outbound", "integracao_contabil",
            "headcount_recomendado", "eventos",
        }


class TestMetaPorCluster:
    def test_integracao_contabil_por_cluster(self):
        # Manual:
        # Incubadora: 3, Avança+/Base/Ouro: 5, Platina/Prime/Black: 8
        assert meta_para_cluster("integracao_contabil", "INCUBADORA") == 3
        assert meta_para_cluster("integracao_contabil", "BASE") == 5
        assert meta_para_cluster("integracao_contabil", "OURO") == 5
        assert meta_para_cluster("integracao_contabil", "PLATINA") == 8
        assert meta_para_cluster("integracao_contabil", "BLACK") == 8

    def test_eventos_por_cluster(self):
        # Manual:
        # Incubadora/Avança+: 2, Base: 3, Ouro: 4, Platina: 5, Prime/Black: 6
        assert meta_para_cluster("eventos", "INCUBADORA") == 2
        assert meta_para_cluster("eventos", "AVANCA_PLUS") == 2
        assert meta_para_cluster("eventos", "BASE") == 3
        assert meta_para_cluster("eventos", "OURO") == 4
        assert meta_para_cluster("eventos", "PLATINA") == 5
        assert meta_para_cluster("eventos", "PRIME") == 6
        assert meta_para_cluster("eventos", "BLACK") == 6

    def test_cluster_inexistente_retorna_none(self):
        assert meta_para_cluster("integracao_contabil", "INVALIDO") is None

    def test_indicador_sem_meta_cluster_retorna_none(self):
        # NMRR não varia por cluster
        assert meta_para_cluster("nmrr", "PLATINA") is None


class TestFaixasPontuacao:
    def test_nmrr_tem_proporcional(self):
        ind = get_indicador("nmrr")
        # Faixa 85-100 é PROPORCIONAL (regra especial do manual)
        assert any(f[2] == "PROPORCIONAL" for f in ind["faixas"])

    def test_big3_escala_discreta(self):
        ind = get_indicador("big3")
        assert ind["tipo"] == "ESCALA_DISCRETA"
        # 0/1/2/3 ações = 0/2/4/6 pts
        assert (0, 0, 0) in ind["faixas"]
        assert (1, 1, 2) in ind["faixas"]
        assert (3, 3, 6) in ind["faixas"]

    def test_indicadores_pct_lower_better(self):
        # Manual: Early Churn, Util Desconto, Turnover Voluntário
        lower_better = {i["codigo"] for i in CATALOGO if i["tipo"] == "PCT_LOWER_BETTER"}
        assert lower_better == {"early_churn", "utilizacao_desconto", "turnover_voluntario"}

    def test_indicadores_binarios(self):
        # Manual: Rem Variável, Instagram
        binarios = {i["codigo"] for i in CATALOGO if i["tipo"] == "BINARIO"}
        assert binarios == {"remuneracao_variavel", "instagram"}


class TestClusters:
    def test_lista_clusters_oficiais(self):
        # Manual cita: Incubadora, Avança+, Base, Ouro, Platina, Prime, Black
        assert set(CLUSTERS) == {
            "INCUBADORA", "AVANCA_PLUS", "BASE", "OURO",
            "PLATINA", "PRIME", "BLACK",
        }
