"""
HIPO — Testes dos endpoints de Dashboard da Carteira (v2).

Foco:
  - GET /carteira/dashboard/hunter
  - GET /carteira/dashboard/farmer
  - GET /carteira/colaboradores/{id}/grupos

Estes testes dependem das mesmas fixtures dos outros testes de router
(db_conn, client, usuario_adm) — definidas em conftest.py.
"""
from datetime import datetime
from uuid import uuid4


# ── Helpers de seeding ───────────────────────────────────────────

async def _seed_colaborador(db_conn, nome: str, funcao: str) -> str:
    """Insere um colaborador na carteira. Retorna o UUID."""
    row = await db_conn.fetchrow(
        """
        INSERT INTO carteira_colaborador (nome, funcao, ativo)
        VALUES ($1, $2::carteira_funcao_enum, TRUE)
        RETURNING id
        """,
        nome, funcao,
    )
    return str(row["id"])


async def _seed_upload(db_conn, tipo: str, usuario_email: str) -> str:
    """Cria um upload pra poder amarrar carteira_cnpj/tarefa nele."""
    u_id = await db_conn.fetchval(
        "SELECT id FROM usuarios WHERE email = $1", usuario_email
    )
    row = await db_conn.fetchrow(
        """
        INSERT INTO carteira_upload
            (tipo, usuario_id, nome_arquivo, total_linhas, total_validos, processado)
        VALUES ($1, $2, 'seed.xlsx', 1, 1, TRUE)
        RETURNING id
        """,
        tipo, u_id,
    )
    return str(row["id"])


async def _seed_cnpj(db_conn, upload_id: str, id_grupo: str, cnpj: str,
                     colaborador_nome: str, nome_grupo: str = "Grupo X",
                     leads_no_mes: int = 0):
    await db_conn.execute(
        """
        INSERT INTO carteira_cnpj (
            upload_id, id_grupo, nome_grupo, cnpj_contador, contabilidade,
            cidade_uf, parceria, tipo_cnae, colaborador_nome,
            funcao_origem, leads_no_mes
        )
        VALUES ($1, $2, $3, $4, 'Contab X', 'SP/SP', 'Parceiro',
                'CNAE Contábil', $5, 'Executivo de Contas - FR', $6)
        """,
        upload_id, id_grupo, nome_grupo, cnpj, colaborador_nome, leads_no_mes,
    )


async def _seed_tarefa(db_conn, upload_id: str, cnpj: str,
                       data_efetiva: datetime, canal: str | None = None,
                       situacao: str = "EM_DIA"):
    await db_conn.execute(
        """
        INSERT INTO carteira_tarefa (
            upload_id, cnpj_contador, executivo_nome, situacao, status,
            tarefa_canal, data_criacao, data_agendamento, data_efetiva
        )
        VALUES ($1, $2, 'Executivo', $3::tarefa_situacao_enum,
                'Concluído', $4, $5, $5, $5)
        """,
        upload_id, cnpj, situacao, canal, data_efetiva,
    )


# ── DASHBOARD HUNTER ─────────────────────────────────────────────

