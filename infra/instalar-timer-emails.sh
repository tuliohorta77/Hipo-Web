#!/usr/bin/env bash
#
# HIPO - instala o hipo-emails.timer (verificacao de resposta, entrega 050).
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t), DEPOIS que o CI
# terminou o deploy da 050 (o script do timer e codigo novo):
#   bash /tmp/instalar-timer-emails.sh
#
# As units vem por scp para /tmp junto com este script: o rsync do CI leva
# so api/ e web/dist/, nunca a pasta infra/.
#
# So a base principal. A instancia MOS nao tem GOOGLE_SA_ARQUIVO (outro
# Workspace); la o envio pelo Gmail fica desligado e nao ha o que verificar.
#
# Codigos de saida: 0 instalado | 1 pre-requisito faltando | 3 cancelado.
# Cancelar sai com 3, e NAO com 0: o deploy que chama este script precisa
# saber que nada foi instalado (licao do incidente da 045).

set -euo pipefail

APP=/home/hipo/app
SCRIPT="$APP/api/scripts/verificar_respostas_email.py"

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
    # No `ssh -t` do Windows o Enter chega como \r: sem limpar, "s\r" nao
    # e "s" e a resposta vira "nao" em silencio (incidente da 045).
    resposta="$(printf '%s' "$resposta" | tr -d '\r[:space:]')"
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

if [ ! -f "$SCRIPT" ]; then
    echo "ERRO: $SCRIPT ainda nao esta no servidor."
    echo "O CI nao terminou o deploy. Espere os 3 jobs ficarem verdes e rode de novo."
    exit 1
fi
for u in hipo-emails.service hipo-emails.timer; do
    if [ ! -f "/tmp/$u" ]; then
        echo "ERRO: /tmp/$u nao existe. Mande por scp junto com este script."
        exit 1
    fi
done

echo "== bibliotecas do Google, como $(whoami) (o User= da unit) =="
if ! python3 -c "import google.auth.transport.requests, google.oauth2.service_account" 2>/dev/null; then
    echo "ERRO: google-auth nao importa como $(whoami)."
    echo "  sudo pip3 install google-api-python-client==2.149.0 google-auth==2.35.0"
    exit 1
fi
echo "  ok"

echo "== ensaio: a fila que a verificacao olharia agora (nao chama o Google) =="
( cd "$APP/api" && PYTHONPATH="$APP/api" python3 -m scripts.verificar_respostas_email --so-listar ) \
    || { echo "ERRO: o ensaio falhou -- nao instalo um timer que ia falhar a cada 15 min."; exit 1; }

if ! perguntar "Instalar e ligar o hipo-emails.timer?"; then
    echo "Cancelado."; exit 3
fi
sudo install -o root -g root -m 644 /tmp/hipo-emails.service \
    /tmp/hipo-emails.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hipo-emails.timer
echo
systemctl list-timers hipo-emails.timer --no-pager
echo
echo "Rodando uma passada agora..."
sudo systemctl start hipo-emails.service || true
journalctl -u hipo-emails.service -n 15 --no-pager
