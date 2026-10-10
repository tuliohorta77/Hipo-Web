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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.principal import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
