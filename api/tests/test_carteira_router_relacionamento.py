"""
HIPO — Testes do Commit 2b da v1.3.0: endpoint /carteira/relacionamento.

Cobre:
  - services.carteira_relacionamento.cruzar_bastoes_com_grupos (service puro)
  - GET /carteira/relacionamento (endpoint, com ?hunter= e controle de acesso)

Depende das fixtures de conftest.py (db_conn, client, usuario_adm).
"""
import bcrypt
from datetime import date

from services.carteira_relacionamento import cruzar_bastoes_com_grupos


# ─────────────────────────────────────────────────────────────────
#  PARTE 1 — service puro (sem banco, sem FastAPI)
# ─────────────────────────────────────────────────────────────────

class TestCruzamentoServicePuro:
    def test_so_bastao_aprovado_conta(self):
        bastoes = [
            {"status": "APROVADO", "cnpj_contador": "11.111.111/0001-11"},
            {"status": "PENDENTE", "cnpj_contador": "22.222.222/0002-22"},
            {"status": "REJEITADO", "cnpj_contador": "33.333.333/0003-33"},
        ]
        grupos = [
            {"id_grupo": "G1", "cnpjs": ["11.111.111/0001-11"],
             "colaborador_nome": "Aline", "tarefas_atrasadas": 0,
             "tarefas_futuras": 0, "leads_no_mes": 0, "meta_atingida": True},
            {"id_grupo": "G2", "cnpjs": ["22.222.222/0002-22"],
             "colaborador_nome": "Aline", "tarefas_atrasadas": 0,
             "tarefas_futuras": 0, "leads_no_mes": 0, "meta_atingida": True},
        ]
        res = cruzar_bastoes_com_grupos(bastoes, grupos)
        # Só G1 casa (bastão aprovado). G2 é de bastão pendente -> não entra.
        ids = {g["id_grupo"] for g in res["grupos"]}
        assert ids == {"G1"}

    def test_cnpj_casado_ignora_mascara(self):
        # bastão sem máscara, grupo com máscara — devem casar
        bastoes = [{"status": "APROVADO", "cnpj_contador": "11111111000111"}]
        grupos = [
            {"id_grupo": "G1", "cnpjs": ["11.111.111/0001-11"],
             "colaborador_nome": "Aline", "tarefas_atrasadas": 0,
             "tarefas_futuras": 0, "leads_no_mes": 0, "meta_atingida": True},
        ]
        res = cruzar_bastoes_com_grupos(bastoes, grupos)
        assert len(res["grupos"]) == 1

    def test_bastao_sem_grupo_vira_aviso(self):
        bastoes = [
            {"status": "APROVADO", "cnpj_contador": "99.999.999/0009-99",
             "contabilidade": "Contab Fantasma"},
        ]
        grupos = []  # nenhum grupo Farmer
        res = cruzar_bastoes_com_grupos(bastoes, grupos)
        assert res["grupos"] == []
        assert len(res["bastoes_sem_grupo"]) == 1
        assert res["bastoes_sem_grupo"][0]["cnpj_contador"] == "99.999.999/0009-99"

    def test_kpis_agregados(self):
        bastoes = [
            {"status": "APROVADO", "cnpj_contador": "11.111.111/0001-11"},
            {"status": "APROVADO", "cnpj_contador": "22.222.222/0002-22"},
        ]
        grupos = [
            {"id_grupo": "G1", "cnpjs": ["11.111.111/0001-11"],
             "colaborador_nome": "Aline", "tarefas_atrasadas": 2,
             "tarefas_futuras": 0, "leads_no_mes": 5, "meta_atingida": False},
            {"id_grupo": "G2", "cnpjs": ["22.222.222/0002-22"],
             "colaborador_nome": "Aline", "tarefas_atrasadas": 0,
             "tarefas_futuras": 1, "leads_no_mes": 3, "meta_atingida": True},
        ]
        res = cruzar_bastoes_com_grupos(bastoes, grupos)
        assert res["kpis"]["total_grupos"] == 2
        assert res["kpis"]["com_atrasada"] == 1   # só G1
        assert res["kpis"]["com_futura"] == 1     # só G2
        assert res["kpis"]["leads"] == 8          # 5 + 3

    def test_grupo_anexa_farmer_nome(self):
        bastoes = [{"status": "APROVADO", "cnpj_contador": "11.111.111/0001-11"}]
        grupos = [
            {"id_grupo": "G1", "cnpjs": ["11.111.111/0001-11"],
             "colaborador_nome": "Aline Martins", "tarefas_atrasadas": 0,
             "tarefas_futuras": 0, "leads_no_mes": 0, "meta_atingida": True},
        ]
        res = cruzar_bastoes_com_grupos(bastoes, grupos)
        assert res["grupos"][0]["_farmer_nome"] == "Aline Martins"

    def test_sem_bastao_aprovado_retorna_vazio(self):
        res = cruzar_bastoes_com_grupos([], [])
        assert res["grupos"] == []
        assert res["bastoes_sem_grupo"] == []
        assert res["kpis"]["total_grupos"] == 0


