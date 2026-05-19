from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from routers import po, pex, auth, bd_ativados, metas, carteira
from routers.permissions import requer_modulo

app = FastAPI(
    title="HIPO API",
    description="Hipotálamo Inteligente de Processos e Operações",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth: sem restrição de módulo — todos os cargos precisam acessar
# login, /me e troca de senha do próprio usuário.
app.include_router(auth.router, prefix="/auth", tags=["auth"])

# Demais routers: protegidos por módulo no nível de inclusão.
# Cargo que não tem o módulo recebe 403 em QUALQUER rota do router.
app.include_router(
    po.router,
    prefix="/po", tags=["POs"],
    dependencies=[Depends(requer_modulo("po"))],
)
app.include_router(
    pex.router,
    prefix="/pex", tags=["PEX"],
    dependencies=[Depends(requer_modulo("pex"))],
)
app.include_router(
    bd_ativados.router,
    prefix="/bd-ativados", tags=["BD Ativados"],
    dependencies=[Depends(requer_modulo("bd"))],
)
app.include_router(
    metas.router,
    prefix="/metas", tags=["Metas PEX"],
    dependencies=[Depends(requer_modulo("metas"))],
)

# Carteira: todos os cargos válidos têm 'carteira' nos módulos
# (Hunter, Farmer, EP, Gerente, ADM, Franqueado). Mesmo assim
# aplicamos o dependency pra rejeitar cargos desconhecidos/nulos.
app.include_router(
    carteira.router,
    prefix="/carteira", tags=["Carteira"],
    dependencies=[Depends(requer_modulo("carteira"))],
)


@app.get("/health")
async def health():
    return {"status": "ok", "sistema": "HIPO v1.0"}
