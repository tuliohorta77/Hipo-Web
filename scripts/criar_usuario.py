#!/usr/bin/env python3
"""
HIPO — Cria o primeiro usuário admin no banco.

Uso (na EC2, dentro do venv da api):
    cd /home/hipo/app/api
    source .venv/bin/activate
    python3 criar_usuario.py

Ele vai pedir nome, email, senha e cargo, gerar o hash bcrypt
e inserir direto na tabela `usuarios`.
"""
import os
import sys
import getpass

import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # tenta ler do .env do projeto
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    DATABASE_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

if not DATABASE_URL:
    print("ERRO: DATABASE_URL não definida. Exporte a variável ou configure o .env.")
    sys.exit(1)


def main():
    print("=== HIPO — Criação de Usuário ===\n")
    nome = input("Nome completo: ").strip()
    email = input("E-mail: ").strip().lower()
    cargo = input("Cargo (ADM, GESTOR, EC, EV, SDR, EP, FRANQUEADO): ").strip().upper() or "ADM"
    senha = getpass.getpass("Senha: ")
    senha2 = getpass.getpass("Confirme a senha: ")

    if not nome or not email or not senha:
        print("ERRO: nome, email e senha são obrigatórios.")
        sys.exit(1)

    if senha != senha2:
        print("ERRO: as senhas não coincidem.")
        sys.exit(1)

    if len(senha) < 6:
        print("ERRO: senha precisa ter ao menos 6 caracteres.")
        sys.exit(1)

    senha_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # verifica se já existe
                cur.execute("SELECT id, email FROM usuarios WHERE email = %s", (email,))
                existente = cur.fetchone()

                if existente:
                    resp = input(
                        f"\n⚠️  Usuário {email} já existe. Atualizar senha/dados? (s/N): "
                    ).strip().lower()
                    if resp != "s":
                        print("Cancelado.")
                        return
                    cur.execute(
                        """
                        UPDATE usuarios
                        SET nome = %s, senha_hash = %s, cargo = %s, ativo = TRUE
                        WHERE email = %s
                        RETURNING id
                        """,
                        (nome, senha_hash, cargo, email),
                    )
                    row = cur.fetchone()
                    print(f"\n✅ Usuário atualizado. ID: {row['id']}")
                else:
                    cur.execute(
                        """
                        INSERT INTO usuarios (nome, email, senha_hash, cargo, ativo)
                        VALUES (%s, %s, %s, %s, TRUE)
                        RETURNING id
                        """,
                        (nome, email, senha_hash, cargo),
                    )
                    row = cur.fetchone()
                    print(f"\n✅ Usuário criado. ID: {row['id']}")
                    print(f"   Email: {email}")
                    print(f"   Cargo: {cargo}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
