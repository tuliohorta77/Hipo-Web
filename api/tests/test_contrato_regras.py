"""
HIPO — Regras puras do contrato (entrega 053). Sem banco, sem rede.

Rodam no pytest do Windows (sem Postgres) e no CI.
"""
import hashlib
import hmac
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from services import contrato as r
from services import proposta as pr


def _sig(papel, nome, email):
    return {"papel": papel, "nome": nome, "email": email}


QUATRO = [
    _sig("contratante", "Eladir Quadros", "eladir@portopisos.com.br"),
    _sig("testemunha_contratante", "Ana RH", "ana@portopisos.com.br"),
    _sig("contratada", "Marcelo Canton Dick", "marcelod@controllermedseg.com.br"),
    _sig("testemunha_contratada", "Bruno Gonçalo", "bruno@controllermedseg.com.br"),
]

CONTA = {
    "razao_social": "Porto Pisos Elevados Ltda.", "cnpj": "08363161000151",
    "logradouro": "Rua Maria Isabel Rezende", "numero": "206", "complemento": None,
    "bairro": "Vila Isabel", "cidade": "Guarulhos", "uf": "sp", "cep": "07111000",
}


def proposta_tabela(**troca):
    base = {
        "modalidade": "tabela",
        "tabela_preco": pr.normalizar_tabela(pr.TABELA_PADRAO),
        "valor_vida_excedente": Decimal("15.00"),
        "valor_por_vida": None,
        "itens": [{"cnpj": "08363161000151", "razao_social": "Porto Pisos Elevados Ltda.",
                   "vidas": 8, "mensalidade": Decimal("220.00"),
                   "valor_tabela": Decimal("220.00")}],
        "treinamentos": Decimal("0"), "laudos": Decimal("0"), "cidade": "Guarulhos",
    }
    base.update(troca)
    return base


class TestSignatarios:
    def test_ordem_da_minuta(self):
        out = r.validar_signatarios(list(reversed(QUATRO)))
        assert [s["papel"] for s in out] == list(r.CHAVES_PAPEIS)
        assert [s["ordem"] for s in out] == [1, 2, 3, 4]

    def test_testemunhas_assinam_como_testemunha(self):
        out = {s["papel"]: s["acao"] for s in r.validar_signatarios(QUATRO)}
        assert out["contratante"] == "SIGN"
        assert out["contratada"] == "SIGN"
        assert out["testemunha_contratante"] == "SIGN_AS_A_WITNESS"
        assert out["testemunha_contratada"] == "SIGN_AS_A_WITNESS"

    def test_email_minusculo_e_nome_aparado(self):
        [s] = [x for x in r.validar_signatarios(
            [_sig("contratante", "  Eladir   Quadros ", "ELADIR@PortoPisos.com.br")] + QUATRO[1:]
        ) if x["papel"] == "contratante"]
        assert s["nome"] == "Eladir Quadros"
        assert s["email"] == "eladir@portopisos.com.br"

    def test_falta_papel(self):
        with pytest.raises(r.ContratoInvalido, match="testemunha da contratante"):
            r.validar_signatarios([QUATRO[0], QUATRO[2], QUATRO[3]])

    def test_papel_repetido(self):
        with pytest.raises(r.ContratoInvalido, match="mais de uma"):
            r.validar_signatarios(QUATRO + [QUATRO[0]])

    def test_mesmo_email_em_dois_papeis(self):
        """Testemunha que é a própria parte não testemunha nada."""
        dup = [QUATRO[0], _sig("testemunha_contratante", "Eladir de novo",
                               "eladir@portopisos.com.br"), *QUATRO[2:]]
        with pytest.raises(r.ContratoInvalido, match="pessoa diferente"):
            r.validar_signatarios(dup)

    @pytest.mark.parametrize("email", ["", "sem-arroba", "a@b", "a b@c.com"])
    def test_email_invalido(self, email):
        with pytest.raises(r.ContratoInvalido, match="não é válido"):
            r.limpar_signatario("contratante", "Fulano", email)

    def test_nome_em_branco(self):
        with pytest.raises(r.ContratoInvalido, match="nome"):
            r.limpar_signatario("contratante", "   ", "a@b.com")

    def test_papel_desconhecido(self):
        with pytest.raises(r.ContratoInvalido):
            r.limpar_signatario("fiador", "Fulano", "a@b.com")


