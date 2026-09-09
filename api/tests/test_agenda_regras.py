"""
HIPO — Regras puras da agenda (services/agenda.py).

Sem banco e sem relógio: tudo que depende de tempo recebe o instante como
parâmetro. É o que permite testar "11:45 ancora nas 11:30" e "12:10 não
ancora em lugar nenhum" sem mockar `datetime.now`.
"""
from datetime import date, datetime, time

import pytest

from services import agenda as regras
from services.agenda import AgendaInvalida


def em(ano, mes, dia, hora, minuto=0):
    """Instante no fuso da operação — é assim que a grade pensa."""
    return datetime(ano, mes, dia, hora, minuto, tzinfo=regras.FUSO_OPERACAO)


# 2026-09-07 é uma SEGUNDA; 09-11, a sexta da mesma semana.
SEG = date(2026, 9, 7)
SEX = date(2026, 9, 11)
SAB = date(2026, 9, 12)
DOM = date(2026, 9, 13)


# ── A grade ──────────────────────────────────────────────────────────

class TestSlots:
    def test_manha_vai_das_8_as_1130(self):
        manha = [s for s in regras.SLOTS if s < time(12, 0)]
        assert manha[0] == time(8, 0)
        assert manha[-1] == time(11, 30)

    def test_tarde_vai_das_13_as_1730(self):
        tarde = [s for s in regras.SLOTS if s >= time(12, 0)]
        assert tarde[0] == time(13, 0)
        assert tarde[-1] == time(17, 30)

    def test_sao_dezoito_slots(self):
        """8 de manhã + 10 de tarde. Se este número mudar, a altura da
        coluna da grade muda junto e a tela volta a rolar."""
        assert len(regras.SLOTS) == 18

    def test_passo_de_trinta_minutos(self):
        for anterior, seguinte in zip(regras.SLOTS, regras.SLOTS[1:]):
            delta = (
                datetime.combine(date(2000, 1, 1), seguinte)
                - datetime.combine(date(2000, 1, 1), anterior)
            ).total_seconds() / 60
            # 90 minutos é o salto do almoço (11:30 -> 13:00); todo o resto
            # tem que ser exatamente um passo.
            assert delta in (30, 90)

    def test_almoco_nao_e_slot(self):
        """O intervalo é AUSÊNCIA de slot, não slot vazio: é o que faz a
        coluna do dia caber na tela sem rolar."""
        for hora in (time(12, 0), time(12, 30)):
            assert hora not in regras.SLOTS

    def test_estao_em_ordem(self):
        assert list(regras.SLOTS) == sorted(regras.SLOTS)

    def test_slots_devolve_a_mesma_tupla(self):
        assert regras.slots() == regras.SLOTS


class TestSlotCanonico:
    def test_em_cima_do_slot(self):
        assert regras.eh_slot_canonico(em(2026, 9, 8, 9, 0))

    def test_desalinhado_nao_e_canonico(self):
        assert not regras.eh_slot_canonico(em(2026, 9, 8, 9, 15))

    def test_no_almoco_nao_e_canonico(self):
        assert not regras.eh_slot_canonico(em(2026, 9, 8, 12, 0))

    def test_fora_da_grade_e_o_complemento(self):
        assert regras.fora_da_grade(em(2026, 9, 8, 9, 15))
        assert not regras.fora_da_grade(em(2026, 9, 8, 9, 0))


