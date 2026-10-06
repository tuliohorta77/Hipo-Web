#!/usr/bin/env bash
#
# HIPO - migration 029 (confirmacao da vespera). Entrega 048.
#
# ORDEM: testes verdes -> ESTE SCRIPT -> push.
# O codigo novo le tarefas.confirmacao_de nas telas de tarefa e agenda:
# sem a migration, essas telas dao 500. Por isso ela vem ANTES do push.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-029-confirmacao-vespera.sh
# e, se a instancia MOS existir (entrega 046), de novo na base dela:
#   ENV_PATH=/home/hipo/mos/.env bash /tmp/aplicar-029-confirmacao-vespera.sh
#
# ADITIVA e IDEMPOTENTE: 1 coluna em tarefas, 1 CHECK, 1 indice unico
# parcial. Sem backfill: so reunioes marcadas ou remarcadas depois do
# deploy ganham a confirmacao. Nenhum DROP, nenhum DELETE. Rodar duas
# vezes nao faz nada na segunda. Nao exige export.
#
# ASCII puro.

set -euo pipefail

SQL=/tmp/029_confirmacao_vespera.sql
ENV_PATH=${ENV_PATH:-/home/hipo/app/.env}

tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }

perguntar() {  # perguntar "texto" -> 0 se sim
    local texto="$1" resposta
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then
        echo "  ($texto -> sim, por HIPO_CONFIRMADO=1)"
        return 0
    fi
    if ! tem_tty; then
        echo "ERRO: sem terminal para confirmar. Use 'ssh -t' ou HIPO_CONFIRMADO=1."
        exit 1
    fi
    read -r -p "$texto [s/N] " resposta < /dev/tty
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

if [ ! -f "$SQL" ]; then
    echo "ERRO: nao achei $SQL. Mande por scp antes."
    exit 1
fi

DATABASE_URL=$(sudo cat "$ENV_PATH" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERRO: $ENV_PATH sem DATABASE_URL."
    exit 1
fi

# Mascara a senha. Confira o HOST: e a unica barreira contra o banco errado.
echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"
echo

estado() {
    psql "$DATABASE_URL" -At <<'SQL_ESTADO'
SELECT 'tarefas.confirmacao_de:          ' || CASE WHEN EXISTS (
         SELECT 1 FROM information_schema.columns
          WHERE table_name = 'tarefas' AND column_name = 'confirmacao_de') THEN 'existe' ELSE 'NAO existe' END;
SELECT 'uq_tarefas_confirmacao_aberta:   ' || CASE WHEN to_regclass('uq_tarefas_confirmacao_aberta') IS NULL THEN 'NAO existe' ELSE 'existe' END;
SELECT 'ck_tarefa_confirmacao:           ' || CASE WHEN EXISTS (
         SELECT 1 FROM pg_constraint WHERE conname = 'ck_tarefa_confirmacao') THEN 'existe' ELSE 'NAO existe' END;
SQL_ESTADO
}

echo "== antes =="
estado
echo

if ! perguntar "Aplicar a migration 029 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
estado

echo
echo "Migration 029 aplicada. As tres linhas tem que dizer 'existe'. Agora o push."