class TestEndereco:
    def test_formato_da_minuta(self):
        assert r.endereco_formatado(CONTA) == (
            "Rua Maria Isabel Rezende, 206, Vila Isabel – Guarulhos - SP, CEP: 07111-000"
        )

    def test_complemento_depois_do_numero(self):
        conta = dict(CONTA, complemento="Galpão 2")
        assert r.endereco_formatado(conta).startswith("Rua Maria Isabel Rezende, 206, Galpão 2,")

    def test_pendencias(self):
        conta = dict(CONTA, numero="", cep=None)
        assert r.pendencias_endereco(conta) == ["número", "CEP"]
        assert r.pendencias_endereco(CONTA) == []


class TestDatas:
    def test_data_com_dois_digitos(self):
        assert r.data_extenso(date(2026, 10, 8)) == "08 de outubro de 2026"

    def test_vigencia_no_dia_seguinte(self):
        assert r.inicio_vigencia_padrao(date(2026, 10, 8)) == date(2026, 10, 9)

    def test_vigencia_antes_do_contrato(self):
        with pytest.raises(r.ContratoInvalido, match="antes"):
            r.validar_datas(date(2026, 10, 8), date(2026, 10, 7), 10)

    def test_vigencia_longe_demais(self):
        with pytest.raises(r.ContratoInvalido, match="6 meses"):
            r.validar_datas(date(2026, 10, 8), date(2027, 6, 1), 10)

    @pytest.mark.parametrize("dia", [0, 29, 31])
    def test_dia_de_vencimento(self, dia):
        with pytest.raises(r.ContratoInvalido, match="vencimento"):
            r.validar_datas(date(2026, 10, 8), date(2026, 10, 9), dia)


class TestPreco:
    def test_tabela_como_na_minuta(self):
        linhas = r.linhas_preco(proposta_tabela())
        assert linhas[0] == "CNPJs até 05 funcionários registrados – R$ 180,00 mensais;"
        assert linhas[1] == "CNPJs entre 06 e 10 funcionários registrados – R$ 220,00 mensais;"
        assert linhas[-1] == ("CNPJs acima de 20 funcionários registrados – R$ 15,00 "
                              "por funcionário/mês excedente.")

    def test_excedente_escolhido_pelo_ev(self):
        linhas = r.linhas_preco(proposta_tabela(valor_vida_excedente=Decimal("12.50")))
        assert "R$ 12,50 por funcionário/mês excedente" in linhas[-1]

    def test_cnpj_com_desconto_ganha_linha(self):
        """A tabela sozinha cobraria a mais de quem negociou abaixo dela."""
        item = {"cnpj": "11222333000181", "razao_social": "Filial Ltda.", "vidas": 3,
                "mensalidade": Decimal("150.00"), "valor_tabela": Decimal("180.00")}
        p = proposta_tabela(itens=proposta_tabela()["itens"] + [item])
        linhas = r.linhas_preco(p)
        assert linhas[-1] == ("Valor negociado para Filial Ltda. (CNPJ 11.222.333/0001-81), "
                              "com até 03 funcionários registrados – R$ 150,00 mensais.")

    def test_por_vida(self):
        p = proposta_tabela(modalidade="por_vida", valor_por_vida=Decimal("20.00"))
        assert r.linhas_preco(p) == ["R$ 20,00 por funcionário registrado/mês."]

    def test_treinamentos_e_laudos(self):
        p = proposta_tabela(modalidade="por_vida", valor_por_vida=Decimal("20"),
                            treinamentos=Decimal("2000"), laudos=Decimal("1000"))
        linhas = r.linhas_preco(p)
        assert linhas[1].startswith("Treinamentos: R$ 2.000,00 (valor único")
        assert linhas[2].startswith("Laudos: R$ 1.000,00") and linhas[2].endswith(".")

    def test_preco_so_dos_cnpjs_do_contrato(self):
        """Contrato de um grupo não traz o desconto de CNPJ de outro grupo."""
        outro = {"cnpj": "11222333000181", "razao_social": "Outra Ltda.", "vidas": 3,
                 "mensalidade": Decimal("150.00"), "valor_tabela": Decimal("180.00")}
        p = proposta_tabela(itens=proposta_tabela()["itens"] + [outro])
        linhas = r.linhas_preco(p, proposta_tabela()["itens"])
        assert not any("Outra Ltda." in l for l in linhas)

    def test_treinamentos_so_no_grupo_principal(self):
        p = proposta_tabela(modalidade="por_vida", valor_por_vida=Decimal("20"),
                            treinamentos=Decimal("2000"))
        assert any(l.startswith("Treinamentos") for l in r.linhas_preco(p, com_extras=True))
        assert not any(l.startswith("Treinamentos") for l in r.linhas_preco(p, com_extras=False))

    def test_campos(self):
        simples, listas = r.campos(proposta=proposta_tabela(), conta=CONTA,
                                   itens_grupo=proposta_tabela()["itens"],
                                   data_contrato=date(2026, 10, 8),
                                   inicio_vigencia=date(2026, 10, 9), dia_vencimento=5)
        assert set(simples) == set(r.CAMPOS_SIMPLES)
        assert set(listas) == set(r.CAMPOS_LISTA)
        assert simples["CONTRATANTE_CNPJ"] == "08.363.161/0001-51"
        assert simples["CONTRATANTE_DEMAIS"] == ""
        assert simples["DIA_VENCIMENTO"] == "05"
        assert simples["INICIO_VIGENCIA"] == "09 de outubro de 2026"
        assert listas["ANEXO_TITULO"] == [] and listas["ANEXO_LINHA"] == []
        assert listas["SUBSTITUICAO"] == [] and listas["SERVICO_EXTRA"] == []


