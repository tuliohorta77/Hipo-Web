"""
HIPO — Testes do router /crm/enriquecimento.

A fonte externa é substituída por uma função de mentira (fixture
`fonte_falsa`), que além de devolver o payload conta quantas vezes foi
chamada. É assim que o teste de cache prova o que interessa: a segunda
consulta do mesmo CNPJ NÃO vai à rede — numa fonte paga, cada ida é
dinheiro.

As quatro regras que esta suíte protege:

  1. DV conferido antes da consulta (CNPJ inválido não gasta crédito).
  2. Enriquecimento não sobrescreve campo preenchido por gente.
  3. Estimado nunca sobrescreve declarado, nem com sobrescrever=true.
  4. CPF de sócio nunca chega inteiro ao banco.
"""
import pytest

from config import settings
from services.enriquecimento import fontes
from tests.conftest import criar_usuario

CNPJ_A = "11222333000181"
CNPJ_B = "34028316000103"

PAYLOAD = {
    "cnpj": CNPJ_A,
    "razao_social": "METALURGICA ALFA LTDA",
    "nome_fantasia": "Alfa Metais",
    "cnae_fiscal": 2511000,
    "cnae_fiscal_descricao": "Fabricação de estruturas metálicas",
    "cnaes_secundarios": [{"codigo": 4399103, "descricao": "Obras de alvenaria"}],
    "descricao_porte": "DEMAIS",
    "descricao_situacao_cadastral": "ATIVA",
    "data_inicio_atividade": "2009-03-17",
    "capital_social": 250000.0,
    "cep": "07190000",
    "logradouro": "AVENIDA DAS INDUSTRIAS",
    "numero": "1500",
    "bairro": "CUMBICA",
    "municipio": "GUARULHOS",
    "uf": "SP",
    "ddd_telefone_1": "1123456789",
    "qsa": [
        {
            "nome_socio": "JOSE DA SILVA",
            # CPF INTEIRO de propósito: é o caso que a regra de privacidade
            # precisa barrar antes do banco.
            "cnpj_cpf_do_socio": "12345678901",
            "qualificacao_socio": "49-Sócio-Administrador",
            "data_entrada_sociedade": "2009-03-17",
        },
    ],
}


@pytest.fixture
def fonte_falsa(monkeypatch):
    """
    Substitui a BrasilAPI por uma função local e conta as chamadas.

    Devolve a lista de CNPJs consultados — `len(chamadas)` é o número de
    idas à rede, que é o que os testes de cache verificam.
    """
    chamadas: list[str] = []

    async def buscar(cnpj):
        chamadas.append(cnpj)
        return {**PAYLOAD, "cnpj": cnpj}, None

    monkeypatch.setattr(settings, "ENRIQUECIMENTO_FONTES", "brasilapi")
    monkeypatch.setattr(settings, "ENRIQUECIMENTO_TTL_DIAS", 90)
    monkeypatch.setitem(fontes.BUSCADORES, fontes.BRASILAPI, buscar)
    return chamadas


@pytest.fixture
def fonte_fora_do_ar(monkeypatch):
    async def buscar(cnpj):
        return None, "CNPJ não encontrado na base da Receita."

    monkeypatch.setattr(settings, "ENRIQUECIMENTO_FONTES", "brasilapi")
    monkeypatch.setitem(fontes.BUSCADORES, fontes.BRASILAPI, buscar)


