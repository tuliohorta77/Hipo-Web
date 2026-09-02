#!/usr/bin/env bash
# HIPO — Corrige os envolvidos da carga: metade que roda NA EC2.
#
#   bash /tmp/corrigir_envolvidos_remoto.sh            -> dry-run
#   bash /tmp/corrigir_envolvidos_remoto.sh --commit   -> grava
#
# Mesma mecanica da carga: root le o .env (que o usuario hipo nao consegue
# ler) e entrega a DATABASE_URL por ambiente ao processo do hipo.
set -euo pipefail

APP=/home/hipo/app
ENVFILE="$APP/.env"
COMMIT="${1:-}"

for f in /tmp/corrigir_envolvidos_crm_omie.py /tmp/crm_omie_ativas_2026-09-01.json; do
    [ -f "$f" ] || { echo "FALTA $f. Rode o corrigir-envolvidos.ps1, que faz o scp." >&2; exit 1; }
done

sudo mkdir -p "$APP/scripts/dados"
sudo cp /tmp/corrigir_envolvidos_crm_omie.py  "$APP/scripts/corrigir_envolvidos_crm_omie.py"
sudo cp /tmp/crm_omie_ativas_2026-09-01.json  "$APP/scripts/dados/crm_omie_ativas_2026-09-01.json"
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
sudo -u hipo env \
    DATABASE_URL="$DB_URL" \
    PYTHONPATH="$APP" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m scripts.corrigir_envolvidos_crm_omie $COMMIT
