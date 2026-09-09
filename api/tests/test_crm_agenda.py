"""
HIPO — Testes do router /crm/agenda.

As regras puras já estão em test_agenda_regras.py. Aqui o foco é o que só
aparece com banco:

  * a reunião e a tarefa nascendo JUNTAS, na mesma transação
  * o horário e o dono morando na tarefa (reagendar é PATCH no prazo)
  * o conflito do mesmo anfitrião, com cancelada liberando o slot
  * "colocar na agenda" reaproveitando a tarefa em vez de criar outra
  * a grade montando os cinco dias, os slots e os agregados do topo
  * o Google desligado NÃO impedindo nada — só marcando o erro na linha

O GOOGLE NÃO É CHAMADO EM NENHUM TESTE. `GOOGLE_SA_ARQUIVO` não existe no
ambiente de teste, então `google_agenda.configurado()` devolve False e toda
sincronização vira `google_erro` sem tocar a rede. Isso é de propósito: uma
suíte que precisasse de credencial do Google para rodar não rodaria no CI —
e o caminho "integração desligada" é o mesmo que roda numa máquina de
desenvolvimento, então é o que mais precisa de teste.
"""
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from services import agenda as regras
from tests.conftest import criar_usuario

CNPJ_A = "11.222.333/0001-81"
CNPJ_B = "11.444.777/0001-61"


# ── Helpers ──────────────────────────────────────────────────────────

def proxima_segunda(semanas=1):
    """
    Uma segunda-feira futura, no fuso da operação.

    Ancorado no fuso da operação e não em UTC pelo mesmo motivo do `em()`
    de test_crm_tarefas: entre 21h e meia-noite o dia UTC já é o seguinte, e
    a semana calculada mudaria conforme a hora em que a suíte rodasse.
    """
    hoje = datetime.now(regras.FUSO_OPERACAO).date()
    segunda = regras.segunda_da_semana(hoje) + timedelta(weeks=semanas)
    return segunda


def as_horas(dia, hora, minuto=0):
    return datetime(
        dia.year, dia.month, dia.day, hora, minuto, tzinfo=regras.FUSO_OPERACAO
    ).isoformat()


async def nova_conta(client, headers, cnpj=CNPJ_A, razao="Metalurgica Alfa LTDA", **extra):
    corpo = {"razao_social": razao, "cnpj": cnpj}
    corpo.update(extra)
    resp = await client.post("/crm/contas", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def nova_oportunidade(client, headers, conta_id):
    resp = await client.post(
        "/crm/oportunidades", json={"conta_id": conta_id}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def novo_tipo(client, headers, sigla="CF", nome="Reuniao de fechamento"):
    resp = await client.post(
        "/crm/agenda/tipos", json={"sigla": sigla, "nome": nome}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def nova_reuniao(client, headers, oportunidade_id, usuario_id, **extra):
    corpo = {
        "oportunidade_id": oportunidade_id,
        "anfitriao_id": usuario_id,
        "inicio": as_horas(proxima_segunda(), 9),
    }
    corpo.update(extra)
    resp = await client.post("/crm/agenda/reunioes", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def cenario(db_conn, client, usuario_adm):
    """Conta + oportunidade + tipo, que quase todo teste precisa."""
    h = usuario_adm["headers"]
    conta = await nova_conta(client, h)
    opp = await nova_oportunidade(client, h, conta["id"])
    tipo = await novo_tipo(client, h)
    me = (await client.get("/auth/me", headers=h)).json()
    return {
        "headers": h, "conta": conta, "oportunidade": opp,
        "tipo": tipo, "usuario_id": me["id"],
    }


# ── Tipos de reunião ─────────────────────────────────────────────────

class TestTipos:
    async def test_gestao_cria_tipo(self, cenario, client):
        resp = await client.get("/crm/agenda/tipos", headers=cenario["headers"])
        assert resp.status_code == 200
        assert [t["sigla"] for t in resp.json()] == ["CF"]

    async def test_post_e_idempotente_pelo_slug(self, cenario, client):
        """
        Criar algo que já existe é o mesmo que selecionar o que existe —
        mesma escolha das outras listas de domínio.
        """
        de_novo = await novo_tipo(client, cenario["headers"])
        assert de_novo["id"] == cenario["tipo"]["id"]

    async def test_sigla_repetida_com_nome_novo_e_409(self, cenario, client):
        """
        Slug diferente, sigla igual: aqui é conflito de verdade, porque duas
        siglas iguais deixariam o rótulo da grade ambíguo.
        """
        resp = await client.post(
            "/crm/agenda/tipos",
            json={"sigla": "CF", "nome": "Outra coisa"},
            headers=cenario["headers"],
        )
        assert resp.status_code == 409

    async def test_sigla_vira_maiuscula(self, cenario, client):
        resp = await client.post(
            "/crm/agenda/tipos",
            json={"sigla": "fup", "nome": "Follow up"},
            headers=cenario["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["sigla"] == "FUP"

    async def test_operacional_le_mas_nao_cria(self, db_conn, client):
        """
        A guarda contra a deriva de vocabulário: se cada vendedor inventar a
        sigla dele, "quantas CF por mês" para de ser uma pergunta
        respondível. Ler e usar continua sendo de todo mundo.
        """
        ev = await criar_usuario(db_conn, client, "EV", "ev-tipo@teste.com")
        assert (await client.get(
            "/crm/agenda/tipos", headers=ev["headers"]
        )).status_code == 200
        resp = await client.post(
            "/crm/agenda/tipos",
            json={"sigla": "XX", "nome": "Inventada"},
            headers=ev["headers"],
        )
        assert resp.status_code == 403


# ── Criar ────────────────────────────────────────────────────────────

class TestCriar:
    async def test_cria_reuniao_e_tarefa_juntas(self, cenario, client, db_conn):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            tipo_id=cenario["tipo"]["id"],
        )
        assert r["tarefa_id"]
        tipo_tarefa = await db_conn.fetchval(
            "SELECT tipo FROM tarefas WHERE id = $1", r["tarefa_id"]
        )
        # Sempre 'reuniao'. Se presencial virasse tipo 'visita', "quantas
        # reuniões em agosto" precisaria somar dois tipos.
        assert tipo_tarefa == "reuniao"

    async def test_o_horario_mora_na_tarefa(self, cenario, client, db_conn):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        prazo = await db_conn.fetchval(
            "SELECT prazo FROM tarefas WHERE id = $1", r["tarefa_id"]
        )
        assert prazo == datetime.fromisoformat(r["inicio"])
        # E não existe coluna própria guardando o mesmo instante.
        colunas = await db_conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'reunioes'"
        )
        nomes = {c["column_name"] for c in colunas}
        assert "inicio" not in nomes
        assert "responsavel_id" not in nomes
        assert "titulo" not in nomes

    async def test_o_anfitriao_e_o_responsavel_da_tarefa(self, cenario, client, db_conn):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        responsavel = await db_conn.fetchval(
            "SELECT responsavel_id FROM tarefas WHERE id = $1", r["tarefa_id"]
        )
        assert str(responsavel) == r["anfitriao_id"] == cenario["usuario_id"]

    async def test_fim_e_derivado_da_duracao(self, cenario, client):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            duracao_min=90,
        )
        inicio = datetime.fromisoformat(r["inicio"])
        assert datetime.fromisoformat(r["fim"]) - inicio == timedelta(minutes=90)

    async def test_titulo_em_branco_vira_o_rotulo(self, cenario, client):
        """
        Obrigar a digitar um título ao marcar de um slot vazio produziria
        "Reunião" repetido quinze vezes na linha do tempo.
        """
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            tipo_id=cenario["tipo"]["id"],
        )
        assert r["titulo"].startswith("CF - Metalurgica Alfa")
        assert r["titulo"].endswith("- ON")

    async def test_titulo_informado_e_respeitado(self, cenario, client):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            titulo="Fechamento com o RH",
        )
        assert r["titulo"] == "Fechamento com o RH"

    async def test_rotulo_no_formato_da_planilha(self, cenario, client):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            tipo_id=cenario["tipo"]["id"], modalidade="presencial",
        )
        assert r["rotulo"].startswith("CF - ")
        assert r["rotulo"].endswith("- PRES")

    async def test_nome_fantasia_ganha_da_razao_social_no_rotulo(self, cenario, client):
        """É como a equipe chama a empresa, e é o que cabe no cartão."""
        h = cenario["headers"]
        conta = await nova_conta(
            client, h, cnpj=CNPJ_B, razao="Comercial Beta LTDA",
            nome_fantasia="Beta",
        )
        opp = await nova_oportunidade(client, h, conta["id"])
        r = await nova_reuniao(client, h, opp["id"], cenario["usuario_id"])
        assert "Beta" in r["rotulo"]
        assert "Comercial" not in r["rotulo"]

    async def test_slot_e_fora_da_grade_vem_prontos(self, cenario, client):
        """
        Calculados no servidor porque a grade, o convite do Google e o
        cartão precisam concordar — três implementações da mesma conta
        divergem.
        """
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        assert r["slot"] == "09:00"
        assert r["fora_da_grade"] is False

    async def test_horario_especifico_e_aceito_e_marcado(self, cenario, client):
        """
        "O SDR pode editar para um horário mais específico." A reunião é
        desenhada na linha do slot que a contém e avisa que está fora.
        """
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            inicio=as_horas(proxima_segunda(), 9, 15),
        )
        assert r["slot"] == "09:00"
        assert r["fora_da_grade"] is True

    async def test_reuniao_de_parceiro(self, cenario, client):
        """
        O alvo vem da tarefa, então a agenda aceita parceiro de graça — sem
        uma linha de código só para isso.
        """
        h = cenario["headers"]
        parceiro = await nova_conta(
            client, h, cnpj=CNPJ_B, razao="Contabilidade Beta LTDA"
        )
        await client.patch(
            f"/crm/parceiros/{parceiro['id']}", json={"eh_finder": True}, headers=h
        )
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "conta_id": parceiro["id"],
                "anfitriao_id": cenario["usuario_id"],
                "inicio": as_horas(proxima_segunda(), 10),
            },
            headers=h,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["oportunidade_id"] is None
        assert resp.json()["conta_id"] == parceiro["id"]

    async def test_sem_alvo_e_422(self, cenario, client):
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "anfitriao_id": cenario["usuario_id"],
                "inicio": as_horas(proxima_segunda(), 9),
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422

    async def test_dois_alvos_e_422(self, cenario, client):
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": cenario["oportunidade"]["id"],
                "conta_id": cenario["conta"]["id"],
                "anfitriao_id": cenario["usuario_id"],
                "inicio": as_horas(proxima_segunda(), 9),
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("dias", [5, 6])
    async def test_fim_de_semana_e_recusado(self, cenario, client, dias):
        """
        Registro que a tela esconde é pior que registro recusado: a grade
        tem cinco colunas.
        """
        dia = proxima_segunda() + timedelta(days=dias)
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": cenario["oportunidade"]["id"],
                "anfitriao_id": cenario["usuario_id"],
                "inicio": as_horas(dia, 9),
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422
        assert "segunda a sexta" in resp.text

    async def test_tipo_inexistente_e_422(self, cenario, client):
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": cenario["oportunidade"]["id"],
                "anfitriao_id": cenario["usuario_id"],
                "inicio": as_horas(proxima_segunda(), 9),
                "tipo_id": 999999,
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422

    async def test_convidado_invalido_e_422(self, cenario, client):
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": cenario["oportunidade"]["id"],
                "anfitriao_id": cenario["usuario_id"],
                "inicio": as_horas(proxima_segunda(), 9),
                "convidados": ["nao-e-email"],
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422


