"""
HIPO — Testes do módulo Vendas (funil CROmie + Funil de Vendas).

Cobre:
  - services.vendas_cromie: classificar_oportunidade, resumir_funil,
    responsavel_da_op, faixa_temperatura (5 faixas), temperatura_incoerente,
    montar_funil (com soma de valor)
  - GET /vendas/funil-cromie: classificação, filtros, so_problema,
    so_incoerente, responsável, filtro de faixa de temperatura
  - GET /vendas/funil-cromie/filtros
  - GET /vendas/funil: agregação por fase x faixa + valor (proposta_nmrr)

Tipos das colunas (conferidos no banco):
  - previsao_preenchido / ticket_preenchido : VARCHAR "Sim"/"Não"
  - tarefa_futura : INT 0/1
  - temperatura   : NUMERIC 0..100
  - proposta_nmrr : NUMERIC
"""
from services.vendas_cromie import (
    classificar_oportunidade,
    resumir_funil,
    responsavel_da_op,
    faixa_temperatura,
    temperatura_incoerente,
    montar_funil,
    REGRA_TAREFA_FUTURA,
    REGRA_TEMPERATURA,
    REGRA_PREVISAO,
    REGRA_TICKET,
    FAIXA_SEM,
    FAIXA_FRIA,
    FAIXA_MORNA,
    FAIXA_QUENTE,
    FAIXA_FECHANDO,
)


# ─────────────────────────────────────────────────────────────────
#  PARTE 1 — service puro (sem banco)
# ─────────────────────────────────────────────────────────────────

def _op(fase, *, tf=0, temp=None, prev="Não", ticket="Não",
        sdr_fr=None, executivo_vendas=None, nmrr=None):
    """Oportunidade mínima com os tipos reais do banco."""
    return {
        "fase": fase,
        "tarefa_futura": tf,
        "temperatura": temp,
        "previsao_preenchido": prev,
        "ticket_preenchido": ticket,
        "sdr_fr": sdr_fr,
        "executivo_vendas": executivo_vendas,
        "proposta_nmrr": nmrr,
    }


class TestClassificarOportunidade:
    def test_suspect_so_cobra_tarefa_futura(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=1))
        assert cls["conforme"] is True
        assert cls["regras_aplicaveis"] == [REGRA_TAREFA_FUTURA]

    def test_suspect_sem_tarefa_futura_nao_conforme(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=0))
        assert cls["conforme"] is False
        assert cls["problemas"] == [REGRA_TAREFA_FUTURA]

    def test_qualificacao_cobra_tres_regras(self):
        cls = classificar_oportunidade(_op("03. Qualificação", tf=1))
        assert set(cls["problemas"]) == {REGRA_TEMPERATURA, REGRA_PREVISAO}

    def test_negociacao_completa_conforme(self):
        cls = classificar_oportunidade(
            _op("05. Negociação", tf=1, temp=90, prev="Sim", ticket="Sim")
        )
        assert cls["conforme"] is True

    def test_conquistado_fora_da_analise(self):
        cls = classificar_oportunidade(_op("06. Conquistado", tf=1))
        assert cls["fase_analisada"] is False

    def test_previsao_texto_nao_conta_como_preenchido(self):
        cls = classificar_oportunidade(
            _op("03. Qualificação", tf=1, temp=70, prev="Não")
        )
        assert REGRA_PREVISAO in cls["problemas"]

    def test_ticket_nao_texto_nao_conta(self):
        cls = classificar_oportunidade(
            _op("05. Negociação", tf=1, temp=80, prev="Sim", ticket="Não")
        )
        assert REGRA_TICKET in cls["problemas"]

    def test_classificacao_traz_flag_incoerente(self):
        cls = classificar_oportunidade(_op("05. Negociação", tf=1, temp=100))
        assert cls["temperatura_incoerente"] is True


