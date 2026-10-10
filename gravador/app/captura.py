"""
Captura do áudio da chamada em DOIS canais.

  canal 0 (esquerdo) = o microfone      → quem ligou (o executivo)
  canal 1 (direito)  = o que o PC toca  → o cliente (loopback da saída)

Separados, o AWS Transcribe transcreve cada lado sozinho: "quem falou" sai
exato, sem adivinhar vozes, e o tempo de fala de cada um vem de graça.

O loopback grava TUDO que o dispositivo de saída toca — se tocar música no
mesmo fone durante a ligação, ela vai junto. Por isso o padrão é o
dispositivo de COMUNICAÇÃO (o headset), e não o alto-falante comum.

A biblioteca `soundcard` usa WASAPI em modo compartilhado com conversão de
taxa, então a gravação já sai na taxa pedida (16 kHz), qualquer que seja a
do fone. Em silêncio a placa às vezes não entrega amostra nenhuma; a
`soundcard` devolve zeros nesse caso, e o `Alinhador` abaixo corrige o que
ainda escapar, para os dois canais não escorregarem um em relação ao outro.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

log = logging.getLogger("gravador.captura")

BLOCO_S = 0.1                 # 100 ms por leitura
FOLGA_ATRASO_S = 0.5          # atraso tolerado antes de preencher com silêncio


def para_int16(sinal):
    """float32 [-1, 1] → int16, cortando o que passar. Já int16 passa direto."""
    import numpy as np

    if sinal.dtype == np.int16:
        return sinal
    return (np.clip(sinal, -1.0, 1.0) * 32767).astype("int16")


class Alinhador:
    """
    Junta blocos de um canal e mantém o total de amostras colado no relógio.

    Se o dispositivo parar de entregar amostras (silêncio sem dados, fone
    desconectado por um instante), o canal ficaria mais curto que o tempo
    real e tudo depois escorregaria. Quando o atraso passa da folga, entra
    silêncio no lugar do que faltou — ANTES do bloco que acabou de chegar,
    que é onde o buraco aconteceu.

    Guarda em int16 (metade da memória do float32): uma ligação de 1 h a
    16 kHz são ~115 MB por canal assim.
    """

    def __init__(self, taxa: int, folga_s: float = FOLGA_ATRASO_S):
        self.taxa = taxa
        self.folga = int(folga_s * taxa)
        self.blocos: list = []
        self.total = 0

    def adicionar(self, bloco, decorrido_s: float) -> None:
        import numpy as np

        n = len(bloco)
        esperado = int(decorrido_s * self.taxa)
        buraco = esperado - (self.total + n)
        if buraco > self.folga:
            self.blocos.append(np.zeros(buraco, dtype="int16"))
            self.total += buraco
        if n:
            self.blocos.append(para_int16(bloco))
            self.total += n

    def sinal(self):
        import numpy as np

        if not self.blocos:
            return np.zeros(0, dtype="int16")
        sinal = np.concatenate(self.blocos)
        self.blocos = [sinal]
        return sinal


def juntar_canais(esquerdo, direito):
    """Dois canais mono → estéreo int16, do tamanho do maior (o menor completa com silêncio)."""
    import numpy as np

    esquerdo, direito = para_int16(esquerdo), para_int16(direito)
    n = max(len(esquerdo), len(direito))
    out = np.zeros((n, 2), dtype="int16")
    out[: len(esquerdo), 0] = esquerdo
    out[: len(direito), 1] = direito
    return out


def salvar_flac(caminho: Path, estereo, taxa: int) -> int:
    """Grava o FLAC e devolve o tamanho em bytes."""
    import soundfile as sf

    caminho.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(caminho), estereo, taxa, format="FLAC", subtype="PCM_16")
    return caminho.stat().st_size


# ── Dispositivos (Windows) ───────────────────────────────────────────


def _id_comunicacao(fluxo: int) -> str | None:
    """Id WASAPI do dispositivo padrão de COMUNICAÇÃO (0 = saída, 1 = entrada)."""
    try:
        from pycaw.utils import AudioUtilities

        dev = AudioUtilities.GetDeviceEnumerator().GetDefaultAudioEndpoint(fluxo, 2)
        return dev.GetId()
    except Exception as e:  # noqa: BLE001
        log.warning("sem dispositivo de comunicacao (%s): %s", fluxo, e)
        return None


def escolher_microfone(pedido: str):
    import soundcard as sc

    if pedido == "comunicacao":
        dev_id = _id_comunicacao(1)
        if dev_id:
            try:
                return sc.get_microphone(dev_id)
            except Exception as e:  # noqa: BLE001
                log.warning("microfone de comunicacao nao abriu: %s", e)
        return sc.default_microphone()
    if pedido == "padrao":
        return sc.default_microphone()
    return sc.get_microphone(pedido)


def escolher_loopback(pedido: str):
    """O 'microfone virtual' que grava o que a saída toca."""
    import soundcard as sc

    if pedido in ("comunicacao", "padrao"):
        dev_id = _id_comunicacao(0) if pedido == "comunicacao" else None
        if not dev_id:
            dev_id = sc.default_speaker().id
        try:
            return sc.get_microphone(dev_id, include_loopback=True)
        except Exception as e:  # noqa: BLE001
            log.warning("loopback de %s nao abriu (%s); usando a saida padrao", dev_id, e)
            return sc.get_microphone(sc.default_speaker().id, include_loopback=True)
    alto = sc.get_speaker(pedido)
    return sc.get_microphone(alto.id, include_loopback=True)


# ── A gravação ───────────────────────────────────────────────────────


class Gravacao:
    """
    Uma chamada sendo gravada: duas threads, uma por canal. `parar()`
    devolve o estéreo pronto.
    """

    def __init__(self, entrada: str, saida: str, taxa: int):
        self.taxa = taxa
        self._parar = threading.Event()
        self._canais = [Alinhador(taxa), Alinhador(taxa)]
        self._erros: list[str] = []
        self._t0 = time.monotonic()
        self._threads = [
            threading.Thread(target=self._ler, args=(0, entrada), name="grav-mic", daemon=True),
            threading.Thread(target=self._ler, args=(1, saida), name="grav-saida", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def _ler(self, canal: int, pedido: str) -> None:
        try:
            import comtypes  # noqa: F401 - garante COM nesta thread
            try:
                comtypes.CoInitializeEx(0)  # MTA, igual ao resto do programa
            except OSError:
                pass
        except ImportError:
            pass
        try:
            dev = escolher_microfone(pedido) if canal == 0 else escolher_loopback(pedido)
            log.info("canal %d gravando de: %s", canal, getattr(dev, "name", dev))
            frames = int(self.taxa * BLOCO_S)
            with dev.recorder(samplerate=self.taxa, channels=1, blocksize=frames) as rec:
                while not self._parar.is_set():
                    bloco = rec.record(numframes=frames)
                    self._canais[canal].adicionar(bloco[:, 0], time.monotonic() - self._t0)
        except Exception as e:  # noqa: BLE001 - um canal falhando não perde o outro
            log.exception("canal %d falhou", canal)
            self._erros.append(f"canal {canal}: {e}")

    def parar(self):
        self._parar.set()
        for t in self._threads:
            t.join(timeout=3)
        decorrido = time.monotonic() - self._t0
        # O último pedaço de silêncio de cada canal, até o fim real.
        import numpy as np

        for c in self._canais:
            c.adicionar(np.zeros(0, dtype="float32"), decorrido)
        return juntar_canais(self._canais[0].sinal(), self._canais[1].sinal()), self._erros