# ── A prévia do convite ──────────────────────────────────────────────

class TestConvite:
    """
    O texto que sai no Google, montado pelo servidor e devolvido junto da
    reunião. Vem pronto — e não montado no navegador — porque é
    literalmente o que o cliente vai receber: duas versões da mesma string
    deixariam a tela prometer um convite e o Google entregar outro.
    """

    async def test_titulo_leva_razao_social_cnpj_e_empresa(self, cenario, client):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            tipo_id=cenario["tipo"]["id"],
        )
        assert r["convite_titulo"] == (
            "Metalurgica Alfa LTDA 11.222.333/0001-81"
            " | Reuniao de fechamento Controller MedSeg"
        )

    async def test_descricao_segue_o_modelo_da_operacao(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        contato = (await client.post(
            "/crm/contatos",
            json={
                "nome": "Nivaldo", "telefone": "11999477607",
                "email": "adm@nnredutores.com.br",
                "conta_id": cenario["conta"]["id"],
            },
            headers=h,
        )).json()
        await db_conn.execute(
            "UPDATE usuarios SET telefone = $2 WHERE id = $1", uid, "(11) 94251-9976"
        )
        r = await nova_reuniao(
            client, h, opp, uid,
            tipo_id=cenario["tipo"]["id"], contato_id=contato["id"],
        )
        linhas = r["convite_descricao"].split("\n")
        assert linhas[0] == r["convite_titulo"]
        assert linhas[2] == "ONLINE"
        assert "Contato: Nivaldo" in linhas
        assert "Email: adm@nnredutores.com.br" in linhas
        assert "Consultor: Test ADM" in linhas
        assert "Cel: (11) 94251-9976" in linhas

    async def test_nao_vaza_o_numero_da_oportunidade(self, cenario, client):
        """É vocabulário nosso, e o cliente vê tudo o que estiver aqui."""
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        assert cenario["oportunidade"]["numero"] not in r["convite_descricao"]

    async def test_o_rotulo_da_grade_continua_curto(self, cenario, client):
        """
        Dois leitores, dois textos. Se voltarem a ser um só, ou o cliente
        recebe uma sigla que não entende, ou a célula da grade recebe um
        parágrafo.
        """
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            tipo_id=cenario["tipo"]["id"],
        )
        assert r["rotulo"] != r["convite_titulo"]
        assert len(r["rotulo"]) < len(r["convite_titulo"])
        assert "11.222.333" not in r["rotulo"]


