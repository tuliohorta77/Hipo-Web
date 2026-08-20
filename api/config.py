from pathlib import Path

from pydantic_settings import BaseSettings

# Caminho absoluto do .env, resolvido a partir deste arquivo.
#
# Era relativo (".env") e isso quebrava todo script rodado a mao: o systemd
# injeta o ambiente por EnvironmentFile e nunca sentiu, mas
# `python -m scripts.seed_usuarios` de dentro de api/ estourava em JWT_SECRET
# porque o .env mora um nivel acima. Procura nos dois lugares — api/.env
# (dev) e app/.env (producao) — e fica com o primeiro que existir.
_CANDIDATOS = [
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / ".env",
]
_ENV_FILE = next((str(p) for p in _CANDIDATOS if p.is_file()), str(_CANDIDATOS[0]))


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_EXPIRE_HOURS: int = 24
    UPLOAD_DIR: str = "/home/hipo/app/uploads"
    MAX_UPLOAD_MB: int = 50
    ENVIRONMENT: str = "production"
    BRIDGE_TOKEN: str = ""

    # ── Telemetria e fechamento diario ──────────────────────────────
    # Vazio = desligado. Nenhum destes campos e obrigatorio: sem chave a IA
    # nao roda, sem remetente o e-mail nao sai, e a API sobe igual nos dois
    # casos. Config de recurso acessorio nao pode impedir o sistema de subir.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5"
    SES_REMETENTE: str = ""
    RELATORIO_DESTINATARIOS: str = ""
    AWS_REGION: str = "eu-central-1"
    TELEMETRIA_RETENCAO_DIAS: int = 90
    TELEMETRIA_ATIVA: bool = True

    class Config:
        env_file = _ENV_FILE


settings = Settings()
