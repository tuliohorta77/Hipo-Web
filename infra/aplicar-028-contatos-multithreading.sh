#!/usr/bin/env bash
#
# HIPO - migration 028 (contatos: ABM / multithreading). Entrega 045.
#
# ORDEM: testes verdes -> ESTE SCRIPT -> push.
# O codigo novo le tarefas.contato_id, oportunidade_contatos e as colunas
# novas de contatos em TODAS as telas de tarefa, agenda e oportunidade:
# sem a migration, essas telas dao 500. Por isso ela vem ANTES do push.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-028-contatos-multithreading.sh
#
# ADITIVA e IDEMPOTENTE: 4 colunas em contatos, 1 tabela nova
# (oportunidade_contatos), 1 coluna em tarefas. Backfill: o contato atual
# de cada oportunidade vira o principal do comite; a tarefa ganha o
# contato da reuniao da agenda; tarefa de interacao AINDA ABERTA herda o
# principal da oportunidade. Nenhum DROP, nenhum DELETE. Rodar duas vezes
# nao faz nada na segunda. Nao exige export.
#
# ASCII puro.

set -euo pipefail

SQL=/tmp/028_contatos_multithreading.sql
ENV_PATH=/home/hipo/app/.env

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
SELECT 'oportunidade_contatos:      ' || CASE WHEN to_regclass('oportunidade_contatos') IS NULL THEN 'NAO existe' ELSE 'existe' END;
SELECT 'tarefas.contato_id:         ' || CASE WHEN EXISTS (
         SELECT 1 FROM information_schema.columns
          WHERE table_name = 'tarefas' AND column_name = 'contato_id') THEN 'existe' ELSE 'NAO existe' END;
SELECT 'contatos.telefone_2:        ' || CASE WHEN EXISTS (
         SELECT 1 FROM information_schema.columns
          WHERE table_name = 'contatos' AND column_name = 'telefone_2') THEN 'existe' ELSE 'NAO existe' END;
SELECT 'oportunidades com contato:  ' || count(*) FROM oportunidades WHERE contato_id IS NOT NULL;
SQL_ESTADO
}

depois() {
    psql "$DATABASE_URL" -At <<'SQL_DEPOIS'
SELECT 'principais no comite:       ' || count(*) FROM oportunidade_contatos WHERE principal;
SELECT 'opp com contato sem comite: ' || count(*) FROM oportunidades o
 WHERE o.contato_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM oportunidade_contatos x
        WHERE x.oportunidade_id = o.id AND x.contato_id = o.contato_id AND x.principal);
SELECT 'tarefas com contato:        ' || count(*) FROM tarefas WHERE contato_id IS NOT NULL;
SELECT 'abertas de interacao sem contato (pedem ao editar): ' || count(*) FROM tarefas
 WHERE contato_id IS NULL AND concluida_em IS NULL AND cancelada_em IS NULL
   AND tipo IN ('ligacao','reuniao','visita','whatsapp','email');
SQL_DEPOIS
}

echo "== antes =="
estado
echo

if ! perguntar "Aplicar a migration 028 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
estado
depois

echo
echo "Migration 028 aplicada. \"opp com contato sem comite\" tem que ser 0. Agora o push."
