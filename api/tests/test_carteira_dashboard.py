"""
HIPO — Testes do dashboard de carteira (por colaborador).

Foco:
  - dashboard_hunter: 1 linha por colaborador EC_HUNTER agregando seus grupos.
  - dashboard_farmer: 1 linha por colaborador EC_FARMER com colunas semanais
    contendo com_reuniao / sem_reuniao / pendente (semana corrente vs passada).
  - grupos_do_colaborador: drilldown filtrando os grupos do colaborador.
"""
from datetime import date, datetime
from uuid import uuid4

from services.carteira_agg import (
    agregar_grupos,
    dashboard_hunter,
    dashboard_farmer,
    grupos_do_colaborador,
)


# Mesma data de referência dos testes existentes — terça 19/maio/2026.
# A semana ISO dessa data é W21. As 4 últimas semanas do mês de maio/2026
# que tocam o calendário são W18, W19, W20, W21 (W21 = corrente).
REF = date(2026, 5, 19)


# ── Builders ─────────────────────────────────────────────────────

def _cnpj(id_grupo, cnpj, colaborador, **kwargs):
    base = {
        "id_grupo": id_grupo,
        "nome_grupo": kwargs.get("nome_grupo", "Grupo X"),
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
    base.update({k: v for k, v in kwargs.items() if k != "nome_grupo"})
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


def _colab(nome, funcao, id_=None):
    return {"id": id_ or uuid4(), "nome": nome, "funcao": funcao}


# ── DASHBOARD HUNTER ─────────────────────────────────────────────

class TestDashboardHunter:
    def test_uma_linha_por_colaborador_hunter(self):
        """Cada colaborador Hunter vira uma linha; Farmer/Outros não entram."""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick"),
            _cnpj("G2", "22.222.222/0002-22", "Patrick"),
            _cnpj("G3", "33.333.333/0003-33", "Caio"),
            _cnpj("G4", "44.444.444/0004-44", "Aline"),    # Farmer, fora
            _cnpj("G5", "55.555.555/0005-55", "Marcos"),   # Outros, fora
        ]
        colab = [
            _colab("Patrick", "EC_HUNTER"),
            _colab("Caio", "EC_HUNTER"),
            _colab("Aline", "EC_FARMER"),
            _colab("Marcos", "OUTROS"),
        ]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)

        nomes = {h["nome"] for h in hunter}
        assert nomes == {"Patrick", "Caio"}

    def test_total_grupos_por_colaborador(self):
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick"),
            _cnpj("G2", "22.222.222/0002-22", "Patrick"),
            _cnpj("G3", "33.333.333/0003-33", "Patrick"),
            _cnpj("G4", "44.444.444/0004-44", "Caio"),
        ]
        colab = [_colab("Patrick", "EC_HUNTER"), _colab("Caio", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)

        por_nome = {h["nome"]: h for h in hunter}
        assert por_nome["Patrick"]["total_grupos"] == 3
        assert por_nome["Caio"]["total_grupos"] == 1

    def test_meta_atingida_conta_grupos_com_tarefa_no_mes(self):
        """Hunter precisa de ≥1 tarefa no mês corrente para bater meta."""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick"),  # com tarefa no mês → meta
            _cnpj("G2", "22.222.222/0002-22", "Patrick"),  # sem tarefa → sem meta
            _cnpj("G3", "33.333.333/0003-33", "Patrick"),  # com tarefa no mês → meta
        ]
        tarefas = [
            _tarefa("11.111.111/0001-11", "Patrick", datetime(2026, 5, 10)),
            _tarefa("33.333.333/0003-33", "Patrick", datetime(2026, 5, 15)),
        ]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)

        assert len(hunter) == 1
        h = hunter[0]
        assert h["total_grupos"] == 3
        assert h["meta_atingida"] == 2
        assert h["compliance_pct"] == round(2 / 3 * 100, 1)

    def test_tarefas_atrasadas_e_sem_futura(self):
        """Soma atrasadas e conta grupos sem tarefa futura."""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick"),
            _cnpj("G2", "22.222.222/0002-22", "Patrick"),
        ]
        tarefas = [
            _tarefa("11.111.111/0001-11", "Patrick", datetime(2026, 5, 1), situacao="ATRASADA"),
            _tarefa("11.111.111/0001-11", "Patrick", datetime(2026, 5, 2), situacao="ATRASADA"),
            _tarefa("11.111.111/0001-11", "Patrick", datetime(2026, 6, 30), situacao="FUTURA"),
            # G2 não tem nenhuma tarefa futura
        ]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)

        h = hunter[0]
        assert h["tarefas_atrasadas"] == 2  # soma das atrasadas dos 2 grupos
        assert h["sem_tarefa_futura"] == 1  # só G2 não tem futura

    def test_leads_no_mes_somados(self):
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick", leads_no_mes=3),
            _cnpj("G2", "22.222.222/0002-22", "Patrick", leads_no_mes=5),
        ]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)
        assert hunter[0]["leads_no_mes"] == 8

    def test_ordenacao_compliance_descendente(self):
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick"),  # 1/1 = 100%
            _cnpj("G2", "22.222.222/0002-22", "Caio"),     # 0/1 = 0%
            _cnpj("G3", "33.333.333/0003-33", "Marina"),   # 1/2 = 50%
            _cnpj("G4", "44.444.444/0004-44", "Marina"),
        ]
        tarefas = [
            _tarefa("11.111.111/0001-11", "Patrick", datetime(2026, 5, 10)),
            _tarefa("33.333.333/0003-33", "Marina", datetime(2026, 5, 10)),
        ]
        colab = [
            _colab("Patrick", "EC_HUNTER"),
            _colab("Caio", "EC_HUNTER"),
            _colab("Marina", "EC_HUNTER"),
        ]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)
        nomes_ordem = [h["nome"] for h in hunter]
        assert nomes_ordem == ["Patrick", "Marina", "Caio"]

    def test_colaborador_id_devolve_uuid_em_texto(self):
        cid = uuid4()
        cnpjs = [_cnpj("G1", "11.111.111/0001-11", "Patrick")]
        colab = [_colab("Patrick", "EC_HUNTER", id_=cid)]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)
        assert hunter[0]["colaborador_id"] == str(cid)


