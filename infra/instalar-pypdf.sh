#!/usr/bin/env bash
#
# HIPO - instala o pypdf no python da API (entrega 052).
#
# POR QUE ESTE SCRIPT EXISTE
#
# O deploy faz rsync e reinicia; NAO roda pip install (mesma armadilha do
# python-pptx, das bibliotecas do Google e do sentry-sdk). O pypdf junta o
# PDF dos slides fixos da proposta (em cache) com o dos slides da proposta.
# Sem ele a API sobe igual e o PDF sai igual -- so mais devagar, todo pelo
# LibreOffice.
#
# Rodar NA EC2, como ec2-user (o deploy-052 faz isso sozinho). Idempotente:
# rodar de novo so confere.
#
#   scp -i $HOME/Downloads/chave-hipo.pem infra/instalar-pypdf.sh ec2-user@hipogestao.com.br:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@hipogestao.com.br bash /tmp/instalar-pypdf.sh
#
# O QUE ELE FAZ
#   1. descobre o python de cada unidade (hipo-api e, se existir,
#      hipo-mos-api) pelo ExecStart
#   2. instala o pacote nesse python (sudo)
#   3. confere o import COMO O USUARIO DA UNIDADE
#   4. reinicia e mostra o /health -- e, na subida, a API ja monta o PDF
#      dos slides fixos (journalctl: "cache do PDF da proposta")

set -uo pipefail

PACOTE='pypdf==6.19.0'

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

    if sudo -u "$USR" "$PY" -c "import pypdf" 2>/dev/null; then
        echo "   pypdf ja instalado: $(sudo -u "$USR" "$PY" -c 'import pypdf; print(pypdf.__version__)')"
    else
        echo "   instalando $PACOTE ..."
        if ! sudo "$PY" -m pip install --quiet "$PACOTE"; then
            echo "   ERRO: pip install falhou."
            FALHOU=1
            continue
        fi
        if ! sudo -u "$USR" "$PY" -c "import pypdf" 2>/dev/null; then
            echo "   ERRO: instalou, mas o usuario $USR nao enxerga o pacote."
            echo "         Tente: sudo -u $USR $PY -m pip install --user '$PACOTE'"
            FALHOU=1
            continue
        fi
        echo "   ok: $(sudo -u "$USR" "$PY" -c 'import pypdf; print(pypdf.__version__)')"
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
    echo "Pronto. Em ~15 s a API monta o PDF dos slides fixos:"
    echo "  sudo journalctl -u hipo-api -n 50 --no-pager | grep 'cache do PDF'"
else
    echo "Terminou COM ERRO -- ver acima."
fi
