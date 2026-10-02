#!/usr/bin/env bash
#
# HIPO - migration 020 (Universidade Corporativa, UC-1).
#
# ORDEM OBRIGATORIA, porque tem migration:
#   1. testes verdes  ->  2. ESTE SCRIPT  ->  3. push
# Invertido, o codigo novo sobe e a tela "Universidade" estoura 500
# pedindo tabelas que ainda nao existem. (O resto do HIPO nao le estas
# tabelas: so a UC quebraria.)
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-020-uc.sh
#
# ADITIVA e IDEMPOTENTE: cinco tabelas e quatro indices novos, nenhum
# DROP, nenhum DELETE. Rodar duas vezes nao faz nada na segunda. Por isso
# NAO exige o export previo em CSV.
#
# ASCII puro.

set -euo pipefail

SQL=/tmp/020_uc.sql
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
SELECT 'tabelas da UC existentes: ' || count(*)
  FROM information_schema.tables
 WHERE table_name IN ('uc_trilhas', 'uc_trilha_cargos', 'uc_aulas',
                      'uc_materiais', 'uc_progresso');
SQL_CONTA
}

echo "== antes =="
contar_tabelas
echo

if ! perguntar "Aplicar a migration 020 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
contar_tabelas

echo
echo "Migration 020 aplicada. Agora o push."
