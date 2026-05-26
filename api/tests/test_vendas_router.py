"""
HIPO — Testes do módulo Vendas (funil CROmie).

Cobre:
  - services.vendas_cromie: classificar_oportunidade + resumir_funil
  - GET /vendas/funil-cromie: classificação, filtros, so_problema
  - GET /vendas/funil-cromie/filtros

Depende das fixtures de conftest.py (db_conn, client, usuario_adm).
"""
import bcrypt

from services.vendas_cromie import (
    classificar_oportunidade,
    resumir_funil,
    REGRA_TAREFA_FUTURA,
    REGRA_TEMPERATURA,
    REGRA_PREVISAO,
    REGRA_TICKET,
)


# ─────────────────────────────────────────────────────────────────
#  PARTE 1 — service puro (sem banco)
# ─────────────────────────────────────────────────────────────────

def _op(fase, *, tf=False, temp=None, prev=False, ticket=False):
    """Monta uma oportunidade mínima para os testes do service."""
    return {
        "fase": fase,
        "tarefa_futura": tf,
        "temperatura": temp,
        "previsao_preenchido": prev,
        "ticket_preenchido": ticket,
    }


class TestClassificarOportunidade:
    def test_suspect_so_cobra_tarefa_futura(self):
        # Suspect com tarefa futura -> conforme.
        cls = classificar_oportunidade(_op("01. Suspect", tf=True))
        assert cls["fase_analisada"] is True
        assert cls["conforme"] is True
        assert cls["regras_aplicaveis"] == [REGRA_TAREFA_FUTURA]

    def test_suspect_sem_tarefa_futura_nao_conforme(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=False))
        assert cls["conforme"] is False
        assert cls["problemas"] == [REGRA_TAREFA_FUTURA]

    def test_qualificacao_cobra_tres_regras(self):
        cls = classificar_oportunidade(_op("03. Qualificação", tf=True))
        # Falta temperatura e previsão.
        assert cls["conforme"] is False
        assert set(cls["problemas"]) == {REGRA_TEMPERATURA, REGRA_PREVISAO}

    def test_qualificacao_completa_conforme(self):
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=True, temp=80, prev=True)
        )
        assert cls["conforme"] is True

    def test_negociacao_cobra_quatro_regras(self):
        # Régua interna: Negociação cobra tarefa futura também.
        cls = classificar_oportunidade(_op("05. Negociação"))
        assert set(cls["regras_aplicaveis"]) == {
            REGRA_TAREFA_FUTURA, REGRA_TEMPERATURA,
            REGRA_PREVISAO, REGRA_TICKET,
        }

    def test_negociacao_completa_conforme(self):
        cls = classificar_oportunidade(
            _op("05. Negociação", tf=True, temp=90, prev=True, ticket=True)
        )
        assert cls["conforme"] is True

    def test_apresentacao_cobra_tarefa_futura_regra_interna(self):
        # Régua interna: tarefa futura também em Apresentação.
        cls = classificar_oportunidade(_op("04. Apresentação", temp=50, prev=True))
        assert cls["conforme"] is False
        assert REGRA_TAREFA_FUTURA in cls["problemas"]

    def test_conquistado_fora_da_analise(self):
        cls = classificar_oportunidade(_op("06. Conquistado", tf=True))
        assert cls["fase_analisada"] is False
        assert cls["conforme"] is False

    def test_fase_desconhecida_fora_da_analise(self):
        cls = classificar_oportunidade(_op("99. Inexistente", tf=True))
        assert cls["fase_analisada"] is False

    def test_temperatura_zero_nao_conta(self):
        # Temperatura 0 não conta como preenchida.
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=True, temp=0, prev=True)
        )
        assert REGRA_TEMPERATURA in cls["problemas"]

    def test_temperatura_nula_nao_conta(self):
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=True, temp=None, prev=True)
        )
        assert REGRA_TEMPERATURA in cls["problemas"]


class TestResumirFunil:
    def test_pct_conforme_calculado(self):
        ops = [
            _op("01. Suspect", tf=True),    # conforme
            _op("01. Suspect", tf=True),    # conforme
            _op("01. Suspect", tf=False),   # não conforme
            _op("06. Conquistado", tf=True),  # fora da análise
        ]
        r = resumir_funil(ops)
        assert r["resumo"]["total_analisadas"] == 3
        assert r["resumo"]["conformes"] == 2
        assert r["resumo"]["nao_conformes"] == 1
        assert r["resumo"]["fora_da_analise"] == 1
        # 2/3 = 66.67
        assert r["resumo"]["pct_conforme"] == 66.67

    def test_funil_vazio_pct_zero(self):
        r = resumir_funil([])
        assert r["resumo"]["pct_conforme"] == 0.0
        assert r["resumo"]["total_analisadas"] == 0

    def test_so_conquistadas_pct_zero(self):
        r = resumir_funil([_op("06. Conquistado", tf=True)])
        assert r["resumo"]["total_analisadas"] == 0
        assert r["resumo"]["fora_da_analise"] == 1


# ─────────────────────────────────────────────────────────────────
#  PARTE 2 — endpoint /vendas/funil-cromie
# ─────────────────────────────────────────────────────────────────

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
                   tf=False, temp=None, prev=False, ticket=False,
                   executivo="Exec Um"):
    await db_conn.execute(
        """
        INSERT INTO cliente_oportunidade (
            upload_id, op_id, cnpj, razao_social, fase, status,
            temperatura, tarefa_futura, previsao_preenchido,
            ticket_preenchido, executivo_vendas
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        upload_id, op_id, f"{op_id:014d}", f"Empresa {op_id}", fase, status,
        temp, tf, prev, ticket, executivo,
    )


class TestFunilCromieEndpoint:
    async def test_sem_auth_401(self, client):
        resp = await client.get("/vendas/funil-cromie")
        assert resp.status_code == 401

    async def test_classifica_oportunidades_ativas(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=True)        # conforme
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=False)       # problema
        await _seed_op(db_conn, up, 3, "06. Conquistado", tf=True)    # fora

        resp = await client.get(
            "/vendas/funil-cromie", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["resumo"]["total_analisadas"] == 2
        assert data["resumo"]["conformes"] == 1
        assert data["resumo"]["pct_conforme"] == 50.0

    async def test_ignora_status_nao_ativo(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=True, status="ativo")
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=True, status="perdido")

        resp = await client.get(
            "/vendas/funil-cromie", headers=usuario_adm["headers"]
        )
        # Só a 'ativo' entra.
        assert resp.json()["resumo"]["total_analisadas"] == 1

    async def test_filtro_so_problema(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=True)    # conforme
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=False)   # problema

        resp = await client.get(
            "/vendas/funil-cromie?so_problema=true",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        # itens só traz a não conforme; resumo continua sobre o conjunto todo.
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 2
        assert data["resumo"]["total_analisadas"] == 2

    async def test_filtro_por_fase(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=True)
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=True)

        resp = await client.get(
            "/vendas/funil-cromie?fase=05.%20Negociação",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert all(it["fase"] == "05. Negociação" for it in data["itens"])

    async def test_endpoint_filtros(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=True, executivo="Ana")
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=True, executivo="Bruno")

        resp = await client.get(
            "/vendas/funil-cromie/filtros", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "01. Suspect" in data["fases"]
        assert "05. Negociação" in data["fases"]
        assert data["executivos"] == ["Ana", "Bruno"]