class TestSlotAncora:
    """
    Em que LINHA da grade a reunião é desenhada. O horário específico que o
    SDR pode digitar precisa cair em algum lugar visível — sumir seria pior
    que aparecer fora do lugar.
    """

    @pytest.mark.parametrize("hora,minuto,esperado", [
        (9, 0, time(9, 0)),      # em cima
        (9, 15, time(9, 0)),     # dentro da janela do slot
        (9, 29, time(9, 0)),     # último minuto da janela
        (9, 30, time(9, 30)),    # já é o próximo slot
        (11, 45, time(11, 30)),  # a janela do último slot da manhã vai até 12:00
        (17, 45, time(17, 30)),  # idem para o último da tarde, até 18:00
    ])
    def test_ancora_no_slot_que_contem(self, hora, minuto, esperado):
        assert regras.slot_ancora(em(2026, 9, 8, hora, minuto)) == esperado

    @pytest.mark.parametrize("hora,minuto", [
        (7, 30),   # antes do expediente
        (12, 0),   # almoço, em cima da hora
        (12, 10),  # almoço, no meio
        (18, 0),   # depois do último slot
        (23, 0),
    ])
    def test_fora_dos_blocos_nao_ancora(self, hora, minuto):
        assert regras.slot_ancora(em(2026, 9, 8, hora, minuto)) is None

    def test_almoco_nao_e_empurrado_para_o_slot_das_1130(self):
        """
        A regressão que a checagem de janela existe para impedir: sem ela,
        12:10 seria ancorado às 11:30 e a reunião do almoço apareceria
        empilhada com a das 11:30, sem nenhuma relação entre as duas.
        """
        assert regras.slot_ancora(em(2026, 9, 8, 12, 10)) != time(11, 30)


class TestFuso:
    def test_ingenuo_e_tratado_como_fuso_da_operacao(self):
        """
        É o que o formulário manda quando o navegador não carimba fuso.
        Tratado como UTC, 09:00 viraria 06:00 e a reunião nasceria fora da
        grade — a mesma classe de bug que a situação da tarefa já enfrentou.
        """
        assert regras.eh_slot_canonico(datetime(2026, 9, 8, 9, 0))

    def test_utc_e_convertido(self):
        """12:00 UTC é 09:00 em Brasília (UTC-3): slot da grade."""
        from datetime import timezone
        assert regras.eh_slot_canonico(datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc))

    def test_no_fuso_e_publico(self):
        """O router usa esta função; ela não pode voltar a ser privada."""
        assert regras.no_fuso(em(2026, 9, 8, 9, 0)).hour == 9


# ── Conflito ─────────────────────────────────────────────────────────

class TestConflito:
    def test_sobreposicao_parcial_conflita(self):
        a1, a2 = em(2026, 9, 8, 9, 0), em(2026, 9, 8, 10, 0)
        b1, b2 = em(2026, 9, 8, 9, 30), em(2026, 9, 8, 10, 30)
        assert regras.conflitam(a1, a2, b1, b2)

    def test_encaixe_perfeito_nao_conflita(self):
        """
        09:00–09:30 e 09:30–10:00 convivem. Comparar com `<=` recusaria a
        agenda cheia — justamente o dia que se quer poder marcar.
        """
        a1, a2 = em(2026, 9, 8, 9, 0), em(2026, 9, 8, 9, 30)
        b1, b2 = em(2026, 9, 8, 9, 30), em(2026, 9, 8, 10, 0)
        assert not regras.conflitam(a1, a2, b1, b2)

    def test_contida_conflita(self):
        a1, a2 = em(2026, 9, 8, 9, 0), em(2026, 9, 8, 11, 0)
        b1, b2 = em(2026, 9, 8, 9, 30), em(2026, 9, 8, 10, 0)
        assert regras.conflitam(a1, a2, b1, b2)

    def test_separadas_nao_conflitam(self):
        a1, a2 = em(2026, 9, 8, 9, 0), em(2026, 9, 8, 9, 30)
        b1, b2 = em(2026, 9, 8, 14, 0), em(2026, 9, 8, 14, 30)
        assert not regras.conflitam(a1, a2, b1, b2)

    def test_e_simetrico(self):
        a1, a2 = em(2026, 9, 8, 9, 0), em(2026, 9, 8, 10, 0)
        b1, b2 = em(2026, 9, 8, 9, 30), em(2026, 9, 8, 10, 30)
        assert regras.conflitam(a1, a2, b1, b2) == regras.conflitam(b1, b2, a1, a2)


class TestFimDe:
    def test_soma_a_duracao(self):
        assert regras.fim_de(em(2026, 9, 8, 9, 0), 30) == em(2026, 9, 8, 9, 30)

    def test_atravessa_a_hora(self):
        assert regras.fim_de(em(2026, 9, 8, 9, 30), 90) == em(2026, 9, 8, 11, 0)


# ── A semana ─────────────────────────────────────────────────────────

