#!/usr/bin/env bash
# HIPO - Responde se uma coluna existe no banco de producao. So LE.
#
#   bash /tmp/conferir_coluna_remoto.sh contas nao_prospectar
#
# Imprime SIM ou NAO na ultima linha, e e essa linha que o .ps1 le.
#
# POR QUE UM SCRIPT SO PARA ISSO
#   A alternativa era montar a consulta dentro do comando do ssh, no .ps1.
#   Aspas simples dentro de aspas duplas dentro de PowerShell dentro de bash
#   e o tipo de coisa que funciona na maquina de quem escreveu e quebra na
#   primeira mudanca. Aqui o quoting fica todo do lado do bash.
set -euo pipefail

TABELA="${1:-}"
COLUNA="${2:-}"
[ -n "$TABELA" ] && [ -n "$COLUNA" ] || { echo "Uso: bash $0 <tabela> <coluna>" >&2; exit 1; }

APP=/home/hipo/app
ENVFILE="$APP/.env"

if ! sudo test -r "$ENVFILE"; then
    echo "Nao consigo ler $ENVFILE nem como root." >&2
    exit 1
fi

DB_URL="$(sudo grep -m1 -E '^[[:space:]]*(export[[:space:]]+)?DATABASE_URL=' "$ENVFILE" \
          | tr -d '\r' | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//")"

[ -n "$DB_URL" ] || { echo "DATABASE_URL nao encontrada em $ENVFILE." >&2; exit 1; }

CONSULTA="SELECT 1 FROM information_schema.columns
           WHERE table_name = '$TABELA' AND column_name = '$COLUNA'"

if command -v psql > /dev/null 2>&1; then
    ACHOU="$(psql "$DB_URL" -At -c "$CONSULTA" 2>/dev/null || true)"
else
    if sudo test -x "$APP/venv/bin/python"; then
        PY="$APP/venv/bin/python"
    elif sudo test -x "$APP/.venv/bin/python"; then
        PY="$APP/.venv/bin/python"
    else
        PY="$(command -v python3)"
    fi
    ACHOU="$(sudo -u hipo env DATABASE_URL="$DB_URL" CONSULTA="$CONSULTA" "$PY" - <<'FIM_PY'
import asyncio, os, asyncpg

async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        print(await conn.fetchval(os.environ["CONSULTA"]) or "")
    finally:
        await conn.close()

asyncio.run(main())
FIM_PY
)"
fi

if [ "$(echo "$ACHOU" | tr -d '[:space:]')" = "1" ]; then
    echo "SIM"
else
    echo "NAO"
fi
