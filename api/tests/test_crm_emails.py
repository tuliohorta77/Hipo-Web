"""
HIPO — Testes do router de e-mail comercial (050).

O Gmail é SIMULADO: o CI não tem credencial, e "Google desligado" é um dos
caminhos que precisam de teste. A simulação troca as quatro funções de
services/gmail que falam com a rede; tudo o que está entre a rota e elas
(contato, proposta, PDF, montagem da mensagem, gravação) roda de verdade.
"""
import email
import uuid
from datetime import datetime, timedelta, timezone
from email import policy

import pytest

from services import gmail
from services import proposta_render as render
from tests.conftest import criar_usuario
from tests.test_crm_propostas import corpo_proposta, nova_conta, nova_oportunidade

PDF_FALSO = b"%PDF-1.4 proposta de teste"


class GmailFalso:
    """Guarda o que foi enviado e responde como o Gmail responderia."""

    def __init__(self):
        self.enviadas: list[tuple[str, bytes]] = []
        self.assinatura_html = "<div>Assinatura do Gmail</div>"
        self.assinatura_erro = None
        self.erro_envio = None
        self.fios: dict[str, dict] = {}
        self.erro_fio = None

    async def assinatura(self, email_):
        return gmail.Assinatura(html=self.assinatura_html, erro=self.assinatura_erro)

    async def enviar(self, email_, mensagem):
        if self.erro_envio:
            return gmail.ResultadoEnvio(ok=False, erro=self.erro_envio)
        self.enviadas.append((email_, mensagem))
        n = len(self.enviadas)
        return gmail.ResultadoEnvio(ok=True, message_id=f"msg{n}", thread_id=f"fio{n}")

    async def fio(self, email_, thread_id):
        if self.erro_fio:
            return gmail.ResultadoFio(erro=self.erro_fio)
        return gmail.ResultadoFio(thread=self.fios.get(thread_id, {"messages": []}))


@pytest.fixture
def g(monkeypatch):
    falso = GmailFalso()
    monkeypatch.setattr(gmail, "configurado", lambda: True)
    monkeypatch.setattr(gmail, "problemas", lambda: [])
    monkeypatch.setattr(gmail, "assinatura", falso.assinatura)
    monkeypatch.setattr(gmail, "enviar", falso.enviar)
    monkeypatch.setattr(gmail, "fio", falso.fio)
    return falso


