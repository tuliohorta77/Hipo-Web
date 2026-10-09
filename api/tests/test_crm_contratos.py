"""
HIPO — Contrato pela Autentique: rotas e webhook (entrega 053).

A Autentique e o LibreOffice são dublados: a suíte nunca fala com a API
de verdade nem precisa do LibreOffice (o CI não tem). O que se prova aqui é
o que só aparece com banco — o registro do envio, o estado que anda com o
documento lido da Autentique, as tarefas, as travas e o webhook.
"""
import hashlib
import hmac
import json
import uuid
from types import SimpleNamespace

import pytest

from config import settings
from routers import crm_contratos
from services import autentique
from services import contrato_render as render
from services import proposta_render
from tests.conftest import criar_usuario
from tests.test_crm_propostas import corpo_proposta, nova_conta, nova_oportunidade

PDF_FALSO = b"%PDF-1.4 contrato de teste"
SEGREDO = "segredo-do-webhook"
CEO = ("Marcelo Canton Dick", "marcelod@controllermedseg.com.br")


# ── Dublês ───────────────────────────────────────────────────────────

class AutentiqueFalsa:
    """Guarda o que o HIPO pediu e devolve um documento controlável."""

    def __init__(self):
        self.criados = []
        self.documentos = {}
        self.reenviados = []
        self.cancelados = []
        self.falhar_criacao = None

    async def criar_documento(self, *, nome, mensagem, pdf, nome_arquivo, signatarios,
                              posicoes=None):
        if self.falhar_criacao:
            raise autentique.AutentiqueErro(self.falhar_criacao)
        doc_id = f"doc-{len(self.criados) + 1}"
        self.criados.append({"id": doc_id, "nome": nome, "pdf": pdf,
                             "signatarios": signatarios, "posicoes": posicoes})
        self.documentos[doc_id] = {
            "id": doc_id,
            "files": {"original": f"https://x/{doc_id}/o.pdf",
                      "signed": f"https://x/{doc_id}/s.pdf"},
            "signatures": [{"public_id": f"{doc_id}-p{i}", "email": s["email"],
                            "name": s["nome"]} for i, s in enumerate(signatarios)],
        }
        return autentique.DocumentoCriado(
            id=doc_id,
            assinaturas=[autentique.Assinatura(public_id=f"{doc_id}-p{i}", email=s["email"],
                                               nome=s["nome"], acao=s["acao"], link=None)
                         for i, s in enumerate(signatarios)],
        )

    async def consultar(self, doc_id):
        return json.loads(json.dumps(self.documentos[doc_id]))

    async def reenviar(self, ids):
        self.reenviados.append(list(ids))

    async def cancelar(self, doc_id, agora=None):
        self.cancelados.append(doc_id)

    async def baixar(self, url):
        return b"%PDF-1.4 baixado de " + url.encode()

    def marcar(self, doc_id, indice, **eventos):
        """marcar('doc-1', 0, viewed='...', signed='...', rejected=('...', motivo))"""
        a = self.documentos[doc_id]["signatures"][indice]
        for chave, valor in eventos.items():
            if chave == "rejected":
                quando, motivo = valor
                a["rejected"] = {"created_at": quando, "reason": motivo}
            else:
                a[chave] = {"created_at": valor}

    def assinar_todos(self, doc_id):
        for i in range(len(self.documentos[doc_id]["signatures"])):
            self.marcar(doc_id, i, viewed=f"2026-10-08 12:0{i}:00",
                        signed=f"2026-10-08 12:1{i}:00")


