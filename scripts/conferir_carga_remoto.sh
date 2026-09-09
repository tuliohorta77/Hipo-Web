#!/usr/bin/env bash
# HIPO - Confere o estado da base depois das cargas. So LE, nunca escreve.
#
#   bash /tmp/conferir_carga_remoto.sh
#
# Existe porque "COMMIT feito" nao e prova de nada: o numero que importa e o
# que ficou no banco, e conferir isso a mao no psql e o passo que ninguem
# faz. Roda sozinho no fim do subir-carteira.ps1.
set -euo pipefail

APP=/home/hipo/app
ENVFILE="$APP/.env"

if ! sudo test -r "$ENVFILE"; then
    echo "Nao consigo ler $ENVFILE nem como root:" >&2
    sudo ls -l "$ENVFILE" >&2 || true
    exit 1
fi

DB_URL="$(sudo grep -m1 -E '^[[:space:]]*(export[[:space:]]+)?DATABASE_URL=' "$ENVFILE" \
          | tr -d '\r' | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//")"

if [ -z "$DB_URL" ]; then
    echo "DATABASE_URL nao encontrada em $ENVFILE." >&2
    exit 1
fi

echo "banco : $(echo "$DB_URL" | sed 's/:[^:@]*@/:****@/')"

if sudo test -x "$APP/venv/bin/python"; then
    PY="$APP/venv/bin/python"
elif sudo test -x "$APP/.venv/bin/python"; then
    PY="$APP/.venv/bin/python"
else
    PY="$(command -v python3)"
fi

SQL="
\echo ''
\echo '== CONTAS =='
SELECT count(*) AS total,
       count(*) FILTER (WHERE nao_prospectar) AS nao_prospectar,
       count(*) FILTER (WHERE eh_finder)      AS finders,
       count(*) FILTER (WHERE NOT ativo)      AS inativas
  FROM contas;

\echo '== CONTATOS =='
SELECT (SELECT count(*) FROM contatos)       AS contatos,
       (SELECT count(*) FROM conta_contatos) AS vinculos,
       (SELECT count(*) FROM (SELECT conta_id FROM conta_contatos
                               WHERE principal GROUP BY 1 HAVING count(*) > 1) x)
                                             AS contas_2_principais;

\echo '== OPORTUNIDADES por fase =='
SELECT fase, status, count(*) FROM oportunidades GROUP BY 1,2 ORDER BY 1,2;

\echo '== CARTEIRA ORACULUS (pela origem) =='
SELECT o.fase, count(*) AS qtd,
       count(*) FILTER (WHERE o.contato_id IS NOT NULL) AS com_contato,
       count(*) FILTER (WHERE o.finder_conta_id IS NOT NULL) AS com_finder
  FROM oportunidades o
  JOIN origens og ON og.id = o.origem_id
 WHERE og.slug = 'carteira-oraculus'
 GROUP BY 1 ORDER BY 1;

\echo '== DIVISAO DOS ENVOLVIDOS (carteira Oraculus) =='
SELECT u.nome, oe.papel, count(*) AS oportunidades
  FROM oportunidade_envolvidos oe
  JOIN oportunidades o ON o.id = oe.oportunidade_id
  JOIN origens og      ON og.id = o.origem_id AND og.slug = 'carteira-oraculus'
  JOIN usuarios u      ON u.id = oe.usuario_id
 GROUP BY 1,2 ORDER BY 1;

\echo '== ALERTA: contas bloqueadas COM negocio em aberto =='
\echo '(o bloqueio nao fecha nada -- estas precisam ser encerradas a mao)'
SELECT c.cnpj, c.razao_social, count(*) AS em_aberto
  FROM contas c
  JOIN oportunidades o ON o.conta_id = c.id
 WHERE c.nao_prospectar AND o.status IN ('ativa','suspensa')
 GROUP BY 1,2 ORDER BY 3 DESC;
"

if command -v psql > /dev/null 2>&1; then
    # Por STDIN, e nao com -c: o -c manda a string como UMA consulta e nao
    # interpreta meta-comando, entao os \echo dos titulos estouram com
    # 'syntax error at or near "\"'. Por stdin o psql processa os dois.
    printf '%s\n' "$SQL" | psql "$DB_URL" -v ON_ERROR_STOP=1
else
    echo "psql nao encontrado nesta maquina; pulei a conferencia." >&2
    echo "Confira pela tela: https://hipogestao.com.br/crm/contas" >&2
fi
