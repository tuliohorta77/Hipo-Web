"""
HIPO — Seed dos usuários iniciais (11 usuários da equipe).

Idempotente: pode rodar várias vezes sem duplicar. Usuários existentes
têm o cargo atualizado pro valor canônico; usuários novos são criados
com senha padrão '123456'.

USO:
  cd api
  python -m scripts.seed_usuarios

Ou via SSH:
  cd /home/hipo/app
  source venv/bin/activate
  python -m scripts.seed_usuarios

A senha padrão é '123456' — todos devem trocar pela página /perfil
após o primeiro login.

ATENÇÃO: este script NUNCA atualiza a senha de um usuário existente.
Se um dos 11 já existe (ex: o ADM Tulio), a senha dele não é mexida.
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
import bcrypt


# CSV dos usuários a seedar. Format: (nome, email, cargo).
# Cargos canônicos: ADM | Franqueado | Gerente | Hunter | Farmer | EP | SDR | EV
USUARIOS = [
    ("Aline Martins",        "aline.martins@omie.com.vc",      "Farmer"),
    ("Beatriz Silva",        "beatriz.teixeira@omie.com.vc",   "Hunter"),
    ("Flavio Souza",         "flavio.souza@omie.com.vc",       "Hunter"),
    ("Jheison Silva",        "jheison.silva@omie.com.vc",      "Farmer"),
    ("Kethlleen Santos",     "kethlleen.santos@omie.com.vc",   "EP"),
    ("Marta Santos",         "marta.santos@omie.com.vc",       "Hunter"),
    ("Patrick Santos",       "patrick.faria@omie.com.vc",      "Farmer"),
    ("Rodrigo Teruel",       "rodrigo.teruel@omie.com.vc",     "Farmer"),
    ("Tulio Horta",          "tulio.horta@omie.com.vc",        "Franqueado"),
    ("Vinícius Trivinho",    "vinicius.trivinho@omie.com.vc",  "Gerente"),
    ("Wellington Souza",     "wellington.souza@omie.com.vc",   "Franqueado"),
]

SENHA_PADRAO = "123456"


def _hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


async def seed(db_url: str) -> None:
    conn = await asyncpg.connect(db_url)
    try:
        criados = 0
        atualizados = 0
        for nome, email, cargo in USUARIOS:
            existente = await conn.fetchrow(
                "SELECT id, cargo FROM usuarios WHERE email = $1", email
            )
            if existente:
                # Atualiza só cargo + nome se mudou. Nunca toca em senha.
                if existente["cargo"] != cargo:
                    await conn.execute(
                        "UPDATE usuarios SET cargo = $1, nome = $2, ativo = TRUE WHERE id = $3",
                        cargo, nome, existente["id"],
                    )
                    print(f"  atualizado: {email} (cargo: {existente['cargo']} → {cargo})")
                    atualizados += 1
                else:
                    print(f"  ok (já existe): {email}")
            else:
                await conn.execute(
                    """
                    INSERT INTO usuarios (nome, email, senha_hash, cargo, ativo)
                    VALUES ($1, $2, $3, $4, TRUE)
                    """,
                    nome, email, _hash(SENHA_PADRAO), cargo,
                )
                print(f"  CRIADO: {email}  (cargo={cargo}, senha=123456)")
                criados += 1
        print()
        print(f"Resumo: {criados} criado(s), {atualizados} atualizado(s), "
              f"{len(USUARIOS) - criados - atualizados} sem mudança.")
    finally:
        await conn.close()


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERRO: variável de ambiente DATABASE_URL não definida.", file=sys.stderr)
        print("Rode com:  DATABASE_URL='postgresql://...' python -m scripts.seed_usuarios", file=sys.stderr)
        return 1

    print("HIPO — Seed de usuários")
    print(f"  Total no CSV: {len(USUARIOS)}")
    print(f"  Senha padrão dos novos: '{SENHA_PADRAO}'")
    print()
    asyncio.run(seed(db_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
