"""
HIPO — services/google_meet.py contra uma sessão HTTP de mentira.

Não fala com o Google: `_sessao` é trocada por um objeto que responde
como a Meet REST API responde (formato da documentação v2). O que se
testa é a NOSSA parte: as URLs, o filtro, a paginação, o updateMask, a
leitura dos campos e a tradução dos erros.
"""
import json

import pytest

from services import google_meet
from services.transcricao import Conferencia, Transcricao, data_do_google


class Resp:
    def __init__(self, status=200, corpo=None):
        self.status_code = status
        self._corpo = corpo or {}
        self.text = json.dumps(self._corpo)
        self.content = self.text.encode()

    def json(self):
        return self._corpo


class Sessao:
    """Responde por (método, url, pageToken)."""

    def __init__(self, rotas):
        self.rotas = rotas
        self.pedidos = []

    def request(self, metodo, url, timeout=None, params=None, json=None):
        self.pedidos.append({"metodo": metodo, "url": url, "params": params, "json": json})
        chave = (metodo, url, (params or {}).get("pageToken"))
        r = self.rotas.get(chave) or self.rotas.get((metodo, url, None))
        if r is None:
            return Resp(404, {"error": {"message": "not found"}})
        return r


@pytest.fixture
def ligado(monkeypatch):
    monkeypatch.setattr(google_meet, "configurado", lambda: True)
    monkeypatch.setattr(google_meet, "problemas", lambda: [])

    def instalar(sessao):
        escopos = []

        def fabrica(email, escopo):
            escopos.append((email, escopo))
            return sessao
        monkeypatch.setattr(google_meet, "_sessao", fabrica)
        return escopos
    return instalar


B = google_meet.BASE


class TestLigar:
    async def test_resolve_o_codigo_e_liga_so_a_transcricao(self, ligado):
        s = Sessao({
            ("GET", f"{B}/spaces/abc-defg-hij", None): Resp(200, {"name": "spaces/XyZ"}),
            ("PATCH", f"{B}/spaces/XyZ", None): Resp(200, {"name": "spaces/XyZ"}),
        })
        escopos = ligado(s)
        r = await google_meet.ligar_transcricao("ana@x.com", "abc-defg-hij")
        assert r.ok and r.erro is None
        patch = s.pedidos[1]
        # Ate o campo final: so ate transcriptionConfig o Google devolve 400.
        assert patch["params"] == {
            "updateMask": "config.artifactConfig.transcriptionConfig.autoTranscriptionGeneration"}
        assert patch["json"] == {"config": {"artifactConfig": {
            "transcriptionConfig": {"autoTranscriptionGeneration": "ON"}}}}
        # Só o escopo de configuração: pedir mais derrubaria o token inteiro.
        assert escopos == [("ana@x.com", google_meet.ESCOPO_CONFIG)]

    async def test_delegacao_sem_escopo_vira_frase(self, ligado):
        s = Sessao({("GET", f"{B}/spaces/abc-defg-hij", None):
                    Resp(401, {"error": "unauthorized_client"})})
        ligado(s)
        r = await google_meet.ligar_transcricao("ana@x.com", "abc-defg-hij")
        assert not r.ok
        assert "meetings.space.settings" in r.erro

    async def test_desligado(self, monkeypatch):
        monkeypatch.setattr(google_meet, "configurado", lambda: False)
        r = await google_meet.ligar_transcricao("a@b", "abc-defg-hij")
        assert not r.ok and "não configurada" in r.erro


