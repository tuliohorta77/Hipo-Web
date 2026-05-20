"""
Testes do router de drilldown (routers/clientes_drilldown.py).

Rotas cobertas (todas em /clientes/* mas com guard requer_qualquer_modulo):
  GET  /clientes/contador-leads
  GET  /clientes/oportunidades/{op_id}
  POST /clientes/funil-por-grupos

Cargos que devem PASSAR (200):
  ADM, Franqueado, Gerente, EP (via 'clientes')
  Hunter, Farmer, SDR, EV, EC  (via 'carteira')

Regressão garantida no fim: rotas de gestão pura de Clientes
(GET /clientes/oportunidades sem op_id, /resumo) continuam BLOQUEADAS pra
Hunter/Farmer.
"""
import io

import bcrypt
import pandas as pd
import pytest


_SENHA = "test123"


async def _seed_user(db_conn, client, cargo: str, email: str):
    pwd = bcrypt.hashpw(_SENHA.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, cargo) "
        "VALUES ($1, $2, $3, $4)",
        f"Test {cargo}", email, pwd, cargo,
    )
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _SENHA},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"email": email, "headers": {"Authorization": f"Bearer {token}"}}


def _xlsx_bytes_op(rows: list[dict]) -> bytes:
    cols = [
        "Contagem", "OP ID", "CNPJ", "Razão Social",
        "Data Criação", "Status", "Fase", "Origem Macro",
        "Unidade", "CNPJ Contador", "Razão Contador",
        "Previsão (R$)", "Temperatura", "Dias Parado",
    ]
    df = pd.DataFrame(rows, columns=cols)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _xlsx_bytes_tarefa(rows: list[dict]) -> bytes:
    cols = [
        "Contagem", "Tarefa ID", "OP ID", "CNPJ", "Razão Social",
        "Data Criação", "Data Agendamento", "Fase Lead",
        "Status", "Finalidade", "Resultado", "Canal",
        "Situação Tarefa", "Unidade", "Usuário Atribuído",
    ]
    df = pd.DataFrame(rows, columns=cols)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


async def _seed_oportunidades(client, headers):
    """Sobe 2 OPs para o CNPJ 99888777000166 via endpoint oficial."""
    conteudo = _xlsx_bytes_op([
        {"Contagem": 1, "OP ID": 101, "CNPJ": "a", "Razão Social": "EMP A",
         "Status": "Ativo", "Fase": "02. Cadência",
         "CNPJ Contador": "99888777000166"},
        {"Contagem": 2, "OP ID": 102, "CNPJ": "b", "Razão Social": "EMP B",
         "Status": "Conquistado", "Fase": "06. Conquistado",
         "CNPJ Contador": "99888777000166"},
    ])
    resp = await client.post(
        "/clientes/upload-oportunidades",
        headers=headers,
        files={"arquivo": (
            "ops.xlsx",
            conteudo,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )},
    )
    assert resp.status_code == 200, resp.text


async def _seed_op_com_tarefas(client, headers):
    """Sobe 1 OP + 2 tarefas para testar /oportunidades/{op_id}."""
    op_bytes = _xlsx_bytes_op([
        {"Contagem": 1, "OP ID": 555, "CNPJ": "x", "Razão Social": "EMP X",
         "Status": "Ativo", "Fase": "03. Qualificação",
         "CNPJ Contador": "11111111000111"},
    ])
    resp = await client.post(
        "/clientes/upload-oportunidades",
        headers=headers,
        files={"arquivo": (
            "ops.xlsx", op_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )},
    )
    assert resp.status_code == 200

    tarefa_bytes = _xlsx_bytes_tarefa([
        {"Contagem": 1, "Tarefa ID": 1001, "OP ID": 555,
         "CNPJ": "x", "Status": "concluída",
         "Finalidade": "Reunião", "Canal": "Online",
         "Situação Tarefa": "Em dia"},
        {"Contagem": 2, "Tarefa ID": 1002, "OP ID": 555,
         "CNPJ": "x", "Status": "pendente",
         "Finalidade": "Follow-up", "Canal": "Telefone",
         "Situação Tarefa": "Atrasada"},
    ])
    resp = await client.post(
        "/clientes/upload-tarefas",
        headers=headers,
        files={"arquivo": (
            "t.xlsx", tarefa_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )},
    )
    assert resp.status_code == 200


# ── /contador-leads ────────────────────────────────────────────────────────

