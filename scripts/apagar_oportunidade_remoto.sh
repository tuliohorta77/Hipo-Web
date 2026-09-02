#!/usr/bin/env bash
# HIPO — Apaga uma oportunidade: metade que roda NA EC2.
#
#   bash /tmp/apagar_oportunidade_remoto.sh OPP-2026-00001            -> so mostra
#   bash /tmp/apagar_oportunidade_remoto.sh OPP-2026-00001 --commit   -> apaga
#
# Mesma mecanica da carga: root le o .env (que o usuario hipo nao consegue
# ler) e entrega a DATABASE_URL por ambiente ao processo do hipo.
set -euo pipefail

APP=/home/hipo/app
ENVFILE="$APP/.env"
NUMERO="${1:-}"
COMMIT="${2:-}"

[ -n "$NUMERO" ] || { echo "Uso: $0 OPP-AAAA-NNNNN [--commit]" >&2; exit 1; }
[ -f /tmp/apagar_oportunidade.py ] || { echo "FALTA /tmp/apagar_oportunidade.py" >&2; exit 1; }

sudo mkdir -p "$APP/scripts"
sudo cp /tmp/apagar_oportunidade.py "$APP/scripts/apagar_oportunidade.py"
sudo touch "$APP/scripts/__init__.py"
sudo chown -R hipo:hipo "$APP/scripts"

if ! sudo test -r "$ENVFILE"; then
    echo "Nao consigo ler $ENVFILE nem como root:" >&2
    sudo ls -l "$ENVFILE" >&2 || true
    exit 1
fi

DB_URL="$(sudo grep -m1 -E '^[[:space:]]*(export[[:space:]]+)?DATABASE_URL=' "$ENVFILE" \
          | tr -d '\r' | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//")"
[ -n "$DB_URL" ] || { echo "DATABASE_URL nao encontrada em $ENVFILE." >&2; exit 1; }

if sudo test -x "$APP/venv/bin/python"; then
    PY="$APP/venv/bin/python"
elif sudo test -x "$APP/.venv/bin/python"; then
    PY="$APP/.venv/bin/python"
else
    PY="$(command -v python3)"
fi

# O backup vai para /tmp com dono hipo, para o .ps1 poder trazer por scp.
BACKUP="/tmp/${NUMERO//\//-}_backup.json"

cd "$APP"
sudo -u hipo env \
    DATABASE_URL="$DB_URL" \
    PYTHONPATH="$APP" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m scripts.apagar_oportunidade "$NUMERO" --backup "$BACKUP" $COMMIT

sudo chmod 644 "$BACKUP" 2>/dev/null || true