class TestSemana:
    @pytest.mark.parametrize("dia", [
        date(2026, 9, 7), date(2026, 9, 9), date(2026, 9, 11),
        date(2026, 9, 12), date(2026, 9, 13),
    ])
    def test_qualquer_dia_cai_na_mesma_segunda(self, dia):
        """
        É o que faz a seta de navegação e um link colado abrirem a mesma
        tela. Sábado e domingo pertencem à semana que acabou de passar.
        """
        assert regras.segunda_da_semana(dia) == SEG

    def test_cinco_dias_de_segunda_a_sexta(self):
        assert regras.dias_da_semana(date(2026, 9, 9)) == [
            date(2026, 9, d) for d in (7, 8, 9, 10, 11)
        ]

    def test_janela_vai_de_segunda_a_sabado(self):
        inicio, fim = regras.janela_da_semana(date(2026, 9, 9))
        assert inicio.date() == SEG and inicio.hour == 0
        assert fim.date() == SAB and fim.hour == 0

    def test_janela_e_meia_aberta(self):
        """
        Fechar em sexta 23:59:59 perderia o que caiu no último segundo do
        dia. Mesma escolha de services/tarefa.janela_utc.
        """
        _, fim = regras.janela_da_semana(SEG)
        ultimo_instante_da_sexta = datetime(
            2026, 9, 11, 23, 59, 59, tzinfo=regras.FUSO_OPERACAO
        )
        assert ultimo_instante_da_sexta < fim

    def test_janela_alcanca_reuniao_fora_do_expediente(self):
        """
        O recorte é da CONSULTA, não do expediente: uma reunião das 19h
        precisa aparecer na semana dela. Recorte que esconde dado é a mesma
        armadilha do registro invisível no sábado.
        """
        inicio, fim = regras.janela_da_semana(SEG)
        assert inicio <= em(2026, 9, 10, 19, 0) < fim

    def test_rotulo_do_dia(self):
        assert regras.rotulo_dia(SEG) == "seg"
        assert regras.rotulo_dia(SEX) == "sex"


class TestDiaDaSemana:
    @pytest.mark.parametrize("dia", [7, 8, 9, 10, 11])
    def test_dia_util_passa(self, dia):
        assert regras.validar_dia_da_semana(em(2026, 9, dia, 9, 0)) is not None

    @pytest.mark.parametrize("dia", [12, 13])
    def test_fim_de_semana_e_recusado(self, dia):
        """
        Não é rigor de expediente: a grade tem cinco colunas, e uma reunião
        no sábado existiria no banco, sairia no convite do cliente e seria
        invisível na única tela que promete mostrar a semana.
        """
        with pytest.raises(AgendaInvalida, match="segunda a sexta"):
            regras.validar_dia_da_semana(em(2026, 9, dia, 9, 0))


# ── Validações ───────────────────────────────────────────────────────

class TestDuracao:
    @pytest.mark.parametrize("minutos", [5, 30, 90, 480])
    def test_aceita_a_faixa(self, minutos):
        assert regras.validar_duracao(minutos) == minutos

    @pytest.mark.parametrize("minutos", [0, 4, 481, 600])
    def test_recusa_fora_da_faixa(self, minutos):
        with pytest.raises(AgendaInvalida):
            regras.validar_duracao(minutos)

    def test_recusa_none(self):
        with pytest.raises(AgendaInvalida):
            regras.validar_duracao(None)


class TestModalidade:
    @pytest.mark.parametrize("m", ["online", "presencial"])
    def test_aceita(self, m):
        assert regras.validar_modalidade(m) == m

    def test_recusa_desconhecida(self):
        with pytest.raises(AgendaInvalida, match="Modalidade inválida"):
            regras.validar_modalidade("hibrida")

    def test_sigla_de_cada_modalidade(self):
        assert regras.SIGLA_MODALIDADE["online"] == "ON"
        assert regras.SIGLA_MODALIDADE["presencial"] == "PRES"


