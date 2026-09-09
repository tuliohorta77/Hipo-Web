#!/usr/bin/env bash
# =====================================================================
#  HIPO -- aplica a migration 012_agenda_desfecho.sql no RDS
#
#  Roda NA EC2, como root. O /home/hipo/app/.env e do ec2-user (o rsync
#  do CI o escreve) mesmo com o app rodando como hipo -- por isso root,
#  e nao `sudo -iu hipo`. Mesma escolha do aplicar-011-agenda.sh.
#
#  A 012 e ADITIVA e IDEMPOTENTE: ADD COLUMN IF NOT EXISTS, CREATE INDEX
#  IF NOT EXISTS, constraints dentro de um DO $$ que checa pg_constraint,
#  e UPDATEs por slug numa lista de dominio de 5 linhas. Nenhum DROP --
#  logo nao exige o export em CSV que as migrations destrutivas exigem.
#
#  O QUE ELA MUDA EM DADO EXISTENTE, e por que e seguro:
#
#    reunioes.agendado_por  <- criado_por, so onde esta NULL. Para o que
#                              ja existe, quem digitou e a melhor verdade
#                              disponivel. O `IS NULL` impede que uma
#                              segunda execucao sobrescreva correcao feita
#                              a mao depois.
#
#    tipos_reuniao          <- as siglas confirmadas pela operacao
#                              (DG/AP/FC/FP/VT). A semente da 011 era um
#                              palpite. Reunioes ja marcadas com esses
#                              tipos passam a exibir a sigla nova no
#                              rotulo -- que e o efeito desejado.
#
#  USO (chamado pelo deploy-015, ou a mao):
#     sudo bash /tmp/aplicar-012-agenda-desfecho.sh /tmp/012_agenda_desfecho.sql
# =====================================================================
set -euo pipefail

ARQ="${1:-/tmp/012_agenda_desfecho.sql}"
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

# A 012 mexe em `reunioes`, que a 011 criou. Sem ela, os ADD COLUMN
# falhariam com uma mensagem sobre relacao inexistente -- correta, mas
# que nao diz qual passo foi pulado.
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

COLUNAS = (
    "agendado_por",
    "desfecho",
    "desfecho_em",
    "desfecho_por",
    "desfecho_observacao",
    "desfecho_antecedencia_horas",
)
CONSTRAINTS = ("ck_reuniao_desfecho", "ck_reuniao_desfecho_em")
INDICES = ("idx_reunioes_agendado_por", "idx_reunioes_desfecho")

# As siglas confirmadas pela operacao. Conferidas por SLUG, que e o que
# nao muda -- a sigla e justamente o que esta mudando nesta migration.
ESPERADO = {
    "diagnostico": "DG",
    "apresentacao": "AP",
    "fechamento": "FC",
    "follow-up": "FP",
    "visita-tecnica": "VT",
}


async def main() -> int:
    caminho = sys.argv[1]
    with open(caminho, encoding="utf-8") as f:
        sql = f.read()

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        existe = await conn.fetchval(
            "SELECT to_regclass('public.reunioes') IS NOT NULL"
        )
        if not existe:
            print("ERRO: tabela `reunioes` nao existe -- rode a 011 primeiro.")
            return 1

        # Sem parametros, o asyncpg usa o simple query protocol -- que e o
        # que permite varios comandos e o BEGIN/COMMIT do proprio arquivo.
        await conn.execute(sql)

        presentes = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'reunioes'"
            )
        }
        faltando = [c for c in COLUNAS if c not in presentes]
        if faltando:
            print("ERRO: coluna(s) ausente(s) depois da migration:", ", ".join(faltando))
            return 1
        print("colunas de rastreio OK:", ", ".join(COLUNAS))

        for nome in CONSTRAINTS:
            tem = await conn.fetchval(
                "SELECT count(*) FROM pg_constraint WHERE conname = $1", nome
            )
            print(f"constraint {nome}:", "OK" if tem else "AUSENTE")
            if not tem:
                return 1

        for indice in INDICES:
            tem = await conn.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", f"public.{indice}"
            )
            print(f"indice {indice}:", "OK" if tem else "AUSENTE")

        # O backfill e a diferenca entre "o SDR nao marcou nada em agosto"
        # e "o campo nasceu vazio". Zero aqui, com reunioes na base, e
        # sintoma de backfill que nao rodou.
        total = await conn.fetchval("SELECT count(*) FROM reunioes")
        com_dono = await conn.fetchval(
            "SELECT count(*) FROM reunioes WHERE agendado_por IS NOT NULL"
        )
        print(f"reunioes: {total} no total, {com_dono} com agendado_por")
        if total and not com_dono:
            print("AVISO: nenhuma reuniao ficou com agendado_por -- confira o backfill.")

        tipos = await conn.fetch(
            "SELECT slug, sigla, nome FROM tipos_reuniao ORDER BY ordem, nome"
        )
        print("tipos de reuniao:", ", ".join(
            f"{t['sigla']}={t['nome']}" for t in tipos
        ))
        # A sigla entra no ROTULO da grade e o nome vai para o TITULO do
        # evento que o cliente le. Sigla errada aqui e um convite com
        # cadastro torto na caixa de entrada de quem esta comprando.
        por_slug = {t["slug"]: t["sigla"] for t in tipos}
        for slug, sigla in ESPERADO.items():
            atual = por_slug.get(slug)
            if atual != sigla:
                print(f"AVISO: slug {slug} esta com sigla {atual!r}, esperado {sigla!r}")
        return 0
    finally:
        await conn.close()


sys.exit(asyncio.run(main()))
PY

echo "migration 012 aplicada."
