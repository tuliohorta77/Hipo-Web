"""
HIPO — Entry point da API.

O módulo 'crm' é compartilhado — todo cargo válido enxerga contas e
contatos, o que é o que impede cadastro duplicado de CNPJ. O filtro por
envolvimento vale para oportunidades, e é aplicado no repositório, não aqui.
"""
import asyncio
import threading
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import resolver_origens_cors, settings
from database import criar_pool
from services import observabilidade
from services.instancia import empresa_nome, empresa_sigla

VERSAO = "2.5.0"

# Sentry ANTES de FastAPI(...): as integracoes de Starlette/FastAPI se
# penduram na classe na hora do init. Sem SENTRY_DSN no .env, nao faz nada.
# Ver services/observabilidade.py.
observabilidade.iniciar(
    settings.SENTRY_DSN,
    ambiente=settings.SENTRY_AMBIENTE
    or observabilidade.ambiente_padrao(settings.ENVIRONMENT, empresa_sigla()),
    release=f"hipo-api@{VERSAO}",
    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    instancia=empresa_sigla(),
)
from middleware.telemetria import TelemetriaMiddleware, buffer, descarga_periodica
from routers import (
    carreira,
    auth,
    crm_agenda,
    crm_anexos,
    crm_ao_vivo,
    crm_avaliacao,
    crm_contas,
    crm_contatos,
    crm_contratos,
    crm_dominio,
    crm_emails,
    crm_enriquecimento,
    crm_oportunidade_contatos,
    crm_oportunidades,
    crm_parceiros,
    crm_propostas,
    crm_prospeccao,
    crm_relatorios,
    crm_tarefas,
    monitor,
    pdi,
    roleplay,
    rper,
    telemetria,
    uc,
    uc_estudio,
    webhooks,
)
from routers.permissions import (
    requer_modulo,
    requer_prospeccao,
    requer_qualquer_modulo,
)

@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """
    Sobe a descarga periódica da telemetria e a encerra com uma última
    descarga.

    A TASK. Sem ela, o buffer só é avaliado quando chega requisição: a última
    ação do dia ficaria em memória até alguém mexer no sistema de novo — e o
    fechamento das 03:10 fecharia o dia sem ela.

    A DESCARGA FINAL. O deploy reinicia o serviço a cada push. Sem esta linha,
    todo evento ainda em memória some no restart.

    A REFERÊNCIA VIVA em `tarefa` não é decorativa: o event loop guarda só
    referência fraca para tasks, e uma task sem dono pode ser coletada no meio
    da execução. Manter a variável no escopo do lifespan resolve.

    O conftest sobe o cliente de teste com lifespan DESABILITADO (para não
    criar conexão asyncpg no event loop errado), então nada disto roda na
    suíte — e é justamente o que impede a descarga automática de disputar lock
    com o TRUNCATE CASCADE da fixture db_conn. Os testes exercitam
    `descarga_periodica` direto, com um buffer próprio.
    """
    # POOL ASYNCPG. Um por worker. Se nao subir (banco fora no boot, rede
    # travada), fica None e database.get_conn cai no connect-por-request --
    # o modo que foi padrao ate esta versao. Degradar e melhor que recusar
    # subir: com a API fora, o nginx devolve 502 para tudo, login incluso.
    log_db = logging.getLogger("hipo.db")
    app.state.pool = None
    try:
        app.state.pool = await criar_pool()
        log_db.info(
            "pool asyncpg criado: min=%d max=%d",
            settings.DB_POOL_MIN, settings.DB_POOL_MAX,
        )
    except Exception as e:
        log_db.warning("pool asyncpg nao subiu (%s); usando connect por request", e)

    tarefa = None
    if settings.TELEMETRIA_ATIVA:
        tarefa = asyncio.create_task(descarga_periodica(buffer))

    # PROPOSTA (052): o PDF dos slides fixos (os institucionais) e montado
    # uma vez e fica em cache. Fazer isso na subida, numa thread, poupa os
    # ~10 s da primeira proposta depois de cada deploy. Daemon: nao segura
    # o desligamento; se falhar, a primeira proposta monta sozinha.
    from services import proposta_render
    threading.Thread(
        target=proposta_render.aquecer_cache, name="aquecer-pdf-proposta", daemon=True,
    ).start()

    yield

    if tarefa is not None:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa
    try:
        gravados = await buffer.descarregar()
        if gravados:
            logging.getLogger("hipo.telemetria").info(
                "descarga no desligamento: %d evento(s)", gravados
            )
    except Exception as e:  # pragma: no cover - blindagem de shutdown
        logging.getLogger("hipo.telemetria").warning(
            "descarga no desligamento falhou: %s", e
        )

    # Pool fecha POR ULTIMO, depois da descarga final da telemetria. E volta
    # para None: o `app` e o mesmo objeto durante toda a suite de testes, e
    # um pool fechado esquecido em app.state faria todo teste seguinte
    # tentar `acquire` num pool morto em vez de cair no fallback.
    pool, app.state.pool = app.state.pool, None
    if pool is not None:
        await pool.close()
        log_db.info("pool asyncpg fechado")


