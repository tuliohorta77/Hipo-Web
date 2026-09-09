#!/usr/bin/env bash
# HIPO - Aplica uma migration na EC2. Metade que roda NA EC2.
#
# Chamado pelo subir-carteira.ps1, mas serve para qualquer migration:
#
#   bash /tmp/aplicar_migration_remoto.sh 010_nao_prospectar.sql
#
# POR QUE ELE EXISTE
#   O deploy do CI faz rsync e reinicia o servico -- NAO aplica DDL. Aplicar
#   migration sempre foi passo manual por SSH, e passo manual e o que a gente
#   esquece de fazer na hora certa. Aqui vira um comando so, dentro da mesma
#   ordem que o resto da carga precisa.
#
# PSQL OU PYTHON
#   Prefere psql. Sem psql na maquina, cai para o python do venv com asyncpg,
#   que existe com certeza porque e o que roda a API. As duas rotas mandam o
#   arquivo inteiro numa tacada, entao o BEGIN/COMMIT de dentro do .sql
#   continua valendo: ou a migration inteira entra, ou nada entra.
#
# NAO E DESTRUTIVO por si so -- destrutivo e o que estiver dentro do .sql.
set -euo pipefail

ARQ="${1:-}"
[ -n "$ARQ" ] || { echo "Uso: bash $0 <nome-da-migration.sql>" >&2; exit 1; }
[ -f "/tmp/$ARQ" ] || { echo "FALTA /tmp/$ARQ. Rode o .ps1, que faz o scp." >&2; exit 1; }

APP=/home/hipo/app
ENVFILE="$APP/.env"

if ! sudo test -r "$ENVFILE"; then
    echo "Nao consigo ler $ENVFILE nem como root:" >&2
    sudo ls -l "$ENVFILE" >&2 || true
    exit 1
fi

DB_URL="$(sudo grep -m1 -E '^[[:space:]]*(export[[:space:]]+)?DATABASE_URL=' "$ENVFILE" \
          | tr -d '\r' | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//")"

if [ -z "$DB_URL" ]; then
    echo "DATABASE_URL nao encontrada em $ENVFILE." >&2
    exit 1
fi

echo "banco : $(echo "$DB_URL" | sed 's/:[^:@]*@/:****@/')"

if sudo test -x "$APP/venv/bin/python"; then
    PY="$APP/venv/bin/python"
elif sudo test -x "$APP/.venv/bin/python"; then
    PY="$APP/.venv/bin/python"
else
    PY="$(command -v python3)"
fi

echo "migration: $ARQ"
echo

if command -v psql > /dev/null 2>&1; then
    echo "aplicando com psql..."
    psql "$DB_URL" -v ON_ERROR_STOP=1 -f "/tmp/$ARQ"
else
    echo "psql nao encontrado; aplicando com o python do venv (asyncpg)..."
    sudo -u hipo env DATABASE_URL="$DB_URL" ARQ="/tmp/$ARQ" "$PY" - <<'FIM_PY'
import asyncio, os, asyncpg

async def main():
    sql = open(os.environ["ARQ"], encoding="utf-8").read()
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        # O .sql ja traz o proprio BEGIN/COMMIT. execute() sem argumentos usa
        # o protocolo simples, que aceita varias instrucoes numa string so --
        # e e por isso que a transacao de dentro do arquivo funciona.
        await conn.execute(sql)
    finally:
        await conn.close()
    print("migration aplicada.")

asyncio.run(main())
FIM_PY
fi

echo
echo "OK. Migration idempotente pode ser rodada de novo sem efeito."
