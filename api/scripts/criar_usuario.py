"""
HIPO — Cria (ou ajusta) um usuário de operação ou gestão (entrega 046).

Nasceu para a instância da MOS, que começa com o banco vazio: o
`seed_usuarios` tem a equipe da Controller MedSeg cravada no código e não
serve para outra base. Este aqui recebe a pessoa na linha de comando.

USO (na EC2, como ec2-user, com o DATABASE_URL da base certa):
  cd /home/hipo/mos/api
  export DATABASE_URL="$(grep '^DATABASE_URL=' /home/hipo/mos/.env | cut -d= -f2-)"
  echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'      # CONFIRA O BANCO
  python3 -m scripts.criar_usuario tulio.horta@mos.com.br --nome "Tulio Horta" --cargo Franqueado

Cargos aceitos: os de CARGOS_VALIDOS (Franqueado, ADM, EC, SDR, EV, EP).
Monitor e UC têm scripts próprios (criar_usuario_monitor, criar_usuario_uc).

Idempotente, com a mesma regra do seed: login existente tem nome, cargo e
ativo ajustados e a senha PRESERVADA — a menos que --redefinir-senha seja
passado. Usuário novo entra com a senha padrão e troca em /perfil no
primeiro login (precisa_trocar_senha = TRUE).

ATENÇÃO: DATABASE_URL não tem safeguard anti-produção. Com duas bases na
mesma máquina, conferir o host E o nome do banco é o que impede de criar a
pessoa da MOS na base da MedSeg.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg
import bcrypt

from routers.permissions import CARGOS_VALIDOS

SENHA_PADRAO = "123456"
TAMANHO_MINIMO_SENHA = 6  # mesmo mínimo do PUT /auth/senha


def _hash(senha: str) -> str:
    from config import settings
    return bcrypt.hashpw(
        senha.encode(), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    ).decode()


def validar(login: str, nome: str, cargo: str, senha: str) -> None:
    if not login or not login.strip():
        raise ValueError("Login vazio.")
    if len(login) > 150:
        raise ValueError("Login com mais de 150 caracteres.")
    if "@" not in login:
        raise ValueError("Login precisa ser um e-mail (é o que vai no convite da agenda).")
    if not nome or not nome.strip():
        raise ValueError("Nome vazio.")
    if cargo not in CARGOS_VALIDOS:
        aceitos = ", ".join(sorted(CARGOS_VALIDOS))
        raise ValueError(f"Cargo '{cargo}' inválido. Aceitos: {aceitos}.")
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ValueError(f"Senha com menos de {TAMANHO_MINIMO_SENHA} caracteres.")


async def criar(
    conn: asyncpg.Connection, login: str, nome: str, cargo: str,
    senha: str, redefinir: bool,
) -> str:
    async with conn.transaction():
        existente = await conn.fetchrow(
            "SELECT id, cargo FROM usuarios WHERE lower(email) = lower($1)", login
        )
        if existente:
            if redefinir:
                await conn.execute(
                    """
                    UPDATE usuarios
                       SET nome = $1, cargo = $2, ativo = TRUE,
                           senha_hash = $3, precisa_trocar_senha = TRUE
                     WHERE id = $4
                    """,
                    nome, cargo, _hash(senha), existente["id"],
                )
                return (f"atualizado (senha redefinida): {login} "
                        f"(cargo {existente['cargo']} -> {cargo})")
            await conn.execute(
                "UPDATE usuarios SET nome = $1, cargo = $2, ativo = TRUE WHERE id = $3",
                nome, cargo, existente["id"],
            )
            return (f"atualizado (senha preservada): {login} "
                    f"(cargo {existente['cargo']} -> {cargo})")

        await conn.execute(
            """
            INSERT INTO usuarios
                (nome, email, senha_hash, cargo, ativo, precisa_trocar_senha)
            VALUES ($1, $2, $3, $4, TRUE, TRUE)
            """,
            nome, login, _hash(senha), cargo,
        )
        return f"CRIADO: {login} (cargo={cargo}, senha inicial a trocar em /perfil)"


async def _rodar(db_url: str, *args) -> str:
    conn = await asyncpg.connect(db_url)
    try:
        return await criar(conn, *args)
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cria ou ajusta um usuário do HIPO.")
    ap.add_argument("login", help="E-mail de login")
    ap.add_argument("--nome", required=True)
    ap.add_argument("--cargo", required=True, help=", ".join(sorted(CARGOS_VALIDOS)))
    ap.add_argument("--senha", default=SENHA_PADRAO)
    ap.add_argument("--redefinir-senha", action="store_true")
    args = ap.parse_args(argv)

    login = args.login.strip().lower()
    nome = args.nome.strip()
    cargo = args.cargo.strip()

    try:
        validar(login, nome, cargo, args.senha)
    except ValueError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERRO: variavel de ambiente DATABASE_URL nao definida.", file=sys.stderr)
        return 1

    print(asyncio.run(_rodar(db_url, login, nome, cargo, args.senha, args.redefinir_senha)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
