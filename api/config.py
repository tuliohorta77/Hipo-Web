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

    # -- Instancia (046) -------------------------------------------------
    # O mesmo codigo roda mais de uma base: hipogestao.com.br (Controller
    # MedSeg) e mos.hipogestao.com.br (MOS), cada uma com banco, .env e
    # servico proprios. Estes tres campos sao o que muda de uma para outra
    # no que o CLIENTE e a equipe leem.
    #
    # Os padroes reproduzem a base principal tal como era antes da 046: com
    # o .env da MedSeg intocado, nada muda -- convite da agenda, nome do
    # RPeR, assunto do e-mail e modelo da proposta saem identicos.
    #
    # EMPRESA_NOME: vai no titulo do convite do Google Calendar e no nome do
    #   arquivo do RPeR.
    # EMPRESA_SIGLA: rotulo curto da instancia. Vazio = base principal. Com
    #   valor, aparece ao lado do logo, no titulo da aba do navegador e no
    #   assunto do fechamento diario ("HIPO MOS 15/09 -- ...") -- quem opera
    #   as duas bases precisa saber em qual esta antes de clicar.
    # PROPOSTA_MODELO_ARQUIVO: PPTX da proposta comercial. Vazio = o modelo
    #   versionado em api/templates/proposta_modelo.pptx.
    EMPRESA_NOME: str = "Controller MedSeg"
    EMPRESA_SIGLA: str = ""
    PROPOSTA_MODELO_ARQUIVO: str = ""

    # ── Telemetria e fechamento diario ──────────────────────────────
    # Vazio = desligado. Nenhum destes campos e obrigatorio: sem chave a IA
    # nao roda, sem remetente o e-mail nao sai, e a API sobe igual nos dois
    # casos. Config de recurso acessorio nao pode impedir o sistema de subir.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5"
    # Modelo do Scorecard da reuniao (deploy 030). Vazio = o padrao de
    # services/avaliacao_roteiro.py. Declarado aqui porque o Settings e
    # extra="forbid": sem esta linha, por ANTHROPIC_MODEL_AVALIACAO no .env
    # derrubaria a API inteira no import, em vez de trocar o modelo.
    ANTHROPIC_MODEL_AVALIACAO: str = ""
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

    # Econodata. Entrou por UM dado: quadro de pessoal. Todo o resto do
    # cadastro vem da BrasilAPI, de graca, da mesma base da Receita.
    ECONODATA_API_KEY: str = ""
    ECONODATA_URL: str = "https://api.econodata.com.br/v4"
    ECONODATA_CAMINHO: str = "companies/search"
    # A cobranca deles e por TIPO DE INFORMACAO pedida em cada empresa, e
    # os blocos sao: cadastro, estrategico, perfilNegocio, contatosBasicos,
    # contatosAvancados. Pedimos so `estrategico`, que e onde mora o numero
    # de funcionarios -- os outros seriam pagar por dado que a BrasilAPI ja
    # deu. Se eles renomearem o bloco, o conserto e uma linha no .env.
    ECONODATA_BLOCOS: str = "estrategico"

    # Oportunidados. Entrou pelo mesmo unico dado que a Econodata --
    # quadro de pessoal -- e pela diferenca que decidiu a troca: a origem
    # e declaracao trabalhista (RAIS/eSocial), confirmada pelo fornecedor
    # em 23/09/2026, e nao inferencia de LinkedIn. Por isso o campo vem
    # como CONTAGEM EXATA ("94"), e nao como faixa.
    #
    # O campo so aparece na resposta quando o plano tem a feature ligada
    # (`EmployeeCountFeature`). Sem ela a chave nem existe no JSON -- o
    # que e diagnostico diferente de "Sem dados oficiais", que e a fonte
    # declarando que nao sabe aquela empresa.
    OPORTUNIDADOS_API_TOKEN: str = ""
    OPORTUNIDADOS_URL: str = "https://app.oportunidados.com.br/api/v1"
    # `{cnpj}` e substituido em tempo de chamada.
    OPORTUNIDADOS_CAMINHO: str = "brazilian_companies/{cnpj}/company"

    # -- CORS ------------------------------------------------------------
    # Lista separada por virgula. VAZIO e o valor normal, e NAO derruba a API:
    # quem decide o que vazio significa e `resolver_origens_cors`, abaixo --
    # em producao vira o dominio do HIPO, fora dela vira "*".
    #
    # Por que nao travar a subida quando vem vazio: o front fala com a API
    # pela MESMA origem (nginx em producao, proxy do Vite em dev; ver
    # web/vite.config.js e o baseURL "/api" de web/src/api.js). O navegador
    # nem consulta CORS para essas chamadas. Uma trava aqui so serviria para
    # tirar o sistema do ar por uma config que nao afeta nenhum usuario --
    # e, com o `extra="forbid"`, nao existiria ordem de deploy que a
    # satisfizesse (ver claude/env-ordem-de-deploy-e-extra-forbid.md).
    CORS_ORIGINS: str = ""

    # -- Pool asyncpg -----------------------------------------------------
    # Um pool POR WORKER, criado no lifespan de main.py. O uvicorn roda
    # --workers 4, entao o teto real de conexoes da API no RDS e
    # 4 x DB_POOL_MAX (20 com o padrao), fora telemetria e fechamento, que
    # abrem conexao propria.
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 5
    # Teto por comando, em segundos. 0 = sem teto, que e o comportamento de
    # antes do pool. Relatorio e RPeR fazem consulta pesada; um teto curto
    # aqui viraria erro 500 onde hoje so ha lentidao.
    DB_COMMAND_TIMEOUT_S: int = 0

    # -- Limite de tentativas de login (032) -----------------------------
    # Falhas dentro da janela. O limite por E-MAIL protege a conta de quem
    # tem a senha atacada; o por IP pega quem varre varios e-mails a partir
    # da mesma maquina. Sucesso zera a contagem daquele e-mail (a falha
    # anterior ao acerto nao conta contra a pessoa), mas nao a do IP.
    # LOGIN_LIMITE_ATIVO=false desliga tudo -- escotilha de emergencia, nao
    # configuracao normal.
    LOGIN_LIMITE_ATIVO: bool = True
    LOGIN_JANELA_MIN: int = 15
    LOGIN_MAX_FALHAS_EMAIL: int = 5
    LOGIN_MAX_FALHAS_IP: int = 20
    # Linhas de login_tentativas mais velhas que isto saem no fechamento
    # diario, junto com a retencao da telemetria.
    LOGIN_RETENCAO_DIAS: int = 180

    # -- Observabilidade (Sentry) ----------------------------------------
    # Vazio = desligado, e a API sobe igual -- mesma regra do SES, do S3 e
    # da chave da IA. O DSN nao e segredo de verdade (vai ate no front de
    # quem usa Sentry no navegador), mas mora no .env para cada instancia
    # (principal, MOS) mandar para o projeto certo.
    SENTRY_DSN: str = ""
    # Vazio = vale ENVIRONMENT + sigla da instancia ("production",
    # "production-mos"). E o filtro de ambiente na tela do Sentry.
    SENTRY_AMBIENTE: str = ""
    # Fracao das requests que viram trace de performance. 0 = so erros,
    # que e o que o plano gratuito comporta sem estourar a cota.
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    # -- Roleplay com IA (Carreira, 034) ----------------------------------
    # Chave do Gemini (AI Studio, plano pre-pago). Vazio = roleplay
    # desligado: a tela explica e a API sobe igual -- mesma regra do S3,
    # do SES e da chave da IA. A chave NUNCA vai ao navegador: o backend
    # emite um token efemero por conexao (services/roleplay.py).
    GEMINI_API_KEY: str = ""
    # Modelo de voz do Live. O 3.8-live seguiu a persona no PoC de
    # 07/10/2026; o 3.1-flash-live despejava as dores de uma vez.
    ROLEPLAY_MODELO_VOZ: str = "gemini-3.8-live"
    # Teto de gasto estimado do mes (US$, todas as sessoes). 0 = sem teto.
    ROLEPLAY_ORCAMENTO_MES_USD: float = 30.0
    # Sessoes por pessoa por dia (a gestao nao conta). 0 = sem limite.
    ROLEPLAY_LIMITE_DIA: int = 2
    # Duracao maxima de uma sessao; a completa e de 45 min.
    ROLEPLAY_DURACAO_MAX_MIN: int = 55

    # -- Contrato com assinatura eletronica (053) ------------------------
    # Autentique (API GraphQL). Sem token = envio desligado: a aba Contrato
    # diz o que falta e a API sobe igual -- mesma regra do S3, do SES e da
    # chave da IA. O token e o segredo do webhook ficam so no .env.
    AUTENTIQUE_API_TOKEN: str = ""
    AUTENTIQUE_URL: str = "https://api.autentique.com.br/v2/graphql"
    # Segredo do endpoint cadastrado no painel da Autentique
    # (https://hipogestao.com.br/api/webhooks/autentique). Vazio = webhook
    # recusa tudo (401) e o estado anda so pelo timer de sincronizacao.
    AUTENTIQUE_WEBHOOK_SEGREDO: str = ""
    # Documento de teste da Autentique: nao gasta credito, some em alguns
    # dias. Fora de producao e SEMPRE sandbox, valha o que valer aqui --
    # um teste local nao pode mandar contrato de verdade para cliente.
    AUTENTIQUE_SANDBOX: bool = False
    # Quem assina pela CONTRATADA. Vazio = envio desligado: sem padrao de
    # proposito, porque o mesmo codigo roda a instancia MOS, e um padrao da
    # MedSeg mandaria o contrato da MOS para o CEO errado.
    CONTRATO_CONTRATADA_NOME: str = ""
    CONTRATO_CONTRATADA_EMAIL: str = ""
    # .docx do contrato. Vazio = api/templates/contrato_modelo.docx (o da
    # Controller MedSeg). Instancia com sigla (MOS) e obrigada a apontar o
    # proprio modelo -- ver services/autentique.problemas().
    CONTRATO_MODELO_ARQUIVO: str = ""

    class Config:
        env_file = _ENV_FILE


