"""
HIPO — Testes do buffer de telemetria: QUANDO ele descarrega.

Puros: sem Postgres, sem AWS. O `descarregar` real é trocado por um dublê, de
modo que o que está sob teste é só a decisão de descarregar — que é exatamente
onde estava o defeito.

O RELÓGIO É INJETADO, não dormido. Mesma escolha de services/tarefa.py e
services/parceiro.py: teste que espera trinta segundos de verdade é teste que
ninguém roda.

O QUE ESTES TESTES TRAVAM

Antes, o único gatilho era o tamanho do lote. Como o buffer é global por
processo e o uvicorn roda com quatro workers, "100 eventos" viravam 400
requisições espalhadas por quatro buffers. Numa operação de sete pessoas, a
telemetria simplesmente não chegava ao banco — e sumia inteira a cada deploy.
Se alguém remover o gatilho por tempo, estes testes caem.
"""
from __future__ import annotations

import asyncio

import pytest

from middleware.telemetria import BufferTelemetria

pytestmark = pytest.mark.anyio

# Um evento qualquer: o buffer não olha o conteúdo, só a quantidade e a idade.
EVENTO = ("alguem@teste.com", "GET", "/crm/contas", "crm", 200, 12, None)


class RelogioFalso:
    """Relógio monotônico controlado pelo teste."""

    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


def montar(**kwargs) -> BufferTelemetria:
    """
    Buffer com `descarregar` trocado por um dublê que registra a chamada.

    O dublê ESVAZIA o buffer e zera o relógio, exatamente como o original faz
    antes de gravar — só não fala com o banco. Um dublê que apenas contasse
    chamadas deixaria o buffer cheio e o `_mais_antigo` velho, e os testes
    passariam a medir a imitação em vez do código.
    """
    b = BufferTelemetria(**kwargs)
    b.descargas = []

    async def falso():
        async with b._lock:
            quantos = len(b._eventos)
            b._eventos = []
            b._mais_antigo = None
        b.descargas.append(quantos)
        return quantos

    b.descarregar = falso
    return b


async def registrar(b: BufferTelemetria, quantos: int = 1) -> None:
    for _ in range(quantos):
        await b.registrar(EVENTO)
    # `registrar` dispara a descarga como task solta; um tick do loop basta
    # para ela rodar.
    await asyncio.sleep(0)


class TestGatilhoPorTamanho:
    async def test_abaixo_do_lote_nao_descarrega(self):
        b = montar(lote=25, relogio=RelogioFalso())
        await registrar(b, 3)
        assert b.descargas == []
        assert len(b) == 3

    async def test_atingir_o_lote_descarrega(self):
        b = montar(lote=3, relogio=RelogioFalso())
        await registrar(b, 3)
        assert b.descargas == [3]


class TestGatilhoPorTempo:
    async def test_evento_velho_descarrega_mesmo_longe_do_lote(self):
        """O caso que a operação real produz: pouquíssimo tráfego."""
        relogio = RelogioFalso()
        b = montar(lote=1000, idade_maxima=30.0, relogio=relogio)

        await registrar(b)
        assert b.descargas == []

        relogio.avancar(31)
        await registrar(b)
        assert b.descargas == [2]

    async def test_dentro_da_idade_nao_descarrega(self):
        relogio = RelogioFalso()
        b = montar(lote=1000, idade_maxima=30.0, relogio=relogio)

        await registrar(b)
        relogio.avancar(29)
        await registrar(b)
        assert b.descargas == []

    async def test_idade_none_desliga_o_gatilho(self):
        """É assim que o conftest impede a descarga automática na suíte."""
        relogio = RelogioFalso()
        b = montar(lote=1000, idade_maxima=None, relogio=relogio)

        await registrar(b)
        relogio.avancar(10_000)
        await registrar(b)
        assert b.descargas == []

    async def test_a_idade_conta_do_evento_mais_antigo(self):
        """
        Não é "o último evento tem 30s", é "o mais antigo tem 30s".

        Tráfego constante e ralo nunca dispararia o gatilho se ele olhasse o
        evento mais recente — que é justamente o padrão desta operação.
        """
        relogio = RelogioFalso()
        b = montar(lote=1000, idade_maxima=30.0, relogio=relogio)

        # Um evento a cada 8 segundos. Nenhum deles é "velho" sozinho, mas o
        # primeiro envelhece: no quinto registro já se passaram 32s desde ele,
        # e é aí que a descarga acontece — com os cinco juntos.
        for _ in range(5):
            await registrar(b)
            relogio.avancar(8)

        assert b.descargas == [5]

        # E o relógio recomeça: o evento seguinte entra num buffer novo.
        await registrar(b)
        assert b.descargas == [5]
        assert len(b) == 1


class TestLimiteDoBuffer:
    async def test_acima_do_limite_descarta_e_conta(self):
        b = montar(limite=2, lote=1000, relogio=RelogioFalso())
        await registrar(b, 3)
        assert len(b) == 2
        assert b.descartados == 1


class TestLimpar:
    async def test_limpar_zera_o_relogio_do_buffer(self):
        """
        Depois de limpar, a idade recomeça do próximo evento.

        Sem isto, o `_mais_antigo` de um buffer limpo continuaria antigo e a
        primeira requisição depois de um TRUNCATE na suíte dispararia uma
        descarga — de novo em cima do lock que a fixture segura.
        """
        relogio = RelogioFalso()
        b = montar(lote=1000, idade_maxima=30.0, relogio=relogio)

        await registrar(b)
        relogio.avancar(100)
        await b.limpar()

        await registrar(b)
        assert b.descargas == []
        assert b.descartados == 0