class TestFaixaTemperatura:
    def test_nula_e_sem(self):
        assert faixa_temperatura(_op("01. Suspect", temp=None)) == FAIXA_SEM

    def test_zero_e_sem(self):
        assert faixa_temperatura(_op("01. Suspect", temp=0)) == FAIXA_SEM

    def test_fria(self):
        assert faixa_temperatura(_op("01. Suspect", temp=10)) == FAIXA_FRIA
        assert faixa_temperatura(_op("01. Suspect", temp=40)) == FAIXA_FRIA

    def test_morna(self):
        assert faixa_temperatura(_op("01. Suspect", temp=50)) == FAIXA_MORNA
        assert faixa_temperatura(_op("01. Suspect", temp=70)) == FAIXA_MORNA

    def test_quente_so_80(self):
        # Quente é exatamente 80 — 90 não é mais quente, é "fechando".
        assert faixa_temperatura(_op("01. Suspect", temp=80)) == FAIXA_QUENTE

    def test_fechando_so_90(self):
        assert faixa_temperatura(_op("05. Negociação", temp=90)) == FAIXA_FECHANDO

    def test_oitenta_nao_e_fechando(self):
        assert faixa_temperatura(_op("05. Negociação", temp=80)) != FAIXA_FECHANDO

    def test_cem_fica_fora_do_funil(self):
        assert faixa_temperatura(_op("05. Negociação", temp=100)) is None


class TestTemperaturaIncoerente:
    def test_cem_em_fase_ativa_e_incoerente(self):
        assert temperatura_incoerente(_op("05. Negociação", temp=100)) is True

    def test_cem_em_conquistado_nao_e_incoerente(self):
        assert temperatura_incoerente(_op("06. Conquistado", temp=100)) is False

    def test_noventa_em_fase_ativa_nao_e_incoerente(self):
        assert temperatura_incoerente(_op("05. Negociação", temp=90)) is False


