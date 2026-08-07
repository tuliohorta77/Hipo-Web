"""
HIPO — Testes das regras do funil (funções puras, sem banco).

O invariante central:
    ativa | suspensa                  -> fase != finalizado
    perdido | cancelado | conquistado -> fase == finalizado

Estes testes são a documentação executável dessa regra. Se alguém afrouxar o
invariante no futuro, quebra aqui antes de quebrar o CHECK do banco.
"""
import pytest

from services.oportunidade import (
    FASES,
    FASES_ABERTAS,
    STATUS_COM_MOTIVO,
    STATUS_CONTA_CONVERSAO,
    STATUS_DESFECHO,
    STATUS_ABERTOS,
    TEMPERATURAS,
    Estado,
    TransicaoInvalida,
    eh_aberta,
    eh_desfecho,
    finalizar,
    formatar_numero,
    mover_para_fase,
    mudar_status,
    reabrir,
    validar_estado,
)


def ativa(fase="lead", temperatura=50):
    return Estado(fase=fase, status="ativa", temperatura=temperatura)


def finalizada(status="perdido", fase_desfecho="negociacao", motivo=1):
    return Estado(
        fase="finalizado",
        status=status,
        fase_desfecho=fase_desfecho,
        motivo_desfecho_id=motivo if status in STATUS_COM_MOTIVO else None,
        temperatura=70,
    )


# ── Vocabulário ──────────────────────────────────────────────────────

class TestVocabulario:
    def test_as_cinco_fases_na_ordem(self):
        assert FASES == ("lead", "qualificacao", "apresentacao", "negociacao", "finalizado")

    def test_finalizado_nao_e_fase_aberta(self):
        assert "finalizado" not in FASES_ABERTAS
        assert len(FASES_ABERTAS) == 4

    def test_status_abertos_e_desfechos_nao_se_misturam(self):
        assert set(STATUS_ABERTOS) & set(STATUS_DESFECHO) == set()

    def test_conquistado_nao_exige_motivo(self):
        """Ganhar não precisa de justificativa — obrigar só geraria lixo."""
        assert "conquistado" not in STATUS_COM_MOTIVO

    def test_cancelado_fica_fora_da_conversao(self):
        """Cancelado é erro nosso de CRM, não recusa do cliente."""
        assert "cancelado" not in STATUS_CONTA_CONVERSAO
        assert "perdido" in STATUS_CONTA_CONVERSAO

    def test_temperaturas_de_dez_em_dez(self):
        assert TEMPERATURAS == (0, 10, 20, 30, 40, 50, 60, 70, 80, 90)

    def test_helpers(self):
        assert eh_aberta("ativa") and eh_aberta("suspensa")
        assert eh_desfecho("perdido") and not eh_desfecho("ativa")


# ── Invariante ───────────────────────────────────────────────────────

class TestInvariante:
    @pytest.mark.parametrize("status", STATUS_ABERTOS)
    def test_aberta_nao_pode_estar_em_finalizado(self, status):
        with pytest.raises(TransicaoInvalida, match="Finalizado"):
            validar_estado(Estado(fase="finalizado", status=status, temperatura=50))

    @pytest.mark.parametrize("status", STATUS_DESFECHO)
    @pytest.mark.parametrize("fase", FASES_ABERTAS)
    def test_desfecho_so_existe_em_finalizado(self, status, fase):
        with pytest.raises(TransicaoInvalida, match="só existe na fase Finalizado"):
            validar_estado(
                Estado(fase=fase, status=status, motivo_desfecho_id=1, temperatura=50)
            )

    def test_finalizado_exige_fase_de_desfecho(self):
        with pytest.raises(TransicaoInvalida, match="de qual fase"):
            validar_estado(
                Estado(fase="finalizado", status="conquistado", fase_desfecho=None)
            )

    def test_nao_finalizado_nao_tem_fase_de_desfecho(self):
        with pytest.raises(TransicaoInvalida, match="Só oportunidade finalizada"):
            validar_estado(
                Estado(fase="lead", status="ativa", fase_desfecho="negociacao", temperatura=50)
            )

    @pytest.mark.parametrize("status", STATUS_COM_MOTIVO)
    def test_perda_e_cancelamento_exigem_motivo(self, status):
        with pytest.raises(TransicaoInvalida, match="motivo"):
            validar_estado(
                Estado(fase="finalizado", status=status, fase_desfecho="negociacao")
            )

    def test_ativa_exige_temperatura(self):
        with pytest.raises(TransicaoInvalida, match="temperatura"):
            validar_estado(Estado(fase="lead", status="ativa", temperatura=None))

    def test_suspensa_nao_exige_temperatura(self):
        validar_estado(Estado(fase="lead", status="suspensa", temperatura=None))

    @pytest.mark.parametrize("t", [5, 15, 91, 100, -10])
    def test_temperatura_fora_da_escala(self, t):
        with pytest.raises(TransicaoInvalida, match="múltiplo de 10"):
            validar_estado(Estado(fase="lead", status="ativa", temperatura=t))

    @pytest.mark.parametrize("t", TEMPERATURAS)
    def test_toda_temperatura_da_escala_e_valida(self, t):
        validar_estado(Estado(fase="lead", status="ativa", temperatura=t))

    def test_fase_desconhecida(self):
        with pytest.raises(TransicaoInvalida, match="Fase desconhecida"):
            validar_estado(Estado(fase="inventada", status="ativa", temperatura=50))

    def test_status_desconhecido(self):
        with pytest.raises(TransicaoInvalida, match="Status desconhecido"):
            validar_estado(Estado(fase="lead", status="inventado", temperatura=50))


