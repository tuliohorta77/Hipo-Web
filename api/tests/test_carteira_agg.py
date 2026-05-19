"""
Testes do agregador de grupos da Carteira.

Foco:
  - Classificação Hunter/Farmer/Outros pela função do colaborador majoritário.
  - Meta do Hunter: ≥1 tarefa no mês corrente.
  - Meta do Farmer: ≥1 reunião por semana ISO do mês corrente.
  - Timeline produzida corretamente para cada função.
  - Filtros e KPIs.
"""
from datetime import date, datetime

from services.carteira_agg import (
    agregar_grupos,
    aplicar_filtros,
    kpis_por_funcao,
    _ref_mes,
    _semanas_iso_do_mes,
)


# Data fixa de referência para todos os testes — uma terça-feira em maio/2026,
# longe de bordas de mês.
REF = date(2026, 5, 19)


def _cnpj(id_grupo, cnpj, colaborador, nome_grupo="Grupo X", **kwargs):
    base = {
        "id_grupo": id_grupo,
        "nome_grupo": nome_grupo,
        "cnpj_contador": cnpj,
        "contabilidade": "Contab X",
        "bairro": None,
        "cidade_uf": "São Paulo/SP",
        "parceria": "Parceiro",
        "data_parceria": None,
        "tipo_cnae": "CNAE Contábil",
        "colaborador_nome": colaborador,
        "funcao_origem": "Executivo de Contas - FR",
        "porte_faturamento": None,
        "score_rfm": None,
        "apps_ativos": None,
        "mrr_ativo": None,
        "leads_no_mes": 0,
        "status_rf": None,
    }
    base.update(kwargs)
    return base


def _tarefa(cnpj, executivo, data_efetiva, canal=None, situacao="EM_DIA"):
    return {
        "cnpj_contador": cnpj,
        "contabilidade": None,
        "executivo_nome": executivo,
        "situacao": situacao,
        "status": "Concluído" if situacao == "EM_DIA" else None,
        "tarefa_canal": canal,
        "tipo_tarefa": None,
        "resultado": None,
        "data_criacao": data_efetiva,
        "data_agendamento": data_efetiva,
        "data_efetiva": data_efetiva,
    }


def _colab(nome, funcao):
    return {"nome": nome, "funcao": funcao}


# ── Helpers de tempo ─────────────────────────────────────────────

class TestHelpersTempo:
    def test_ref_mes_maio_2026(self):
        ini, fim = _ref_mes(REF)
        assert ini == date(2026, 5, 1)
        assert fim == date(2026, 6, 1)

    def test_ref_mes_dezembro_vira_ano(self):
        ini, fim = _ref_mes(date(2026, 12, 15))
        assert ini == date(2026, 12, 1)
        assert fim == date(2027, 1, 1)

    def test_semanas_iso_maio_2026(self):
        ini, fim = _ref_mes(REF)
        semanas = _semanas_iso_do_mes(ini, fim)
        # Maio/2026: 01/05 (sex) cai na semana ISO 18, e o mês toca 18..22.
        assert len(semanas) >= 4
        anos = {a for a, _ in semanas}
        assert anos == {2026}


# ── Classificação por função ─────────────────────────────────────

class TestClassificacao:
    def test_grupo_de_hunter_vai_para_hunter(self):
        cnpjs = [_cnpj("G1", "11.111.111/0001-11", "Patrick")]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        assert len(grupos) == 1
        assert grupos[0]["funcao"] == "EC_HUNTER"

    def test_grupo_de_farmer_vai_para_farmer(self):
        cnpjs = [_cnpj("G1", "11.111.111/0001-11", "Beatriz")]
        colab = [_colab("Beatriz", "EC_FARMER")]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        assert grupos[0]["funcao"] == "EC_FARMER"

    def test_colaborador_sem_classificacao_vai_para_outros(self):
        cnpjs = [_cnpj("G1", "11.111.111/0001-11", "Desconhecido")]
        # Colaborador não está no cadastro → cai em OUTROS
        grupos = agregar_grupos(cnpjs, [], [], ref_date=REF)
        assert grupos[0]["funcao"] == "OUTROS"

    def test_colaborador_majoritario_decide_a_funcao(self):
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick"),
            _cnpj("G1", "11.111.111/0001-12", "Patrick"),
            _cnpj("G1", "11.111.111/0001-13", "Beatriz"),
        ]
        colab = [
            _colab("Patrick", "EC_HUNTER"),
            _colab("Beatriz", "EC_FARMER"),
        ]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        assert grupos[0]["funcao"] == "EC_HUNTER"
        assert grupos[0]["colaborador_nome"] == "Patrick"
        assert grupos[0]["colaboradores_multiplos"] is True


