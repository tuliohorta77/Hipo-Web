#!/usr/bin/env bash
#
# HIPO - instala o LibreOffice na EC2 para a proposta sair em PDF (050b).
#
# Sem ele: o PPTX da proposta funciona, mas nao ha PDF -- e o e-mail de
# proposta (entrega 050) nao tem o que anexar.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/instalar-libreoffice.sh
#
# A Amazon Linux 2023 NAO tem LibreOffice nos repositorios: a instalacao e
# pelo pacote oficial da Document Foundation (RPMs em tar.gz, ~300 MB de
# download, ~1,3 GB em /opt). A versao e a "stable" mais nova publicada --
# descoberta na hora, porque a Document Foundation tira as antigas da pasta
# stable/ (o 25.2.5 fixo da 009 teria dado 404).
#
# As fontes da marca (Codec Pro, Poppins) vem extraidas do proprio modelo
# por scp em /tmp/fontes-hipo: o LibreOffice NAO usa fonte embutida de pptx
# e, sem elas, o PDF sai com o texto estourando as caixas.
#
# IDEMPOTENTE: LibreOffice ja instalado pula o download; fontes sao
# recopiadas; o ensaio de conversao roda sempre.
#
# Codigos de saida: 0 ok | 1 falhou | 3 cancelado.

set -euo pipefail

APP=/home/hipo/app
MODELO="$APP/api/templates/proposta_modelo.pptx"
BASE_URL="https://download.documentfoundation.org/libreoffice/stable"

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
    # \r do Enter no ssh -t do Windows (incidente da 045).
    resposta="$(printf '%s' "$resposta" | tr -d '[:space:]')"
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

achar_binario() {
    command -v soffice 2>/dev/null \
        || ls -d /opt/libreoffice*/program/soffice 2>/dev/null | sort -V | tail -1 \
        || true
}

# -- 1. LibreOffice ------------------------------------------------------

BIN="$(achar_binario)"
if [ -n "$BIN" ]; then
    echo "== LibreOffice ja instalado: $BIN"
else
    echo "== LibreOffice nao encontrado"
    LIVRE=$(df -Pk /opt | awk 'NR==2 {print $4}')
    if [ "$LIVRE" -lt 2000000 ]; then
        echo "ERRO: menos de 2 GB livres em /opt ($((LIVRE / 1024)) MB). Libere espaco antes."
        exit 1
    fi
    echo "   espaco livre em /opt: $((LIVRE / 1024)) MB"

    VER=$(curl -fsSL --retry 3 "$BASE_URL/" \
        | grep -oE 'href="[0-9]+\.[0-9]+\.[0-9]+/"' \
        | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | sort -V | tail -1 || true)
    if [ -z "$VER" ]; then
        echo "ERRO: nao consegui descobrir a versao em $BASE_URL/ (sem internet na EC2?)."
        exit 1
    fi
    URL="$BASE_URL/$VER/rpm/x86_64/LibreOffice_${VER}_Linux_x86-64_rpm.tar.gz"
    echo "   versao stable mais nova: $VER"

    if ! perguntar "Baixar (~300 MB) e instalar o LibreOffice $VER em /opt?"; then
        echo "Cancelado."; exit 3
    fi

    TMP=$(mktemp -d /tmp/lo-instalacao.XXXXXX)
    trap 'rm -rf "$TMP"' EXIT
    echo "== baixando..."
    curl -fL --retry 3 -o "$TMP/lo.tar.gz" "$URL"
    tar xzf "$TMP/lo.tar.gz" -C "$TMP"
    RPMS=$(ls -d "$TMP"/*/RPMS | head -1)
    echo "== instalando $(ls "$RPMS"/*.rpm | wc -l) pacotes..."
    # O pacote oficial nao traz as libs de sistema que a AL2023 minima nao
    # tem; o dnf resolve as dependencias dos RPMs locais sozinho.
    sudo dnf install -y "$RPMS"/*.rpm
    BIN="$(achar_binario)"
    [ -n "$BIN" ] || { echo "ERRO: instalou mas nao achei o binario soffice."; exit 1; }
    echo "   binario: $BIN"
fi

# Bibliotecas que o soffice headless pede e a AL2023 minima nao traz.
# Sem elas a conversao morre com "error while loading shared libraries".
# Uma por vez: nome que nao existe no repositorio nao derruba as outras.
for pkg in fontconfig cairo libXinerama dbus-libs cups-libs nss libSM libICE; do
    sudo dnf install -y -q "$pkg" >/dev/null 2>&1 \
        || echo "   AVISO: $pkg nao instalou -- o ensaio abaixo diz se faz falta."
done

"$BIN" --version || true

# -- 2. Fontes da marca --------------------------------------------------

echo "== fontes da marca"
if ls /tmp/fontes-hipo/* >/dev/null 2>&1; then
    sudo mkdir -p /usr/share/fonts/hipo
    sudo cp /tmp/fontes-hipo/* /usr/share/fonts/hipo/
    sudo fc-cache -f >/dev/null
    echo "   $(ls /tmp/fontes-hipo | wc -l) arquivo(s) em /usr/share/fonts/hipo"
else
    echo "   AVISO: /tmp/fontes-hipo vazio -- o PDF sai com fonte substituta."
fi
echo "   faces Codec Pro/Poppins visiveis: $(fc-list | grep -ci -e 'codec pro' -e poppins || true)"

# -- 3. Ensaio: o mesmo comando que a API roda ---------------------------

echo "== ensaio de conversao, como $(whoami) (o User= do hipo-api)"
if [ ! -f "$MODELO" ]; then
    echo "ERRO: modelo nao encontrado em $MODELO"
    exit 1
fi
ENSAIO=$(mktemp -d /tmp/hipo-ensaio-pdf.XXXXXX)
cp "$MODELO" "$ENSAIO/proposta.pptx"
INICIO=$(date +%s)
HOME="$ENSAIO" timeout 180 "$BIN" --headless --norestore --invisible \
    --convert-to pdf --outdir "$ENSAIO" "$ENSAIO/proposta.pptx" >/dev/null 2>"$ENSAIO/erro.txt" || true
FIM=$(date +%s)
if [ -s "$ENSAIO/proposta.pdf" ]; then
    echo "   OK: PDF de $(du -k "$ENSAIO/proposta.pdf" | cut -f1) KB em $((FIM - INICIO)) s"
else
    echo "ERRO: o LibreOffice nao produziu o PDF."
    head -20 "$ENSAIO/erro.txt"
    rm -rf "$ENSAIO"
    exit 1
fi
rm -rf "$ENSAIO"

echo "== a API enxerga o binario?"
( cd "$APP/api" && PYTHONPATH="$APP/api" python3 -c \
    "from services import proposta_render as r; b = r.libreoffice_disponivel(); print('   ', b or 'NAO'); raise SystemExit(0 if b else 1)" )

echo
echo "Pronto. Nao precisa reiniciar a API: ela procura o LibreOffice a cada"
echo "pedido. Recarregue a tela (Ctrl+Shift+R) e o botao PDF / E-mail aparece."
