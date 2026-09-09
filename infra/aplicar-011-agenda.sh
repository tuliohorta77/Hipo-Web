#!/usr/bin/env bash
# =====================================================================
#  HIPO -- aplica a migration 011_agenda.sql no RDS
#
#  Roda NA EC2, como root. O /home/hipo/app/.env e do ec2-user (o rsync
#  do CI o escreve) mesmo com o app rodando como hipo -- por isso root,
#  e nao `sudo -iu hipo`. Mesma escolha do aplicar-009-anexos.sh.
#
#  A 011 e ADITIVA e IDEMPOTENTE: CREATE TABLE / CREATE INDEX IF NOT
#  EXISTS e um INSERT com ON CONFLICT DO NOTHING. Rodar duas vezes nao
#  duplica a semente e nao ha DROP -- logo nao exige o export em CSV que
#  as migrations destrutivas exigem.
#
#  USO (chamado pelo deploy-014, ou a mao):
#     sudo bash /tmp/aplicar-011-agenda.sh /tmp/011_agenda.sql
# =====================================================================
set -euo pipefail

ARQ="${1:-/tmp/011_agenda.sql}"
ENV_FILE="/home/hipo/app/.env"

[ -f "$ARQ" ]      || { echo "ERRO: migration nao encontrada em $ARQ"; exit 1; }
[ -f "$ENV_FILE" ] || { echo "ERRO: $ENV_FILE nao encontrado"; exit 1; }

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${DATABASE_URL:?DATABASE_URL ausente no .env}"

# Mascarar a senha antes de imprimir. Conferir o HOST a olho e a unica
# rede embaixo de quem roda migration a mao -- entao o host precisa
# aparecer, e a senha nao.
echo "banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

# O interpretador certo e o da unit, nao o `python3` do PATH do root: se
# o app vive num venv, o asyncpg esta la dentro e o python do sistema nem
# o enxerga.
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

TABELAS = ("tipos_reuniao", "reunioes", "reuniao_participantes")
INDICES = (
    "idx_tarefas_responsavel_prazo",
    "idx_reunioes_tipo",
    "idx_reunioes_nao_sincronizadas",
    "idx_reuniao_participantes_usuario",
)


async def main() -> int:
    caminho = sys.argv[1]
    with open(caminho, encoding="utf-8") as f:
        sql = f.read()

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        # Sem parametros, o asyncpg usa o simple query protocol -- que e o
        # que permite varios comandos e o BEGIN/COMMIT do proprio arquivo.
        await conn.execute(sql)

        faltando = []
        for tabela in TABELAS:
            existe = await conn.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", f"public.{tabela}"
            )
            if not existe:
                faltando.append(tabela)
        if faltando:
            print("ERRO: tabela(s) ausente(s) depois da migration:", ", ".join(faltando))
            return 1

        for tabela in TABELAS:
            colunas = await conn.fetch(
                """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_name = $1
                 ORDER BY ordinal_position
                """,
                tabela,
            )
            print(f"{tabela} OK:", ", ".join(c["column_name"] for c in colunas))

        for indice in INDICES:
            tem = await conn.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", f"public.{indice}"
            )
            print(f"indice {indice}:", "OK" if tem else "AUSENTE")

        # A semente e o que o combobox de tipo oferece no primeiro uso.
        # Zero aqui nao quebra nada (tipo_id e nulavel), mas a tela abriria
        # so com "-- sem tipo --" e o rotulo da grade sairia sem sigla --
        # sintoma que parece bug de tela e e semente que nao entrou.
        tipos = await conn.fetch(
            "SELECT sigla, nome FROM tipos_reuniao ORDER BY ordem, nome"
        )
        print("tipos de reuniao:", ", ".join(f"{t['sigla']}={t['nome']}" for t in tipos))
        if not tipos:
            print("AVISO: nenhum tipo de reuniao cadastrado.")

        # A UNIQUE de tarefa_id e a regra "uma tarefa nunca vira duas
        # reunioes". E ela que impede dois cliques em "colocar na agenda"
        # de duplicarem a reuniao na grade -- vale conferir que chegou.
        unica = await conn.fetchval(
            """
            SELECT count(*)
              FROM pg_indexes
             WHERE tablename = 'reunioes'
               AND indexdef ILIKE '%UNIQUE%'
               AND indexdef ILIKE '%tarefa_id%'
            """
        )
        print("UNIQUE em reunioes.tarefa_id:", "OK" if unica else "AUSENTE")
        return 0
    finally:
        await conn.close()


sys.exit(asyncio.run(main()))
PY

echo "migration 011 aplicada."
