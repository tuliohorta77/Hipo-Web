"""
HIPO — Autenticação e gestão do próprio perfil.

Endpoints:
  POST /auth/login     — gera JWT (com limite de tentativas, ver
                         services/login_limite.py)
  GET  /auth/me        — dados do usuário logado + módulos visíveis
  PUT  /auth/senha     — troca senha do próprio usuário

Cargo é VARCHAR(80) livre em 'usuarios.cargo'. Permissões por cargo
são definidas em routers/permissions.py (modulos_do_cargo).
"""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from pydantic import BaseModel, Field
import bcrypt
from database import get_conn
from config import settings
from services import login_limite, observabilidade
from services.instancia import empresa_sigla

log = logging.getLogger("hipo.auth")

router = APIRouter()
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Schemas ──────────────────────────────────────────────────────

class TrocarSenhaPayload(BaseModel):
    senha_atual: str = Field(..., min_length=1)
    nova_senha: str  = Field(..., min_length=6, max_length=200)


class PerfilPayload(BaseModel):
    """
    O que o próprio usuário edita de si.

    Só telefone por enquanto: nome e e-mail identificam a pessoa nas
    trilhas e no login, e mudá-los é ato de administração, não de perfil.
    Formato livre de propósito — o número sai na proposta comercial
    exatamente como foi digitado, e forçar máscara brigaria com ramal,
    DDI e "9 9571-3682".
    """
    telefone: str | None = Field(None, max_length=30)


# ── Helpers ──────────────────────────────────────────────────────

def _hash_senha(senha: str) -> str:
    return bcrypt.hashpw(
        senha.encode(), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    ).decode()


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
    user = dict(user)
    # Erro desta request chega no Sentry dizendo QUEM (id + cargo). No-op
    # sem Sentry.
    observabilidade.marcar_usuario(user)
    return user


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/login")
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    conn=Depends(get_conn),
):
    """
    Troca e-mail + senha por um JWT.

    ORDEM: limite primeiro, senha depois. Barrado, nem o bcrypt roda --
    ver services/login_limite.py. Toda tentativa vira linha em
    login_tentativas, inclusive a barrada (sem contar contra o limite).

    A resposta de credencial errada e a MESMA para e-mail inexistente e
    senha errada: diferenciar diria a quem testa quais e-mails existem.
    """
    email = login_limite.normalizar_email(form.username)
    ip = login_limite.ip_do_cliente(request)
    ua = request.headers.get("user-agent")

    # Falha na checagem (tabela fora, migration pulada no deploy de
    # emergencia) libera o login em vez de derrubar todo mundo. O log.error
    # vira alerta: e o sinal de que o limite parou de proteger.
    try:
        decisao = await login_limite.verificar(conn, email, ip)
    except Exception:
        log.error("limite de login indisponivel; seguindo sem ele", exc_info=True)
        decisao = login_limite.Decisao(bloqueado=False)

    if decisao.bloqueado:
        await login_limite.registrar(
            conn, email, ip, sucesso=False, motivo="bloqueado", user_agent=ua,
        )
        raise HTTPException(
            429, decisao.mensagem(),
            headers={"Retry-After": str(decisao.segundos)},
        )

    # lower() dos dois lados: quem digitou "Fulano@" nao pode ter o login
    # recusado, nem ser contado no limite como alvo diferente de "fulano@".
    # O token segue levando o e-mail como esta no cadastro.
    user = await conn.fetchrow(
        "SELECT * FROM usuarios WHERE lower(email) = $1 AND ativo = TRUE", email
    )
    if not user:
        await login_limite.registrar(
            conn, email, ip, sucesso=False, motivo="inativo_ou_inexistente",
            user_agent=ua,
        )
        raise HTTPException(401, "Credenciais inválidas")
    if not _verificar_senha(form.password, user["senha_hash"]):
        await login_limite.registrar(
            conn, email, ip, sucesso=False, motivo="senha", user_agent=ua,
        )
        raise HTTPException(401, "Credenciais inválidas")

    await login_limite.registrar(conn, email, ip, sucesso=True, user_agent=ua)
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
        # Sai no slide de fechamento da proposta. Vem no /me para a tela de
        # Perfil poder exibir e editar sem uma segunda chamada.
        "telefone": user.get("telefone"),
        "modulos": sorted(modulos_do_cargo(user.get("cargo"))),
        # 046: rotulo da instancia (None na base principal). O front grava
        # junto com o resto no login e mostra ao lado do logo.
        "instancia": empresa_sigla() or None,
    }


@router.put("/perfil")
async def atualizar_perfil(
    payload: PerfilPayload,
    user=Depends(usuario_atual),
    conn=Depends(get_conn),
):
    """Atualiza os dados que o próprio usuário mantém. Hoje: telefone."""
    telefone = (payload.telefone or "").strip() or None
    await conn.execute(
        "UPDATE usuarios SET telefone = $1 WHERE id = $2", telefone, user["id"]
    )
    return {"telefone": telefone}


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
