"""
HIPO — Regras puras do e-mail comercial (050). Sem banco, sem rede: rodam
no pytest local do Windows.
"""
import email
from datetime import date, datetime, timezone
from decimal import Decimal
from email import policy
from pathlib import Path

import pytest

from services import email_comercial as r
from services import gmail


def _vals(**troca):
    base = dict(
        agora=datetime(2026, 10, 6, 17, 0, tzinfo=timezone.utc),  # 14h BRT
        contato_nome="NIVALDO PEREIRA",
        razao_social="NN MANUTENCAO EM REDUTORES LTDA",
        nome_fantasia="NN Redutores",
        cnpj_formatado="06.335.181/0001-93",
        remetente_nome="Gabriel Lira",
        remetente_telefone="(11) 91100-5646",
        nossa_empresa="Controller MedSeg",
    )
    base.update(troca)
    return r.valores(**base)


class TestModelosPadrao:
    def test_os_dois_modelos_existem(self):
        assert set(r.MODELOS_PADRAO) == set(r.SLUGS)

    @pytest.mark.parametrize("slug", r.SLUGS)
    def test_padrao_passa_na_propria_validacao(self, slug):
        m = r.MODELOS_PADRAO[slug]
        r.validar_modelo(m["nome"], m["assunto"], m["corpo"])

    def test_so_o_de_proposta_anexa(self):
        assert r.MODELOS_PADRAO["proposta"]["anexa_proposta"] is True
        assert r.MODELOS_PADRAO["primeiro_contato"]["anexa_proposta"] is False

    @pytest.mark.parametrize("slug", r.SLUGS)
    def test_semente_da_migration_igual_ao_codigo(self, slug, db_free_sql):
        """
        A migration semeia o banco; o código vale quando a tabela está vazia.
        Se os dois divergirem, a base nova e a de produção mandam textos
        diferentes sem ninguém perceber.
        """
        m = r.MODELOS_PADRAO[slug]
        assert m["corpo"] in db_free_sql[slug]["corpo"]
        assert m["assunto"] == db_free_sql[slug]["assunto"]


@pytest.fixture(scope="module")
def db_free_sql():
    """Lê a semente da 030 sem banco: desfaz os E'...' || da migration."""
    import re
    sql = (Path(__file__).resolve().parent.parent / "migrations" / "030_emails.sql").read_text("utf-8")
    bloco = sql.split("INSERT INTO email_modelos", 1)[1]
    saida = {}
    for slug in r.SLUGS:
        trecho = bloco.split(f"'{slug}',", 1)[1].split("\n)", 1)[0]
        literais = re.findall(r"E?'((?:[^']|'')*)'", trecho)
        # [nome, assunto, corpo em pedaços..., ] -> FALSE/ordem não são literais
        nome, assunto, *corpo = literais
        texto = "".join(corpo).replace("\\n", "\n").replace("''", "'")
        saida[slug] = {"nome": nome, "assunto": assunto, "corpo": texto}
    return saida


class TestValidarModelo:
    def test_variavel_desconhecida_recusa(self):
        with pytest.raises(r.EmailInvalido, match="desconhecida"):
            r.validar_modelo("X", "Oi {{cliente}}", "corpo")

    def test_chave_mal_fechada_recusa(self):
        with pytest.raises(r.EmailInvalido, match="mal escrita"):
            r.validar_modelo("X", "Oi", "Olá {{contato_nome}")

    @pytest.mark.parametrize("campo", ["nome", "assunto", "corpo"])
    def test_vazio_recusa(self, campo):
        dados = {"nome": "X", "assunto": "A", "corpo": "C"}
        dados[campo] = "   "
        with pytest.raises(r.EmailInvalido):
            r.validar_modelo(**dados)

    def test_aceita_espaco_dentro_da_chave(self):
        r.validar_modelo("X", "{{ empresa }}", "{{saudacao}}")


class TestValores:
    def test_saudacao_pela_hora_de_brasilia(self):
        assert _vals()["saudacao"] == "Boa tarde"
        assert _vals(agora=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc))["saudacao"] == "Bom dia"
        assert _vals(agora=datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc))["saudacao"] == "Boa noite"

    def test_primeiro_nome_sem_caixa_alta(self):
        v = _vals()
        assert v["contato_primeiro_nome"] == "Nivaldo"
        assert v["remetente_primeiro_nome"] == "Gabriel"

    def test_empresa_e_a_fantasia_e_cai_na_razao(self):
        assert _vals()["empresa"] == "NN Redutores"
        assert _vals(nome_fantasia=None)["empresa"] == "NN MANUTENCAO EM REDUTORES LTDA"

    def test_sem_proposta_as_variaveis_ficam_vazias(self):
        v = _vals()
        assert v["proposta_mensalidade"] == v["proposta_vidas"] == v["proposta_validade"] == ""

    def test_proposta_formatada(self):
        v = _vals(proposta={"mensalidade": Decimal("1270"), "vidas": 70,
                            "validade": date(2026, 10, 16)})
        assert v["proposta_mensalidade"] == "R$ 1.270,00"
        assert v["proposta_vidas"] == "70"
        assert v["proposta_validade"] == "16/10/2026"

    def test_moeda_grande(self):
        assert r._moeda(Decimal("1234567.5")) == "R$ 1.234.567,50"

    def test_toda_variavel_tem_valor_e_rotulo_de_ausencia(self):
        v = _vals()
        assert set(v) == r.NOMES_VARIAVEIS
        assert set(r.ROTULO_AUSENTE) | {"saudacao", "nossa_empresa"} == r.NOMES_VARIAVEIS


