#!/usr/bin/env bash
#
# HIPO - poe uma chave no .env de producao, com seguranca.
#
# O NOME da variavel vem por argumento (nome nao e segredo). O VALOR e
# digitado no terminal e nunca aparece.
#
# Rodar NA EC2, como ec2-user. O `-t` E OBRIGATORIO: o script pergunta.
#
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       infra/por-chave-no-env.sh ec2-user@63.179.88.212:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212 \
#       bash /tmp/por-chave-no-env.sh ECONODATA_API_KEY
#
# Tambem serve para ligar a fonte:
#   bash /tmp/por-chave-no-env.sh ENRIQUECIMENTO_FONTES
#   (ai o "valor" e brasilapi,econodata -- nao e segredo, mas o script
#    funciona igual)
#
# POR QUE ELE PERGUNTA A CHAVE EM VEZ DE RECEBER COMO ARGUMENTO
#
# Valor em linha de comando vaza em tres lugares de uma vez: no histerico
# do shell da sua maquina, no `ps` de qualquer usuario do servidor
# enquanto o comando roda, e no seu terminal para quem estiver olhando.
# Digitado aqui, nao aparece em nenhum: `read -rs` nao ecoa, e o valor so
# existe dentro deste processo. O NOME vai por argumento porque nome nao
# e segredo -- e assim um script so serve para qualquer chave.
#
# O QUE ELE FAZ, NESTA ORDEM
#
#   1. backup do .env com carimbo de hora
#   2. tira o \r das linhas (fim de linha do Windows)
#   3. grava o valor -- sem nunca imprimi-lo
#   4. descobre o nome da unidade systemd e reinicia
#   5. confere que subiu
#
# O .env e 600 e o dono NAO e necessariamente `hipo`: em producao e o
# ec2-user. Por isso tudo passa por `sudo`, e a leitura tenta a cascata.

set -uo pipefail

ENV_PATH=/home/hipo/app/.env

VARIAVEL="${1:-}"
if [ -z "$VARIAVEL" ]; then
    echo "ERRO: falta o nome da variavel."
    echo
    echo "Uso:  bash $0 NOME_DA_VARIAVEL"
    echo "Ex.:  bash $0 ECONODATA_API_KEY"
    exit 1
fi
case "$VARIAVEL" in
    [A-Za-z_]*) ;;
    *) echo "ERRO: nome de variavel invalido: $VARIAVEL"; exit 1 ;;
esac
case "$VARIAVEL" in
    *[!A-Za-z0-9_]*) echo "ERRO: nome de variavel invalido: $VARIAVEL"; exit 1 ;;
esac

linha() { printf '%s\n' "------------------------------------------------------"; }

if [ ! -f "$ENV_PATH" ] && ! sudo test -f "$ENV_PATH"; then
    echo "ERRO: $ENV_PATH nao existe."
    exit 1
fi

# ── 1. backup ─────────────────────────────────────────────────────────
CARIMBO=$(date +%Y%m%d-%H%M%S)
BACKUP="${ENV_PATH}.bak-${CARIMBO}"
sudo cp -p "$ENV_PATH" "$BACKUP" || { echo "ERRO: backup falhou."; exit 1; }
echo "Backup: $BACKUP"

desfazer() {
    echo
    echo "Para voltar atras:"
    echo "  sudo cp $BACKUP $ENV_PATH"
}

# ── 2. CRLF ───────────────────────────────────────────────────────────
ANTES=$(sudo grep -c $'\r' "$ENV_PATH" 2>/dev/null || echo 0)
if [ "$ANTES" -gt 0 ]; then
    sudo sed -i 's/\r$//' "$ENV_PATH"
    echo "CRLF: $ANTES linha(s) limpa(s)."
    echo "      (o \\r fica no fim de todo valor e quebra header HTTP --"
    echo "       era ele o unico conteudo da LEADCNPJ_API_KEY)"
else
    echo "CRLF: nenhum. O arquivo ja estava com fim de linha Unix."
fi

# ── 3. a chave ────────────────────────────────────────────────────────
linha
if ! ( exec 3< /dev/tty ) 2>/dev/null; then
    echo "ERRO: sem terminal. Rode com 'ssh -t'."
    desfazer
    exit 1
fi

echo "Cole o valor de $VARIAVEL (NAO vai aparecer enquanto voce digita)."
echo "Enter vazio = nao mexer no valor, so manter a limpeza do CRLF."
printf '  valor: '
read -rs CHAVE < /dev/tty
echo

# Cola de painel web costuma trazer espaco, aspas ou quebra de linha
# junto. Limpar aqui e melhor que descobrir depois por um 401.
CHAVE=$(printf '%s' "$CHAVE" | tr -d '\r\n' \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
          -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

if [ -z "$CHAVE" ]; then
    echo "$VARIAVEL nao alterada."
else
    case "$CHAVE" in
        *[![:print:]]*)
            echo "ERRO: o valor tem caractere nao imprimivel no meio."
            echo "Copie de novo do painel, sem selecionar a quebra de linha."
            desfazer
            exit 1 ;;
    esac
    echo "$VARIAVEL recebida: ${CHAVE:0:4}... (${#CHAVE} caracteres)"

    # Gravar com `sed` embutiria a chave na linha de comando do sed, que
    # aparece no `ps`. Reescrever o arquivo por fora e mais seguro: a
    # chave so transita por variavel e pelo stdin do tee.
    NOVO=$(mktemp)
    chmod 600 "$NOVO"
    if sudo grep -qE "^${VARIAVEL}=" "$ENV_PATH"; then
        sudo grep -vE "^${VARIAVEL}=" "$ENV_PATH" > "$NOVO"
    else
        sudo cat "$ENV_PATH" > "$NOVO"
    fi
    printf '%s=%s\n' "$VARIAVEL" "$CHAVE" >> "$NOVO"
    sudo cp "$NOVO" "$ENV_PATH"
    sudo chmod 600 "$ENV_PATH"
    # Dono e grupo vieram do backup feito com -p; restaura a partir dele
    # para nao trocar o dono do arquivo por descuido.
    sudo chown --reference="$BACKUP" "$ENV_PATH"
    rm -f "$NOVO"
    echo "Gravada."
fi

# ── 4. reiniciar ──────────────────────────────────────────────────────
linha
UNIDADE=$(systemctl list-units --type=service --all --no-legend --plain 2>/dev/null \
    | awk '{print $1}' | grep -i 'hipo' | head -1)

if [ -z "$UNIDADE" ]; then
    echo "Nao achei unidade systemd com 'hipo' no nome."
    echo "Quem esta servindo as portas:"
    sudo ss -ltnp 2>/dev/null | grep -E ':(443|80|8000)\b' | sed 's/^/  /'
    echo
    echo "O .env ja esta corrigido; falta so reiniciar quem le ele."
    desfazer
    exit 0
fi

echo "Unidade: $UNIDADE"
echo "Reiniciando..."
sudo systemctl restart "$UNIDADE"
sleep 3
systemctl show "$UNIDADE" -p ActiveState -p SubState -p ExecMainStartTimestamp \
    2>/dev/null | sed 's/^/  /'

linha
echo " Agora reinicie ja foi feito acima. Para conferir que pegou:"
echo "   bash /tmp/sondar-econodata.sh      # se foi a chave da Econodata"
echo "   bash /tmp/diagnosticar-leadcnpj.sh # se foi a da LeadCNPJ"
echo
echo " E lembre: abrir a aba NAO reconsulta. So o botao ATUALIZAR DADOS"
echo " PUBLICOS ignora o cache -- em fonte paga, abrir aba nao pode"
echo " custar credito."
linha
