#!/usr/bin/env bash
#
# HIPO - migration 019 (transcricao ao vivo da reuniao).
#
# ORDEM OBRIGATORIA, porque tem migration:
#   1. testes verdes  ->  2. ESTE SCRIPT  ->  3. push
# Invertido, o codigo novo sobe e a tela "Reuniao ao vivo" estoura 500
# pedindo tabelas que ainda nao existem. (A agenda e o resto do HIPO nao
# leem estas tabelas: so a tela nova quebraria.)
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-019-reuniao-ao-vivo.sh
#
# A migration e ADITIVA e IDEMPOTENTE: duas tabelas e um indice novos,
# nenhum DROP, nenhum DELETE. Rodar duas vezes nao faz nada na segunda. Por
# isso NAO exige o export previo em CSV.
#
# ASCII puro.

set -euo pipefail

SQL=/tmp/019_reuniao_ao_vivo.sql
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

contar_tabelas() {
    psql "$DATABASE_URL" -At <<'SQL_CONTA'
SELECT 'tabelas ao vivo existentes: ' || count(*)
  FROM information_schema.tables
 WHERE table_name IN ('reuniao_sessoes_ao_vivo', 'reuniao_falas_ao_vivo');
SQL_CONTA
}

echo "== antes =="
contar_tabelas
echo

if ! perguntar "Aplicar a migration 019 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
contar_tabelas
psql "$DATABASE_URL" -At <<'SQL_DEPOIS'
SELECT 'indices: ' || string_agg(indexname, ', ' ORDER BY indexname)
  FROM pg_indexes
 WHERE tablename IN ('reuniao_sessoes_ao_vivo', 'reuniao_falas_ao_vivo');
SQL_DEPOIS

echo
echo "Migration 019 aplicada. Agora o push."
