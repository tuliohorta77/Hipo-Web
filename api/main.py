"""
HIPO — Entry point da API.

O módulo 'crm' é compartilhado — todo cargo válido enxerga contas e
contatos, o que é o que impede cadastro duplicado de CNPJ. O filtro por
envolvimento vale para oportunidades, e é aplicado no repositório, não aqui.
"""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, crm_contas, crm_contatos, crm_dominio
from routers.permissions import requer_modulo

app = FastAPI(
    title="HIPO API",
    description="Hipotálamo Inteligente de Processos e Operações",
    version="2.2.0",
)

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

# Listas de domínio (verticais, origens, concorrentes, motivos). Mesmo módulo:
# quem cadastra conta precisa poder criar a vertical dela no mesmo formulário.
app.include_router(
    crm_dominio.router,
    prefix="/crm/dominio", tags=["CRM - Domínio"],
    dependencies=[Depends(requer_modulo("crm"))],
)


@app.get("/health")
async def health():
    return {"status": "ok", "sistema": "HIPO", "versao": app.version}