def _item(cnpj, razao, vidas=5, mensal="180.00"):
    return {"cnpj": cnpj, "razao_social": razao, "vidas": vidas,
            "mensalidade": Decimal(mensal), "valor_tabela": Decimal(mensal)}


class TestGrupos:
    """Matriz e filiais (mesma raiz) juntas; raízes diferentes, separadas."""

    def test_raiz(self):
        assert r.raiz("42.385.626/0002-94") == "42385626"
        assert r.eh_matriz("42385626000103") and not r.eh_matriz("42385626000294")

    def test_matriz_vira_contratante_mesmo_vindo_depois(self):
        itens = [_item("42385626000294", "Filial 1"), _item("42385626000103", "Matriz"),
                 _item("42385626000375", "Filial 2")]
        [g] = r.agrupar_itens(itens)
        assert g["raiz"] == "42385626"
        assert g["contratante"]["razao_social"] == "Matriz"
        assert [i["razao_social"] for i in g["itens"]] == ["Matriz", "Filial 1", "Filial 2"]

    def test_raizes_diferentes_viram_contratos_diferentes(self):
        """Mesmo sendo do mesmo grupo econômico (caso Unique): sempre separado."""
        itens = [_item("20371142000133", "Unique"), _item("46601592000146", "Auto Super"),
                 _item("20371142000214", "Unique Filial")]
        grupos = r.agrupar_itens(itens)
        assert [g["raiz"] for g in grupos] == ["20371142", "46601592"]
        assert len(grupos[0]["itens"]) == 2 and len(grupos[1]["itens"]) == 1

    def test_sem_matriz_o_primeiro_e_contratante(self):
        [g] = r.agrupar_itens([_item("42385626000294", "F1"), _item("42385626000375", "F2")])
        assert g["contratante"]["razao_social"] == "F1"

    def test_grupo_da_raiz_inexistente(self):
        with pytest.raises(r.ContratoInvalido):
            r.grupo_da_raiz([_item("42385626000103", "M")], "99999999")

    def test_anexo_1(self):
        itens = [_item("42385626000103", "M Foods"), _item("42385626000294", "MFO1 Trattoria"),
                 _item("42385626000375", "MFO2 Steak")]
        titulo, linhas = r.linhas_anexo(itens, {"42385626000294": "Rua Itapeva, 569"})
        assert titulo[0].startswith("ANEXO 1")
        assert linhas == ["MFO1 Trattoria – CNPJ 42.385.626/0002-94 – Rua Itapeva, 569;",
                          "MFO2 Steak – CNPJ 42.385.626/0003-75."]
        assert r.texto_demais(itens).startswith(", e demais CNPJs")
        assert r.linhas_anexo(itens[:1]) == ([], [])
        assert r.texto_demais(itens[:1]) == ""

    def test_substituicao(self):
        assert r.linhas_substituicao([]) == []
        [l] = r.linhas_substituicao([{"data_contrato": date(2026, 10, 8)}])
        assert "substitui integralmente" in l and "o contrato firmado" in l and "08/10/2026" in l
        [l] = r.linhas_substituicao([{"data_contrato": date(2025, 1, 2)},
                                     {"data_contrato": date(2026, 10, 8)}])
        assert "os contratos firmados" in l and "02/01/2025, 08/10/2026" in l


