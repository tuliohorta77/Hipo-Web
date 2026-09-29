#!/usr/bin/env bash
#
# HIPO - migration 018 (metas_comerciais: metas do RPeR por squad e pessoa).
#
# ORDEM OBRIGATORIA, porque tem migration:
#   1. testes verdes  ->  2. ESTE SCRIPT  ->  3. push
# Invertido, o codigo novo sobe e a tela de metas do RPeR (e o proprio PPT,
# que le as metas) estoura 500 pedindo uma tabela que ainda nao existe.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-018-metas-comerciais.sh
#
# A migration e ADITIVA e IDEMPOTENTE: uma tabela e tres indices novos,
# nenhum DROP, nenhum DELETE. Rodar duas vezes nao faz nada na segunda. Por
# isso NAO exige o export previo em CSV.
#
# Tambem mostra, ANTES de gravar, quem vai sair em cada squad do RPeR:
# usuarios ATIVOS com cargo EC, SDR ou EV. Quem estiver com o cargo errado
# sai no bloco errado do PPT -- corrija o cargo antes da reuniao.

set -euo pipefail

SQL=/tmp/018_metas_comerciais.sql
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

echo "== quem sai em cada squad do RPeR (usuarios ativos) =="
psql "$DATABASE_URL" -P pager=off <<'SQL_SQUADS'
SELECT cargo AS squad,
       string_agg(nome || ' <' || email || '>', ', ' ORDER BY nome) AS pessoas
  FROM usuarios
 WHERE ativo AND cargo IN ('EC', 'SDR', 'EV')
 GROUP BY cargo
 ORDER BY cargo;
SQL_SQUADS
echo "  (squad sem ninguem sai zerado no PPT)"
echo

if ! perguntar "Aplicar a migration 018 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo "== antes =="
psql "$DATABASE_URL" -At <<'SQL_ANTES'
SELECT 'tabela metas_comerciais existe: ' || count(*)
  FROM information_schema.tables WHERE table_name = 'metas_comerciais';
SQL_ANTES

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
psql "$DATABASE_URL" -At <<'SQL_DEPOIS'
SELECT 'tabela metas_comerciais existe: ' || count(*)
  FROM information_schema.tables WHERE table_name = 'metas_comerciais';
SELECT 'indices: ' || string_agg(indexname, ', ')
  FROM pg_indexes WHERE tablename = 'metas_comerciais';
SQL_DEPOIS

echo
echo "Migration 018 aplicada. Agora o push."