# ── DASHBOARD FARMER ─────────────────────────────────────────────

class TestDashboardFarmer:
    def test_so_inclui_colaboradores_farmer(self):
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Patrick"),
            _cnpj("G3", "33.333.333/0003-33", "Marcos"),
        ]
        colab = [
            _colab("Aline", "EC_FARMER"),
            _colab("Patrick", "EC_HUNTER"),
            _colab("Marcos", "OUTROS"),
        ]
        farmer = dashboard_farmer(cnpjs, [], colab, ref_date=REF)
        nomes = {f["nome"] for f in farmer}
        assert nomes == {"Aline"}

    def test_total_contadores_e_quatro_semanas(self):
        """Cada CNPJ é um contador. Resultado tem 4 semanas (maio/2026)."""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
            _cnpj("G3", "33.333.333/0003-33", "Aline"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, [], colab, ref_date=REF)
        assert len(farmer) == 1
        a = farmer[0]
        assert a["total_contadores"] == 3
        # Maio/2026 toca 5 semanas ISO (W18 a W22), pode variar
        assert len(a["semanas"]) >= 4
        assert all("S" in s["label"] for s in a["semanas"])

    def test_com_reuniao_conta_contadores_distintos_nao_reunioes(self):
        """Bolinha verde mostra CONTADORES que reuniram, não nº de reuniões."""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
        ]
        # Mesmo CNPJ tem 3 reuniões na mesma semana — ainda conta como 1 contador
        tarefas = [
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 4), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 5), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 6), canal="Reunião"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        # Semana W19 (04 a 10 de maio) deve ter 1 com_reuniao (CNPJ 11.111…)
        s_W19 = next(s for s in a["semanas"] if s["key"] == "2026-W19")
        assert s_W19["com_reuniao"] == 1
        # CNPJ 22.222… não teve reunião nessa semana e ela já passou → sem_reuniao
        assert s_W19["sem_reuniao"] == 1

    def test_semana_corrente_usa_pendente_nao_sem_reuniao(self):
        """
        Semana corrente (W21 em 19/maio/2026) não pode marcar contador
        como 'sem_reuniao' porque a semana ainda está rolando — vai pra
        'pendente'.
        """
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
        ]
        # Só um contador reuniu na semana corrente
        tarefas = [
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 18), canal="Reunião"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        s_W21 = next(s for s in a["semanas"] if s["key"] == "2026-W21")
        assert s_W21["com_reuniao"] == 1
        assert s_W21["sem_reuniao"] == 0
        assert s_W21["pendente"] == 1

    def test_semana_passada_zera_pendente(self):
        """Semana já encerrada não tem 'pendente'."""
        cnpjs = [_cnpj("G1", "11.111.111/0001-11", "Aline")]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, [], colab, ref_date=REF)
        a = farmer[0]
        s_W18 = next(s for s in a["semanas"] if s["key"] == "2026-W18")
        assert s_W18["pendente"] == 0
        # E como não teve reunião, é sem_reuniao
        assert s_W18["sem_reuniao"] == 1

    def test_soma_atrasadas_futuras_leads(self):
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline", leads_no_mes=5),
            _cnpj("G2", "22.222.222/0002-22", "Aline", leads_no_mes=7),
        ]
        tarefas = [
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 1), situacao="ATRASADA"),
            _tarefa("22.222.222/0002-22", "Aline", datetime(2026, 5, 2), situacao="ATRASADA"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 6, 30), situacao="FUTURA"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        assert a["tarefas_atrasadas"] == 2
        assert a["tarefas_futuras"] == 1
        assert a["leads_no_mes"] == 12

    def test_soma_de_bolinhas_iguala_total_contadores(self):
        """Invariante crítica: com_reuniao + sem_reuniao + pendente == total_contadores"""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
            _cnpj("G3", "33.333.333/0003-33", "Aline"),
            _cnpj("G4", "44.444.444/0004-44", "Aline"),
            _cnpj("G5", "55.555.555/0005-55", "Aline"),
        ]
        tarefas = [
            # W18 (28/abr a 03/mai): 2 contadores reuniram
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 4, 30), canal="Reunião"),
            _tarefa("22.222.222/0002-22", "Aline", datetime(2026, 5, 1), canal="Reunião"),
            # W19 (04 a 10): todos os 5 contadores
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 4), canal="Reunião"),
            _tarefa("22.222.222/0002-22", "Aline", datetime(2026, 5, 5), canal="Reunião"),
            _tarefa("33.333.333/0003-33", "Aline", datetime(2026, 5, 6), canal="Reunião"),
            _tarefa("44.444.444/0004-44", "Aline", datetime(2026, 5, 7), canal="Reunião"),
            _tarefa("55.555.555/0005-55", "Aline", datetime(2026, 5, 8), canal="Reunião"),
            # W21 (corrente): 1 reuniu
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 18), canal="Reunião"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        for s in a["semanas"]:
            total = s["com_reuniao"] + s["sem_reuniao"] + s["pendente"]
            assert total == a["total_contadores"], (
                f"Semana {s['label']} ({s['key']}): "
                f"com={s['com_reuniao']} sem={s['sem_reuniao']} pend={s['pendente']} "
                f"!= total {a['total_contadores']}"
            )

    def test_tarefa_que_nao_eh_reuniao_nao_conta(self):
        """Hunter conta qualquer tarefa, mas Farmer só conta 'Reunião'."""
        cnpjs = [_cnpj("G1", "11.111.111/0001-11", "Aline")]
        tarefas = [
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 18), canal="Ligação"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 19), canal="WhatsApp"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        s_W21 = next(s for s in a["semanas"] if s["key"] == "2026-W21")
        # Não houve reunião → contador fica pendente (semana corrente)
        assert s_W21["com_reuniao"] == 0
        assert s_W21["pendente"] == 1

    def test_cnpj_repetido_em_grupos_diferentes_conta_uma_vez(self):
        """Mesmo CNPJ aparecendo em 2 grupos do mesmo colaborador = 1 contador."""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "11.111.111/0001-11", "Aline"),  # mesmo CNPJ, outro grupo
            _cnpj("G3", "22.222.222/0002-22", "Aline"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, [], colab, ref_date=REF)
        a = farmer[0]
        assert a["total_contadores"] == 2


# ── grupos_do_colaborador (drilldown) ────────────────────────────

class TestGruposDoColaborador:
    def test_filtra_grupos_do_colaborador_informado(self):
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick", nome_grupo="Alfa"),
            _cnpj("G2", "22.222.222/0002-22", "Caio", nome_grupo="Beta"),
            _cnpj("G3", "33.333.333/0003-33", "Patrick", nome_grupo="Gamma"),
        ]
        colab = [_colab("Patrick", "EC_HUNTER"), _colab("Caio", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)

        do_patrick = grupos_do_colaborador(grupos, "Patrick")
        nomes = sorted(g["nome_grupo"] for g in do_patrick)
        assert nomes == ["Alfa", "Gamma"]

    def test_colaborador_inexistente_retorna_vazio(self):
        cnpjs = [_cnpj("G1", "11.111.111/0001-11", "Patrick")]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        assert grupos_do_colaborador(grupos, "Inexistente") == []
