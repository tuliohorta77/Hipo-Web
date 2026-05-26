"""
HIPO — Testes do módulo Vendas (funil CROmie).

Cobre:
  - services.vendas_cromie: classificar_oportunidade, resumir_funil,
    responsavel_da_op (SDR nas fases iniciais, executivo nas demais)
  - GET /vendas/funil-cromie: classificação, filtros, so_problema, responsável
  - GET /vendas/funil-cromie/filtros

Depende das fixtures de conftest.py (db_conn, client, usuario_adm).

Tipos das colunas de flag em cliente_oportunidade (conferidos no banco):
  - previsao_preenchido : VARCHAR(10) — "Sim" / "Não"
  - ticket_preenchido   : VARCHAR(10) — "Sim" / "Não"
  - tarefa_futura       : INT          — 0 / 1
"""
from services.vendas_cromie import (
    classificar_oportunidade,
    resumir_funil,
    responsavel_da_op,
    REGRA_TAREFA_FUTURA,
    REGRA_TEMPERATURA,
    REGRA_PREVISAO,
    REGRA_TICKET,
)


# ─────────────────────────────────────────────────────────────────
#  PARTE 1 — service puro (sem banco)
# ─────────────────────────────────────────────────────────────────

def _op(fase, *, tf=0, temp=None, prev="Não", ticket="Não",
        sdr_fr=None, executivo_vendas=None):
    """
    Monta uma oportunidade mínima para os testes do service, usando os
    MESMOS tipos do banco: tf é INT (0/1), prev/ticket são texto
    ("Sim"/"Não"), temp é numérico.
    """
    return {
        "fase": fase,
        "tarefa_futura": tf,
        "temperatura": temp,
        "previsao_preenchido": prev,
        "ticket_preenchido": ticket,
        "sdr_fr": sdr_fr,
        "executivo_vendas": executivo_vendas,
    }


class TestClassificarOportunidade:
    def test_suspect_so_cobra_tarefa_futura(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=1))
        assert cls["fase_analisada"] is True
        assert cls["conforme"] is True
        assert cls["regras_aplicaveis"] == [REGRA_TAREFA_FUTURA]

    def test_suspect_sem_tarefa_futura_nao_conforme(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=0))
        assert cls["conforme"] is False
        assert cls["problemas"] == [REGRA_TAREFA_FUTURA]

    def test_qualificacao_cobra_tres_regras(self):
        cls = classificar_oportunidade(_op("03. Qualificação", tf=1))
        assert cls["conforme"] is False
        assert set(cls["problemas"]) == {REGRA_TEMPERATURA, REGRA_PREVISAO}

    def test_qualificacao_completa_conforme(self):
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=1, temp=80, prev="Sim")
        )
        assert cls["conforme"] is True

    def test_negociacao_cobra_quatro_regras(self):
        cls = classificar_oportunidade(_op("05. Negociação"))
        assert set(cls["regras_aplicaveis"]) == {
            REGRA_TAREFA_FUTURA, REGRA_TEMPERATURA,
            REGRA_PREVISAO, REGRA_TICKET,
        }

    def test_negociacao_completa_conforme(self):
        cls = classificar_oportunidade(
            _op("05. Negociação", tf=1, temp=90, prev="Sim", ticket="Sim")
        )
        assert cls["conforme"] is True

    def test_apresentacao_cobra_tarefa_futura_regra_interna(self):
        cls = classificar_oportunidade(
            _op("04. Apresentação", tf=0, temp=50, prev="Sim")
        )
        assert cls["conforme"] is False
        assert REGRA_TAREFA_FUTURA in cls["problemas"]

    def test_conquistado_fora_da_analise(self):
        cls = classificar_oportunidade(_op("06. Conquistado", tf=1))
        assert cls["fase_analisada"] is False
        assert cls["conforme"] is False

    def test_fase_desconhecida_fora_da_analise(self):
        cls = classificar_oportunidade(_op("99. Inexistente", tf=1))
        assert cls["fase_analisada"] is False

    def test_temperatura_zero_nao_conta(self):
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=1, temp=0, prev="Sim")
        )
        assert REGRA_TEMPERATURA in cls["problemas"]

    def test_temperatura_nula_nao_conta(self):
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=1, temp=None, prev="Sim")
        )
        assert REGRA_TEMPERATURA in cls["problemas"]

    def test_previsao_texto_nao_conta_como_preenchido(self):
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=1, temp=70, prev="Não")
        )
        assert REGRA_PREVISAO in cls["problemas"]

    def test_previsao_sim_conta_como_preenchido(self):
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=1, temp=70, prev="Sim")
        )
        assert REGRA_PREVISAO not in cls["problemas"]

    def test_ticket_nao_texto_nao_conta(self):
        cls = classificar_oportunidade(
            _op("05. Negociação", tf=1, temp=80, prev="Sim", ticket="Não")
        )
        assert REGRA_TICKET in cls["problemas"]


