#!/usr/bin/env bash
#
# HIPO - instala o sentry-sdk no python da API (entrega 032).
#
# POR QUE ESTE SCRIPT EXISTE
#
# O deploy faz rsync e reinicia; NAO roda pip install. Pacote novo no
# requirements.txt so chega ao servidor a mao -- a mesma armadilha do
# python-pptx e das bibliotecas do Google. Sem o pacote a API sobe igual
# e o /health responde "sentry": false; com o pacote e sem SENTRY_DSN, a
# mesma coisa. Os dois passos sao necessarios.
#
# Rodar NA EC2, como ec2-user, UMA vez (idempotente: rodar de novo so
# confere):
#
#   scp -i $HOME/Downloads/chave-hipo.pem infra/instalar-sentry.sh ec2-user@35.156.111.168:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@35.156.111.168 bash /tmp/instalar-sentry.sh
#
# Depois, o DSN (o script abaixo pergunta o valor sem ecoar e reinicia):
#
#   scp -i $HOME/Downloads/chave-hipo.pem infra/por-chave-no-env.sh ec2-user@35.156.111.168:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@35.156.111.168 bash /tmp/por-chave-no-env.sh SENTRY_DSN
#
# ORDEM: o DSN so entra no .env DEPOIS do deploy da 032. O Settings e
# extra="forbid": variavel desconhecida no .env derruba a API no import
# (claude/env-ordem-de-deploy-e-extra-forbid.md).
#
# O QUE ELE FAZ
#   1. descobre o python de cada unidade (hipo-api e, se existir,
#      hipo-mos-api) pelo ExecStart -- o mesmo jeito do passo de
#      migrations do CI
#   2. instala o pacote nesse python, para todos os usuarios (sudo)
#   3. confere o import COMO O USUARIO DA UNIDADE -- e o que importa
#   4. reinicia e mostra o /health de cada instancia

set -uo pipefail

PACOTE='sentry-sdk[fastapi]==2.71.0'

python_da_unidade() {
    local unidade="$1" py
    py="$(systemctl show -p ExecStart --value "$unidade" 2>/dev/null \
          | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
    echo "${py:-/usr/bin/python3}"
}

usuario_da_unidade() {
    local u
    u="$(systemctl show -p User --value "$1" 2>/dev/null)"
    echo "${u:-root}"
}

existe_unidade() {
    # `systemctl cat` acha a unidade onde quer que ela esteja (/etc ou
    # /usr/lib); o arquivo em /etc/systemd/system e a rede de seguranca.
    systemctl cat "$1.service" >/dev/null 2>&1 \
        || sudo test -f "/etc/systemd/system/$1.service"
}

FALHOU=0
for par in "hipo-api:8001" "hipo-mos-api:8002"; do
    unidade="${par%%:*}"; porta="${par#*:}"
    if ! existe_unidade "$unidade"; then
        echo "-- $unidade nao instalada, pulando"
        continue
    fi

    PY="$(python_da_unidade "$unidade")"
    USR="$(usuario_da_unidade "$unidade")"
    echo
    echo "== $unidade  (python: $PY, usuario: $USR)"

    if sudo -u "$USR" "$PY" -c "import sentry_sdk" 2>/dev/null; then
        echo "   sentry-sdk ja instalado: $(sudo -u "$USR" "$PY" -c 'import sentry_sdk; print(sentry_sdk.VERSION)')"
    else
        echo "   instalando $PACOTE ..."
        if ! sudo "$PY" -m pip install --quiet "$PACOTE"; then
            echo "   ERRO: pip install falhou."
            FALHOU=1
            continue
        fi
        if ! sudo -u "$USR" "$PY" -c "import sentry_sdk" 2>/dev/null; then
            echo "   ERRO: instalou, mas o usuario $USR nao enxerga o pacote."
            echo "         Tente: sudo -u $USR $PY -m pip install --user '$PACOTE'"
            FALHOU=1
            continue
        fi
        echo "   ok: $(sudo -u "$USR" "$PY" -c 'import sentry_sdk; print(sentry_sdk.VERSION)')"
    fi

    sudo systemctl restart "$unidade"
    for i in $(seq 1 30); do
        if saida="$(curl -sf "http://localhost:$porta/health")"; then
            echo "   /health: $saida"
            break
        fi
        sleep 2
        if [ "$i" = 30 ]; then
            echo "   ERRO: $unidade nao respondeu em 60 s"
            sudo journalctl -u "$unidade" -n 30 --no-pager
            FALHOU=1
        fi
    done
done

# Timers que rodam scripts com o mesmo python (fechamento, e-mails,
# transcricoes) herdam a instalacao -- nao ha nada a fazer por eles.

echo
if [ "$FALHOU" = 0 ]; then
    echo "Pronto. \"sentry\": false no /health e o esperado ate o SENTRY_DSN entrar no .env."
else
    echo "Terminou COM ERRO -- ver acima."
fi
