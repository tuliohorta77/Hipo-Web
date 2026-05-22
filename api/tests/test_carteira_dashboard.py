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
        """
        Regra v3: tarefas_atrasadas conta GRUPOS afetados, não soma de tarefas.
        Um grupo com 5 atrasadas conta 1.
        """
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick"),
            _cnpj("G2", "22.222.222/0002-22", "Patrick"),
            _cnpj("G3", "33.333.333/0003-33", "Patrick"),  # sem atrasada
        ]
        tarefas = [
            # G1 tem 2 atrasadas (mas conta 1 grupo)
            _tarefa("11.111.111/0001-11", "Patrick", datetime(2026, 5, 1), situacao="ATRASADA"),
            _tarefa("11.111.111/0001-11", "Patrick", datetime(2026, 5, 2), situacao="ATRASADA"),
            # G2 tem 1 atrasada
            _tarefa("22.222.222/0002-22", "Patrick", datetime(2026, 5, 3), situacao="ATRASADA"),
            # G3 sem nada
            # Futura só pra G1
            _tarefa("11.111.111/0001-11", "Patrick", datetime(2026, 6, 30), situacao="FUTURA"),
        ]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, tarefas, colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)

        h = hunter[0]
        # 2 grupos têm ≥1 atrasada (G1 e G2), não 3 tarefas
        assert h["tarefas_atrasadas"] == 2
        # 2 grupos não têm tarefa futura (G2 e G3)
        assert h["sem_tarefa_futura"] == 2

    def test_grupos_inclusos_no_dashboard(self):
        """Hunter v3: cada linha tem o campo 'grupos' com drilldown completo."""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick", contabilidade="Alfa"),
            _cnpj("G2", "22.222.222/0002-22", "Patrick", contabilidade="Beta"),
        ]
        colab = [_colab("Patrick", "EC_HUNTER")]
        grupos = agregar_grupos(cnpjs, [], colab, ref_date=REF)
        hunter = dashboard_hunter(grupos, colab)

        h = hunter[0]
        assert "grupos" in h
        assert len(h["grupos"]) == 2
        nomes = {g["nome_grupo"] for g in h["grupos"]}
        assert nomes == {"Alfa", "Beta"}
        # Schema completo: cada grupo tem timeline, atrasadas, futuras, etc.
        for g in h["grupos"]:
            assert "timeline" in g
            assert "tarefas_atrasadas" in g
            assert "tarefas_futuras" in g
            assert "leads_no_mes" in g

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

    def test_total_grupos_e_contadores_e_quatro_semanas(self):
        """
        v4: 'total_grupos' é o primário (bolinhas contam grupos).
        'total_contadores' é preservado pro subtítulo.
        """
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
            _cnpj("G3", "33.333.333/0003-33", "Aline"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, [], colab, ref_date=REF)
        assert len(farmer) == 1
        a = farmer[0]
        # 3 grupos com 1 CNPJ cada — total_grupos == total_contadores nesse caso
        assert a["total_grupos"] == 3
        assert a["total_contadores"] == 3
        # Maio/2026 toca 5 semanas ISO (W18 a W22), pode variar
        assert len(a["semanas"]) >= 4
        assert all("S" in s["label"] for s in a["semanas"])

    def test_com_reuniao_conta_grupos_distintos_nao_reunioes(self):
        """
        v4: bolinha verde mostra GRUPOS que reuniram, não nº de reuniões.
        Múltiplas reuniões no mesmo grupo (mesmo CNPJ) na semana = 1 grupo.
        """
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
        ]
        # Mesmo CNPJ tem 3 reuniões na mesma semana — conta 1 grupo
        tarefas = [
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 4), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 5), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 6), canal="Reunião"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        # Semana W19 (04 a 10 de maio): só G1 reuniu — 1 grupo no verde
        s_W19 = next(s for s in a["semanas"] if s["key"] == "2026-W19")
        assert s_W19["com_reuniao"] == 1
        # G2 não teve reunião e a semana já passou → sem_reuniao
        assert s_W19["sem_reuniao"] == 1

    def test_semana_corrente_usa_pendente_nao_sem_reuniao(self):
        """
        Semana corrente (W21 em 19/maio/2026) não pode marcar grupo
        como 'sem_reuniao' porque a semana ainda está rolando — vai pra
        'pendente'.
        """
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
        ]
        # Só um grupo reuniu na semana corrente
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
        """
        Regra v3: tarefas_atrasadas/futuras contam GRUPOS afetados, não tarefas.
        Leads continua sendo soma.
        """
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline", leads_no_mes=5),
            _cnpj("G2", "22.222.222/0002-22", "Aline", leads_no_mes=7),
        ]
        tarefas = [
            # G1: 1 atrasada
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 1), situacao="ATRASADA"),
            # G2: 1 atrasada
            _tarefa("22.222.222/0002-22", "Aline", datetime(2026, 5, 2), situacao="ATRASADA"),
            # G1: 1 futura
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 6, 30), situacao="FUTURA"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        # 2 grupos têm ≥1 atrasada
        assert a["tarefas_atrasadas"] == 2
        # 1 grupo tem ≥1 futura (G1)
        assert a["tarefas_futuras"] == 1
        # leads continua soma
        assert a["leads_no_mes"] == 12

    def test_grupos_inclusos_no_dashboard_farmer(self):
        """Farmer v3: cada linha tem 'grupos' detalhados (drilldown)."""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline", nome_grupo="Alfa"),
            _cnpj("G2", "22.222.222/0002-22", "Aline", nome_grupo="Beta"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, [], colab, ref_date=REF)
        a = farmer[0]

        assert "grupos" in a
        assert "total_grupos" in a
        assert a["total_grupos"] == 2
        assert len(a["grupos"]) == 2
        # Timeline semanal vem em cada grupo
        for g in a["grupos"]:
            assert "timeline" in g
            # Farmer tem ≥4 células (semanas ISO do mês)
            assert len(g["timeline"]) >= 4

    def test_multiplas_reunioes_mesmo_grupo_semana_contam_1_vez(self):
        """
        Regra travada: grupo com 50 reuniões em 1 semana (mesmo CNPJ ou
        CNPJs diferentes do mesmo grupo) entra UMA vez no verde. Esse é
        o bug que o franqueado pegou em produção (Patrick com 95 'bolinhas'
        pra 51 grupos).
        """
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
        ]
        # 10 reuniões na MESMA semana, MESMO CNPJ — deve contar 1 grupo no verde
        tarefas = [
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 4), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 5), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 6), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 7), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 8), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 4), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 5), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 6), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 7), canal="Reunião"),
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 5, 8), canal="Reunião"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        s_W19 = next(s for s in a["semanas"] if s["key"] == "2026-W19")
        # Apesar das 10 reuniões, conta 1 grupo no verde
        assert s_W19["com_reuniao"] == 1
        # G2 não reuniu nessa semana E ela já passou → sem_reuniao
        assert s_W19["sem_reuniao"] == 1
        # Invariante mantida: soma == total_grupos
        assert s_W19["com_reuniao"] + s_W19["sem_reuniao"] + s_W19["pendente"] == 2

    def test_qualquer_cnpj_do_grupo_reuniao_conta_o_grupo_no_verde(self):
        """
        Regra v4 (chave): se um grupo tem 3 CNPJs (matriz + 2 filiais) e só
        UM CNPJ reuniu na semana, o GRUPO inteiro entra UMA vez no verde.
        Cenário exato da Aline com o grupo ABC.
        """
        cnpjs = [
            # Grupo ABC: matriz + 2 filiais (3 CNPJs)
            _cnpj("ABC", "11.111.111/0001-11", "Aline", nome_grupo="ABC"),
            _cnpj("ABC", "11.111.111/0002-22", "Aline", nome_grupo="ABC"),
            _cnpj("ABC", "11.111.111/0003-33", "Aline", nome_grupo="ABC"),
            # Grupo XYZ: 1 CNPJ
            _cnpj("XYZ", "22.222.222/0001-11", "Aline", nome_grupo="XYZ"),
        ]
        # Na W19, só a "filial 2" do grupo ABC reuniu
        tarefas = [
            _tarefa("11.111.111/0002-22", "Aline", datetime(2026, 5, 5), canal="Reunião"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        # 2 grupos no total (ABC + XYZ), apesar de 4 CNPJs
        assert a["total_grupos"] == 2
        assert a["total_contadores"] == 4

        s_W19 = next(s for s in a["semanas"] if s["key"] == "2026-W19")
        # ABC reuniu via filial 2 → conta 1 grupo no verde
        assert s_W19["com_reuniao"] == 1
        # XYZ não reuniu → sem_reuniao (W19 já passou no REF=19/maio)
        assert s_W19["sem_reuniao"] == 1
        # Invariante: soma == total_grupos
        assert s_W19["com_reuniao"] + s_W19["sem_reuniao"] + s_W19["pendente"] == 2

    def test_soma_bolinhas_nunca_excede_total_grupos(self):
        """
        Invariante crítica v4: a soma das bolinhas de uma semana é sempre
        igual a total_grupos. Esse era o sintoma do bug (Patrick: 95 bolinhas
        pra 51 grupos — agora bate exatamente).
        """
        cnpjs = [
            _cnpj(f"G{i}", f"{i:02d}.000.000/0001-00", "Aline")
            for i in range(1, 6)
        ]
        # Várias reuniões pra cada CNPJ na mesma semana
        tarefas = []
        for i in range(1, 6):
            cnpj = f"{i:02d}.000.000/0001-00"
            for _ in range(5):
                tarefas.append(_tarefa(cnpj, "Aline", datetime(2026, 5, 4), canal="Reunião"))

        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, tarefas, colab, ref_date=REF)
        a = farmer[0]
        assert a["total_grupos"] == 5
        for s in a["semanas"]:
            soma = s["com_reuniao"] + s["sem_reuniao"] + s["pendente"]
            assert soma == 5, (
                f"Semana {s['label']}: soma {soma} != total_grupos 5. "
                f"({s})"
            )

    def test_soma_de_bolinhas_iguala_total_grupos(self):
        """Invariante crítica v4: com_reuniao + sem_reuniao + pendente == total_grupos"""
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "22.222.222/0002-22", "Aline"),
            _cnpj("G3", "33.333.333/0003-33", "Aline"),
            _cnpj("G4", "44.444.444/0004-44", "Aline"),
            _cnpj("G5", "55.555.555/0005-55", "Aline"),
        ]
        tarefas = [
            # W18 (28/abr a 03/mai): 2 grupos reuniram
            _tarefa("11.111.111/0001-11", "Aline", datetime(2026, 4, 30), canal="Reunião"),
            _tarefa("22.222.222/0002-22", "Aline", datetime(2026, 5, 1), canal="Reunião"),
            # W19 (04 a 10): todos os 5 grupos
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
            assert total == a["total_grupos"], (
                f"Semana {s['label']} ({s['key']}): "
                f"com={s['com_reuniao']} sem={s['sem_reuniao']} pend={s['pendente']} "
                f"!= total_grupos {a['total_grupos']}"
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

    def test_grupos_distintos_apesar_de_mesmo_cnpj(self):
        """
        Cenário marginal: mesmo CNPJ aparecendo em 2 grupos diferentes
        da Aline. Conta como 2 grupos (são unidades de trabalho separadas)
        e 1 contador único.
        """
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Aline"),
            _cnpj("G2", "11.111.111/0001-11", "Aline"),  # mesmo CNPJ, outro grupo
            _cnpj("G3", "22.222.222/0002-22", "Aline"),
        ]
        colab = [_colab("Aline", "EC_FARMER")]
        farmer = dashboard_farmer(cnpjs, [], colab, ref_date=REF)
        a = farmer[0]
        # 3 grupos (G1, G2, G3) mas só 2 CNPJs distintos
        assert a["total_grupos"] == 3
        assert a["total_contadores"] == 2


# ── grupos_do_colaborador (drilldown) ────────────────────────────

class TestGruposDoColaborador:
    def test_filtra_grupos_do_colaborador_informado(self):
        cnpjs = [
            _cnpj("G1", "11.111.111/0001-11", "Patrick", contabilidade="Alfa"),
            _cnpj("G2", "22.222.222/0002-22", "Caio", contabilidade="Beta"),
            _cnpj("G3", "33.333.333/0003-33", "Patrick", contabilidade="Gamma"),
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
