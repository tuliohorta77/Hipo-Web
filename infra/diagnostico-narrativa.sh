#!/usr/bin/env bash
# =====================================================================
# HIPO - Por que a narrativa nao apareceu no e-mail?
#
# SO LE. Tres desfechos possiveis, e cada um pede uma acao diferente:
#
#   1. narrativa preenchida no banco -> o problema e no RENDER, nao na IA
#   2. narrativa NULA e modelo NULO  -> a chamada a API nao aconteceu
#      (sem chave, timeout, HTTP != 200). O log diz qual.
#   3. narrativa NULA e modelo PREENCHIDO -> impossivel pelo codigo atual
#      (grava os dois juntos), mas vale conferir
#
#   ... e o caso que mais importa:
#
#   4. o log tem "narrativa descartada" -> a guarda numerica barrou, e ela
#      lista os numeros que considerou inventados. Se forem numeros que
#      EXISTEM na telemetria, a guarda e que esta com falso positivo.
#
#   scp -i "$HOME/Downloads/chave-hipo.pem" \
#       infra/diagnostico-narrativa.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/diagnostico-narrativa.sh'
# =====================================================================
set -o pipefail

titulo() { printf '\n==== %s ====\n' "$1"; }
D=$(sudo sed -n 's/^DATABASE_URL=//p' /home/hipo/app/.env)
[ -n "$D" ] || { echo "DATABASE_URL vazia."; exit 1; }

titulo "1. O que o banco guardou"
psql "$D" -c "select dia, gerado_em, enviado_em, narrativa_modelo,
                     coalesce(length(narrativa), -1) as tam_narrativa, erro
                from relatorios_diarios order by dia desc;"
echo "  tam_narrativa = -1 significa NULO (nao vazio)."

titulo "2. A narrativa em si"
psql "$D" -Atc "select coalesce(narrativa, '(NULA)') from relatorios_diarios
                 order by dia desc limit 1;" | sed 's/^/  /'

titulo "3. O que a IA registrou no log (ultima hora)"
# O envio rodou por systemd-run, unit transitoria -- por isso o filtro e por
# TEXTO e nao por -u hipo-fechamento.
sudo journalctl --since '60 min ago' --no-pager 2>/dev/null \
    | grep -iE 'hipo\.ia|hipo\.fechamento|narrativa|anthropic' \
    | tail -40 | sed 's/^/  /'
echo "  (se aparecer 'narrativa descartada', os numeros barrados vem na linha)"

titulo "4. A chave e o modelo ainda respondem?"
KEY=$(sudo sed -n 's/^ANTHROPIC_API_KEY=//p' /home/hipo/app/.env)
MODELO=$(sudo sed -n 's/^ANTHROPIC_MODEL=//p' /home/hipo/app/.env)
MODELO=${MODELO:-claude-haiku-4-5}
if [ -z "$KEY" ]; then
    echo "  ANTHROPIC_API_KEY ausente."
else
    CODIGO=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
        "https://api.anthropic.com/v1/models/$MODELO" \
        -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01")
    echo "  GET /v1/models/$MODELO -> HTTP $CODIGO   (200 = chave e modelo ok)"
fi
unset KEY

printf '\n==== FIM ====\n'