# ── Participantes ────────────────────────────────────────────────────

class TestParticipantes:
    async def test_grava_e_devolve_os_participantes(self, cenario, client, db_conn):
        ep = await criar_usuario(db_conn, client, "EP", "ep-agenda@teste.com")
        me_ep = (await client.get("/auth/me", headers=ep["headers"])).json()
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            participantes=[me_ep["id"]],
        )
        assert [p["usuario_id"] for p in r["participantes"]] == [me_ep["id"]]

    async def test_anfitriao_nao_entra_na_lista_de_participantes(self, cenario, client):
        """
        Ele é `tarefas.responsavel_id`. Repeti-lo criaria a pergunta "e se
        as duas discordarem?", que não tem resposta boa.
        """
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        assert r["participantes"] == []

    async def test_participante_inativo_e_422(self, cenario, client, db_conn):
        outro = await criar_usuario(db_conn, client, "EV", "inativo@teste.com")
        me = (await client.get("/auth/me", headers=outro["headers"])).json()
        await db_conn.execute("UPDATE usuarios SET ativo = FALSE WHERE id = $1", me["id"])
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": cenario["oportunidade"]["id"],
                "anfitriao_id": cenario["usuario_id"],
                "inicio": as_horas(proxima_segunda(), 9),
                "participantes": [me["id"]],
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422


# ── Conflito ─────────────────────────────────────────────────────────

class TestConflito:
    async def test_mesmo_slot_do_mesmo_anfitriao_e_409(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": opp, "anfitriao_id": uid,
                "inicio": as_horas(proxima_segunda(), 9),
            },
            headers=h,
        )
        assert resp.status_code == 409

    async def test_a_mensagem_nomeia_a_reuniao_que_ja_estava_la(self, cenario, client):
        """
        "Esse horário já está ocupado" sozinho manda o vendedor procurar na
        grade o que ele mesmo acabou de tentar marcar.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid, titulo="Fechamento com o RH")
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": opp, "anfitriao_id": uid,
                "inicio": as_horas(proxima_segunda(), 9),
            },
            headers=h,
        )
        assert "Fechamento com o RH" in resp.text

    async def test_sobreposicao_parcial_tambem_e_409(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid, duracao_min=60)
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": opp, "anfitriao_id": uid,
                "inicio": as_horas(proxima_segunda(), 9, 30),
            },
            headers=h,
        )
        assert resp.status_code == 409

    async def test_slot_seguinte_encaixa(self, cenario, client):
        """
        09:00–09:30 e 09:30–10:00 convivem: é a grade cheia funcionando,
        não conflito.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": opp, "anfitriao_id": uid,
                "inicio": as_horas(proxima_segunda(), 9, 30),
            },
            headers=h,
        )
        assert resp.status_code == 201, resp.text

    async def test_outro_anfitriao_pode_usar_o_mesmo_horario(self, cenario, client, db_conn):
        """A grade é a coluna de UMA pessoa."""
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        ev = await criar_usuario(db_conn, client, "EV", "ev-conflito@teste.com")
        me_ev = (await client.get("/auth/me", headers=ev["headers"])).json()
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": opp, "anfitriao_id": me_ev["id"],
                "inicio": as_horas(proxima_segunda(), 9),
            },
            headers=h,
        )
        assert resp.status_code == 201, resp.text

    async def test_cancelada_libera_o_slot(self, cenario, client):
        """
        Cancelar é dizer que aquilo não vai acontecer, e o horário volta a
        valer.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        await client.post(
            f"/crm/agenda/reunioes/{r['id']}/cancelar",
            json={"motivo": "cliente remarcou"}, headers=h,
        )
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": opp, "anfitriao_id": uid,
                "inicio": as_horas(proxima_segunda(), 9),
            },
            headers=h,
        )
        assert resp.status_code == 201, resp.text

    async def test_concluida_continua_ocupando(self, cenario, client):
        """
        Concluída aconteceu: o horário esteve ocupado de verdade, e deixar
        marcar por cima reescreveria o passado da agenda.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        concluir = await client.post(
            f"/crm/tarefas/{r['tarefa_id']}/concluir",
            json={
                "resultado": "aconteceu",
                "proxima": {
                    "tipo": "ligacao", "titulo": "Retomar",
                    "responsavel_id": uid,
                    "prazo": as_horas(proxima_segunda(2), 9),
                },
            },
            headers=h,
        )
        assert concluir.status_code == 200, concluir.text
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": opp, "anfitriao_id": uid,
                "inicio": as_horas(proxima_segunda(), 9),
            },
            headers=h,
        )
        assert resp.status_code == 409

    async def test_editar_nao_conflita_consigo_mesma(self, cenario, client):
        """
        Sem o `ignorar_reuniao_id`, mudar só a modalidade devolveria 409
        contra a própria reunião.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"duracao_min": 60}, headers=h,
        )
        assert resp.status_code == 200, resp.text


# ── Colocar na agenda uma tarefa que já existe ───────────────────────

class TestDeTarefa:
    async def _tarefa(self, client, headers, opp_id, uid, tipo="reuniao"):
        resp = await client.post(
            "/crm/tarefas",
            json={
                "oportunidade_id": opp_id, "tipo": tipo,
                "titulo": "Apresentar a proposta",
                "responsavel_id": uid,
                "prazo": as_horas(proxima_segunda(), 14),
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    async def test_reaproveita_a_tarefa(self, cenario, client, db_conn):
        """
        Criar uma segunda tarefa diria a mesma coisa duas vezes na linha do
        tempo e contaria duas reuniões na produção do mês.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = await self._tarefa(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["tarefa_id"] == t["id"]
        assert await db_conn.fetchval(
            "SELECT count(*) FROM tarefas WHERE oportunidade_id = $1", opp
        ) == 1

    async def test_herda_horario_titulo_e_dono(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = await self._tarefa(client, h, opp, uid)
        r = (await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h
        )).json()
        assert r["titulo"] == t["titulo"]
        assert r["inicio"] == t["prazo"]
        assert r["anfitriao_id"] == uid

    async def test_visita_entra_e_mantem_o_tipo_da_tarefa(self, cenario, client, db_conn):
        """
        Reclassificar por baixo mudaria números de meses fechados.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = await self._tarefa(client, h, opp, uid, tipo="visita")
        resp = await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}",
            json={"modalidade": "presencial"}, headers=h,
        )
        assert resp.status_code == 201, resp.text
        assert await db_conn.fetchval(
            "SELECT tipo FROM tarefas WHERE id = $1", t["id"]
        ) == "visita"

    async def test_ligacao_nao_entra_na_agenda(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = await self._tarefa(client, h, opp, uid, tipo="ligacao")
        resp = await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h
        )
        assert resp.status_code == 422
        assert "Reunião ou Visita" in resp.text

    async def test_duas_vezes_e_409(self, cenario, client):
        """O UNIQUE de tarefa_id: dois cliques não podem virar duas linhas."""
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = await self._tarefa(client, h, opp, uid)
        await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h
        )
        resp = await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h
        )
        assert resp.status_code == 409

    async def test_tarefa_fechada_nao_entra(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = await self._tarefa(client, h, opp, uid)
        await client.post(
            f"/crm/tarefas/{t['id']}/cancelar", json={"motivo": "x"}, headers=h
        )
        resp = await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h
        )
        assert resp.status_code == 422

    async def test_a_tarefa_passa_a_saber_da_reuniao(self, cenario, client):
        """
        `reuniao_id` no payload da tarefa é o que permite à aba mostrar
        "Agendar" numas e "Ver na agenda" noutras sem um N+1.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = await self._tarefa(client, h, opp, uid)
        antes = (await client.get(f"/crm/tarefas/{t['id']}", headers=h)).json()
        assert antes["reuniao_id"] is None
        r = (await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}", json={}, headers=h
        )).json()
        depois = (await client.get(f"/crm/tarefas/{t['id']}", headers=h)).json()
        assert depois["reuniao_id"] == r["id"]


