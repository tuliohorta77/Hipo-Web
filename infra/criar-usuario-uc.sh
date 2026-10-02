#!/usr/bin/env bash
#
# HIPO - cria (ou ajusta) uma conta com acesso SO a Universidade Corporativa.
#
# Roda DEPOIS do deploy: api/scripts/criar_usuario_uc.py chega pelo CI.
#
# Rodar NA EC2, como ec2-user:
#   bash /tmp/criar-usuario-uc.sh <email> "<nome>" [senha]
#
# Idempotente: login existente tem nome/cargo ajustados e a senha
# preservada.
#
# Mesmo arranjo do semear-uc.sh: o .env e do root (600), entao as
# variaveis sao lidas com sudo e exportadas. Sem `source`.
#
# ASCII puro.

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Uso: bash $0 <email> \"<nome>\" [senha]" >&2
    exit 1
fi
LOGIN="$1"
NOME="$2"
SENHA="${3:-123456}"

APP=/home/hipo/app
ENV_PATH=$APP/.env

ler() { sudo cat "$ENV_PATH" | grep -E "^$1=" | head -1 | cut -d= -f2- || true; }

export DATABASE_URL="$(ler DATABASE_URL)"
export JWT_SECRET="$(ler JWT_SECRET)"

if [ -z "$DATABASE_URL" ] || [ -z "$JWT_SECRET" ]; then
    echo "ERRO: $ENV_PATH sem DATABASE_URL ou JWT_SECRET."
    exit 1
fi
echo "banco : $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

PY=""
tem_libs() { [ -x "$1" ] && "$1" -c 'import asyncpg, bcrypt' >/dev/null 2>&1; }
for c in "$APP/venv/bin/python" "$APP/.venv/bin/python" \
         "$APP/api/venv/bin/python" "$APP/api/.venv/bin/python" \
         "$(command -v python3.11 || true)" "$(command -v python3 || true)"; do
    if [ -n "$c" ] && tem_libs "$c"; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
    echo "ERRO: nenhum python com asyncpg e bcrypt encontrado."
    exit 2
fi

cd "$APP/api"
PYTHONPATH="$APP/api" "$PY" -m scripts.criar_usuario_uc "$LOGIN" --nome "$NOME" --senha "$SENHA"
