"""
HIPO — Testes das permissões do módulo Agendamento.

v1.3.1: SDR vê SÓ 'agendamento' (Opção 1).
v1.3.2: ADM, Franqueado e Gerente também passam a ver 'agendamento'
(acompanhamento). EP NÃO recebe.

Garante também que os demais cargos não foram afetados (Hunter/Farmer/EC
em 'carteira'; EV em 'clientes').
"""
from routers.permissions import modulos_do_cargo, deve_filtrar_por_usuario


class TestModulosDoCargoSDR:
    def test_sdr_ve_somente_agendamento(self):
        assert modulos_do_cargo("SDR") == {"agendamento"}

    def test_sdr_nao_ve_carteira(self):
        assert "carteira" not in modulos_do_cargo("SDR")

    def test_sdr_nao_ve_clientes(self):
        assert "clientes" not in modulos_do_cargo("SDR")

    def test_sdr_filtra_por_usuario_por_seguranca(self):
        assert deve_filtrar_por_usuario("SDR") is True


class TestAgendamentoParaGestao:
    """v1.3.2: ADM, Franqueado e Gerente acompanham o Agendamento."""

    def test_adm_ve_agendamento(self):
        assert "agendamento" in modulos_do_cargo("ADM")

    def test_franqueado_ve_agendamento(self):
        assert "agendamento" in modulos_do_cargo("Franqueado")

    def test_gerente_ve_agendamento(self):
        assert "agendamento" in modulos_do_cargo("Gerente")

    def test_gerente_mantem_carteira_e_clientes(self):
        # Agendamento é ADICIONAL, não substitui.
        assert modulos_do_cargo("Gerente") == {"carteira", "clientes", "agendamento"}

    def test_ep_NAO_ve_agendamento(self):
        # Decisão de produto: EP fica de fora.
        assert "agendamento" not in modulos_do_cargo("EP")
        assert modulos_do_cargo("EP") == {"carteira", "clientes"}

    def test_adm_mantem_modulos_de_sempre(self):
        mods = modulos_do_cargo("ADM")
        assert {"pex", "po", "bd", "metas", "carteira", "clientes", "usuarios"} <= mods


class TestModulosDosDemaisCargosInalterados:
    def test_hunter_continua_carteira(self):
        assert modulos_do_cargo("Hunter") == {"carteira"}

    def test_farmer_continua_carteira(self):
        assert modulos_do_cargo("Farmer") == {"carteira"}

    def test_ec_continua_carteira(self):
        assert modulos_do_cargo("EC") == {"carteira"}

    def test_ev_continua_clientes(self):
        assert modulos_do_cargo("EV") == {"clientes"}

    def test_cargo_desconhecido_vazio(self):
        assert modulos_do_cargo("Inexistente") == set()

    def test_cargo_none_vazio(self):
        assert modulos_do_cargo(None) == set()