class TestConvidados:
    def test_limpa_espaco_e_vazio(self):
        assert regras.normalizar_convidados(
            [" ana@x.com ", "", "   ", "bruno@y.com"]
        ) == ["ana@x.com", "bruno@y.com"]

    def test_deduplica_ignorando_caixa(self):
        """
        O Google recusa o evento INTEIRO com 400 quando o mesmo endereço
        aparece duas vezes — e "Ana@x.com" digitado à mão ao lado de
        "ana@x.com" vindo do cadastro é exatamente como isso acontece.
        """
        assert regras.normalizar_convidados(
            ["Ana@X.com", "ana@x.com"]
        ) == ["Ana@X.com"]

    def test_preserva_a_ordem_digitada(self):
        entrada = ["zeca@x.com", "ana@x.com", "bruno@x.com"]
        assert regras.normalizar_convidados(entrada) == entrada

    @pytest.mark.parametrize("ruim", [
        "sem-arroba", "sem@dominio", "com espaco@x.com", "a@b,c.com", "@x.com",
    ])
    def test_recusa_endereco_malformado(self, ruim):
        with pytest.raises(AgendaInvalida, match="inválido"):
            regras.normalizar_convidados([ruim])

    def test_recusa_acima_do_teto(self):
        muitos = [f"p{i}@x.com" for i in range(regras.MAX_CONVIDADOS + 1)]
        with pytest.raises(AgendaInvalida, match="No máximo"):
            regras.normalizar_convidados(muitos)

    def test_none_vira_lista_vazia(self):
        assert regras.normalizar_convidados(None) == []


# ── O rótulo ─────────────────────────────────────────────────────────

class TestRotulo:
    def test_formato_da_planilha(self):
        assert regras.rotulo(
            sigla_tipo="CF", empresa="XPTO",
            anfitriao="Bruno Gonçalo", modalidade="online",
        ) == "CF - XPTO (Bruno) - ON"

    def test_presencial(self):
        assert regras.rotulo(
            sigla_tipo="CF", empresa="XPTO 2",
            anfitriao="Jakeline Santana", modalidade="presencial",
        ) == "CF - XPTO 2 (Jakeline) - PRES"

    def test_sem_tipo_nao_deixa_separador_solto(self):
        """
        Reunião sem tipo é comum — a lista é esvaziada pelo TRUNCATE do
        conftest e pode estar incompleta em produção. Um rótulo " - XPTO"
        faria a tela parecer quebrada por um campo que o sistema aceita
        vazio.
        """
        texto = regras.rotulo(
            sigla_tipo=None, empresa="XPTO",
            anfitriao="Bruno", modalidade="online",
        )
        assert texto == "XPTO (Bruno) - ON"
        assert not texto.startswith(" -")

    def test_sem_empresa_e_sem_anfitriao_sobra_a_modalidade(self):
        assert regras.rotulo(
            sigla_tipo=None, empresa=None, anfitriao=None, modalidade="online",
        ) == "ON"

    def test_nunca_devolve_vazio_com_modalidade_valida(self):
        """
        Garante o contrato de `_titulo_padrao`: o CHECK ck_tarefa_titulo
        devolveria 500 num título em branco.
        """
        for m in regras.MODALIDADES:
            assert regras.rotulo(
                sigla_tipo=None, empresa="", anfitriao="", modalidade=m,
            ).strip() != ""

    def test_empresa_longa_e_cortada_com_reticencias(self):
        """
        Corte seco faria "CONTROLLER SERVICOS" e "CONTROLLER SERVIÇOS
        MEDICOS" virarem o mesmo texto, e o vendedor abriria a reunião
        errada.
        """
        texto = regras.rotulo(
            sigla_tipo="CF",
            empresa="CONTROLLER SERVICOS MEDICOS OCUPACIONAIS DO BRASIL LTDA",
            anfitriao="Bruno", modalidade="online",
        )
        assert "…" in texto
        assert len(texto) < 70

    def test_usa_so_o_primeiro_nome(self):
        assert regras.primeiro_nome("Bruno Gonçalo da Silva") == "Bruno"
        assert regras.primeiro_nome("") == ""
        assert regras.primeiro_nome(None) == ""


# ── O convite que o CLIENTE recebe ───────────────────────────────────
#
# Outro leitor, outro formato. O caso de referência abaixo foi copiado de
# um convite real da operação — o que estes testes travam não é uma
# preferência de estilo, é o desenho que a equipe e os clientes já leem.

REAL = {
    "razao_social": "NN MANUTENCAO EM REDUTORES E USINAGEM LTDA",
    "cnpj": "06335181000193",
    "tipo_nome": "Apresentação",
}