class TestPreencher:
    def test_modelo_de_primeiro_contato(self):
        m = r.MODELOS_PADRAO["primeiro_contato"]
        p = r.preencher(m["corpo"], _vals())
        assert p.texto.startswith("Olá, Nivaldo, tudo bem?")
        assert "Meu nome é Gabriel" in p.texto
        assert "{{" not in p.texto
        assert p.ausentes == []

    def test_modelo_de_proposta(self):
        m = r.MODELOS_PADRAO["proposta"]
        vals = _vals()
        assert r.preencher(m["assunto"], vals).texto == "Proposta comercial Controller MedSeg — NN Redutores"
        corpo = r.preencher(m["corpo"], vals).texto
        assert corpo.startswith("Boa tarde, Nivaldo, tudo bem?")
        assert "proposta comercial para a NN MANUTENCAO EM REDUTORES LTDA." in corpo

    def test_contato_sem_nome_vira_aviso_e_tira_a_virgula_orfa(self):
        p = r.preencher("Olá, {{contato_primeiro_nome}}, tudo bem?", _vals(contato_nome=None))
        assert p.texto == "Olá, tudo bem?"
        assert r.avisos_de_ausencia(p.ausentes) == ["O contato não tem nome no cadastro."]

    def test_variavel_inexistente_levanta(self):
        with pytest.raises(r.EmailInvalido):
            r.preencher("{{xpto}}", _vals())

    def test_avisos_nao_repetem(self):
        assert len(r.avisos_de_ausencia(
            ["proposta_mensalidade", "proposta_vidas", "proposta_validade"]
        )) == 1


class TestValidarEnvio:
    def _ok(self, **troca):
        base = dict(para=["ana@cliente.com"], cc=[], assunto="Oi", corpo="Texto",
                    remetente_email="gabriel@controllermedseg.com")
        base.update(troca)
        return r.validar_envio(**base)

    def test_ok(self):
        e = self._ok()
        assert e.para == ["ana@cliente.com"] and e.assunto == "Oi"

    def test_endereco_invalido(self):
        with pytest.raises(r.EmailInvalido, match="inválido"):
            self._ok(para=["ana@cliente"])

    def test_sem_destinatario(self):
        with pytest.raises(r.EmailInvalido):
            self._ok(para=["  "])

    def test_deduplica_por_minuscula_e_tira_cc_repetido(self):
        e = self._ok(para=["Ana@Cliente.com", "ana@cliente.com"],
                     cc=["ANA@cliente.com", "rh@cliente.com"])
        assert e.para == ["Ana@Cliente.com"]
        assert e.cc == ["rh@cliente.com"]

    def test_teto_de_destinatarios(self):
        with pytest.raises(r.EmailInvalido, match="No máximo"):
            self._ok(para=[f"p{i}@x.com" for i in range(r.MAX_DESTINATARIOS + 1)])

    def test_variavel_sobrando_recusa(self):
        with pytest.raises(r.EmailInvalido, match="variável"):
            self._ok(corpo="Olá {{contato_primeiro_nome}}")

    def test_nao_manda_para_si_mesmo(self):
        with pytest.raises(r.EmailInvalido, match="você mesmo"):
            self._ok(para=["Gabriel@ControllerMedSeg.com"])

    def test_assunto_em_uma_linha(self):
        assert self._ok(assunto="Proposta\n  comercial").assunto == "Proposta comercial"


class TestMensagem:
    def _msg(self, **kw):
        envio = r.Envio(["ana@cliente.com"], ["rh@cliente.com"], "Proposta",
                        "Olá, Ana.\n\nSegue <anexo>.\nAt.te")
        bruto = r.montar_mensagem(
            remetente_nome="Gabriel Lira", remetente_email="gabriel@controllermedseg.com",
            envio=envio, **kw,
        )
        return email.message_from_bytes(bruto, policy=policy.default)

    def test_cabecalhos(self):
        m = self._msg()
        assert m["From"] == "Gabriel Lira <gabriel@controllermedseg.com>"
        assert m["To"] == "ana@cliente.com"
        assert m["Cc"] == "rh@cliente.com"
        assert m["Subject"] == "Proposta"

    def test_html_escapado_e_com_paragrafos(self):
        html = self._msg().get_body(("html",)).get_content()
        assert "&lt;anexo&gt;" in html
        assert html.count("<p ") == 2
        assert "Segue &lt;anexo&gt;.<br>At.te" in html

    def test_assinatura_no_html_e_no_texto(self):
        m = self._msg(assinatura_html="<div>Gabriel Lira<br>Executivo Comercial</div>")
        assert 'class="gmail_signature"' in m.get_body(("html",)).get_content()
        texto = m.get_body(("plain",)).get_content()
        assert "-- \nGabriel Lira\nExecutivo Comercial" in texto

    def test_anexo_pdf(self):
        m = self._msg(anexo=r.Anexo("OPP-1_v1.pdf", b"%PDF-1.4 teste"))
        anexos = list(m.iter_attachments())
        assert len(anexos) == 1
        assert anexos[0].get_filename() == "OPP-1_v1.pdf"
        assert anexos[0].get_content_type() == "application/pdf"
        assert anexos[0].get_content() == b"%PDF-1.4 teste"

    def test_mensagem_grande_demais(self, monkeypatch):
        monkeypatch.setattr(r, "MAX_MENSAGEM_BYTES", 100)
        with pytest.raises(r.EmailInvalido, match="35 MB"):
            self._msg()


