#!/usr/bin/env bash
#
# HIPO - migration 026 (proposta com varios CNPJs e tabela de preco).
#
# ORDEM: testes verdes -> ESTE SCRIPT -> push.
# O codigo novo le oportunidade_contas na tela da conta e na busca do
# funil, e proposta_itens na aba Proposta: sem as tabelas, essas telas dao
# 500. Por isso a migration vem ANTES do push.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-026-proposta-multi-cnpj.sh
#
# ADITIVA e IDEMPOTENTE: 3 tabelas novas, 2 colunas novas em propostas,
# valor_por_vida passa a aceitar NULL, e cada proposta antiga ganha 1 item
# (INSERT). Nenhum DROP de tabela/coluna, nenhum DELETE. Rodar duas vezes
# nao faz nada na segunda. Nao exige export.
#
# ASCII puro.

set -euo pipefail

SQL=/tmp/026_proposta_multi_cnpj.sql
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
SELECT 'oportunidade_contas: ' || CASE WHEN to_regclass('oportunidade_contas') IS NULL THEN 'NAO existe' ELSE 'existe' END;
SELECT 'tabela_preco_faixas: ' || CASE WHEN to_regclass('tabela_preco_faixas') IS NULL THEN 'NAO existe' ELSE 'existe' END;
SELECT 'proposta_itens:      ' || CASE WHEN to_regclass('proposta_itens') IS NULL THEN 'NAO existe' ELSE 'existe' END;
SELECT 'propostas:           ' || count(*) FROM propostas;
SQL_CONTA
}

depois() {
    psql "$DATABASE_URL" -At <<'SQL_DEPOIS'
SELECT 'faixas na tabela:    ' || count(*) FROM tabela_preco_faixas;
SELECT 'propostas sem item:  ' || count(*) FROM propostas p
 WHERE NOT EXISTS (SELECT 1 FROM proposta_itens i WHERE i.proposta_id = p.id);
SELECT 'itens de proposta:   ' || count(*) FROM proposta_itens;
SQL_DEPOIS
}

echo "== antes =="
tem_coluna
echo

if ! perguntar "Aplicar a migration 026 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
tem_coluna
depois

echo
echo "Migration 026 aplicada. \"propostas sem item\" tem que ser 0. Agora o push."
