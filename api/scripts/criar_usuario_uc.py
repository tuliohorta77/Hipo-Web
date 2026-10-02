"""
HIPO — Cria (ou ajusta) uma conta com acesso SÓ à Universidade Corporativa.

Para quem estuda o conteúdo da UC sem operar o CRM (sócio, parceiro,
candidato). Cargo 'UC' -> modulos_do_cargo devolve {'uc'}: a API libera
/uc/* (painel, trilhas, aulas, materiais, concluir) e barra todo o resto
(CRM, estúdio, Monitor, relatórios, RPeR, parceiros, telemetria). A tela
/perfil continua acessível para trocar a senha.

A conta vê TODAS as trilhas publicadas e nenhuma como obrigatória.

USO:
  cd api
  python -m scripts.criar_usuario_uc marcelod@controllermedseg.com.br --nome "Marcelo"
  python -m scripts.criar_usuario_uc fulano@x.com --nome "Fulano" --senha 123456

Idempotente: se o login já existe, ajusta nome/cargo/ativo e NÃO mexe na
senha — a menos que --redefinir-senha seja passado.

ATENÇÃO: DATABASE_URL não tem safeguard anti-produção. Confira o host:
  echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg
import bcrypt

from routers.permissions import CARGO_UC

SENHA_PADRAO = "123456"
TAMANHO_MINIMO_SENHA = 6  # mesmo mínimo do PUT /auth/senha


def _hash(senha: str) -> str:
    from config import settings
    return bcrypt.hashpw(
        senha.encode(), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    ).decode()


def validar(login: str, nome: str, senha: str) -> None:
    if not login or not login.strip():
        raise ValueError("Login vazio.")
    if len(login) > 150:
        raise ValueError("Login com mais de 150 caracteres.")
    if not nome or not nome.strip():
        raise ValueError("Nome vazio.")
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ValueError(f"Senha com menos de {TAMANHO_MINIMO_SENHA} caracteres.")


async def criar(db_url: str, login: str, nome: str, senha: str, redefinir: bool) -> str:
    conn = await asyncpg.connect(db_url)
    try:
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
                        nome, CARGO_UC, _hash(senha), existente["id"],
                    )
                    return f"atualizado (senha redefinida): {login} (cargo {existente['cargo']} -> {CARGO_UC})"
                await conn.execute(
                    "UPDATE usuarios SET nome = $1, cargo = $2, ativo = TRUE WHERE id = $3",
                    nome, CARGO_UC, existente["id"],
                )
                return f"atualizado (senha preservada): {login} (cargo {existente['cargo']} -> {CARGO_UC})"

            # Pessoa de verdade: entra com a senha padrão e troca em /perfil,
            # como no seed_usuarios.
            await conn.execute(
                """
                INSERT INTO usuarios
                    (nome, email, senha_hash, cargo, ativo, precisa_trocar_senha)
                VALUES ($1, $2, $3, $4, TRUE, TRUE)
                """,
                nome, login, _hash(senha), CARGO_UC,
            )
            return f"CRIADO: {login} (cargo={CARGO_UC})"
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cria conta com acesso só à UC.")
    ap.add_argument("login", help="E-mail de login")
    ap.add_argument("--nome", required=True)
    ap.add_argument("--senha", default=SENHA_PADRAO)
    ap.add_argument("--redefinir-senha", action="store_true")
    args = ap.parse_args(argv)

    login = args.login.strip().lower()
    nome = args.nome.strip()

    try:
        validar(login, nome, args.senha)
    except ValueError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERRO: variavel de ambiente DATABASE_URL nao definida.", file=sys.stderr)
        return 1

    print(asyncio.run(criar(db_url, login, nome, args.senha, args.redefinir_senha)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
