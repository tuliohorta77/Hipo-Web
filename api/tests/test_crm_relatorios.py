"""
HIPO - Testes do router /crm/relatorios (com banco).

As regras puras (catalogo, montagem, filtros) estao em
test_relatorios_regras.py. Aqui o foco e o que so aparece executando:

  * todo campo do catalogo roda no Postgres de verdade (o teste de fumaca
    `TestCatalogoExecuta` -- campo com SQL quebrado so apareceria quando
    alguem clicasse nele);
  * o RECORTE: operacional ve so o que e seu, e isso vale para a tabela,
    para o drilldown e para a lista de valores do filtro;
  * os totais saem do banco certos -- media do total geral e media dos
    registros, nao media das medias;
  * relatorios salvos: dono, compartilhamento, duplicar, nome unico.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from services import relatorios as rel
from tests.conftest import criar_usuario

HOJE = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
PERIODO = {"data_ref": "data_criacao", "inicio": (HOJE - timedelta(days=30)).isoformat(),
           "fim": HOJE.isoformat()}


# ── Helpers ──────────────────────────────────────────────────────────

async def uid(db_conn, email):
    return await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", email)


async def nova_conta(client, headers, cnpj, razao):
    r = await client.post("/crm/contas", json={"razao_social": razao, "cnpj": cnpj}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def nova_opp(client, headers, conta_id, envolvidos=(), **extra):
    corpo = {"conta_id": conta_id, "envolvidos": list(envolvidos), **extra}
    r = await client.post("/crm/oportunidades", json=corpo, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def corpo(**extra):
    base = {"fonte": "oportunidades", "periodo": dict(PERIODO), "linhas": [], "colunas": [],
            "valores": [], "filtros": []}
    base.update(extra)
    return base


async def consultar(client, headers, **extra):
    r = await client.post("/crm/relatorios/consulta", json=corpo(**extra), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def celula(res, *chave):
    """A celula de detalhe (nenhuma dimensao somada) com esta chave."""
    for c in res["celulas"]:
        if c["d"] == list(chave) and not any(c["g"]):
            return c
    raise AssertionError(f"celula {chave} nao encontrada em {res['celulas']}")


def total_geral(res):
    return next(c for c in res["celulas"] if all(c["g"]))


@pytest.fixture
async def cenario(db_conn, client, usuario_adm):
    """
    Tres oportunidades: duas do EV Ana (100 e 300), uma do EV Beto (200).
    A terceira conta nao tem vertical nem origem -- serve para '(em branco)'.
    """
    h = usuario_adm["headers"]
    ana = await criar_usuario(db_conn, client, "EV", "ana@teste.com")
    beto = await criar_usuario(db_conn, client, "EV", "beto@teste.com")
    id_ana, id_beto = await uid(db_conn, "ana@teste.com"), await uid(db_conn, "beto@teste.com")
    # O helper do conftest chama todo EV de "Test EV"; a tabela agrupa por nome.
    await db_conn.execute("UPDATE usuarios SET nome = 'Ana' WHERE id = $1", id_ana)
    await db_conn.execute("UPDATE usuarios SET nome = 'Beto' WHERE id = $1", id_beto)

    c1 = await nova_conta(client, h, "11.222.333/0001-81", "Metalurgica Alfa LTDA")
    c2 = await nova_conta(client, h, "11.444.777/0001-61", "Padaria Beta ME")
    o1 = await nova_opp(client, h, c1["id"], [{"usuario_id": str(id_ana), "papel": "EV"}],
                        valor_mensalidade="100.00", fase="lead")
    o2 = await nova_opp(client, h, c2["id"], [{"usuario_id": str(id_ana), "papel": "EV"}],
                        valor_mensalidade="300.00", fase="negociacao")
    o3 = await nova_opp(client, h, c1["id"], [{"usuario_id": str(id_beto), "papel": "EV"}],
                        valor_mensalidade="200.00", fase="lead")
    return {"adm": usuario_adm, "ana": ana, "beto": beto, "opps": (o1, o2, o3),
            "contas": (c1, c2), "id_ana": id_ana, "id_beto": id_beto}


# ── Fumaça: todo o catálogo executa ──────────────────────────────────

class TestCatalogoExecuta:
    async def test_todo_campo_de_toda_fonte_roda(self, db_conn, cenario):
        """
        Cada campo como linha, com todas as suas agregacoes, com e sem
        recorte. Campo com SQL quebrado so seria descoberto quando alguem
        clicasse nele -- aqui cai no CI.
        """
        erros = []
        for f in rel.FONTES.values():
            for c in f.campos:
                for escopo in (None, cenario["id_ana"]):
                    valores = [{"campo": "*", "agregacao": "contagem"}] + [
                        {"campo": c.chave, "agregacao": a} for a in c.agregacoes()
                    ]
                    q = {
                        "fonte": f.chave,
                        "periodo": {"data_ref": f.data_padrao, "inicio": date(2020, 1, 1),
                                    "fim": HOJE + timedelta(days=400)},
                        "linhas": [{"campo": c.chave}], "colunas": [],
                        "valores": valores, "filtros": [],
                    }
                    try:
                        sql, params, _ = rel.montar_consulta(q, escopo)
                        await db_conn.fetch(sql, *params)
                    except Exception as e:  # pragma: no cover - so no erro
                        erros.append(f"{f.chave}.{c.chave}: {e}")
        assert not erros, "\n".join(erros)

    async def test_toda_data_de_referencia_roda(self, db_conn, cenario):
        for f in rel.FONTES.values():
            for c in f.campos:
                if not c.referencia:
                    continue
                q = {"fonte": f.chave,
                     "periodo": {"data_ref": c.chave, "inicio": date(2020, 1, 1), "fim": HOJE},
                     "linhas": [], "colunas": [], "valores": [], "filtros": []}
                sql, params, _ = rel.montar_consulta(q, None)
                await db_conn.fetch(sql, *params)

    async def test_catalogo_pela_api(self, client, cenario):
        r = await client.get("/crm/relatorios/catalogo", headers=cenario["ana"]["headers"])
        assert r.status_code == 200
        chaves = [f["chave"] for f in r.json()["fontes"]]
        assert chaves[0] == "oportunidades"
        assert set(chaves) == set(rel.FONTES)


# ── Tabela dinâmica ──────────────────────────────────────────────────

class TestConsulta:
    async def test_total_e_contagem_por_fase(self, client, cenario):
        res = await consultar(client, cenario["adm"]["headers"], linhas=[{"campo": "fase"}])
        assert res["total_registros"] == 3
        assert celula(res, "lead")["v"] == [2]
        assert celula(res, "negociacao")["v"] == [1]
        assert res["valores"][0]["rotulo"] == "Quantidade de oportunidades"
        assert res["linhas"][0]["rotulo"] == "Fase"

    async def test_media_do_total_e_dos_registros(self, client, cenario):
        """Media do total geral = (100+300+200)/3, e nao a media das medias por fase."""
        res = await consultar(
            client, cenario["adm"]["headers"], linhas=[{"campo": "fase"}],
            valores=[{"campo": "mensalidade", "agregacao": "media"},
                     {"campo": "mensalidade", "agregacao": "soma"}],
        )
        assert celula(res, "lead")["v"] == [150, 300]
        assert total_geral(res)["v"] == [200, 600]
        assert res["valores"][0]["formato"] == "moeda"

    async def test_linhas_e_colunas_com_subtotais(self, client, cenario):
        res = await consultar(
            client, cenario["adm"]["headers"],
            linhas=[{"campo": "ev"}], colunas=[{"campo": "fase"}],
            valores=[{"campo": "mensalidade", "agregacao": "soma"}],
        )
        assert celula(res, "Ana", "lead")["v"] == [100]
        assert celula(res, "Ana", "negociacao")["v"] == [300]
        assert celula(res, "Beto", "lead")["v"] == [200]
        total_ana = next(c for c in res["celulas"] if c["g"] == [False, True] and c["d"][0] == "Ana")
        assert total_ana["v"] == [400]
        col_lead = next(c for c in res["celulas"] if c["g"] == [True, False] and c["d"][1] == "lead")
        assert col_lead["v"] == [300]
        assert total_geral(res)["v"] == [600]

    async def test_percentual_de_booleano(self, client, cenario):
        res = await consultar(
            client, cenario["adm"]["headers"],
            valores=[{"campo": "esta_aberta", "agregacao": "percentual"}],
        )
        assert total_geral(res)["v"] == [100]

    async def test_data_agrupada_por_mes(self, client, cenario):
        res = await consultar(client, cenario["adm"]["headers"],
                              linhas=[{"campo": "data_criacao", "granularidade": "mes"}])
        detalhe = [c for c in res["celulas"] if not any(c["g"])]
        assert detalhe[0]["d"][0] == HOJE.replace(day=1).isoformat()

    async def test_periodo_fora_nao_traz_nada(self, client, cenario):
        per = {"data_ref": "data_criacao", "inicio": "2020-01-01", "fim": "2020-12-31"}
        r = await client.post("/crm/relatorios/consulta", json=corpo(periodo=per),
                              headers=cenario["adm"]["headers"])
        assert r.json()["total_registros"] == 0

    async def test_filtro_em_branco(self, client, cenario):
        res = await consultar(
            client, cenario["adm"]["headers"],
            filtros=[{"campo": "origem", "operador": "em", "valores": [None]}],
        )
        assert res["total_registros"] == 3

    async def test_filtro_entre(self, client, cenario):
        res = await consultar(
            client, cenario["adm"]["headers"],
            filtros=[{"campo": "mensalidade", "operador": "entre", "minimo": "150", "maximo": "250"}],
        )
        assert res["total_registros"] == 1

    async def test_consulta_invalida_e_422_em_portugues(self, client, cenario):
        r = await client.post("/crm/relatorios/consulta",
                              json=corpo(linhas=[{"campo": "coluna_secreta"}]),
                              headers=cenario["adm"]["headers"])
        assert r.status_code == 422
        assert "não existe" in r.json()["detail"]

    async def test_colunas_demais(self, db_conn, client, cenario, monkeypatch):
        monkeypatch.setattr(rel, "MAX_COMBINACOES_COLUNA", 2)
        r = await client.post("/crm/relatorios/consulta",
                              json=corpo(colunas=[{"campo": "numero"}]),
                              headers=cenario["adm"]["headers"])
        assert r.status_code == 422
        assert "3 colunas" in r.json()["detail"]

    async def test_celulas_demais(self, client, cenario, monkeypatch):
        monkeypatch.setattr(rel, "MAX_CELULAS", 2)
        r = await client.post("/crm/relatorios/consulta",
                              json=corpo(linhas=[{"campo": "numero"}]),
                              headers=cenario["adm"]["headers"])
        assert r.status_code == 422
        assert "grande demais" in r.json()["detail"]


# ── Recorte ──────────────────────────────────────────────────────────

class TestRecorte:
    async def test_operacional_ve_so_o_seu(self, client, cenario):
        res = await consultar(client, cenario["ana"]["headers"],
                              valores=[{"campo": "mensalidade", "agregacao": "soma"}])
        assert res["total_registros"] == 2
        assert total_geral(res)["v"] == [400]

    async def test_outro_operacional_ve_o_dele(self, client, cenario):
        res = await consultar(client, cenario["beto"]["headers"])
        assert res["total_registros"] == 1

    async def test_gestao_ve_tudo(self, client, cenario, usuario_franqueado):
        res = await consultar(client, usuario_franqueado["headers"])
        assert res["total_registros"] == 3

    async def test_drilldown_respeita_recorte(self, client, cenario):
        r = await client.post("/crm/relatorios/registros",
                              json={**corpo(), "celula": []}, headers=cenario["beto"]["headers"])
        assert r.status_code == 200
        assert r.json()["total"] == 1

    async def test_valores_do_filtro_respeitam_recorte(self, client, cenario):
        r = await client.post("/crm/relatorios/valores",
                              json={**corpo(), "campo": "empresa"}, headers=cenario["beto"]["headers"])
        assert [i["valor"] for i in r.json()["itens"]] == ["Metalurgica Alfa LTDA"]

    async def test_tarefas_so_do_responsavel(self, db_conn, client, cenario):
        h = cenario["adm"]["headers"]
        o1 = cenario["opps"][0]
        prazo = (datetime.now(ZoneInfo("UTC")) + timedelta(days=1)).isoformat()
        for resp in (cenario["id_ana"], cenario["id_beto"]):
            r = await client.post("/crm/tarefas", json={
                "oportunidade_id": o1["id"], "tipo": "ligacao", "titulo": "Ligar",
                "responsavel_id": str(resp), "prazo": prazo,
            }, headers=h)
            assert r.status_code == 201, r.text
        res = await consultar(client, cenario["ana"]["headers"], fonte="tarefas",
                              periodo={**PERIODO, "data_ref": "data_criacao"})
        assert res["total_registros"] == 1
        res = await consultar(client, h, fonte="tarefas", periodo={**PERIODO, "data_ref": "data_criacao"})
        assert res["total_registros"] == 2

    async def test_contas_sao_abertas_mas_negocios_recortados(self, client, cenario):
        """
        Conta e base compartilhada (todo mundo ve as 2), mas a soma de
        oportunidades dentro da conta so conta o que quem olha enxerga.
        """
        per = {"data_ref": "data_cadastro", "inicio": PERIODO["inicio"], "fim": PERIODO["fim"]}
        res = await consultar(client, cenario["beto"]["headers"], fonte="contas", periodo=per,
                              valores=[{"campo": "qtd_oportunidades", "agregacao": "soma"}])
        assert res["total_registros"] == 2
        assert total_geral(res)["v"] == [1]


# ── Drilldown ────────────────────────────────────────────────────────

class TestRegistros:
    async def test_celula_traz_os_registros_e_o_que_abrir(self, client, cenario):
        r = await client.post("/crm/relatorios/registros", json={
            **corpo(), "celula": [{"campo": "fase", "valor": "lead"}],
        }, headers=cenario["adm"]["headers"])
        body = r.json()
        assert body["total"] == 2
        assert all(i["abrir"]["tipo"] == "oportunidade" for i in body["itens"])
        ids = {i["abrir"]["id"] for i in body["itens"]}
        assert ids == {cenario["opps"][0]["id"], cenario["opps"][2]["id"]}
        assert body["colunas"][0]["rotulo"] == "Número da oportunidade"

    async def test_paginacao(self, client, cenario):
        r = await client.post("/crm/relatorios/registros", json={**corpo(), "limite": 1, "deslocamento": 1},
                              headers=cenario["adm"]["headers"])
        body = r.json()
        assert body["total"] == 3 and len(body["itens"]) == 1

    async def test_celula_de_data(self, client, cenario):
        r = await client.post("/crm/relatorios/registros", json={
            **corpo(), "celula": [{"campo": "data_criacao", "granularidade": "mes",
                                   "valor": HOJE.replace(day=1).isoformat()}],
        }, headers=cenario["adm"]["headers"])
        assert r.json()["total"] == 3


class TestValores:
    async def test_valores_com_contagem(self, client, cenario):
        r = await client.post("/crm/relatorios/valores", json={**corpo(), "campo": "fase"},
                              headers=cenario["adm"]["headers"])
        itens = {i["valor"]: i["n"] for i in r.json()["itens"]}
        assert itens == {"lead": 2, "negociacao": 1}

    async def test_busca(self, client, cenario):
        r = await client.post("/crm/relatorios/valores",
                              json={**corpo(), "campo": "empresa", "busca": "padaria"},
                              headers=cenario["adm"]["headers"])
        assert [i["valor"] for i in r.json()["itens"]] == ["Padaria Beta ME"]


# ── Acesso ───────────────────────────────────────────────────────────

class TestAcesso:
    async def test_cargo_extinto_nao_entra(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Gerente", "ex@teste.com")
        r = await client.get("/crm/relatorios/catalogo", headers=u["headers"])
        assert r.status_code == 403

    async def test_sem_token(self, client):
        r = await client.get("/crm/relatorios/catalogo")
        assert r.status_code == 401


# ── Relatórios salvos ────────────────────────────────────────────────

def config(**troca):
    base = {
        "fonte": "oportunidades",
        "periodo": {"tipo": "relativo", "preset": "mes_atual", "data_ref": "data_criacao"},
        "linhas": [{"campo": "fase"}],
        "colunas": [],
        "valores": [{"campo": "*", "agregacao": "contagem"}],
        "filtros": [],
        "ordenacao": {"por": "rotulo", "direcao": "asc"},
    }
    base.update(troca)
    return base


async def salvar(client, headers, nome="Funil do mês", **extra):
    r = await client.post("/crm/relatorios/salvos",
                          json={"nome": nome, "config": config(), **extra}, headers=headers)
    return r


class TestSalvos:
    async def test_criar_e_listar(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        r = await salvar(client, h, nome="  Funil   do mês ")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["nome"] == "Funil do mês"
        assert body["eh_meu"] and not body["compartilhado"]
        assert body["fonte_rotulo"] == "Oportunidades"
        assert body["config"]["ordenacao"] == {"por": "rotulo", "direcao": "asc"}
        lista = (await client.get("/crm/relatorios/salvos", headers=h)).json()
        assert [x["nome"] for x in lista] == ["Funil do mês"]

    async def test_nome_unico_sem_diferenciar_caixa(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        assert (await salvar(client, h)).status_code == 201
        r = await salvar(client, h, nome="FUNIL DO MÊS")
        assert r.status_code == 409

    async def test_mesmo_nome_em_donos_diferentes_pode(self, db_conn, client, usuario_adm):
        ev = await criar_usuario(db_conn, client, "EV")
        assert (await salvar(client, usuario_adm["headers"])).status_code == 201
        assert (await salvar(client, ev["headers"])).status_code == 201

    async def test_config_invalida(self, db_conn, client, usuario_adm):
        r = await client.post("/crm/relatorios/salvos", json={
            "nome": "X", "config": config(linhas=[{"campo": "nao_existe"}]),
        }, headers=usuario_adm["headers"])
        assert r.status_code == 422

    async def test_privado_nao_aparece_para_outro(self, db_conn, client, usuario_adm):
        ev = await criar_usuario(db_conn, client, "EV")
        rid = (await salvar(client, usuario_adm["headers"])).json()["id"]
        assert (await client.get("/crm/relatorios/salvos", headers=ev["headers"])).json() == []
        r = await client.put(f"/crm/relatorios/salvos/{rid}",
                             json={"nome": "Meu", "config": config()}, headers=ev["headers"])
        assert r.status_code == 404
        r = await client.post(f"/crm/relatorios/salvos/{rid}/duplicar", json={}, headers=ev["headers"])
        assert r.status_code == 404

    async def test_compartilhado_ve_e_duplica_mas_nao_edita(self, db_conn, client, usuario_adm):
        ev = await criar_usuario(db_conn, client, "EV")
        rid = (await salvar(client, usuario_adm["headers"], compartilhado=True)).json()["id"]

        lista = (await client.get("/crm/relatorios/salvos", headers=ev["headers"])).json()
        assert len(lista) == 1 and not lista[0]["eh_meu"]
        assert lista[0]["dono_nome"] == "Test ADM"

        r = await client.put(f"/crm/relatorios/salvos/{rid}",
                             json={"nome": "Hack", "config": config()}, headers=ev["headers"])
        assert r.status_code == 403
        r = await client.delete(f"/crm/relatorios/salvos/{rid}", headers=ev["headers"])
        assert r.status_code == 403

        r = await client.post(f"/crm/relatorios/salvos/{rid}/duplicar", json={}, headers=ev["headers"])
        assert r.status_code == 201
        copia = r.json()
        assert copia["eh_meu"] and not copia["compartilhado"]
        assert copia["nome"] == "Funil do mês (cópia)"
        r = await client.post(f"/crm/relatorios/salvos/{rid}/duplicar", headers=ev["headers"])
        assert r.json()["nome"] == "Funil do mês (cópia) (2)"

    async def test_duplicar_com_nome_que_ja_existe(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        rid = (await salvar(client, h)).json()["id"]
        r = await client.post(f"/crm/relatorios/salvos/{rid}/duplicar",
                              json={"nome": "funil do mês"}, headers=h)
        assert r.status_code == 409

    async def test_dono_edita_e_exclui(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        rid = (await salvar(client, h)).json()["id"]
        r = await client.put(f"/crm/relatorios/salvos/{rid}", json={
            "nome": "Funil por EV", "config": config(linhas=[{"campo": "ev"}]), "compartilhado": True,
        }, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["nome"] == "Funil por EV"
        assert r.json()["config"]["linhas"] == [{"campo": "ev"}]
        assert r.json()["compartilhado"] is True
        assert (await client.delete(f"/crm/relatorios/salvos/{rid}", headers=h)).status_code == 204
        assert (await client.get("/crm/relatorios/salvos", headers=h)).json() == []

    async def test_renomear_para_nome_existente(self, db_conn, client, usuario_adm):
        h = usuario_adm["headers"]
        await salvar(client, h, nome="A")
        rid = (await salvar(client, h, nome="B")).json()["id"]
        r = await client.put(f"/crm/relatorios/salvos/{rid}", json={"nome": "a", "config": config()}, headers=h)
        assert r.status_code == 409

    async def test_meus_primeiro(self, db_conn, client, usuario_adm):
        ev = await criar_usuario(db_conn, client, "EV")
        await salvar(client, usuario_adm["headers"], nome="Aaa do ADM", compartilhado=True)
        await salvar(client, ev["headers"], nome="Zzz do EV")
        lista = (await client.get("/crm/relatorios/salvos", headers=ev["headers"])).json()
        assert [x["nome"] for x in lista] == ["Zzz do EV", "Aaa do ADM"]