class TestTituloDoEvento:
    def test_reproduz_o_convite_real(self):
        assert regras.titulo_evento(**REAL) == (
            "NN MANUTENCAO EM REDUTORES E USINAGEM LTDA 06.335.181/0001-93"
            " | Apresentação Controller MedSeg"
        )

    def test_usa_razao_social_e_nao_fantasia(self):
        """
        Na agenda do cliente este texto vive ao lado de compromissos de
        outras empresas: o nome do contrato é o que ele reconhece.
        """
        assert "NN MANUTENCAO" in regras.titulo_evento(**REAL)

    def test_cnpj_sai_pontuado(self):
        assert "06.335.181/0001-93" in regras.titulo_evento(**REAL)

    def test_sem_tipo_nao_deixa_separador_solto(self):
        texto = regras.titulo_evento(
            razao_social="Alfa LTDA", cnpj="11222333000181", tipo_nome=None,
        )
        assert texto == "Alfa LTDA 11.222.333/0001-81 | Controller MedSeg"
        assert "|  " not in texto

    def test_sem_cnpj_nao_deixa_espaco_duplo(self):
        texto = regras.titulo_evento(
            razao_social="Alfa LTDA", cnpj=None, tipo_nome="Apresentação",
        )
        assert texto == "Alfa LTDA | Apresentação Controller MedSeg"

    def test_e_diferente_do_rotulo_da_grade(self):
        """
        Dois leitores, dois formatos. Se um dia estes dois textos voltarem a
        ser o mesmo, ou o cliente recebe uma sigla que não entende, ou a
        célula da grade recebe um parágrafo.
        """
        curto = regras.rotulo(
            sigla_tipo="AP", empresa="NN Manutencao",
            anfitriao="Jakeline Santana", modalidade="online",
        )
        assert curto != regras.titulo_evento(**REAL)


class TestDescricaoDoEvento:
    def _completa(self, **troca):
        base = dict(
            titulo=regras.titulo_evento(**REAL),
            inicio=em(2026, 9, 9, 9, 30),
            modalidade="online",
            contato_nome="Nivaldo",
            contato_telefone="(11) 99947-7607",
            contato_email="ADM.Nnredutores@gmail.com",
            anfitriao_nome="Jakeline Santana",
            anfitriao_telefone="(11) 94251-9976",
        )
        base.update(troca)
        return regras.descricao_evento(**base)

    def test_reproduz_o_convite_real(self):
        assert self._completa() == (
            "NN MANUTENCAO EM REDUTORES E USINAGEM LTDA 06.335.181/0001-93"
            " | Apresentação Controller MedSeg\n"
            "09/09 às 09:30\n"
            "ONLINE\n"
            "Contato: Nivaldo\n"
            "Cel: (11) 99947-7607\n"
            "Email: ADM.Nnredutores@gmail.com\n"
            "Consultor: Jakeline Santana\n"
            "Cel: (11) 94251-9976"
        )

    def test_repete_a_data_no_corpo(self):
        """
        Não é redundância: o cliente encaminha o convite por WhatsApp, e no
        encaminhamento sobra o texto, não o campo de horário do evento.
        """
        assert "09/09 às 09:30" in self._completa()

    def test_modalidade_em_caixa_alta(self):
        assert "\nONLINE\n" in self._completa()
        assert "\nPRESENCIAL\n" in self._completa(modalidade="presencial")

    def test_campo_vazio_some_em_vez_de_virar_travessao(self):
        """
        "Cel: —" no convite do cliente parece cadastro pela metade, e esta é
        a única peça do módulo que uma pessoa de fora lê.
        """
        texto = self._completa(contato_telefone=None, anfitriao_telefone="")
        assert "Cel:" not in texto
        assert "—" not in texto
        assert "Contato: Nivaldo" in texto

    def test_endereco_entra_quando_presencial(self):
        texto = self._completa(
            modalidade="presencial", endereco="Av. Paulista, 1000 — São Paulo"
        )
        assert "PRESENCIAL\nAv. Paulista, 1000" in texto

    def test_observacoes_vao_para_o_fim(self):
        texto = self._completa(observacoes="Levar o cartão CNPJ assinado.")
        assert texto.endswith("Levar o cartão CNPJ assinado.")

    def test_nao_vaza_vocabulario_interno(self):
        """
        Número de oportunidade, fase e temperatura são nossos. O cliente vê
        tudo o que estiver aqui.
        """
        texto = self._completa()
        for interno in ("OPP-", "oportunidade", "temperatura", "funil"):
            assert interno.lower() not in texto.lower()

    def test_hora_sai_no_fuso_da_operacao(self):
        """
        Montado a partir de um instante UTC, o corpo tem que dizer a hora de
        Brasília — é ela que o cliente vai ler.
        """
        from datetime import timezone
        texto = regras.descricao_evento(
            titulo="x",
            inicio=datetime(2026, 9, 9, 12, 30, tzinfo=timezone.utc),
            modalidade="online",
        )
        assert "09/09 às 09:30" in texto


