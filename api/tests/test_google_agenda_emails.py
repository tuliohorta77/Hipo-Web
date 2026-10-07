"""
HIPO — Lista de convidados enviada ao Google.

O Google recusa o evento INTEIRO com 400 "Invalid attendee email" por um
único endereço ruim. A lista que sai daqui é a última barreira: precisa
separar campos com vários endereços (cadastro antigo "a@x; b@y") e não
repetir ninguém.
"""
from datetime import datetime, timedelta

from services import google_agenda
from services.agenda import FUSO_OPERACAO


def _dados(anfitriao="consultor@hipo.com", convidados=None):
    inicio = datetime(2026, 10, 8, 9, 0, tzinfo=FUSO_OPERACAO)
    return google_agenda.DadosEvento(
        titulo="Teste",
        inicio=inicio,
        fim=inicio + timedelta(minutes=30),
        anfitriao_email=anfitriao,
        convidados=convidados or [],
    )


class TestEmails:
    def test_campo_com_dois_enderecos_vira_dois_convidados(self):
        d = _dados(convidados=["kethlleen@wprado.com.br; financeiro@wprado.com.br"])
        assert google_agenda._emails(d) == [
            "consultor@hipo.com",
            "kethlleen@wprado.com.br",
            "financeiro@wprado.com.br",
        ]

    def test_virgula_tambem_separa(self):
        d = _dados(convidados=["a@x.com, b@y.com"])
        assert google_agenda._emails(d)[1:] == ["a@x.com", "b@y.com"]

    def test_sem_repetido_entre_campos(self):
        d = _dados(convidados=["Consultor@hipo.com", "a@x.com; A@X.com", "a@x.com"])
        assert google_agenda._emails(d) == ["consultor@hipo.com", "a@x.com"]

    def test_vazio_e_none_ignorados(self):
        d = _dados(convidados=["", "  ", "a@x.com"])
        assert google_agenda._emails(d) == ["consultor@hipo.com", "a@x.com"]

    def test_corpo_nao_leva_separador_em_nenhum_attendee(self):
        d = _dados(convidados=["a@x.com;b@y.com"])
        attendees = google_agenda._corpo(d)["attendees"]
        assert [a["email"] for a in attendees] == [
            "consultor@hipo.com", "a@x.com", "b@y.com",
        ]
