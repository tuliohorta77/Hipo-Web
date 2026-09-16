#!/usr/bin/env bash
# definir-destinatarios-relatorio.sh - grava RELATORIO_DESTINATARIOS no .env
# de producao, com backup, validacao e conferencia.
#
# Uso (na EC2, como ec2-user):
#   bash definir-destinatarios-relatorio.sh "tulio.horta@controllermedseg.com,wellington.souza@controllermedseg.com"
#   bash definir-destinatarios-relatorio.sh            # so mostra o valor atual
#
# Idempotente: apaga a linha existente antes de escrever.
#
# NAO precisa reiniciar o hipo-api. Quem le esta variavel e o
# hipo-fechamento.service (oneshot), que carrega o EnvironmentFile de novo a
# cada disparo do timer. A API nao usa a lista.
#
# ASCII puro, LF. Nao entra no deploy: sobe por scp.

set -euo pipefail

ENV_FILE=/home/hipo/app/.env
CHAVE=RELATORIO_DESTINATARIOS

atual() {
  sudo grep -E "^${CHAVE}=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r' || true
}

echo "Valor atual: $(atual)"

if [ $# -eq 0 ]; then
  exit 0
fi

NOVO="$(echo "$1" | tr -d ' \r')"
if [ -z "$NOVO" ]; then
  echo "ERRO: lista vazia."
  exit 2
fi

IFS=',' read -r -a LISTA <<< "$NOVO"
for e in "${LISTA[@]}"; do
  if ! [[ "$e" =~ ^[^@[:space:],\;]+@[^@[:space:],\;]+\.[A-Za-z]{2,}$ ]]; then
    echo "ERRO: e-mail invalido: '$e'"
    exit 2
  fi
done

# EnvironmentFile do systemd nao faz expansao de shell e trata aspas de
# forma especial: valor com $, # ou aspas quebra em silencio.
if [[ "$NOVO" == *'$'* || "$NOVO" == *'#'* || "$NOVO" == *'"'* || "$NOVO" == *"'"* ]]; then
  echo "ERRO: a lista nao pode conter \$, #, ou aspas."
  exit 2
fi

BACKUP="$ENV_FILE.bak-$(date +%Y%m%d-%H%M%S)"
sudo cp -p "$ENV_FILE" "$BACKUP"
echo "Backup: $BACKUP"

sudo sed -i "/^${CHAVE}=/d" "$ENV_FILE"
echo "${CHAVE}=${NOVO}" | sudo tee -a "$ENV_FILE" >/dev/null

GRAVADO="$(atual)"
if [ "$GRAVADO" != "$NOVO" ]; then
  echo "ERRO: conferencia falhou. Gravado: '$GRAVADO'. Restaure com:"
  echo "  sudo cp -p $BACKUP $ENV_FILE"
  exit 1
fi

echo "OK  ${CHAVE}=${GRAVADO}"
echo "    ${#LISTA[@]} destinatario(s). O proximo fechamento ja envia para esta lista."
