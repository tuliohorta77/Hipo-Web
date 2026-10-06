"""
HIPO — Regras puras do comitê da oportunidade e do contato da tarefa (045).

Sem banco: services/contato_oportunidade.py e o trecho de contato de
services/tarefa.py.
"""
import pytest

from services import contato_oportunidade as regras
from services import tarefa as regras_tarefa
from services.contato_oportunidade import ContatoOportunidadeInvalido
from services.tarefa import TarefaInvalida


class TestPapel:
    @pytest.mark.parametrize("papel", regras.PAPEIS)
    def test_todos_os_papeis_do_vocabulario_passam(self, papel):
        assert regras.validar_papel(papel) == papel

    def test_normaliza_caixa_e_espaco(self):
        assert regras.validar_papel("  Decisor ") == "decisor"

    def test_vazio_vira_sem_papel(self):
        assert regras.validar_papel("") is None
        assert regras.validar_papel(None) is None

    def test_papel_inventado_e_recusado(self):
        """Vocabulário fechado: papel inventado não entra na cobertura."""
        with pytest.raises(ContatoOportunidadeInvalido):
            regras.validar_papel("chefe")

    def test_todo_papel_tem_rotulo(self):
        assert set(regras.ROTULOS_PAPEL) == set(regras.PAPEIS)


class TestFarol:
    def test_sem_contato_e_vermelho(self):
        f = regras.farol_multithreading(0)
        assert (f.nivel, f.tom) == ("sem_contato", "danger")

    def test_um_contato_e_amarelo_nao_vermelho(self):
        """
        Um só é o estado normal logo depois do primeiro contato. Pintar de
        vermelho ensinaria a ignorar a cor.
        """
        f = regras.farol_multithreading(1, ["decisor"])
        assert (f.nivel, f.tom) == ("um_so", "warning")
        assert "uma pessoa só" in f.dica

    @pytest.mark.parametrize("qtd", [2, 3, 4])
    def test_de_dois_a_quatro_e_o_ideal(self, qtd):
        f = regras.farol_multithreading(qtd, ["decisor"])
        assert (f.nivel, f.tom) == ("ideal", "success")
        assert f.rotulo == f"{qtd} contatos"

    def test_cinco_ou_mais_continua_verde(self):
        f = regras.farol_multithreading(6, ["decisor"])
        assert (f.nivel, f.tom) == ("amplo", "success")

    def test_sem_decisor_muda_a_dica_nao_a_cor(self):
        f = regras.farol_multithreading(3, ["operacional", "compras", None])
        assert f.tom == "success"
        assert f.tem_decisor is False
        assert "decisor" in f.dica

    def test_com_decisor_comite_coberto(self):
        f = regras.farol_multithreading(2, ["decisor", "tecnico"])
        assert f.tem_decisor is True
        assert f.dica == "Comitê coberto."

    def test_faixa_ideal_e_a_do_metodo(self):
        """O mesmo número que a aula da Universidade ensina: 2 a 4."""
        assert (regras.MINIMO_IDEAL, regras.MAXIMO_IDEAL) == (2, 4)


class TestContatoDaTarefa:
    @pytest.mark.parametrize("tipo", ["ligacao", "reuniao", "visita", "whatsapp", "email"])
    def test_interacao_exige_contato(self, tipo):
        assert regras_tarefa.exige_contato(tipo)
        with pytest.raises(TarefaInvalida) as e:
            regras_tarefa.validar_contato_obrigatorio(tipo, None)
        assert "com quem" in str(e.value)

    @pytest.mark.parametrize("tipo", ["proposta", "outro"])
    def test_trabalho_interno_dispensa(self, tipo):
        assert not regras_tarefa.exige_contato(tipo)
        regras_tarefa.validar_contato_obrigatorio(tipo, None)

    def test_com_contato_passa(self):
        regras_tarefa.validar_contato_obrigatorio("ligacao", "qualquer-id")

    def test_a_lista_so_tem_tipos_que_existem(self):
        assert set(regras_tarefa.TIPOS_EXIGEM_CONTATO) <= set(regras_tarefa.TIPOS)

    def test_a_mensagem_usa_o_rotulo_do_tipo(self):
        with pytest.raises(TarefaInvalida) as e:
            regras_tarefa.validar_contato_obrigatorio("whatsapp", None)
        assert str(e.value).startswith("WhatsApp precisa de um contato")