app = FastAPI(
    title="HIPO API",
    description="Hipotálamo Inteligente de Processos e Operações",
    version=VERSAO,
    lifespan=ciclo_de_vida,
)
# Sem lifespan (suite de testes) ninguem cria o pool; o atributo existe
# desde o import para o estado ser explicito, e nao um getattr que adivinha.
app.state.pool = None

# Telemetria ANTES do CORS na lista = camada mais externa da pilha (o
# Starlette monta os middlewares na ordem inversa do add_middleware). Assim a
# duracao medida inclui todo o trabalho da request, e nao so o miolo dela.
# Desligavel por .env: TELEMETRIA_ATIVA=false sobe a API sem captura nenhuma.
if settings.TELEMETRIA_ATIVA:
    app.add_middleware(TelemetriaMiddleware)

# CORS. Ver `resolver_origens_cors` em config.py: em producao vale o dominio
# do HIPO (ou a lista do .env, sem curinga); fora dela, "*". O front chama a
# API pela mesma origem, entao isto so afeta cliente de OUTRA origem.
_cors_bruto = settings.CORS_ORIGINS
if settings.ENVIRONMENT == "production" and "*" in [o.strip() for o in _cors_bruto.split(",")]:
    logging.getLogger("hipo").warning("CORS_ORIGINS com '*' em producao: curinga ignorado")