@pytest.fixture
def pdf(monkeypatch):
    """O CI não tem LibreOffice; o PDF é simulado, o PPTX é montado de verdade."""
    monkeypatch.setattr(render, "libreoffice_disponivel", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(render, "para_pdf", lambda pptx: PDF_FALSO)


async def cenario(client, db_conn, *, cargo="EV", email_contato="nivaldo@nnredutores.com.br"):
    u = await criar_usuario(db_conn, client, cargo, f"vendedor-{cargo.lower()}@controllermedseg.com")
    h = u["headers"]
    await db_conn.execute(
        "UPDATE usuarios SET nome = 'Gabriel Lira', telefone = '(11) 91100-5646' WHERE email = $1",
        u["email"],
    )
    conta = await nova_conta(client, h, razao="NN MANUTENCAO EM REDUTORES LTDA")
    opp = await nova_oportunidade(client, h, conta["id"])
    ct = await client.post(
        "/crm/contatos",
        json={"nome": "NIVALDO PEREIRA", "email": email_contato, "conta_id": conta["id"]},
        headers=h,
    )
    assert ct.status_code == 201, ct.text
    return u, conta, opp, ct.json()


def corpo_envio(contato_id, **troca):
    base = {
        "contato_id": contato_id,
        "para": ["nivaldo@nnredutores.com.br"],
        "assunto": "Medicina Ocupacional e Segurança do Trabalho",
        "corpo": "Olá, Nivaldo, tudo bem?\n\nTexto do e-mail.",
        "modelo": "primeiro_contato",
    }
    base.update(troca)
    return base


def mensagem(g, i=0):
    return email.message_from_bytes(g.enviadas[i][1], policy=policy.default)


# ── Modelos ──────────────────────────────────────────────────────────

class TestModelos:
    async def test_lista_os_dois_e_as_variaveis(self, db_conn, client, g):
        u, *_ = await cenario(client, db_conn)
        r = await client.get("/crm/email/modelos", headers=u["headers"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert [m["slug"] for m in body["modelos"]] == ["primeiro_contato", "proposta"]
        assert any(v["nome"] == "contato_primeiro_nome" for v in body["variaveis"])
        assert body["gmail"]["ligado"] is True
        assert body["gmail"]["remetente"] == u["email"]
        assert body["pode_editar"] is False

    async def test_tabela_vazia_cai_no_padrao_do_codigo(self, db_conn, client, g):
        """O TRUNCATE de usuarios CASCADE esvazia email_modelos no teste."""
        u, *_ = await cenario(client, db_conn)
        assert await db_conn.fetchval("SELECT count(*) FROM email_modelos") == 0
        body = (await client.get("/crm/email/modelos", headers=u["headers"])).json()
        assert body["modelos"][1]["anexa_proposta"] is True

    async def test_google_desligado_aparece(self, db_conn, client, monkeypatch):
        monkeypatch.setattr(gmail, "configurado", lambda: False)
        u, *_ = await cenario(client, db_conn)
        body = (await client.get("/crm/email/modelos", headers=u["headers"])).json()
        assert body["gmail"]["ligado"] is False
        assert body["gmail"]["problemas"]

    async def test_gestao_edita(self, db_conn, client, g):
        u, *_ = await cenario(client, db_conn)
        adm = await criar_usuario(db_conn, client, "ADM", "adm@controllermedseg.com")
        r = await client.put(
            "/crm/email/modelos/primeiro_contato",
            json={"nome": "Primeiro contato", "assunto": "Olá {{empresa}}",
                  "corpo": "{{saudacao}}, {{contato_primeiro_nome}}."},
            headers=adm["headers"],
        )
        assert r.status_code == 200, r.text
        assert r.json()["assunto"] == "Olá {{empresa}}"
        assert r.json()["atualizado_por_nome"] == "Test ADM"
        # o anexa_proposta não muda pela edição de texto
        assert r.json()["anexa_proposta"] is False
        lista = (await client.get("/crm/email/modelos", headers=u["headers"])).json()
        assert lista["modelos"][0]["assunto"] == "Olá {{empresa}}"

    async def test_operacional_nao_edita(self, db_conn, client, g):
        u, *_ = await cenario(client, db_conn)
        r = await client.put(
            "/crm/email/modelos/primeiro_contato",
            json={"nome": "X", "assunto": "Y", "corpo": "Z"}, headers=u["headers"],
        )
        assert r.status_code == 403

    async def test_variavel_desconhecida_e_422(self, db_conn, client, g):
        adm = await criar_usuario(db_conn, client, "ADM", "adm@controllermedseg.com")
        r = await client.put(
            "/crm/email/modelos/proposta",
            json={"nome": "X", "assunto": "{{cliente}}", "corpo": "Z"}, headers=adm["headers"],
        )
        assert r.status_code == 422
        assert "{{cliente}}" in r.json()["detail"]

    async def test_slug_inexistente_e_404(self, db_conn, client, g):
        adm = await criar_usuario(db_conn, client, "ADM", "adm@controllermedseg.com")
        r = await client.put(
            "/crm/email/modelos/xpto",
            json={"nome": "X", "assunto": "Y", "corpo": "Z"}, headers=adm["headers"],
        )
        assert r.status_code == 404


# ── Rascunho ─────────────────────────────────────────────────────────

class TestRascunho:
    async def test_primeiro_contato_preenchido(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn)
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"modelo": "primeiro_contato", "contato_id": ct["id"]},
            headers=u["headers"],
        )
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["para"] == ["nivaldo@nnredutores.com.br"]
        assert b["assunto"] == "Medicina Ocupacional e Segurança do Trabalho"
        assert b["corpo"].startswith("Olá, Nivaldo, tudo bem?")
        assert "Meu nome é Gabriel" in b["corpo"]
        assert b["assinatura"] is True
        assert b["avisos"] == []
        assert b["anexo_nome"] is None

    async def test_em_branco(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn)
        b = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"contato_id": ct["id"]}, headers=u["headers"],
        )).json()
        assert b["assunto"] == "" and b["corpo"] == ""
        assert b["para"] == ["nivaldo@nnredutores.com.br"]

    async def test_proposta_sem_versao_avisa(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn)
        b = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"modelo": "proposta", "contato_id": ct["id"]}, headers=u["headers"],
        )).json()
        assert any("escolha a versão" in a for a in b["avisos"])

    async def test_proposta_com_versao(self, db_conn, client, g, pdf):
        u, _, opp, ct = await cenario(client, db_conn)
        p = (await client.post(
            f"/crm/oportunidades/{opp['id']}/propostas",
            json=corpo_proposta(), headers=u["headers"],
        )).json()
        b = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"modelo": "proposta", "contato_id": ct["id"], "proposta_id": p["id"]},
            headers=u["headers"],
        )).json()
        assert b["anexo_nome"].endswith("_v1.pdf")
        assert "NN MANUTENCAO EM REDUTORES LTDA" in b["corpo"]
        assert b["avisos"] == []

    async def test_sem_pdf_no_servidor_avisa(self, db_conn, client, g, monkeypatch):
        monkeypatch.setattr(render, "libreoffice_disponivel", lambda: None)
        u, _, opp, ct = await cenario(client, db_conn)
        p = (await client.post(
            f"/crm/oportunidades/{opp['id']}/propostas",
            json=corpo_proposta(), headers=u["headers"],
        )).json()
        b = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"modelo": "proposta", "contato_id": ct["id"], "proposta_id": p["id"]},
            headers=u["headers"],
        )).json()
        assert any("LibreOffice" in a for a in b["avisos"])

    async def test_contato_sem_email_avisa(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn, email_contato=None)
        b = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"modelo": "primeiro_contato", "contato_id": ct["id"]},
            headers=u["headers"],
        )).json()
        assert b["para"] == []
        assert any("não tem e-mail" in a for a in b["avisos"])

    async def test_assinatura_ilegivel_avisa(self, db_conn, client, g):
        g.assinatura_html, g.assinatura_erro = None, "falta o escopo gmail.settings.basic."
        u, _, opp, ct = await cenario(client, db_conn)
        b = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"modelo": "primeiro_contato", "contato_id": ct["id"]},
            headers=u["headers"],
        )).json()
        assert b["assinatura"] is False
        assert any("assinatura" in a for a in b["avisos"])

    async def test_contato_de_outra_empresa_e_422(self, db_conn, client, g):
        u, _, opp, _ = await cenario(client, db_conn)
        outra = await nova_conta(client, u["headers"], cnpj="11.444.777/0001-61",
                                 razao="Outra LTDA")
        estranho = (await client.post(
            "/crm/contatos", json={"nome": "Fulano", "conta_id": outra["id"]},
            headers=u["headers"],
        )).json()
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"modelo": "primeiro_contato", "contato_id": estranho["id"]},
            headers=u["headers"],
        )
        assert r.status_code == 422

    async def test_proposta_de_outra_oportunidade_e_422(self, db_conn, client, g):
        u, conta, opp, ct = await cenario(client, db_conn)
        outra = await nova_oportunidade(client, u["headers"], conta["id"])
        p = (await client.post(
            f"/crm/oportunidades/{outra['id']}/propostas",
            json=corpo_proposta(), headers=u["headers"],
        )).json()
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails/rascunho",
            json={"modelo": "proposta", "contato_id": ct["id"], "proposta_id": p["id"]},
            headers=u["headers"],
        )
        assert r.status_code == 422


