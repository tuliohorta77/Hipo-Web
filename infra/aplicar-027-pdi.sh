#!/usr/bin/env bash
#
# HIPO - migration 027 (Carreira: PDI).
#
# ORDEM: testes verdes -> ESTE SCRIPT -> push -> carga.
# O codigo novo le pdi_acoes na aba PDI da Carreira: sem a tabela, a aba
# da 500. Por isso a migration vem ANTES do push.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-027-pdi.sh
#
# ADITIVA e IDEMPOTENTE: uma tabela nova. Nenhum DROP, nenhum DELETE.
# Rodar duas vezes nao faz nada na segunda. Nao exige export.
#
# ASCII puro.

set -euo pipefail

SQL=/tmp/027_pdi.sql
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
SELECT CASE WHEN count(*) = 1 THEN 'pdi_acoes existe' ELSE 'pdi_acoes NAO existe' END
  FROM information_schema.tables WHERE table_name = 'pdi_acoes';
SQL_CONTA
}

echo "== antes =="
tem_coluna
echo

if ! perguntar "Aplicar a migration 027 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
tem_coluna

echo
echo "Migration 027 aplicada. Agora o push."