# ── Movimento no funil ───────────────────────────────────────────────

class TestMoverParaFase:
    def test_avanca(self):
        novo = mover_para_fase(ativa("lead"), "qualificacao")
        assert novo.fase == "qualificacao"
        assert novo.status == "ativa"

    def test_retrocede(self):
        """Voltar fase é legítimo: proposta rejeitada volta para negociação."""
        assert mover_para_fase(ativa("negociacao"), "qualificacao").fase == "qualificacao"

    def test_pula_fase(self):
        """O funil não obriga passar por todas — lead pode ir direto a negociação."""
        assert mover_para_fase(ativa("lead"), "negociacao").fase == "negociacao"

    def test_arrastar_para_finalizado_e_recusado(self):
        """
        O kanban precisa abrir o modal de desfecho. Sem esta guarda, soltar
        na coluna Finalizado criaria registro sem status nem motivo.
        """
        with pytest.raises(TransicaoInvalida, match="informe o desfecho"):
            mover_para_fase(ativa("negociacao"), "finalizado")

    def test_finalizada_nao_muda_de_fase(self):
        with pytest.raises(TransicaoInvalida, match="Reabra antes"):
            mover_para_fase(finalizada(), "negociacao")

    def test_mover_para_a_mesma_fase(self):
        with pytest.raises(TransicaoInvalida, match="já está"):
            mover_para_fase(ativa("lead"), "lead")

    def test_fase_inexistente(self):
        with pytest.raises(TransicaoInvalida, match="Fase desconhecida"):
            mover_para_fase(ativa("lead"), "inventada")

    def test_suspensa_pode_mudar_de_fase(self):
        novo = mover_para_fase(Estado(fase="lead", status="suspensa"), "apresentacao")
        assert novo.status == "suspensa"

    def test_preserva_temperatura(self):
        assert mover_para_fase(ativa("lead", 80), "negociacao").temperatura == 80


# ── Desfecho ─────────────────────────────────────────────────────────

class TestFinalizar:
    def test_conquistado_sem_motivo(self):
        novo = finalizar(ativa("negociacao"), "conquistado", None)
        assert novo.fase == "finalizado"
        assert novo.status == "conquistado"
        assert novo.motivo_desfecho_id is None

    def test_guarda_a_fase_de_origem(self):
        """
        É `fase_desfecho` que responde "em qual fase a gente perde" — sem
        isso, todo desfecho pareceria ter acontecido em Finalizado.
        """
        assert finalizar(ativa("apresentacao"), "perdido", 3).fase_desfecho == "apresentacao"

    @pytest.mark.parametrize("fase", FASES_ABERTAS)
    def test_pode_finalizar_de_qualquer_fase(self, fase):
        """Lead que não responde é perdido em Lead, não em Negociação."""
        assert finalizar(ativa(fase), "perdido", 1).fase_desfecho == fase

    @pytest.mark.parametrize("status", STATUS_COM_MOTIVO)
    def test_perda_e_cancelamento_sem_motivo_falham(self, status):
        with pytest.raises(TransicaoInvalida, match="exige informar o motivo"):
            finalizar(ativa("negociacao"), status, None)

    def test_motivo_em_conquistado_e_descartado(self):
        assert finalizar(ativa("negociacao"), "conquistado", 7).motivo_desfecho_id is None

    def test_nao_finaliza_duas_vezes(self):
        with pytest.raises(TransicaoInvalida, match="já está finalizada"):
            finalizar(finalizada(), "conquistado", None)

    def test_status_que_nao_e_desfecho(self):
        with pytest.raises(TransicaoInvalida, match="não é um desfecho"):
            finalizar(ativa(), "ativa", None)

    def test_suspensa_pode_ser_finalizada(self):
        """Suspensa por meses e o cliente some: dá para perder sem reativar."""
        novo = finalizar(Estado(fase="negociacao", status="suspensa"), "perdido", 2)
        assert novo.status == "perdido"