# ── Editar ───────────────────────────────────────────────────────────

class TestEditar:
    async def test_reagendar_move_o_prazo_da_tarefa(self, cenario, client, db_conn):
        """
        `inicio` não é coluna de `reunioes`. Reagendar pela agenda e pela
        aba de tarefas têm que produzir exatamente o mesmo efeito.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        novo = as_horas(proxima_segunda(), 15)
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}", json={"inicio": novo}, headers=h
        )
        assert resp.status_code == 200, resp.text
        prazo = await db_conn.fetchval(
            "SELECT prazo FROM tarefas WHERE id = $1", r["tarefa_id"]
        )
        assert prazo == datetime.fromisoformat(novo)
        assert resp.json()["slot"] == "15:00"

    async def test_trocar_anfitriao_move_o_responsavel(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        ev = await criar_usuario(db_conn, client, "EV", "ev-troca@teste.com")
        me_ev = (await client.get("/auth/me", headers=ev["headers"])).json()
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"anfitriao_id": me_ev["id"]}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        responsavel = await db_conn.fetchval(
            "SELECT responsavel_id FROM tarefas WHERE id = $1", r["tarefa_id"]
        )
        assert str(responsavel) == me_ev["id"]

    async def test_reagendar_para_horario_ocupado_e_409(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        primeira = await nova_reuniao(client, h, opp, uid)
        segunda = await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(proxima_segunda(), 10)
        )
        resp = await client.patch(
            f"/crm/agenda/reunioes/{segunda['id']}",
            json={"inicio": as_horas(proxima_segunda(), 9)}, headers=h,
        )
        assert resp.status_code == 409
        assert primeira["titulo"] in resp.text

    async def test_troca_de_modalidade(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"modalidade": "presencial", "endereco": "Rua X, 10"},
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["modalidade"] == "presencial"
        assert resp.json()["modalidade_rotulo"] == "Presencial"
        assert resp.json()["rotulo"].endswith("- PRES")

    async def test_substitui_a_lista_de_participantes(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        a = await criar_usuario(db_conn, client, "EP", "p1@teste.com")
        b = await criar_usuario(db_conn, client, "EP", "p2@teste.com")
        id_a = (await client.get("/auth/me", headers=a["headers"])).json()["id"]
        id_b = (await client.get("/auth/me", headers=b["headers"])).json()["id"]
        r = await nova_reuniao(client, h, opp, uid, participantes=[id_a])
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"participantes": [id_b]}, headers=h,
        )
        assert [p["usuario_id"] for p in resp.json()["participantes"]] == [id_b]

    async def test_reuniao_concluida_nao_se_edita(self, cenario, client):
        """
        Reescrever o horário de uma reunião que já aconteceu apagaria o
        histórico que a linha do tempo existe para mostrar.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        await client.post(
            f"/crm/tarefas/{r['tarefa_id']}/concluir",
            json={
                "resultado": "ok",
                "proxima": {
                    "tipo": "ligacao", "titulo": "Retomar",
                    "responsavel_id": uid, "prazo": as_horas(proxima_segunda(2), 9),
                },
            },
            headers=h,
        )
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}", json={"duracao_min": 60}, headers=h
        )
        assert resp.status_code == 422

    async def test_titulo_em_branco_e_422(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}", json={"titulo": "   "}, headers=h
        )
        assert resp.status_code == 422


# ── Cancelar ─────────────────────────────────────────────────────────

