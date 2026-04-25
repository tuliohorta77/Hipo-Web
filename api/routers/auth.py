from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from database import get_conn
from config import settings

router = APIRouter()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")

def criar_token(sub: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": sub, "exp": exp}, settings.JWT_SECRET, algorithm="HS256")

async def usuario_atual(token: str = Depends(oauth2), conn=Depends(get_conn)):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(401, "Token inválido")
    user = await conn.fetchrow("SELECT * FROM usuarios WHERE email = $1 AND ativo = TRUE", email)
    if not user:
        raise HTTPException(401, "Usuário não encontrado")
    return dict(user)

@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_conn)):
    user = await conn.fetchrow(
        "SELECT * FROM usuarios WHERE email = $1 AND ativo = TRUE", form.username
    )
    if not user or not pwd_ctx.verify(form.password, user["senha_hash"]):
        raise HTTPException(401, "Credenciais inválidas")
    return {"access_token": criar_token(user["email"]), "token_type": "bearer"}

@router.get("/me")
async def me(user=Depends(usuario_atual)):
    return {"id": str(user["id"]), "nome": user["nome"],
            "email": user["email"], "cargo": user["cargo"]}
