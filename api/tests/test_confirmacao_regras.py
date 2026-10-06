"""
HIPO — Regras puras da confirmação da véspera (029).

Sem banco: rodam no Windows sem Postgres. O que só aparece com banco está
em test_crm_confirmacao_vespera.py.

Datas fixas de outubro/2026: 12/10 (segunda) é Nossa Senhora Aparecida,
o que dá um feriado de verdade para os casos de dia não útil.
"""
from datetime import date, datetime, timezone

from services import confirmacao as regras
from services.tarefa import FUSO_OPERACAO as SP


def em(dia, hora=9, minuto=0):
    return datetime(2026, 10, dia, hora, minuto, tzinfo=SP)


class TestDiaUtilAnterior:
    def test_meio_da_semana_e_o_dia_anterior(self):
        assert regras.dia_util_anterior(date(2026, 10, 8)) == date(2026, 10, 7)

    def test_segunda_confirma_na_sexta(self):
        assert regras.dia_util_anterior(date(2026, 10, 19)) == date(2026, 10, 16)

    def test_pula_o_feriado(self):
        # Terça 13/10, com a segunda 12/10 feriado: confirma na sexta 09/10.
        assert regras.dia_util_anterior(
            date(2026, 10, 13), [date(2026, 10, 12)]
        ) == date(2026, 10, 9)


class TestPrazoDaConfirmacao:
    def test_dois_dias_uteis_de_folga_cria_na_vespera_as_nove(self):
        # Marcada na terça 06/10 para a quinta 08/10: confirma quarta 07/10.
        prazo = regras.prazo_da_confirmacao(em(8, 14), em(6, 17))
        assert prazo == datetime(2026, 10, 7, 9, 0, tzinfo=SP)

    def test_marcada_na_vespera_nao_cria(self):
        # Marcada na quarta para a quinta: a véspera é hoje.
        assert regras.prazo_da_confirmacao(em(8, 14), em(7, 8)) is None

    def test_marcada_para_amanha_cedo_nao_cria(self):
        assert regras.prazo_da_confirmacao(em(8, 8), em(7, 18)) is None

    def test_segunda_marcada_na_quinta_confirma_na_sexta(self):
        prazo = regras.prazo_da_confirmacao(em(19, 10), em(15, 11))
        assert prazo == datetime(2026, 10, 16, 9, 0, tzinfo=SP)

    def test_segunda_marcada_na_sexta_nao_cria(self):
        assert regras.prazo_da_confirmacao(em(19, 10), em(16, 11)) is None

    def test_feriado_na_vespera_empurra_para_tras(self):
        prazo = regras.prazo_da_confirmacao(
            em(13, 10), em(7, 11), [date(2026, 10, 12)]
        )
        assert prazo == datetime(2026, 10, 9, 9, 0, tzinfo=SP)

    def test_feriado_pode_tirar_a_folga(self):
        # Terça 13/10 marcada na sexta 09/10: sem o feriado a véspera seria
        # a segunda; com ele, é a própria sexta.
        assert regras.prazo_da_confirmacao(
            em(13, 10), em(9, 11), [date(2026, 10, 12)]
        ) is None

    def test_o_dia_de_hoje_e_o_de_brasilia_e_nao_o_de_utc(self):
        """
        Terça 23:30 em Brasília já é quarta em UTC. Comparando em UTC, a
        reunião de quinta marcada na terça à noite perderia a confirmação.
        """
        agora_utc = datetime(2026, 10, 6, 23, 30, tzinfo=SP).astimezone(
            timezone.utc
        )
        prazo = regras.prazo_da_confirmacao(em(8, 10), agora_utc)
        assert prazo == datetime(2026, 10, 7, 9, 0, tzinfo=SP)


class TestTexto:
    def test_dia_seguinte_e_amanha(self):
        assert regras.dia_por_extenso(em(8, 10), date(2026, 10, 7)) == "amanhã"

    def test_na_sexta_para_segunda_diz_o_dia(self):
        assert regras.dia_por_extenso(em(19, 10), date(2026, 10, 16)) == "segunda"

    def test_feriado_no_meio_diz_o_dia(self):
        assert regras.dia_por_extenso(em(13, 10), date(2026, 10, 9)) == "terça"

    def test_mensagem_do_roteiro(self):
        msg = regras.mensagem_confirmacao(
            contato_nome="Nivaldo Pereira", inicio=em(8, 9, 30),
            vespera=date(2026, 10, 7), anfitriao_nome="Jakeline Santana",
            modalidade="online",
        )
        assert msg == (
            "Nivaldo, tudo certo para amanhã às 09:30 com Jakeline? "
            "O link está no convite. Qualquer coisa, me avisa por aqui."
        )

    def test_presencial_fala_do_endereco(self):
        msg = regras.mensagem_confirmacao(
            contato_nome="Ana", inicio=em(19, 14), vespera=date(2026, 10, 16),
            anfitriao_nome="Bruno", modalidade="presencial",
        )
        assert msg.startswith("Ana, tudo certo para segunda às 14:00 com Bruno?")
        assert "O endereço está no convite." in msg

    def test_sem_contato_e_sem_anfitriao_nao_deixa_buraco(self):
        msg = regras.mensagem_confirmacao(
            contato_nome=None, inicio=em(8, 9), vespera=date(2026, 10, 7),
            anfitriao_nome=None, modalidade="online",
        )
        assert msg.startswith("Tudo certo para amanhã às 09:00?")

    def test_descricao_leva_a_mensagem_e_o_que_fazer(self):
        d = regras.descricao_confirmacao("Oi?")
        assert '"Oi?"' in d
        assert "conclua esta tarefa" in d
        assert "edite a reunião" in d

    def test_titulo(self):
        assert regras.titulo_confirmacao(
            empresa="Metalurgica Alfa", inicio=em(8, 9, 30)
        ) == "Confirmar reunião 08/10 09:30 - Metalurgica Alfa"
        assert len(regras.titulo_confirmacao(empresa="X" * 400, inicio=em(8))) == 200