class TestCancelar:
    async def test_fecha_a_tarefa(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/cancelar",
            json={"motivo": "cliente remarcou"}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["situacao"] == "cancelada"
        motivo = await db_conn.fetchval(
            "SELECT motivo_cancelamento FROM tarefas WHERE id = $1", r["tarefa_id"]
        )
        assert motivo == "cliente remarcou"

    async def test_nao_exige_proxima(self, cenario, client):
        """
        Cancelar é dizer que aquilo não deveria ter sido marcado, não que o
        negócio andou. Mesma regra do cancelamento de tarefa.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/cancelar", json={}, headers=h
        )
        assert resp.status_code == 200

    async def test_duas_vezes_e_422(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        await client.post(f"/crm/agenda/reunioes/{r['id']}/cancelar", json={}, headers=h)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/cancelar", json={}, headers=h
        )
        assert resp.status_code == 422

    async def test_cancelar_a_tarefa_por_fora_nao_quebra(self, cenario, client):
        """
        A tela de gestão e a aba da oportunidade cancelam pela rota de
        tarefa, que chama `remover_evento_da_tarefa`. Com o Google
        desligado a chamada é inócua — o que este teste trava é que ela não
        estoure e derrube o cancelamento.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/tarefas/{r['tarefa_id']}/cancelar",
            json={"motivo": "duplicada"}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        depois = (await client.get(f"/crm/agenda/reunioes/{r['id']}", headers=h)).json()
        assert depois["situacao"] == "cancelada"


# ── A grade da semana ────────────────────────────────────────────────

class TestSemana:
    async def test_monta_cinco_dias_e_dezoito_slots(self, cenario, client):
        segunda = proxima_segunda()
        resp = await client.get(
            "/crm/agenda/semana",
            params={"inicio": segunda.isoformat()},
            headers=cenario["headers"],
        )
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert len(corpo["dias"]) == 5
        assert [d["dia_semana"] for d in corpo["dias"]] == [
            "seg", "ter", "qua", "qui", "sex"
        ]
        assert corpo["slots"][0] == "08:00"
        assert corpo["slots"][-1] == "17:30"
        assert len(corpo["slots"]) == 18

    async def test_qualquer_dia_abre_a_mesma_semana(self, cenario, client):
        """A seta de navegação e um link colado precisam concordar."""
        segunda = proxima_segunda()
        h = cenario["headers"]
        a = (await client.get(
            "/crm/agenda/semana", params={"inicio": segunda.isoformat()}, headers=h
        )).json()
        b = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": (segunda + timedelta(days=3)).isoformat()},
            headers=h,
        )).json()
        assert a["inicio"] == b["inicio"] and a["fim"] == b["fim"]

    async def test_a_reuniao_cai_no_dia_certo(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        quarta = proxima_segunda() + timedelta(days=2)
        await nova_reuniao(client, h, opp, uid, inicio=as_horas(quarta, 14))
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda().isoformat(), "anfitriao_id": uid},
            headers=h,
        )).json()
        por_dia = {d["dia_semana"]: len(d["reunioes"]) for d in corpo["dias"]}
        assert por_dia == {"seg": 0, "ter": 0, "qua": 1, "qui": 0, "sex": 0}

    async def test_filtra_por_anfitriao(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        ev = await criar_usuario(db_conn, client, "EV", "ev-grade@teste.com")
        me_ev = (await client.get("/auth/me", headers=ev["headers"])).json()
        await nova_reuniao(client, h, opp, uid)
        await nova_reuniao(
            client, h, opp, me_ev["id"], inicio=as_horas(proxima_segunda(), 10)
        )
        params = {"inicio": proxima_segunda().isoformat()}
        todos = (await client.get("/crm/agenda/semana", params=params, headers=h)).json()
        so_um = (await client.get(
            "/crm/agenda/semana", params={**params, "anfitriao_id": uid}, headers=h
        )).json()
        assert todos["total"] == 2
        assert so_um["total"] == 1

    async def test_livres_desconta_o_que_esta_ocupado(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        params = {"inicio": proxima_segunda().isoformat(), "anfitriao_id": uid}
        antes = (await client.get("/crm/agenda/semana", params=params, headers=h)).json()
        assert antes["livres"] == 5 * 18
        await nova_reuniao(client, h, opp, uid)
        depois = (await client.get("/crm/agenda/semana", params=params, headers=h)).json()
        assert depois["livres"] == antes["livres"] - 1

    async def test_reuniao_longa_ocupa_varios_slots(self, cenario, client):
        """
        Contar por reunião diria "17 livres" numa manhã em que não cabe
        mais nada.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        params = {"inicio": proxima_segunda().isoformat(), "anfitriao_id": uid}
        await nova_reuniao(client, h, opp, uid, duracao_min=90)
        corpo = (await client.get("/crm/agenda/semana", params=params, headers=h)).json()
        assert corpo["livres"] == 5 * 18 - 3

    async def test_livres_nao_existe_sem_anfitriao(self, cenario, client):
        """
        Somar os slots vagos de cinco agendas produziria um número que não
        responde à pergunta de ninguém.
        """
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda().isoformat()},
            headers=cenario["headers"],
        )).json()
        assert corpo["livres"] is None

    async def test_cancelada_nao_conta_no_total_mas_conta_em_canceladas(
        self, cenario, client
    ):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        await client.post(f"/crm/agenda/reunioes/{r['id']}/cancelar", json={}, headers=h)
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda().isoformat(), "anfitriao_id": uid},
            headers=h,
        )).json()
        assert corpo["total"] == 0
        assert corpo["canceladas"] == 1
        # Continua VISÍVEL na grade: some do contador, não da tela.
        assert sum(len(d["reunioes"]) for d in corpo["dias"]) == 1

    async def test_feriado_marca_o_dia_mas_nao_bloqueia(self, cenario, client, db_conn):
        """
        O calendário de `dia_nao_util` é mantido à mão e pode estar
        desatualizado; recusar com base nele transformaria uma tabela
        esquecida em erro para o usuário.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        quarta = proxima_segunda() + timedelta(days=2)
        await db_conn.execute(
            "INSERT INTO dia_nao_util (data, motivo) VALUES ($1, $2)",
            quarta, "Feriado municipal",
        )
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": opp, "anfitriao_id": uid,
                "inicio": as_horas(quarta, 9),
            },
            headers=h,
        )
        assert resp.status_code == 201, resp.text
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda().isoformat(), "anfitriao_id": uid},
            headers=h,
        )).json()
        dia = next(d for d in corpo["dias"] if d["dia_semana"] == "qua")
        assert dia["nao_util"] is True
        assert dia["motivo"] == "Feriado municipal"
        # O feriado sai INTEIRO da conta: não oferece slot e, por isso,
        # também não desconta o que foi marcado nele. Contar a reunião do
        # feriado sem contar os slots dele diria "71 de 72 livres" numa
        # semana que só tem 4 dias de trabalho — a reunião apareceria como
        # dívida contra um dia que nem existe na conta.
        assert corpo["livres"] == 4 * 18
        # E ela continua VISÍVEL na grade, que é onde o feriado se explica.
        assert len(dia["reunioes"]) == 1

    async def test_semana_vazia_nao_quebra(self, cenario, client):
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda(52).isoformat()},
            headers=cenario["headers"],
        )).json()
        assert corpo["total"] == 0
        assert all(d["reunioes"] == [] for d in corpo["dias"])

    async def test_sem_inicio_abre_a_semana_corrente(self, cenario, client):
        corpo = (await client.get(
            "/crm/agenda/semana", headers=cenario["headers"]
        )).json()
        hoje = datetime.now(regras.FUSO_OPERACAO).date()
        assert corpo["inicio"] == regras.segunda_da_semana(hoje).isoformat()


# ── O Google desligado ───────────────────────────────────────────────

