#!/usr/bin/env bash
#
# HIPO - instala o hipo-contratos.timer (sincronizacao com a Autentique, 053).
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t), DEPOIS que o CI
# terminou o deploy da 053 (o script do timer e codigo novo):
#   bash /tmp/instalar-timer-contratos.sh
#
# As units vem por scp para /tmp junto com este script: o rsync do CI leva
# so api/ e web/dist/, nunca a pasta infra/.
#
# So a base principal. A instancia MOS nao tem AUTENTIQUE_API_TOKEN; la o
# envio de contrato fica desligado e nao ha o que sincronizar.
#
# Codigos de saida: 0 instalado | 1 pre-requisito faltando | 3 cancelado.

set -euo pipefail

APP=/home/hipo/app
SCRIPT="$APP/api/scripts/sincronizar_contratos.py"

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
    # No `ssh -t` do Windows o Enter chega como \r (incidente da 045).
    resposta="$(printf '%s' "$resposta" | tr -d '\r[:space:]')"
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

if [ ! -f "$SCRIPT" ]; then
    echo "ERRO: $SCRIPT ainda nao esta no servidor."
    echo "O CI nao terminou o deploy. Espere os 3 jobs ficarem verdes e rode de novo."
    exit 1
fi
for u in hipo-contratos.service hipo-contratos.timer; do
    if [ ! -f "/tmp/$u" ]; then
        echo "ERRO: /tmp/$u nao existe. Mande por scp junto com este script."
        exit 1
    fi
done

echo "== ensaio: a fila que a sincronizacao olharia agora (nao chama a Autentique) =="
( cd "$APP/api" && PYTHONPATH="$APP/api" python3 -m scripts.sincronizar_contratos --so-listar ) \
    || { echo "ERRO: o ensaio falhou -- nao instalo um timer que ia falhar a cada 30 min."; exit 1; }

if ! perguntar "Instalar e ligar o hipo-contratos.timer?"; then
    echo "Cancelado."; exit 3
fi
sudo install -o root -g root -m 644 /tmp/hipo-contratos.service \
    /tmp/hipo-contratos.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hipo-contratos.timer
echo
systemctl list-timers hipo-contratos.timer --no-pager
echo
echo "Rodando uma passada agora..."
sudo systemctl start hipo-contratos.service || true
journalctl -u hipo-contratos.service -n 15 --no-pager