# Origens do HIPO em producao. Usadas quando CORS_ORIGINS vem vazio e
# ENVIRONMENT e production -- ou seja, o caso normal do servidor.
ORIGENS_PRODUCAO = (
    "https://hipogestao.com.br",
    "https://www.hipogestao.com.br",
)


def resolver_origens_cors(valor: str, ambiente: str) -> list[str]:
    """
    Converte CORS_ORIGINS na lista que vai para o CORSMiddleware.

    - Itens separados por virgula; espaco e barra final caem fora (origem
      nunca tem barra final, e "https://x.com/" nao casaria com nada).
    - PRODUCAO: "*" e descartado -- curinga em producao e recurso de teste
      copiado por engano, mesma logica da trava do BCRYPT_ROUNDS. Se nao
      sobrar nada, vale ORIGENS_PRODUCAO.
    - FORA DE PRODUCAO: vazio vira ["*"]; lista explicita vale como veio.

    Pura, sem ler `settings`, para ser testada sem mexer no ambiente.
    """
    itens = [o.strip().rstrip("/") for o in (valor or "").split(",")]
    itens = [o for o in itens if o]
    if ambiente == "production":
        itens = [o for o in itens if o != "*"]
        return itens or list(ORIGENS_PRODUCAO)
    return itens or ["*"]


settings = Settings()

# Trava de seguranca: custo baixo e recurso de teste. Se o .env de
# producao vier com BCRYPT_ROUNDS rebaixado (copiado do CI, por engano),
# o valor e ignorado e volta para 12 -- em vez de subir a API gravando
# senha fraca em silencio.
if settings.ENVIRONMENT == "production" and settings.BCRYPT_ROUNDS < 12:
    settings.BCRYPT_ROUNDS = 12