class TestResponsavelDaOp:
    def test_suspect_usa_sdr(self):
        op = _op("01. Suspect", sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        assert responsavel_da_op(op) == "Carla SDR"

    def test_cadencia_usa_sdr(self):
        op = _op("02. Cadência", sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        assert responsavel_da_op(op) == "Carla SDR"

    def test_qualificacao_usa_executivo(self):
        op = _op("03. Qualificação", sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        assert responsavel_da_op(op) == "Bruno EV"

    def test_negociacao_usa_executivo(self):
        op = _op("05. Negociação", sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        assert responsavel_da_op(op) == "Bruno EV"

    def test_sdr_vazio_retorna_none(self):
        op = _op("01. Suspect", sdr_fr=None, executivo_vendas="Bruno EV")
        assert responsavel_da_op(op) is None

    def test_executivo_vazio_retorna_none(self):
        op = _op("05. Negociação", sdr_fr="Carla SDR", executivo_vendas="")
        assert responsavel_da_op(op) is None

    def test_resumir_funil_anexa_responsavel(self):
        ops = [_op("01. Suspect", tf=1, sdr_fr="Carla SDR")]
        r = resumir_funil(ops)
        assert r["itens"][0]["responsavel"] == "Carla SDR"


class TestResumirFunil:
    def test_pct_conforme_calculado(self):
        ops = [
            _op("01. Suspect", tf=1),
            _op("01. Suspect", tf=1),
            _op("01. Suspect", tf=0),
            _op("06. Conquistado", tf=1),
        ]
        r = resumir_funil(ops)
        assert r["resumo"]["total_analisadas"] == 3
        assert r["resumo"]["conformes"] == 2
        assert r["resumo"]["nao_conformes"] == 1
        assert r["resumo"]["fora_da_analise"] == 1
        assert r["resumo"]["pct_conforme"] == 66.67

    def test_funil_vazio_pct_zero(self):
        r = resumir_funil([])
        assert r["resumo"]["pct_conforme"] == 0.0
        assert r["resumo"]["total_analisadas"] == 0

    def test_so_conquistadas_pct_zero(self):
        r = resumir_funil([_op("06. Conquistado", tf=1)])
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
                   tf=0, temp=None, prev="Não", ticket="Não",
                   sdr_fr="SDR Padrao", executivo_vendas="Exec Padrao"):
    """
    Insere uma oportunidade respeitando os tipos reais das colunas:
      - tarefa_futura: INT  (0/1)
      - previsao_preenchido / ticket_preenchido: VARCHAR ("Sim"/"Não")
      - sdr_fr / executivo_vendas: VARCHAR
    """
    await db_conn.execute(
        """
        INSERT INTO cliente_oportunidade (
            upload_id, op_id, cnpj, razao_social, fase, status,
            temperatura, tarefa_futura, previsao_preenchido,
            ticket_preenchido, sdr_fr, executivo_vendas
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        """,
        upload_id, op_id, f"{op_id:014d}", f"Empresa {op_id}", fase, status,
        temp, tf, prev, ticket, sdr_fr, executivo_vendas,
    )


class TestFunilCromieEndpoint:
    async def test_sem_auth_401(self, client):
        resp = await client.get("/vendas/funil-cromie")
        assert resp.status_code == 401

    async def test_classifica_oportunidades_ativas(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1)
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=0)
        await _seed_op(db_conn, up, 3, "06. Conquistado", tf=1)

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
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1, status="ativo")
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=1, status="perdido")

        resp = await client.get(
            "/vendas/funil-cromie", headers=usuario_adm["headers"]
        )
        assert resp.json()["resumo"]["total_analisadas"] == 1

    async def test_previsao_nao_classifica_como_problema(self, db_conn, client, usuario_adm):
        """Regressão do bug bool('Não')."""
        up = await _seed_upload(db_conn)
        await _seed_op(
            db_conn, up, 1, "03. Qualificação",
            tf=1, temp=80, prev="Não", ticket="Não",
        )
        resp = await client.get(
            "/vendas/funil-cromie?so_problema=true",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert "previsao" in data["itens"][0]["classificacao"]["problemas"]

    async def test_filtro_so_problema(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1)
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=0)

        resp = await client.get(
            "/vendas/funil-cromie?so_problema=true",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 2
        assert data["resumo"]["total_analisadas"] == 2

    async def test_filtro_por_fase(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1)
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1)

        resp = await client.get(
            "/vendas/funil-cromie?fase=05.%20Negociação",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert all(it["fase"] == "05. Negociação" for it in data["itens"])

    async def test_item_traz_responsavel_por_fase(self, db_conn, client, usuario_adm):
        """Suspect -> responsável é o SDR; Negociação -> o executivo."""
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")

        resp = await client.get(
            "/vendas/funil-cromie", headers=usuario_adm["headers"]
        )
        itens = {it["op_id"]: it for it in resp.json()["itens"]}
        assert itens[1]["responsavel"] == "Carla SDR"   # Suspect -> SDR
        assert itens[2]["responsavel"] == "Bruno EV"    # Negociação -> exec

    async def test_filtro_por_responsavel_sdr(self, db_conn, client, usuario_adm):
        """Filtrar pelo SDR traz as OPs em fase inicial dele."""
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=1,
                       sdr_fr="Outro SDR", executivo_vendas="Bruno EV")

        resp = await client.get(
            "/vendas/funil-cromie?responsavel=Carla%20SDR",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 1

    async def test_filtro_por_responsavel_executivo(self, db_conn, client, usuario_adm):
        """Filtrar pelo executivo traz as OPs em fase avançada dele,
        e NÃO traz uma OP em Suspect mesmo que ele seja o executivo_vendas."""
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")

        resp = await client.get(
            "/vendas/funil-cromie?responsavel=Bruno%20EV",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        # Só a Negociação (op 1). A Suspect (op 2) pertence à Carla SDR.
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 1

    async def test_endpoint_filtros(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1,
                       sdr_fr="Carla SDR", executivo_vendas="Bruno EV")

        resp = await client.get(
            "/vendas/funil-cromie/filtros", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "01. Suspect" in data["fases"]
        assert "05. Negociação" in data["fases"]
        # Responsáveis: a Carla (SDR da Suspect) e o Bruno (exec da Negociação).
        assert "Carla SDR" in data["responsaveis"]
        assert "Bruno EV" in data["responsaveis"]
