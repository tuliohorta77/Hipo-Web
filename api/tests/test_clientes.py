"""
Testes do módulo Clientes:
  - parsers (Oportunidades + Tarefas)
  - permissões (cargos novos + bloqueio)
  - endpoints upload/listagem/drilldown/contador-leads
"""
import io
import bcrypt
import pandas as pd
import pytest

from parsers.cliente_oportunidades import parse_oportunidades_arquivo
from parsers.cliente_tarefas import parse_tarefas_clientes_arquivo
from routers.permissions import modulos_do_cargo


# ── Permissões ──────────────────────────────────────────────────

class TestPermissoesClientes:
    def test_adm_ve_clientes(self):
        assert "clientes" in modulos_do_cargo("ADM")

    def test_franqueado_ve_clientes(self):
        assert "clientes" in modulos_do_cargo("Franqueado")

    def test_gerente_ve_clientes(self):
        m = modulos_do_cargo("Gerente")
        assert m == {"carteira", "clientes", "agendamento", "painel"}

    def test_ep_ve_clientes(self):
        m = modulos_do_cargo("EP")
        assert m == {"carteira", "clientes", "painel"}

    def test_hunter_NAO_ve_clientes(self):
        m = modulos_do_cargo("Hunter")
        assert "clientes" not in m
        assert m == {"carteira", "painel"}

    def test_farmer_NAO_ve_clientes(self):
        m = modulos_do_cargo("Farmer")
        assert "clientes" not in m


# ── Parsers ─────────────────────────────────────────────────────

def _xlsx_bytes_op(rows: list[dict]) -> bytes:
    """Gera planilha de Oportunidades pra teste."""
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


class TestParserOportunidades:
    def test_parse_basico(self, tmp_path):
        f = tmp_path / "ops.xlsx"
        f.write_bytes(_xlsx_bytes_op([
            {"Contagem": 1, "OP ID": 12345, "CNPJ": "00.111.222/0001-33",
             "Razão Social": "ACME LTDA", "Data Criação": "2026-01-15",
             "Status": "Ativo", "Fase": "02. Cadência",
             "Origem Macro": "Outbound",
             "Unidade": "Omie SP - Unidade Guarulhos",
             "CNPJ Contador": "99.888.777/0001-66",
             "Razão Contador": "CONT XYZ",
             "Previsão (R$)": 1500.50, "Temperatura": 70, "Dias Parado": 5},
        ]))
        r = parse_oportunidades_arquivo(str(f))
        assert r["total_validos"] == 1
        assert r["erros"] == []
        ln = r["linhas"][0]
        assert ln["op_id"] == 12345
        assert ln["cnpj"] == "00.111.222/0001-33"
        assert ln["status"] == "Ativo"
        assert ln["cnpj_contador"] == "99.888.777/0001-66"
        assert ln["previsao_valor"] == 1500.50
        assert ln["temperatura"] == 70.0
        assert ln["dias_parado"] == 5

    def test_descarta_linha_sem_op_id(self, tmp_path):
        f = tmp_path / "ops.xlsx"
        f.write_bytes(_xlsx_bytes_op([
            {"Contagem": 1, "OP ID": 1, "CNPJ": "x", "Status": "ok"},
            {"Contagem": 2, "OP ID": None, "CNPJ": "y", "Status": "ok"},
            {"Contagem": 3, "OP ID": 3, "CNPJ": "z", "Status": "ok"},
        ]))
        r = parse_oportunidades_arquivo(str(f))
        assert r["total_linhas"] == 3
        assert r["total_validos"] == 2
        op_ids = sorted(ln["op_id"] for ln in r["linhas"])
        assert op_ids == [1, 3]

    def test_erro_sem_op_id_na_planilha(self, tmp_path):
        # Planilha sem coluna "OP ID" → retorna erro
        df = pd.DataFrame([{"CNPJ": "x", "Status": "y"}])
        f = tmp_path / "ruim.xlsx"
        df.to_excel(str(f), index=False, engine="openpyxl")
        r = parse_oportunidades_arquivo(str(f))
        assert r["total_validos"] == 0
        assert any("OP ID" in e for e in r["erros"])


class TestParserTarefas:
    def test_parse_basico(self, tmp_path):
        f = tmp_path / "t.xlsx"
        f.write_bytes(_xlsx_bytes_tarefa([
            {"Contagem": 1, "Tarefa ID": 999, "OP ID": 12345,
             "CNPJ": "00.111.222/0001-33", "Razão Social": "ACME",
             "Data Criação": "2026-03-12 09:00",
             "Data Agendamento": "2026-03-12 10:00",
             "Fase Lead": "01. Suspect", "Status": "concluída",
             "Finalidade": "Tentativa de contato",
             "Resultado": "Ligação sem sucesso",
             "Canal": "Telefone", "Situação Tarefa": "Em dia",
             "Unidade": "Omie SP", "Usuário Atribuído": "Daniele"},
        ]))
        r = parse_tarefas_clientes_arquivo(str(f))
        assert r["total_validos"] == 1
        ln = r["linhas"][0]
        assert ln["tarefa_id"] == 999
        assert ln["op_id"] == 12345
        assert ln["canal"] == "Telefone"
        assert ln["situacao_tarefa"] == "Em dia"

    def test_descarta_sem_tarefa_id(self, tmp_path):
        f = tmp_path / "t.xlsx"
        f.write_bytes(_xlsx_bytes_tarefa([
            {"Contagem": 1, "Tarefa ID": 1, "OP ID": 10},
            {"Contagem": 2, "Tarefa ID": None, "OP ID": 20},
        ]))
        r = parse_tarefas_clientes_arquivo(str(f))
        assert r["total_validos"] == 1


# ── Endpoints (com DB) ──────────────────────────────────────────

