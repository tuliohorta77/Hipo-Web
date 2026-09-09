#!/usr/bin/env bash
# HIPO - Carga da carteira Oraculus: metade que roda NA EC2.
#
# Chamado pelo carga-oraculus.ps1.
#
#   bash /tmp/carga_oraculus_remoto.sh <cnpj-finder> [outros args...]
#
# Exemplos:
#   bash /tmp/carga_oraculus_remoto.sh 12345678000199                 -> dry-run
#   bash /tmp/carga_oraculus_remoto.sh 12345678000199 --commit        -> grava
#   bash /tmp/carga_oraculus_remoto.sh 12345678000199 --limite 100 --commit
#
# O primeiro argumento e SEMPRE o CNPJ da Oraculus; o resto e repassado
# inteiro ao importador.
#
# POR QUE O .env E LIDO COMO ROOT: mesma razao do carga_crm_omie_remoto.sh.
set -euo pipefail

APP=/home/hipo/app
ENVFILE="$APP/.env"

if [ $# -lt 1 ]; then
    echo "Uso: bash $0 <cnpj-da-oraculus> [--commit] [--limite N] ..." >&2
    exit 1
fi
FINDER="$1"; shift

for f in /tmp/importar_oraculus.py /tmp/oraculus_2026-09-09.json; do
    [ -f "$f" ] || { echo "FALTA $f. Rode o carga-oraculus.ps1, que faz o scp." >&2; exit 1; }
done

sudo mkdir -p "$APP/scripts/dados"
sudo cp /tmp/importar_oraculus.py       "$APP/scripts/importar_oraculus.py"
sudo cp /tmp/oraculus_2026-09-09.json   "$APP/scripts/dados/oraculus_2026-09-09.json"
sudo touch "$APP/scripts/__init__.py"
sudo chown -R hipo:hipo "$APP/scripts"

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
echo "python: $PY"
echo

cd "$APP"

# Repassa com "$@", preservando os limites de cada argumento:
# --finder-razao "RAZAO COM ESPACO" tem que chegar como UM argumento
# no Python. Achatar numa string so quebra em tres.
#
# O comentario fica ACIMA do bloco: dentro dele, cada linha termina em
# barra invertida, entao um "#" ali nao e comentario -- vira argumento
# do env, e o erro so aparece na hora de rodar a carga.
sudo -u hipo env \
    DATABASE_URL="$DB_URL" \
    PYTHONPATH="$APP" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m scripts.importar_oraculus --finder-cnpj "$FINDER" "$@"
