#!/usr/bin/env bash
#
# HIPO - poe a chave da LeadCNPJ no .env de producao, com seguranca.
#
# Rodar NA EC2, como ec2-user. O `-t` E OBRIGATORIO: o script pede a
# chave pelo terminal.
#
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       infra/corrigir-env-leadcnpj.sh ec2-user@63.179.88.212:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212 \
#       bash /tmp/corrigir-env-leadcnpj.sh
#
# POR QUE ELE PERGUNTA A CHAVE EM VEZ DE RECEBER COMO ARGUMENTO
#
# Chave em linha de comando vaza em tres lugares de uma vez: no histerico
# do shell da sua maquina, no `ps` de qualquer usuario do servidor
# enquanto o comando roda, e no seu terminal para quem estiver olhando.
# Digitada aqui, ela nao aparece em nenhum: `read -rs` nao ecoa, e o
# valor so existe dentro deste processo.
#
# O QUE ELE FAZ, NESTA ORDEM
#
#   1. backup do .env com carimbo de hora
#   2. tira o \r das linhas (fim de linha do Windows)
#   3. grava a chave -- sem nunca imprimi-la
#   4. descobre o nome da unidade systemd e reinicia
#   5. confere que subiu
#
# O .env e 600 e o dono NAO e necessariamente `hipo`: em producao e o
# ec2-user. Por isso tudo passa por `sudo`, e a leitura tenta a cascata.

set -uo pipefail

ENV_PATH=/home/hipo/app/.env

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
# `grep -c` sai com codigo 1 quando nao acha nada -- e ai o `|| echo 0`
# disparava JUNTO com o "0" que o grep ja tinha impresso, produzindo
# "0\n0" e um "integer expression expected" na comparacao seguinte. O
# `|| true` deixa o grep falar sozinho; o `head -1` garante um numero so.
ANTES=$(sudo grep -c $'\r' "$ENV_PATH" 2>/dev/null || true)
ANTES=$(printf '%s' "${ANTES:-0}" | head -1 | tr -cd '0-9')
ANTES=${ANTES:-0}
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

echo "Cole a chave da LeadCNPJ (ela NAO vai aparecer enquanto voce digita)."
echo "Enter vazio = nao mexer na chave, so manter a limpeza do CRLF."
printf '  chave: '
read -rs CHAVE < /dev/tty
echo

# Cola de painel web costuma trazer espaco, aspas ou quebra de linha
# junto. Limpar aqui e melhor que descobrir depois por um 401.
CHAVE=$(printf '%s' "$CHAVE" | tr -d '\r\n' \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
          -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

if [ -z "$CHAVE" ]; then
    echo "Chave nao alterada."
else
    case "$CHAVE" in
        *[![:print:]]*)
            echo "ERRO: a chave tem caractere nao imprimivel no meio."
            echo "Copie de novo do painel, sem selecionar a quebra de linha."
            desfazer
            exit 1 ;;
    esac
    echo "Chave recebida: ${CHAVE:0:4}... (${#CHAVE} caracteres)"

    # Gravar com `sed` embutiria a chave na linha de comando do sed, que
    # aparece no `ps`. Reescrever o arquivo por fora e mais seguro: a
    # chave so transita por variavel e pelo stdin do tee.
    NOVO=$(mktemp)
    chmod 600 "$NOVO"
    if sudo grep -qE '^LEADCNPJ_API_KEY=' "$ENV_PATH"; then
        sudo grep -vE '^LEADCNPJ_API_KEY=' "$ENV_PATH" > "$NOVO"
    else
        sudo cat "$ENV_PATH" > "$NOVO"
    fi
    printf 'LEADCNPJ_API_KEY=%s\n' "$CHAVE" >> "$NOVO"
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
echo " Agora, na tela: abra uma conta, aba Dados publicos, e aperte"
echo " ATUALIZAR DADOS PUBLICOS. Abrir a aba nao reconsulta -- em fonte"
echo " paga, abrir aba nao pode custar credito."
echo
echo " Deu certo se a linha da fonte disser 'leadcnpj+brasilapi' e o"
echo " No de funcionarios vier preenchido. Esse campo e o unico que a"
echo " BrasilAPI nao da, entao ele e a prova de que a fonte paga"
echo " respondeu de verdade."
echo
echo " Se falhar, rode o diagnostico -- agora com a chave no lugar o"
echo " teste vale:"
echo "   bash /tmp/diagnosticar-leadcnpj.sh"
linha
