#!/usr/bin/env bash
# =====================================================================
# HIPO - Ensaia a unit DE VERDADE, com o endurecimento dela, sem enviar.
#
# O BURACO QUE ISTO FECHA
#
# O ensaio do instalador rodou por `systemd-run --uid=ec2-user`, passando
# so User, Group, EnvironmentFile e WorkingDirectory. A unit real tem MAIS
# coisa, e nada disso foi exercitado:
#
#     NoNewPrivileges=true
#     PrivateTmp=true
#     ProtectSystem=full      # /usr, /boot e /etc somente leitura
#     ProtectHome=read-only   # /home somente leitura -- inclusive o .env
#
# Ou seja: provamos que o CODIGO roda naquele usuario, nao que a UNIT roda.
# E o .env ja derrubou um ensaio hoje por um detalhe exatamente desse tipo.
# "Provavelmente funciona" foi a frase mais cara desta semana.
#
# COMO ELE NAO ENVIA E-MAIL
#
# Um drop-in temporario troca o ExecStart por `--so-imprime`, que nao grava,
# nao chama a IA e nao envia. O drop-in tambem poe `Restart=no`: sem isso, uma
# falha no ensaio agendaria uma retentativa em 300s -- que rodaria DEPOIS de o
# drop-in ser removido, ou seja, rodaria a coisa real e mandaria o e-mail.
#
# O drop-in e removido sempre, inclusive se o script morrer no meio (trap).
#
#   scp -i "$HOME/Downloads/chave-hipo.pem" \
#       infra/ensaiar-unit-real.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/ensaiar-unit-real.sh'
# =====================================================================
set -o pipefail

DIR=/etc/systemd/system/hipo-fechamento.service.d
CONF="$DIR/zz-ensaio.conf"
titulo() { printf '\n==== %s ====\n' "$1"; }

limpar() {
    titulo "4. Removendo o drop-in do ensaio"
    sudo systemctl stop hipo-fechamento.service 2>/dev/null
    sudo systemctl reset-failed hipo-fechamento.service 2>/dev/null
    sudo rm -f "$CONF"
    sudo rmdir "$DIR" 2>/dev/null
    sudo systemctl daemon-reload
    if [ -f "$CONF" ]; then
        echo "  !! O DROP-IN NAO SAIU: $CONF"
        echo "  !! Apague a mao antes das 03:12, ou o fechamento real nao roda:"
        echo "  !!   sudo rm -f $CONF && sudo systemctl daemon-reload"
        return
    fi
    echo "  [ok] removido"
    echo "  ExecStart que vai valer no disparo real:"
    systemctl show hipo-fechamento.service -p ExecStart --no-pager \
        | sed 's/^/    /' | cut -c1-160
}
trap limpar EXIT

titulo "1. Instalando o drop-in temporario"
sudo mkdir -p "$DIR" || exit 1
sudo tee "$CONF" >/dev/null <<'CONF'
# TEMPORARIO - criado por ensaiar-unit-real.sh, removido por ele no fim.
# Se este arquivo ainda existir, o fechamento diario esta rodando em modo
# ensaio e NAO envia e-mail nenhum. Apague-o.
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -m scripts.fechamento_diario --so-imprime
Restart=no
CONF
sudo systemctl daemon-reload || exit 1
echo "  [ok] ExecStart trocado por --so-imprime, Restart desligado"

titulo "2. Rodando a unit real"
MARCO=$(date '+%Y-%m-%d %H:%M:%S')
sudo systemctl start hipo-fechamento.service
CODIGO=$?
sleep 2
echo "  systemctl start -> codigo $CODIGO"
systemctl is-failed hipo-fechamento.service 2>&1 | sed 's/^/  estado: /'

titulo "3. O que a unit registrou no journal"
# E tambem a prova de que `journalctl -u hipo-fechamento` vai ter conteudo
# depois do disparo de verdade -- ate agora dava "-- No entries --" porque o
# ensaio anterior rodou como unit transitoria do systemd-run.
sudo journalctl -u hipo-fechamento.service --since "$MARCO" --no-pager \
    | sed 's/^/  /'

RESULTADO=$(systemctl show hipo-fechamento.service -p Result --value)
echo
echo "  Result=$RESULTADO   (esperado: success)"
if [ "$RESULTADO" != "success" ]; then
    echo
    echo "  A UNIT FALHOU com o endurecimento ligado, mesmo com o codigo"
    echo "  funcionando fora dela. Suspeitos, nesta ordem:"
    echo "    ProtectHome=read-only  -> algo tentou escrever em /home"
    echo "    ProtectSystem=full     -> algo tentou escrever em /usr ou /etc"
    echo "    PrivateTmp=true        -> algo contava com /tmp compartilhado"
    echo "  Desligue UM de cada vez no .service para achar qual."
fi
