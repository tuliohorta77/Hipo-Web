import os
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


def _legivel(p: Path) -> bool:
    """
    Existe E este processo consegue abrir.

    O `is_file()` sozinho nao basta. O systemd le o EnvironmentFile como root
    e injeta as variaveis no processo; o pydantic-settings, DENTRO do
    processo, abre o mesmo caminho de novo por conta propria. Quando o
    processo roda como um usuario que nao e dono do .env (600), o import
    inteiro morre com PermissionError — mesmo com todas as variaveis ja
    presentes no ambiente e nada faltando.

    Foi o que derrubou o ensaio a seco do fechamento diario em 31/08, com a
    unit declarando User=hipo e o .env sendo de ec2-user.

    Arquivo ilegivel volta a ser tratado como arquivo ausente: se as
    variaveis estiverem no ambiente, sobe normal; se nao estiverem, o erro e
    o ValidationError dizendo QUAL campo falta, que e uma mensagem util —
    e nao um PermissionError sobre um arquivo que talvez nem precisasse.
    """
    return p.is_file() and os.access(p, os.R_OK)


# O padrao e None, e NAO o primeiro candidato: apontar para um arquivo que
# existe e nao pode ser aberto e exatamente o caso que estoura. `None` desliga
# a leitura do dotenv e deixa o pydantic usar so o ambiente — que, sob
# systemd, ja tem tudo.
_ENV_FILE = next((str(p) for p in _CANDIDATOS if _legivel(p)), None)


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
