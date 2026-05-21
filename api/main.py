from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from routers import (
    po, pex, auth, bd_ativados, metas, carteira, clientes, clientes_drilldown,
    bastao,
)
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

# Auth: livre (todos os cargos precisam logar/ver /me/trocar senha)
app.include_router(auth.router, prefix="/auth", tags=["auth"])

# Demais routers: protegidos por módulo
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
app.include_router(
    carteira.router,
    prefix="/carteira", tags=["Contadores"],
    dependencies=[Depends(requer_modulo("carteira"))],
)
# Bastão (passagem Hunter → Farmer): vive sob /carteira porque é feature
# do módulo Contadores. ADM-only para aprovar/rejeitar é checado dentro
# do handler (não dá pra fazer só com dependency de módulo).
app.include_router(
    bastao.router,
    prefix="/carteira", tags=["Contadores - Bastão"],
    dependencies=[Depends(requer_modulo("carteira"))],
)
app.include_router(
    clientes.router,
    prefix="/clientes", tags=["Clientes"],
    dependencies=[Depends(requer_modulo("clientes"))],
)
# Drilldown da Carteira que vive em /clientes/* mas precisa ser acessível
# por quem tem APENAS o módulo 'carteira' (Hunter/Farmer). Guard próprio
# vive dentro das rotas deste router (não no include) — assim este include
# não restringe nada e cada rota declara seus módulos permitidos.
app.include_router(
    clientes_drilldown.router,
    prefix="/clientes", tags=["Clientes - Drilldown"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "sistema": "HIPO v1.0"}
