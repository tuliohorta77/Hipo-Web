"""
Detecção da chamada: o softphone está com o áudio aberto?

O Vivo Voz Negócio não avisa ninguém quando uma chamada começa. O que dá
para ver de fora é o MIXER do Windows: cada programa que usa microfone ou
alto-falante abre uma "sessão de áudio", e a sessão fica Ativa enquanto
o som passa. O gravador olha as sessões do processo do softphone a cada
meio segundo:

  * microfone ativo  → em chamada (padrão). O toque de chamada recebida
                       usa só a saída; o microfone só abre quando atende.
  * saída ativa      → alternativa, para softphone que deixa o microfone
                       aberto o tempo todo.

`MaquinaDeChamada` é a parte pura (testável fora do Windows): recebe
"ativo/inativo" com o horário e devolve início e fim. O fim só vale depois
de alguns segundos seguidos sem sinal — uma pausa de fala não derruba a
gravação no meio da conversa.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("gravador.deteccao")


@dataclass(frozen=True)
class Evento:
    tipo: str            # "inicio" | "fim"
    inicio: float        # time.time() do início
    fim: float | None = None


class MaquinaDeChamada:
    def __init__(self, fim_apos_s: float = 4.0, max_duracao_s: float = 4 * 3600):
        self.fim_apos_s = fim_apos_s
        self.max_duracao_s = max_duracao_s
        self.gravando = False
        self.inicio: float | None = None
        self.ultimo_ativo: float | None = None

    def atualizar(self, ativo: bool, agora: float) -> Evento | None:
        if not self.gravando:
            if ativo:
                self.gravando, self.inicio, self.ultimo_ativo = True, agora, agora
                return Evento("inicio", agora)
            return None
        if ativo:
            self.ultimo_ativo = agora
            if agora - self.inicio >= self.max_duracao_s:
                return self._fechar(agora)
            return None
        if agora - self.ultimo_ativo >= self.fim_apos_s:
            return self._fechar(self.ultimo_ativo)
        return None

    def forcar_fim(self, agora: float) -> Evento | None:
        """Fecha a gravação em andamento (pausa, saída do programa)."""
        if not self.gravando:
            return None
        return self._fechar(agora)

    def _fechar(self, fim: float) -> Evento:
        ev = Evento("fim", self.inicio, fim)
        self.gravando, self.inicio, self.ultimo_ativo = False, None, None
        return ev


def casa_processo(nome_exe: str | None, padroes: list[str]) -> bool:
    """
    >>> casa_processo("Accession Communicator.exe", ["accession"])
    True
    >>> casa_processo("Teams.exe", ["accession", "Vivo Voz"])
    False
    """
    nome = (nome_exe or "").lower()
    if nome.endswith(".exe"):
        nome = nome[:-4]
    return any(p and p.lower() in nome for p in padroes)


# ── Windows ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Sessao:
    fluxo: str        # "microfone" | "saida"
    pid: int
    processo: str
    ativa: bool
    dispositivo: str


def sessoes_windows() -> list[Sessao]:
    """
    Todas as sessões de áudio de todos os dispositivos ativos, de entrada e
    de saída. Só funciona no Windows (pycaw + comtypes).
    """
    import comtypes
    import psutil
    from pycaw.api.audiopolicy import IAudioSessionControl2, IAudioSessionManager2
    from pycaw.utils import AudioUtilities

    saida: list[Sessao] = []
    enum = AudioUtilities.GetDeviceEnumerator()
    for fluxo_id, fluxo in ((1, "microfone"), (0, "saida")):
        colecao = enum.EnumAudioEndpoints(fluxo_id, 1)  # DEVICE_STATE_ACTIVE
        for i in range(colecao.GetCount()):
            dev = colecao.Item(i)
            try:
                dev_id = dev.GetId()
                iface = dev.Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_ALL, None)
                mgr = iface.QueryInterface(IAudioSessionManager2)
                se = mgr.GetSessionEnumerator()
            except Exception as e:  # noqa: BLE001 - um dispositivo esquisito não para os outros
                log.debug("dispositivo %s ignorado: %s", i, e)
                continue
            for j in range(se.GetCount()):
                try:
                    ctl = se.GetSession(j)
                    if ctl is None:
                        continue
                    c2 = ctl.QueryInterface(IAudioSessionControl2)
                    pid = c2.GetProcessId()
                    estado = c2.GetState()
                except Exception:  # noqa: BLE001
                    continue
                if not pid:
                    continue  # sons do sistema
                try:
                    nome = psutil.Process(pid).name()
                except Exception:  # noqa: BLE001
                    nome = f"pid {pid}"
                saida.append(Sessao(fluxo, pid, nome, estado == 1, dev_id))
    return saida


def softphone_ativo(sessoes: list[Sessao], processos: list[str], detectar_por: str) -> bool:
    fluxo = "saida" if detectar_por == "saida" else "microfone"
    return any(s.ativa and s.fluxo == fluxo and casa_processo(s.processo, processos) for s in sessoes)


def softphone_aberto(sessoes: list[Sessao], processos: list[str]) -> bool:
    """O softphone tem QUALQUER sessão (aberto, mesmo sem chamada)?"""
    return any(casa_processo(s.processo, processos) for s in sessoes)