_SENHA = "test123"


async def _seed_user(db_conn, client, cargo: str, email: str = None):
    email = email or f"u-{cargo.lower()}-clientes@teste.com"
    pwd = bcrypt.hashpw(_SENHA.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, cargo) VALUES ($1, $2, $3, $4)",
        f"Test {cargo}", email, pwd, cargo,
    )
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _SENHA},
    )
    token = resp.json()["access_token"]
    return {"email": email, "headers": {"Authorization": f"Bearer {token}"}}


class TestEndpointsAcesso:
    async def test_hunter_bloqueado_clientes(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Hunter", "h-cli@teste.com")
        resp = await client.get("/clientes/oportunidades", headers=u["headers"])
        assert resp.status_code == 403

    async def test_farmer_bloqueado_clientes(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Farmer", "f-cli@teste.com")
        resp = await client.get("/clientes/oportunidades", headers=u["headers"])
        assert resp.status_code == 403

    async def test_ep_acessa_clientes(self, db_conn, client):
        u = await _seed_user(db_conn, client, "EP", "ep-cli@teste.com")
        resp = await client.get("/clientes/oportunidades", headers=u["headers"])
        assert resp.status_code == 200

    async def test_gerente_acessa_clientes(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Gerente", "g-cli@teste.com")
        resp = await client.get("/clientes/oportunidades", headers=u["headers"])
        assert resp.status_code == 200

    async def test_franqueado_acessa_clientes(self, db_conn, client):
        u = await _seed_user(db_conn, client, "Franqueado", "fq-cli@teste.com")
        resp = await client.get("/clientes/oportunidades", headers=u["headers"])
        assert resp.status_code == 200


class TestUploadOportunidades:
    async def test_upload_e_lista(self, client, usuario_adm):
        # CNPJs sem barra '/' pra evitar problema de URL routing no httpx test client
        # (o /contador/{cnpj}/leads não suporta barras no path).
        conteudo = _xlsx_bytes_op([
            {"Contagem": 1, "OP ID": 11, "CNPJ": "a", "Razão Social": "EMP A",
             "Status": "Ativo", "Fase": "02. Cadência",
             "CNPJ Contador": "99888777000166"},
            {"Contagem": 2, "OP ID": 22, "CNPJ": "b", "Razão Social": "EMP B",
             "Status": "Conquistado", "Fase": "06. Conquistado",
             "CNPJ Contador": "99888777000166"},
            {"Contagem": 3, "OP ID": 33, "CNPJ": "c", "Razão Social": "EMP C",
             "Status": "Ativo", "Fase": "01. Suspect",
             "CNPJ Contador": "11111111000111"},
        ])
        resp = await client.post(
            "/clientes/upload-oportunidades",
            headers=usuario_adm["headers"],
            files={"arquivo": ("ops.xlsx", conteudo,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_validos"] == 3

        # Lista as oportunidades
        resp = await client.get(
            "/clientes/oportunidades",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

        # Filtra por status
        resp = await client.get(
            "/clientes/oportunidades?status=Conquistado",
            headers=usuario_adm["headers"],
        )
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["op_id"] == 22

        # Leads de um contador específico (CNPJ sem barras pra evitar URL encoding)
        resp = await client.get(
            "/clientes/contador-leads?cnpj=99888777000166",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["kpis"]["total"] == 2
        assert body["kpis"]["em_andamento"] == 1
        assert body["kpis"]["conquistado"] == 1

    async def test_upload_sem_oportunidades_validas_400(self, client, usuario_adm):
        # Planilha sem coluna OP ID
        df = pd.DataFrame([{"CNPJ": "x", "Status": "y"}])
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        resp = await client.post(
            "/clientes/upload-oportunidades",
            headers=usuario_adm["headers"],
            files={"arquivo": ("ruim.xlsx", buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 400


class TestUploadTarefas:
    async def test_upload_e_drilldown(self, client, usuario_adm):
        # Primeiro insere uma OP
        op_bytes = _xlsx_bytes_op([
            {"Contagem": 1, "OP ID": 555, "CNPJ": "x", "Razão Social": "EMP X",
             "Status": "Ativo", "Fase": "03. Qualificação",
             "CNPJ Contador": "11111111000111"},
        ])
        await client.post(
            "/clientes/upload-oportunidades",
            headers=usuario_adm["headers"],
            files={"arquivo": ("ops.xlsx", op_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        # Agora envia tarefas
        tarefa_bytes = _xlsx_bytes_tarefa([
            {"Contagem": 1, "Tarefa ID": 100, "OP ID": 555,
             "CNPJ": "x", "Status": "concluída",
             "Finalidade": "Reunião", "Canal": "Online",
             "Situação Tarefa": "Em dia"},
            {"Contagem": 2, "Tarefa ID": 101, "OP ID": 555,
             "CNPJ": "x", "Status": "pendente",
             "Finalidade": "Follow-up", "Canal": "Telefone",
             "Situação Tarefa": "Atrasada"},
        ])
        resp = await client.post(
            "/clientes/upload-tarefas",
            headers=usuario_adm["headers"],
            files={"arquivo": ("t.xlsx", tarefa_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        assert resp.json()["total_validos"] == 2

        # Drilldown: detalhe da OP 555 traz as 2 tarefas
        resp = await client.get(
            "/clientes/oportunidades/555",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["oportunidade"]["op_id"] == 555
        assert len(body["tarefas"]) == 2

    async def test_op_inexistente_404(self, client, usuario_adm):
        resp = await client.get(
            "/clientes/oportunidades/999999999",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 404


class TestResumo:
    async def test_resumo_zera_sem_dados(self, client, usuario_adm):
        resp = await client.get("/clientes/resumo", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["oportunidades"]["total"] == 0
        assert body["tarefas"]["total"] == 0