@pytest.fixture
def fake(monkeypatch):
    f = AutentiqueFalsa()
    for nome in ("criar_documento", "consultar", "reenviar", "cancelar", "baixar"):
        monkeypatch.setattr(autentique, nome, getattr(f, nome))
    monkeypatch.setattr(settings, "AUTENTIQUE_API_TOKEN", "token-teste")
    monkeypatch.setattr(settings, "AUTENTIQUE_WEBHOOK_SEGREDO", SEGREDO)
    monkeypatch.setattr(settings, "CONTRATO_CONTRATADA_NOME", CEO[0])
    monkeypatch.setattr(settings, "CONTRATO_CONTRATADA_EMAIL", CEO[1])
    monkeypatch.setattr(settings, "S3_BUCKET_ANEXOS", "")
    monkeypatch.setattr(proposta_render, "libreoffice_disponivel", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(render, "montar_pdf", lambda simples, listas: PDF_FALSO)
    monkeypatch.setattr(render, "localizar_assinaturas", lambda pdf: {
        "contratante": {"x": "10.0", "y": "40.0", "z": 4}})
    return f


# ── Cenário ──────────────────────────────────────────────────────────

ENDERECO = {"cep": "07111000", "logradouro": "Rua Maria Isabel Rezende", "numero": "206",
            "bairro": "Vila Isabel", "cidade": "Guarulhos", "uf": "SP"}


async def cenario(client, headers, *, aprovar=True, endereco=True):
    conta = await nova_conta(client, headers)
    if endereco:
        r = await client.patch(f"/crm/contas/{conta['id']}", json=ENDERECO, headers=headers)
        assert r.status_code == 200, r.text
    opp = await nova_oportunidade(client, headers, conta["id"])
    prop = (await client.post(f"/crm/oportunidades/{opp['id']}/propostas",
                              json=corpo_proposta(), headers=headers)).json()
    if aprovar:
        r = await client.post(f"/crm/propostas/{prop['id']}/aprovar", headers=headers)
        assert r.status_code == 200, r.text
    contato = (await client.post("/crm/contatos", json={
        "nome": "Eladir Quadros", "email": "eladir@cliente.com.br", "conta_id": conta["id"],
    }, headers=headers)).json()
    r = await client.post(f"/crm/oportunidades/{opp['id']}/contatos",
                          json={"contato_id": contato["id"], "papel": "decisor"},
                          headers=headers)
    assert r.status_code == 201, r.text
    return SimpleNamespace(conta=conta, opp=opp, prop=prop, contato=contato)


def corpo_envio(c, **troca):
    base = {
        "signatarios": [
            {"papel": "contratante", "nome": "Eladir Quadros",
             "email": "eladir@cliente.com.br", "contato_id": c.contato["id"]},
            {"papel": "testemunha_contratante", "nome": "Ana RH",
             "email": "ana@cliente.com.br"},
            {"papel": "testemunha_contratada", "nome": "Bruno Gonçalo",
             "email": "bruno@controllermedseg.com.br"},
        ],
        "data_contrato": "2026-10-08",
        "dia_vencimento": 10,
    }
    base.update(troca)
    return base


async def enviar(client, headers, c, **troca):
    return await client.post(f"/crm/propostas/{c.prop['id']}/contratos",
                             json=corpo_envio(c, **troca), headers=headers)


def assinar_webhook(corpo: bytes, segredo=SEGREDO) -> dict:
    return {"X-Autentique-Signature": hmac.new(segredo.encode(), corpo,
                                               hashlib.sha256).hexdigest(),
            "Content-Type": "application/json"}


async def webhook(client, doc_id, evento_id, tipo="signature.accepted", segredo=SEGREDO):
    # Evento de documento traz o id em data.id; de assinatura, em data.document.
    dados = {"id": doc_id} if tipo.startswith("document.") else {"document": doc_id}
    corpo = json.dumps({"id": "w", "event": {"id": evento_id, "type": tipo,
                                             "data": dados}}).encode()
    return await client.post("/webhooks/autentique", content=corpo,
                             headers=assinar_webhook(corpo, segredo))


# ── Situação ─────────────────────────────────────────────────────────

class TestSituacao:
    async def test_desligado_sem_token(self, db_conn, client, usuario_adm, monkeypatch):
        monkeypatch.setattr(settings, "AUTENTIQUE_API_TOKEN", "")
        monkeypatch.setattr(settings, "CONTRATO_CONTRATADA_EMAIL", "")
        body = (await client.get("/crm/contratos/situacao",
                                 headers=usuario_adm["headers"])).json()
        assert body["configurado"] is False
        assert any("AUTENTIQUE_API_TOKEN" in p for p in body["problemas"])
        assert any("CONTRATADA" in p for p in body["problemas"])
        # Fora de produção é sempre sandbox.
        assert body["sandbox"] is True

    async def test_ligado(self, db_conn, client, usuario_adm, fake):
        body = (await client.get("/crm/contratos/situacao",
                                 headers=usuario_adm["headers"])).json()
        assert body == {"configurado": True, "problemas": [], "sandbox": True,
                        "previa_disponivel": True, "aviso_destinatarios": []}

    async def test_instancia_com_sigla_exige_modelo_proprio(self, db_conn, client,
                                                             usuario_adm, fake, monkeypatch):
        monkeypatch.setattr(autentique, "empresa_sigla", lambda: "MOS")
        body = (await client.get("/crm/contratos/situacao",
                                 headers=usuario_adm["headers"])).json()
        assert any("CONTRATO_MODELO_ARQUIVO" in p for p in body["problemas"])


# ── Padrão ───────────────────────────────────────────────────────────

class TestPadrao:
    async def test_sugere_decisor_e_executivo(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        body = (await client.get(f"/crm/propostas/{c.prop['id']}/contrato-padrao",
                                 headers=h)).json()
        assert body["aprovada"] is True
        assert body["sugestao_contratante_id"] == c.contato["id"]
        me = (await client.get("/auth/me", headers=h)).json()
        assert body["sugestao_testemunha_contratada_id"] == me["id"]
        assert body["contratada_email"] == CEO[1]
        assert body["pendencias_endereco"] == []
        assert body["endereco"].startswith("Rua Maria Isabel Rezende, 206")
        assert body["linhas_preco"] == ["R$ 20,00 por funcionário registrado/mês;",
                                        "Treinamentos: R$ 2.000,00 (valor único, "
                                        "conforme proposta comercial);",
                                        "Laudos: R$ 1.000,00 (valor único, conforme "
                                        "proposta comercial)."]
        assert body["contrato_em_aberto_id"] is None

    async def test_endereco_pendente(self, db_conn, client, usuario_adm, fake):
        c = await cenario(client, usuario_adm["headers"], endereco=False)
        body = (await client.get(f"/crm/propostas/{c.prop['id']}/contrato-padrao",
                                 headers=usuario_adm["headers"])).json()
        assert "logradouro" in body["pendencias_endereco"]


# ── Envio ────────────────────────────────────────────────────────────

class TestEnvio:
    async def test_envia_e_registra(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        r = await enviar(client, h, c)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "enviado"
        assert body["versao"] == 1
        assert body["sandbox"] is True
        assert body["hash_original"] == hashlib.sha256(PDF_FALSO).hexdigest()
        assert [s["papel"] for s in body["signatarios"]] == [
            "contratante", "testemunha_contratante", "contratada", "testemunha_contratada"]
        contratada = body["signatarios"][2]
        assert (contratada["nome"], contratada["email"]) == CEO
        assert body["signatarios"][0]["da_vez"] is True
        assert body["proximo_nome"] == "Eladir Quadros"
        assert body["eventos"][0]["tipo"] == "enviado"
        assert "sandbox" in body["eventos"][0]["descricao"].lower()

        [enviado] = fake.criados
        assert enviado["pdf"] == PDF_FALSO
        assert [s["acao"] for s in enviado["signatarios"]] == [
            "SIGN", "SIGN_AS_A_WITNESS", "SIGN", "SIGN_AS_A_WITNESS"]
        assert enviado["posicoes"]["contratante"]["z"] == 4

        sig = await db_conn.fetch(
            "SELECT papel, autentique_public_id, contato_id FROM contrato_signatarios "
            "ORDER BY ordem")
        assert sig[0]["autentique_public_id"] == "doc-1-p0"
        assert str(sig[0]["contato_id"]) == c.contato["id"]

    async def test_envio_vira_tarefa_concluida(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        await enviar(client, h, c)
        t = await db_conn.fetchrow(
            "SELECT t.* FROM tarefas t JOIN contratos k ON k.tarefa_envio_id = t.id")
        assert t["concluida_em"] is not None
        assert t["titulo"] == "Contrato v1 enviado para assinatura"
        assert "Marcelo Canton Dick" in t["resultado"]

    async def test_contratada_nao_vem_da_tela(self, db_conn, client, usuario_adm, fake):
        c = await cenario(client, usuario_adm["headers"])
        sigs = corpo_envio(c)["signatarios"]
        sigs[2] = {"papel": "contratada", "nome": "Outro", "email": "outro@x.com"}
        r = await enviar(client, usuario_adm["headers"], c, signatarios=sigs)
        assert r.status_code == 422

    async def test_mesmo_email_em_dois_papeis(self, db_conn, client, usuario_adm, fake):
        c = await cenario(client, usuario_adm["headers"])
        sigs = corpo_envio(c)["signatarios"]
        sigs[2]["email"] = CEO[1]
        r = await enviar(client, usuario_adm["headers"], c, signatarios=sigs)
        assert r.status_code == 422
        assert "pessoa diferente" in r.json()["detail"]
        assert fake.criados == []

    async def test_proposta_nao_aprovada(self, db_conn, client, usuario_adm, fake):
        c = await cenario(client, usuario_adm["headers"], aprovar=False)
        r = await enviar(client, usuario_adm["headers"], c)
        assert r.status_code == 422
        assert "Aprove" in r.json()["detail"]

    async def test_endereco_incompleto(self, db_conn, client, usuario_adm, fake):
        c = await cenario(client, usuario_adm["headers"], endereco=False)
        r = await enviar(client, usuario_adm["headers"], c)
        assert r.status_code == 422
        assert "endereço" in r.json()["detail"]

    async def test_contato_de_fora(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        outro = (await client.post("/crm/contatos", json={"nome": "Estranho"}, headers=h)).json()
        sigs = corpo_envio(c)["signatarios"]
        sigs[1]["contato_id"] = outro["id"]
        r = await enviar(client, h, c, signatarios=sigs)
        assert r.status_code == 422

    async def test_um_em_andamento_por_oportunidade(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        assert (await enviar(client, h, c)).status_code == 201
        r = await enviar(client, h, c)
        assert r.status_code == 409
        assert "Cancele" in r.json()["detail"]

    async def test_autentique_recusa_nada_fica(self, db_conn, client, usuario_adm, fake):
        fake.falhar_criacao = "A Autentique recusou o pedido: arquivo inválido"
        c = await cenario(client, usuario_adm["headers"])
        r = await enviar(client, usuario_adm["headers"], c)
        assert r.status_code == 502
        assert await db_conn.fetchval("SELECT COUNT(*) FROM contratos") == 0
        assert await db_conn.fetchval(
            "SELECT COUNT(*) FROM tarefas WHERE titulo LIKE 'Contrato%'") == 0

    async def test_desligado(self, db_conn, client, usuario_adm, fake, monkeypatch):
        monkeypatch.setattr(settings, "AUTENTIQUE_API_TOKEN", "")
        c = await cenario(client, usuario_adm["headers"])
        r = await enviar(client, usuario_adm["headers"], c)
        assert r.status_code == 503

    async def test_oportunidade_finalizada(self, db_conn, client, usuario_adm, fake):
        c = await cenario(client, usuario_adm["headers"])
        await db_conn.execute(
            "UPDATE oportunidades SET status = 'conquistado', fase = 'finalizado' WHERE id = $1",
            uuid.UUID(c.opp["id"]))
        r = await enviar(client, usuario_adm["headers"], c)
        assert r.status_code == 422

    async def test_previa_devolve_o_pdf(self, db_conn, client, usuario_adm, fake):
        c = await cenario(client, usuario_adm["headers"])
        r = await client.post(f"/crm/propostas/{c.prop['id']}/contrato/previa",
                              json={"dia_vencimento": 5}, headers=usuario_adm["headers"])
        assert r.status_code == 200
        assert r.content == PDF_FALSO
        assert fake.criados == []

    async def test_modelo_quebrado_vira_503(self, db_conn, client, usuario_adm, fake,
                                            monkeypatch):
        def quebra(simples, listas):
            raise render.ModeloInvalido("campo {{X}} desconhecido")
        monkeypatch.setattr(render, "montar_pdf", quebra)
        c = await cenario(client, usuario_adm["headers"])
        r = await enviar(client, usuario_adm["headers"], c)
        assert r.status_code == 503
        assert fake.criados == []


# ── Estado: webhook e sincronização ──────────────────────────────────

class TestWebhook:
    async def test_assinatura_errada(self, db_conn, client, usuario_adm, fake):
        r = await webhook(client, "doc-1", "e1", segredo="outro")
        assert r.status_code == 401

    async def test_sem_segredo_configurado(self, db_conn, client, fake, monkeypatch):
        monkeypatch.setattr(settings, "AUTENTIQUE_WEBHOOK_SEGREDO", "")
        r = await webhook(client, "doc-1", "e1")
        assert r.status_code == 503

    async def test_documento_alheio_e_ignorado(self, db_conn, client, fake):
        r = await webhook(client, "doc-de-outro-lugar", "e1")
        assert r.status_code == 200
        assert "ignorado" in r.json()

    async def test_visualizou_e_assinou(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        fake.marcar("doc-1", 0, viewed="2026-10-08 12:00:00", signed="2026-10-08 12:05:00")
        r = await webhook(client, "doc-1", "e1")
        assert r.status_code == 200, r.text
        body = (await client.get(f"/crm/contratos/{contrato['id']}", headers=h)).json()
        assert body["signatarios"][0]["situacao"] == "assinado"
        assert body["assinados"] == 1
        assert body["proximo_nome"] == "Ana RH"
        assert body["signatarios"][1]["da_vez"] is True
        assert {e["descricao"] for e in body["eventos"]} >= {"Eladir Quadros assinou"}

    async def test_entrega_repetida(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        await enviar(client, h, c)
        fake.marcar("doc-1", 0, signed="2026-10-08 12:05:00")
        assert (await webhook(client, "doc-1", "e1")).status_code == 200
        r = await webhook(client, "doc-1", "e1")
        assert r.json() == {"ok": True, "repetido": True}
        assert await db_conn.fetchval(
            "SELECT COUNT(*) FROM contrato_eventos WHERE tipo = 'assinado'") == 1

    async def test_todos_assinaram_avisa_o_executivo(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        fake.assinar_todos("doc-1")
        r = await webhook(client, "doc-1", "e9", tipo="document.finished")
        assert r.status_code == 200
        assert r.json()["status"] == "assinado"
        body = (await client.get(f"/crm/contratos/{contrato['id']}", headers=h)).json()
        assert body["status"] == "assinado"
        assert body["assinado_em"] is not None
        assert body["tem_assinado"] is True
        assert body["pode_cancelar"] is False
        aviso = await db_conn.fetchrow(
            "SELECT t.* FROM tarefas t JOIN contratos k ON k.tarefa_aviso_id = t.id")
        assert aviso["concluida_em"] is None
        assert aviso["titulo"].startswith("Contrato assinado por todos")
        me = (await client.get("/auth/me", headers=h)).json()
        assert str(aviso["responsavel_id"]) == me["id"]
        # Só registra e avisa: a oportunidade continua aberta.
        status = await db_conn.fetchval("SELECT status FROM oportunidades WHERE id = $1",
                                        uuid.UUID(c.opp["id"]))
        assert status == "ativa"

    async def test_recusa_avisa_com_motivo(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        fake.marcar("doc-1", 0, rejected=("2026-10-08 12:00:00", "valor errado"))
        await webhook(client, "doc-1", "e1", tipo="signature.rejected")
        body = (await client.get(f"/crm/contratos/{contrato['id']}", headers=h)).json()
        assert body["status"] == "recusado"
        assert body["signatarios"][0]["motivo_recusa"] == "valor errado"
        aviso = await db_conn.fetchrow(
            "SELECT t.* FROM tarefas t JOIN contratos k ON k.tarefa_aviso_id = t.id")
        assert "recusado por Eladir Quadros" in aviso["titulo"]
        assert "valor errado" in aviso["descricao"]
        # Recusado libera mandar outro.
        assert (await enviar(client, h, c)).json()["versao"] == 2

    async def test_botao_atualizar(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        fake.marcar("doc-1", 0, viewed="2026-10-08 12:00:00")
        r = await client.post(f"/crm/contratos/{contrato['id']}/sincronizar", headers=h)
        assert r.status_code == 200
        assert r.json()["signatarios"][0]["situacao"] == "visualizado"
        assert r.json()["sincronizado_em"] is not None

    async def test_timer_pega_o_que_aguarda(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        await enviar(client, h, c)
        fila = await crm_contratos.pendentes_de_sincronizacao(db_conn)
        assert [f["autentique_id"] for f in fila] == ["doc-1"]
        fake.assinar_todos("doc-1")
        atualizado = await crm_contratos.sincronizar_um(db_conn, fila[0])
        assert atualizado["status"] == "assinado"
        # Sem bucket, assinado não volta para a fila.
        assert await crm_contratos.pendentes_de_sincronizacao(db_conn) == []

    async def test_sincronizar_de_novo_nao_duplica_tarefa(self, db_conn, client,
                                                          usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        fake.assinar_todos("doc-1")
        for _ in range(2):
            await client.post(f"/crm/contratos/{contrato['id']}/sincronizar", headers=h)
        assert await db_conn.fetchval(
            "SELECT COUNT(*) FROM tarefas WHERE titulo LIKE 'Contrato assinado%'") == 1


# ── Ações ────────────────────────────────────────────────────────────

class TestAcoes:
    async def test_reenviar_para_quem_e_a_vez(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        fake.marcar("doc-1", 0, signed="2026-10-08 12:05:00")
        await client.post(f"/crm/contratos/{contrato['id']}/sincronizar", headers=h)
        r = await client.post(f"/crm/contratos/{contrato['id']}/reenviar", headers=h)
        assert r.status_code == 200
        assert fake.reenviados == [["doc-1-p1"]]
        assert r.json()["signatarios"][1]["reenviado_em"] is not None

    async def test_cancelar_e_mandar_outro(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        r = await client.post(f"/crm/contratos/{contrato['id']}/cancelar",
                              json={"motivo": "cliente pediu mudar o vencimento"}, headers=h)
        assert r.status_code == 200
        assert r.json()["status"] == "cancelado"
        assert r.json()["motivo_cancelamento"] == "cliente pediu mudar o vencimento"
        assert fake.cancelados == ["doc-1"]
        novo = await enviar(client, h, c, dia_vencimento=15)
        assert novo.status_code == 201
        assert novo.json()["versao"] == 2

    async def test_cancelado_ignora_webhook(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        await client.post(f"/crm/contratos/{contrato['id']}/cancelar",
                          json={"motivo": "teste"}, headers=h)
        fake.assinar_todos("doc-1")
        r = await webhook(client, "doc-1", "e1")
        assert r.json()["ignorado"]
        body = (await client.get(f"/crm/contratos/{contrato['id']}", headers=h)).json()
        assert body["status"] == "cancelado"

    async def test_outro_operacional_nao_cancela(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr@teste.com")
        r = await client.post(f"/crm/contratos/{contrato['id']}/cancelar",
                              json={"motivo": "não sou eu"}, headers=sdr["headers"])
        assert r.status_code == 403
        lido = (await client.get(f"/crm/contratos/{contrato['id']}",
                                 headers=sdr["headers"])).json()
        assert lido["pode_cancelar"] is False

    async def test_listar_da_oportunidade(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        await client.post(f"/crm/contratos/{contrato['id']}/cancelar",
                          json={"motivo": "refazer"}, headers=h)
        await enviar(client, h, c)
        lista = (await client.get(f"/crm/oportunidades/{c.opp['id']}/contratos",
                                  headers=h)).json()
        assert [x["versao"] for x in lista] == [2, 1]
        assert [x["status"] for x in lista] == ["enviado", "cancelado"]

    async def test_arquivo_original_vem_da_autentique_sem_bucket(self, db_conn, client,
                                                                 usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        r = await client.get(f"/crm/contratos/{contrato['id']}/arquivo", headers=h)
        assert r.status_code == 200
        assert r.content.endswith(b"doc-1/o.pdf")
        assert "CONTRATO_" in r.headers["content-disposition"]

    async def test_assinado_antes_da_hora(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        r = await client.get(f"/crm/contratos/{contrato['id']}/arquivo",
                             params={"tipo": "assinado"}, headers=h)
        assert r.status_code == 409

    async def test_contrato_inexistente(self, db_conn, client, usuario_adm, fake):
        r = await client.get(f"/crm/contratos/{uuid.uuid4()}", headers=usuario_adm["headers"])
        assert r.status_code == 404

    async def test_s3_guarda_original_e_assinado(self, db_conn, client, usuario_adm, fake,
                                                 monkeypatch):
        guardados = {}
        monkeypatch.setattr(settings, "S3_BUCKET_ANEXOS", "bucket-teste")
        monkeypatch.setattr(crm_contratos.s3, "subir",
                            lambda chave, corpo, tipo: guardados.__setitem__(chave, corpo))
        monkeypatch.setattr(crm_contratos, "_ler_s3", lambda chave: guardados[chave])
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        assert any(k.endswith("/original.pdf") for k in guardados)
        fake.assinar_todos("doc-1")
        await webhook(client, "doc-1", "e1")
        assert any(k.endswith("/assinado.pdf") for k in guardados)
        r = await client.get(f"/crm/contratos/{contrato['id']}/arquivo",
                             params={"tipo": "assinado"}, headers=h)
        assert r.content == b"%PDF-1.4 baixado de https://x/doc-1/s.pdf"



# ── 054: aviso de contrato assinado ──────────────────────────────────

from email import message_from_bytes, policy  # noqa: E402

from services import gmail  # noqa: E402

DESTINOS = "faturamento@controllermedseg.com.br, contratos@controllermedseg.com.br; adm@controllermedseg.com.br"


class GmailFalso:
    def __init__(self):
        self.enviados = []
        self.falhar = None

    async def assinatura(self, email):
        return gmail.Assinatura(html="<p>Assinatura do EV</p>")

    async def enviar(self, email, mensagem):
        if self.falhar:
            return gmail.ResultadoEnvio(ok=False, erro=self.falhar)
        self.enviados.append((email, message_from_bytes(mensagem, policy=policy.default)))
        return gmail.ResultadoEnvio(ok=True, message_id="m1", thread_id="t1")


@pytest.fixture
def correio(monkeypatch, fake):
    g = GmailFalso()
    monkeypatch.setattr(gmail, "configurado", lambda: True)
    monkeypatch.setattr(gmail, "assinatura", g.assinatura)
    monkeypatch.setattr(gmail, "enviar", g.enviar)
    monkeypatch.setattr(settings, "CONTRATO_AVISO_DESTINATARIOS", DESTINOS)
    monkeypatch.setattr(settings, "HIPO_URL_PUBLICA", "")
    # Fora de produção todo contrato nasce sandbox, e contrato de teste não
    # avisa sozinho. Estes testes são do contrato de verdade.
    monkeypatch.setattr(autentique, "em_sandbox", lambda: False)
    return g


async def assinado_por_todos(client, h, c, fake, evento="e-fim"):
    contrato = (await enviar(client, h, c)).json()
    fake.assinar_todos("doc-1")
    r = await webhook(client, "doc-1", evento)
    assert r.status_code == 200, r.text
    return contrato


def _texto(msg):
    for parte in msg.walk():
        if parte.get_content_type() == "text/plain" and not parte.get_filename():
            return parte.get_content()
    return ""


class TestAviso:
    async def test_sai_quando_todos_assinam(self, db_conn, client, usuario_adm, fake, correio):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = await assinado_por_todos(client, h, c, fake)
        [(remetente, msg)] = correio.enviados
        assert remetente == "adm@teste.com"  # o executivo da proposta
        para = [e.strip() for e in " ".join(str(msg["To"]).split()).split(",")]
        assert para == ["faturamento@controllermedseg.com.br",
                        "contratos@controllermedseg.com.br", "adm@controllermedseg.com.br"]
        assert msg["Subject"].startswith("Contrato assinado — Metalurgica Alfa LTDA")
        corpo = _texto(msg)
        assert "11.222.333/0001-81" in corpo
        assert "R$ 20,00 por funcionário registrado/mês" in corpo
        assert "Vencimento: todo dia 10" in corpo
        assert "Contratada: Marcelo Canton Dick" in corpo
        assert f"/crm/oportunidades?abrir={c.opp['id']}" in corpo
        anexos = [p for p in msg.walk() if p.get_filename()]
        assert anexos[0].get_filename().endswith("_assinado.pdf")
        assert anexos[0].get_payload(decode=True).startswith(b"%PDF")

        body = (await client.get(f"/crm/contratos/{contrato['id']}", headers=h)).json()
        assert body["aviso_enviado_em"] is not None
        assert body["aviso_remetente"] == "adm@teste.com"
        assert len(body["aviso_para"]) == 3
        assert any(e["tipo"] == "aviso_enviado" for e in body["eventos"])

    async def test_nao_repete(self, db_conn, client, usuario_adm, fake, correio):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = await assinado_por_todos(client, h, c, fake)
        await webhook(client, "doc-1", "e-outro")
        await client.post(f"/crm/contratos/{contrato['id']}/sincronizar", headers=h)
        assert len(correio.enviados) == 1

    async def test_remetente_fora_da_lista(self, db_conn, client, usuario_adm, fake, correio,
                                           monkeypatch):
        monkeypatch.setattr(settings, "CONTRATO_AVISO_DESTINATARIOS",
                            DESTINOS + ", adm@teste.com, invalido")
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        await assinado_por_todos(client, h, c, fake)
        [(_, msg)] = correio.enviados
        assert "adm@teste.com" not in msg["To"]
        assert "invalido" not in msg["To"]

    async def test_desligado_sem_destinatarios(self, db_conn, client, usuario_adm, fake, correio,
                                               monkeypatch):
        monkeypatch.setattr(settings, "CONTRATO_AVISO_DESTINATARIOS", "")
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = await assinado_por_todos(client, h, c, fake)
        assert correio.enviados == []
        assert await crm_contratos.pendentes_de_sincronizacao(db_conn) == []
        r = await client.post(f"/crm/contratos/{contrato['id']}/aviso", headers=h)
        assert r.status_code == 503

    async def test_falha_do_gmail_nao_derruba_e_o_timer_tenta_de_novo(
        self, db_conn, client, usuario_adm, fake, correio,
    ):
        correio.falhar = "O Gmail recusou: delegação sem o escopo de envio."
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = await assinado_por_todos(client, h, c, fake)
        body = (await client.get(f"/crm/contratos/{contrato['id']}", headers=h)).json()
        assert body["status"] == "assinado"
        assert body["aviso_enviado_em"] is None
        assert "delegação" in body["aviso_erro"]

        fila = await crm_contratos.pendentes_de_sincronizacao(db_conn)
        assert [f["id"] for f in fila] == [uuid.UUID(contrato["id"])]
        correio.falhar = None
        await crm_contratos.sincronizar_um(db_conn, fila[0])
        assert len(correio.enviados) == 1
        assert await crm_contratos.pendentes_de_sincronizacao(db_conn) == []

    async def test_timer_desiste_depois_do_limite(self, db_conn, client, usuario_adm, fake,
                                                  correio):
        correio.falhar = "fora do ar"
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        await assinado_por_todos(client, h, c, fake)
        for _ in range(10):
            fila = await crm_contratos.pendentes_de_sincronizacao(db_conn)
            if not fila:
                break
            await crm_contratos.sincronizar_um(db_conn, fila[0])
        tentativas = await db_conn.fetchval("SELECT aviso_tentativas FROM contratos")
        from services import contrato as regras_contrato
        assert tentativas == regras_contrato.MAX_TENTATIVAS_AVISO
        assert await crm_contratos.pendentes_de_sincronizacao(db_conn) == []

    async def test_reenviar_manual(self, db_conn, client, usuario_adm, fake, correio):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = await assinado_por_todos(client, h, c, fake)
        lido = (await client.get(f"/crm/contratos/{contrato['id']}", headers=h)).json()
        assert lido["pode_reenviar_aviso"] is True
        r = await client.post(f"/crm/contratos/{contrato['id']}/aviso", headers=h)
        assert r.status_code == 200, r.text
        assert len(correio.enviados) == 2

    async def test_reenviar_antes_de_assinar(self, db_conn, client, usuario_adm, fake, correio):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = (await enviar(client, h, c)).json()
        r = await client.post(f"/crm/contratos/{contrato['id']}/aviso", headers=h)
        assert r.status_code == 409

    async def test_outro_operacional_nao_reenvia(self, db_conn, client, usuario_adm, fake,
                                                 correio):
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = await assinado_por_todos(client, h, c, fake)
        sdr = await criar_usuario(db_conn, client, "SDR", "sdr@teste.com")
        r = await client.post(f"/crm/contratos/{contrato['id']}/aviso", headers=sdr["headers"])
        assert r.status_code == 403

    async def test_contrato_de_teste_nao_avisa_sozinho(self, db_conn, client, usuario_adm,
                                                       fake, correio, monkeypatch):
        monkeypatch.setattr(autentique, "em_sandbox", lambda: True)
        h = usuario_adm["headers"]
        c = await cenario(client, h)
        contrato = await assinado_por_todos(client, h, c, fake)
        assert correio.enviados == []
        assert await crm_contratos.pendentes_de_sincronizacao(db_conn) == []
        # Pelo botão sai, marcado como teste.
        r = await client.post(f"/crm/contratos/{contrato['id']}/aviso", headers=h)
        assert r.status_code == 200, r.text
        [(_, msg)] = correio.enviados
        assert msg["Subject"].startswith("[TESTE] ")


# ── 055: grupos de CNPJ, substituição e serviços ─────────────────────

from tests.test_crm_proposta_multi_cnpj import (  # noqa: E402
    FILIAL_1, FILIAL_2, MATRIZ, OUTRA, corpo as corpo_multi, vincular,
)


async def cenario_grupos(client, h, *, filiais=(FILIAL_1,), outra=True):
    """Matriz + filiais (mesma raiz) e, opcionalmente, uma empresa de outra raiz."""
    matriz = (await client.post("/crm/contas", json={
        "razao_social": "PATIMIRIM PARTICIPACOES LTDA", "cnpj": MATRIZ, **ENDERECO,
    }, headers=h)).json()
    opp = (await client.post("/crm/oportunidades", json={"conta_id": matriz["id"]},
                             headers=h)).json()
    contas = [matriz]
    for i, cnpj in enumerate(filiais, start=1):
        c = (await client.post("/crm/contas", json={
            "razao_social": f"PATIMIRIM FILIAL {i} LTDA", "cnpj": cnpj, **ENDERECO,
        }, headers=h)).json()
        assert (await vincular(client, h, opp["id"], c["id"])).status_code == 201
        contas.append(c)
    if outra:
        c = (await client.post("/crm/contas", json={
            "razao_social": "OUTRA EMPRESA LTDA", "cnpj": OUTRA, **ENDERECO,
        }, headers=h)).json()
        assert (await vincular(client, h, opp["id"], c["id"])).status_code == 201
        contas.append(c)
    itens = [{"conta_id": c["id"], "vidas": 4} for c in contas]
    prop = (await client.post(f"/crm/oportunidades/{opp['id']}/propostas",
                              json=corpo_multi(itens, escopo=["PGR", "CIPA - NR-05"]),
                              headers=h)).json()
    r = await client.post(f"/crm/propostas/{prop['id']}/aprovar", headers=h)
    assert r.status_code == 200, r.text
    contato = (await client.post("/crm/contatos", json={
        "nome": "Eladir Quadros", "email": "eladir@cliente.com.br", "conta_id": matriz["id"],
    }, headers=h)).json()
    return SimpleNamespace(opp=opp, prop=prop, contas=contas, contato=contato)


class TestGrupos:
    async def test_padrao_separa_por_raiz(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario_grupos(client, h)
        body = (await client.get(f"/crm/propostas/{c.prop['id']}/contrato-padrao",
                                 headers=h)).json()
        assert [g["raiz"] for g in body["grupos"]] == [MATRIZ[:8], OUTRA[:8]]
        g1, g2 = body["grupos"]
        assert g1["principal"] and not g2["principal"]
        assert g1["contratante_razao_social"] == "PATIMIRIM PARTICIPACOES LTDA"
        assert [x["cnpj"] for x in g1["cnpjs"]] == [MATRIZ, FILIAL_1]
        assert [x["cnpj"] for x in g2["cnpjs"]] == [OUTRA]
        assert body["servicos_sugeridos"] == ["cipa"]
        assert {s["chave"] for s in body["servicos_catalogo"]} >= {"cipa", "ppp", "brigada"}

    async def test_um_contrato_por_raiz(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario_grupos(client, h)
        r1 = await enviar(client, h, c)  # sem raiz: o grupo do CNPJ principal
        assert r1.status_code == 201, r1.text
        b1 = r1.json()
        assert b1["raiz_cnpj"] == MATRIZ[:8]
        assert [x["cnpj"] for x in b1["cnpjs"]] == [MATRIZ, FILIAL_1]
        # O outro grupo pode ir em paralelo: a trava é por raiz.
        r2 = await enviar(client, h, c, raiz_cnpj=OUTRA[:8])
        assert r2.status_code == 201, r2.text
        assert r2.json()["contratante_razao_social"] == "OUTRA EMPRESA LTDA"
        # O mesmo grupo de novo, não.
        r3 = await enviar(client, h, c, raiz_cnpj=MATRIZ[:8])
        assert r3.status_code == 409
        assert "PATIMIRIM PARTICIPACOES" in r3.json()["detail"]

    async def test_raiz_de_fora_da_proposta(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario_grupos(client, h)
        r = await enviar(client, h, c, raiz_cnpj="12345678")
        assert r.status_code == 422

    async def test_servicos_vao_para_o_contrato(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario_grupos(client, h, outra=False)
        r = await enviar(client, h, c, servicos=["cipa", "ppp"],
                         servicos_livres=["Treinamento NR-35"])
        assert r.status_code == 201, r.text
        assert r.json()["servicos"] == ["cipa", "ppp"]
        listas = json.loads(await db_conn.fetchval("SELECT campos FROM contratos"))["listas"]
        assert listas["SERVICO_EXTRA"][0].startswith("2.7) Elaboração do PPP")
        assert listas["SERVICO_EXTRA"][2] == "2.9) Treinamento NR-35;"
        assert listas["ANEXO_LINHA"][0].startswith("PATIMIRIM FILIAL 1 LTDA – CNPJ")

    async def test_servico_desconhecido(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario_grupos(client, h, outra=False)
        r = await enviar(client, h, c, servicos=["xpto"])
        assert r.status_code == 422


class TestSubstituicao:
    async def test_contrato_novo_substitui_o_assinado(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario_grupos(client, h, outra=False)
        antigo = (await enviar(client, h, c)).json()
        fake.assinar_todos("doc-1")
        await webhook(client, "doc-1", "e1")

        # Entrou mais uma filial: proposta nova com todos os CNPJs.
        f2 = (await client.post("/crm/contas", json={
            "razao_social": "PATIMIRIM FILIAL 2 LTDA", "cnpj": FILIAL_2, **ENDERECO,
        }, headers=h)).json()
        assert (await vincular(client, h, c.opp["id"], f2["id"])).status_code == 201
        itens = [{"conta_id": x["id"], "vidas": 4} for x in c.contas + [f2]]
        prop2 = (await client.post(f"/crm/oportunidades/{c.opp['id']}/propostas",
                                   json=corpo_multi(itens), headers=h)).json()
        await client.post(f"/crm/propostas/{prop2['id']}/aprovar", headers=h)

        padrao = (await client.get(f"/crm/propostas/{prop2['id']}/contrato-padrao",
                                   headers=h)).json()
        assert [s["id"] for s in padrao["grupos"][0]["substitui"]] == [antigo["id"]]

        c2 = SimpleNamespace(**{**vars(c), "prop": prop2})
        novo = (await enviar(client, h, c2)).json()
        assert [x["cnpj"] for x in novo["cnpjs"]] == [MATRIZ, FILIAL_1, FILIAL_2]
        assert [s["versao"] for s in novo["substitui"]] == [1]
        listas = json.loads(await db_conn.fetchval(
            "SELECT campos FROM contratos WHERE id = $1", uuid.UUID(novo["id"])))["listas"]
        assert "substitui integralmente" in listas["SUBSTITUICAO"][0]

        # Enquanto o novo não é assinado, o antigo continua valendo.
        lido = (await client.get(f"/crm/contratos/{antigo['id']}", headers=h)).json()
        assert lido["status"] == "assinado"

        fake.assinar_todos("doc-2")
        await webhook(client, "doc-2", "e2")
        lido = (await client.get(f"/crm/contratos/{antigo['id']}", headers=h)).json()
        assert lido["status"] == "substituido"
        assert lido["substituido_por_versao"] == 2
        assert any(e["tipo"] == "substituido" for e in lido["eventos"])

    async def test_cancelar_o_novo_nao_mexe_no_antigo(self, db_conn, client, usuario_adm, fake):
        h = usuario_adm["headers"]
        c = await cenario_grupos(client, h, outra=False)
        antigo = (await enviar(client, h, c)).json()
        fake.assinar_todos("doc-1")
        await webhook(client, "doc-1", "e1")
        novo = (await enviar(client, h, c)).json()
        await client.post(f"/crm/contratos/{novo['id']}/cancelar",
                          json={"motivo": "desistiu"}, headers=h)
        lido = (await client.get(f"/crm/contratos/{antigo['id']}", headers=h)).json()
        assert lido["status"] == "assinado"
