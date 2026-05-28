"""
HIPO — Testes do router de Agendamento (v1.3.1).

Cobre os endpoints sob /agendamento:
  - GET /agendamento/conformidade          — classificação, filtros, so_*
  - GET /agendamento/conformidade/filtros  — valores p/ dropdowns

E a barreira de permissão:
  - sem auth -> 401
  - cargo sem o módulo 'agendamento' (ex: ADM) -> 403
  - cargo SDR -> 200

A lógica de classificação é a mesma de Vendas (delega a
services.vendas_cromie.resumir_funil), já testada em test_vendas_router.
Aqui validamos o WIRING do router novo: prefixo, guard de módulo e
formato da resposta.

Tipos das colunas (conferidos no banco):
  - previsao_preenchido / ticket_preenchido : VARCHAR "Sim"/"Não"
  - tarefa_futura : INT 0/1
  - temperatura   : NUMERIC 0..100
  - proposta_nmrr : NUMERIC
"""
import bcrypt


_SENHA_TESTE = "test123"


# ── Fixtures locais ──────────────────────────────────────────────────

async def _criar_usuario(db_conn, client, email, cargo):
    """Cria um usuário com o cargo dado e devolve headers autenticados."""
    pwd_hash = bcrypt.hashpw(_SENHA_TESTE.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo, ativo)
        VALUES ($1, $2, $3, $4, TRUE)
        """,
        f"User {cargo}", email, pwd_hash, cargo,
    )
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _SENHA_TESTE},
    )
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_upload(db_conn) -> str:
    row = await db_conn.fetchrow(
        """
        INSERT INTO cliente_upload
            (tipo, nome_arquivo, total_linhas, total_validos, processado)
        VALUES ('OPORTUNIDADES', 'seed.xlsx', 1, 1, TRUE)
        RETURNING id
        """
    )
    return str(row["id"])


async def _seed_op(db_conn, upload_id, op_id, fase, *, status="ativo",
                   tf=0, temp=None, prev="Não", ticket="Não",
                   sdr_fr="SDR Padrao", executivo_vendas="Exec Padrao",
                   nmrr=None):
    await db_conn.execute(
        """
        INSERT INTO cliente_oportunidade (
            upload_id, op_id, cnpj, razao_social, fase, status,
            temperatura, tarefa_futura, previsao_preenchido,
            ticket_preenchido, sdr_fr, executivo_vendas, proposta_nmrr
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
        """,
        upload_id, op_id, f"{op_id:014d}", f"Empresa {op_id}", fase, status,
        temp, tf, prev, ticket, sdr_fr, executivo_vendas, nmrr,
    )


# ── Permissão ────────────────────────────────────────────────────────

class TestAgendamentoPermissao:
    async def test_sem_auth_401(self, client):
        resp = await client.get("/agendamento/conformidade")
        assert resp.status_code == 401

    async def test_filtros_sem_auth_401(self, client):
        resp = await client.get("/agendamento/conformidade/filtros")
        assert resp.status_code == 401

    async def test_adm_sem_modulo_agendamento_403(self, db_conn, client):
        # ADM vê tudo MENOS 'agendamento' (módulo é exclusivo do SDR).
        headers = await _criar_usuario(db_conn, client, "adm@teste.com", "ADM")
        resp = await client.get("/agendamento/conformidade", headers=headers)
        assert resp.status_code == 403

    async def test_farmer_sem_modulo_agendamento_403(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "farmer@teste.com", "Farmer")
        resp = await client.get("/agendamento/conformidade", headers=headers)
        assert resp.status_code == 403

    async def test_sdr_acessa_200(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        resp = await client.get("/agendamento/conformidade", headers=headers)
        assert resp.status_code == 200


# ── Conformidade ─────────────────────────────────────────────────────

class TestAgendamentoConformidade:
    async def test_classifica_oportunidades_ativas(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1)
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=0)
        await _seed_op(db_conn, up, 3, "06. Conquistado", tf=1)

        resp = await client.get("/agendamento/conformidade", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["resumo"]["total_analisadas"] == 2
        assert data["resumo"]["conformes"] == 1

    async def test_filtro_so_problema(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1)
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=0)

        resp = await client.get(
            "/agendamento/conformidade?so_problema=true", headers=headers
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 2

    async def test_filtro_so_incoerente(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", tf=1, temp=100)
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1, temp=80)

        resp = await client.get(
            "/agendamento/conformidade?so_incoerente=true", headers=headers
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 1

    async def test_filtro_por_fase(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1)
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1)

        resp = await client.get(
            "/agendamento/conformidade?fase=05.%20Negociação", headers=headers
        )
        data = resp.json()
        assert all(it["fase"] == "05. Negociação" for it in data["itens"])

    async def test_filtro_temperatura_fechando(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", tf=1, temp=90)
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1, temp=80)

        resp = await client.get(
            "/agendamento/conformidade?temperatura=fechando", headers=headers
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 1

    async def test_resposta_tem_resumo_e_responsavel(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")

        resp = await client.get("/agendamento/conformidade", headers=headers)
        data = resp.json()
        assert "resumo" in data
        assert "por_fase" in data
        # Suspect usa o SDR como responsável.
        assert data["itens"][0]["responsavel"] == "Carla SDR"


class TestAgendamentoFiltros:
    async def test_endpoint_filtros(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")

        resp = await client.get(
            "/agendamento/conformidade/filtros", headers=headers
        )
        data = resp.json()
        assert "01. Suspect" in data["fases"]
        assert "Carla SDR" in data["responsaveis"]
        assert "Bruno EV" in data["responsaveis"]

    async def test_filtros_403_para_nao_sdr(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "adm@teste.com", "ADM")
        resp = await client.get(
            "/agendamento/conformidade/filtros", headers=headers
        )
        assert resp.status_code == 403
