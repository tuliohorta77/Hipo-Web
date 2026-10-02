#!/usr/bin/env bash
#
# HIPO - migration 021 (scorecard da reuniao contra o Roteiro de Vendas).
#
# ORDEM OBRIGATORIA, porque tem migration:
#   1. testes verdes  ->  2. ESTE SCRIPT  ->  3. push
# Invertido, o codigo novo sobe e o MONITOR inteiro estoura 500: o painel
# passa a ler reuniao_avaliacoes (quadro SCORECARD e coluna Nota do APRE).
# A TV da sala ficaria com o aviso de erro ate a migration rodar.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-021-reuniao-avaliacao.sh
#
# A migration e ADITIVA e IDEMPOTENTE: duas tabelas e um indice novos,
# nenhum DROP, nenhum DELETE. Rodar duas vezes nao faz nada na segunda. Por
# isso NAO exige o export previo em CSV.
#
# ASCII puro.

set -euo pipefail

SQL=/tmp/021_reuniao_avaliacao.sql
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
SELECT 'tabelas do scorecard existentes: ' || count(*)
  FROM information_schema.tables
 WHERE table_name IN ('reuniao_avaliacoes', 'reuniao_avaliacao_itens');
SQL_CONTA
}

echo "== antes =="
contar_tabelas
echo

if ! perguntar "Aplicar a migration 021 nesse banco?"; then
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
 WHERE tablename IN ('reuniao_avaliacoes', 'reuniao_avaliacao_itens');
SELECT 'transcricoes prontas de oportunidade desde 01/09 (candidatas ao backfill): '
       || count(*)
  FROM reuniao_transcricoes rt
  JOIN reunioes r ON r.id = rt.reuniao_id
  JOIN tarefas t  ON t.id = r.tarefa_id
 WHERE rt.status = 'pronta' AND t.oportunidade_id IS NOT NULL
   AND t.prazo >= '2026-09-01';
SQL_DEPOIS

echo
echo "Migration 021 aplicada. Agora o push."