class TestDashboardHunter:
    async def test_sem_autenticacao_retorna_401(self, client):
        resp = await client.get("/carteira/dashboard/hunter")
        assert resp.status_code == 401

    async def test_retorna_estrutura_basica_vazia(self, db_conn, client, usuario_adm):
        resp = await client.get(
            "/carteira/dashboard/hunter",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "linhas" in data
        assert data["total"] == 0
        assert data["linhas"] == []

    async def test_lista_colaboradores_hunter_com_kpis(self, db_conn, client, usuario_adm):
        upload_c = await _seed_upload(db_conn, "CARTEIRA", "adm@teste.com")
        upload_t = await _seed_upload(db_conn, "TAREFAS", "adm@teste.com")

        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        await _seed_colaborador(db_conn, "Caio", "EC_HUNTER")
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")

        # Patrick: 2 grupos, 1 com tarefa no mês
        await _seed_cnpj(db_conn, upload_c, "P_G1", "11.111.111/0001-11",
                         "Patrick", leads_no_mes=3)
        await _seed_cnpj(db_conn, upload_c, "P_G2", "11.222.333/0001-22",
                         "Patrick", leads_no_mes=2)
        await _seed_tarefa(db_conn, upload_t, "11.111.111/0001-11",
                           datetime.now().replace(day=15))

        # Caio: 1 grupo, sem tarefa no mês
        await _seed_cnpj(db_conn, upload_c, "C_G1", "22.222.222/0002-22",
                         "Caio", leads_no_mes=1)

        # Aline: 1 grupo (Farmer, não deve aparecer no dashboard Hunter)
        await _seed_cnpj(db_conn, upload_c, "A_G1", "33.333.333/0003-33",
                         "Aline")

        resp = await client.get(
            "/carteira/dashboard/hunter",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()

        nomes = {l["nome"] for l in data["linhas"]}
        assert nomes == {"Patrick", "Caio"}

        por_nome = {l["nome"]: l for l in data["linhas"]}
        assert por_nome["Patrick"]["total_grupos"] == 2
        assert por_nome["Patrick"]["meta_atingida"] == 1
        assert por_nome["Patrick"]["leads_no_mes"] == 5

        assert por_nome["Caio"]["total_grupos"] == 1
        assert por_nome["Caio"]["meta_atingida"] == 0

        # v3: cada linha vem com os grupos pra drilldown imediato (sem refetch)
        assert "grupos" in por_nome["Patrick"]
        assert len(por_nome["Patrick"]["grupos"]) == 2
        nomes_grupos = {g["nome_grupo"] for g in por_nome["Patrick"]["grupos"]}
        assert nomes_grupos == {"Grupo X"}  # default do _seed_cnpj


# ── DASHBOARD FARMER ─────────────────────────────────────────────

class TestDashboardFarmer:
    async def test_sem_autenticacao_retorna_401(self, client):
        resp = await client.get("/carteira/dashboard/farmer")
        assert resp.status_code == 401

    async def test_retorna_estrutura_basica_vazia(self, db_conn, client, usuario_adm):
        resp = await client.get(
            "/carteira/dashboard/farmer",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["linhas"] == []

    async def test_lista_colaboradores_farmer_com_semanas(
        self, db_conn, client, usuario_adm
    ):
        upload_c = await _seed_upload(db_conn, "CARTEIRA", "adm@teste.com")
        upload_t = await _seed_upload(db_conn, "TAREFAS", "adm@teste.com")

        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")
        await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")

        # Aline: 3 contadores
        await _seed_cnpj(db_conn, upload_c, "A_G1", "11.111.111/0001-11",
                         "Aline", leads_no_mes=5)
        await _seed_cnpj(db_conn, upload_c, "A_G2", "22.222.222/0002-22",
                         "Aline", leads_no_mes=3)
        await _seed_cnpj(db_conn, upload_c, "A_G3", "33.333.333/0003-33",
                         "Aline", leads_no_mes=2)

        # Patrick (Hunter): não deve aparecer
        await _seed_cnpj(db_conn, upload_c, "P_G1", "44.444.444/0004-44",
                         "Patrick")

        # 2 reuniões da Aline esta semana (do mesmo CNPJ — deve contar como 1)
        agora = datetime.now()
        await _seed_tarefa(db_conn, upload_t, "11.111.111/0001-11",
                           agora, canal="Reunião")
        await _seed_tarefa(db_conn, upload_t, "11.111.111/0001-11",
                           agora, canal="Reunião")

        resp = await client.get(
            "/carteira/dashboard/farmer",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()

        nomes = {l["nome"] for l in data["linhas"]}
        assert nomes == {"Aline"}

        aline = data["linhas"][0]
        assert aline["total_contadores"] == 3
        assert aline["leads_no_mes"] == 10
        assert len(aline["semanas"]) >= 4

        # Invariante: soma == total_contadores em cada semana
        for s in aline["semanas"]:
            assert s["com_reuniao"] + s["sem_reuniao"] + s["pendente"] == 3

        # v3: linha já traz os grupos pro drilldown imediato
        assert "grupos" in aline
        assert "total_grupos" in aline
        assert aline["total_grupos"] == 3


# ── DRILLDOWN: grupos do colaborador ────────────────────────────

class TestDrilldownColaborador:
    async def test_sem_autenticacao_retorna_401(self, client):
        resp = await client.get(f"/carteira/colaboradores/{uuid4()}/grupos")
        assert resp.status_code == 401

    async def test_id_invalido_retorna_400(self, client, usuario_adm):
        resp = await client.get(
            "/carteira/colaboradores/nao-eh-uuid/grupos",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 400

    async def test_colaborador_inexistente_retorna_404(self, client, usuario_adm):
        resp = await client.get(
            f"/carteira/colaboradores/{uuid4()}/grupos",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 404

    async def test_retorna_grupos_do_colaborador(
        self, db_conn, client, usuario_adm
    ):
        upload_c = await _seed_upload(db_conn, "CARTEIRA", "adm@teste.com")
        patrick_id = await _seed_colaborador(db_conn, "Patrick", "EC_HUNTER")
        await _seed_colaborador(db_conn, "Caio", "EC_HUNTER")

        await _seed_cnpj(db_conn, upload_c, "P_G1", "11.111.111/0001-11",
                         "Patrick", nome_grupo="Alfa")
        await _seed_cnpj(db_conn, upload_c, "P_G2", "22.222.222/0002-22",
                         "Patrick", nome_grupo="Gamma")
        # Caio — não deve aparecer no drilldown do Patrick
        await _seed_cnpj(db_conn, upload_c, "C_G1", "33.333.333/0003-33",
                         "Caio", nome_grupo="Beta")

        resp = await client.get(
            f"/carteira/colaboradores/{patrick_id}/grupos",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["colaborador"]["nome"] == "Patrick"
        assert data["colaborador"]["funcao"] == "EC_HUNTER"
        assert data["total"] == 2

        nomes_grupos = {g["nome_grupo"] for g in data["grupos"]}
        assert nomes_grupos == {"Alfa", "Gamma"}
