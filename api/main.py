"""
HIPO — Entry point da API.

O módulo 'crm' é compartilhado — todo cargo válido enxerga contas e
contatos, o que é o que impede cadastro duplicado de CNPJ. O filtro por
envolvimento vale para oportunidades, e é aplicado no repositório, não aqui.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from middleware.telemetria import TelemetriaMiddleware, buffer
from routers import (
    auth, crm_contas, crm_contatos, crm_dominio, crm_oportunidades,
    crm_parceiros, crm_tarefas, telemetria,
)
from routers.permissions import requer_modulo

@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """
    Descarrega o buffer de telemetria no desligamento.

    O deploy reinicia o serviço a cada push. Sem isto, todo evento ainda em
    memória some no restart — e numa operação pequena, que raramente enche o
    lote, isso é quase toda a telemetria do dia.

    O conftest sobe o cliente de teste com lifespan DESABILITADO (para não
    criar conexão asyncpg no event loop errado), então este hook não roda na
    suíte. É intencional: quem testa a descarga chama `descarregar()` na mão.
    """
    yield
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


app = FastAPI(
    title="HIPO API",
    description="Hipotálamo Inteligente de Processos e Operações",
    version="2.5.0",
    lifespan=ciclo_de_vida,
)

# Telemetria ANTES do CORS na lista = camada mais externa da pilha (o
# Starlette monta os middlewares na ordem inversa do add_middleware). Assim a
# duracao medida inclui todo o trabalho da request, e nao so o miolo dela.
# Desligavel por .env: TELEMETRIA_ATIVA=false sobe a API sem captura nenhuma.
if settings.TELEMETRIA_ATIVA:
    app.add_middleware(TelemetriaMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# Tarefas ficam num prefixo proprio e nao aninhadas em /oportunidades/{id}
# porque a agenda por pessoa (a "proxima tarefa" da Etapa 5) vai consultar por
# responsavel, sem oportunidade no caminho.
app.include_router(
    crm_tarefas.router,
    prefix="/crm/tarefas", tags=["CRM - Tarefas"],
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

# Listas de domínio (verticais, origens, concorrentes, motivos). Mesmo módulo:
# quem cadastra conta precisa poder criar a vertical dela no mesmo formulário.
app.include_router(
    crm_dominio.router,
    prefix="/crm/dominio", tags=["CRM - Domínio"],
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
    return {"status": "ok", "sistema": "HIPO", "versao": app.version}
