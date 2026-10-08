"""
HIPO -- confere se o roleplay consegue falar com o Gemini. Nao grava nada.

Pede ao Google um token efemero igual ao da tela (persona do primeiro
cenario, modelo e configuracao do .env) e diz se deu certo. A chave nunca
e impressa.

Uso (na EC2, como o usuario do app; o config.py le o .env sozinho):
    sudo -u hipo bash -c 'cd /home/hipo/app/api && python3 -m scripts.roleplay_diagnostico'

No Windows, antes do deploy (pede a chave sem mostrar; nao toca no banco):
    cd api; $env:DATABASE_URL="postgresql://local/nada"; $env:JWT_SECRET="local"
    venv\Scripts\python.exe -m scripts.roleplay_diagnostico

Saida 0 = token emitido; 1 = sem chave; 2 = o Google recusou.
"""
from __future__ import annotations

import asyncio
import sys


async def _main() -> int:
    from config import settings
    from services import roleplay as regras
    from services.roleplay_cenarios import CENARIOS, montar_instrucao

    if not settings.GEMINI_API_KEY and sys.stdin.isatty():
        import getpass
        settings.GEMINI_API_KEY = getpass.getpass("GEMINI_API_KEY (nao aparece): ").strip()
    if not settings.GEMINI_API_KEY:
        print("GEMINI_API_KEY vazia no .env: roleplay desligado.")
        return 1
    chave = settings.GEMINI_API_KEY
    print(f"Chave: {len(chave)} caracteres, comeca com {chave[:3]}...")
    print(f"Modelo: {settings.ROLEPLAY_MODELO_VOZ}")
    cid, cenario = next(iter(CENARIOS.items()))
    setup = regras.setup_live(settings.ROLEPLAY_MODELO_VOZ, montar_instrucao(cenario), cenario["voz"])
    try:
        token = await regras.emitir_token(setup)
    except regras.GeminiIndisponivel as e:
        print(f"FALHOU: {e}" + (" (cobranca/cota: confira o credito no AI Studio)" if e.sem_saldo else ""))
        return 2
    print(f"OK: token emitido para o cenario {cid} ({token[:16]}...).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
