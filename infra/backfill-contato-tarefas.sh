#!/usr/bin/env bash
#
# HIPO - backfill: "com quem" foi cada tarefa de interacao antiga.
#
# A migration 028 so preencheu tarefas.contato_id das tarefas ABERTAS. O
# historico concluido ficou sem contato e, por isso, a temperatura (047)
# mostra todo mundo Frio. Este script completa o resto:
#
#   tarefa de ligacao, reuniao, visita, WhatsApp ou e-mail, de OPORTUNIDADE,
#   ainda sem contato  ->  recebe o contato principal da oportunidade
#   (oportunidades.contato_id, o "marcado no CRM").
#
# Fica de fora: tarefa de parceiro (conta) -- la nao existe um contato
# marcado; tarefa de outro tipo (proposta, outro); tarefa que ja tem
# contato (nunca e sobrescrita); oportunidade sem contato.
#
# REVERSIVEL: antes de gravar, os ids das tarefas alteradas vao para
#   ~/backfill-contato-tarefas-AAAAMMDD-HHMMSS.csv
# Para desfazer: UPDATE tarefas SET contato_id = NULL WHERE id IN (...csv).
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/backfill-contato-tarefas.sh
# Sem DROP, sem DELETE. Rodar duas vezes nao faz nada na segunda.
#
# ASCII puro.

set -euo pipefail

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
    # O ssh do Windows pode mandar o Enter como \r: "s\r" nao e "s".
    resposta=$(printf '%s' "$resposta" | tr -d '\r[:space:]')
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

DATABASE_URL=$(sudo cat "$ENV_PATH" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERRO: $ENV_PATH sem DATABASE_URL."
    exit 1
fi

# Mascara a senha. Confira o HOST: e a unica barreira contra o banco errado.
echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"
echo

# A regra da temperatura (services/temperatura_contato.py) reescrita em SQL
# so para mostrar o antes e o depois. Quem vale na tela e a do Python.
temperaturas() {
    psql "$DATABASE_URL" -At -F ' ' <<'SQL_TEMP'
WITH contatos_em_opp AS (
    SELECT DISTINCT contato_id FROM oportunidade_contatos
),
pontos AS (
    SELECT t.contato_id,
           sum(
             (CASE WHEN now() - t.concluida_em <= interval '15 days' THEN 3
                   WHEN now() - t.concluida_em <= interval '31 days' THEN 2
                   WHEN now() - t.concluida_em <= interval '61 days' THEN 1
                   ELSE 0 END)
             * (CASE WHEN t.tipo IN ('reuniao', 'visita') THEN 2 ELSE 1 END)
           ) AS pts,
           max(t.concluida_em) AS ultima
      FROM tarefas t
     WHERE t.contato_id IS NOT NULL
       AND t.concluida_em IS NOT NULL AND t.cancelada_em IS NULL
     GROUP BY t.contato_id
),
nivel AS (
    SELECT c.contato_id,
           CASE WHEN coalesce(p.pts, 0) >= 6 AND now() - p.ultima <= interval '15 days' THEN 'quente'
                WHEN coalesce(p.pts, 0) >= 2 THEN 'morno'
                ELSE 'frio' END AS n
      FROM contatos_em_opp c LEFT JOIN pontos p ON p.contato_id = c.contato_id
)
SELECT '  ' || rpad(n, 8) || count(*) FROM nivel GROUP BY n ORDER BY n DESC;
SQL_TEMP
}

estado() {
    psql "$DATABASE_URL" -At <<'SQL_ESTADO'
SELECT 'vao receber o contato:            ' || count(*)
  FROM tarefas t JOIN oportunidades o ON o.id = t.oportunidade_id
 WHERE t.contato_id IS NULL AND o.contato_id IS NOT NULL
   AND t.tipo IN ('ligacao', 'reuniao', 'visita', 'whatsapp', 'email');
SELECT '   ' || rpad(x.tipo, 9) || ' ' || rpad(x.situacao, 10) || count(*)
  FROM (SELECT t.tipo,
               CASE WHEN t.concluida_em IS NOT NULL THEN 'concluida'
                    WHEN t.cancelada_em IS NOT NULL THEN 'cancelada'
                    ELSE 'aberta' END AS situacao
          FROM tarefas t JOIN oportunidades o ON o.id = t.oportunidade_id
         WHERE t.contato_id IS NULL AND o.contato_id IS NOT NULL
           AND t.tipo IN ('ligacao', 'reuniao', 'visita', 'whatsapp', 'email')) x
 GROUP BY x.tipo, x.situacao ORDER BY x.tipo, x.situacao;
SELECT 'ficam sem (opp sem contato):      ' || count(*)
  FROM tarefas t JOIN oportunidades o ON o.id = t.oportunidade_id
 WHERE t.contato_id IS NULL AND o.contato_id IS NULL
   AND t.tipo IN ('ligacao', 'reuniao', 'visita', 'whatsapp', 'email');
SELECT 'ficam sem (tarefa de parceiro):   ' || count(*)
  FROM tarefas t
 WHERE t.contato_id IS NULL AND t.oportunidade_id IS NULL
   AND t.tipo IN ('ligacao', 'reuniao', 'visita', 'whatsapp', 'email');
SQL_ESTADO
}

echo "== antes =="
estado
echo
echo "temperatura dos contatos que estao em oportunidade (antes):"
temperaturas
echo

QTD=$(psql "$DATABASE_URL" -At -c "
SELECT count(*)
  FROM tarefas t JOIN oportunidades o ON o.id = t.oportunidade_id
 WHERE t.contato_id IS NULL AND o.contato_id IS NOT NULL
   AND t.tipo IN ('ligacao', 'reuniao', 'visita', 'whatsapp', 'email');")

if [ "$QTD" = "0" ]; then
    echo "Nada a fazer: nenhuma tarefa de interacao de oportunidade sem contato."
    exit 0
fi

if ! perguntar "Gravar o contato principal da oportunidade em $QTD tarefa(s)?"; then
    echo "Cancelado. Nada foi gravado."
    exit 3
fi

CSV="$HOME/backfill-contato-tarefas-$(date +%Y%m%d-%H%M%S).csv"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q <<SQL_GRAVA
BEGIN;
CREATE TEMP TABLE alvo_backfill ON COMMIT DROP AS
SELECT t.id AS tarefa_id, o.contato_id
  FROM tarefas t JOIN oportunidades o ON o.id = t.oportunidade_id
 WHERE t.contato_id IS NULL AND o.contato_id IS NOT NULL
   AND t.tipo IN ('ligacao', 'reuniao', 'visita', 'whatsapp', 'email');
\copy (SELECT tarefa_id, contato_id FROM alvo_backfill ORDER BY tarefa_id) TO '$CSV' WITH (FORMAT csv, HEADER)
UPDATE tarefas t
   SET contato_id = a.contato_id
  FROM alvo_backfill a
 WHERE t.id = a.tarefa_id
   AND t.contato_id IS NULL;
COMMIT;
SQL_GRAVA

echo "Gravado. Ids das tarefas alteradas (para desfazer): $CSV"
echo
echo "== depois =="
estado
echo
echo "temperatura dos contatos que estao em oportunidade (depois):"
temperaturas