async def criar_conta(client, headers, cnpj=CNPJ_A, **extra):
    corpo = {"razao_social": "Conta de teste", "cnpj": cnpj, **extra}
    resp = await client.post("/crm/contas", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Consulta ─────────────────────────────────────────────────────────

class TestConsultarCnpj:
    async def test_devolve_sugestao_sem_gravar_conta(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        resp = await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["encontrado"] is True
        assert corpo["razao_social"] == "METALURGICA ALFA LTDA"
        assert corpo["cnae_codigo"] == "2511000"
        assert corpo["cidade"] == "GUARULHOS"
        # Consulta não cria conta.
        assert await db_conn.fetchval("SELECT count(*) FROM contas") == 0

    async def test_cnpj_invalido_nao_gasta_consulta(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        resp = await client.get(
            "/crm/enriquecimento/cnpj/11222333000182", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 422
        assert fonte_falsa == []

    async def test_registra_o_cnae_com_vertical_derivada(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        """
        015: o CNAE nasce classificado pela seção da CNAE 2.0 — mas como
        SUGESTÃO, e sem grau de risco (que vale por subclasse na NR-4).
        """
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        row = await db_conn.fetchrow("SELECT * FROM cnaes WHERE codigo = '2511000'")
        assert row is not None
        assert row["vertical_id"] is not None
        assert row["mapeamento_origem"] == "derivado"
        assert row["mapeado_por"] is None, "derivação não tem autor humano"
        assert row["grau_risco"] is None

    async def test_segunda_consulta_vem_do_cache(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        for _ in range(3):
            resp = await client.get(
                f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
            )
            assert resp.status_code == 200
        assert len(fonte_falsa) == 1, "cache não segurou: fonte chamada mais de uma vez"
        assert any("cache" in a for a in resp.json()["avisos"])

    async def test_forcar_ignora_o_cache(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}?forcar=true",
            headers=usuario_adm["headers"],
        )
        assert len(fonte_falsa) == 2

    async def test_avisa_quando_o_cnpj_ja_esta_cadastrado(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        existente = resp.json()["conta_existente"]
        assert existente["conta_id"] == conta["id"]
        assert existente["razao_social"] == "Conta de teste"

    async def test_fonte_sem_resultado_devolve_encontrado_falso(
        self, db_conn, client, usuario_adm, fonte_fora_do_ar
    ):
        resp = await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        assert resp.status_code == 200
        assert resp.json()["encontrado"] is False
        assert resp.json()["avisos"]

    async def test_falha_tambem_fica_registrada(
        self, db_conn, client, usuario_adm, fonte_fora_do_ar
    ):
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        row = await db_conn.fetchrow(
            "SELECT sucesso, erro FROM conta_enriquecimentos WHERE cnpj = $1", CNPJ_A
        )
        assert row["sucesso"] is False
        assert "não encontrado" in row["erro"]

    async def test_consulta_falha_nao_entra_no_cache(
        self, db_conn, client, usuario_adm, fonte_fora_do_ar, monkeypatch
    ):
        """Erro de hoje não pode calar a fonte pelos próximos 90 dias."""
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        chamadas = []

        async def buscar(cnpj):
            chamadas.append(cnpj)
            return {**PAYLOAD, "cnpj": cnpj}, None

        monkeypatch.setitem(fontes.BUSCADORES, fontes.BRASILAPI, buscar)
        resp = await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        assert resp.json()["encontrado"] is True
        assert len(chamadas) == 1


# ── Aplicação na conta ───────────────────────────────────────────────

class TestAplicarNaConta:
    async def test_preenche_os_campos_vazios(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200, resp.text
        aplicados = resp.json()["aplicados"]
        assert aplicados["cidade"] == "GUARULHOS"
        assert aplicados["cnae_codigo"] == "2511000"

        row = await db_conn.fetchrow(
            "SELECT cidade, uf, cep, cnae_codigo, porte, enriquecida_em"
            "  FROM contas WHERE id = $1",
            conta["id"],
        )
        assert row["cidade"] == "GUARULHOS"
        assert row["uf"] == "SP"
        assert row["cep"] == "07190000"
        assert row["enriquecida_em"] is not None

    async def test_nao_sobrescreve_o_que_uma_pessoa_digitou(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(
            client, usuario_adm["headers"], razao_social="ORACULU'S CONTABIL LTDA"
        )
        resp = await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        corpo = resp.json()
        assert "razao_social" not in corpo["aplicados"]
        divergencia = [m for m in corpo["mantidos"] if m["campo"] == "razao_social"]
        assert divergencia, "a divergência precisa voltar para a tela mostrar"
        assert divergencia[0]["atual"] == "ORACULU'S CONTABIL LTDA"

        atual = await db_conn.fetchval(
            "SELECT razao_social FROM contas WHERE id = $1", conta["id"]
        )
        assert atual == "ORACULU'S CONTABIL LTDA"

    async def test_sobrescrever_true_troca_o_que_estava_la(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={"sobrescrever": True}, headers=usuario_adm["headers"],
        )
        atual = await db_conn.fetchval(
            "SELECT razao_social FROM contas WHERE id = $1", conta["id"]
        )
        assert atual == "METALURGICA ALFA LTDA"

    async def test_campos_restringe_o_que_entra(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={"campos": ["cidade", "uf"]}, headers=usuario_adm["headers"],
        )
        assert set(resp.json()["aplicados"]) == {"cidade", "uf"}
        cep = await db_conn.fetchval(
            "SELECT cep FROM contas WHERE id = $1", conta["id"]
        )
        assert cep is None

    async def test_conta_inexistente_404(self, db_conn, client, usuario_adm, fonte_falsa):
        resp = await client.post(
            "/crm/enriquecimento/contas/00000000-0000-0000-0000-000000000000/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        assert resp.status_code == 404


class TestNumeroDeFuncionarios:
    """
    A trava mais cara de furar: o número que o cliente informou vira
    proposta; o estimado é de base anual defasada.
    """

    @pytest.fixture
    def fonte_com_funcionarios(self, monkeypatch):
        async def buscar(cnpj):
            return {**PAYLOAD, "cnpj": cnpj, "quantidade_funcionarios": 180}, None

        monkeypatch.setattr(settings, "ENRIQUECIMENTO_FONTES", "leadcnpj")
        monkeypatch.setattr(settings, "LEADCNPJ_API_KEY", "chave-de-teste")
        monkeypatch.setitem(fontes.BUSCADORES, fontes.LEADCNPJ, buscar)

    async def test_estimado_preenche_quando_o_campo_esta_vazio(
        self, db_conn, client, usuario_adm, fonte_com_funcionarios
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        row = await db_conn.fetchrow(
            "SELECT num_funcionarios, num_funcionarios_origem, num_funcionarios_em"
            "  FROM contas WHERE id = $1",
            conta["id"],
        )
        assert row["num_funcionarios"] == 180
        assert row["num_funcionarios_origem"] == "estimado"
        assert row["num_funcionarios_em"] is not None

    async def test_estimado_nao_sobrescreve_declarado_nem_forcando(
        self, db_conn, client, usuario_adm, fonte_com_funcionarios
    ):
        conta = await criar_conta(client, usuario_adm["headers"], num_funcionarios=42)
        # O número veio do formulário: é declarado.
        await db_conn.execute(
            "UPDATE contas SET num_funcionarios_origem = 'declarado' WHERE id = $1",
            conta["id"],
        )
        resp = await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={"sobrescrever": True}, headers=usuario_adm["headers"],
        )
        mantido = [
            m for m in resp.json()["mantidos"] if m["campo"] == "num_funcionarios"
        ]
        assert mantido and "declarado" in mantido[0]["motivo"]

        atual = await db_conn.fetchval(
            "SELECT num_funcionarios FROM contas WHERE id = $1", conta["id"]
        )
        assert atual == 42

    async def test_estimado_sobrescreve_estimado_anterior(
        self, db_conn, client, usuario_adm, fonte_com_funcionarios
    ):
        conta = await criar_conta(client, usuario_adm["headers"], num_funcionarios=10)
        await db_conn.execute(
            "UPDATE contas SET num_funcionarios_origem = 'estimado' WHERE id = $1",
            conta["id"],
        )
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={"sobrescrever": True}, headers=usuario_adm["headers"],
        )
        atual = await db_conn.fetchval(
            "SELECT num_funcionarios FROM contas WHERE id = $1", conta["id"]
        )
        assert atual == 180


# ── Sócios ───────────────────────────────────────────────────────────

class TestSocios:
    async def test_cpf_inteiro_nunca_chega_ao_banco(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        doc = await db_conn.fetchval(
            "SELECT documento_mascarado FROM conta_socios WHERE conta_id = $1",
            conta["id"],
        )
        assert doc == "***456789**"
        assert "12345678901" not in doc

    async def test_reaplicar_nao_duplica_socio(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        for _ in range(3):
            await client.post(
                f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
                json={}, headers=usuario_adm["headers"],
            )
        total = await db_conn.fetchval(
            "SELECT count(*) FROM conta_socios WHERE conta_id = $1", conta["id"]
        )
        assert total == 1

    async def test_lista_socios_da_conta(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        resp = await client.get(
            f"/crm/enriquecimento/contas/{conta['id']}/socios",
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()[0]["nome"] == "JOSE DA SILVA"

    async def test_cnaes_secundarios_gravados(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        assert resp.json()["cnaes_secundarios_novos"] == 1
        codigos = await db_conn.fetchval(
            "SELECT cnae_codigo FROM conta_cnaes_secundarios WHERE conta_id = $1",
            conta["id"],
        )
        assert codigos == "4399103"


class TestBuscaReversaDeSocio:
    async def test_encontra_outra_conta_com_o_mesmo_socio(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta_a = await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_A)
        conta_b = await criar_conta(client, usuario_adm["headers"], cnpj=CNPJ_B)
        for conta in (conta_a, conta_b):
            await client.post(
                f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
                json={}, headers=usuario_adm["headers"],
            )

        resp = await client.get(
            "/crm/enriquecimento/socios/empresas",
            params={"nome": "Jose da Silva", "excluir_conta_id": conta_a["id"]},
            headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200, resp.text
        empresas = resp.json()["empresas"]
        assert len(empresas) == 1
        assert empresas[0]["conta_id"] == conta_b["id"]

    async def test_confianca_alta_so_com_documento_batendo(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )

        so_nome = await client.get(
            "/crm/enriquecimento/socios/empresas",
            params={"nome": "JOSE DA SILVA"}, headers=usuario_adm["headers"],
        )
        assert so_nome.json()["empresas"][0]["confianca"] == "media"

        com_doc = await client.get(
            "/crm/enriquecimento/socios/empresas",
            params={"nome": "JOSE DA SILVA", "documento": "***456789**"},
            headers=usuario_adm["headers"],
        )
        assert com_doc.json()["empresas"][0]["confianca"] == "alta"

    async def test_avisa_que_nao_procurou_fora_da_base(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        resp = await client.get(
            "/crm/enriquecimento/socios/empresas",
            params={"nome": "Fulano Inexistente"}, headers=usuario_adm["headers"],
        )
        assert resp.json()["empresas"] == []
        assert resp.json()["avisos"], (
            "sem aviso, 'nenhuma empresa' seria lido como 'não existe' em vez "
            "de 'não procurei fora daqui'"
        )


# ── Mapeamento de CNAE ───────────────────────────────────────────────

class TestMapearCnae:
    async def _cnae_registrado(self, client, headers):
        await client.get("/crm/enriquecimento/cnpj/" + CNPJ_A, headers=headers)

    async def test_operacional_mapeia_cnae_ainda_sem_classificacao(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        sdr = await criar_usuario(db_conn, client, "SDR")
        await self._cnae_registrado(client, sdr["headers"])
        vertical = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=sdr["headers"],
        )
        resp = await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": vertical.json()["id"], "grau_risco": 3},
            headers=sdr["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["grau_risco"] == 3
        assert resp.json()["vertical_nome"] == "Indústria"

    async def test_operacional_nao_remapeia_cnae_ja_classificado(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        await self._cnae_registrado(client, usuario_adm["headers"])
        vertical = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=usuario_adm["headers"],
        )
        await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": vertical.json()["id"]},
            headers=usuario_adm["headers"],
        )

        sdr = await criar_usuario(db_conn, client, "SDR")
        outra = await client.post(
            "/crm/dominio/verticais", json={"nome": "Serviços"},
            headers=sdr["headers"],
        )
        resp = await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": outra.json()["id"]}, headers=sdr["headers"],
        )
        assert resp.status_code == 403

    async def test_gestao_remapeia(
        self, db_conn, client, usuario_adm, usuario_franqueado, fonte_falsa
    ):
        await self._cnae_registrado(client, usuario_adm["headers"])
        v1 = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=usuario_adm["headers"],
        )
        v2 = await client.post(
            "/crm/dominio/verticais", json={"nome": "Serviços"},
            headers=usuario_adm["headers"],
        )
        await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": v1.json()["id"]}, headers=usuario_adm["headers"],
        )
        resp = await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": v2.json()["id"]},
            headers=usuario_franqueado["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["vertical_nome"] == "Serviços"

    async def test_cnae_desconhecido_404(self, db_conn, client, usuario_adm):
        resp = await client.patch(
            "/crm/enriquecimento/cnaes/9999999",
            json={"grau_risco": 2}, headers=usuario_adm["headers"],
        )
        assert resp.status_code == 404

    async def test_grau_de_risco_fora_da_faixa_recusado(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        await self._cnae_registrado(client, usuario_adm["headers"])
        resp = await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"grau_risco": 5}, headers=usuario_adm["headers"],
        )
        assert resp.status_code == 422

    async def test_vertical_mapeada_entra_na_proxima_conta(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        """
        O ganho que justifica o mapeamento: classificar o CNAE uma vez
        preenche a vertical de toda conta que vier depois com aquele código.
        """
        await self._cnae_registrado(client, usuario_adm["headers"])
        vertical = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=usuario_adm["headers"],
        )
        await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": vertical.json()["id"], "grau_risco": 3},
            headers=usuario_adm["headers"],
        )

        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        assert resp.json()["aplicados"]["vertical_id"] == str(vertical.json()["id"])

        atual = await db_conn.fetchval(
            "SELECT vertical_id FROM contas WHERE id = $1", conta["id"]
        )
        assert atual == vertical.json()["id"]

    async def test_lista_cnaes_a_mapear(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        await self._cnae_registrado(client, usuario_adm["headers"])
        resp = await client.get(
            "/crm/enriquecimento/cnaes?apenas_nao_mapeados=true",
            headers=usuario_adm["headers"],
        )
        codigos = [c["codigo"] for c in resp.json()]
        assert "2511000" in codigos


# ── Resumo e permissões ──────────────────────────────────────────────

class TestResumo:
    async def test_conta_o_que_falta_mapear(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        resp = await client.get(
            "/crm/enriquecimento/resumo", headers=usuario_adm["headers"]
        )
        corpo = resp.json()
        assert corpo["contas_enriquecidas"] == 1
        # O CNAE tem vertical (derivada) mas ainda não passou por gente.
        assert corpo["cnaes_a_confirmar"] >= 1
        assert corpo["contas_com_vertical_sugerida"] == 1
        assert corpo["contas_sem_vertical"] == 0
        assert corpo["fontes"] == ["brasilapi"]


class TestPermissoes:
    async def test_todo_cargo_valido_consulta(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        for cargo in ("SDR", "EV", "EP", "EC"):
            user = await criar_usuario(db_conn, client, cargo)
            resp = await client.get(
                f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=user["headers"]
            )
            assert resp.status_code == 200, f"{cargo}: {resp.text}"

    async def test_sem_token_401(self, db_conn, client):
        resp = await client.get(f"/crm/enriquecimento/cnpj/{CNPJ_A}")
        assert resp.status_code == 401


class TestDeParaRetroativo:
    """
    O que faz o de-para valer: classificar um CNAE preenche a vertical das
    contas que JÁ existem com aquele código. Sem isso, mapear só valeria
    para consultas futuras e as 1.751 contas ficariam esperando.
    """

    async def _mapear(self, client, headers, vertical_id, aplicar=True):
        return await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={
                "vertical_id": vertical_id,
                "grau_risco": 3,
                "aplicar_em_contas": aplicar,
            },
            headers=headers,
        )

    async def _duas_contas_com_cnae(self, db_conn, client, headers):
        """
        Reproduz a BASE LEGADA: contas com CNAE e sem vertical.

        Depois da 015 isso não acontece mais sozinho — o CNAE nasce
        derivado e a conta já sai classificada. O de-para retroativo existe
        justamente para o que entrou ANTES, então o cenário é montado à mão
        limpando a vertical dos dois lados.
        """
        contas = []
        for cnpj in (CNPJ_A, CNPJ_B):
            conta = await criar_conta(client, headers, cnpj=cnpj)
            await client.post(
                f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
                json={}, headers=headers,
            )
            contas.append(conta)
        await db_conn.execute(
            "UPDATE contas SET vertical_id = NULL WHERE cnae_codigo = '2511000'"
        )
        await db_conn.execute(
            """
            UPDATE cnaes
               SET vertical_id = NULL, mapeado_em = NULL,
                   mapeamento_origem = NULL
             WHERE codigo = '2511000'
            """
        )
        return contas

    async def test_mapear_classifica_as_contas_que_ja_existiam(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        contas = await self._duas_contas_com_cnae(
            db_conn, client, usuario_adm["headers"]
        )
        vertical = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=usuario_adm["headers"],
        )
        vid = vertical.json()["id"]

        resp = await self._mapear(client, usuario_adm["headers"], vid)
        assert resp.status_code == 200, resp.text
        assert resp.json()["contas_atualizadas"] == 2

        for conta in contas:
            atual = await db_conn.fetchval(
                "SELECT vertical_id FROM contas WHERE id = $1", conta["id"]
            )
            assert atual == vid

    async def test_nao_toca_em_conta_que_ja_tem_vertical(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        """Mesma regra do enriquecimento: trabalho humano não é sobrescrito."""
        outra = await client.post(
            "/crm/dominio/verticais", json={"nome": "Serviços"},
            headers=usuario_adm["headers"],
        )
        conta = await criar_conta(
            client, usuario_adm["headers"], vertical_id=outra.json()["id"]
        )
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        vertical = await client.post(
            "/crm/dominio/verticais", json={"nome": "Metalurgia"},
            headers=usuario_adm["headers"],
        )

        resp = await self._mapear(
            client, usuario_adm["headers"], vertical.json()["id"]
        )
        assert resp.json()["contas_atualizadas"] == 0

        atual = await db_conn.fetchval(
            "SELECT vertical_id FROM contas WHERE id = $1", conta["id"]
        )
        assert atual == outra.json()["id"]

    async def test_sem_aplicar_em_contas_nao_mexe_em_nada(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        # Base legada: sem vertical dos dois lados.
        await db_conn.execute(
            "UPDATE contas SET vertical_id = NULL WHERE id = $1", conta["id"]
        )
        await db_conn.execute(
            """
            UPDATE cnaes SET vertical_id = NULL, mapeado_em = NULL,
                             mapeamento_origem = NULL
             WHERE codigo = '2511000'
            """
        )
        vertical = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=usuario_adm["headers"],
        )

        resp = await self._mapear(
            client, usuario_adm["headers"], vertical.json()["id"], aplicar=False
        )
        assert resp.json()["contas_atualizadas"] == 0
        atual = await db_conn.fetchval(
            "SELECT vertical_id FROM contas WHERE id = $1", conta["id"]
        )
        assert atual is None

    async def test_lista_mostra_quantas_contas_esperam_vertical(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        await self._duas_contas_com_cnae(db_conn, client, usuario_adm["headers"])
        resp = await client.get(
            "/crm/enriquecimento/cnaes", headers=usuario_adm["headers"]
        )
        linha = [c for c in resp.json() if c["codigo"] == "2511000"][0]
        assert linha["qtd_contas"] == 2
        assert linha["qtd_contas_sem_vertical"] == 2

    async def test_contador_zera_depois_de_mapear(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        await self._duas_contas_com_cnae(db_conn, client, usuario_adm["headers"])
        vertical = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=usuario_adm["headers"],
        )
        await self._mapear(client, usuario_adm["headers"], vertical.json()["id"])

        resp = await client.get(
            "/crm/enriquecimento/cnaes", headers=usuario_adm["headers"]
        )
        linha = [c for c in resp.json() if c["codigo"] == "2511000"][0]
        assert linha["qtd_contas_sem_vertical"] == 0

        resumo = await client.get(
            "/crm/enriquecimento/resumo", headers=usuario_adm["headers"]
        )
        assert resumo.json()["contas_sem_vertical"] == 0


class TestSemQuadroSocietario:
    """
    Empresário individual e MEI não têm QSA na Receita — a resposta vem com
    `qsa` vazio, e isso não é falha de consulta.
    """

    @pytest.fixture
    def fonte_sem_qsa(self, monkeypatch):
        async def buscar(cnpj):
            return {**PAYLOAD, "cnpj": cnpj, "qsa": []}, None

        monkeypatch.setattr(settings, "ENRIQUECIMENTO_FONTES", "brasilapi")
        monkeypatch.setitem(fontes.BUSCADORES, fontes.BRASILAPI, buscar)

    async def test_enriquecimento_conclui_sem_socios(
        self, db_conn, client, usuario_adm, fonte_sem_qsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["socios_novos"] == 0
        # O resto do cadastro entra normalmente: QSA vazio não invalida nada.
        assert resp.json()["aplicados"]["cidade"] == "GUARULHOS"

        enriquecida = await db_conn.fetchval(
            "SELECT enriquecida_em FROM contas WHERE id = $1", conta["id"]
        )
        assert enriquecida is not None


class TestVerticalDerivada:
    """
    015: o CNAE nasce classificado pela seção da CNAE 2.0, em vez de
    esperar alguém preencher um a um.
    """

    async def test_consulta_ja_deixa_o_cnae_com_vertical(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        row = await db_conn.fetchrow(
            """
            SELECT c.vertical_id, c.mapeamento_origem, v.nome, v.slug
              FROM cnaes c JOIN verticais v ON v.id = c.vertical_id
             WHERE c.codigo = '2511000'
            """
        )
        # 25 = divisão da seção C (indústria de transformação).
        assert row is not None, "o CNAE devia nascer com vertical derivada"
        assert row["slug"] == "industria"
        assert row["mapeamento_origem"] == "derivado"

    async def test_conta_nasce_com_a_vertical_da_secao(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        conta = await criar_conta(client, usuario_adm["headers"])
        resp = await client.post(
            f"/crm/enriquecimento/contas/{conta['id']}/aplicar",
            json={}, headers=usuario_adm["headers"],
        )
        assert "vertical_id" in resp.json()["aplicados"]

        nome = await db_conn.fetchval(
            """
            SELECT v.nome FROM contas c JOIN verticais v ON v.id = c.vertical_id
             WHERE c.id = $1
            """,
            conta["id"],
        )
        assert nome == "Indústria"

    async def test_nao_duplica_vertical_que_ja_existe(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        """O casamento é por slug — 'Indústria' criada à mão é reaproveitada."""
        criada = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=usuario_adm["headers"],
        )
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        total = await db_conn.fetchval(
            "SELECT count(*) FROM verticais WHERE slug = 'industria'"
        )
        assert total == 1
        vertical_do_cnae = await db_conn.fetchval(
            "SELECT vertical_id FROM cnaes WHERE codigo = '2511000'"
        )
        assert vertical_do_cnae == criada.json()["id"]

    async def test_operacional_pode_corrigir_uma_sugestao(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        """
        A trava de gestão é sobre DECISÃO HUMANA. Corrigir o que a regra
        sugeriu é trabalho de quem está com a conta na frente.
        """
        sdr = await criar_usuario(db_conn, client, "SDR")
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=sdr["headers"]
        )
        outra = await client.post(
            "/crm/dominio/verticais", json={"nome": "Metalurgia pesada"},
            headers=sdr["headers"],
        )
        resp = await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": outra.json()["id"], "grau_risco": 3},
            headers=sdr["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["mapeamento_origem"] == "humano"

    async def test_operacional_nao_troca_o_que_gente_decidiu(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        v1 = await client.post(
            "/crm/dominio/verticais", json={"nome": "Decidida"},
            headers=usuario_adm["headers"],
        )
        await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": v1.json()["id"]},
            headers=usuario_adm["headers"],
        )

        sdr = await criar_usuario(db_conn, client, "SDR")
        v2 = await client.post(
            "/crm/dominio/verticais", json={"nome": "Outra"},
            headers=sdr["headers"],
        )
        resp = await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": v2.json()["id"]}, headers=sdr["headers"],
        )
        assert resp.status_code == 403

    async def test_grau_de_risco_nao_e_derivado(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        """
        Grau de risco vale por subclasse no Anexo I da NR-4. Derivar por
        seção seria inventar o número que dimensiona SESMT.
        """
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        grau = await db_conn.fetchval(
            "SELECT grau_risco FROM cnaes WHERE codigo = '2511000'"
        )
        assert grau is None

    async def test_sugestao_continua_na_fila_de_confirmacao(
        self, db_conn, client, usuario_adm, fonte_falsa
    ):
        """
        Derivado não é resolvido: a sugestão fica na lista para alguém
        confirmar ou corrigir.
        """
        await client.get(
            f"/crm/enriquecimento/cnpj/{CNPJ_A}", headers=usuario_adm["headers"]
        )
        resp = await client.get(
            "/crm/enriquecimento/cnaes?apenas_nao_mapeados=true",
            headers=usuario_adm["headers"],
        )
        codigos = [c["codigo"] for c in resp.json()]
        assert "2511000" in codigos

        # Depois de confirmada por gente, sai da fila.
        vertical = await client.post(
            "/crm/dominio/verticais", json={"nome": "Indústria"},
            headers=usuario_adm["headers"],
        )
        await client.patch(
            "/crm/enriquecimento/cnaes/2511000",
            json={"vertical_id": vertical.json()["id"]},
            headers=usuario_adm["headers"],
        )
        resp = await client.get(
            "/crm/enriquecimento/cnaes?apenas_nao_mapeados=true",
            headers=usuario_adm["headers"],
        )
        assert "2511000" not in [c["codigo"] for c in resp.json()]