# ── Envio ────────────────────────────────────────────────────────────

class TestEnvio:
    async def test_envia_da_caixa_do_vendedor_e_grava(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn)
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"]), headers=u["headers"],
        )
        assert r.status_code == 201, r.text
        b = r.json()
        assert b["remetente_email"] == u["email"]
        assert b["remetente_nome"] == "Gabriel Lira"
        assert b["contato_nome"] == "NIVALDO PEREIRA"
        assert b["modelo_nome"] == "Primeiro contato"
        assert b["com_assinatura"] is True
        assert b["gmail_thread_id"] == "fio1"
        assert b["respondido_em"] is None

        assert len(g.enviadas) == 1
        caixa, _ = g.enviadas[0]
        assert caixa == u["email"]
        m = mensagem(g)
        assert m["From"] == f"Gabriel Lira <{u['email']}>"
        assert m["To"] == "nivaldo@nnredutores.com.br"
        assert "Assinatura do Gmail" in m.get_body(("html",)).get_content()

        lista = (await client.get(f"/crm/oportunidades/{opp['id']}/emails",
                                  headers=u["headers"])).json()
        assert [e["id"] for e in lista] == [b["id"]]

    async def test_manda_o_texto_da_tela_e_nao_o_modelo(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn)
        await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"], corpo="Texto que o vendedor reescreveu."),
            headers=u["headers"],
        )
        assert "Texto que o vendedor reescreveu." in mensagem(g).get_body(("plain",)).get_content()

    async def test_proposta_vai_em_pdf(self, db_conn, client, g, pdf):
        u, _, opp, ct = await cenario(client, db_conn)
        p = (await client.post(
            f"/crm/oportunidades/{opp['id']}/propostas",
            json=corpo_proposta(), headers=u["headers"],
        )).json()
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"], modelo="proposta", proposta_id=p["id"]),
            headers=u["headers"],
        )
        assert r.status_code == 201, r.text
        assert r.json()["proposta_versao"] == 1
        assert r.json()["anexo_nome"].endswith("_v1.pdf")
        anexos = list(mensagem(g).iter_attachments())
        assert len(anexos) == 1
        assert anexos[0].get_content() == PDF_FALSO
        assert anexos[0].get_filename() == r.json()["anexo_nome"]

    async def test_proposta_de_um_cnpj(self, db_conn, client, g, pdf):
        u, _, opp, ct = await cenario(client, db_conn)
        p = (await client.post(
            f"/crm/oportunidades/{opp['id']}/propostas",
            json=corpo_proposta(), headers=u["headers"],
        )).json()
        item = p["itens"][0]
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"], modelo="proposta", proposta_id=p["id"],
                             proposta_item_id=item["id"]),
            headers=u["headers"],
        )
        assert r.status_code == 201, r.text
        digitos = "".join(c for c in item["cnpj"] if c.isdigit())
        assert r.json()["anexo_nome"].endswith(f"_v1_{digitos}.pdf")

    async def test_sem_pdf_nao_envia(self, db_conn, client, g, monkeypatch):
        def falha(pptx):
            raise render.PdfIndisponivel("LibreOffice não está instalado.")
        monkeypatch.setattr(render, "para_pdf", falha)
        u, _, opp, ct = await cenario(client, db_conn)
        p = (await client.post(
            f"/crm/oportunidades/{opp['id']}/propostas",
            json=corpo_proposta(), headers=u["headers"],
        )).json()
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"], modelo="proposta", proposta_id=p["id"]),
            headers=u["headers"],
        )
        assert r.status_code == 503
        assert "LibreOffice" in r.json()["detail"]
        assert g.enviadas == []
        assert await db_conn.fetchval("SELECT count(*) FROM emails_enviados") == 0

    async def test_falha_do_gmail_nao_grava(self, db_conn, client, g):
        g.erro_envio = "O Google recusou o acesso ao Gmail."
        u, _, opp, ct = await cenario(client, db_conn)
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"]), headers=u["headers"],
        )
        assert r.status_code == 502
        assert r.json()["detail"] == "O Google recusou o acesso ao Gmail."
        assert await db_conn.fetchval("SELECT count(*) FROM emails_enviados") == 0

    async def test_google_desligado_e_503(self, db_conn, client, g, monkeypatch):
        monkeypatch.setattr(gmail, "configurado", lambda: False)
        u, _, opp, ct = await cenario(client, db_conn)
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"]), headers=u["headers"],
        )
        assert r.status_code == 503

    async def test_variavel_sobrando_e_422(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn)
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"], corpo="Olá {{contato_primeiro_nome}}"),
            headers=u["headers"],
        )
        assert r.status_code == 422
        assert g.enviadas == []

    async def test_endereco_invalido_e_422(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn)
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"], para=["nivaldo@"]), headers=u["headers"],
        )
        assert r.status_code == 422

    async def test_sem_assinatura_envia_igual(self, db_conn, client, g):
        g.assinatura_html, g.assinatura_erro = None, "sem escopo"
        u, _, opp, ct = await cenario(client, db_conn)
        r = await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"]), headers=u["headers"],
        )
        assert r.status_code == 201
        assert r.json()["com_assinatura"] is False

    async def test_conta_como_atividade(self, db_conn, client, g):
        from services import atividade
        assert atividade.CATALOGO[
            ("POST", "/crm/oportunidades/{oportunidade_id}/emails")
        ].rotulo == "E-mail enviado ao cliente"