# ── O desfecho ───────────────────────────────────────────────────────
#
# Três resultados, e a fronteira entre os dois últimos é uma régua de
# relógio: 24h de antecedência. O que a pessoa registra ganha da dedução —
# a dedução só entra quando ninguém registrou nada.

from datetime import timedelta


class TestAntecedencia:
    def test_conta_horas_antes_do_inicio(self):
        inicio = em(2026, 9, 10, 14, 0)
        assert regras.antecedencia_horas(inicio, em(2026, 9, 10, 11, 0)) == 3.0

    def test_negativa_quando_o_aviso_veio_depois(self):
        """
        O cliente que simplesmente não apareceu, e o vendedor registrou às
        14h20 uma reunião das 14h. Cai em no-show pela própria conta, sem
        precisar de uma regra separada para "não apareceu".
        """
        inicio = em(2026, 9, 10, 14, 0)
        assert regras.antecedencia_horas(inicio, em(2026, 9, 10, 14, 20)) < 0

    def test_normaliza_ingenuo_e_com_fuso_do_mesmo_jeito(self):
        """
        Três horas é exatamente a distância entre BRT e UTC — e exatamente
        a distância que separa um cancelamento de um no-show numa véspera.
        Misturar as duas normalizações produziria a classificação errada
        sem erro nenhum aparecer.
        """
        from datetime import timezone
        inicio_ingenuo = datetime(2026, 9, 10, 14, 0)
        inicio_utc = datetime(2026, 9, 10, 17, 0, tzinfo=timezone.utc)
        momento = em(2026, 9, 10, 11, 0)
        assert (
            regras.antecedencia_horas(inicio_ingenuo, momento)
            == regras.antecedencia_horas(inicio_utc, momento)
            == 3.0
        )


class TestDesfechoPeloRelogio:
    def test_muito_antes_e_cancelamento(self):
        inicio = em(2026, 9, 10, 14, 0)
        assert regras.desfecho_pelo_relogio(inicio, em(2026, 9, 7, 9, 0)) == "cancelada"

    def test_em_cima_da_hora_e_no_show(self):
        inicio = em(2026, 9, 10, 14, 0)
        assert regras.desfecho_pelo_relogio(inicio, em(2026, 9, 10, 12, 0)) == "no_show"

    def test_exatamente_24h_conta_como_cancelamento(self):
        """
        A régua é "com 24h OU MAIS", e quem avisou no limite avisou dentro
        dele. Um `>` no lugar do `>=` transformaria o aviso pontual em
        falta — e é o tipo de erro que só aparece na reclamação de alguém.
        """
        inicio = em(2026, 9, 10, 14, 0)
        assert regras.desfecho_pelo_relogio(inicio, em(2026, 9, 9, 14, 0)) == "cancelada"

    def test_um_minuto_depois_do_limite_e_no_show(self):
        inicio = em(2026, 9, 10, 14, 0)
        assert regras.desfecho_pelo_relogio(inicio, em(2026, 9, 9, 14, 1)) == "no_show"

    def test_depois_da_hora_e_no_show(self):
        inicio = em(2026, 9, 10, 14, 0)
        assert regras.desfecho_pelo_relogio(inicio, em(2026, 9, 10, 14, 20)) == "no_show"

    def test_o_limite_e_parametrizavel_para_teste(self):
        """
        A constante é 24h e assim fica. O parâmetro existe para o teste
        provar a fronteira sem depender do valor de produção — mesmo padrão
        de `hoje: date | None` nas regras de negócio do projeto.
        """
        inicio = em(2026, 9, 10, 14, 0)
        assert regras.desfecho_pelo_relogio(
            inicio, em(2026, 9, 10, 12, 0), limite_horas=1
        ) == "cancelada"


