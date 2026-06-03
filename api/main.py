from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from routers import (
    bridge,
    po, pex, auth, bd_ativados, metas, carteira, clientes, clientes_drilldown,
    bastao, vendas, agendamento,
)
from routers.permissions import requer_modulo

app = FastAPI(
    title="HIPO API",
    description="HipotÃ¡lamo Inteligente de Processos e OperaÃ§Ãµes",
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

# Demais routers: protegidos por mÃ³dulo
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
# BastÃ£o (passagem Hunter â†’ Farmer): vive sob /carteira porque Ã© feature
# do mÃ³dulo Contadores. ADM-only para aprovar/rejeitar Ã© checado dentro
# do handler (nÃ£o dÃ¡ pra fazer sÃ³ com dependency de mÃ³dulo).
app.include_router(
    bastao.router,
    prefix="/carteira", tags=["Contadores - BastÃ£o"],
    dependencies=[Depends(requer_modulo("carteira"))],
)
app.include_router(
    clientes.router,
    prefix="/clientes", tags=["Clientes"],
    dependencies=[Depends(requer_modulo("clientes"))],
)
# Drilldown da Carteira que vive em /clientes/* mas precisa ser acessÃ­vel
# por quem tem APENAS o mÃ³dulo 'carteira' (Hunter/Farmer). Guard prÃ³prio
# vive dentro das rotas deste router (nÃ£o no include) â€” assim este include
# nÃ£o restringe nada e cada rota declara seus mÃ³dulos permitidos.
app.include_router(
    clientes_drilldown.router,
    prefix="/clientes", tags=["Clientes - Drilldown"],
)
# Vendas: funil CROmie. Usa o modulo 'clientes' (mesma permissao) por
# decisao de produto â€” quem ve Clientes ve Vendas.
app.include_router(
    vendas.router,
    prefix="/vendas", tags=["Vendas"],
    dependencies=[Depends(requer_modulo("clientes"))],
)
# Agendamento (cargo SDR): v1 replica a rÃ©gua de conformidade do CROmie.
# Router prÃ³prio (nÃ£o reusa /vendas) porque o SDR nÃ£o tem o mÃ³dulo
# 'clientes' e porque o Agendamento vai divergir de Vendas nas prÃ³ximas
# versÃµes. Protegido pelo mÃ³dulo 'agendamento'.
app.include_router(
    agendamento.router,
    prefix="/agendamento", tags=["Agendamento"],
    dependencies=[Depends(requer_modulo("agendamento"))],
)


@app.get("/health")
async def health():
    return {"status": "ok", "sistema": "HIPO v1.0"}

# Bridge: auth via X-Bridge-Token, sem requer_modulo
app.include_router(bridge.router)