# ── Reabertura ───────────────────────────────────────────────────────

class TestReabrir:
    def test_volta_para_a_fase_de_origem_por_padrao(self):
        novo = reabrir(finalizada(fase_desfecho="apresentacao"), None, 60)
        assert novo.fase == "apresentacao"
        assert novo.status == "ativa"

    def test_fase_de_destino_explicita(self):
        assert reabrir(finalizada(), "lead", 30).fase == "lead"

    def test_limpa_desfecho_e_motivo(self):
        novo = reabrir(finalizada("perdido", motivo=5), None, 40)
        assert novo.fase_desfecho is None
        assert novo.motivo_desfecho_id is None

    def test_reabrir_conquistada(self):
        """Fechou por engano, desfaz."""
        assert reabrir(finalizada("conquistado"), None, 50).status == "ativa"

    def test_so_reabre_finalizada(self):
        with pytest.raises(TransicaoInvalida, match="Só oportunidade finalizada"):
            reabrir(ativa(), None, 50)

    def test_nao_reabre_para_finalizado(self):
        with pytest.raises(TransicaoInvalida, match="Fase de retorno inválida"):
            reabrir(finalizada(), "finalizado", 50)

    def test_preserva_temperatura_se_nao_informada(self):
        assert reabrir(finalizada(), None, None).temperatura == 70

    def test_sem_temperatura_nenhuma_falha(self):
        """Reabrir leva a 'ativa', que exige temperatura."""
        fim = Estado(fase="finalizado", status="conquistado",
                     fase_desfecho="negociacao", temperatura=None)
        with pytest.raises(TransicaoInvalida, match="temperatura"):
            reabrir(fim, None, None)


# ── Suspender / reativar ─────────────────────────────────────────────

class TestMudarStatus:
    def test_suspende(self):
        novo = mudar_status(ativa("negociacao", 70), "suspensa")
        assert novo.status == "suspensa"
        assert novo.fase == "negociacao"

    def test_reativa(self):
        novo = mudar_status(Estado(fase="lead", status="suspensa", temperatura=40), "ativa")
        assert novo.status == "ativa"

    def test_reativar_sem_temperatura_falha(self):
        with pytest.raises(TransicaoInvalida, match="temperatura"):
            mudar_status(Estado(fase="lead", status="suspensa"), "ativa")

    def test_suspender_preserva_a_temperatura(self):
        """O valor volta a valer quando a oportunidade for reativada."""
        assert mudar_status(ativa("lead", 80), "suspensa").temperatura == 80

    def test_nao_aceita_desfecho(self):
        with pytest.raises(TransicaoInvalida, match="use o desfecho"):
            mudar_status(ativa(), "perdido")

    def test_finalizada_precisa_reabrir_antes(self):
        with pytest.raises(TransicaoInvalida, match="reaberta"):
            mudar_status(finalizada(), "ativa")

    def test_mesmo_status(self):
        with pytest.raises(TransicaoInvalida, match="já está"):
            mudar_status(ativa(), "ativa")


# ── Numeração ────────────────────────────────────────────────────────

class TestNumero:
    def test_formato(self):
        assert formatar_numero(2026, 1) == "OPP-2026-00001"

    def test_preenche_com_zeros(self):
        assert formatar_numero(2026, 42) == "OPP-2026-00042"

    def test_nao_trunca_acima_de_cinco_digitos(self):
        assert formatar_numero(2026, 123456) == "OPP-2026-123456"

    def test_ordena_lexicograficamente_dentro_do_ano(self):
        numeros = [formatar_numero(2026, n) for n in (1, 2, 10, 100)]
        assert numeros == sorted(numeros)


# ── Ciclo completo ───────────────────────────────────────────────────

class TestCicloDeVida:
    def test_lead_ate_conquista(self):
        e = ativa("lead", 30)
        for fase in ("qualificacao", "apresentacao", "negociacao"):
            e = mover_para_fase(e, fase)
        e = finalizar(e, "conquistado", None)
        assert (e.fase, e.status, e.fase_desfecho) == ("finalizado", "conquistado", "negociacao")

    def test_perde_reabre_e_ganha(self):
        e = finalizar(mover_para_fase(ativa("lead", 50), "negociacao"), "perdido", 1)
        e = reabrir(e, None, 80)
        assert (e.fase, e.status) == ("negociacao", "ativa")
        e = finalizar(e, "conquistado", None)
        assert e.status == "conquistado"

    def test_suspende_no_meio_e_retoma(self):
        e = mover_para_fase(ativa("lead", 50), "apresentacao")
        e = mudar_status(e, "suspensa")
        e = mover_para_fase(e, "negociacao")
        e = mudar_status(e, "ativa", 90)
        assert (e.fase, e.status, e.temperatura) == ("negociacao", "ativa", 90)