app.add_middleware(
    CORSMiddleware,
    allow_origins=resolver_origens_cors(_cors_bruto, settings.ENVIRONMENT),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth é livre: todo cargo precisa logar, ler /auth/me e trocar a senha.
app.include_router(auth.router, prefix="/auth", tags=["auth"])

app.include_router(
    crm_contas.router,
    prefix="/crm/contas", tags=["CRM - Contas"],
    dependencies=[Depends(requer_modulo("crm"))],
)

app.include_router(
    crm_contatos.router,
    prefix="/crm/contatos", tags=["CRM - Contatos"],
    dependencies=[Depends(requer_modulo("crm"))],
)

app.include_router(
    crm_oportunidades.router,
    prefix="/crm/oportunidades", tags=["CRM - Oportunidades"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# O comite da oportunidade (045 -- ABM / multithreading). Mesmo prefixo e
# mesmo modulo: e a mesma oportunidade, vista pelas pessoas da conta. Router
# separado porque crm_oportunidades.py ja passa de 60 KB, e porque crm_tarefas
# precisa dos helpers daqui sem importar o modulo de oportunidades (que
# importa crm_tarefas -- seria ciclo).
app.include_router(
    crm_oportunidade_contatos.router,
    prefix="/crm/oportunidades", tags=["CRM - Contatos da oportunidade"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# Tarefas ficam num prefixo proprio e nao aninhadas em /oportunidades/{id}
# porque a agenda por pessoa (a "proxima tarefa" da Etapa 5) vai consultar por
# responsavel, sem oportunidade no caminho.
app.include_router(
    crm_tarefas.router,
    prefix="/crm/tarefas", tags=["CRM - Tarefas"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# Agenda de reunioes. Prefixo proprio, e nao aninhado em /crm/tarefas,
# porque a grade e consultada por ANFITRIAO e SEMANA -- nunca a partir de
# uma tarefa. Mesmo raciocinio que tirou /crm/tarefas de dentro de
# /crm/oportunidades na Sprint 5.
#
# Modulo 'crm', e nao um modulo proprio como 'parceiros': marcar reuniao
# atravessa toda a operacao. O SDR agenda para o EV, o EV conduz, o EP
# entra como participante e a gestao acompanha -- nenhum desses ficaria de
# fora, entao um modulo novo so acrescentaria uma lista para manter. O
# recorte por pessoa acontece DENTRO da tela (a grade abre no usuario
# logado), que e onde ele significa alguma coisa.
app.include_router(
    crm_agenda.router,
    prefix="/crm/agenda", tags=["CRM - Agenda"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# Transcricao AO VIVO da reuniao (prova de conceito do copiloto). Mesmo
# prefixo e mesmo modulo da agenda: e a mesma reuniao, vista durante a call.
# Router separado porque pode sair inteiro se o reconhecimento de voz do
# navegador nao servir -- ver routers/crm_ao_vivo.py.
app.include_router(
    crm_ao_vivo.router,
    prefix="/crm/agenda", tags=["CRM - Reuniao ao vivo"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# Scorecard da reuniao contra o Roteiro de Vendas (030). Mesmo prefixo e
# mesmo modulo: e a mesma reuniao, avaliada depois da call. O ajuste e o
# selo sao checados por cargo dentro do router (gestao).
app.include_router(
    crm_avaliacao.router,
    prefix="/crm/agenda", tags=["CRM - Scorecard da reuniao"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# Parceiros é o ÚNICO router fora do módulo 'crm'. Cultivar a relação com quem
# indica é trabalho do EC (e da gestão, que remaneja carteira) — SDR, EV e EP
# não têm o que fazer aqui. É a diretriz "uma tela por função" aplicada à
# permissão, não só ao layout.
app.include_router(
    crm_parceiros.router,
    prefix="/crm/parceiros", tags=["CRM - Parceiros"],
    dependencies=[Depends(requer_modulo("parceiros"))],
)

# Propostas. Prefixo proprio, e nao aninhado em /crm/oportunidades, porque o
# download (/crm/propostas/{id}/arquivo) e endereçado pela proposta: o link do
# arquivo precisa sobreviver a um copiar-e-colar sem carregar o id da
# oportunidade junto.
app.include_router(
    crm_propostas.router,
    prefix="/crm", tags=["CRM - Propostas"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# E-mail comercial pela Gmail API (050): primeiro contato e envio de
# proposta, da caixa do vendedor. Prefixo /crm como as propostas: os
# modelos (/crm/email/modelos) nao sao de uma oportunidade so. A edicao dos
# modelos e checada por cargo dentro do router (gestao).
app.include_router(
    crm_emails.router,
    prefix="/crm", tags=["CRM - E-mail"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# Contrato com assinatura eletronica pela Autentique (053). Prefixo /crm
# como as propostas: o contrato nasce de uma versao de proposta
# (/crm/propostas/{id}/contratos) e depois e enderecado por ele mesmo
# (/crm/contratos/{id}). Modulo 'crm': quem manda proposta manda contrato,
# e modulo novo so valeria depois de todo mundo relogar. Quem pode cancelar
# e decidido dentro da rota.
app.include_router(
    crm_contratos.router,
    prefix="/crm", tags=["CRM - Contratos"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# Webhooks de servicos externos: o UNICO router sem login. Quem prova a
# origem e a assinatura HMAC do corpo, conferida dentro da rota (ver
# routers/webhooks.py). Publico em /api/webhooks/autentique.
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])

# Anexos de tarefa. Prefixo /crm e nao /crm/tarefas: as rotas de leitura e
# remocao sao enderecadas pelo ID DO ANEXO, sem repetir a tarefa no caminho,
# porque esse endereco viaja (vai para o <img src>, para um copiar-e-colar).
# Mesma escolha das propostas, logo acima.
app.include_router(
    crm_anexos.router,
    prefix="/crm", tags=["CRM - Anexos"],
    dependencies=[Depends(requer_modulo("crm"))],
)

# Listas de domínio (verticais, origens, concorrentes, motivos). Mesmo módulo:
# quem cadastra conta precisa poder criar a vertical dela no mesmo formulário.
app.include_router(
    crm_dominio.router,
    prefix="/crm/dominio", tags=["CRM - Domínio"],
    dependencies=[Depends(requer_modulo("crm"))],
)


# Enriquecimento cadastral por CNPJ. Módulo 'crm' e não um módulo próprio:
# quem cadastra conta é quem usa o botão de buscar na Receita, e são os
# mesmos cargos que já veem contas. Módulo novo só refletiria depois de
# todo mundo relogar, em troca de nenhuma separação real.
#
# Prefixo próprio, e não aninhado em /crm/contas, porque a consulta por
# CNPJ acontece ANTES de a conta existir — no formulário de cadastro, não
# em cima de um registro. Mesma escolha que tirou /crm/tarefas de dentro
# de /crm/oportunidades.
app.include_router(
    crm_enriquecimento.router,
    prefix="/crm/enriquecimento", tags=["CRM - Enriquecimento"],
    dependencies=[Depends(requer_modulo("crm"))],
)



# Prospeccao: fatia da base de Dados Abertos do CNPJ (022) e o "puxar para
# o HIPO". Modulo 'crm' + restricao por CARGO (SDR e gestao), sem modulo
# novo -- modulo novo so reflete depois de relogin e quebraria os asserts de
# modulos_do_cargo. A base e fonte de consulta; o que entra no CRM entra
# pelo POST /puxar, com autoria. Ver routers/crm_prospeccao.py.
app.include_router(
    crm_prospeccao.router,
    prefix="/crm/prospeccao", tags=["CRM - Prospecção"],
    dependencies=[Depends(requer_modulo("crm")), Depends(requer_prospeccao)],
)

# Relatorios: tabela dinamica sobre a base + relatorios salvos no perfil.
# Modulo 'crm' e nao um modulo proprio: todo cargo monta relatorio, e o que
# muda entre cargos e o RECORTE dos dados (services/permissao.py), aplicado
# dentro do motor -- gestao ve a base inteira, operacional ve o que e seu.
# Modulo novo so valeria depois de todo mundo relogar.
app.include_router(
    crm_relatorios.router,
    prefix="/crm/relatorios", tags=["CRM - Relatórios"],
    dependencies=[Depends(requer_modulo("crm"))],
)


# Monitor: o painel de parede. Modulo 'crm' e nao um modulo proprio — todo
# cargo valido tem 'crm', a tela fica numa TV para a equipe inteira, e
# modulo novo so valeria depois de todo mundo relogar. Quem barra a ESCRITA
# de metas e feriados e `requer_gestao`, dentro do router.
#
# 'crm' OU 'monitor': o modulo 'monitor' e exclusivo do cargo Monitor, a conta
# de TV que so abre o painel. Os demais cargos continuam entrando pelo 'crm'
# -- assim ninguem precisa relogar e os asserts de modulos_do_cargo ficam
# como estao.
app.include_router(
    monitor.router,
    prefix="/monitor", tags=["Monitor"],
    dependencies=[Depends(requer_qualquer_modulo(["crm", "monitor"]))],
)


# RPeR: o PPT da Reuniao de Planejamento e Resultados, gerado do HIPO, e as
# metas por squad e por pessoa que ele cobra. Modulo 'crm' no router e
# `requer_gestao` em CADA rota: o RPeR mostra o resultado individual de cada
# pessoa, e modulo novo so valeria depois de todo mundo relogar. Mesma
# escolha das metas do Monitor.
app.include_router(
    rper.router,
    prefix="/rper", tags=["RPeR"],
    dependencies=[Depends(requer_modulo("crm"))],
)


# Universidade Corporativa: trilhas por pilar (Tecnica, Metodo, Energia), o
# manual da funcao e o andamento de cada pessoa. Modulo 'crm' e nao um
# modulo proprio -- todo cargo valido aprende, e modulo novo so valeria
# depois de todo mundo relogar. Mesma escolha do Monitor e do RPeR.
#
# Dois routers: /uc e a tela de quem aprende; /uc/estudio e o conteudo e a
# visao do time, barrados por gestao DENTRO do router (requer_gestao_uc).
# Ver claude/universidade-corporativa.md.
app.include_router(
    uc_estudio.router,
    prefix="/uc/estudio", tags=["UC - Estudio"],
    dependencies=[Depends(requer_modulo("crm"))],
)
#
# /uc aceita 'crm' OU 'uc': o modulo 'uc' e exclusivo do cargo UC, a conta
# que so estuda. O estudio continua so no 'crm' (e requer_gestao_uc dentro).
app.include_router(
    uc.router,
    prefix="/uc", tags=["UC - Universidade Corporativa"],
    dependencies=[Depends(requer_qualquer_modulo(["crm", "uc"]))],
)


# Carreira (Universidade, PDI, Desempenho). O Desempenho e de cada pessoa:
# os indicadores da RPeR contra as metas individuais do mes. Modulo 'crm',
# como a UC e o RPeR; quem ve a pessoa dos outros e decidido dentro da rota
# (so a gestao, em modo leitura).
app.include_router(
    carreira.router,
    prefix="/carreira", tags=["Carreira"],
    dependencies=[Depends(requer_modulo("crm"))],
)
# PDI (segunda aba da Carreira): mesmo prefixo e mesmo modulo. Quem monta
# (gestao) e quem conclui (o dono) e decidido dentro de cada rota.
app.include_router(
    pdi.router,
    prefix="/carreira", tags=["Carreira"],
    dependencies=[Depends(requer_modulo("crm"))],
)


# Roleplay com IA (terceira aba da Carreira, 034): mesmo prefixo e mesmo
# modulo do PDI. Quem treina (quiz do roteiro aprovado) e quem ve a sessao
# dos outros (gestao, em leitura) e decidido dentro de cada rota.
app.include_router(
    roleplay.router,
    prefix="/carreira", tags=["Carreira"],
    dependencies=[Depends(requer_modulo("crm"))],
)


# Telemetria e leitura de gestao: quem opera nao precisa ver quantas acoes o
# colega fez. Ver a nota em routers/permissions.py.
app.include_router(
    telemetria.router,
    prefix="/telemetria", tags=["Telemetria"],
    dependencies=[Depends(requer_modulo("telemetria"))],
)


@app.get("/health")
async def health():
    # `pool`: True quando este worker usa o pool asyncpg; False quando caiu
    # no connect-por-request (banco fora no boot). E a conferencia do deploy:
    # o log INFO de "pool criado" nao chega ao journal, porque o uvicorn so
    # configura os proprios loggers.
    return {
        "status": "ok",
        "sistema": "HIPO",
        "versao": app.version,
        "pool": app.state.pool is not None,
        # 032: True quando este worker manda erro para o Sentry. E a
        # conferencia de que o DSN entrou e o pacote esta instalado.
        "sentry": observabilidade.ativo(),
        # 046: qual base respondeu. E a conferencia do deploy em cada
        # instancia -- o mesmo codigo responde em hipogestao.com.br e em
        # mos.hipogestao.com.br, e o smoke precisa provar que cada dominio
        # caiu no servico (e no banco) certo.
        "empresa": empresa_nome(),
        "instancia": empresa_sigla() or None,
    }