# ── Meta do Hunter ───────────────────────────────────────────────

class TestMetaHunter:
    def test_hunter_com_uma_tarefa_no_mes_atinge_meta(self):
        cnpjs = [_cnpj("G1", "C1", "Patrick")]
        tarefas = [_tarefa("C1", "Patrick", datetime(2026, 5, 15, 10, 0))]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        assert grupos[0]["meta_atingida"] is True
        assert grupos[0]["timeline"][0]["status"] == "ok"
        assert grupos[0]["timeline"][0]["count"] == 1

    def test_hunter_sem_tarefa_no_mes_nao_atinge(self):
        cnpjs = [_cnpj("G1", "C1", "Patrick")]
        # Tarefa em ABRIL — fora do mês corrente
        tarefas = [_tarefa("C1", "Patrick", datetime(2026, 4, 15))]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        assert grupos[0]["meta_atingida"] is False
        assert grupos[0]["timeline"][0]["status"] == "miss"
        assert grupos[0]["timeline"][0]["count"] == 0

    def test_hunter_qualquer_canal_conta_para_meta(self):
        """Hunter aceita QUALQUER tarefa — não só reunião."""
        cnpjs = [_cnpj("G1", "C1", "Patrick")]
        tarefas = [_tarefa("C1", "Patrick", datetime(2026, 5, 15), canal="WhatsApp")]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        assert grupos[0]["meta_atingida"] is True


# ── Meta do Farmer ───────────────────────────────────────────────

