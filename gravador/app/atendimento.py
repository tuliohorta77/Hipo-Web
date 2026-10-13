"""
Onde a ligação foi ATENDIDA: corta o "chamando" do começo da gravação.

O gravador começa quando o softphone abre o microfone, e isso acontece no
momento em que a pessoa disca, não quando o cliente atende. Os primeiros
segundos são o tom de chamada (o "tuuu... tuuu"), e ninguém quer ouvir isso
nem contar como duração da ligação.

O softphone não diz quando o outro lado atendeu. O que dá para ver é o que
chega no canal do CLIENTE (canal 1, o som que o PC toca):

  * tom de chamada: um tom puro e grave, quase toda a energia numa faixa
    estreita (425 Hz no Brasil; 440 + 480 Hz no padrão americano, que
    alguns softphones tocam), ligado e desligado em cadência;
  * silêncio entre um toque e outro;
  * VOZ (o cliente atendeu, ou a caixa postal falou): energia espalhada de
    100 Hz a 3 kHz, nada parecido com um tom puro.

O atendimento é o começo do primeiro trecho contínuo de "voz" — mais de
0,3 s seguidos que não são nem silêncio nem tom. A gravação passa a valer
meio segundo antes dele, para não comer o "alô".

Ligação que só chamou (ninguém atendeu, sem caixa postal) devolve None e
segue inteira: o HIPO transcreve, não acha fala e marca "Sem conversa" —
a tentativa fica registrada na oportunidade.

Funções puras sobre numpy: testáveis fora do Windows, com tom sintético.
"""
from __future__ import annotations

QUADRO_S = 0.05          # 50 ms por quadro
VOZ_SEGUIDA_S = 0.3      # quanto de "voz" seguida conta como atendeu
FOLGA_ANTES_S = 0.5      # mantém meio segundo antes do atendimento
SILENCIO_RMS = 250       # int16; abaixo disso é silêncio (~ -42 dBFS)
FAIXA_TOM_HZ = (300, 520)
TOM_ENERGIA_MIN = 0.80   # fração da energia na faixa do tom para ser "tom"


def classificar_quadros(sinal, taxa: int):
    """
    Uma letra por quadro de 50 ms: 's' silêncio, 't' tom de chamada, 'v' voz.
    """
    import numpy as np

    n = int(taxa * QUADRO_S)
    if n <= 0 or len(sinal) < n:
        return ""
    total = len(sinal) // n
    quadros = np.asarray(sinal[: total * n], dtype=np.float64).reshape(total, n)
    rms = np.sqrt(np.mean(quadros ** 2, axis=1))
    freqs = np.fft.rfftfreq(n, d=1.0 / taxa)
    faixa = (freqs >= FAIXA_TOM_HZ[0]) & (freqs <= FAIXA_TOM_HZ[1])
    janela = np.hanning(n)
    espectro = np.abs(np.fft.rfft(quadros * janela, axis=1)) ** 2
    energia = espectro.sum(axis=1)
    na_faixa = espectro[:, faixa].sum(axis=1)
    letras = []
    for i in range(total):
        if rms[i] < SILENCIO_RMS:
            letras.append("s")
        elif energia[i] > 0 and na_faixa[i] / energia[i] >= TOM_ENERGIA_MIN:
            letras.append("t")
        else:
            letras.append("v")
    return "".join(letras)


def inicio_do_atendimento(cliente, taxa: int) -> float | None:
    """
    Segundos desde o começo da gravação em que o atendimento começa (já com
    a folga), ou None se o cliente nunca falou nada que não fosse tom.
    """
    letras = classificar_quadros(cliente, taxa)
    seguidos = max(1, int(round(VOZ_SEGUIDA_S / QUADRO_S)))
    pos = letras.find("v" * seguidos)
    if pos < 0:
        return None
    return max(0.0, pos * QUADRO_S - FOLGA_ANTES_S)


def houve_chamando(cliente, taxa: int, ate_s: float) -> bool:
    """Tinha tom de chamada antes do ponto de corte? (só corta se tinha.)"""
    letras = classificar_quadros(cliente, taxa)
    limite = int(ate_s / QUADRO_S)
    return "t" in letras[:limite]