# ─────────────────────────────────────────────────────────────────
#  PARTE 2 — endpoint /carteira/relacionamento
# ─────────────────────────────────────────────────────────────────

# ── Helpers de seeding ───────────────────────────────────────────

async def _login(client, db_conn, nome: str, email: str, cargo: str) -> dict:
    senha = "test123"
    pwd_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
    row = await db_conn.fetchrow(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo, ativo)
        VALUES ($1, $2, $3, $4, TRUE)
        RETURNING id
        """,
        nome, email, pwd_hash, cargo,
    )
    resp = await client.post(
        "/auth/login", data={"username": email, "password": senha}
    )
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    token = resp.json()["access_token"]
    return {"id": str(row["id"]), "headers": {"Authorization": f"Bearer {token}"}}


async def _seed_colaborador(db_conn, nome: str, funcao: str,
                            usuario_id: str | None = None) -> str:
    row = await db_conn.fetchrow(
        """
        INSERT INTO carteira_colaborador (nome, funcao, ativo, usuario_id)
        VALUES ($1, $2::carteira_funcao_enum, TRUE, $3)
        RETURNING id
        """,
        nome, funcao, usuario_id,
    )
    return str(row["id"])


async def _seed_upload(db_conn, tipo: str) -> str:
    row = await db_conn.fetchrow(
        """
        INSERT INTO carteira_upload
            (tipo, nome_arquivo, total_linhas, total_validos, processado)
        VALUES ($1, 'seed.xlsx', 1, 1, TRUE)
        RETURNING id
        """,
        tipo,
    )
    return str(row["id"])


async def _seed_cnpj(db_conn, upload_id: str, id_grupo: str, cnpj: str,
                     colaborador_nome: str):
    await db_conn.execute(
        """
        INSERT INTO carteira_cnpj (
            upload_id, id_grupo, nome_grupo, cnpj_contador, contabilidade,
            cidade_uf, parceria, tipo_cnae, colaborador_nome,
            funcao_origem, leads_no_mes
        )
        VALUES ($1, $2, 'Grupo', $3, 'Contab', 'SP/SP', 'Parceiro',
                'CNAE Contábil', $4, 'Executivo de Contas - FR', 0)
        """,
        upload_id, id_grupo, cnpj, colaborador_nome,
    )


async def _seed_bastao(db_conn, hunter_nome: str, farmer_nome: str,
                       cnpj: str, status: str, criado_por: str):
    await db_conn.execute(
        """
        INSERT INTO carteira_bastao (
            hunter_nome, farmer_nome, cnpj_contador,
            data_parceria, leads_iniciais, status, criado_por
        ) VALUES ($1, $2, $3, $4, 2, $5::bastao_status_enum, $6)
        """,
        hunter_nome, farmer_nome, cnpj, date(2026, 1, 10), status, criado_por,
    )


# ── Testes do endpoint ───────────────────────────────────────────

class TestRelacionamentoEndpoint:
    async def test_sem_autenticacao_retorna_401(self, client):
        resp = await client.get("/carteira/relacionamento")
        assert resp.status_code == 401

    async def test_hunter_ve_grupos_via_bastao_aprovado(self, db_conn, client):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        # Hunter logado + vinculado
        beatriz = await _login(client, db_conn, "Beatriz", "bea@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Beatriz", "EC_HUNTER",
                                usuario_id=beatriz["id"])
        # Farmer com um grupo
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")
        await _seed_cnpj(db_conn, upload, "G1", "11.111.111/0001-11", "Aline")
        # Bastão APROVADO de Beatriz pra Aline naquele CNPJ
        await _seed_bastao(db_conn, "Beatriz", "Aline", "11.111.111/0001-11",
                           "APROVADO", beatriz["id"])

        resp = await client.get(
            "/carteira/relacionamento", headers=beatriz["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hunter_nome"] == "Beatriz"
        assert len(data["grupos"]) == 1
        assert data["kpis"]["total_grupos"] == 1

    async def test_bastao_pendente_nao_aparece(self, db_conn, client):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        beatriz = await _login(client, db_conn, "Beatriz", "bea@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Beatriz", "EC_HUNTER",
                                usuario_id=beatriz["id"])
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")
        await _seed_cnpj(db_conn, upload, "G1", "11.111.111/0001-11", "Aline")
        # Bastão PENDENTE — não deve casar
        await _seed_bastao(db_conn, "Beatriz", "Aline", "11.111.111/0001-11",
                           "PENDENTE", beatriz["id"])

        resp = await client.get(
            "/carteira/relacionamento", headers=beatriz["headers"]
        )
        assert resp.status_code == 200
        assert resp.json()["grupos"] == []

    async def test_hunter_sem_vinculo_recebe_aviso(self, db_conn, client):
        novato = await _login(client, db_conn, "Novato", "novato@teste.com", "Hunter")
        resp = await client.get(
            "/carteira/relacionamento", headers=novato["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["grupos"] == []
        assert data["aviso"] is not None
        assert data["hunter_nome"] is None

    async def test_operacional_ignora_param_hunter(self, db_conn, client):
        """Hunter operacional não consegue espiar outro Hunter via ?hunter=."""
        upload = await _seed_upload(db_conn, "CARTEIRA")
        beatriz = await _login(client, db_conn, "Beatriz", "bea@teste.com", "Hunter")
        await _seed_colaborador(db_conn, "Beatriz", "EC_HUNTER",
                                usuario_id=beatriz["id"])
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")
        await _seed_cnpj(db_conn, upload, "G1", "11.111.111/0001-11", "Aline")
        # Bastão de OUTRO hunter (Marta)
        await _seed_bastao(db_conn, "Marta", "Aline", "11.111.111/0001-11",
                           "APROVADO", beatriz["id"])

        # Beatriz tenta ?hunter=Marta — deve ser ignorado, vê o DELA (vazio)
        resp = await client.get(
            "/carteira/relacionamento?hunter=Marta", headers=beatriz["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hunter_nome"] == "Beatriz"  # ignorou o ?hunter=Marta
        assert data["grupos"] == []  # Beatriz não tem bastão

    async def test_admin_pode_consultar_outro_hunter(self, db_conn, client, usuario_adm):
        upload = await _seed_upload(db_conn, "CARTEIRA")
        await _seed_colaborador(db_conn, "Marta", "EC_HUNTER")
        await _seed_colaborador(db_conn, "Aline", "EC_FARMER")
        await _seed_cnpj(db_conn, upload, "G1", "11.111.111/0001-11", "Aline")
        # bastão da Marta — criado_por aponta pro próprio adm (só pra ter um UUID válido)
        adm_id = await db_conn.fetchval(
            "SELECT id FROM usuarios WHERE email = 'adm@teste.com'"
        )
        await _seed_bastao(db_conn, "Marta", "Aline", "11.111.111/0001-11",
                           "APROVADO", str(adm_id))

        resp = await client.get(
            "/carteira/relacionamento?hunter=Marta", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hunter_nome"] == "Marta"
        assert len(data["grupos"]) == 1
