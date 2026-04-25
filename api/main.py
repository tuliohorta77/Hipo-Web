from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import po, pex, auth, bd_ativados

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

app.include_router(auth.router,        prefix="/auth",        tags=["auth"])
app.include_router(po.router,          prefix="/po",          tags=["POs"])
app.include_router(pex.router,         prefix="/pex",         tags=["PEX"])
app.include_router(bd_ativados.router, prefix="/bd-ativados", tags=["BD Ativados"])


@app.get("/health")
async def health():
    return {"status": "ok", "sistema": "HIPO v1.0"}
