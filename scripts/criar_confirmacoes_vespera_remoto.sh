#!/usr/bin/env bash
# HIPO - confirmacao da vespera das reunioes ja marcadas (entrega 048).
# Metade que roda NA EC2, como ec2-user.
#
#   bash /tmp/hipo-048/remoto.sh principal            -> so mostra
#   bash /tmp/hipo-048/remoto.sh principal --commit   -> grava
#   bash /tmp/hipo-048/remoto.sh mos [--commit]       -> base da MOS
#
# Usa o codigo JA DEPLOYADO da base escolhida (a mesma regra da tela) e o
# mesmo interpretador da hipo-api. O .py fica em /tmp/hipo-048, fora da
# pasta do app: o proximo deploy (rsync --delete) nao precisa saber dele.
# ASCII puro.
set -euo pipefail

BASE="${1:-}"
COMMIT="${2:-}"
case "$BASE" in
    principal) RAIZ=/home/hipo/app ;;
    mos)       RAIZ=/home/hipo/mos ;;
    *) echo "Uso: $0 principal|mos [--commit]" >&2; exit 1 ;;
esac
ENVFILE="$RAIZ/.env"
SCRIPT=/tmp/hipo-048/criar_confirmacoes_vespera.py

[ -f "$SCRIPT" ] || { echo "FALTA $SCRIPT" >&2; exit 1; }
if ! sudo test -f "$ENVFILE"; then
    echo "  $BASE: sem $ENVFILE -- instancia nao instalada, pulando."
    exit 0
fi
if [ ! -f "$RAIZ/api/services/confirmacao.py" ]; then
    echo "ERRO: $BASE ainda sem o codigo da 048 ($RAIZ/api/services/confirmacao.py)." >&2
    echo "      Espere o deploy do CI ficar verde e rode de novo." >&2
    exit 2
fi

DB_URL="$(sudo grep -m1 -E '^[[:space:]]*(export[[:space:]]+)?DATABASE_URL=' "$ENVFILE" \
          | tr -d '\r' | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//")"
[ -n "$DB_URL" ] || { echo "DATABASE_URL nao encontrada em $ENVFILE." >&2; exit 1; }

PY="$(systemctl show -p ExecStart --value hipo-api 2>/dev/null \
      | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
[ -x "${PY:-}" ] || PY="$(command -v python3)"

echo "== $BASE =="
cd "$RAIZ/api"
DATABASE_URL="$DB_URL" PYTHONPATH="$RAIZ/api" PYTHONDONTWRITEBYTECODE=1 \
    "$PY" "$SCRIPT" $COMMIT