class TestMetaFarmer:
    def test_farmer_precisa_de_reuniao_em_todas_semanas_passadas(self):
        """Mês de maio/2026 — semanas ISO tocadas: 18, 19, 20, 21, 22.
        Cobrimos 18..21 (passadas e atual) com reuniões; semana 22 ainda é futura."""
        cnpjs = [_cnpj("G1", "C1", "Beatriz")]
        tarefas = [
            _tarefa("C1", "Beatriz", datetime(2026, 5, 1),  canal="Reunião"),  # sem 18 (sex 01/05)
            _tarefa("C1", "Beatriz", datetime(2026, 5, 4),  canal="Reunião"),  # sem 19
            _tarefa("C1", "Beatriz", datetime(2026, 5, 11), canal="Reunião"),  # sem 20
            _tarefa("C1", "Beatriz", datetime(2026, 5, 18), canal="Reunião"),  # sem 21 (atual)
        ]
        colab = [_colab("Beatriz", "EC_FARMER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)

        timeline = grupos[0]["timeline"]
        # Status das semanas passadas/atual = ok; semanas futuras podem estar 'future'
        status_passados_e_atuais = [c["status"] for c in timeline if c["status"] != "future"]
        assert all(s == "ok" for s in status_passados_e_atuais), \
            f"timeline inesperada: {timeline}"
        assert grupos[0]["reunioes_mes"] == 4

    def test_farmer_sem_reuniao_em_semana_passada_nao_atinge_meta(self):
        cnpjs = [_cnpj("G1", "C1", "Beatriz")]
        # Só uma reunião na primeira semana — outras semanas que já passaram ficam 'miss'
        tarefas = [
            _tarefa("C1", "Beatriz", datetime(2026, 5, 4),  canal="Reunião"),
        ]
        colab = [_colab("Beatriz", "EC_FARMER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)

        timeline = grupos[0]["timeline"]
        # Deve ter pelo menos uma célula com status 'miss' (semana 11/05 passou sem reunião)
        assert any(c["status"] == "miss" for c in timeline)
        assert grupos[0]["meta_atingida"] is False

    def test_farmer_so_canal_reuniao_conta(self):
        """WhatsApp e Telefone não contam — só 'Reunião'."""
        cnpjs = [_cnpj("G1", "C1", "Beatriz")]
        tarefas = [
            _tarefa("C1", "Beatriz", datetime(2026, 5, 4), canal="WhatsApp"),
            _tarefa("C1", "Beatriz", datetime(2026, 5, 11), canal="Telefone"),
        ]
        colab = [_colab("Beatriz", "EC_FARMER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        assert grupos[0]["reunioes_mes"] == 0

    def test_farmer_semana_corrente_sem_reuniao_eh_status_now(self):
        cnpjs = [_cnpj("G1", "C1", "Beatriz")]
        # Reuniões em todas as semanas passadas, nada na semana corrente (19/05)
        tarefas = [
            _tarefa("C1", "Beatriz", datetime(2026, 5, 4),  canal="Reunião"),
            _tarefa("C1", "Beatriz", datetime(2026, 5, 11), canal="Reunião"),
        ]
        colab = [_colab("Beatriz", "EC_FARMER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        timeline = grupos[0]["timeline"]
        # A célula da semana atual deve estar como 'now' (nem ok nem miss ainda)
        assert any(c["status"] == "now" for c in timeline)


# ── Agregados extra ──────────────────────────────────────────────

class TestAgregados:
    def test_qtd_cnpj_e_leads_somados(self):
        cnpjs = [
            _cnpj("G1", "C1", "Ana", leads_no_mes=2),
            _cnpj("G1", "C2", "Ana", leads_no_mes=3),
            _cnpj("G1", "C3", "Ana", leads_no_mes=None),
        ]
        grupos = agregar_grupos(cnpjs, [], [_colab("Ana", "EC_FARMER")], ref_date=REF)
        assert grupos[0]["qtd_cnpj"] == 3
        assert grupos[0]["leads_no_mes"] == 5

    def test_atrasadas_e_futuras_contadas(self):
        cnpjs = [_cnpj("G1", "C1", "Ana")]
        tarefas = [
            _tarefa("C1", "Ana", datetime(2026, 5, 1), situacao="ATRASADA"),
            _tarefa("C1", "Ana", datetime(2026, 5, 1), situacao="ATRASADA"),
            _tarefa("C1", "Ana", datetime(2026, 5, 25), situacao="FUTURA"),
        ]
        grupos = agregar_grupos(cnpjs, tarefas, [_colab("Ana", "EC_HUNTER")], ref_date=REF)
        assert grupos[0]["tarefas_atrasadas"] == 2
        assert grupos[0]["tarefas_futuras"] == 1


# ── Filtros ──────────────────────────────────────────────────────

class TestFiltros:
    def _fixture(self):
        cnpjs = [
            _cnpj("G1", "C1", "Patrick"),
            _cnpj("G2", "C2", "Beatriz"),
            _cnpj("G3", "C3", "Desconhecido"),
        ]
        tarefas = [
            _tarefa("C1", "Patrick", datetime(2026, 5, 10), situacao="ATRASADA"),
            _tarefa("C2", "Beatriz", datetime(2026, 5, 10), canal="Reunião"),
            _tarefa("C2", "Beatriz", datetime(2026, 5, 25), situacao="FUTURA"),
        ]
        colab = [
            _colab("Patrick", "EC_HUNTER"),
            _colab("Beatriz", "EC_FARMER"),
        ]
        return agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)

    def test_filtro_funcao(self):
        grupos = self._fixture()
        hunter = aplicar_filtros(grupos, funcao="EC_HUNTER")
        farmer = aplicar_filtros(grupos, funcao="EC_FARMER")
        outros = aplicar_filtros(grupos, funcao="OUTROS")
        assert len(hunter) == 1 and hunter[0]["id_grupo"] == "G1"
        assert len(farmer) == 1 and farmer[0]["id_grupo"] == "G2"
        assert len(outros) == 1 and outros[0]["id_grupo"] == "G3"

    def test_filtro_tarefa_atrasada(self):
        grupos = self._fixture()
        out = aplicar_filtros(grupos, tarefa_atrasada=True)
        assert len(out) == 1
        assert out[0]["id_grupo"] == "G1"

    def test_filtro_sem_tarefa_futura(self):
        grupos = self._fixture()
        out = aplicar_filtros(grupos, sem_tarefa_futura=True)
        ids = {g["id_grupo"] for g in out}
        # G1 (sem futura) e G3 (sem nenhuma) sim; G2 tem futura → fora
        assert ids == {"G1", "G3"}

    def test_filtro_busca_por_colaborador(self):
        grupos = self._fixture()
        out = aplicar_filtros(grupos, busca="beat")
        assert len(out) == 1
        assert out[0]["colaborador_nome"] == "Beatriz"


# ── KPIs ─────────────────────────────────────────────────────────

class TestKpis:
    def test_kpis_hunter(self):
        cnpjs = [
            _cnpj("G1", "C1", "P", leads_no_mes=5),
            _cnpj("G2", "C2", "P", leads_no_mes=0),
        ]
        tarefas = [_tarefa("C1", "P", datetime(2026, 5, 10))]
        colab = [_colab("P", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        k = kpis_por_funcao(grupos, "EC_HUNTER")
        assert k["total_grupos"] == 2
        assert k["meta_atingida"] == 1
        assert k["compliance_pct"] == 50.0
        assert k["leads_no_mes"] == 5

    def test_kpis_vazio(self):
        k = kpis_por_funcao([], "EC_HUNTER")
        assert k["total_grupos"] == 0
        assert k["compliance_pct"] == 0.0
