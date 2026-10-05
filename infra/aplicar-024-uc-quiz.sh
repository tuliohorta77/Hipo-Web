#!/usr/bin/env bash
#
# HIPO - migration 024 (UC: quiz depois da aula).
#
# ORDEM: testes verdes -> ESTE SCRIPT -> push -> carga.
# O codigo novo le uc_perguntas e uc_tentativas em toda abertura de aula:
# sem as tabelas, a aula da 500. Por isso a migration vem ANTES do push.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-024-uc-quiz.sh
#
# NAO DESTRUTIVA e IDEMPOTENTE: tres tabelas novas, um DEFAULT novo e
# nota_minima 70 -> 85 (valor nunca usado). Nenhum DROP, nenhum DELETE.
# Rodar duas vezes nao faz nada na segunda. Nao exige export.
#
# ASCII puro.

set -euo pipefail

SQL=/tmp/024_uc_quiz.sql
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

tem_coluna() {
    psql "$DATABASE_URL" -At <<'SQL_CONTA'
SELECT 'tabelas do quiz: ' || count(*) || ' de 3'
  FROM information_schema.tables
 WHERE table_name IN ('uc_perguntas', 'uc_alternativas', 'uc_tentativas');
SELECT 'aulas com nota minima 85: ' || count(*) FILTER (WHERE nota_minima = 85) || ' de ' || count(*)
  FROM uc_aulas;
SQL_CONTA
}

echo "== antes =="
tem_coluna
echo

if ! perguntar "Aplicar a migration 024 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
tem_coluna

echo
echo "Migration 024 aplicada. Agora o push."
