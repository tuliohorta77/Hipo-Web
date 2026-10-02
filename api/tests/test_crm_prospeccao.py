"""
HIPO — Testes do router /crm/prospeccao.

A base da Receita é semeada direto no banco (é o script de carga que a
escreve, e ele tem os próprios testes). O que esta suíte protege:

  1. Quem pode: SDR e gestão; EV/EC/EP recebem 403.
  2. A fatia: UF e CNAE obrigatórios, prefixo de CNAE como faixa, e os
     demais filtros.
  3. A situação de cada CNPJ: a regra SQL (lista e KPIs) e a regra Python
     (decisão do puxar) dizem a mesma coisa.
  4. Puxar cria conta + oportunidade + tarefa com AUTORIA do SDR, e nunca
     abre segunda oportunidade, nem em conta bloqueada, nem em cliente.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from config import settings
from routers import crm_prospeccao
from services import prospeccao as regras
from services.enriquecimento import fontes
from tests.conftest import criar_usuario

# Referencia guardada no import: a fixture `segundo_plano` troca o atributo
# do modulo por um gravador, e os testes de enriquecimento precisam da real.
ENRIQUECER_DE_VERDADE = crm_prospeccao.enriquecer_contas


def _cnpj(base12: str) -> str:
    def dv(numeros, pesos):
        resto = sum(int(n) * p for n, p in zip(numeros, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)
    d1 = dv(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = dv(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base12 + d1 + d2


ACME = _cnpj("112223330001")        # 2511000 indústria, Guarulhos, não Simples
BETA = _cnpj("459974180001")        # 4120400 construção, São Paulo, Simples
GAMA = _cnpj("190000000001")        # 4321500 instalação elétrica, Guarulhos
DELTA = _cnpj("200000000001")       # 4711302 comércio, secundário 4120400
NOVA_DEMAIS = _cnpj("210000000001")  # 4120400, aberta há 1 ano


async def _semear_base(conn):
    hoje = date.today()
    linhas = [
        (ACME, "11222333", True, "METALURGICA ACME LTDA", "ACME", "05",
         Decimal("900000.00"), False, date(2010, 1, 1), "2511000", [],
         "6477", "1123456789", "contato@acme.com.br"),
        (BETA, "45997418", True, "CONSTRUTORA BETA LTDA", None, "03",
         Decimal("200000.00"), True, date(2015, 1, 1), "4120400", [],
         "7107", None, None),
        (GAMA, "19000000", False, "GAMA INSTALACOES LTDA", "GAMA", "01",
         Decimal("50000.00"), True, date(2018, 1, 1), "4321500", [],
         "6477", "1133334444", None),
        (DELTA, "20000000", True, "DELTA COMERCIO LTDA", None, "05",
         Decimal("100000.00"), False, date(2005, 1, 1), "4711302", ["4120400"],
         "6477", None, None),
        (NOVA_DEMAIS, "21000000", True, "OMEGA OBRAS LTDA", None, "05",
         Decimal("300000.00"), False, hoje - timedelta(days=365), "4120400", [],
         "6477", None, None),
    ]
    for (cnpj, basico, matriz, razao, fantasia, porte, capital, simples,
         abertura, cnae, sec, mun, tel, email) in linhas:
        await conn.execute(
            """
            INSERT INTO receita_estabelecimentos (
                cnpj, cnpj_basico, matriz, razao_social, nome_fantasia, porte,
                capital_social, simples, mei, data_abertura, cnae_principal,
                cnaes_secundarios, logradouro, numero, bairro, cep, uf,
                municipio_codigo, telefone, email
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,FALSE,$9,$10,$11,'RUA X','10',
                      'CENTRO','07010000','SP',$12,$13,$14)
            """,
            cnpj, basico, matriz, razao, fantasia, porte, capital, simples,
            abertura, cnae, sec, mun, tel, email,
        )
    await conn.executemany(
        "INSERT INTO receita_municipios (codigo, nome, uf) VALUES ($1, $2, 'SP')",
        [("6477", "GUARULHOS"), ("7107", "SÃO PAULO")],
    )
    await conn.executemany(
        "INSERT INTO receita_cnaes (codigo, descricao) VALUES ($1, $2)",
        [("2511000", "Fabricação de estruturas metálicas"),
         ("4120400", "Construção de edifícios"),
         ("4321500", "Instalação e manutenção elétrica"),
         ("4711302", "Comércio varejista de mercadorias")],
    )
    await conn.execute(
        """
        INSERT INTO receita_cargas (referencia, ufs, status, estabelecimentos, concluida_em)
        VALUES ('2026-09', 'SP', 'concluida', 5, NOW())
        """
    )


@pytest.fixture
async def base(db_conn):
    await _semear_base(db_conn)


@pytest.fixture
async def sdr(db_conn, client):
    u = await criar_usuario(db_conn, client, "SDR", "sdr@teste.com")
    u["id"] = await db_conn.fetchval("SELECT id FROM usuarios WHERE email = $1", u["email"])
    return u


@pytest.fixture
def segundo_plano(monkeypatch):
    """Troca o enriquecimento em segundo plano por um gravador — nada vai à rede."""
    chamadas = []

    async def gravar(pool, alvos, user_id):
        chamadas.append(list(alvos))

    monkeypatch.setattr(crm_prospeccao, "enriquecer_contas", gravar)
    return chamadas


async def _conta(conn, cnpj, criado_por, **extra):
    campos = {"razao_social": "JA NO CRM LTDA", "cnpj": cnpj, "criado_por": criado_por, **extra}
    cols = ", ".join(campos)
    marc = ", ".join(f"${i}" for i in range(1, len(campos) + 1))
    return await conn.fetchval(
        f"INSERT INTO contas ({cols}) VALUES ({marc}) RETURNING id", *campos.values()
    )


async def _oportunidade(conn, conta_id, criado_por, status="ativa"):
    fase = "finalizado" if status in ("conquistado", "perdido") else "lead"
    fase_desfecho = "negociacao" if fase == "finalizado" else None
    motivo = None
    if status == "perdido":
        motivo = await conn.fetchval(
            "INSERT INTO motivos_desfecho (tipo, nome, slug) VALUES ('perda','Preço','preco') RETURNING id"
        )
    return await conn.fetchval(
        """
        INSERT INTO oportunidades (numero, conta_id, fase, status, fase_desfecho,
                                   motivo_desfecho_id, temperatura, criado_por)
        VALUES ('OPP-T-' || nextval('oportunidade_numero_seq'), $1, $2, $3, $4, $5, 50, $6)
        RETURNING id
        """,
        conta_id, fase, status, fase_desfecho, motivo, criado_por,
    )


FATIA = {"uf": "SP", "cnae": "41"}


# ── Permissão ────────────────────────────────────────────────────────

class TestPermissao:
    @pytest.mark.parametrize("cargo", ["EV", "EC", "EP"])
    async def test_operacional_fora_da_prospeccao_recebe_403(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo)
        for rota in ("/crm/prospeccao/base", "/crm/prospeccao/resumo?uf=SP&cnae=41"):
            r = await client.get(rota, headers=u["headers"])
            assert r.status_code == 403, rota
        r = await client.post("/crm/prospeccao/puxar", json={"cnpjs": [ACME]},
                              headers=u["headers"])
        assert r.status_code == 403

    @pytest.mark.parametrize("cargo", ["SDR", "ADM", "Franqueado"])
    async def test_sdr_e_gestao_entram(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo)
        r = await client.get("/crm/prospeccao/base", headers=u["headers"])
        assert r.status_code == 200


# ── Base, CNAEs e municípios ─────────────────────────────────────────

class TestApoio:
    async def test_base_nao_carregada(self, client, sdr):
        r = await client.get("/crm/prospeccao/base", headers=sdr["headers"])
        assert r.json() == {"carregada": False, "referencia": None, "ufs": [],
                            "estabelecimentos": None, "concluida_em": None}

    async def test_base_carregada_mostra_a_ultima_concluida(self, db_conn, client, sdr, base):
        await db_conn.execute(
            "INSERT INTO receita_cargas (referencia, ufs, status) VALUES ('2026-10','SP','erro')"
        )
        r = (await client.get("/crm/prospeccao/base", headers=sdr["headers"])).json()
        assert r["carregada"] is True
        assert r["referencia"] == "2026-09"
        assert r["ufs"] == ["SP"]

    async def test_cnae_por_descricao_sem_acento(self, client, sdr, base):
        r = await client.get("/crm/prospeccao/cnaes?q=construcao", headers=sdr["headers"])
        assert [c["codigo"] for c in r.json()] == ["4120400"]

    async def test_cnae_por_codigo(self, client, sdr, base):
        r = await client.get("/crm/prospeccao/cnaes?q=43", headers=sdr["headers"])
        assert [c["codigo"] for c in r.json()] == ["4321500"]

    async def test_municipios_por_uf_e_prefixo(self, client, sdr, base):
        r = await client.get("/crm/prospeccao/municipios?uf=SP&q=sao", headers=sdr["headers"])
        assert [m["nome"] for m in r.json()] == ["SÃO PAULO"]


# ── A fatia ──────────────────────────────────────────────────────────

class TestFatia:
    async def _cnpjs(self, client, sdr, **params):
        r = await client.get("/crm/prospeccao", params=params, headers=sdr["headers"])
        assert r.status_code == 200, r.text
        return [i["cnpj"] for i in r.json()["itens"]]

    @pytest.mark.parametrize("params,trecho", [
        ({"cnae": "41"}, "UF"),
        ({"uf": "SP"}, "CNAE"),
        ({"uf": "SP", "cnae": "4"}, "dígitos"),
    ])
    async def test_recorte_obrigatorio(self, client, sdr, base, params, trecho):
        r = await client.get("/crm/prospeccao", params=params, headers=sdr["headers"])
        assert r.status_code == 422
        assert trecho in r.json()["detail"]

    async def test_divisao_pega_todas_as_subclasses_e_ordena_por_capital(self, client, sdr, base):
        assert await self._cnpjs(client, sdr, **FATIA) == [NOVA_DEMAIS, BETA]

    async def test_secundario(self, client, sdr, base):
        cnpjs = await self._cnpjs(client, sdr, uf="SP", cnae="4120400", secundarios="true")
        assert set(cnpjs) == {BETA, NOVA_DEMAIS, DELTA}

    async def test_varios_cnaes(self, client, sdr, base):
        cnpjs = await self._cnpjs(client, sdr, uf="SP", cnae=["41", "43"])
        assert set(cnpjs) == {BETA, NOVA_DEMAIS, GAMA}

    async def test_municipio_e_regime(self, client, sdr, base):
        assert await self._cnpjs(client, sdr, **FATIA, municipio="7107") == [BETA]
        assert await self._cnpjs(client, sdr, **FATIA, regime="nao_simples") == [NOVA_DEMAIS]

    async def test_idade_minima_porte_e_matriz(self, client, sdr, base):
        assert await self._cnpjs(client, sdr, **FATIA, idade_min=3) == [BETA]
        assert await self._cnpjs(client, sdr, uf="SP", cnae=["41", "43"], porte="01") == [GAMA]
        assert await self._cnpjs(client, sdr, uf="SP", cnae="43", so_matriz="true") == []

    async def test_contato_e_busca(self, client, sdr, base):
        assert await self._cnpjs(client, sdr, uf="SP", cnae="25", com_email="true") == [ACME]
        assert await self._cnpjs(client, sdr, uf="SP", cnae="25", com_telefone="true") == [ACME]
        assert await self._cnpjs(client, sdr, **FATIA, q="beta") == [BETA]
        assert await self._cnpjs(client, sdr, **FATIA, q=BETA[:8]) == [BETA]

    async def test_item_traz_nomes_e_rotulos(self, client, sdr, base):
        r = await client.get("/crm/prospeccao", params={"uf": "SP", "cnae": "25"},
                             headers=sdr["headers"])
        item = r.json()["itens"][0]
        assert item["municipio"] == "GUARULHOS"
        assert item["cnae_descricao"] == "Fabricação de estruturas metálicas"
        assert item["porte"] == "DEMAIS"
        assert item["situacao"] == "nova"
        assert item["cnpj_formatado"].count(".") == 2

    async def test_paginacao(self, client, sdr, base):
        r = await client.get("/crm/prospeccao", params={**FATIA, "limit": 1, "offset": 1},
                             headers=sdr["headers"])
        corpo = r.json()
        assert corpo["total"] == 2
        assert [i["cnpj"] for i in corpo["itens"]] == [BETA]


# ── Situação: SQL e Python dizem a mesma coisa ──────────────────────

class TestSituacao:
    async def _montar(self, db_conn, sdr):
        uid = sdr["id"]
        # BETA: conta com oportunidade aberta. NOVA_DEMAIS: conta sem
        # negócio (só uma perdida). GAMA: bloqueada. ACME: cliente.
        beta = await _conta(db_conn, BETA, uid)
        await _oportunidade(db_conn, beta, uid, "ativa")
        omega = await _conta(db_conn, NOVA_DEMAIS, uid)
        await _oportunidade(db_conn, omega, uid, "perdido")
        await _conta(db_conn, GAMA, uid, nao_prospectar=True,
                     nao_prospectar_motivo="Cliente MedSeg",
                     nao_prospectar_em=datetime.now(timezone.utc))
        acme = await _conta(db_conn, ACME, uid)
        await _oportunidade(db_conn, acme, uid, "conquistado")

    async def test_lista_so_puxaveis_por_padrao(self, db_conn, client, sdr, base):
        await self._montar(db_conn, sdr)
        r = await client.get("/crm/prospeccao", params=FATIA, headers=sdr["headers"])
        itens = r.json()["itens"]
        assert [(i["cnpj"], i["situacao"]) for i in itens] == [(NOVA_DEMAIS, "conta_sem_negocio")]
        assert itens[0]["conta_id"] is not None

    async def test_todas_mostra_cada_situacao(self, db_conn, client, sdr, base):
        await self._montar(db_conn, sdr)
        r = await client.get(
            "/crm/prospeccao",
            params={"uf": "SP", "cnae": ["25", "41", "43", "47"], "situacao": "todas"},
            headers=sdr["headers"],
        )
        sit = {i["cnpj"]: i["situacao"] for i in r.json()["itens"]}
        assert sit == {
            ACME: "cliente", BETA: "em_negociacao", NOVA_DEMAIS: "conta_sem_negocio",
            GAMA: "bloqueada", DELTA: "nova",
        }

    async def test_resumo_conta_cada_situacao(self, db_conn, client, sdr, base):
        await self._montar(db_conn, sdr)
        r = await client.get(
            "/crm/prospeccao/resumo",
            params={"uf": "SP", "cnae": ["25", "41", "43", "47"]},
            headers=sdr["headers"],
        )
        d = r.json()
        assert d["total"] == 5
        assert (d["novas"], d["conta_sem_negocio"], d["em_negociacao"],
                d["clientes"], d["bloqueadas"], d["inativas"]) == (1, 1, 1, 1, 1, 0)
        assert d["puxaveis"] == 2

    async def test_inativa(self, db_conn, client, sdr, base):
        await _conta(db_conn, BETA, sdr["id"], ativo=False)
        r = await client.get("/crm/prospeccao", params={**FATIA, "situacao": "todas"},
                             headers=sdr["headers"])
        sit = {i["cnpj"]: i["situacao"] for i in r.json()["itens"]}
        assert sit[BETA] == "inativa"


# ── Puxar ────────────────────────────────────────────────────────────

class TestPuxar:
    async def _puxar(self, client, sdr, cnpjs, **extra):
        r = await client.post("/crm/prospeccao/puxar", json={"cnpjs": cnpjs, **extra},
                              headers=sdr["headers"])
        assert r.status_code == 200, r.text
        return r.json()

    async def test_cria_conta_oportunidade_e_tarefa_com_autoria(
        self, db_conn, client, sdr, base, segundo_plano
    ):
        corpo = await self._puxar(client, sdr, [ACME])
        assert corpo["puladas"] == []
        p = corpo["puxadas"][0]
        assert p["conta_nova"] is True
        assert p["oportunidade_numero"].startswith("OPP-")

        conta = await db_conn.fetchrow("SELECT * FROM contas WHERE id = $1", p["conta_id"])
        assert conta["razao_social"] == "METALURGICA ACME LTDA"
        assert conta["cidade"] == "GUARULHOS"
        assert conta["porte"] == "DEMAIS"
        assert conta["situacao_cadastral"] == "ATIVA"
        assert conta["cnae_codigo"] == "2511000"
        assert conta["criado_por"] == sdr["id"]
        # Vertical derivada da seção C da CNAE 2.0 (015), sem ninguém mapear.
        vertical = await db_conn.fetchval(
            "SELECT slug FROM verticais WHERE id = $1", conta["vertical_id"]
        )
        assert vertical is not None
        # Enriquecimento ainda não rodou: fica na fila de quem não foi.
        assert conta["enriquecida_em"] is None

        opp = await db_conn.fetchrow("SELECT * FROM oportunidades WHERE id = $1",
                                     p["oportunidade_id"])
        assert (opp["fase"], opp["status"], opp["temperatura"]) == ("suspect", "ativa", 10)
        assert opp["criado_por"] == sdr["id"]
        assert await db_conn.fetchval(
            "SELECT slug FROM origens WHERE id = $1", opp["origem_id"]
        ) == regras.ORIGEM_SLUG
        envolvidos = await db_conn.fetch(
            "SELECT usuario_id, papel FROM oportunidade_envolvidos WHERE oportunidade_id = $1",
            opp["id"],
        )
        assert [(e["usuario_id"], e["papel"]) for e in envolvidos] == [(sdr["id"], "SDR")]
        assert await db_conn.fetchval(
            "SELECT count(*) FROM oportunidade_eventos WHERE oportunidade_id = $1 AND tipo = 'criacao'",
            opp["id"],
        ) == 1

        tarefa = await db_conn.fetchrow("SELECT * FROM tarefas WHERE id = $1", p["tarefa_id"])
        assert tarefa["oportunidade_id"] == opp["id"]
        assert tarefa["tipo"] == "ligacao"
        assert tarefa["titulo"] == "Primeiro contato - ACME"
        assert tarefa["responsavel_id"] == sdr["id"]
        assert tarefa["concluida_em"] is None

        assert corpo["enriquecimento_em_segundo_plano"] == 1
        assert segundo_plano == [[(conta["id"], ACME)]]

    async def test_prazo_e_temperatura_informados(self, db_conn, client, sdr, base, segundo_plano):
        prazo = "2026-11-03T09:00:00-03:00"
        corpo = await self._puxar(client, sdr, [BETA], prazo=prazo, temperatura=20)
        p = corpo["puxadas"][0]
        tarefa = await db_conn.fetchrow("SELECT prazo FROM tarefas WHERE id = $1", p["tarefa_id"])
        assert tarefa["prazo"] == datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
        assert await db_conn.fetchval(
            "SELECT temperatura FROM oportunidades WHERE id = $1", p["oportunidade_id"]
        ) == 20

    async def test_segunda_puxada_e_pulada(self, db_conn, client, sdr, base, segundo_plano):
        await self._puxar(client, sdr, [ACME])
        corpo = await self._puxar(client, sdr, [ACME])
        assert corpo["puxadas"] == []
        assert corpo["puladas"][0]["motivo"] == "em_negociacao"
        assert await db_conn.fetchval("SELECT count(*) FROM oportunidades") == 1

    async def test_outro_sdr_tambem_e_pulado(self, db_conn, client, sdr, base, segundo_plano):
        await self._puxar(client, sdr, [ACME])
        outro = await criar_usuario(db_conn, client, "SDR", "sdr2@teste.com")
        corpo = await self._puxar(client, outro, [ACME])
        assert corpo["puladas"][0]["motivo"] == "em_negociacao"

    async def test_bloqueada_e_cliente_sao_puladas(self, db_conn, client, sdr, base, segundo_plano):
        await _conta(db_conn, GAMA, sdr["id"], nao_prospectar=True,
                     nao_prospectar_motivo="Cliente MedSeg",
                     nao_prospectar_em=datetime.now(timezone.utc))
        acme = await _conta(db_conn, ACME, sdr["id"])
        await _oportunidade(db_conn, acme, sdr["id"], "conquistado")

        corpo = await self._puxar(client, sdr, [GAMA, ACME])
        assert [(p["cnpj"], p["motivo"]) for p in corpo["puladas"]] == [
            (GAMA, "bloqueada"), (ACME, "cliente"),
        ]
        assert all(p["mensagem"] for p in corpo["puladas"])
        assert await db_conn.fetchval("SELECT count(*) FROM tarefas") == 0

    async def test_conta_sem_negocio_e_reaproveitada(self, db_conn, client, sdr, base, segundo_plano):
        conta = await _conta(db_conn, BETA, sdr["id"], razao_social="Beta (cadastro manual)")
        await _oportunidade(db_conn, conta, sdr["id"], "perdido")
        corpo = await self._puxar(client, sdr, [BETA])
        p = corpo["puxadas"][0]
        assert p["conta_nova"] is False
        assert p["conta_id"] == str(conta)
        assert p["razao_social"] == "Beta (cadastro manual)"
        # O cadastro feito por gente não é tocado pela base.
        assert await db_conn.fetchval(
            "SELECT razao_social FROM contas WHERE id = $1", conta
        ) == "Beta (cadastro manual)"
        assert await db_conn.fetchval("SELECT count(*) FROM contas") == 1

    async def test_lote_com_invalido_repetido_e_fora_da_base(
        self, client, sdr, base, segundo_plano
    ):
        fora = _cnpj("990000000001")
        corpo = await self._puxar(client, sdr, [ACME, ACME, "123", fora])
        assert len(corpo["puxadas"]) == 1
        assert sorted(p["motivo"] for p in corpo["puladas"]) == [
            "cnpj_invalido", "fora_da_base", "repetido",
        ]

    async def test_teto_do_lote(self, client, sdr, base):
        r = await client.post("/crm/prospeccao/puxar",
                              json={"cnpjs": [ACME] * (regras.LIMITE_LOTE + 1)},
                              headers=sdr["headers"])
        assert r.status_code == 422

    async def test_temperatura_invalida(self, client, sdr, base):
        r = await client.post("/crm/prospeccao/puxar",
                              json={"cnpjs": [ACME], "temperatura": 15},
                              headers=sdr["headers"])
        assert r.status_code == 422

    async def test_resumo_mostra_o_placar_do_sdr(self, db_conn, client, sdr, base, segundo_plano):
        await self._puxar(client, sdr, [BETA, NOVA_DEMAIS])
        r = await client.get("/crm/prospeccao/resumo", params=FATIA, headers=sdr["headers"])
        d = r.json()
        assert d["meus_suspects_abertos"] == 2
        assert d["minhas_puxadas_no_mes"] == 2
        assert d["em_negociacao"] == 2 and d["puxaveis"] == 0

        outro = await criar_usuario(db_conn, client, "SDR", "sdr2@teste.com")
        r = await client.get("/crm/prospeccao/resumo", params=FATIA, headers=outro["headers"])
        assert r.json()["meus_suspects_abertos"] == 0

    async def test_puxada_aparece_na_fila_de_tarefas_do_sdr(
        self, client, sdr, base, segundo_plano
    ):
        await self._puxar(client, sdr, [ACME])
        r = await client.get("/crm/tarefas", params={"responsavel_id": str(sdr["id"])},
                             headers=sdr["headers"])
        assert r.status_code == 200
        titulos = [t["titulo"] for t in r.json()["itens"]]
        assert "Primeiro contato - ACME" in titulos


# ── Enriquecimento em segundo plano ─────────────────────────────────

class TestEnriquecimento:
    async def test_enriquece_sem_sobrescrever_e_grava_socios(
        self, db_conn, client, sdr, base, segundo_plano, monkeypatch
    ):
        corpo = await self._puxar_acme(client, sdr)
        conta_id = corpo["puxadas"][0]["conta_id"]

        async def buscar(cnpj):
            return {
                "cnpj": cnpj, "razao_social": "RAZAO DIFERENTE NA BRASILAPI",
                "cnae_fiscal": 2511000, "cnae_fiscal_descricao": "Estruturas",
                "cnaes_secundarios": [{"codigo": 2512800, "descricao": "Esquadrias"}],
                "qsa": [{"nome_socio": "JOSE DA SILVA", "cnpj_cpf_do_socio": "***123456**",
                         "qualificacao_socio": "Sócio-Administrador"}],
            }, None

        monkeypatch.setattr(settings, "ENRIQUECIMENTO_FONTES", "brasilapi")
        monkeypatch.setitem(fontes.BUSCADORES, fontes.BRASILAPI, buscar)
        monkeypatch.setattr(crm_prospeccao, "PAUSA_ENRIQUECIMENTO_S", 0)

        alvos = segundo_plano[0]
        await ENRIQUECER_DE_VERDADE(None, alvos, sdr["id"])

        conta = await db_conn.fetchrow("SELECT * FROM contas WHERE id = $1", conta_id)
        assert conta["enriquecida_em"] is not None
        assert conta["razao_social"] == "METALURGICA ACME LTDA"
        assert await db_conn.fetchval(
            "SELECT count(*) FROM conta_socios WHERE conta_id = $1", conta["id"]
        ) == 1
        assert await db_conn.fetchval(
            "SELECT count(*) FROM conta_cnaes_secundarios WHERE conta_id = $1", conta["id"]
        ) == 1

    async def test_fonte_fora_do_ar_nao_levanta(
        self, db_conn, client, sdr, base, segundo_plano, monkeypatch
    ):
        await self._puxar_acme(client, sdr)

        async def buscar(cnpj):
            return None, "fora do ar"

        monkeypatch.setattr(settings, "ENRIQUECIMENTO_FONTES", "brasilapi")
        monkeypatch.setitem(fontes.BUSCADORES, fontes.BRASILAPI, buscar)
        await ENRIQUECER_DE_VERDADE(None, segundo_plano[0], sdr["id"])
        assert await db_conn.fetchval(
            "SELECT enriquecida_em FROM contas WHERE cnpj = $1", ACME
        ) is None

    async def _puxar_acme(self, client, sdr):
        r = await client.post("/crm/prospeccao/puxar", json={"cnpjs": [ACME]},
                              headers=sdr["headers"])
        assert r.status_code == 200, r.text
        return r.json()