class TestDesfechoEfetivo:
    INICIO = em(2026, 9, 10, 14, 0)

    def test_o_registrado_ganha_de_tudo(self):
        """
        É o dado de melhor qualidade que existe aqui. Sobrescrevê-lo com
        uma dedução seria dizer à equipe que o clique dela não vale nada.
        """
        assert regras.desfecho_efetivo(
            desfecho="realizada",
            concluida_em=None,
            cancelada_em=em(2026, 9, 10, 13, 0),   # a dedução diria no_show
            inicio=self.INICIO,
        ) == "realizada"

    def test_tarefa_concluida_sem_registro_vira_realizada(self):
        """
        Acontece quando alguém fecha a reunião pela aba de Tarefas ou pela
        tela de gestão, que não conhecem a agenda. Sem esta regra, uma
        reunião que comprovadamente aconteceu ficaria pendente para sempre.
        """
        assert regras.desfecho_efetivo(
            desfecho=None, concluida_em=em(2026, 9, 10, 15, 0),
            cancelada_em=None, inicio=self.INICIO,
        ) == "realizada"

    def test_tarefa_cancelada_sem_registro_pergunta_ao_relogio(self):
        assert regras.desfecho_efetivo(
            desfecho=None, concluida_em=None,
            cancelada_em=em(2026, 9, 5, 9, 0), inicio=self.INICIO,
        ) == "cancelada"
        assert regras.desfecho_efetivo(
            desfecho=None, concluida_em=None,
            cancelada_em=em(2026, 9, 10, 13, 0), inicio=self.INICIO,
        ) == "no_show"

    def test_nada_registrado_e_nada_fechado_devolve_none(self):
        """
        None é informação, não falha: é o que a tela usa para COBRAR o
        registro em vez de inventar um resultado que ninguém afirmou.
        """
        assert regras.desfecho_efetivo(
            desfecho=None, concluida_em=None, cancelada_em=None,
            inicio=self.INICIO,
        ) is None


class TestSugestaoDeDesfecho:
    """
    A sugestão NÃO é o `desfecho_pelo_relogio` cru.

    O relógio responde "cancelamento ou no-show"; o formulário pergunta "o
    que aconteceu". Para uma reunião que já terminou a antecedência é
    negativa, e usar o relógio direto pré-selecionaria no-show em toda
    reunião passada — o padrão errado no caso mais comum, e um Enter
    distraído bastaria para transformar uma reunião que aconteceu em falta
    do cliente.
    """
    INICIO = em(2026, 9, 10, 14, 0)   # 14h, 30 min -> termina 14h30

    def test_reuniao_que_terminou_sugere_realizada(self):
        assert regras.sugestao_de_desfecho(
            self.INICIO, 30, em(2026, 9, 10, 15, 0)
        ) == "realizada"

    def test_exatamente_no_fim_ja_sugere_realizada(self):
        """
        Às 14h30 em ponto a reunião das 14h acabou. Mesma fronteira de
        `pendente_de_desfecho`, e as duas precisam concordar: uma reunião
        que aparece como pendente e abre o formulário sugerindo no-show
        estaria cobrando e respondendo errado no mesmo gesto.
        """
        assert regras.sugestao_de_desfecho(
            self.INICIO, 30, em(2026, 9, 10, 14, 30)
        ) == "realizada"

    def test_em_andamento_ainda_nao_sugere_realizada(self):
        """
        14h05: a reunião das 14h está acontecendo. Quem abre o formulário
        agora está registrando que o cliente não apareceu.
        """
        assert regras.sugestao_de_desfecho(
            self.INICIO, 30, em(2026, 9, 10, 14, 5)
        ) == "no_show"

    def test_desmarcada_com_antecedencia_sugere_cancelada(self):
        assert regras.sugestao_de_desfecho(
            self.INICIO, 30, em(2026, 9, 7, 9, 0)
        ) == "cancelada"

    def test_desmarcada_em_cima_da_hora_sugere_no_show(self):
        assert regras.sugestao_de_desfecho(
            self.INICIO, 30, em(2026, 9, 10, 12, 0)
        ) == "no_show"

    def test_a_duracao_desloca_a_fronteira(self):
        """
        Uma reunião de 2h que começou às 14h não terminou às 14h30 — e o
        formulário aberto no meio dela não pode sugerir que ela aconteceu.
        """
        assert regras.sugestao_de_desfecho(
            self.INICIO, 120, em(2026, 9, 10, 15, 0)
        ) == "no_show"
        assert regras.sugestao_de_desfecho(
            self.INICIO, 120, em(2026, 9, 10, 16, 1)
        ) == "realizada"

    def test_sempre_devolve_um_desfecho_valido(self):
        for momento in (em(2026, 9, 1, 8, 0), em(2026, 9, 10, 14, 10),
                        em(2026, 9, 30, 8, 0)):
            assert regras.sugestao_de_desfecho(
                self.INICIO, 30, momento
            ) in regras.DESFECHOS


