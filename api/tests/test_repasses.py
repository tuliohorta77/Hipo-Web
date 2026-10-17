"""
HIPO — Contratos (043): recebimento do repasse Controller -> Spectre.

Cobertura:
  - permissão: Franqueado, ADM e Financeiro entram; EC, SDR, EV e EP não
  - cargo Financeiro: só o módulo 'contratos', fora de CARGOS_VALIDOS,
    barrado no CRM; script criar_usuario_financeiro
  - contrato: criar, CNPJ inválido/duplicado, editar, encerrar
  - lançamento: K/L/N/O gravados, 100% no primeiro mês e 30% depois,
    override de percentual, fora da vigência, apagar e voltar ao primeiro mês
  - painel: sugestão do mês anterior, pendentes, totais, descontos, NF,
    próxima ação, lançar sugestões em lote
  - contratos a partir da oportunidade conquistada (um por CNPJ da proposta)
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from routers.permissions import (
    CARGO_FINANCEIRO,
    CARGOS_DE_TELA,
    CARGOS_VALIDOS,
    modulos_do_cargo,
)
from scripts.criar_usuario_financeiro import LOGIN_PADRAO, validar
from tests.conftest import criar_usuario

CNPJ_A = "32390090000160"
CNPJ_B = "22675768000106"


def _d(v) -> Decimal:
    return Decimal(str(v))


async def _novo_contrato(client, headers, **campos) -> dict:
    corpo = {
        "razao_social": "SERVCON UNIQUE",
        "cnpj": CNPJ_A,
        "data_venda": "2026-02-02",
        "modalidade": "por_vida",
        "vidas": 121,
        "valor_por_vida": "11.50",
        **campos,
    }
    resp = await client.post("/repasses/contratos", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _lancar(client, headers, contrato_id, competencia, **corpo):
    return await client.put(
        f"/repasses/contratos/{contrato_id}/lancamentos/{competencia}",
        json=corpo, headers=headers,
    )


# ── Permissões ───────────────────────────────────────────────────────

class TestPermissoes:
    def test_financeiro_so_ve_contratos(self):
        assert modulos_do_cargo(CARGO_FINANCEIRO) == {"contratos"}

    def test_financeiro_e_conta_de_tela(self):
        assert CARGO_FINANCEIRO not in CARGOS_VALIDOS
        assert CARGO_FINANCEIRO in CARGOS_DE_TELA

    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM"])
    def test_gestao_ve_contratos(self, cargo):
        assert "contratos" in modulos_do_cargo(cargo)

    @pytest.mark.parametrize("cargo", ["EC", "SDR", "EV", "EP"])
    def test_operacional_nao_ve_contratos(self, cargo):
        assert "contratos" not in modulos_do_cargo(cargo)

    @pytest.mark.parametrize("cargo", ["EC", "SDR", "EV", "EP"])
    async def test_operacional_barrado_na_api(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo)
        resp = await client.get("/repasses/painel", headers=u["headers"])
        assert resp.status_code == 403

    @pytest.mark.parametrize("cargo", ["Franqueado", "ADM", CARGO_FINANCEIRO])
    async def test_quem_entra(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo)
        resp = await client.get("/repasses/painel", headers=u["headers"])
        assert resp.status_code == 200, resp.text

    async def test_financeiro_barrado_no_resto(self, db_conn, client):
        u = await criar_usuario(db_conn, client, CARGO_FINANCEIRO)
        me = await client.get("/auth/me", headers=u["headers"])
        assert me.json()["modulos"] == ["contratos"]
        for rota in ("/crm/oportunidades", "/crm/contas", "/crm/tarefas",
                     "/telemetria/resumo", "/monitor/painel"):
            resp = await client.get(rota, headers=u["headers"])
            assert resp.status_code in (403, 404), f"{rota}: {resp.status_code}"
            assert resp.status_code != 200

    async def test_financeiro_fora_do_seletor_de_envolvidos(self, db_conn, client, usuario_adm):
        await criar_usuario(db_conn, client, CARGO_FINANCEIRO, "adm.fin@teste.com")
        resp = await client.get("/crm/dominio/usuarios", headers=usuario_adm["headers"])
        assert resp.status_code == 200, resp.text
        assert all(u["cargo"] != CARGO_FINANCEIRO for u in resp.json())

    def test_script_login_padrao(self):
        assert LOGIN_PADRAO == "administracao@controllermedseg.com"
        validar(LOGIN_PADRAO, "Administração", "123456")

    @pytest.mark.parametrize("login,nome,senha", [
        ("", "X", "123456"), ("a@b.com", "", "123456"), ("a@b.com", "X", "123"),
    ])
    def test_script_valida(self, login, nome, senha):
        with pytest.raises(ValueError):
            validar(login, nome, senha)


# ── Contrato ─────────────────────────────────────────────────────────

class TestContrato:
    async def test_criar_e_obter(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h, grupo="GRUPO B")
        assert c["cnpj_formatado"] == "32.390.090/0001-60"
        assert _d(c["percentual_repasse"]) == Decimal("30")
        assert _d(c["percentual_primeiro_mes"]) == Decimal("100")
        assert _d(c["imposto_percentual"]) == Decimal("14.33")
        assert c["primeira_competencia"] is None
        det = await client.get(f"/repasses/contratos/{c['id']}", headers=h)
        assert det.status_code == 200
        assert det.json()["lancamentos"] == []

    async def test_cnpj_invalido(self, db_conn, client, usuario_adm):
        resp = await client.post("/repasses/contratos", json={
            "razao_social": "X", "cnpj": "11222333000182", "data_venda": "2026-02-02",
            "modalidade": "valor_fixo", "valor_fixo": "100",
        }, headers=usuario_adm["headers"])
        assert resp.status_code == 422

    async def test_sem_cnpj_e_aceito(self, db_conn, client, usuario_adm):
        c = await _novo_contrato(
            client, usuario_adm["headers"], cnpj=None, razao_social="VALLEY SISTEMAS",
            modalidade="valor_fixo", valor_por_vida=None, valor_fixo="130",
        )
        assert c["cnpj"] is None

    async def test_cnpj_duplicado_ativo(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        await _novo_contrato(client, h)
        resp = await client.post("/repasses/contratos", json={
            "razao_social": "Outra", "cnpj": CNPJ_A, "data_venda": "2026-03-01",
            "modalidade": "valor_fixo", "valor_fixo": "100",
        }, headers=h)
        assert resp.status_code == 409

    async def test_modalidade_sem_valor(self, db_conn, client, usuario_adm):
        resp = await client.post("/repasses/contratos", json={
            "razao_social": "X", "data_venda": "2026-02-02", "modalidade": "por_vida",
        }, headers=usuario_adm["headers"])
        assert resp.status_code == 422

    async def test_editar_e_encerrar(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h)
        resp = await client.patch(f"/repasses/contratos/{c['id']}", json={
            "percentual_repasse": "25", "cnpj": "22.675.768/0001-06",
        }, headers=h)
        assert resp.status_code == 200, resp.text
        assert _d(resp.json()["percentual_repasse"]) == Decimal("25")
        assert resp.json()["cnpj"] == CNPJ_B
        enc = await client.patch(f"/repasses/contratos/{c['id']}", json={
            "status": "encerrado", "encerrado_em": "2026-09-30",
        }, headers=h)
        assert enc.status_code == 200
        assert enc.json()["status"] == "encerrado"
        # Encerrado libera o CNPJ para um contrato novo.
        await _novo_contrato(client, h, cnpj=CNPJ_B, razao_social="GSE")

    async def test_encerrar_antes_da_venda(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h)
        resp = await client.patch(f"/repasses/contratos/{c['id']}", json={
            "status": "encerrado", "encerrado_em": "2026-01-01",
        }, headers=h)
        assert resp.status_code == 422

    async def test_listar_e_buscar(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        await _novo_contrato(client, h)
        await _novo_contrato(client, h, cnpj=CNPJ_B, razao_social="GSE COMERCIO")
        tudo = await client.get("/repasses/contratos", headers=h)
        assert len(tudo.json()) == 2
        por_nome = await client.get("/repasses/contratos", params={"q": "gse"}, headers=h)
        assert [c["razao_social"] for c in por_nome.json()] == ["GSE COMERCIO"]
        por_cnpj = await client.get("/repasses/contratos", params={"q": "32.390"}, headers=h)
        assert [c["cnpj"] for c in por_cnpj.json()] == [CNPJ_A]


# ── Lançamento ───────────────────────────────────────────────────────

class TestLancamento:
    async def test_primeiro_mes_100_e_depois_30(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h, data_venda="2026-08-20", modalidade="valor_fixo",
                                 valor_por_vida=None, valor_fixo="130", vidas=1)
        r1 = await _lancar(client, h, c["id"], "2026-08", vidas=1, valor_fixo="130")
        assert r1.status_code == 200, r1.text
        l1 = r1.json()
        assert l1["primeiro_mes"] is True
        assert (_d(l1["valor_repasse"]), _d(l1["valor_imposto"]), _d(l1["valor_liquido"])) == (
            Decimal("130.00"), Decimal("18.63"), Decimal("111.37"),
        )
        det = await client.get(f"/repasses/contratos/{c['id']}", headers=h)
        assert det.json()["primeira_competencia"] == "2026-08"

        r2 = await _lancar(client, h, c["id"], "2026-09", vidas=1, valor_fixo="130")
        l2 = r2.json()
        assert l2["primeiro_mes"] is False
        assert _d(l2["percentual_repasse"]) == Decimal("30")
        assert _d(l2["valor_repasse"]) == Decimal("39.00")
        assert _d(l2["valor_liquido"]) == Decimal("33.41")

    async def test_por_vida(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h, primeira_competencia="2026-03")
        resp = await _lancar(client, h, c["id"], "2026-09", vidas=142, valor_por_vida="11.50", pago=True)
        assert resp.status_code == 200, resp.text
        l = resp.json()
        assert _d(l["valor_contrato"]) == Decimal("1633.00")
        assert _d(l["valor_repasse"]) == Decimal("489.90")
        assert _d(l["valor_imposto"]) == Decimal("70.20")
        assert _d(l["valor_liquido"]) == Decimal("419.70")
        assert l["pago"] is True

    async def test_regravar_atualiza(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h, primeira_competencia="2026-03")
        await _lancar(client, h, c["id"], "2026-09", vidas=100, valor_por_vida="11.50")
        resp = await _lancar(client, h, c["id"], "2026-09", vidas=110, valor_por_vida="11.50")
        assert _d(resp.json()["valor_contrato"]) == Decimal("1265.00")
        n = await db_conn.fetchval("SELECT count(*) FROM repasse_lancamentos")
        assert n == 1

    async def test_override_de_percentual_e_imposto(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h, primeira_competencia="2026-03")
        resp = await _lancar(client, h, c["id"], "2026-09", vidas=10, valor_por_vida="10",
                             percentual_repasse="100", imposto_percentual="0")
        l = resp.json()
        assert _d(l["valor_repasse"]) == Decimal("100.00")
        assert _d(l["valor_liquido"]) == Decimal("100.00")

    async def test_fora_da_vigencia(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h, data_venda="2026-05-20")
        resp = await _lancar(client, h, c["id"], "2026-04", vidas=1, valor_por_vida="10")
        assert resp.status_code == 422

    async def test_sem_valor(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h)
        resp = await _lancar(client, h, c["id"], "2026-09", vidas=1)
        assert resp.status_code == 422

    async def test_competencia_ruim(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h)
        resp = await _lancar(client, h, c["id"], "09-2026", vidas=1, valor_fixo="1")
        assert resp.status_code == 422

    async def test_apagar_o_unico_volta_a_esperar_o_primeiro_mes(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h)
        await _lancar(client, h, c["id"], "2026-10", vidas=1, valor_por_vida="10")
        resp = await client.delete(f"/repasses/contratos/{c['id']}/lancamentos/2026-10", headers=h)
        assert resp.status_code == 204
        det = await client.get(f"/repasses/contratos/{c['id']}", headers=h)
        assert det.json()["primeira_competencia"] is None
        de_novo = await client.delete(f"/repasses/contratos/{c['id']}/lancamentos/2026-10", headers=h)
        assert de_novo.status_code == 404

    async def test_autoria(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h)
        await _lancar(client, h, c["id"], "2026-10", vidas=1, valor_por_vida="10")
        quem = await db_conn.fetchval(
            "SELECT u.email FROM repasse_lancamentos l JOIN usuarios u ON u.id = l.lancado_por"
        )
        assert quem == "adm@teste.com"


# ── Painel do mês ────────────────────────────────────────────────────

class TestPainel:
    async def test_sugestao_pendentes_e_totais(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        a = await _novo_contrato(client, h, primeira_competencia="2026-03")
        b = await _novo_contrato(client, h, cnpj=CNPJ_B, razao_social="GSE", data_venda="2026-04-24",
                                 modalidade="valor_fixo", valor_por_vida=None, valor_fixo="140", vidas=7)
        # Contrato vendido depois do mes nao aparece.
        await _novo_contrato(client, h, cnpj="17194159000197", razao_social="LC MONTEIRO",
                             data_venda="2026-11-05")

        await _lancar(client, h, a["id"], "2026-09", vidas=142, valor_por_vida="11.50")
        resp = await client.get("/repasses/painel", params={"competencia": "2026-10"}, headers=h)
        assert resp.status_code == 200, resp.text
        p = resp.json()
        assert p["rotulo"] == "out/2026"
        assert p["pendentes"] == 2 and p["lancados"] == 0
        assert len(p["linhas"]) == 2
        linha_a = next(l for l in p["linhas"] if l["contrato"]["id"] == a["id"])
        # Sugestao = o mes anterior.
        assert linha_a["sugestao"]["vidas"] == 142
        assert _d(linha_a["sugestao"]["valor_por_vida"]) == Decimal("11.50")
        assert linha_a["sugestao"]["primeiro_mes"] is False
        linha_b = next(l for l in p["linhas"] if l["contrato"]["id"] == b["id"])
        # Sem mes anterior e sem primeira competencia: primeiro mes, 100%.
        assert linha_b["sugestao"]["primeiro_mes"] is True
        assert _d(linha_b["sugestao"]["valor_repasse"]) == Decimal("140.00")
        assert p["proximo_passo"]["acao"] == "lancar"

    async def test_lancar_sugestoes_desconto_e_nf(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        a = await _novo_contrato(client, h, primeira_competencia="2026-03")
        await _lancar(client, h, a["id"], "2026-09", vidas=142, valor_por_vida="11.50")
        lote = await client.post("/repasses/competencias/2026-10/lancar-sugestoes", json={}, headers=h)
        assert lote.status_code == 200, lote.text
        assert lote.json()["lancados"] == 1
        de_novo = await client.post("/repasses/competencias/2026-10/lancar-sugestoes", json={}, headers=h)
        assert de_novo.json()["lancados"] == 0

        desc = await client.post("/repasses/competencias/2026-10/descontos",
                                 json={"descricao": "Pagamento indevido", "valor": "19.70"}, headers=h)
        assert desc.status_code == 201, desc.text

        p = (await client.get("/repasses/painel", params={"competencia": "2026-10"}, headers=h)).json()
        assert p["pendentes"] == 0
        assert _d(p["totais"]["valor_liquido"]) == Decimal("419.70")
        assert _d(p["totais"]["descontos"]) == Decimal("19.70")
        assert _d(p["totais"]["valor_nf"]) == Decimal("400.00")
        assert p["proximo_passo"]["acao"] == "emitir_nf"
        assert "R$ 400,00" in p["proximo_passo"]["texto"]

        sem_nf = await client.put("/repasses/competencias/2026-10",
                                  json={"recebido_em": "2026-10-25"}, headers=h)
        assert sem_nf.status_code == 422
        nf = await client.put("/repasses/competencias/2026-10",
                              json={"nf_numero": "1234", "nf_emitida_em": "2026-10-20"}, headers=h)
        assert nf.status_code == 200, nf.text
        p = (await client.get("/repasses/painel", params={"competencia": "2026-10"}, headers=h)).json()
        assert p["proximo_passo"]["acao"] == "receber"
        await client.put("/repasses/competencias/2026-10", json={
            "nf_numero": "1234", "nf_emitida_em": "2026-10-20", "recebido_em": "2026-10-28",
        }, headers=h)
        p = (await client.get("/repasses/painel", params={"competencia": "2026-10"}, headers=h)).json()
        assert p["proximo_passo"]["acao"] == "fechado"
        hist = {m["competencia"]: m for m in p["historico"]}
        assert _d(hist["2026-10"]["valor_nf"]) == Decimal("400.00")
        assert hist["2026-09"]["contratos"] == 1

        apaga = await client.delete(f"/repasses/descontos/{desc.json()['id']}", headers=h)
        assert apaga.status_code == 204

    async def test_desconto_invalido(self, db_conn, client, usuario_adm):
        resp = await client.post("/repasses/competencias/2026-10/descontos",
                                 json={"descricao": "x", "valor": "0"}, headers=usuario_adm["headers"])
        assert resp.status_code == 422

    async def test_encerrado_sai_do_mes_seguinte(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        c = await _novo_contrato(client, h)
        await client.patch(f"/repasses/contratos/{c['id']}",
                           json={"status": "encerrado", "encerrado_em": "2026-09-10"}, headers=h)
        set_ = (await client.get("/repasses/painel", params={"competencia": "2026-09"}, headers=h)).json()
        out = (await client.get("/repasses/painel", params={"competencia": "2026-10"}, headers=h)).json()
        assert len(set_["linhas"]) == 1
        assert out["linhas"] == []


# ── A partir da oportunidade ─────────────────────────────────────────

async def _opp_conquistada(db_conn, com_proposta: bool = True):
    autor = await db_conn.fetchval("SELECT id FROM usuarios LIMIT 1")
    conta_a = await db_conn.fetchval(
        "INSERT INTO contas (razao_social, cnpj) VALUES ('SERVCON UNIQUE', $1) RETURNING id", CNPJ_A,
    )
    conta_b = await db_conn.fetchval(
        "INSERT INTO contas (razao_social, cnpj) VALUES ('GSE', $1) RETURNING id", CNPJ_B,
    )
    opp = await db_conn.fetchval(
        """
        INSERT INTO oportunidades (numero, conta_id, fase, status, fase_desfecho, valor_mensalidade)
        VALUES ('OPP-2026-90001', $1, 'finalizado', 'conquistado', 'negociacao', 400)
        RETURNING id
        """,
        conta_a,
    )
    await db_conn.execute(
        """
        INSERT INTO oportunidade_eventos (oportunidade_id, tipo, de, para, usuario_id, criado_em)
        VALUES ($1, 'status', 'ativa', 'conquistado', $2, $3)
        """,
        opp, autor, datetime(2026, 2, 2, 15, 0, tzinfo=timezone.utc),
    )
    if com_proposta:
        prop = await db_conn.fetchval(
            """
            INSERT INTO propostas (oportunidade_id, versao, vidas, escopo, data_proposta,
                validade, cliente_razao_social, executivo_nome, executivo_email,
                modalidade, tabela_preco, aprovada_em)
            VALUES ($1, 1, 12, '["PCMSO"]'::jsonb, '2026-02-01', '2026-02-10',
                    'SERVCON UNIQUE', 'Karine', 'k@x.com', 'tabela', '[]'::jsonb, NOW())
            RETURNING id
            """,
            opp,
        )
        await db_conn.execute(
            """
            INSERT INTO proposta_itens (proposta_id, ordem, conta_id, cnpj, razao_social, vidas, mensalidade)
            VALUES ($1, 1, $2, $3, 'SERVCON UNIQUE', 5, 180),
                   ($1, 2, $4, $5, 'GSE', 7, 220)
            """,
            prop, conta_a, CNPJ_A, conta_b, CNPJ_B,
        )
    return opp


class TestDaOportunidade:
    async def test_lista_e_cria_um_por_cnpj(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        opp = await _opp_conquistada(db_conn)
        lista = await client.get("/repasses/oportunidades", headers=h)
        assert lista.status_code == 200, lista.text
        assert len(lista.json()) == 1
        assert len(lista.json()[0]["cnpjs_sem_contrato"]) == 2
        assert lista.json()[0]["data_conquista"] == "2026-02-02"

        resp = await client.post("/repasses/contratos/da-oportunidade",
                                 json={"oportunidade_id": str(opp)}, headers=h)
        assert resp.status_code == 201, resp.text
        criados = resp.json()["criados"]
        assert {c["cnpj"] for c in criados} == {CNPJ_A, CNPJ_B}
        a = next(c for c in criados if c["cnpj"] == CNPJ_A)
        assert a["modalidade"] == "valor_fixo"
        assert _d(a["valor_fixo"]) == Decimal("180.00")
        assert a["data_venda"] == "2026-02-02"
        assert a["oportunidade_numero"] == "OPP-2026-90001"

        de_novo = await client.post("/repasses/contratos/da-oportunidade",
                                    json={"oportunidade_id": str(opp)}, headers=h)
        assert de_novo.status_code == 409
        assert (await client.get("/repasses/oportunidades", headers=h)).json() == []

    async def test_sem_proposta_usa_a_conta(self, db_conn, client, usuario_adm):
        opp = await _opp_conquistada(db_conn, com_proposta=False)
        resp = await client.post("/repasses/contratos/da-oportunidade",
                                 json={"oportunidade_id": str(opp)}, headers=usuario_adm["headers"])
        assert resp.status_code == 201, resp.text
        assert [c["cnpj"] for c in resp.json()["criados"]] == [CNPJ_A]

    async def test_opp_aberta_recusada(self, db_conn, client, usuario_adm):
        conta = await db_conn.fetchval(
            "INSERT INTO contas (razao_social, cnpj) VALUES ('X', $1) RETURNING id", CNPJ_A,
        )
        opp = await db_conn.fetchval(
            """
            INSERT INTO oportunidades (numero, conta_id, temperatura)
            VALUES ('OPP-2026-90002', $1, 30) RETURNING id
            """,
            conta,
        )
        resp = await client.post("/repasses/contratos/da-oportunidade",
                                 json={"oportunidade_id": str(opp)}, headers=usuario_adm["headers"])
        assert resp.status_code == 422