class TestContadorLeadsAcesso:
    async def test_adm_acessa_com_dados(self, db_conn, client, usuario_adm):
        await _seed_oportunidades(client, usuario_adm["headers"])
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["kpis"]["total"] == 2
        assert body["kpis"]["em_andamento"] == 1
        assert body["kpis"]["conquistado"] == 1

    async def test_hunter_acessa(self, db_conn, client, usuario_adm):
        """Bug original: Hunter levava 403. Agora deve passar (200)."""
        await _seed_oportunidades(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "Hunter", "h-leads@teste.com")
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=u["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["kpis"]["total"] == 2

    async def test_farmer_acessa(self, db_conn, client, usuario_adm):
        await _seed_oportunidades(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "Farmer", "f-leads@teste.com")
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=u["headers"],
        )
        assert resp.status_code == 200, resp.text

    async def test_ep_acessa(self, db_conn, client, usuario_adm):
        await _seed_oportunidades(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "EP", "ep-leads@teste.com")
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=u["headers"],
        )
        assert resp.status_code == 200

    async def test_cnpj_sem_oportunidades_retorna_vazio(
        self, db_conn, client
    ):
        u = await _seed_user(db_conn, client, "Hunter", "h-vazio@teste.com")
        resp = await client.get(
            "/clientes/contador-leads?cnpj=11111111000111",
            headers=u["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["kpis"]["total"] == 0
        assert body["leads"] == []

    async def test_sem_token_retorna_401(self, client):
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
        )
        assert resp.status_code == 401


# ── /oportunidades/{op_id} ─────────────────────────────────────────────────

class TestDetalheOportunidadeAcesso:
    async def test_adm_acessa(self, db_conn, client, usuario_adm):
        await _seed_op_com_tarefas(client, usuario_adm["headers"])
        resp = await client.get(
            "/clientes/oportunidades/555",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["oportunidade"]["op_id"] == 555
        assert len(body["tarefas"]) == 2

    async def test_hunter_acessa(self, db_conn, client, usuario_adm):
        """Era o 2º bug: Farmer/Hunter levava 403 ao expandir tarefa do lead."""
        await _seed_op_com_tarefas(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "Hunter", "h-detop@teste.com")
        resp = await client.get(
            "/clientes/oportunidades/555",
            headers=u["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["oportunidade"]["op_id"] == 555

    async def test_farmer_acessa(self, db_conn, client, usuario_adm):
        await _seed_op_com_tarefas(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "Farmer", "f-detop@teste.com")
        resp = await client.get(
            "/clientes/oportunidades/555",
            headers=u["headers"],
        )
        assert resp.status_code == 200, resp.text

    async def test_ep_acessa(self, db_conn, client, usuario_adm):
        await _seed_op_com_tarefas(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "EP", "ep-detop@teste.com")
        resp = await client.get(
            "/clientes/oportunidades/555",
            headers=u["headers"],
        )
        assert resp.status_code == 200

    async def test_op_inexistente_404(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "f-404@teste.com")
        resp = await client.get(
            "/clientes/oportunidades/999999999",
            headers=u["headers"],
        )
        assert resp.status_code == 404

    async def test_sem_token_retorna_401(self, client):
        resp = await client.get("/clientes/oportunidades/555")
        assert resp.status_code == 401


# ── /funil-por-grupos ──────────────────────────────────────────────────────

class TestFunilPorGruposAcesso:
    async def test_lista_vazia_retorna_dict_vazio(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h-funil-vaz@teste.com")
        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=u["headers"],
            json={"id_grupos": []},
        )
        assert resp.status_code == 200
        assert resp.json() == {"por_grupo": {}}

    async def test_hunter_acessa(self, db_conn, client):
        """Bug 2: Hunter levava 403 ao carregar mini funil na listagem."""
        u = await _seed_user(db_conn, client, "Hunter", "h-funil@teste.com")
        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=u["headers"],
            json={"id_grupos": ["grupo-x"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Grupo inexistente vem zerado, não bloqueado
        assert "grupo-x" in body["por_grupo"]
        assert body["por_grupo"]["grupo-x"]["suspect"] == {"qtd": 0, "ticket": 0.0}

    async def test_farmer_acessa(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "f-funil@teste.com")
        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=u["headers"],
            json={"id_grupos": ["g1", "g2"]},
        )
        assert resp.status_code == 200
        assert set(resp.json()["por_grupo"].keys()) == {"g1", "g2"}

    async def test_adm_acessa(self, db_conn, client, usuario_adm):
        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=usuario_adm["headers"],
            json={"id_grupos": ["g1"]},
        )
        assert resp.status_code == 200

    async def test_estrutura_resposta_zerada(self, db_conn, client):
        """Cada grupo deve ter as 5 etapas (suspect..negociacao) zeradas."""
        u = await _seed_user(db_conn, client, "Farmer", "f-funil-est@teste.com")
        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=u["headers"],
            json={"id_grupos": ["grupo-vazio"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        chaves_esperadas = {"suspect", "cadencia", "qualificacao",
                            "apresentacao", "negociacao"}
        assert set(body["por_grupo"]["grupo-vazio"].keys()) == chaves_esperadas

    async def test_sem_token_retorna_401(self, client):
        resp = await client.post(
            "/clientes/funil-por-grupos",
            json={"id_grupos": []},
        )
        assert resp.status_code == 401


# ── Regressão: rotas de gestão pura continuam bloqueadas pra Hunter/Farmer ─

class TestRegressaoClientesContinuaBloqueado:
    """
    O patch só liberou as 3 rotas de drilldown. As outras rotas de /clientes
    (upload, listagem geral, resumo, histórico) seguem trancadas pra quem
    não tem o módulo 'clientes'.
    """

    async def test_hunter_bloqueado_listagem_oportunidades(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h-bloq-list@teste.com")
        resp = await client.get(
            "/clientes/oportunidades",
            headers=u["headers"],
        )
        assert resp.status_code == 403

    async def test_farmer_bloqueado_listagem_oportunidades(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "f-bloq-list@teste.com")
        resp = await client.get(
            "/clientes/oportunidades",
            headers=u["headers"],
        )
        assert resp.status_code == 403

    async def test_hunter_bloqueado_resumo(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h-bloq-r@teste.com")
        resp = await client.get("/clientes/resumo", headers=u["headers"])
        assert resp.status_code == 403

    async def test_hunter_bloqueado_tarefas(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h-bloq-t@teste.com")
        resp = await client.get("/clientes/tarefas", headers=u["headers"])
        assert resp.status_code == 403

    async def test_farmer_bloqueado_upload_oportunidades(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "f-bloq-up@teste.com")
        resp = await client.post(
            "/clientes/upload-oportunidades",
            headers=u["headers"],
            files={"arquivo": ("vazio.xlsx", b"", "application/octet-stream")},
        )
        assert resp.status_code == 403

    async def test_hunter_bloqueado_historico(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h-bloq-h@teste.com")
        resp = await client.get("/clientes/historico", headers=u["headers"])
        assert resp.status_code == 403
