"""
HIPO — Ligações gravadas (056): endpoints, casamento e coletor, com banco.

As regras puras estão em test_ligacao_regras.py. Aqui o foco é a costura:

  * o clique gravado com o alvo certo (e o alvo herdado da tarefa)
  * o token do gravador: gera, autentica, revoga, usuário inativo
  * a gravação casando com o clique da mesma pessoa — e NÃO com o de outra
  * gravação sem clique entrando sem vínculo, visível só ao dono e à gestão
  * o reenvio do agente caindo na mesma linha
  * a passada: transcrição pronta, sem fala, falha da AWS virando coluna,
    clique expirado, upload que nunca chegou, retenção do áudio
  * vincular, descartar, ouvir

A AWS E A IA NÃO SÃO CHAMADAS: `services.ligacao_aws` e
`resumo_reuniao.resumir` são substituídos por dublês.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from services import coleta_ligacao as coleta
from services import ligacao_aws as aws
from services import resumo_reuniao
from services.resumo_reuniao import Resumo
from tests.conftest import contato_do_alvo, criar_usuario
from tests.test_ligacao_regras import json_transcribe

UTC = timezone.utc


def agora():
    return datetime.now(UTC)


class AwsFalsa:
    """S3 + Transcribe de mentira, guardando o que foi pedido."""

    def __init__(self):
        self.objetos: dict[str, int] = {}
        self.jobs: dict[str, dict] = {}
        self.removidos: list[str] = []
        self.jobs_apagados: list[str] = []
        self.falha_inicio: Exception | None = None
        self.resultado = json_transcribe()

    # S3
    def url_upload(self, chave, tipo):
        return f"https://s3.falso/{chave}?put&tipo={tipo}"

    def tamanho_no_s3(self, chave):
        return self.objetos.get(chave)

    def url_leitura(self, chave):
        return f"https://s3.falso/{chave}?get"

    def remover(self, chave):
        self.removidos.append(chave)
        self.objetos.pop(chave, None)

    # Transcribe
    def iniciar_transcricao(self, nome, chave, formato="flac"):
        if self.falha_inicio:
            raise self.falha_inicio
        self.jobs[nome] = {"estado": "IN_PROGRESS", "chave": chave}

    def estado_transcricao(self, nome):
        j = self.jobs.get(nome)
        if j is None:
            return "NOT_FOUND", None, "sumiu"
        url = f"https://transcribe.falso/{nome}.json" if j["estado"] == "COMPLETED" else None
        return j["estado"], url, j.get("motivo")

    def baixar_transcricao(self, url):
        return self.resultado

    def apagar_job(self, nome):
        self.jobs_apagados.append(nome)

    def terminar(self, estado="COMPLETED", motivo=None):
        for j in self.jobs.values():
            j["estado"] = estado
            j["motivo"] = motivo


@pytest.fixture
def aws_falsa(monkeypatch):
    f = AwsFalsa()
    monkeypatch.setattr(aws, "problemas", lambda: [])
    for nome in ("url_upload", "tamanho_no_s3", "url_leitura", "remover", "iniciar_transcricao",
                 "estado_transcricao", "baixar_transcricao", "apagar_job"):
        monkeypatch.setattr(aws, nome, getattr(f, nome))

    chamadas = {"resumir": 0}

    async def resumir(texto, ctx, **kw):
        chamadas["resumir"] += 1
        chamadas["ctx"] = ctx
        chamadas["kw"] = kw
        return Resumo(resumo="Carla pediu retorno.", proximos_passos=("Ligar na quinta",), modelo="m")

    monkeypatch.setattr(resumo_reuniao, "configurado", lambda: True)
    monkeypatch.setattr(resumo_reuniao, "resumir", resumir)
    f.chamadas = chamadas
    return f


@pytest.fixture
async def base(db_conn, client):
    sdr = await criar_usuario(db_conn, client, "SDR", "sdr@teste.com")
    ev = await criar_usuario(db_conn, client, "EV", "ev@teste.com")
    adm = await criar_usuario(db_conn, client, "ADM", "adm@teste.com")
    h = sdr["headers"]
    conta = (await client.post(
        "/crm/contas",
        json={"razao_social": "Metalurgica Alfa LTDA", "cnpj": "11.222.333/0001-81"},
        headers=h,
    )).json()
    opp = (await client.post("/crm/oportunidades", json={"conta_id": conta["id"]}, headers=h)).json()
    contato_id = await contato_do_alvo(client, h, oportunidade_id=opp["id"], nome="Carla Souza")
    me = (await client.get("/auth/me", headers=h)).json()
    return {"sdr": sdr, "ev": ev, "adm": adm, "h": h, "conta": conta, "opp": opp,
            "contato_id": contato_id, "uid": me["id"], "conn": db_conn}


async def novo_gravador(client, headers, nome="Notebook"):
    r = await client.post("/crm/ligacoes/gravadores", json={"nome": nome}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["token"], {"Authorization": f"Bearer {r.json()['token']}"}


def gravacao(inicio, dur=95, id_local="grav-0001-abcd", agora_agente=None):
    return {
        "inicio": inicio.isoformat(),
        "fim": (inicio + timedelta(seconds=dur)).isoformat(),
        "agora": (agora_agente or agora()).isoformat(),
        "duracao_s": dur,
        "tamanho_bytes": 900_000,
        "formato": "flac",
        "id_local": id_local,
    }


async def clicar(client, base, **extra):
    corpo = {"telefone": "(11) 9 9571-3682", "oportunidade_id": base["opp"]["id"],
             "contato_id": base["contato_id"], **extra}
    r = await client.post("/crm/ligacoes", json=corpo, headers=base["h"])
    assert r.status_code == 201, r.text
    return r.json()


async def gravar_e_subir(client, aws_falsa, gh, inicio, **kw):
    """O caminho do agente: pede URL, 'sobe' e conclui."""
    r = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(inicio, **kw), headers=gh)
    assert r.status_code == 200, r.text
    corpo = r.json()
    chave = corpo["upload_url"].split("s3.falso/")[1].split("?")[0]
    aws_falsa.objetos[chave] = 900_000
    c = await client.post(f"/ligacoes/gravador/gravacoes/{corpo['ligacao_id']}/concluir", headers=gh)
    assert c.status_code == 200, c.text
    return corpo, c.json()


# ── Clique ───────────────────────────────────────────────────────────


async def test_clique_grava_a_ligacao_discando(client, base):
    lig = await clicar(client, base)
    assert lig["status"] == "discando"
    assert lig["telefone"] == "11995713682"
    assert lig["oportunidade_id"] == base["opp"]["id"]
    assert lig["contato_nome"] == "Carla Souza"
    assert lig["empresa"] == "Metalurgica Alfa LTDA"


async def test_duplo_clique_e_a_mesma_ligacao(client, base):
    a = await clicar(client, base)
    b = await clicar(client, base)
    assert a["id"] == b["id"]
    n = await base["conn"].fetchval("SELECT COUNT(*) FROM ligacoes")
    assert n == 1


async def test_clique_herda_alvo_e_contato_da_tarefa(client, base):
    t = await client.post("/crm/tarefas", json={
        "oportunidade_id": base["opp"]["id"], "tipo": "ligacao", "titulo": "FUP",
        "prazo": (agora() + timedelta(days=1)).isoformat(),
        "responsavel_id": base["uid"], "contato_id": base["contato_id"],
    }, headers=base["h"])
    assert t.status_code == 201, t.text
    r = await client.post("/crm/ligacoes", json={"telefone": "1122223333",
                                                 "tarefa_id": t.json()["id"]}, headers=base["h"])
    assert r.status_code == 201, r.text
    assert r.json()["oportunidade_id"] == base["opp"]["id"]
    assert r.json()["contato_id"] == base["contato_id"]
    assert r.json()["tarefa_id"] == t.json()["id"]


@pytest.mark.parametrize("corpo,trecho", [
    ({"telefone": "sem numero"}, "Telefone"),
    ({"telefone": "1122223333", "oportunidade_id": "00000000-0000-0000-0000-000000000000"}, "Oportunidade"),
])
async def test_clique_recusa(client, base, corpo, trecho):
    r = await client.post("/crm/ligacoes", json=corpo, headers=base["h"])
    assert r.status_code == 422
    assert trecho in r.text


# ── Gravador ─────────────────────────────────────────────────────────


async def test_token_do_gravador_autentica_o_pulso(client, base, aws_falsa):
    token, gh = await novo_gravador(client, base["h"])
    r = await client.post("/ligacoes/gravador/pulso", json={"versao": "1.0.0", "maquina": "PC-SDR"},
                          headers=gh)
    assert r.status_code == 200, r.text
    assert r.json()["usuario"] == "Test SDR"
    assert r.json()["aceita_gravacao"] is True
    lista = (await client.get("/crm/ligacoes/gravadores", headers=base["h"])).json()
    assert lista["gravadores"][0]["online"] is True
    assert lista["gravadores"][0]["versao_agente"] == "1.0.0"
    # O token em claro não volta na lista.
    assert token not in str(lista)


async def test_gravador_recusa_token_errado_jwt_e_revogado(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    assert (await client.post("/ligacoes/gravador/pulso", json={},
                              headers={"Authorization": "Bearer hipograv_errado"})).status_code == 401
    # O JWT do usuário não abre a porta do gravador.
    assert (await client.post("/ligacoes/gravador/pulso", json={}, headers=base["h"])).status_code == 401
    gid = (await client.get("/crm/ligacoes/gravadores", headers=base["h"])).json()["gravadores"][0]["id"]
    assert (await client.delete(f"/crm/ligacoes/gravadores/{gid}", headers=base["h"])).status_code == 200
    assert (await client.post("/ligacoes/gravador/pulso", json={}, headers=gh)).status_code == 401


async def test_usuario_inativo_nao_grava(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    await base["conn"].execute("UPDATE usuarios SET ativo = FALSE WHERE email = 'sdr@teste.com'")
    assert (await client.post("/ligacoes/gravador/pulso", json={}, headers=gh)).status_code == 401


async def test_outro_usuario_nao_revoga_gravador_alheio(client, base):
    await novo_gravador(client, base["h"])
    gid = (await client.get("/crm/ligacoes/gravadores", headers=base["h"])).json()["gravadores"][0]["id"]
    r = await client.delete(f"/crm/ligacoes/gravadores/{gid}", headers=base["ev"]["headers"])
    assert r.status_code == 404
    # A gestão vê todos e pode revogar.
    todos = (await client.get("/crm/ligacoes/gravadores?todos=true", headers=base["adm"]["headers"])).json()
    assert len(todos["gravadores"]) == 1
    assert (await client.delete(f"/crm/ligacoes/gravadores/{gid}",
                                headers=base["adm"]["headers"])).status_code == 200


async def test_sem_s3_o_servidor_pede_para_guardar(client, base, monkeypatch):
    _, gh = await novo_gravador(client, base["h"])
    monkeypatch.setattr(aws, "problemas", lambda: ["S3_BUCKET_ANEXOS não configurado"])
    r = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    assert r.status_code == 503


async def test_gravacao_curta_e_recusada(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    r = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora(), dur=2), headers=gh)
    assert r.status_code == 422


# ── Casamento ────────────────────────────────────────────────────────


async def test_gravacao_casa_com_o_clique_e_transcreve(client, base, aws_falsa):
    clique = await clicar(client, base)
    _, gh = await novo_gravador(client, base["h"])
    corpo, fim = await gravar_e_subir(client, aws_falsa, gh, agora() + timedelta(seconds=5))
    assert corpo["ligacao_id"] == clique["id"]
    assert corpo["vinculada"] is True
    assert fim["status"] == "transcrevendo"
    assert len(aws_falsa.jobs) == 1

    aws_falsa.terminar()
    await coleta.passada(base["conn"])

    d = (await client.get(f"/crm/ligacoes/{clique['id']}", headers=base["h"])).json()
    assert d["status"] == "pronta"
    assert d["transcricao"][0]["participante"] == "Test"          # primeiro nome do SDR
    assert d["transcricao"][1]["participante"] == "Carla"         # primeiro nome do contato
    assert d["fala_usuario_pct"] == 56
    assert d["resumo"] == "Carla pediu retorno."
    assert d["proximos_passos"] == ["Ligar na quinta"]
    assert aws_falsa.chamadas["kw"]["rotulo"] == "ligação"
    assert aws_falsa.chamadas["ctx"]["empresa"] == "Metalurgica Alfa LTDA"
    assert aws_falsa.jobs_apagados                                   # job limpo na AWS


async def test_gravacao_nao_casa_com_clique_de_outra_pessoa(client, base, aws_falsa):
    await clicar(client, base)                                       # clique do SDR
    _, gh_ev = await novo_gravador(client, base["ev"]["headers"])
    corpo, _ = await gravar_e_subir(client, aws_falsa, gh_ev, agora())
    assert corpo["vinculada"] is False
    lig = await base["conn"].fetchrow("SELECT * FROM ligacoes WHERE id = $1", UUID(corpo["ligacao_id"]))
    assert lig["origem"] == "gravador"
    assert str(lig["usuario_id"]) != base["uid"]


async def test_relogio_atrasado_da_maquina_ainda_casa(client, base, aws_falsa):
    clique = await clicar(client, base)
    # O clique foi há 100 s; a chamada começou 5 s depois e acabou agora.
    await base["conn"].execute("UPDATE ligacoes SET clicada_em = NOW() - INTERVAL '100 seconds'")
    _, gh = await novo_gravador(client, base["h"])
    atraso = timedelta(minutes=10)
    # A máquina acha que são 10 min mais cedo: manda início e "agora" atrasados.
    corpo, _ = await gravar_e_subir(
        client, aws_falsa, gh, agora() - atraso - timedelta(seconds=95), id_local="grav-relogio-01",
        agora_agente=agora() - atraso,
    )
    assert corpo["ligacao_id"] == clique["id"]


async def test_reenvio_do_agente_cai_na_mesma_linha(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    a = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    b = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    assert a.json()["ligacao_id"] == b.json()["ligacao_id"]
    assert b.json()["upload_url"]
    # Depois de concluída, o reenvio só confirma.
    chave = b.json()["upload_url"].split("s3.falso/")[1].split("?")[0]
    aws_falsa.objetos[chave] = 1
    await client.post(f"/ligacoes/gravador/gravacoes/{a.json()['ligacao_id']}/concluir", headers=gh)
    c = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    assert c.json() == {"ligacao_id": a.json()["ligacao_id"], "ja_recebida": True}
    assert await base["conn"].fetchval("SELECT COUNT(*) FROM ligacoes") == 1


async def test_concluir_sem_arquivo_e_409(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    r = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    c = await client.post(f"/ligacoes/gravador/gravacoes/{r.json()['ligacao_id']}/concluir", headers=gh)
    assert c.status_code == 409


# ── Sem vínculo ──────────────────────────────────────────────────────


async def test_sem_vinculo_so_dono_e_gestao_e_vincular(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    corpo, _ = await gravar_e_subir(client, aws_falsa, gh, agora())
    lid = corpo["ligacao_id"]

    minhas = (await client.get("/crm/ligacoes/sem-vinculo", headers=base["h"])).json()
    assert [l["id"] for l in minhas["ligacoes"]] == [lid]
    assert minhas["gravador_online"] is True
    assert (await client.get(f"/crm/ligacoes/{lid}", headers=base["ev"]["headers"])).status_code == 404
    assert (await client.get(f"/crm/ligacoes/{lid}", headers=base["adm"]["headers"])).status_code == 200
    # Outro operacional não vincula a gravação de alguém.
    r = await client.post(f"/crm/ligacoes/{lid}/vincular",
                          json={"oportunidade_id": base["opp"]["id"]}, headers=base["ev"]["headers"])
    assert r.status_code == 404

    r = await client.post(f"/crm/ligacoes/{lid}/vincular", json={
        "oportunidade_id": base["opp"]["id"], "contato_id": base["contato_id"],
    }, headers=base["h"])
    assert r.status_code == 200, r.text
    assert r.json()["vinculada"] is True
    # Vinculada: é da negociação, o EV vê.
    assert (await client.get(f"/crm/ligacoes/{lid}", headers=base["ev"]["headers"])).status_code == 200
    aba = (await client.get(f"/crm/ligacoes?oportunidade_id={base['opp']['id']}",
                            headers=base["ev"]["headers"])).json()
    assert [l["id"] for l in aba["ligacoes"]] == [lid]
    assert aba["kpis"]["gravadas"] == 1


async def test_descartar_so_sem_vinculo(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    corpo, _ = await gravar_e_subir(client, aws_falsa, gh, agora())
    lid = corpo["ligacao_id"]
    r = await client.delete(f"/crm/ligacoes/{lid}", headers=base["h"])
    assert r.status_code == 200
    assert aws_falsa.removidos
    assert await base["conn"].fetchval("SELECT COUNT(*) FROM ligacoes") == 0

    clique = await clicar(client, base)
    corpo, _ = await gravar_e_subir(client, aws_falsa, gh, agora(), id_local="grav-0002-abcd")
    assert corpo["ligacao_id"] == clique["id"]
    assert (await client.delete(f"/crm/ligacoes/{clique['id']}", headers=base["h"])).status_code == 409


async def test_listar_exige_um_filtro(client, base):
    assert (await client.get("/crm/ligacoes", headers=base["h"])).status_code == 422


async def test_ouvir_devolve_url_assinada(client, base, aws_falsa):
    clique = await clicar(client, base)
    assert (await client.get(f"/crm/ligacoes/{clique['id']}/audio", headers=base["h"])).status_code == 404
    _, gh = await novo_gravador(client, base["h"])
    await gravar_e_subir(client, aws_falsa, gh, agora())
    r = await client.get(f"/crm/ligacoes/{clique['id']}/audio", headers=base["h"])
    assert r.status_code == 200
    assert r.json()["url"].endswith("?get")


# ── A passada ────────────────────────────────────────────────────────


async def test_audio_sem_fala_vira_sem_fala(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    corpo, _ = await gravar_e_subir(client, aws_falsa, gh, agora())
    aws_falsa.resultado = {"results": {"channel_labels": {"channels": []}}}
    aws_falsa.terminar()
    await coleta.passada(base["conn"])
    st = await base["conn"].fetchval("SELECT status FROM ligacoes WHERE id = $1", UUID(corpo["ligacao_id"]))
    assert st == "sem_fala"
    assert aws_falsa.chamadas["resumir"] == 0


async def test_falha_da_aws_vira_coluna_e_tenta_de_novo(client, base, aws_falsa):
    from botocore.exceptions import ClientError

    _, gh = await novo_gravador(client, base["h"])
    aws_falsa.falha_inicio = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "x"}}, "StartTranscriptionJob")
    corpo, fim = await gravar_e_subir(client, aws_falsa, gh, agora())
    lid = UUID(corpo["ligacao_id"])
    lig = await base["conn"].fetchrow("SELECT * FROM ligacoes WHERE id = $1", lid)
    assert lig["status"] == "transcrevendo" and lig["transcricao_job"] is None
    assert "permissão" in lig["erro"]
    assert lig["tentativas"] == 1

    aws_falsa.falha_inicio = None
    await coleta.passada(base["conn"])
    lig = await base["conn"].fetchrow("SELECT * FROM ligacoes WHERE id = $1", lid)
    assert lig["transcricao_job"] == f"hipo-ligacao-{lid}-t2"
    assert lig["erro"] is None


async def test_job_que_falha_desiste_depois_do_limite(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    corpo, _ = await gravar_e_subir(client, aws_falsa, gh, agora())
    lid = UUID(corpo["ligacao_id"])
    for _ in range(4):
        aws_falsa.terminar("FAILED", "audio corrompido")
        await coleta.passada(base["conn"])
    lig = await base["conn"].fetchrow("SELECT * FROM ligacoes WHERE id = $1", lid)
    assert lig["status"] == "erro"
    assert "audio corrompido" in lig["erro"]


async def test_clique_sem_gravacao_expira(client, base, aws_falsa):
    clique = await clicar(client, base)
    await base["conn"].execute("UPDATE ligacoes SET clicada_em = NOW() - INTERVAL '7 hours'")
    await coleta.passada(base["conn"])
    d = (await client.get(f"/crm/ligacoes/{clique['id']}", headers=base["h"])).json()
    assert d["status"] == "sem_gravacao"
    assert d["status_rotulo"] == "Sem gravação"


async def test_upload_que_nunca_chegou_vira_erro(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    r = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    lid = UUID(r.json()["ligacao_id"])
    await base["conn"].execute("UPDATE ligacoes SET atualizado_em = NOW() - INTERVAL '3 hours'")
    await coleta.passada(base["conn"])
    lig = await base["conn"].fetchrow("SELECT * FROM ligacoes WHERE id = $1", lid)
    assert lig["status"] == "erro" and lig["audio_s3_chave"] is None
    # O agente reenvia a mesma gravação: volta a "enviando".
    again = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    assert again.json()["ligacao_id"] == str(lid) and again.json()["upload_url"]


async def test_upload_que_chegou_sem_confirmar_segue(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    r = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    chave = r.json()["upload_url"].split("s3.falso/")[1].split("?")[0]
    aws_falsa.objetos[chave] = 12345
    await base["conn"].execute("UPDATE ligacoes SET atualizado_em = NOW() - INTERVAL '3 hours'")
    await coleta.passada(base["conn"])
    lig = await base["conn"].fetchrow("SELECT * FROM ligacoes")
    assert lig["status"] == "transcrevendo" and lig["audio_bytes"] == 12345


async def test_retencao_apaga_o_audio_e_guarda_o_texto(client, base, aws_falsa):
    clique = await clicar(client, base)
    _, gh = await novo_gravador(client, base["h"])
    await gravar_e_subir(client, aws_falsa, gh, agora())
    aws_falsa.terminar()
    await coleta.passada(base["conn"])
    await base["conn"].execute("UPDATE ligacoes SET inicio_em = NOW() - INTERVAL '200 days'")
    n = await coleta.reter(base["conn"], retencao_dias=180)
    assert n == 1
    d = (await client.get(f"/crm/ligacoes/{clique['id']}", headers=base["h"])).json()
    assert d["tem_audio"] is False and d["transcricao"]
    r = await client.get(f"/crm/ligacoes/{clique['id']}/audio", headers=base["h"])
    assert r.status_code == 410


async def test_atualizar_e_resumo_pela_tela(client, base, aws_falsa):
    clique = await clicar(client, base)
    _, gh = await novo_gravador(client, base["h"])
    await gravar_e_subir(client, aws_falsa, gh, agora())
    aws_falsa.terminar()
    r = await client.post(f"/crm/ligacoes/{clique['id']}/atualizar", headers=base["h"])
    assert r.status_code == 200 and r.json()["status"] == "pronta"
    r = await client.post(f"/crm/ligacoes/{clique['id']}/resumo", headers=base["h"])
    assert r.status_code == 200 and r.json()["resumo"]
    # Quem não ligou não refaz o resumo.
    r = await client.post(f"/crm/ligacoes/{clique['id']}/resumo", headers=base["ev"]["headers"])
    assert r.status_code == 403


# ── Corridas e becos sem saída (revisão da 056) ──────────────────────


async def test_timer_e_botao_ao_mesmo_tempo_nao_disputam(client, base, aws_falsa):
    """Com a trava de outra conexão na mão, a passada só devolve o estado."""
    import asyncpg

    from tests.conftest import _DB_URL

    clique = await clicar(client, base)
    _, gh = await novo_gravador(client, base["h"])
    await gravar_e_subir(client, aws_falsa, gh, agora())
    aws_falsa.terminar()
    lid = UUID(clique["id"])
    outra = await asyncpg.connect(_DB_URL)
    try:
        await outra.fetchval("SELECT pg_advisory_lock($1)", coleta._chave_trava(lid))
        atual = await coleta.processar(base["conn"], lid)
        assert atual["status"] == "transcrevendo"          # não mexeu
        await outra.fetchval("SELECT pg_advisory_unlock($1)", coleta._chave_trava(lid))
    finally:
        await outra.close()
    atual = await coleta.processar(base["conn"], lid)
    assert atual["status"] == "pronta"


async def test_gravacao_atrasada_reabre_clique_dado_por_perdido(client, base, aws_falsa):
    clique = await clicar(client, base)
    await base["conn"].execute(
        "UPDATE ligacoes SET status = 'sem_gravacao', clicada_em = NOW() - INTERVAL '8 hours'")
    _, gh = await novo_gravador(client, base["h"])
    # O agente guardou offline: a chamada foi há 8 h (relógio da máquina certo).
    corpo, _ = await gravar_e_subir(
        client, aws_falsa, gh, agora() - timedelta(hours=8) + timedelta(seconds=10),
        id_local="grav-atrasada-1",
    )
    assert corpo["ligacao_id"] == clique["id"] and corpo["vinculada"] is True


async def test_resultado_ilegivel_desiste_depois_da_janela(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    corpo, _ = await gravar_e_subir(client, aws_falsa, gh, agora())
    lid = UUID(corpo["ligacao_id"])

    def explode(url):
        raise ValueError("json torto")

    aws_falsa.baixar_transcricao = explode
    aws.baixar_transcricao = explode
    aws_falsa.terminar()
    await coleta.passada(base["conn"])
    lig = await base["conn"].fetchrow("SELECT * FROM ligacoes WHERE id = $1", lid)
    assert lig["status"] == "transcrevendo" and "ler a transcrição" in lig["erro"]
    await base["conn"].execute(
        "UPDATE ligacoes SET transcricao_iniciada_em = NOW() - INTERVAL '4 hours' WHERE id = $1", lid)
    await coleta.passada(base["conn"])
    assert await base["conn"].fetchval("SELECT status FROM ligacoes WHERE id = $1", lid) == "erro"


async def test_nao_descarta_no_meio_do_envio(client, base, aws_falsa):
    _, gh = await novo_gravador(client, base["h"])
    r = await client.post("/ligacoes/gravador/gravacoes", json=gravacao(agora()), headers=gh)
    d = await client.delete(f"/crm/ligacoes/{r.json()['ligacao_id']}", headers=base["h"])
    assert d.status_code == 409


async def test_lote_do_timer_ignora_clique_que_ainda_espera(client, base, aws_falsa):
    await clicar(client, base)
    assert await coleta.pendentes(base["conn"]) == []
    await base["conn"].execute("UPDATE ligacoes SET clicada_em = NOW() - INTERVAL '7 hours'")
    assert len(await coleta.pendentes(base["conn"])) == 1