# ── Resposta do cliente ──────────────────────────────────────────────

def _msg(id_, ms, de, rotulos=("INBOX",)):
    return {"id": id_, "internalDate": str(ms), "labelIds": list(rotulos),
            "payload": {"headers": [{"name": "From", "value": de}]}}


class TestVerificar:
    async def _enviado(self, client, db_conn, g):
        u, _, opp, ct = await cenario(client, db_conn)
        e = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"]), headers=u["headers"],
        )).json()
        return u, opp, e

    async def test_sem_resposta(self, db_conn, client, g):
        u, opp, e = await self._enviado(client, db_conn, g)
        g.fios["fio1"] = {"messages": [_msg("msg1", 1000, u["email"], ("SENT",))]}
        r = await client.post(f"/crm/oportunidades/{opp['id']}/emails/verificar",
                              headers=u["headers"])
        assert r.json() == {"verificados": 1, "respondidos": 0, "erros": []}
        lista = (await client.get(f"/crm/oportunidades/{opp['id']}/emails",
                                  headers=u["headers"])).json()
        assert lista[0]["verificado_em"] is not None
        assert lista[0]["respondido_em"] is None

    async def test_cliente_respondeu(self, db_conn, client, g):
        u, opp, e = await self._enviado(client, db_conn, g)
        g.fios["fio1"] = {"messages": [
            _msg("msg1", 1000, u["email"], ("SENT",)),
            _msg("r1", 1_791_300_000_000, "Nivaldo <nivaldo@nnredutores.com.br>"),
        ]}
        r = await client.post(f"/crm/oportunidades/{opp['id']}/emails/verificar",
                              headers=u["headers"])
        assert r.json()["respondidos"] == 1
        lista = (await client.get(f"/crm/oportunidades/{opp['id']}/emails",
                                  headers=u["headers"])).json()
        assert lista[0]["resposta_de"] == "Nivaldo <nivaldo@nnredutores.com.br>"
        assert lista[0]["respondido_em"] is not None
        # respondido sai da fila
        r2 = await client.post(f"/crm/oportunidades/{opp['id']}/emails/verificar",
                               headers=u["headers"])
        assert r2.json()["verificados"] == 0

    async def test_erro_vai_para_a_coluna(self, db_conn, client, g):
        u, opp, e = await self._enviado(client, db_conn, g)
        g.erro_fio = "falta o escopo gmail.metadata"
        r = await client.post(f"/crm/oportunidades/{opp['id']}/emails/verificar",
                              headers=u["headers"])
        assert r.json()["erros"] == ["falta o escopo gmail.metadata"]
        lista = (await client.get(f"/crm/oportunidades/{opp['id']}/emails",
                                  headers=u["headers"])).json()
        assert lista[0]["verificacao_erro"] == "falta o escopo gmail.metadata"

    async def test_email_antigo_sai_da_fila(self, db_conn, client, g):
        u, opp, e = await self._enviado(client, db_conn, g)
        await db_conn.execute(
            "UPDATE emails_enviados SET enviado_em = $1",
            datetime.now(timezone.utc) - timedelta(days=31),
        )
        r = await client.post(f"/crm/oportunidades/{opp['id']}/emails/verificar",
                              headers=u["headers"])
        assert r.json()["verificados"] == 0

    async def test_script_da_passada(self, db_conn, client, g, monkeypatch):
        """O script do timer usa as mesmas funções da tela."""
        from scripts import verificar_respostas_email as script
        u, opp, e = await self._enviado(client, db_conn, g)
        g.fios["fio1"] = {"messages": [
            _msg("msg1", 1000, u["email"], ("SENT",)),
            _msg("r1", 2000, "ana@cliente.com"),
        ]}
        assert await script.executar() == 0
        assert await db_conn.fetchval(
            "SELECT resposta_de FROM emails_enviados WHERE id = $1",
            uuid.UUID(e["id"]),
        ) == "ana@cliente.com"

    async def test_script_com_google_desligado_sai_limpo(self, db_conn, monkeypatch):
        from scripts import verificar_respostas_email as script
        monkeypatch.setattr(gmail, "configurado", lambda: False)
        assert await script.executar() == 0


