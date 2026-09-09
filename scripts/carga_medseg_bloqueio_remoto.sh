#!/usr/bin/env bash
# HIPO - Bloqueio dos clientes MedSeg: metade que roda NA EC2.
#
# Chamado pelo carga-medseg-bloqueio.ps1. Instala o importador e o JSON em
# /home/hipo/app/scripts e roda a carga.
#
#   bash /tmp/carga_medseg_bloqueio_remoto.sh            -> dry-run (rollback)
#   bash /tmp/carga_medseg_bloqueio_remoto.sh --commit   -> grava
#
# POR QUE O .env E LIDO COMO ROOT
#   /home/hipo/app/.env nao e legivel pelo proprio usuario hipo. Um
#   `source .env` dentro do bloco que roda como hipo morre com "Permission
#   denied". Entao root le o arquivo, extrai a DATABASE_URL e entrega por
#   variavel de ambiente ao processo do hipo - que continua sendo quem
#   executa o Python, porque e dele o venv.
set -euo pipefail

APP=/home/hipo/app
ENVFILE="$APP/.env"
COMMIT="${1:-}"

for f in /tmp/importar_medseg_bloqueio.py /tmp/medseg_nao_prospectar_2026-09-09.json; do
    [ -f "$f" ] || { echo "FALTA $f. Rode o carga-medseg-bloqueio.ps1, que faz o scp." >&2; exit 1; }
done

sudo mkdir -p "$APP/scripts/dados"
sudo cp /tmp/importar_medseg_bloqueio.py            "$APP/scripts/importar_medseg_bloqueio.py"
sudo cp /tmp/medseg_nao_prospectar_2026-09-09.json  "$APP/scripts/dados/medseg_nao_prospectar_2026-09-09.json"
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
sudo -u hipo env \
    DATABASE_URL="$DB_URL" \
    PYTHONPATH="$APP" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m scripts.importar_medseg_bloqueio $COMMIT
