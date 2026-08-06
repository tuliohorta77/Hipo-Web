"""
HIPO — Entry point da API.

Sprint 0 (limpeza do legado): o app expõe apenas autenticação e health.
Os routers de PEX, CROmie, BD Ativados, POs, Carteira, Bastão, Clientes,
Vendas e Agendamento foram removidos junto com as tabelas que consultavam.

O CRM nativo (contas, contatos, oportunidades) entra na Sprint 1 sob o
prefixo /crm, protegido pelo módulo 'crm'.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth

app = FastAPI(
    title="HIPO API",
    description="Hipotálamo Inteligente de Processos e Operações",
    version="2.0.0",
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


@app.get("/health")
async def health():
    return {"status": "ok", "sistema": "HIPO", "versao": app.version}
