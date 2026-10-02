#!/usr/bin/env bash
#
# HIPO - carga das trilhas iniciais da UC:
#   01 Boas-vindas a Controller, 02 Conceitos gerais de SST,
#   03 Produto e normas (a antiga trilha de NR, renomeada).
#
# Roda DEPOIS do deploy: o codigo da carga (api/scripts/semear_uc.py e
# uc_conteudo.py) chega ao servidor pelo CI.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/semear-uc.sh
# com os PDFs ja em /tmp/uc/ (o deploy-032 manda):
#   apresentacao-controller.pdf, nr-01.pdf, nr-04.pdf
#
# IDEMPOTENTE: ids fixos. Roda com --atualizar: textos e ordem das aulas
# do conteudo sao reescritos SEM subir versao (ninguem perde conclusao);
# prazo e cargo que a gestao mudou no estudio ficam como estao.
#
# Por que exporta variaveis em vez de deixar o config.py ler o .env: o .env
# de producao e do root (600) e quem roda aqui e o ec2-user. O
# pydantic-settings le o ambiente antes do arquivo. Sem `source`: valor
# com `$` seria expandido.
#
# ASCII puro.

set -euo pipefail

APP=/home/hipo/app
ENV_PATH=$APP/.env
PDFS=/tmp/uc

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
    echo "AVISO: S3_BUCKET_ANEXOS vazio -- as trilhas entram sem os PDFs."
fi

PY=""
tem_libs() { [ -x "$1" ] && "$1" -c 'import asyncpg, boto3' >/dev/null 2>&1; }
for c in "$APP/venv/bin/python" "$APP/.venv/bin/python" \
         "$APP/api/venv/bin/python" "$APP/api/.venv/bin/python" \
         "$(command -v python3.11 || true)" "$(command -v python3 || true)"; do
    if [ -n "$c" ] && tem_libs "$c"; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
    echo "ERRO: nenhum python com asyncpg e boto3 encontrado."
    exit 2
fi
echo "Python: $PY"

ARGS=(--atualizar)
if [ -d "$PDFS" ]; then
    ARGS+=(--pdfs "$PDFS")
else
    echo "AVISO: $PDFS nao existe -- as trilhas entram sem os PDFs."
fi

cd "$APP/api"
echo
echo "== ensaio =="
PYTHONPATH="$APP/api" "$PY" -m scripts.semear_uc --simular "${ARGS[@]}"
echo
echo "== carga (o script pergunta antes de gravar) =="
PYTHONPATH="$APP/api" "$PY" -m scripts.semear_uc "${ARGS[@]}" < /dev/tty
