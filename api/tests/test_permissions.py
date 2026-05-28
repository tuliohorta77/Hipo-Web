"""
Testes da camada de permissões (routers/permissions.py).

Cobertos:
  - modulos_do_cargo: já testado por test_clientes.py::TestPermissoesClientes
  - requer_qualquer_modulo: usado pelo drilldown de contador-leads
  - Regressões: garantias por cargo de quais módulos têm/não têm
"""
import pytest
from fastapi import HTTPException

from routers.permissions import (
    modulos_do_cargo,
    requer_qualquer_modulo,
)


class TestRequerQualquerModulo:
    """
    requer_qualquer_modulo libera o usuário se ele tiver QUALQUER UM
    dos módulos da lista. Usado em rotas multi-módulo (ex: /contador-leads
    que serve à aba Leads da Carteira E à interface de Clientes).
    """

    @pytest.mark.asyncio
    async def test_adm_passa_com_qualquer_lista(self):
        dep = requer_qualquer_modulo(["clientes", "carteira"])
        result = await dep(user={"cargo": "ADM"})
        assert result == {"cargo": "ADM"}

    @pytest.mark.asyncio
    async def test_hunter_passa_via_carteira(self):
        """Hunter só tem 'carteira' — passa porque carteira está na lista."""
        dep = requer_qualquer_modulo(["clientes", "carteira"])
        result = await dep(user={"cargo": "Hunter"})
        assert result == {"cargo": "Hunter"}

    @pytest.mark.asyncio
    async def test_farmer_passa_via_carteira(self):
        dep = requer_qualquer_modulo(["clientes", "carteira"])
        result = await dep(user={"cargo": "Farmer"})
        assert result == {"cargo": "Farmer"}

    @pytest.mark.asyncio
    async def test_ep_passa_via_clientes(self):
        dep = requer_qualquer_modulo(["clientes", "carteira"])
        result = await dep(user={"cargo": "EP"})
        assert result == {"cargo": "EP"}

    @pytest.mark.asyncio
    async def test_gerente_passa_via_clientes(self):
        dep = requer_qualquer_modulo(["clientes", "carteira"])
        result = await dep(user={"cargo": "Gerente"})
        assert result == {"cargo": "Gerente"}

    @pytest.mark.asyncio
    async def test_ev_passa_via_clientes(self):
        """EV tem 'clientes' (e não 'carteira') — passa via clientes."""
        dep = requer_qualquer_modulo(["clientes", "carteira"])
        result = await dep(user={"cargo": "EV"})
        assert result == {"cargo": "EV"}

    @pytest.mark.asyncio
    async def test_ev_bloqueado_em_rota_so_de_carteira(self):
        """EV NÃO tem 'carteira' — bloqueado em rota carteira-only."""
        dep = requer_qualquer_modulo(["carteira"])
        with pytest.raises(HTTPException) as exc:
            await dep(user={"cargo": "EV"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_hunter_bloqueado_sem_modulo_compativel(self):
        """Hunter (só carteira) tentando acessar rota que exige pex ou po → 403."""
        dep = requer_qualquer_modulo(["pex", "po"])
        with pytest.raises(HTTPException) as exc:
            await dep(user={"cargo": "Hunter"})
        assert exc.value.status_code == 403
        assert "Hunter" in exc.value.detail

    @pytest.mark.asyncio
    async def test_cargo_desconhecido_bloqueado(self):
        dep = requer_qualquer_modulo(["clientes"])
        with pytest.raises(HTTPException) as exc:
            await dep(user={"cargo": "CargoQueNaoExiste"})
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_sem_cargo_bloqueado(self):
        dep = requer_qualquer_modulo(["clientes", "carteira"])
        with pytest.raises(HTTPException) as exc:
            await dep(user={"cargo": None})
        assert exc.value.status_code == 403
        assert "sem cargo" in exc.value.detail

    def test_lista_vazia_levanta_value_error(self):
        """Erro de programação: tentar criar guard com lista vazia."""
        with pytest.raises(ValueError):
            requer_qualquer_modulo([])

    @pytest.mark.asyncio
    async def test_modulo_unico_funciona_como_requer_modulo(self):
        """Lista de 1 módulo deve se comportar igual a requer_modulo."""
        dep = requer_qualquer_modulo(["clientes"])
        # ADM tem clientes
        await dep(user={"cargo": "ADM"})
        # Hunter NÃO tem clientes
        with pytest.raises(HTTPException) as exc:
            await dep(user={"cargo": "Hunter"})
        assert exc.value.status_code == 403


class TestModulosDoCargoRegressao:
    """
    Garantia explícita por cargo:
      - Hunter/Farmer/SDR: NÃO veem 'clientes', SIM veem 'carteira'.
      - EV: SIM vê 'clientes', NÃO vê 'carteira' (regra inversa).
    Importante: o drilldown de Hunter/Farmer não deve aparecer na nav
    principal de Clientes; só funciona pelo drawer da Carteira. E o EV
    não deve ver Contadores no menu, só Clientes/Vendas.
    """

    def test_hunter_sem_clientes(self):
        m = modulos_do_cargo("Hunter")
        assert "clientes" not in m
        assert "carteira" in m

    def test_farmer_sem_clientes(self):
        m = modulos_do_cargo("Farmer")
        assert "clientes" not in m
        assert "carteira" in m

    def test_sdr_sem_clientes(self):
        # v1.3.1: SDR migrou para o modulo 'agendamento' (Opcao 1).
        # Nao ve clientes nem carteira.
        m = modulos_do_cargo("SDR")
        assert "clientes" not in m
        assert "carteira" not in m
        assert "agendamento" in m

    def test_ev_com_clientes_sem_carteira(self):
        m = modulos_do_cargo("EV")
        assert "clientes" in m
        assert "carteira" not in m