# ── O envio como tarefa (050c) ───────────────────────────────────────

class TestTarefaDoEnvio:
    async def test_envio_vira_tarefa_concluida(self, db_conn, client, g):
        u, _, opp, ct = await cenario(client, db_conn)
        e = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"]), headers=u["headers"],
        )).json()
        assert e["tarefa_id"]
        t = await client.get(f"/crm/tarefas/{e['tarefa_id']}", headers=u["headers"])
        assert t.status_code == 200, t.text
        t = t.json()
        assert t["tipo"] == "email"
        assert t["situacao"] == "concluida"
        assert t["titulo"] == "E-mail enviado: Medicina Ocupacional e Segurança do Trabalho"
        assert t["resultado"] == "Enviado pelo HIPO para nivaldo@nnredutores.com.br"
        assert t["contato_id"] == ct["id"]
        assert t["oportunidade_id"] == opp["id"]
        # aparece na lista de tarefas da oportunidade
        lista = await client.get(
            "/crm/tarefas", params={"oportunidade_id": opp["id"]}, headers=u["headers"],
        )
        assert lista.status_code == 200, lista.text
        corpo = lista.json()
        itens = corpo["itens"] if isinstance(corpo, dict) else corpo
        assert e["tarefa_id"] in [i["id"] for i in itens]

    async def test_proposta_vira_tarefa_de_proposta(self, db_conn, client, g, pdf):
        u, _, opp, ct = await cenario(client, db_conn)
        p = (await client.post(
            f"/crm/oportunidades/{opp['id']}/propostas",
            json=corpo_proposta(), headers=u["headers"],
        )).json()
        e = (await client.post(
            f"/crm/oportunidades/{opp['id']}/emails",
            json=corpo_envio(ct["id"], modelo="proposta", proposta_id=p["id"]),
            headers=u["headers"],
        )).json()
        t = (await client.get(f"/crm/tarefas/{e['tarefa_id']}", headers=u["headers"])).json()
        assert t["tipo"] == "proposta"
        assert t["titulo"] == "Proposta v1 enviada por e-mail"
        assert "anexo " + e["anexo_nome"] in t["resultado"]

    async def test_nao_abre_nem_exige_proximo_passo(self, db_conn, client, g):
        """A tarefa nasce fechada: não mexe na contagem de abertas."""
        u, _, opp, ct = await cenario(client, db_conn)
        antes = await db_conn.fetchval(
            "SELECT count(*) FROM tarefas WHERE oportunidade_id = $1 "
            "AND concluida_em IS NULL AND cancelada_em IS NULL",
            uuid.UUID(opp["id"]),
        )
        await client.post(f"/crm/oportunidades/{opp['id']}/emails",
                          json=corpo_envio(ct["id"]), headers=u["headers"])
        depois = await db_conn.fetchval(
            "SELECT count(*) FROM tarefas WHERE oportunidade_id = $1 "
            "AND concluida_em IS NULL AND cancelada_em IS NULL",
            uuid.UUID(opp["id"]),
        )
        assert antes == depois

    async def test_falha_do_gmail_nao_cria_tarefa(self, db_conn, client, g):
        g.erro_envio = "recusado"
        u, _, opp, ct = await cenario(client, db_conn)
        await client.post(f"/crm/oportunidades/{opp['id']}/emails",
                          json=corpo_envio(ct["id"]), headers=u["headers"])
        assert await db_conn.fetchval(
            "SELECT count(*) FROM tarefas WHERE oportunidade_id = $1 AND tipo = 'email'",
            uuid.UUID(opp["id"]),
        ) == 0

    async def test_backfill_da_031(self, db_conn, client, g):
        """E-mail gravado antes da 031 (sem tarefa) ganha a tarefa ao reaplicar o bloco."""
        from pathlib import Path
        u, _, opp, ct = await cenario(client, db_conn)
        e = (await client.post(f"/crm/oportunidades/{opp['id']}/emails",
                               json=corpo_envio(ct["id"], cc=["rh@cliente.com"]),
                               headers=u["headers"])).json()
        eid = uuid.UUID(e["id"])
        await db_conn.execute("UPDATE emails_enviados SET tarefa_id = NULL WHERE id = $1", eid)
        await db_conn.execute("DELETE FROM tarefas WHERE id = $1", uuid.UUID(e["tarefa_id"]))

        sql = (Path(__file__).resolve().parent.parent / "migrations" / "031_email_tarefa.sql").read_text("utf-8")
        await db_conn.execute(sql)
        await db_conn.execute(sql)  # idempotente

        linhas = await db_conn.fetch(
            "SELECT t.* FROM tarefas t JOIN emails_enviados e ON e.tarefa_id = t.id WHERE e.id = $1",
            eid,
        )
        assert len(linhas) == 1
        t = linhas[0]
        assert t["tipo"] == "email"
        assert t["concluida_em"] is not None
        assert t["titulo"] == "E-mail enviado: Medicina Ocupacional e Segurança do Trabalho"
        assert t["resultado"] == (
            "Enviado pelo HIPO para nivaldo@nnredutores.com.br (cc rh@cliente.com)"
        )
        assert await db_conn.fetchval(
            "SELECT count(*) FROM tarefas WHERE oportunidade_id = $1 AND tipo = 'email'",
            uuid.UUID(opp["id"]),
        ) == 1
