"""
HIPO — Seed de usuários.

Sprint 0: a equipe da operação Omie deixou de existir. Este script garante
que o banco tenha um usuário master (Franqueado) capaz de logar, e — quando
explicitamente autorizado — remove todos os demais.

USO NORMAL (idempotente, não apaga nada):
  cd api
  python -m scripts.seed_usuarios

RESET COMPLETO (apaga todos os usuários exceto o master):
  HIPO_RESET_USUARIOS=1 python -m scripts.seed_usuarios

Configuração por ambiente:
  HIPO_MASTER_NOME    default 'Tulio Horta'
  HIPO_MASTER_EMAIL   default 'tuliohortaribas@gmail.com'
  HIPO_MASTER_SENHA   default '123456'

O master é criado com precisa_trocar_senha=TRUE e deve trocar a senha na
página /perfil no primeiro login.

ATENÇÃO: este script NUNCA sobrescreve a senha de um usuário existente.
Se o master já existe, apenas o nome, o cargo e o flag ativo são ajustados.

ATENÇÃO 2: DATABASE_URL não tem safeguard anti-produção como o conftest.
Confira o host antes de rodar:
  echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
import bcrypt


MASTER_NOME = os.environ.get("HIPO_MASTER_NOME", "Tulio Horta")
MASTER_EMAIL = os.environ.get("HIPO_MASTER_EMAIL", "tuliohortaribas@gmail.com")
MASTER_SENHA = os.environ.get("HIPO_MASTER_SENHA", "123456")
MASTER_CARGO = "Franqueado"

RESET = os.environ.get("HIPO_RESET_USUARIOS") == "1"


def _hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


async def seed(db_url: str) -> None:
    conn = await asyncpg.connect(db_url)
    try:
        async with conn.transaction():
            existente = await conn.fetchrow(
                "SELECT id, cargo, ativo FROM usuarios WHERE email = $1",
                MASTER_EMAIL,
            )

            if existente:
                await conn.execute(
                    """
                    UPDATE usuarios
                       SET nome = $1, cargo = $2, ativo = TRUE
                     WHERE id = $3
                    """,
                    MASTER_NOME, MASTER_CARGO, existente["id"],
                )
                print(f"  master ok (senha preservada): {MASTER_EMAIL}")
            else:
                await conn.execute(
                    """
                    INSERT INTO usuarios
                        (nome, email, senha_hash, cargo, ativo, precisa_trocar_senha)
                    VALUES ($1, $2, $3, $4, TRUE, TRUE)
                    """,
                    MASTER_NOME, MASTER_EMAIL, _hash(MASTER_SENHA), MASTER_CARGO,
                )
                print(f"  master CRIADO: {MASTER_EMAIL} (senha='{MASTER_SENHA}', trocar no 1o login)")

            if RESET:
                removidos = await conn.fetch(
                    "DELETE FROM usuarios WHERE email <> $1 RETURNING email, cargo",
                    MASTER_EMAIL,
                )
                for r in removidos:
                    print(f"  removido: {r['email']} (cargo={r['cargo']})")
                print(f"\n  RESET: {len(removidos)} usuario(s) removido(s).")

            total = await conn.fetchval("SELECT count(*) FROM usuarios")
            if total == 0:
                # A transação inteira volta atrás — nunca deixar o banco sem login.
                raise RuntimeError("Nenhum usuario restante. Abortando (rollback).")
            print(f"\nTotal de usuarios no banco: {total}")
    finally:
        await conn.close()


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERRO: variavel de ambiente DATABASE_URL nao definida.", file=sys.stderr)
        print(
            "Rode com:  DATABASE_URL='postgresql://...' python -m scripts.seed_usuarios",
            file=sys.stderr,
        )
        return 1

    print("HIPO — Seed de usuarios")
    print(f"  Master : {MASTER_NOME} <{MASTER_EMAIL}> ({MASTER_CARGO})")
    print(f"  Modo   : {'RESET (apaga os demais)' if RESET else 'normal (nao apaga nada)'}")
    print()
    asyncio.run(seed(db_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