class TestLevantar:
    async def test_filtra_pela_sala_pagina_e_le_as_transcricoes(self, ligado):
        url = f"{B}/conferenceRecords"
        s = Sessao({
            ("GET", url, None): Resp(200, {
                "conferenceRecords": [{"name": "conferenceRecords/c1",
                                       "startTime": "2026-09-24T12:00:00Z",
                                       "endTime": "2026-09-24T12:31:00.5Z"}],
                "nextPageToken": "p2"}),
            ("GET", url, "p2"): Resp(200, {
                "conferenceRecords": [{"name": "conferenceRecords/c2",
                                       "startTime": "2026-09-24T12:40:00Z"},
                                      {"name": "sem-inicio"}]}),
            ("GET", f"{B}/conferenceRecords/c1/transcripts", None): Resp(200, {
                "transcripts": [{"name": "conferenceRecords/c1/transcripts/t1",
                                 "state": "FILE_GENERATED",
                                 "docsDestination": {"exportUri": "https://docs/x"}}]}),
            ("GET", f"{B}/conferenceRecords/c2/transcripts", None): Resp(200, {}),
        })
        escopos = ligado(s)
        lev = await google_meet.levantar("ana@x.com", "abc-defg-hij")
        assert lev.erro is None
        assert s.pedidos[0]["params"]["filter"] == 'space.meeting_code = "abc-defg-hij"'
        assert [c.nome for c in lev.conferencias] == ["conferenceRecords/c1", "conferenceRecords/c2"]
        c1, c2 = lev.conferencias
        assert c1.fim == data_do_google("2026-09-24T12:31:00.5Z")
        assert c1.transcricoes == (Transcricao("conferenceRecords/c1/transcripts/t1",
                                               "FILE_GENERATED", "https://docs/x"),)
        assert c2.fim is None and c2.transcricoes == ()
        assert {e for _, e in escopos} == {google_meet.ESCOPO_LEITURA}

    async def test_api_desabilitada(self, ligado):
        ligado(Sessao({("GET", f"{B}/conferenceRecords", None):
                       Resp(403, {"error": {"status": "PERMISSION_DENIED",
                                            "details": ["SERVICE_DISABLED"]}})}))
        lev = await google_meet.levantar("a@b", "abc-defg-hij")
        assert "Meet REST API" in lev.erro


class TestBaixar:
    async def test_resolve_nomes_e_idioma(self, ligado):
        conf = Conferencia(
            nome="conferenceRecords/c1",
            inicio=data_do_google("2026-09-24T12:00:00Z"),
            fim=data_do_google("2026-09-24T12:30:00Z"),
            transcricoes=(Transcricao("conferenceRecords/c1/transcripts/t1",
                                      "FILE_GENERATED", "https://docs/x"),),
        )
        s = Sessao({
            ("GET", f"{B}/conferenceRecords/c1/participants", None): Resp(200, {
                "participants": [
                    {"name": "conferenceRecords/c1/participants/p1",
                     "signedinUser": {"displayName": "Ana Vendas"}},
                    {"name": "conferenceRecords/c1/participants/p2",
                     "anonymousUser": {"displayName": "Carlos Cliente"}},
                ]}),
            ("GET", f"{B}/conferenceRecords/c1/transcripts/t1/entries", None): Resp(200, {
                "transcriptEntries": [
                    {"participant": "conferenceRecords/c1/participants/p1",
                     "text": "Bom dia", "languageCode": "pt-BR",
                     "startTime": "2026-09-24T12:01:00Z", "endTime": "2026-09-24T12:01:05Z"},
                    {"participant": "conferenceRecords/c1/participants/p9",
                     "text": "Oi", "languageCode": "pt-BR",
                     "startTime": "2026-09-24T12:02:00Z"},
                    {"participant": "x", "text": "sem hora"},
                ]}),
        })
        ligado(s)
        d = await google_meet.baixar("ana@x.com", (conf,))
        assert d.erro is None
        assert [(f.participante, f.texto) for f in d.falas] == [
            ("Ana Vendas", "Bom dia"), ("Participante", "Oi"),
        ]
        assert d.idioma == "pt-BR"
        assert d.documento_url == "https://docs/x"
        assert d.conferencias == ("conferenceRecords/c1",)

    async def test_erro_no_meio_devolve_erro_sem_falas(self, ligado):
        conf = Conferencia("conferenceRecords/c1", data_do_google("2026-09-24T12:00:00Z"),
                           None, (Transcricao("conferenceRecords/c1/transcripts/t1", "ENDED"),))
        ligado(Sessao({("GET", f"{B}/conferenceRecords/c1/participants", None):
                       Resp(429, {})}))
        d = await google_meet.baixar("a@b", (conf,))
        assert d.falas == () and "Limite" in d.erro
