"""
HIPO — Autenticação e gestão do próprio perfil.

Endpoints:
  POST /auth/login     — gera JWT
  GET  /auth/me        — dados do usuário logado + módulos visíveis
  PUT  /auth/senha     — troca senha do próprio usuário

Cargo é VARCHAR(80) livre em 'usuarios.cargo'. Permissões por cargo
são definidas em routers/permissions.py (modulos_do_cargo).
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from pydantic import BaseModel, Field
import bcrypt
from database import get_conn
from config import settings

router = APIRouter()
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Schemas ──────────────────────────────────────────────────────

class TrocarSenhaPayload(BaseModel):
    senha_atual: str = Field(..., min_length=1)
    nova_senha: str  = Field(..., min_length=6, max_length=200)


# ── Helpers ──────────────────────────────────────────────────────

def _hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def _verificar_senha(senha: str, hash_: str) -> bool:
    return bcrypt.checkpw(senha.encode(), hash_.encode())


def criar_token(sub: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": sub, "exp": exp}, settings.JWT_SECRET, algorithm="HS256")


async def usuario_atual(token: str = Depends(oauth2), conn=Depends(get_conn)):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(401, "Token inválido")
    user = await conn.fetchrow(
        "SELECT * FROM usuarios WHERE email = $1 AND ativo = TRUE", email
    )
    if not user:
        raise HTTPException(401, "Usuário não encontrado")
    return dict(user)


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_conn)):
    user = await conn.fetchrow(
        "SELECT * FROM usuarios WHERE email = $1 AND ativo = TRUE", form.username
    )
    if not user or not _verificar_senha(form.password, user["senha_hash"]):
        raise HTTPException(401, "Credenciais inválidas")
    return {"access_token": criar_token(user["email"]), "token_type": "bearer"}


@router.get("/me")
async def me(user=Depends(usuario_atual)):
    # Importa aqui pra evitar import circular (permissions importa usuario_atual).
    from routers.permissions import modulos_do_cargo
    return {
        "id": str(user["id"]),
        "nome": user["nome"],
        "email": user["email"],
        "cargo": user["cargo"],
        "modulos": sorted(modulos_do_cargo(user.get("cargo"))),
    }


@router.put("/senha")
async def trocar_senha(
    payload: TrocarSenhaPayload,
    user=Depends(usuario_atual),
    conn=Depends(get_conn),
):
    """Troca a senha do próprio usuário."""
    if not _verificar_senha(payload.senha_atual, user["senha_hash"]):
        raise HTTPException(400, "Senha atual incorreta.")
    if payload.senha_atual == payload.nova_senha:
        raise HTTPException(400, "Nova senha não pode ser igual à atual.")

    novo_hash = _hash_senha(payload.nova_senha)
    await conn.execute(
        "UPDATE usuarios SET senha_hash = $1 WHERE id = $2",
        novo_hash, user["id"],
    )
    return {"message": "Senha alterada com sucesso."}