class TestGoogleDesligado:
    async def test_a_reuniao_nasce_mesmo_assim(self, cenario, client):
        """
        A regra central da integração: indisponibilidade de terceiro não
        apaga o registro do que foi combinado com o cliente.
        """
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        assert r["google_event_id"] is None
        assert r["google_erro"]

    async def test_o_erro_e_visivel_e_em_portugues(self, cenario, client):
        """
        Falha silenciosa é pior que falha visível: um convite que o cliente
        nunca recebeu é uma reunião que não vai acontecer.
        """
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        assert "Google" in r["google_erro"]

    async def test_a_grade_avisa_quantas_nao_sincronizaram(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda().isoformat(), "anfitriao_id": uid},
            headers=h,
        )).json()
        assert corpo["nao_sincronizadas"] == 1
        assert corpo["google_configurado"] is False

    async def test_botao_de_sincronizar_responde(self, cenario, client):
        """
        Sem o botão, uma queda momentânea do Google deixaria a reunião
        invisível para o cliente para sempre.
        """
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/sincronizar",
            json={}, headers=cenario["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["google_erro"]


# ── Leitura e 404 ────────────────────────────────────────────────────

class TestLeitura:
    async def test_obter_devolve_a_reuniao(self, cenario, client):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        resp = await client.get(
            f"/crm/agenda/reunioes/{r['id']}", headers=cenario["headers"]
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == r["id"]

    async def test_inexistente_e_404(self, cenario, client):
        import uuid
        resp = await client.get(
            f"/crm/agenda/reunioes/{uuid.uuid4()}", headers=cenario["headers"]
        )
        assert resp.status_code == 404

    async def test_semana_vem_antes_do_wildcard(self, cenario, client):
        """
        Guarda de rota: com `/{id}` declarado antes, "semana" seria lido
        como id e a resposta viraria 422. Mesma armadilha do /kanban.
        """
        resp = await client.get("/crm/agenda/semana", headers=cenario["headers"])
        assert resp.status_code == 200

    async def test_sem_token_e_401(self, client):
        assert (await client.get("/crm/agenda/semana")).status_code == 401

    async def test_cargo_extinto_nao_ve_a_agenda(self, db_conn, client):
        u = await criar_usuario(db_conn, client, "Gerente", "ex@teste.com")
        resp = await client.get("/crm/agenda/semana", headers=u["headers"])
        assert resp.status_code == 403


# ── Quem agendou ─────────────────────────────────────────────────────

class TestAgendadoPor:
    """
    `agendado_por` responde "de quem é o crédito" e é MÉTRICA;
    `criado_por` responde "quem digitou" e é auditoria. São a mesma pessoa
    em quase toda linha — e é no dia em que divergem, que é o dia em que
    alguém cobre o colega, que a distinção paga por si.
    """

    async def test_em_branco_cai_em_quem_esta_criando(self, cenario, client):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        assert r["agendado_por"] == cenario["usuario_id"]

    async def test_explicito_ganha_de_quem_digitou(self, cenario, client, db_conn):
        """O ADM lança em nome do SDR que marcou por telefone."""
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-credito@teste.com")
        id_sdr = (await client.get("/auth/me", headers=sdr["headers"])).json()["id"]
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
            agendado_por=id_sdr,
        )
        assert r["agendado_por"] == id_sdr
        # e `criado_por` continua guardando quem digitou
        criado_por = await db_conn.fetchval(
            "SELECT criado_por FROM reunioes WHERE id = $1", r["id"]
        )
        assert str(criado_por) == cenario["usuario_id"]

    async def test_devolve_o_nome_para_a_tela(self, cenario, client):
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        assert r["agendado_por_nome"] == "Test ADM"

    async def test_inativo_e_422(self, cenario, client, db_conn):
        outro = await criar_usuario(db_conn, client, "SDR", "sdr-off@teste.com")
        uid = (await client.get("/auth/me", headers=outro["headers"])).json()["id"]
        await db_conn.execute("UPDATE usuarios SET ativo = FALSE WHERE id = $1", uid)
        resp = await client.post(
            "/crm/agenda/reunioes",
            json={
                "oportunidade_id": cenario["oportunidade"]["id"],
                "anfitriao_id": cenario["usuario_id"],
                "inicio": as_horas(proxima_segunda(), 9),
                "agendado_por": uid,
            },
            headers=cenario["headers"],
        )
        assert resp.status_code == 422

    async def test_editavel_depois(self, cenario, client, db_conn):
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-troca@teste.com")
        id_sdr = (await client.get("/auth/me", headers=sdr["headers"])).json()["id"]
        r = await nova_reuniao(
            client, cenario["headers"],
            cenario["oportunidade"]["id"], cenario["usuario_id"],
        )
        resp = await client.patch(
            f"/crm/agenda/reunioes/{r['id']}",
            json={"agendado_por": id_sdr}, headers=cenario["headers"],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["agendado_por"] == id_sdr

    async def test_de_tarefa_tambem_aceita(self, cenario, client, db_conn):
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-tarefa@teste.com")
        id_sdr = (await client.get("/auth/me", headers=sdr["headers"])).json()["id"]
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        t = (await client.post(
            "/crm/tarefas",
            json={
                "oportunidade_id": opp, "tipo": "reuniao", "titulo": "Apresentar",
                "responsavel_id": uid, "prazo": as_horas(proxima_segunda(), 16),
            },
            headers=h,
        )).json()
        resp = await client.post(
            f"/crm/agenda/reunioes/de-tarefa/{t['id']}",
            json={"agendado_por": id_sdr}, headers=h,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["agendado_por"] == id_sdr


# ── O desfecho ───────────────────────────────────────────────────────

def proxima_de(uid, semanas=2):
    return {
        "tipo": "ligacao", "titulo": "Retomar",
        "responsavel_id": uid, "prazo": as_horas(proxima_segunda(semanas), 9),
    }


class TestDesfecho:
    async def test_realizada_conclui_a_tarefa(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "realizada", "observacao": "pediu proposta",
                  "proxima": proxima_de(uid)},
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["desfecho"] == "realizada"
        assert resp.json()["desfecho_efetivo"] == "realizada"
        assert resp.json()["situacao"] == "concluida"
        assert await db_conn.fetchval(
            "SELECT resultado FROM tarefas WHERE id = $1", r["tarefa_id"]
        ) == "pediu proposta"

    async def test_realizada_exige_a_proxima(self, cenario, client):
        """
        É a regra da Sprint 5, e é ela que faz a reunião empurrar o funil
        em vez de virar um fato isolado.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "realizada"}, headers=h,
        )
        assert resp.status_code == 422
        assert "próxima" in resp.text

    @pytest.mark.parametrize("desfecho", ["cancelada", "no_show"])
    async def test_nao_realizada_cancela_e_nao_exige_proxima(
        self, cenario, client, desfecho
    ):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": desfecho}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["desfecho"] == desfecho
        assert resp.json()["situacao"] == "cancelada"

    async def test_no_show_aceita_a_proxima(self, cenario, client, db_conn):
        """Remarcar é o desfecho natural de um no-show — só não é exigido."""
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "no_show", "proxima": proxima_de(uid)}, headers=h,
        )
        assert resp.status_code == 200, resp.text
        assert await db_conn.fetchval(
            "SELECT count(*) FROM tarefas WHERE tarefa_anterior_id = $1", r["tarefa_id"]
        ) == 1

    async def test_guarda_a_antecedencia_do_relogio(self, cenario, client, db_conn):
        """
        O que o relógio dizia, ao lado do que a pessoa escolheu. É o único
        jeito de responder depois "esse no-show foi avisado com quanto
        tempo?" sem reconstruir nada.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "cancelada"}, headers=h,
        )
        horas = resp.json()["desfecho_antecedencia_horas"]
        # A reunião foi marcada para a próxima segunda: dias de antecedência.
        assert horas is not None and horas > 24

    async def test_a_escolha_da_pessoa_nao_e_sobrescrita_pelo_relogio(
        self, cenario, client
    ):
        """
        O relógio diria "cancelada" (faltam dias). A pessoa disse no_show,
        e é isso que fica: ela sabe de algo que o relógio não sabe.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "no_show"}, headers=h,
        )
        assert resp.json()["desfecho"] == "no_show"
        assert resp.json()["desfecho_antecedencia_horas"] > 24

    async def test_nao_se_registra_duas_vezes(self, cenario, client):
        """
        Reabrir apagaria o histórico pelo mesmo motivo que tarefa fechada é
        imutável — e o número do mês passado mudaria depois de fechado.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "cancelada"}, headers=h,
        )
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "realizada", "proxima": proxima_de(uid)}, headers=h,
        )
        assert resp.status_code == 422
        assert "já foi registrada" in resp.text

    async def test_desfecho_invalido_e_422(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "faltou"}, headers=h,
        )
        assert resp.status_code == 422

    async def test_sem_observacao_o_motivo_vira_o_desfecho(self, cenario, client, db_conn):
        """
        "cancelada" sem motivo nenhum na linha do tempo parece registro
        pela metade para quem lê seis meses depois.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "no_show"}, headers=h,
        )
        assert await db_conn.fetchval(
            "SELECT motivo_cancelamento FROM tarefas WHERE id = $1", r["tarefa_id"]
        ) == "No-show"

    async def test_fechada_por_outra_tela_deduz_o_desfecho(self, cenario, client):
        """
        A aba de Tarefas e a tela de gestão não conhecem a agenda. Sem a
        dedução, uma reunião que comprovadamente aconteceu ficaria pendente
        para sempre.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        await client.post(
            f"/crm/tarefas/{r['tarefa_id']}/concluir",
            json={"resultado": "ok", "proxima": proxima_de(uid)}, headers=h,
        )
        depois = (await client.get(f"/crm/agenda/reunioes/{r['id']}", headers=h)).json()
        assert depois["desfecho"] is None          # ninguém registrou
        assert depois["desfecho_efetivo"] == "realizada"   # mas dá para deduzir
        assert depois["pendente_de_desfecho"] is False

    async def test_sugere_o_desfecho_enquanto_esta_em_aberto(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        # marcada para dias à frente: quem abrir o formulário agora está
        # desmarcando, e com essa antecedência isso é cancelamento.
        assert r["desfecho_sugerido"] == "cancelada"
        assert r["desfecho_efetivo"] is None

    async def test_reuniao_que_ja_passou_sugere_realizada(
        self, cenario, client, db_conn,
    ):
        """
        O caso mais comum do formulário: alguém fechando na sexta as
        reuniões da semana. Sugerir no-show aqui — que é o que o relógio
        cru diria, com a antecedência negativa — faria um Enter distraído
        transformar uma reunião que aconteceu em falta do cliente.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        # Empurrar o prazo para trás pelo banco: a API recusa marcar no
        # passado, e é justamente a reunião passada que interessa aqui.
        await db_conn.execute(
            "UPDATE tarefas SET prazo = NOW() - INTERVAL '3 hours' WHERE id = $1",
            UUID(r["tarefa_id"]),
        )
        depois = (await client.get(f"/crm/agenda/reunioes/{r['id']}", headers=h)).json()
        assert depois["desfecho_sugerido"] == "realizada"
        assert depois["pendente_de_desfecho"] is True

    async def test_a_sugestao_some_depois_de_registrado(self, cenario, client):
        """
        Uma sugestão ao lado de uma resposta já dada só convida a mexer no
        que está certo.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "cancelada"}, headers=h,
        )
        assert resp.json()["desfecho_sugerido"] is None

    async def test_realizada_mantem_o_evento_no_google(self, cenario, client, db_conn):
        """
        Apagar o evento de uma reunião que aconteceu limparia o histórico
        do calendário do vendedor — que é onde ele reconstrói a semana.
        Aqui o Google está desligado, então o que se prova é que a rota de
        remoção NÃO é chamada: `google_erro` continua o da criação.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        r = await nova_reuniao(client, h, opp, uid)
        resp = await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "realizada", "proxima": proxima_de(uid)}, headers=h,
        )
        assert resp.status_code == 200, resp.text


# ── A semana, com o rastreio ─────────────────────────────────────────

class TestSemanaComRastreio:
    async def test_filtra_por_quem_agendou(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-filtro@teste.com")
        id_sdr = (await client.get("/auth/me", headers=sdr["headers"])).json()["id"]
        await nova_reuniao(client, h, opp, uid, agendado_por=id_sdr)
        await nova_reuniao(
            client, h, opp, uid, inicio=as_horas(proxima_segunda(), 10)
        )
        params = {"inicio": proxima_segunda().isoformat()}
        todos = (await client.get("/crm/agenda/semana", params=params, headers=h)).json()
        do_sdr = (await client.get(
            "/crm/agenda/semana", params={**params, "agendado_por": id_sdr}, headers=h
        )).json()
        assert todos["total"] == 2
        assert do_sdr["total"] == 1

    async def test_combina_com_o_filtro_de_anfitriao(self, cenario, client, db_conn):
        """
        "As reuniões que EU marquei para o Bruno" é a pergunta do SDR
        conferindo o próprio trabalho, e ela precisa dos dois filtros.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        ev = await criar_usuario(db_conn, client, "EV", "ev-combo@teste.com")
        id_ev = (await client.get("/auth/me", headers=ev["headers"])).json()["id"]
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-combo@teste.com")
        id_sdr = (await client.get("/auth/me", headers=sdr["headers"])).json()["id"]

        await nova_reuniao(client, h, opp, id_ev, agendado_por=id_sdr)
        await nova_reuniao(
            client, h, opp, uid, agendado_por=id_sdr,
            inicio=as_horas(proxima_segunda(), 10),
        )
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda().isoformat(),
                    "anfitriao_id": id_ev, "agendado_por": id_sdr},
            headers=h,
        )).json()
        assert corpo["total"] == 1

    async def test_conta_as_pendentes(self, cenario, client, db_conn):
        """
        Sem um número visível cobrando, a reunião esquecida sairia de toda
        estatística em silêncio — é o preço da decisão de NÃO adivinhar.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        passada = proxima_segunda(-2)
        r = await nova_reuniao(client, h, opp, uid, inicio=as_horas(passada, 9))
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": passada.isoformat(), "anfitriao_id": uid},
            headers=h,
        )).json()
        assert corpo["pendentes"] == 1

    async def test_registrada_sai_das_pendentes(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        passada = proxima_segunda(-2)
        r = await nova_reuniao(client, h, opp, uid, inicio=as_horas(passada, 9))
        await client.post(
            f"/crm/agenda/reunioes/{r['id']}/desfecho",
            json={"desfecho": "no_show"}, headers=h,
        )
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": passada.isoformat(), "anfitriao_id": uid},
            headers=h,
        )).json()
        assert corpo["pendentes"] == 0

    async def test_futura_nao_e_pendente(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda().isoformat(), "anfitriao_id": uid},
            headers=h,
        )).json()
        assert corpo["pendentes"] == 0

    async def test_a_grade_e_a_mesma_para_todo_mundo(self, cenario, client, db_conn):
        """
        Nada aqui é filtrado por quem está olhando: um slot marcado aparece
        ocupado para a equipe inteira. É o que faz o SDR confiar no buraco
        que ele vê antes de oferecer o horário ao cliente.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        outro = await criar_usuario(db_conn, client, "SDR", "sdr-ve-tudo@teste.com")
        corpo = (await client.get(
            "/crm/agenda/semana",
            params={"inicio": proxima_segunda().isoformat()},
            headers=outro["headers"],
        )).json()
        assert corpo["total"] == 1
        assert sum(len(d["reunioes"]) for d in corpo["dias"]) == 1


