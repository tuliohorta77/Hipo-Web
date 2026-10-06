#!/usr/bin/env bash
#
# HIPO - aplica UM arquivo .sql em TODAS as bases desta EC2 (entrega 046).
#
# Desde a 046 existem duas bases com o mesmo codigo:
#   principal  /home/hipo/app/.env  (Controller MedSeg)
#   mos        /home/hipo/mos/.env  (MOS)
# Migration que entra numa so deixa a outra dando 500 no primeiro deploy.
#
# Uso (na EC2, ec2-user, com terminal):
#   bash /tmp/mos/aplicar-sql-nas-bases.sh /tmp/029_alguma_coisa.sql
#
# Para os aplicar-NNN-*.sh que ja existem (antes / depois / backfill
# proprios), a regra da 046 e: ENV_PATH sobrescrevivel no topo
#   ENV_PATH=${ENV_PATH:-/home/hipo/app/.env}
# e rodar duas vezes:
#   bash /tmp/aplicar-NNN.sh
#   ENV_PATH=/home/hipo/mos/.env bash /tmp/aplicar-NNN.sh
#
# Para no primeiro erro: a base seguinte NAO recebe uma migration que
# falhou na anterior. ASCII puro.

set -euo pipefail

SQL="${1:-}"
[ -n "$SQL" ] && [ -f "$SQL" ] || { echo "uso: $0 arquivo.sql"; exit 1; }

BASES=(
    "principal:/home/hipo/app/.env"
    "mos:/home/hipo/mos/.env"
)

tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }
perguntar() {
    local r
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then return 0; fi
    tem_tty || { echo "ERRO: sem terminal. Use 'ssh -t' ou HIPO_CONFIRMADO=1."; exit 1; }
    read -r -p "$1 [s/N] " r < /dev/tty
    r="$(printf '%s' "$r" | tr -d '\r[:space:]')"
    [ "$r" = "s" ] || [ "$r" = "S" ]
}
url_de() {
    { cat "$1" 2>/dev/null || sudo cat "$1"; } | grep -E '^DATABASE_URL=' | tail -1 | cut -d= -f2- || true
}

echo "Arquivo: $SQL"
for b in "${BASES[@]}"; do
    nome="${b%%:*}"; env="${b#*:}"
    if [ ! -f "$env" ]; then
        echo "  $nome: sem $env -- pulando"
        continue
    fi
    url="$(url_de "$env")"
    [ -n "$url" ] || { echo "ERRO: $env sem DATABASE_URL"; exit 1; }
    echo
    echo "== $nome: $(echo "$url" | sed 's/:[^:@]*@/:****@/') =="
    perguntar "Aplicar nesta base?" || { echo "Cancelado."; exit 3; }
    psql "$url" -v ON_ERROR_STOP=1 -q -f "$SQL"
    echo "  OK  aplicado em $nome"
done
