"""
HIPO — Transcrição de reunião: endpoints, coleta e timer, com banco.

As regras (esperar/coletar/desistir) estão em test_transcricao_regras.py.
Aqui o foco é a costura:

  * o estado que a tela recebe em cada fase (sem Meet, antes do fim,
    aguardando, pronta, indisponível)
  * o erro do Google virando COLUNA, com a reunião seguindo aguardando
  * o texto e o resumo gravados na linha, e o resumo descartado com motivo
  * a lista do timer: quem entra, quem sai
  * ligar a transcrição automática na sala, uma vez só

O GOOGLE E A IA NÃO SÃO CHAMADOS. `google_meet.levantar/baixar/ligar` e
`resumo_reuniao.resumir` são substituídos por funções de teste — o mesmo
motivo de test_crm_agenda: suíte que precisa de credencial não roda no CI.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from services import coleta_transcricao as coleta
from services import google_meet, resumo_reuniao
from services.google_meet import Download, Levantamento, ResultadoMeet
from services.resumo_reuniao import Resumo
from services.transcricao import Conferencia, Fala, Transcricao
from tests.test_crm_agenda import nova_reuniao

LINK = "https://meet.google.com/abc-defg-hij"
UTC = timezone.utc


def agora():
    return datetime.now(UTC)


# ── Cenário ──────────────────────────────────────────────────────────


@pytest.fixture
async def base(db_conn, client, usuario_adm):
    h = usuario_adm["headers"]
    conta = (await client.post(
        "/crm/contas",
        json={"razao_social": "Metalurgica Alfa LTDA", "cnpj": "11.222.333/0001-81"},
        headers=h,
    )).json()
    opp = (await client.post(
        "/crm/oportunidades", json={"conta_id": conta["id"]}, headers=h,
    )).json()
    me = (await client.get("/auth/me", headers=h)).json()
    return {"h": h, "opp": opp, "uid": me["id"], "conn": db_conn}


async def reuniao_com_meet(base, client, client_fim_ha=timedelta(hours=1), link=LINK,
                           duracao=30):
    """
    Uma reunião que JÁ ACONTECEU, com sala do Meet.

    Nasce no futuro pela API (a agenda não aceita marcar no passado) e é
    empurrada para trás por SQL — é o único jeito de ter, no teste, uma
    reunião que terminou há uma hora.
    """
    r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"],
                           duracao_min=duracao)
    inicio = agora() - client_fim_ha - timedelta(minutes=duracao)
    await base["conn"].execute("UPDATE tarefas SET prazo = $2 WHERE id = $1",
                               UUID(r["tarefa_id"]), inicio)
    await base["conn"].execute(
        "UPDATE reunioes SET google_link = $2, google_calendar_id = $3 WHERE id = $1",
        UUID(r["id"]), link, "adm@teste.com",
    )
    r["inicio_real"] = inicio
    r["fim_real"] = inicio + timedelta(minutes=duracao)
    return r


def ligar_google(monkeypatch, levantamento=None, download=None, resumo=None, ia=True):
    """Liga o Google e a IA de mentira, e grava quem foi chamado."""
    chamadas = {"levantar": 0, "baixar": 0, "resumir": 0, "ligar": 0}

    async def levantar(email, codigo):
        chamadas["levantar"] += 1
        chamadas["codigo"] = codigo
        chamadas["email"] = email
        return levantamento() if callable(levantamento) else (levantamento or Levantamento())

    async def baixar(email, conferencias):
        chamadas["baixar"] += 1
        return download or Download()

    async def resumir(texto, ctx):
        chamadas["resumir"] += 1
        chamadas["ctx"] = ctx
        return resumo or Resumo(resumo="Cliente quer PCMSO.",
                                proximos_passos=("Enviar proposta",), modelo="m")

    monkeypatch.setattr(google_meet, "configurado", lambda: True)
    monkeypatch.setattr(google_meet, "levantar", levantar)
    monkeypatch.setattr(google_meet, "baixar", baixar)
    monkeypatch.setattr(resumo_reuniao, "configurado", lambda: ia)
    monkeypatch.setattr(resumo_reuniao, "resumir", resumir)
    return chamadas


def pronta_no_google(r):
    """Uma conferência acabada, com o arquivo da transcrição gerado."""
    return Levantamento(conferencias=(Conferencia(
        nome="conferenceRecords/c1",
        inicio=r["inicio_real"] + timedelta(minutes=1),
        fim=r["fim_real"],
        transcricoes=(Transcricao("conferenceRecords/c1/transcripts/t1",
                                  "FILE_GENERATED", "https://docs.google.com/d/x"),),
    ),))


def falas(r):
    ini = r["inicio_real"]
    return Download(
        falas=(
            Fala(ini + timedelta(minutes=1), None, "Test ADM", "Bom dia, tudo bem?"),
            Fala(ini + timedelta(minutes=2), None, "Cliente", "Tudo. Temos 120 vidas."),
            Fala(ini + timedelta(minutes=3), None, "Cliente", "Mande a proposta."),
        ),
        idioma="pt-BR",
        documento_url="https://docs.google.com/d/x",
        conferencias=("conferenceRecords/c1",),
    )


def url(r, sufixo=""):
    return f"/crm/agenda/tarefas/{r['tarefa_id']}/transcricao{sufixo}"


# ── Estado inicial ───────────────────────────────────────────────────


class TestEstado:
    async def test_sem_meet(self, base, client):
        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"])
        resp = await client.get(url(r), headers=base["h"])
        assert resp.status_code == 200
        d = resp.json()
        assert d["status"] == "sem_meet"
        assert d["tem_meet"] is False
        assert d["pode_buscar"] is False

    async def test_link_do_meet_colado_a_mao_serve(self, base, client):
        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"],
                               link_video="https://meet.google.com/xyz-abcd-efg")
        d = (await client.get(url(r), headers=base["h"])).json()
        assert d["tem_meet"] is True
        assert d["status"] == "nao_iniciada"

    async def test_antes_do_fim_nao_busca(self, base, client):
        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"])
        await base["conn"].execute("UPDATE reunioes SET google_link = $2 WHERE id = $1",
                                   UUID(r["id"]), LINK)
        d = (await client.get(url(r), headers=base["h"])).json()
        assert d["status"] == "nao_iniciada"
        assert "depois que a reunião termina" in d["motivo"]
        assert d["pode_buscar"] is False
        resp = await client.post(url(r, "/buscar"), headers=base["h"])
        assert resp.status_code == 422

    async def test_depois_do_fim_pode_buscar(self, base, client):
        r = await reuniao_com_meet(base, client)
        d = (await client.get(url(r), headers=base["h"])).json()
        assert d["status"] == "nao_iniciada"
        assert d["pode_buscar"] is True
        assert "fila" in d["motivo"]

    async def test_tarefa_sem_reuniao_e_404(self, base, client):
        tarefa = (await client.post(
            "/crm/tarefas",
            json={"oportunidade_id": base["opp"]["id"], "tipo": "ligacao",
                  "titulo": "Ligar", "responsavel_id": base["uid"],
                  "prazo": (agora() + timedelta(days=1)).isoformat()},
            headers=base["h"],
        ))
        assert tarefa.status_code == 201, tarefa.text
        resp = await client.get(
            f"/crm/agenda/tarefas/{tarefa.json()['id']}/transcricao", headers=base["h"],
        )
        assert resp.status_code == 404

    async def test_exige_login(self, base, client):
        r = await reuniao_com_meet(base, client)
        assert (await client.get(url(r))).status_code == 401

    async def test_reuniao_expoe_o_status_na_grade(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ligar_google(monkeypatch, levantamento=pronta_no_google(r), download=falas(r))
        await client.post(url(r, "/buscar"), headers=base["h"])
        det = (await client.get(f"/crm/agenda/reunioes/{r['id']}", headers=base["h"])).json()
        assert det["transcricao_status"] == "pronta"


# ── A coleta ─────────────────────────────────────────────────────────


class TestColeta:
    async def test_pronta_grava_texto_e_resumo(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ch = ligar_google(monkeypatch, levantamento=pronta_no_google(r), download=falas(r))

        resp = await client.post(url(r, "/buscar"), headers=base["h"])
        assert resp.status_code == 200, resp.text
        d = resp.json()
        assert d["status"] == "pronta"
        assert d["falas"] == 2  # as duas do cliente viram uma
        assert "Test ADM: Bom dia, tudo bem?" in d["texto"]
        assert "Cliente: Tudo. Temos 120 vidas. Mande a proposta." in d["texto"]
        assert d["documento_url"] == "https://docs.google.com/d/x"
        assert d["idioma"] == "pt-BR"
        assert d["resumo"] == "Cliente quer PCMSO."
        assert d["proximos_passos"] == ["Enviar proposta"]
        assert d["pode_buscar"] is False
        assert d["pode_resumir"] is True
        # Código e calendário certos: o dono da sala é quem tem o evento.
        assert ch["codigo"] == "abc-defg-hij"
        assert ch["email"] == "adm@teste.com"
        assert ch["ctx"]["empresa"] == "Metalurgica Alfa LTDA"

        # GET devolve o mesmo, e buscar de novo não vai ao Google.
        again = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert again["status"] == "pronta"
        assert ch["levantar"] == 1

    async def test_sem_chave_da_ia_chega_sem_resumo(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ch = ligar_google(monkeypatch, levantamento=pronta_no_google(r),
                          download=falas(r), ia=False)
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["status"] == "pronta"
        assert d["resumo"] is None and d["resumo_erro"] is None
        assert ch["resumir"] == 0
        # E pedir resumo sem chave é 422, dizendo o que falta.
        resp = await client.post(url(r, "/resumo"), headers=base["h"])
        assert resp.status_code == 422
        assert "ANTHROPIC_API_KEY" in resp.json()["detail"]

    async def test_erro_do_google_vira_coluna_e_continua_aguardando(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ligar_google(monkeypatch, levantamento=Levantamento(erro="Falta o escopo X."))
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["status"] == "aguardando"
        assert d["erro"] == "Falta o escopo X."
        assert d["tentativas"] == 1
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["tentativas"] == 2

    async def test_erro_some_quando_o_google_volta(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        estado = {"erro": True}

        def lev():
            return Levantamento(erro="caiu") if estado["erro"] else Levantamento()

        ligar_google(monkeypatch, levantamento=lev)
        await client.post(url(r, "/buscar"), headers=base["h"])
        estado["erro"] = False
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["status"] == "aguardando"
        assert d["erro"] is None
        assert "Ninguém entrou" in d["motivo"]

    async def test_ninguem_entrou_em_24h_fica_indisponivel(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client, client_fim_ha=timedelta(hours=25))
        ligar_google(monkeypatch)
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["status"] == "indisponivel"
        assert "Ninguém entrou" in d["motivo"]
        assert d["rotulo"] == "Sem transcrição"

    async def test_download_com_erro_nao_perde_nada(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ligar_google(monkeypatch, levantamento=pronta_no_google(r),
                     download=Download(erro="rede"))
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["status"] == "aguardando"
        assert d["erro"] == "rede"
        assert d["texto"] is None

    async def test_transcricao_vazia_e_indisponivel(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ligar_google(monkeypatch, levantamento=pronta_no_google(r),
                     download=Download(falas=(), conferencias=("c1",)))
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["status"] == "indisponivel"
        assert "sem nenhuma fala" in d["motivo"]

    async def test_cancelada_nao_busca(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        await base["conn"].execute("UPDATE tarefas SET cancelada_em = NOW() WHERE id = $1",
                                   UUID(r["tarefa_id"]))
        ligar_google(monkeypatch)
        resp = await client.post(url(r, "/buscar"), headers=base["h"])
        assert resp.status_code == 422

    async def test_passou_30_dias(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client, client_fim_ha=timedelta(days=31))
        ligar_google(monkeypatch)
        d = (await client.get(url(r), headers=base["h"])).json()
        assert d["pode_buscar"] is False
        # O coletor (manual) grava o porquê, sem ir ao Google.
        d = await coleta.coletar(base["conn"], UUID(r["id"]), manual=True)
        assert d["status"] == "indisponivel"
        assert "30 dias" in d["motivo"]

    async def test_manual_reavalia_indisponivel(self, base, client, monkeypatch):
        """Quem acabou de corrigir a delegação não pode ficar sem o texto."""
        r = await reuniao_com_meet(base, client, client_fim_ha=timedelta(hours=25))
        ligar_google(monkeypatch)
        await client.post(url(r, "/buscar"), headers=base["h"])
        ligar_google(monkeypatch, levantamento=pronta_no_google(r), download=falas(r))
        # O timer NÃO reavalia...
        d = await coleta.coletar(base["conn"], UUID(r["id"]))
        assert d["status"] == "indisponivel"
        # ...o botão sim.
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["status"] == "pronta"


# ── O resumo ─────────────────────────────────────────────────────────


class TestResumo:
    async def test_resumo_descartado_guarda_o_motivo_e_regera(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ch = ligar_google(monkeypatch, levantamento=pronta_no_google(r), download=falas(r),
                          resumo=Resumo(erro="Resumo descartado: citou número (45)."))
        d = (await client.post(url(r, "/buscar"), headers=base["h"])).json()
        assert d["status"] == "pronta"
        assert d["resumo"] is None
        assert "descartado" in d["resumo_erro"]

        ligar_google(monkeypatch)  # IA de volta ao normal
        d = (await client.post(url(r, "/resumo"), headers=base["h"])).json()
        assert d["resumo"] == "Cliente quer PCMSO."
        assert d["resumo_erro"] is None
        assert d["resumo_modelo"] == "m"
        assert ch["resumir"] == 1

    async def test_resumo_antes_de_pronta_e_422(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ligar_google(monkeypatch)
        resp = await client.post(url(r, "/resumo"), headers=base["h"])
        assert resp.status_code == 422


# ── O timer ──────────────────────────────────────────────────────────


class TestPendentes:
    async def test_quem_entra_e_quem_sai(self, base, client, monkeypatch):
        acabou = await reuniao_com_meet(base, client)
        futura = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"],
                                    inicio=(agora() + timedelta(days=7)).isoformat())
        await base["conn"].execute("UPDATE reunioes SET google_link=$2 WHERE id=$1",
                                   UUID(futura["id"]), LINK)
        velha = await reuniao_com_meet(base, client, client_fim_ha=timedelta(days=4))
        sem_meet = await reuniao_com_meet(base, client, link="https://zoom.us/j/1")
        cancelada = await reuniao_com_meet(base, client)
        await base["conn"].execute("UPDATE tarefas SET cancelada_em = NOW() WHERE id = $1",
                                   UUID(cancelada["tarefa_id"]))
        no_show = await reuniao_com_meet(base, client)
        await base["conn"].execute(
            "UPDATE reunioes SET desfecho='no_show', desfecho_em=NOW() WHERE id=$1",
            UUID(no_show["id"]))

        ids = {str(i) for i in await coleta.pendentes(base["conn"])}
        assert str(acabou["id"]) in ids
        for fora in (futura, velha, sem_meet, cancelada, no_show):
            assert str(fora["id"]) not in ids

        # Pronta sai da lista; aguardando continua.
        ligar_google(monkeypatch, levantamento=pronta_no_google(acabou), download=falas(acabou))
        await coleta.coletar(base["conn"], UUID(acabou["id"]))
        assert str(acabou["id"]) not in {str(i) for i in await coleta.pendentes(base["conn"])}

    async def test_aguardando_continua_na_lista(self, base, client, monkeypatch):
        r = await reuniao_com_meet(base, client)
        ligar_google(monkeypatch)
        await coleta.coletar(base["conn"], UUID(r["id"]))
        assert UUID(r["id"]) in await coleta.pendentes(base["conn"])

    async def test_sem_resumo_so_quem_nunca_tentou(self, base, client, monkeypatch):
        a = await reuniao_com_meet(base, client)
        b = await reuniao_com_meet(base, client)
        ligar_google(monkeypatch, levantamento=pronta_no_google(a), download=falas(a), ia=False)
        await coleta.coletar(base["conn"], UUID(a["id"]))
        ligar_google(monkeypatch, levantamento=pronta_no_google(b), download=falas(b),
                     resumo=Resumo(erro="descartado"))
        await coleta.coletar(base["conn"], UUID(b["id"]))
        assert await coleta.sem_resumo(base["conn"]) == [UUID(a["id"])]

    async def test_script_uma_passada(self, base, client, monkeypatch):
        from scripts import coletar_transcricoes as script
        r = await reuniao_com_meet(base, client)
        ligar_google(monkeypatch, levantamento=pronta_no_google(r), download=falas(r))
        assert await script.executar() == 0
        d = (await client.get(url(r), headers=base["h"])).json()
        assert d["status"] == "pronta"
        assert d["resumo"] == "Cliente quer PCMSO."

    async def test_script_com_google_desligado_sai_limpo(self, base, client):
        from scripts import coletar_transcricoes as script
        await reuniao_com_meet(base, client)
        assert await script.executar() == 0


# ── Ligar a transcrição automática ───────────────────────────────────


class TestLigarNaSala:
    async def test_liga_uma_vez_so(self, base, client, monkeypatch):
        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"])
        chamadas = []

        async def ligar(email, codigo):
            chamadas.append((email, codigo))
            return ResultadoMeet(True)

        monkeypatch.setattr(google_meet, "configurado", lambda: True)
        monkeypatch.setattr(google_meet, "ligar_transcricao", ligar)
        for _ in range(2):
            await coleta.ligar_na_sala(base["conn"], UUID(r["id"]), "adm@teste.com", LINK)
        assert chamadas == [("adm@teste.com", "abc-defg-hij")]
        em = await base["conn"].fetchval(
            "SELECT transcricao_auto_em FROM reunioes WHERE id = $1", UUID(r["id"]))
        assert em is not None

    async def test_falha_vira_coluna_e_aparece_na_reuniao(self, base, client, monkeypatch):
        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"])

        async def ligar(email, codigo):
            return ResultadoMeet(False, "Falta o escopo meetings.space.settings.")

        monkeypatch.setattr(google_meet, "configurado", lambda: True)
        monkeypatch.setattr(google_meet, "ligar_transcricao", ligar)
        await coleta.ligar_na_sala(base["conn"], UUID(r["id"]), "adm@teste.com", LINK)
        det = (await client.get(f"/crm/agenda/reunioes/{r['id']}", headers=base["h"])).json()
        assert "meetings.space.settings" in det["transcricao_auto_erro"]

    async def test_sem_meet_ou_desligado_nao_faz_nada(self, base, client, monkeypatch):
        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"])

        async def ligar(email, codigo):  # pragma: no cover - não pode ser chamada
            raise AssertionError("não devia ligar")

        monkeypatch.setattr(google_meet, "ligar_transcricao", ligar)
        await coleta.ligar_na_sala(base["conn"], UUID(r["id"]), "a@b", LINK)  # desligado
        monkeypatch.setattr(google_meet, "configurado", lambda: True)
        await coleta.ligar_na_sala(base["conn"], UUID(r["id"]), "a@b", "https://zoom.us/j/1")

    async def test_marcar_reuniao_com_meet_liga_a_transcricao(self, base, client, monkeypatch):
        """A costura com a agenda: evento criado com Meet -> sala com transcrição."""
        from services import google_agenda

        async def criar_evento(dados):
            assert dados.criar_meet is True
            return google_agenda.ResultadoSync(
                ok=True, event_id="ev1", calendar_id="adm@teste.com", link=LINK,
            )

        ligadas = []

        async def ligar(email, codigo):
            ligadas.append((email, codigo))
            return ResultadoMeet(True)

        monkeypatch.setattr(google_agenda, "criar_evento", criar_evento)
        monkeypatch.setattr(google_meet, "configurado", lambda: True)
        monkeypatch.setattr(google_meet, "ligar_transcricao", ligar)

        r = await nova_reuniao(client, base["h"], base["opp"]["id"], base["uid"])
        assert r["google_link"] == LINK
        assert r["transcricao_auto_erro"] is None
        assert ligadas == [("adm@teste.com", "abc-defg-hij")]
