#!/usr/bin/env bash
#
# HIPO - migration 017 (relatorios salvos).
#
# ORDEM OBRIGATORIA, porque tem migration:
#   1. testes verdes  ->  2. ESTE SCRIPT  ->  3. push
# Invertido, o codigo novo sobe e a lista de relatorios salvos (que a tela
# carrega ao abrir) estoura 500 pedindo uma tabela que ainda nao existe.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-017-relatorios.sh
#
# A migration e ADITIVA e IDEMPOTENTE: uma tabela e dois indices novos,
# nenhum DROP, nenhum DELETE. Rodar duas vezes nao faz nada na segunda. Por
# isso NAO exige o export previo em CSV.
#
# Tambem mostra, ANTES de gravar, quantas oportunidades cada usuario ativo
# enxerga pelo recorte de envolvimento. O modulo de Relatorios aplica esse
# recorte (operacional ve so o que e seu) -- quem estiver com zero vai abrir
# a tela e ver tudo vazio. Ver filtro-por-envolvimento.md, secao 7.

set -euo pipefail

SQL=/tmp/017_relatorios_salvos.sql
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

echo "== o que cada usuario ativo vai enxergar nos Relatorios (oportunidades) =="
psql "$DATABASE_URL" -P pager=off <<'EOF'
SELECT u.nome, u.cargo,
       CASE WHEN u.cargo IN ('Franqueado','ADM') THEN 'todas'
            ELSE COUNT(DISTINCT oe.oportunidade_id)::text END AS oportunidades_visiveis
  FROM usuarios u
  LEFT JOIN oportunidade_envolvidos oe ON oe.usuario_id = u.id
 WHERE u.ativo
 GROUP BY u.nome, u.cargo
 ORDER BY u.cargo, u.nome;
EOF
echo "  (operacional com 0 vai ver os relatorios vazios -- atribua a carteira antes)"
echo

if ! perguntar "Aplicar a migration 017 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo "== antes =="
psql "$DATABASE_URL" -At <<'EOF'
SELECT 'tabela relatorios_salvos existe: ' || count(*)
  FROM information_schema.tables WHERE table_name = 'relatorios_salvos';
EOF

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
psql "$DATABASE_URL" -At <<'EOF'
SELECT 'tabela relatorios_salvos existe: ' || count(*)
  FROM information_schema.tables WHERE table_name = 'relatorios_salvos';
SELECT 'indices: ' || string_agg(indexname, ', ')
  FROM pg_indexes WHERE tablename = 'relatorios_salvos';
EOF

echo
echo "Migration 017 aplicada. Agora o push."
