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
    # Custo do bcrypt. 12 e o padrao e o que vale em producao.
    # O CI baixa para 4 via variavel de ambiente: a suite cria e loga
    # ~1200 usuarios, e a 12 sao ~277ms por operacao (2x por teste) --
    # sozinho isso respondia por ~80% do tempo do job Backend Tests.
    # O hash guarda o proprio custo, entao hashes antigos (12) seguem
    # validando normalmente depois da mudanca.
    BCRYPT_ROUNDS: int = 12
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
    # Vazio = anexos desligados, e a tela nem oferece o botao. Config de
    # recurso acessorio nao pode impedir a API de subir -- mesma regra do
    # SES e da chave da IA logo acima.
    S3_BUCKET_ANEXOS: str = ""
    # Agenda: conta de servico do Google com delegacao em todo o dominio.
    # Vazio = integracao desligada, e a reuniao e criada do mesmo jeito --
    # so nao vira evento. Mesma regra do S3, do SES e da chave da IA acima:
    # config de recurso acessorio nao pode impedir a API de subir, e no CI
    # nenhum desses existe. O passo a passo de como ligar esta no cabecalho
    # de services/google_agenda.py.
    GOOGLE_SA_ARQUIVO: str = ""
    GOOGLE_CALENDAR_FUSO: str = "America/Sao_Paulo"
    TELEMETRIA_RETENCAO_DIAS: int = 90
    TELEMETRIA_ATIVA: bool = True

    # ── Enriquecimento cadastral por CNPJ (014) ─────────────────────
    # Lista separada por virgula, NA ORDEM DE PRECEDENCIA: a primeira
    # fonte que trouxer um campo vence e as seguintes so completam o que
    # faltou. Com "leadcnpj,brasilapi", a paga responde primeiro (e a
    # unica com numero de funcionarios) e a gratuita preenche o resto.
    # Vazio = recurso desligado e a API sobe igual -- mesma regra do S3,
    # do SES e da chave da IA acima.
    ENRIQUECIMENTO_FONTES: str = "brasilapi"
    # Dias que uma consulta bem-sucedida vale antes de ir de novo a fonte.
    # 0 desliga o cache. Em fonte paga isto e dinheiro: reabrir a mesma
    # conta cinco vezes na semana custaria cinco consultas.
    ENRIQUECIMENTO_TTL_DIAS: int = 90

    BRASILAPI_URL: str = "https://brasilapi.com.br/api/cnpj/v1"

    # LeadCNPJ. Sem a chave, a fonte nao entra na lista de habilitadas.
    LEADCNPJ_API_KEY: str = ""
    LEADCNPJ_URL: str = "https://leadcnpj.com.br/api"
    # Header e caminho seguem configuraveis, mas os valores abaixo agora
    # vem da pagina publica leadcnpj.com.br/api-empresas, e nao de palpite:
    #
    #   curl -H "Authorization: Bearer leadcnpj_live_..." \
    #        "https://leadcnpj.com.br/api/v1/empresa/12345678000190?enriquecer=true"
    #
    # O padrao anterior era `empresas/{cnpj}` -- plural e sem o /v1 -- e
    # respondia 400 em toda consulta. Se a API mudar, o ajuste continua
    # sendo uma linha no .env e um restart, nao um deploy. O que NAO se
    # ajusta aqui e a LEITURA do payload: isso e
    # services/enriquecimento/modelo.normalizar_leadcnpj.
    LEADCNPJ_HEADER: str = "Authorization"
    LEADCNPJ_PREFIXO_HEADER: str = "Bearer"
    # `enriquecer=true` e o que dispara o enriquecimento ativo -- sem ele a
    # resposta e so o espelho da Receita, que a BrasilAPI ja da de graca.
    # E tambem onde mora o numero de funcionarios, o unico motivo de a
    # fonte paga existir aqui.
    LEADCNPJ_CAMINHO_CNPJ: str = "v1/empresa/{cnpj}?enriquecer=true"
    # Busca reversa de socio (outras empresas em que ele participa).
    #
    # Fica VAZIO porque a LeadCNPJ nao tem esse endpoint: a API publica
    # deles expoe consulta por CNPJ, busca por filtros firmograficos
    # (UF, CNAE, porte, capital...) e enriquecimento em lote. Nenhuma
    # dessas responde "em que outras empresas este CPF aparece". A tela
    # segue mostrando so a busca DENTRO da base do HIPO, dizendo em voz
    # alta que nao procurou fora.
    LEADCNPJ_CAMINHO_SOCIO: str = ""

    class Config:
        env_file = _ENV_FILE


settings = Settings()

# Trava de seguranca: custo baixo e recurso de teste. Se o .env de
# producao vier com BCRYPT_ROUNDS rebaixado (copiado do CI, por engano),
# o valor e ignorado e volta para 12 -- em vez de subir a API gravando
# senha fraca em silencio.
if settings.ENVIRONMENT == "production" and settings.BCRYPT_ROUNDS < 12:
    settings.BCRYPT_ROUNDS = 12