class TestServicos:
    def test_sugeridos_pelo_escopo(self):
        escopo = ["PGR - (NR-01)", "Laudo de Insalubridade - NR15", "Laudo Ergonômico – NR17",
                  "CIPA (Comissão Interna)", "PPP (Perfil Profissiográfico Previdenciário)"]
        assert r.servicos_sugeridos(escopo) == ["ppp", "ergonomia", "insalubridade", "cipa"]
        # O escopo padrão só tem o básico do modelo (LTCAT cita a NR-15, mas
        # é o item 2.4, não o laudo de insalubridade).
        assert r.servicos_sugeridos(pr.ESCOPO_PADRAO) == []
        assert r.servicos_sugeridos(None) == []

    def test_numeracao_continua_a_clausula_2(self):
        linhas = r.linhas_servicos(["cipa", "ppp"], ["Treinamento de NR-35 ", " "])
        assert linhas[0].startswith("2.7) Elaboração do PPP")
        assert linhas[1].startswith("2.8) CIPA")
        assert linhas[2] == "2.9) Treinamento de NR-35;"

    def test_chave_desconhecida(self):
        with pytest.raises(r.ContratoInvalido, match="desconhecido"):
            r.linhas_servicos(["xpto"])

    def test_limites_das_linhas_livres(self):
        with pytest.raises(r.ContratoInvalido):
            r.linhas_servicos([], ["x"] * (r.MAX_SERVICOS_LIVRES + 1))
        with pytest.raises(r.ContratoInvalido):
            r.linhas_servicos([], ["x" * (r.MAX_TEXTO_SERVICO + 1)])


class TestNomes:
    def test_nome_do_documento(self):
        assert r.nome_documento("OPP-0042", "Porto Pisos", 1) == \
            "Contrato Controller MedSeg - Porto Pisos (OPP-0042)"
        assert r.nome_documento("OPP-0042", "Porto Pisos", 2).endswith(" v2")

    def test_nome_do_arquivo_sem_acento(self):
        assert r.nome_arquivo("OPP-0042", "Ação & Cia Ltda.", 1, assinado=True) == \
            "CONTRATO_OPP-0042_ACAO_CIA_LTDA_v1_assinado.pdf"


class TestLeituraDaAutentique:
    def test_parse_data_sem_fuso_e_utc(self):
        d = r.parse_data("2026-10-08 12:56:01")
        assert d == datetime(2026, 10, 8, 12, 56, 1, tzinfo=timezone.utc)
        assert r.parse_data("2026-10-08T12:56:01.000Z").tzinfo is not None
        assert r.parse_data(None) is None
        assert r.parse_data("lixo") is None

    def test_situacoes(self):
        assert r.situacao_signatario({})["situacao"] == r.SIG_PENDENTE
        assert r.situacao_signatario(
            {"viewed": {"created_at": "2026-10-08 10:00:00"}})["situacao"] == r.SIG_VISUALIZADO
        assinado = r.situacao_signatario({
            "viewed": {"created_at": "2026-10-08 10:00:00"},
            "signed": {"created_at": "2026-10-08 10:05:00"},
        })
        assert assinado["situacao"] == r.SIG_ASSINADO
        assert assinado["assinado_em"].minute == 5
        recusado = r.situacao_signatario({
            "signed": None, "rejected": {"created_at": "2026-10-08 11:00:00",
                                         "reason": " valor errado "},
        })
        assert recusado["situacao"] == r.SIG_RECUSADO
        assert recusado["motivo_recusa"] == "valor errado"

    def test_falha_de_entrega_so_antes_de_abrir(self):
        falhou = r.situacao_signatario({"email_events": {"refused": "2026-10-08"}})
        assert falhou["situacao"] == r.SIG_FALHA
        abriu = r.situacao_signatario({"email_events": {"refused": "x"},
                                       "viewed": {"created_at": "2026-10-08 10:00:00"}})
        assert abriu["situacao"] == r.SIG_VISUALIZADO

    def test_status_do_contrato(self):
        A, P, X = r.SIG_ASSINADO, r.SIG_PENDENTE, r.SIG_RECUSADO
        assert r.status_do_contrato([A, A, A, A], "enviado") == "assinado"
        assert r.status_do_contrato([A, P, P, P], "enviado") == "enviado"
        assert r.status_do_contrato([A, X, P, P], "enviado") == "recusado"
        assert r.status_do_contrato([A, A, A, A], "cancelado") == "cancelado"
        assert r.status_do_contrato([], "enviado") == "enviado"

    def test_casar_por_public_id_e_por_email(self):
        sigs = [{"id": 1, "autentique_public_id": "p1", "email": "a@x.com"},
                {"id": 2, "autentique_public_id": None, "email": "B@x.com"},
                {"id": 3, "autentique_public_id": None, "email": "c@x.com"}]
        assinaturas = [{"public_id": "p1", "email": "outro@x.com"},
                       {"public_id": "p2", "user": {"email": "b@x.com"}}]
        casados = r.casar_assinaturas(sigs, assinaturas)
        assert casados[1]["public_id"] == "p1"
        assert casados[2]["public_id"] == "p2"
        assert 3 not in casados

    def test_proximo_a_assinar(self):
        sigs = [{"ordem": 2, "situacao": "pendente", "nome": "B"},
                {"ordem": 1, "situacao": "assinado", "nome": "A"}]
        assert r.proximo_a_assinar(sigs)["nome"] == "B"
        assert r.proximo_a_assinar([{"ordem": 1, "situacao": "assinado"}]) is None


