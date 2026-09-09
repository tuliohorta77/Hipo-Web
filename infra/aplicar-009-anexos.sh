#!/usr/bin/env bash
# =====================================================================
#  HIPO -- aplica a migration 009_anexos.sql no RDS
#
#  Roda NA EC2, como root. O /home/hipo/app/.env e do ec2-user (o rsync
#  do CI o escreve) mesmo com o app rodando como hipo -- por isso root,
#  e nao `sudo -iu hipo`.
#
#  A 009 e ADITIVA e IDEMPOTENTE: so CREATE TABLE IF NOT EXISTS e
#  CREATE INDEX IF NOT EXISTS. Rodar duas vezes nao faz nada na segunda,
#  e nao ha DROP -- logo nao exige o export em CSV que as migrations
#  destrutivas exigem.
#
#  USO (chamado pelo deploy-012, ou a mao):
#     sudo bash /tmp/aplicar-009-anexos.sh /tmp/009_anexos.sql
# =====================================================================
set -euo pipefail

ARQ="${1:-/tmp/009_anexos.sql}"
ENV_FILE="/home/hipo/app/.env"

[ -f "$ARQ" ]      || { echo "ERRO: migration nao encontrada em $ARQ"; exit 1; }
[ -f "$ENV_FILE" ] || { echo "ERRO: $ENV_FILE nao encontrado"; exit 1; }

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${DATABASE_URL:?DATABASE_URL ausente no .env}"

# Mascarar a senha antes de imprimir. O seed nao tem o safeguard que o
# conftest tem, e conferir o HOST a olho e a unica rede embaixo de quem
# roda migration a mao -- entao o host precisa aparecer, e a senha nao.
echo "banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

# O interpretador certo e o da unit, nao o `python3` do PATH do root. Se
# o app vive num venv, o asyncpg esta la dentro e o python do sistema nem
# o enxerga -- foi assim que o python-pptx da 009 "instalou" no lugar
# errado e o sintoma nao mudou.
UNIT_EXEC="$(systemctl show -p ExecStart --value hipo-api.service 2>/dev/null || true)"
PY="$(printf '%s' "$UNIT_EXEC" | sed -n 's/.*path=\([^ ;]*\).*/\1/p')"
if [ -z "${PY:-}" ] || [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
  echo "aviso: nao achei o interpretador da unit; usando $PY"
else
  echo "interpretador da unit: $PY"
fi

"$PY" - "$ARQ" <<'PY'
import asyncio
import os
import sys

import asyncpg


async def main() -> int:
    caminho = sys.argv[1]
    with open(caminho, encoding="utf-8") as f:
        sql = f.read()

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        # Sem parametros, o asyncpg usa o simple query protocol -- que e o
        # que permite varios comandos e o BEGIN/COMMIT do proprio arquivo.
        await conn.execute(sql)

        existe = await conn.fetchval(
            "SELECT to_regclass('public.tarefa_anexos') IS NOT NULL"
        )
        if not existe:
            print("ERRO: a tabela tarefa_anexos nao existe depois da migration")
            return 1

        colunas = await conn.fetch(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'tarefa_anexos'
             ORDER BY ordinal_position
            """
        )
        print("tarefa_anexos OK:", ", ".join(c["column_name"] for c in colunas))

        indice = await conn.fetchval(
            "SELECT to_regclass('public.idx_tarefa_anexos_tarefa') IS NOT NULL"
        )
        print("indice idx_tarefa_anexos_tarefa:", "OK" if indice else "AUSENTE")
        return 0
    finally:
        await conn.close()


sys.exit(asyncio.run(main()))
PY

echo "migration 009 aplicada."