class TestPendenteDeDesfecho:
    INICIO = em(2026, 9, 10, 14, 0)

    def _pendente(self, **troca):
        base = dict(
            desfecho=None, concluida_em=None, cancelada_em=None,
            inicio=self.INICIO, duracao_min=30,
            agora=em(2026, 9, 10, 18, 0),
        )
        base.update(troca)
        return regras.pendente_de_desfecho(**base)

    def test_terminou_e_ninguem_marcou(self):
        assert self._pendente() is True

    def test_ainda_nao_comecou(self):
        assert self._pendente(agora=em(2026, 9, 10, 9, 0)) is False

    def test_no_meio_da_reuniao_nao_cobra(self):
        """
        Às 14h05 a reunião das 14h ainda está acontecendo. A conta é a
        partir do FIM, não do início — cobrar o desfecho no meio dela seria
        ruído puro.
        """
        assert self._pendente(agora=em(2026, 9, 10, 14, 5)) is False

    def test_no_minuto_do_fim_ja_cobra(self):
        assert self._pendente(agora=em(2026, 9, 10, 14, 30)) is True

    def test_reuniao_longa_so_cobra_depois_do_fim_dela(self):
        assert self._pendente(duracao_min=180, agora=em(2026, 9, 10, 16, 0)) is False
        assert self._pendente(duracao_min=180, agora=em(2026, 9, 10, 17, 30)) is True

    def test_registrada_nao_e_pendente(self):
        assert self._pendente(desfecho="no_show") is False

    def test_fechada_por_outra_tela_nao_e_pendente(self):
        """
        A dedução de `desfecho_efetivo` também apaga a pendência — senão a
        barra cobraria uma reunião que a tela de Tarefas já fechou.
        """
        assert self._pendente(concluida_em=em(2026, 9, 10, 15, 0)) is False
        assert self._pendente(cancelada_em=em(2026, 9, 9, 9, 0)) is False


class TestVocabularioDoDesfecho:
    def test_os_tres_valores(self):
        assert regras.DESFECHOS == ("realizada", "cancelada", "no_show")

    def test_underscore_e_nao_hifen(self):
        """
        Vai para um CHECK do banco e para chave de dicionário nos dois
        lados. O hífen aparece só no rótulo.
        """
        assert "no_show" in regras.DESFECHOS
        assert regras.ROTULO_DESFECHO["no_show"] == "No-show"

    def test_todo_desfecho_tem_rotulo(self):
        for d in regras.DESFECHOS:
            assert regras.ROTULO_DESFECHO[d]

    def test_recusa_desconhecido(self):
        with pytest.raises(AgendaInvalida, match="Desfecho inválido"):
            regras.validar_desfecho("faltou")

    def test_so_cancelada_e_no_show_encerram(self):
        assert regras.encerra_a_reuniao("cancelada") is True
        assert regras.encerra_a_reuniao("no_show") is True
        assert regras.encerra_a_reuniao("realizada") is False

    def test_o_limite_de_24h_e_o_da_operacao(self):
        assert regras.HORAS_ANTECEDENCIA_MINIMA == 24
