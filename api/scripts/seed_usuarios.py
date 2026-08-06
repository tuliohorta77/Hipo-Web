"""
HIPO — Seed de usuários.

Sprint 0: a equipe da operação Omie deixou de existir. Este script cadastra
a equipe da Controller MedSeg e, quando explicitamente autorizado, remove
qualquer usuário que não esteja na lista.

USO NORMAL (idempotente, não apaga ninguém):
  cd api
  python -m scripts.seed_usuarios

RESET COMPLETO (apaga todo usuário fora da lista abaixo):
  HIPO_RESET_USUARIOS=1 python -m scripts.seed_usuarios

Requer PYTHONPATH apontando para api/ (o script valida os cargos contra
routers.permissions).

Todos os usuários novos entram com a senha padrão e precisa_trocar_senha=TRUE
— devem trocar pela página /perfil no primeiro login.

ATENÇÃO: este script NUNCA sobrescreve a senha de um usuário existente.
Se o e-mail já existe, apenas nome, cargo e ativo são ajustados.

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

from routers.permissions import CARGOS_VALIDOS


# Equipe da operação. Formato: (nome, email, cargo).
# Cargos canônicos: Franqueado | ADM | EC | SDR | EV | EP
USUARIOS = [
    ("Jakeline Santana", "jakeline.santana@controllermedseg.com", "EV"),
    ("Bruno Gonçalo",    "bruno.goncalo@controllermedseg.com",    "EV"),
    ("Tulio Horta",      "tulio.horta@controllermedseg.com",      "Franqueado"),
    ("Wellington Souza", "wellington.souza@controllermedseg.com", "Franqueado"),
    ("Gabriel Lira",     "gabriel.lira@controllermedseg.com",     "SDR"),
    ("Kethlleen Gomes",  "comercial@controllermedseg.com",        "SDR"),
]

SENHA_PADRAO = "@123456"

RESET = os.environ.get("HIPO_RESET_USUARIOS") == "1"


def validar_lista() -> None:
    """
    Falha cedo se a lista tiver e-mail duplicado ou cargo que o sistema não
    reconhece. Um cargo inválido criaria um usuário que loga mas não recebe
    módulo nenhum — bug silencioso que só apareceria em produção.
    """
    emails = [email.lower() for _, email, _ in USUARIOS]
    duplicados = {e for e in emails if emails.count(e) > 1}
    if duplicados:
        raise ValueError(f"E-mail(s) duplicado(s) na lista: {sorted(duplicados)}")

    invalidos = {cargo for _, _, cargo in USUARIOS if cargo not in CARGOS_VALIDOS}
    if invalidos:
        raise ValueError(
            f"Cargo(s) invalido(s): {sorted(invalidos)}. "
            f"Validos: {sorted(CARGOS_VALIDOS)}"
        )

    if not USUARIOS:
        raise ValueError("Lista de usuarios vazia — o banco ficaria sem login.")


def _hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


async def seed(db_url: str) -> None:
    conn = await asyncpg.connect(db_url)
    try:
        async with conn.transaction():
            criados = 0
            atualizados = 0

            for nome, email, cargo in USUARIOS:
                existente = await conn.fetchrow(
                    "SELECT id, nome, cargo, ativo FROM usuarios WHERE email = $1",
                    email,
                )
                if existente:
                    mudou = (
                        existente["nome"] != nome
                        or existente["cargo"] != cargo
                        or not existente["ativo"]
                    )
                    if mudou:
                        await conn.execute(
                            "UPDATE usuarios SET nome = $1, cargo = $2, ativo = TRUE WHERE id = $3",
                            nome, cargo, existente["id"],
                        )
                        print(f"  atualizado: {email} (cargo: {existente['cargo']} -> {cargo})")
                        atualizados += 1
                    else:
                        print(f"  ok (ja existe, senha preservada): {email}")
                else:
                    await conn.execute(
                        """
                        INSERT INTO usuarios
                            (nome, email, senha_hash, cargo, ativo, precisa_trocar_senha)
                        VALUES ($1, $2, $3, $4, TRUE, TRUE)
                        """,
                        nome, email, _hash(SENHA_PADRAO), cargo,
                    )
                    print(f"  CRIADO: {email} (cargo={cargo}, senha padrao, trocar no 1o login)")
                    criados += 1

            if RESET:
                emails = [email for _, email, _ in USUARIOS]
                removidos = await conn.fetch(
                    "DELETE FROM usuarios WHERE email <> ALL($1::text[]) RETURNING email, cargo",
                    emails,
                )
                for r in removidos:
                    print(f"  removido: {r['email']} (cargo={r['cargo']})")
                print(f"\n  RESET: {len(removidos)} usuario(s) removido(s).")

            total = await conn.fetchval("SELECT count(*) FROM usuarios")
            if total == 0:
                # Desfaz a transacao inteira — nunca deixar o banco sem login.
                raise RuntimeError("Nenhum usuario restante. Abortando (rollback).")

            print()
            print(f"Resumo: {criados} criado(s), {atualizados} atualizado(s).")
            print(f"Total de usuarios no banco: {total}")
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

    try:
        validar_lista()
    except ValueError as e:
        print(f"ERRO na lista de usuarios: {e}", file=sys.stderr)
        return 1

    print("HIPO — Seed de usuarios")
    print(f"  Na lista : {len(USUARIOS)} usuario(s)")
    print(f"  Modo     : {'RESET (apaga quem nao esta na lista)' if RESET else 'normal (nao apaga ninguem)'}")
    print()
    asyncio.run(seed(db_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