class TestWebhook:
    def test_hmac_sobre_o_corpo_cru(self):
        corpo = b'{"event": {"id": "e1"}}'
        assinatura = hmac.new(b"segredo", corpo, hashlib.sha256).hexdigest()
        assert r.assinatura_webhook_valida("segredo", corpo, assinatura)
        assert r.assinatura_webhook_valida("segredo", corpo, assinatura.upper())
        assert not r.assinatura_webhook_valida("segredo", corpo + b" ", assinatura)
        assert not r.assinatura_webhook_valida("outro", corpo, assinatura)
        assert not r.assinatura_webhook_valida("", corpo, assinatura)
        assert not r.assinatura_webhook_valida("segredo", corpo, None)

    def test_evento_de_documento(self):
        ev = r.ler_evento({"id": "w1", "event": {"id": "e1", "type": "document.finished",
                                                  "data": {"id": "doc-1"}}})
        assert ev == {"id": "e1", "tipo": "document.finished", "documento_id": "doc-1"}

    def test_evento_de_assinatura(self):
        ev = r.ler_evento({"event": {"id": "e2", "type": "signature.accepted",
                                     "data": {"public_id": "p", "document": "doc-2"}}})
        assert ev["documento_id"] == "doc-2"
        ev = r.ler_evento({"event": {"id": "e3", "type": "signature.viewed",
                                     "data": {"object": {"document": {"id": "doc-3"}}}}})
        assert ev["documento_id"] == "doc-3"

    def test_evento_sem_documento(self):
        assert r.ler_evento({"event": {"type": "member.created", "data": {}}})["documento_id"] is None



class TestAviso:
    def test_destinatarios(self):
        out = r.destinatarios_aviso(
            "Fat@X.com, contratos@x.com;adm@x.com fat@x.com lixo ev@x.com", "EV@x.com")
        assert out == ["fat@x.com", "contratos@x.com", "adm@x.com"]
        assert r.destinatarios_aviso("") == []
        assert r.destinatarios_aviso(None) == []

    def test_link(self):
        assert r.url_oportunidade("", "", "abc") == \
            "https://hipogestao.com.br/crm/oportunidades?abrir=abc"
        assert r.url_oportunidade("https://mos.hipogestao.com.br/", "MOS", "abc") == \
            "https://mos.hipogestao.com.br/crm/oportunidades?abrir=abc"
        assert r.url_oportunidade("", "MOS", "abc") is None

    def test_corpo(self):
        p = proposta_tabela(mensalidade=Decimal("220.00"))
        contrato = {"data_contrato": date(2026, 10, 8), "inicio_vigencia": date(2026, 10, 9),
                    "dia_vencimento": 5, "hash_original": "f" * 64,
                    "assinado_em": datetime(2026, 10, 8, 15, 30, tzinfo=timezone.utc)}
        sigs = [dict(s, ordem=i + 1, assinado_em=None) for i, s in enumerate(QUATRO)]
        corpo = r.corpo_aviso(razao_social="Porto Pisos Elevados Ltda.", cnpj="08363161000151",
                              numero_oportunidade="OPP-1", executivo_nome="Bruno",
                              proposta=p, contrato=contrato, signatarios=sigs, link=None)
        assert "Porto Pisos Elevados Ltda. — CNPJ 08.363.161/0001-51" in corpo
        assert "8 vidas — R$ 220,00/mês" in corpo
        assert "Mensalidade total deste contrato: R$ 220,00" in corpo
        assert "Vencimento: todo dia 05" in corpo
        # Horário de Brasília.
        assert "Assinado por todos em: 08/10/2026 12:30" in corpo
        assert "Abrir no HIPO" not in corpo

    def test_assunto(self):
        assert r.assunto_aviso("Porto Pisos ", "OPP-1") == "Contrato assinado — Porto Pisos (OPP-1)"
