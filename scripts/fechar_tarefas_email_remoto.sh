#!/usr/bin/env bash
# HIPO -- Baixa das tarefas de e-mail da carga do CRM Omie: metade que roda NA EC2.
#
#   bash /tmp/fechar_tarefas_email_remoto.sh            -> dry-run
#   bash /tmp/fechar_tarefas_email_remoto.sh --commit   -> grava
#
# Mesma mecanica dos outros scripts de operacao: root le o .env (que o usuario
# hipo nao consegue ler) e entrega a DATABASE_URL por ambiente ao processo do
# hipo, que e quem tem o venv.
set -euo pipefail

APP=/home/hipo/app
ENVFILE="$APP/.env"
COMMIT="${1:-}"
CSV=/tmp/tarefas_email_baixa.csv

[ -f /tmp/fechar_tarefas_email_crm_omie.py ] || {
    echo "FALTA /tmp/fechar_tarefas_email_crm_omie.py. Rode o fechar-tarefas-email.ps1, que faz o scp." >&2
    exit 1
}

sudo mkdir -p "$APP/scripts"
sudo cp /tmp/fechar_tarefas_email_crm_omie.py "$APP/scripts/fechar_tarefas_email_crm_omie.py"
sudo touch "$APP/scripts/__init__.py"
sudo chown -R hipo:hipo "$APP/scripts"

# CSV de rodada anterior pode ser de outro dono; o hipo precisa poder reescrever.
sudo rm -f "$CSV"

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
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m scripts.fechar_tarefas_email_crm_omie --csv "$CSV" $COMMIT

# O .ps1 puxa este arquivo por scp logo em seguida.
[ -f "$CSV" ] && sudo chmod 644 "$CSV" || true
