"""
Testes do endpoint POST /clientes/funil-por-grupos:
  - Body vazio devolve {}
  - Sem dados em cliente_oportunidade, devolve zeros pra todos os grupos pedidos
  - Com dados, agrega por id_grupo e por etapa (5 etapas)
  - Filtra status != 'em andamento'
  - Filtra fase '06. Conquistado' (fora do funil)
  - Soma ticket (proposta_nmrr) corretamente
  - 403 pra cargo sem acesso
"""
import bcrypt
import pytest


_SENHA = "test123"


async def _seed_adm(db_conn, client):
    pwd = bcrypt.hashpw(_SENHA.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, cargo) VALUES ($1, $2, $3, $4)",
        "ADM Funil", "adm-funil@teste.com", pwd, "ADM",
    )
    resp = await client.post(
        "/auth/login",
        data={"username": "adm-funil@teste.com", "password": _SENHA},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed_hunter(db_conn, client):
    pwd = bcrypt.hashpw(_SENHA.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, cargo) VALUES ($1, $2, $3, $4)",
        "Hunter Funil", "h-funil@teste.com", pwd, "Hunter",
    )
    resp = await client.post(
        "/auth/login",
        data={"username": "h-funil@teste.com", "password": _SENHA},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestFunilPorGrupos:
    async def test_body_vazio(self, db_conn, client):
        headers = await _seed_adm(db_conn, client)
        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=headers,
            json={"id_grupos": []},
        )
        assert resp.status_code == 200
        assert resp.json() == {"por_grupo": {}}

    async def test_grupos_inexistentes(self, db_conn, client):
        """Grupos pedidos não estão no banco → todos retornam zeros."""
        headers = await _seed_adm(db_conn, client)
        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=headers,
            json={"id_grupos": ["g1", "g2"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "g1" in body["por_grupo"]
        assert "g2" in body["por_grupo"]
        # cada grupo tem 5 etapas com qtd=0 e ticket=0
        for gid in ["g1", "g2"]:
            f = body["por_grupo"][gid]
            assert set(f.keys()) == {"suspect", "cadencia", "qualificacao", "apresentacao", "negociacao"}
            for etapa in f.values():
                assert etapa == {"qtd": 0, "ticket": 0.0}

    async def test_agrega_por_grupo_e_etapa(self, db_conn, client):
        """Seed: 2 grupos, 3 contadores, 5 oportunidades em fases diferentes."""
        headers = await _seed_adm(db_conn, client)

        # Upload mínimo de carteira pra ter id_grupo → cnpj_contador
        await db_conn.execute("""
            INSERT INTO carteira_upload (id, tipo, total_linhas, total_validos, processado)
            VALUES ('11111111-1111-1111-1111-111111111111', 'CARTEIRA', 10, 10, TRUE)
        """)
        await db_conn.execute("""
            INSERT INTO carteira_cnpj (upload_id, id_grupo, nome_grupo, cnpj_contador, tipo_cnae)
            VALUES
              ('11111111-1111-1111-1111-111111111111', 'G1', 'Grupo A', 'CC-A1', 'CNAE Contábil'),
              ('11111111-1111-1111-1111-111111111111', 'G1', 'Grupo A', 'CC-A2', 'CNAE Contábil'),
              ('11111111-1111-1111-1111-111111111111', 'G2', 'Grupo B', 'CC-B',  'CNAE Contábil')
        """)

        # Oportunidades
        await db_conn.execute("""
            INSERT INTO cliente_upload (id, tipo, total_linhas, total_validos, processado)
            VALUES ('22222222-2222-2222-2222-222222222222', 'OPORTUNIDADES', 10, 10, TRUE)
        """)
        await db_conn.executemany(
            """INSERT INTO cliente_oportunidade (upload_id, op_id, cnpj_contador, status, fase, proposta_nmrr)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            [
                # Grupo A (CC-A1 + CC-A2): 3 leads ativos, etapas diversas
                ('22222222-2222-2222-2222-222222222222', 1, 'CC-A1', 'Ativo', '01. Suspect',       1000),
                ('22222222-2222-2222-2222-222222222222', 2, 'CC-A1', 'Ativo', '02. Cadência',      2000),
                ('22222222-2222-2222-2222-222222222222', 3, 'CC-A2', 'Ativo', '02. Cadência',      3000),
                # Grupo A: 1 conquistado (deve ser ignorado)
                ('22222222-2222-2222-2222-222222222222', 4, 'CC-A1', 'Conquistado',  '06. Conquistado',   9999),
                # Grupo A: 1 perdido (deve ser ignorado)
                ('22222222-2222-2222-2222-222222222222', 5, 'CC-A2', 'Perdido',      '04. Apresentação',  5000),
                # Grupo B: 1 lead em negociação
                ('22222222-2222-2222-2222-222222222222', 6, 'CC-B',  'Ativo', '05. Negociação',    7500),
            ],
        )

        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=headers,
            json={"id_grupos": ["G1", "G2"]},
        )
        assert resp.status_code == 200
        body = resp.json()["por_grupo"]

        # Grupo A: 1 suspect (R$1000) + 2 cadência (R$5000), demais zeros
        assert body["G1"]["suspect"]      == {"qtd": 1, "ticket": 1000.0}
        assert body["G1"]["cadencia"]     == {"qtd": 2, "ticket": 5000.0}
        assert body["G1"]["qualificacao"] == {"qtd": 0, "ticket": 0.0}
        assert body["G1"]["apresentacao"] == {"qtd": 0, "ticket": 0.0}
        assert body["G1"]["negociacao"]   == {"qtd": 0, "ticket": 0.0}
        # Grupo B: 1 negociação (R$7500), demais zeros
        assert body["G2"]["negociacao"]   == {"qtd": 1, "ticket": 7500.0}
        assert body["G2"]["suspect"]      == {"qtd": 0, "ticket": 0.0}

    async def test_hunter_bloqueado(self, db_conn, client):
        """Hunter não tem módulo 'clientes' → 403."""
        headers = await _seed_hunter(db_conn, client)
        resp = await client.post(
            "/clientes/funil-por-grupos",
            headers=headers,
            json={"id_grupos": ["g1"]},
        )
        assert resp.status_code == 403
