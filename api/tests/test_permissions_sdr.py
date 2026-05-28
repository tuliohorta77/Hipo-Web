"""
HIPO — Testes das permissões do cargo SDR (v1.3.1).

Opção 1: SDR vê SÓ o módulo 'agendamento'. Não vê carteira, clientes,
pex, etc. Garante que a régua de Vendas (clientes) e Contadores
(carteira) permanecem fora do alcance do SDR.

Também confirma que os demais cargos não foram afetados pela mudança
(Hunter/Farmer continuam em 'carteira'; EC permanece em 'carteira').
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
        # SDR não tem carteira, mas se a função for consultada deve
        # cair no ramo seguro (filtra).
        assert deve_filtrar_por_usuario("SDR") is True


class TestModulosDosDemaisCargosInalterados:
    def test_hunter_continua_carteira(self):
        assert modulos_do_cargo("Hunter") == {"carteira"}

    def test_farmer_continua_carteira(self):
        assert modulos_do_cargo("Farmer") == {"carteira"}

    def test_ec_continua_carteira(self):
        # EC permanece em carteira por compat (não migrou pra agendamento).
        assert modulos_do_cargo("EC") == {"carteira"}

    def test_ev_continua_clientes(self):
        assert modulos_do_cargo("EV") == {"clientes"}

    def test_gestao_continua_carteira_clientes(self):
        assert modulos_do_cargo("Gerente") == {"carteira", "clientes"}
        assert modulos_do_cargo("EP") == {"carteira", "clientes"}

    def test_admin_ve_tudo_sem_agendamento_explicito(self):
        # ADM/Franqueado não recebem 'agendamento' no conjunto — o
        # módulo é específico do SDR. (Se um dia o ADM precisar ver
        # Agendamento, ajustar aqui.)
        mods = modulos_do_cargo("ADM")
        assert "agendamento" not in mods
        assert {"pex", "po", "bd", "metas", "carteira", "clientes"} <= mods

    def test_cargo_desconhecido_vazio(self):
        assert modulos_do_cargo("Inexistente") == set()

    def test_cargo_none_vazio(self):
        assert modulos_do_cargo(None) == set()