# ── O relatório ──────────────────────────────────────────────────────

class TestProdutividade:
    def _params(self, semanas=1):
        """
        A semana das reuniões, não a corrente: `nova_reuniao` marca para
        `proxima_segunda()`, que é `semanas=1`. Com o default em 0 a janela
        cobria a semana que já passou e o relatório vinha vazio — parecia
        bug do endpoint e era da janela do teste.
        """
        seg = proxima_segunda(semanas)
        return {"de": seg.isoformat(), "ate": (seg + timedelta(days=4)).isoformat()}

    async def test_conta_agendamentos_por_sdr(self, cenario, client, db_conn):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr-prod@teste.com")
        id_sdr = (await client.get("/auth/me", headers=sdr["headers"])).json()["id"]
        await nova_reuniao(client, h, opp, uid, agendado_por=id_sdr)
        await nova_reuniao(
            client, h, opp, uid, agendado_por=id_sdr,
            inicio=as_horas(proxima_segunda(), 10),
        )
        # A janela do SDR é a de CRIAÇÃO: as duas foram criadas hoje.
        hoje = datetime.now(regras.FUSO_OPERACAO).date()
        corpo = (await client.get(
            "/crm/agenda/produtividade",
            params={"de": hoje.isoformat(), "ate": hoje.isoformat()},
            headers=h,
        )).json()
        linha = next(p for p in corpo["por_sdr"] if p["usuario_id"] == id_sdr)
        assert linha["total"] == 2
        assert corpo["agendamentos"] == 2

    async def test_os_dois_eixos_de_data_sao_diferentes(self, cenario, client):
        """
        A reunião é CRIADA hoje e ACONTECE na semana que vem. Ela conta no
        dia de hoje para o SDR e no dia dela para o EV — um único eixo
        teria que escolher um dos dois e mentir no outro.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        hoje = datetime.now(regras.FUSO_OPERACAO).date()

        so_hoje = (await client.get(
            "/crm/agenda/produtividade",
            params={"de": hoje.isoformat(), "ate": hoje.isoformat()},
            headers=h,
        )).json()
        assert so_hoje["agendamentos"] == 1     # o SDR trabalhou hoje
        assert so_hoje["por_ev"] == []          # mas nenhuma reunião é hoje

        na_semana = (await client.get(
            "/crm/agenda/produtividade", params=self._params(), headers=h,
        )).json()
        assert na_semana["agendamentos"] == 0   # ninguém marcou nada naquela semana
        assert na_semana["por_ev"][0]["total"] == 1

    async def test_classifica_os_desfechos_por_ev(self, cenario, client):
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        a = await nova_reuniao(client, h, opp, uid, inicio=as_horas(proxima_segunda(), 9))
        b = await nova_reuniao(client, h, opp, uid, inicio=as_horas(proxima_segunda(), 10))
        c = await nova_reuniao(client, h, opp, uid, inicio=as_horas(proxima_segunda(), 11))
        await client.post(f"/crm/agenda/reunioes/{a['id']}/desfecho",
                          json={"desfecho": "realizada", "proxima": proxima_de(uid, 4)},
                          headers=h)
        await client.post(f"/crm/agenda/reunioes/{b['id']}/desfecho",
                          json={"desfecho": "cancelada"}, headers=h)
        await client.post(f"/crm/agenda/reunioes/{c['id']}/desfecho",
                          json={"desfecho": "no_show"}, headers=h)

        corpo = (await client.get(
            "/crm/agenda/produtividade", params=self._params(), headers=h,
        )).json()
        assert corpo["realizadas"] == 1
        assert corpo["canceladas"] == 1
        assert corpo["no_show"] == 1
        linha = corpo["por_ev"][0]
        assert (linha["realizadas"], linha["canceladas"], linha["no_show"]) == (1, 1, 1)

    async def test_as_taxas_excluem_o_que_ainda_nao_tem_resultado(self, cenario, client):
        """
        Pendente não é fracasso: contá-lo no denominador puniria quem
        marcou ontem. Mesma regra das taxas de parceiro.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        a = await nova_reuniao(client, h, opp, uid, inicio=as_horas(proxima_segunda(), 9))
        await nova_reuniao(client, h, opp, uid, inicio=as_horas(proxima_segunda(), 10))
        await client.post(f"/crm/agenda/reunioes/{a['id']}/desfecho",
                          json={"desfecho": "no_show"}, headers=h)
        corpo = (await client.get(
            "/crm/agenda/produtividade", params=self._params(), headers=h,
        )).json()
        # uma fechada (no-show) e uma em aberto: a taxa olha só a fechada
        assert corpo["taxa_no_show"] == 1.0
        assert corpo["taxa_realizacao"] == 0.0

    async def test_taxa_e_none_sem_denominador(self, cenario, client):
        """
        0% e "ainda não deu para saber" são coisas diferentes, e a tela
        mostra `—` na segunda.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        corpo = (await client.get(
            "/crm/agenda/produtividade", params=self._params(), headers=h,
        )).json()
        assert corpo["taxa_no_show"] is None
        assert corpo["taxa_realizacao"] is None

    async def test_devolve_os_dias_da_janela(self, cenario, client):
        corpo = (await client.get(
            "/crm/agenda/produtividade", params=self._params(),
            headers=cenario["headers"],
        )).json()
        assert len(corpo["dias"]) == 5

    async def test_por_dia_tem_uma_entrada_por_dia_da_janela(self, cenario, client):
        """
        Inclusive os zerados: omitir o dia vazio faria a tabela trocar de
        largura a cada semana, e o zero é informação.
        """
        h, opp, uid = cenario["headers"], cenario["oportunidade"]["id"], cenario["usuario_id"]
        await nova_reuniao(client, h, opp, uid)
        corpo = (await client.get(
            "/crm/agenda/produtividade", params=self._params(), headers=h,
        )).json()
        assert len(corpo["por_ev"][0]["por_dia"]) == 5

    async def test_janela_invertida_e_422(self, cenario, client):
        seg = proxima_segunda()
        resp = await client.get(
            "/crm/agenda/produtividade",
            params={"de": (seg + timedelta(days=4)).isoformat(), "ate": seg.isoformat()},
            headers=cenario["headers"],
        )
        assert resp.status_code == 422

    async def test_rota_nao_e_lida_como_id(self, cenario, client):
        """Mesma armadilha do /semana: com o wildcard na frente, viraria 422."""
        hoje = datetime.now(regras.FUSO_OPERACAO).date()
        resp = await client.get(
            "/crm/agenda/produtividade",
            params={"de": hoje.isoformat(), "ate": hoje.isoformat()},
            headers=cenario["headers"],
        )
        assert resp.status_code == 200