def _m(id_, quando, de, rotulos=("INBOX",)):
    return {"id": id_, "internalDate": str(quando), "labelIds": list(rotulos),
            "payload": {"headers": [{"name": "From", "value": de}]}}


class TestDetectarResposta:
    EU = "gabriel@controllermedseg.com"

    def test_sem_resposta(self):
        fio = {"messages": [_m("a", 1000, self.EU, ("SENT",))]}
        assert r.detectar_resposta(fio, "a", self.EU) is None

    def test_resposta_do_cliente(self):
        fio = {"messages": [
            _m("a", 1000, self.EU, ("SENT",)),
            _m("b", 5000, "Ana <ana@cliente.com>"),
        ]}
        resp = r.detectar_resposta(fio, "a", self.EU)
        assert resp is not None
        assert resp.de == "Ana <ana@cliente.com>"
        assert resp.em == datetime.fromtimestamp(5, tz=timezone.utc)

    def test_followup_do_proprio_vendedor_nao_conta(self):
        fio = {"messages": [
            _m("a", 1000, self.EU, ("SENT",)),
            _m("b", 2000, f"Gabriel <{self.EU.upper()}>", ("INBOX",)),
            _m("c", 3000, self.EU, ("SENT",)),
        ]}
        assert r.detectar_resposta(fio, "a", self.EU) is None

    def test_mensagem_anterior_a_nossa_nao_conta(self):
        fio = {"messages": [
            _m("x", 500, "ana@cliente.com"),
            _m("a", 1000, self.EU, ("SENT",)),
        ]}
        assert r.detectar_resposta(fio, "a", self.EU) is None

    def test_rascunho_nao_conta(self):
        fio = {"messages": [
            _m("a", 1000, self.EU, ("SENT",)),
            _m("b", 2000, "ana@cliente.com", ("DRAFT",)),
        ]}
        assert r.detectar_resposta(fio, "a", self.EU) is None

    def test_pega_a_primeira_resposta(self):
        fio = {"messages": [
            _m("a", 1000, self.EU, ("SENT",)),
            _m("c", 9000, "rh@cliente.com"),
            _m("b", 4000, "ana@cliente.com"),
        ]}
        assert r.detectar_resposta(fio, "a", self.EU).de == "ana@cliente.com"

    def test_nossa_mensagem_sumiu_do_fio(self):
        fio = {"messages": [_m("b", 4000, "ana@cliente.com")]}
        assert r.detectar_resposta(fio, "a", self.EU) is None


class TestGmailTraducao:
    def test_escopo_faltando(self):
        assert "gmail.send" in gmail.traduzir(None, "unauthorized_client", gmail.ESCOPO_ENVIO)

    def test_usuario_fora_do_workspace(self):
        assert "Workspace" in gmail.traduzir(400, "invalid_grant", gmail.ESCOPO_ENVIO)

    def test_assinatura_do_endereco_certo(self):
        lista = {"sendAs": [
            {"sendAsEmail": "alias@x.com", "signature": "ALIAS"},
            {"sendAsEmail": "eu@x.com", "isPrimary": True, "signature": "<b>EU</b>"},
        ]}
        assert gmail.escolher_assinatura(lista, "EU@x.com") == "<b>EU</b>"
        assert gmail.escolher_assinatura(lista, "outro@x.com") == "<b>EU</b>"
        assert gmail.escolher_assinatura({}, "eu@x.com") is None


class TestTarefaDoEnvio:
    def test_email(self):
        t = r.tarefa_do_envio(assunto="  Oi   tudo ", para=["a@x.com", "b@x.com"])
        assert (t.tipo, t.titulo) == ("email", "E-mail enviado: Oi tudo")
        assert t.resultado == "Enviado pelo HIPO para a@x.com, b@x.com"

    def test_proposta(self):
        t = r.tarefa_do_envio(assunto="x", para=["a@x.com"], anexo_nome="P.pdf",
                              proposta_versao=3)
        assert (t.tipo, t.titulo) == ("proposta", "Proposta v3 enviada por e-mail")
        assert t.resultado.endswith("· anexo P.pdf")

    def test_titulo_cabe_na_coluna(self):
        assert len(r.tarefa_do_envio(assunto="a" * 400, para=["a@x.com"]).titulo) == 200
