#!/usr/bin/env bash
#
# HIPO - instala o hipo-ligacoes.timer e confere a AWS (entrega 056).
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t), DEPOIS que o CI
# terminou o deploy da 056 (o script do coletor e codigo novo):
#   bash /tmp/instalar-ligacoes.sh
#
# As units vem por scp para /tmp junto com este script: o rsync do CI leva
# so api/ e web/dist/, nunca a pasta infra/.
#
# O que confere antes de ligar o timer:
#   1. o coletor existe e o ensaio (--so-listar) roda;
#   2. a role da instancia alcanca o AWS Transcribe. Pergunta por um job
#      que nao existe: "nao encontrado" prova a permissao; "acesso negado"
#      quer dizer que a policy da 056 ainda nao foi colada na role.
#
# Codigos de saida: 0 instalado | 1 pre-requisito faltando | 3 cancelado.

set -euo pipefail

APP=/home/hipo/app
SCRIPT="$APP/api/scripts/coletar_ligacoes.py"

tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }

perguntar() {  # perguntar "texto" -> 0 se sim
    local texto="$1" resposta
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then
        echo "  ($texto -> sim, por HIPO_CONFIRMADO=1)"
        return 0
    fi
    if ! tem_tty; then
        echo "ERRO: sem terminal para confirmar. Use 'ssh -t' ou HIPO_CONFIRMADO=1."
        exit 1
    fi
    read -r -p "$texto [s/N] " resposta < /dev/tty
    resposta="$(printf '%s' "$resposta" | tr -d '\r[:space:]')"
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

if [ ! -f "$SCRIPT" ]; then
    echo "ERRO: $SCRIPT ainda nao esta no servidor."
    echo "O CI nao terminou o deploy. Espere os 3 jobs ficarem verdes e rode de novo."
    exit 1
fi
for u in hipo-ligacoes.service hipo-ligacoes.timer; do
    if [ ! -f "/tmp/$u" ]; then
        echo "ERRO: /tmp/$u nao existe. Mande por scp junto com este script."
        exit 1
    fi
done

echo "== AWS Transcribe pela role da instancia =="
REGIAO="$(sudo grep -E '^AWS_REGION=' "$APP/.env" | cut -d= -f2- | tr -d '"'"'"' ')"
REGIAO="${REGIAO:-eu-central-1}"
set +e
python3 - "$REGIAO" <<'PY'
import sys
import boto3
from botocore.exceptions import ClientError
c = boto3.client("transcribe", region_name=sys.argv[1])
try:
    c.get_transcription_job(TranscriptionJobName="hipo-sonda-permissao-056")
    print("  ok (job de sonda existe?!)")
except ClientError as e:
    code = e.response.get("Error", {}).get("Code", "")
    if code in ("NotFoundException", "BadRequestException"):
        print("  ok: a role alcanca o Transcribe")
        sys.exit(0)
    print(f"  FALHOU: {code}: {e}")
    sys.exit(2)
PY
SONDA=$?
set -e
if [ "$SONDA" -ne 0 ]; then
    echo
    echo "A role da EC2 ainda nao pode usar o Transcribe. No console da AWS:"
    echo "  IAM > Roles > (role da instancia) > Add permissions > Create inline policy > JSON"
    echo "  e cole o arquivo infra/policy-transcribe-ligacoes.json da entrega 056."
    echo "Depois rode este script de novo."
    exit 1
fi

echo "== bucket das gravacoes =="
if ! sudo grep -qE '^S3_BUCKET_ANEXOS=.+' "$APP/.env"; then
    echo "ERRO: S3_BUCKET_ANEXOS vazio no .env -- sem ele o gravador nao tem para onde mandar."
    exit 1
fi
echo "  ok"

echo "== ensaio: o que a passada olharia agora =="
( cd "$APP/api" && PYTHONPATH="$APP/api" python3 -m scripts.coletar_ligacoes --so-listar ) \
    || { echo "ERRO: o ensaio falhou -- nao instalo um timer que ia falhar a cada 2 min."; exit 1; }

if ! perguntar "Instalar e ligar o hipo-ligacoes.timer?"; then
    echo "Cancelado."; exit 3
fi
sudo install -o root -g root -m 644 /tmp/hipo-ligacoes.service \
    /tmp/hipo-ligacoes.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hipo-ligacoes.timer
echo
systemctl list-timers hipo-ligacoes.timer --no-pager
echo
echo "Rodando uma passada agora..."
sudo systemctl start hipo-ligacoes.service || true
journalctl -u hipo-ligacoes.service -n 15 --no-pager