class TestResponsavelDaOp:
    def test_suspect_usa_sdr(self):
        op = _op("01. Suspect", sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        assert responsavel_da_op(op) == "Carla SDR"

    def test_negociacao_usa_executivo(self):
        op = _op("05. Negociação", sdr_fr="Carla SDR", executivo_vendas="Bruno EV")
        assert responsavel_da_op(op) == "Bruno EV"


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
        assert r["resumo"]["pct_conforme"] == 66.67

    def test_resumo_conta_incoerentes(self):
        ops = [
            _op("05. Negociação", tf=1, temp=100),
            _op("05. Negociação", tf=1, temp=90),
        ]
        r = resumir_funil(ops)
        assert r["resumo"]["temperatura_incoerente"] == 1


class TestMontarFunil:
    def test_agrega_por_fase_e_cinco_faixas(self):
        ops = [
            _op("01. Suspect", temp=None),
            _op("01. Suspect", temp=20),
            _op("05. Negociação", temp=80),
            _op("05. Negociação", temp=90),
        ]
        funil = montar_funil(ops)
        fases = {f["fase"]: f for f in funil["fases"]}
        assert fases["01. Suspect"]["faixas"]["sem"]["total"] == 1
        assert fases["01. Suspect"]["faixas"]["fria"]["total"] == 1
        assert fases["05. Negociação"]["faixas"]["quente"]["total"] == 1
        assert fases["05. Negociação"]["faixas"]["fechando"]["total"] == 1

    def test_soma_valor_proposta_nmrr(self):
        ops = [
            _op("05. Negociação", temp=90, nmrr=1000),
            _op("05. Negociação", temp=90, nmrr=500),
            _op("05. Negociação", temp=80, nmrr=300),
        ]
        funil = montar_funil(ops)
        fases = {f["fase"]: f for f in funil["fases"]}
        neg = fases["05. Negociação"]
        assert neg["faixas"]["fechando"]["valor"] == 1500
        assert neg["faixas"]["quente"]["valor"] == 300
        assert neg["valor"] == 1800
        assert funil["valor_geral"] == 1800

    def test_valor_zero_quando_nmrr_ausente(self):
        funil = montar_funil([_op("01. Suspect", temp=20, nmrr=None)])
        fases = {f["fase"]: f for f in funil["fases"]}
        assert fases["01. Suspect"]["valor"] == 0

    def test_cinco_fases_sempre_presentes(self):
        funil = montar_funil([])
        assert len(funil["fases"]) == 5
        assert funil["total_geral"] == 0
        assert funil["valor_geral"] == 0

    def test_conquistado_nao_entra(self):
        funil = montar_funil([_op("06. Conquistado", temp=100)])
        assert funil["total_geral"] == 0

    def test_temp_cem_fica_fora_e_e_contada(self):
        ops = [
            _op("05. Negociação", temp=100),
            _op("05. Negociação", temp=80),
        ]
        funil = montar_funil(ops)
        assert funil["total_geral"] == 1
        assert funil["temperatura_incoerente"] == 1

    def test_ordem_das_fases(self):
        funil = montar_funil([])
        ordem = [f["fase"] for f in funil["fases"]]
        assert ordem == [
            "01. Suspect", "02. Cadência", "03. Qualificação",
            "04. Apresentação", "05. Negociação",
        ]


# ─────────────────────────────────────────────────────────────────
#  PARTE 2 — endpoints
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
                   sdr_fr="SDR Padrao", executivo_vendas="Exec Padrao",
                   nmrr=None):
    """Insere uma oportunidade com os tipos reais das colunas."""
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

    async def test_filtro_so_incoerente(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", tf=1, temp=100)
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1, temp=80)

        resp = await client.get(
            "/vendas/funil-cromie?so_incoerente=true",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 1

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

    async def test_filtro_temperatura_fechando(self, db_conn, client, usuario_adm):
        # Recorte do drawer: faixa "fechando" = temperatura 90.
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", tf=1, temp=90)
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1, temp=80)
        await _seed_op(db_conn, up, 3, "05. Negociação", tf=1, temp=50)

        resp = await client.get(
            "/vendas/funil-cromie?temperatura=fechando",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 1

    async def test_filtro_temperatura_quente_so_80(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", tf=1, temp=80)
        await _seed_op(db_conn, up, 2, "05. Negociação", tf=1, temp=90)

        resp = await client.get(
            "/vendas/funil-cromie?temperatura=quente",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 1

    async def test_filtro_temperatura_sem(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", tf=1, temp=None)
        await _seed_op(db_conn, up, 2, "01. Suspect", tf=1, temp=20)

        resp = await client.get(
            "/vendas/funil-cromie?temperatura=sem",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
        assert len(data["itens"]) == 1
        assert data["itens"][0]["op_id"] == 1

    async def test_filtro_fase_e_temperatura_juntos(self, db_conn, client, usuario_adm):
        # O drawer combina fase + temperatura.
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", tf=1, temp=90)
        await _seed_op(db_conn, up, 2, "04. Apresentação", tf=1, temp=90)

        resp = await client.get(
            "/vendas/funil-cromie?fase=05.%20Negociação&temperatura=fechando",
            headers=usuario_adm["headers"],
        )
        data = resp.json()
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
        data = resp.json()
        assert "01. Suspect" in data["fases"]
        assert "Carla SDR" in data["responsaveis"]
        assert "Bruno EV" in data["responsaveis"]


class TestFunilEndpoint:
    async def test_sem_auth_401(self, client):
        resp = await client.get("/vendas/funil")
        assert resp.status_code == 401

    async def test_agrega_cinco_faixas(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", temp=None)
        await _seed_op(db_conn, up, 2, "01. Suspect", temp=20)
        await _seed_op(db_conn, up, 3, "05. Negociação", temp=80)
        await _seed_op(db_conn, up, 4, "05. Negociação", temp=90)

        resp = await client.get("/vendas/funil", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["fases"]) == 5
        fases = {f["fase"]: f for f in data["fases"]}
        assert fases["01. Suspect"]["faixas"]["sem"]["total"] == 1
        assert fases["01. Suspect"]["faixas"]["fria"]["total"] == 1
        assert fases["05. Negociação"]["faixas"]["quente"]["total"] == 1
        assert fases["05. Negociação"]["faixas"]["fechando"]["total"] == 1
        assert data["total_geral"] == 4

    async def test_soma_valor(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", temp=90, nmrr=1000)
        await _seed_op(db_conn, up, 2, "05. Negociação", temp=80, nmrr=500)

        resp = await client.get("/vendas/funil", headers=usuario_adm["headers"])
        data = resp.json()
        assert data["valor_geral"] == 1500
        fases = {f["fase"]: f for f in data["fases"]}
        assert fases["05. Negociação"]["faixas"]["fechando"]["valor"] == 1000

    async def test_ignora_status_nao_ativo(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "01. Suspect", temp=20, status="ativo")
        await _seed_op(db_conn, up, 2, "01. Suspect", temp=20, status="perdido")

        resp = await client.get("/vendas/funil", headers=usuario_adm["headers"])
        assert resp.json()["total_geral"] == 1

    async def test_temp_cem_fica_fora_e_e_contada(self, db_conn, client, usuario_adm):
        up = await _seed_upload(db_conn)
        await _seed_op(db_conn, up, 1, "05. Negociação", temp=100)
        await _seed_op(db_conn, up, 2, "05. Negociação", temp=80)

        resp = await client.get("/vendas/funil", headers=usuario_adm["headers"])
        data = resp.json()
        assert data["total_geral"] == 1
        assert data["temperatura_incoerente"] == 1
