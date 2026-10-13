"""
HIPO Gravador — ponto de entrada.

.pyw: o Windows abre com pythonw.exe, sem janela de console. Para ver o
diário na tela: python hipo_gravador.pyw --console
"""
import os
import sys

# COM em modo multithread ANTES de qualquer import de comtypes/soundcard.
# A soundcard inicia o COM em MTA; o comtypes, por padrão, em STA. Se os
# dois discordarem na mesma thread, o segundo falha com RPC_E_CHANGED_MODE.
sys.coinit_flags = 0  # COINIT_MULTITHREADED

# A soundcard PRIMEIRO. Ela chama CoInitializeEx no import e trata qualquer
# resposta diferente de S_OK como erro -- inclusive S_FALSE ("o COM desta
# thread ja estava iniciado"), que e o que volta quando o comtypes chegou
# antes. Sintoma: "Microfone FALHOU: Error 0x100000001" (1.0.0). Importada
# aqui, na thread principal e antes de tudo, ela inicia o COM do processo;
# o comtypes recebe S_FALSE depois e aceita normalmente.
try:
    import soundcard  # noqa: F401,E402
except Exception:  # noqa: BLE001 - fora do Windows, ou lib faltando: --testar diz
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.principal import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
