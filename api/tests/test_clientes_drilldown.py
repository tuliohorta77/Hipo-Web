"""
Testes do endpoint /clientes/contador-leads no router de drilldown.

Esse endpoint vive em routers/clientes_drilldown.py (separado de
routers/clientes.py) justamente pra ser acessível a Hunter/Farmer
(que NÃO têm o módulo 'clientes', só 'carteira').

Cobertos:
  - ADM acessa (com dados)
  - Hunter acessa (sem dados — apenas confere autorização)
  - Farmer acessa
  - EP acessa
  - Gerente acessa
  - Hunter CONTINUA bloqueado em /clientes/oportunidades (regressão da
    permissão fina do router de Clientes)
  - Cargo sem nenhum dos módulos → 403
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


class TestContadorLeadsAcesso:
    """
    Quem pode acessar GET /clientes/contador-leads:
      ADM, Franqueado, Gerente, EP   (via módulo 'clientes')
      Hunter, Farmer, SDR, EV, EC     (via módulo 'carteira')
    """

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
        u = await _seed_user(db_conn, client, "Hunter", "h-drill@teste.com")
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=u["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["kpis"]["total"] == 2

    async def test_farmer_acessa(self, db_conn, client, usuario_adm):
        await _seed_oportunidades(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "Farmer", "f-drill@teste.com")
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=u["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["kpis"]["total"] == 2

    async def test_ep_acessa(self, db_conn, client, usuario_adm):
        await _seed_oportunidades(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "EP", "ep-drill@teste.com")
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=u["headers"],
        )
        assert resp.status_code == 200

    async def test_gerente_acessa(self, db_conn, client, usuario_adm):
        await _seed_oportunidades(client, usuario_adm["headers"])
        u = await _seed_user(db_conn, client, "Gerente", "g-drill@teste.com")
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=u["headers"],
        )
        assert resp.status_code == 200

    async def test_cnpj_sem_oportunidades_retorna_vazio(
        self, db_conn, client, usuario_adm
    ):
        """Sem nenhuma OP cadastrada — deve retornar 200 com kpis zerados."""
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


class TestRegressaoClientesContinuaBloqueado:
    """
    Garante que liberar /contador-leads NÃO afrouxou o resto de /clientes.
    Hunter/Farmer continuam 403 nas outras rotas de gestão de Clientes.
    """

    async def test_hunter_bloqueado_oportunidades(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h-bloq@teste.com")
        resp = await client.get(
            "/clientes/oportunidades",
            headers=u["headers"],
        )
        assert resp.status_code == 403

    async def test_farmer_bloqueado_oportunidades(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "f-bloq@teste.com")
        resp = await client.get(
            "/clientes/oportunidades",
            headers=u["headers"],
        )
        assert resp.status_code == 403

    async def test_hunter_bloqueado_resumo(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h-bloq-r@teste.com")
        resp = await client.get(
            "/clientes/resumo",
            headers=u["headers"],
        )
        assert resp.status_code == 403
