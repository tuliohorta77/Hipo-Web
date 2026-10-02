#!/usr/bin/env bash
#
# HIPO - carga da primeira trilha da UC: "Normas Regulamentadoras: NR-01 e
# NR-04" (pilar Tecnica), com os PDFs oficiais como material de apoio.
#
# Roda DEPOIS do deploy da UC-1: o script Python que carrega
# (api/scripts/semear_uc_nr.py) chega ao servidor pelo CI.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/semear-uc-nr.sh
# com os PDFs ja em /tmp/nr-01.pdf e /tmp/nr-04.pdf (o deploy-029 manda).
#
# IDEMPOTENTE: ids fixos. Rodar de novo nao duplica trilha, aula nem PDF.
# Trilha que ja existe nao e tocada (a gestao pode ter editado no estudio).
#
# Por que exporta variaveis em vez de deixar o config.py ler o .env: o .env
# de producao e do root (600) e quem roda aqui e o ec2-user. O
# pydantic-settings le o ambiente antes do arquivo, entao basta exportar o
# que o script usa. Sem `source`: valor com `$` seria expandido.
#
# ASCII puro.

set -euo pipefail

APP=/home/hipo/app
ENV_PATH=$APP/.env

ler() { sudo cat "$ENV_PATH" | grep -E "^$1=" | head -1 | cut -d= -f2- || true; }

export DATABASE_URL="$(ler DATABASE_URL)"
export JWT_SECRET="$(ler JWT_SECRET)"
export S3_BUCKET_ANEXOS="$(ler S3_BUCKET_ANEXOS)"
export AWS_REGION="$(ler AWS_REGION)"
[ -n "$AWS_REGION" ] || export AWS_REGION=eu-central-1

if [ -z "$DATABASE_URL" ] || [ -z "$JWT_SECRET" ]; then
    echo "ERRO: $ENV_PATH sem DATABASE_URL ou JWT_SECRET."
    exit 1
fi
if [ -z "$S3_BUCKET_ANEXOS" ]; then
    echo "AVISO: S3_BUCKET_ANEXOS vazio -- a trilha entra sem os PDFs."
fi

PY=""
tem_asyncpg() { [ -x "$1" ] && "$1" -c 'import asyncpg, boto3' >/dev/null 2>&1; }
for c in "$APP/venv/bin/python" "$APP/.venv/bin/python" \
         "$APP/api/venv/bin/python" "$APP/api/.venv/bin/python" \
         "$(command -v python3.11 || true)" "$(command -v python3 || true)"; do
    if [ -n "$c" ] && tem_asyncpg "$c"; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
    echo "ERRO: nenhum python com asyncpg e boto3 encontrado."
    exit 2
fi
echo "Python: $PY"

ARGS=()
[ -f /tmp/nr-01.pdf ] && ARGS+=(--pdf-nr01 /tmp/nr-01.pdf)
[ -f /tmp/nr-04.pdf ] && ARGS+=(--pdf-nr04 /tmp/nr-04.pdf)

cd "$APP/api"
echo
echo "== ensaio =="
PYTHONPATH="$APP/api" "$PY" -m scripts.semear_uc_nr --simular "${ARGS[@]}"
echo
echo "== carga (o script pergunta antes de gravar) =="
PYTHONPATH="$APP/api" "$PY" -m scripts.semear_uc_nr "${ARGS[@]}" < /dev/tty
