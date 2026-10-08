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
APP_DIR=/home/hipo/app/api

VARIAVEL="${1:-}"
if [ -z "$VARIAVEL" ]; then
    echo "ERRO: falta o nome da variavel."
    echo
    echo "Uso:  bash $0 NOME_DA_VARIAVEL"
    echo "      bash $0 NOME_DA_VARIAVEL --valor VALOR   (so para valor publico)"
    echo "Ex.:  bash $0 ECONODATA_API_KEY"
    echo "      bash $0 ENRIQUECIMENTO_FONTES --valor brasilapi,oportunidados"
    exit 1
fi

# ── --valor: sem prompt nenhum ────────────────────────────────────────
#
# Prompt interativo dentro de `ssh -t` chamado de um script do PowerShell
# embaralha na tela: a saida do ssh e a do PowerShell se intercalam e a
# pergunta aparece fora de ordem, as vezes depois do que vem DEPOIS dela.
# Duas vezes seguidas isso fez a ENRIQUECIMENTO_FONTES receber a coisa
# errada -- primeiro um token colado, depois um Enter vazio.
#
# Valor publico nao precisa de prompt. Passar por argumento e seguro aqui
# porque nao e segredo -- e a checagem abaixo garante que so valor publico
# pode vir por esse caminho.
VALOR_ARG=""
TEM_VALOR_ARG=0
if [ "${2:-}" = "--valor" ]; then
    if [ "$#" -lt 3 ]; then
        echo "ERRO: --valor sem valor depois."
        exit 1
    fi
    shift 2
    VALOR_ARG="$*"
    TEM_VALOR_ARG=1
fi
case "$VARIAVEL" in
    [A-Za-z_]*) ;;
    *) echo "ERRO: nome de variavel invalido: $VARIAVEL"; exit 1 ;;
esac
case "$VARIAVEL" in
    *[!A-Za-z0-9_]*) echo "ERRO: nome de variavel invalido: $VARIAVEL"; exit 1 ;;
esac

FONTES_PY="$APP_DIR/services/enriquecimento/fontes.py"

# ── SEGREDO OU NAO ────────────────────────────────────────────────────
#
# Nem toda variavel do .env e chave. URL, caminho, nome de header, lista
# de fontes -- nada disso e segredo, e esconder o que voce digita nesses
# casos nao protege nada: tira a unica chance de ver que a area de
# transferencia ainda tinha o token da variavel anterior.
#
# Foi exatamente isso em 23/09/2026. O token da Oportunidados foi colado
# no primeiro prompt e colado DE NOVO no segundo, onde devia ir
# "brasilapi,oportunidados". Como `read -rs` nao ecoa, nada na tela
# desmentiu. A ENRIQUECIMENTO_FONTES ficou com 64 caracteres de hex, o
# enriquecimento ficou sem nenhuma fonte valida, e o token foi parar no
# log de erro do script seguinte -- ou seja, vazou por ter sido gravado
# no lugar errado.
#
# Valor que nao e segredo ECOA, e conferido, e e confirmado antes de
# gravar.
case "$VARIAVEL" in
    *_KEY|*_TOKEN|*_SECRET|*_PASSWORD|*_SENHA|DATABASE_URL)
        SEGREDO=1 ;;
    ENRIQUECIMENTO_*|*_URL|*_CAMINHO|*_CAMINHO_*|*_HEADER|*_PREFIXO_HEADER|\
    *_BLOCOS|*_MODEL|*_ARQUIVO|*_BUCKET|*_REMETENTE|*_DESTINATARIOS|\
    AWS_REGION|ENVIRONMENT|*_FUSO|*_DIAS|*_ATIVA|*_ROUNDS|\
    CONTRATO_CONTRATADA_*|*_SANDBOX)
        SEGREDO=0 ;;
    # Na duvida, trata como segredo: esconder valor publico e so
    # incomodo, ecoar valor secreto e vazamento.
    *) SEGREDO=1 ;;
esac

# Segredo por argumento vaza em tres lugares de uma vez: historico do
# shell da sua maquina, `ps` de qualquer usuario do servidor, e a tela.
# Por isso --valor so existe para valor publico.
if [ "$TEM_VALOR_ARG" = "1" ] && [ "$SEGREDO" = "1" ]; then
    echo "ERRO: $VARIAVEL e segredo -- nao aceita --valor."
    echo
    echo "Valor em linha de comando aparece no historico do seu shell e"
    echo "no 'ps' de qualquer usuario da maquina enquanto o comando roda."
    echo "Rode sem --valor (com 'ssh -t') e cole no prompt."
    exit 1
fi

linha() { printf '%s\n' "------------------------------------------------------"; }

if [ ! -f "$ENV_PATH" ] && ! sudo test -f "$ENV_PATH"; then
    echo "ERRO: $ENV_PATH nao existe."
    exit 1
fi

# ── 0. O CODIGO EM PRODUCAO CONHECE ESSA VARIAVEL? ────────────────────
#
# Esta trava existe porque a falta dela derrubou a producao em 22/09/2026.
#
# O `Settings` do HIPO usa `extra="forbid"`: variavel no .env que o
# `config.py` nao declara faz o pydantic abortar NA PARTIDA. O app nao sobe
# degradado -- ele simplesmente nao sobe, e o nginx segue servindo o front
# com a API em 502.
#
# Ou seja: gravar a chave ANTES do push do codigo que a declara derruba o
# sistema no primeiro restart. A ordem certa e sempre:
#
#     1. push (o CI leva o config.py novo)
#     2. este script
#
# `--forcar` existe para o caso legitimo de variavel que nao vive no
# config.py (algo lido por outro processo, por exemplo).

FORCAR=""
if [ "${2:-}" = "--forcar" ]; then FORCAR=1; fi

if [ -z "$FORCAR" ] && ! sudo grep -qE "^[[:space:]]*${VARIAVEL}[[:space:]]*:" \
        "$APP_DIR/config.py" 2>/dev/null; then
    echo "ERRO: o config.py em producao NAO declara $VARIAVEL."
    echo
    echo "Gravar agora derrubaria a API no restart: o Settings usa"
    echo "extra=forbid, entao variavel desconhecida aborta a partida."
    echo
    echo "A ordem certa e:"
    echo "  1. git push   (o CI leva o config.py que declara $VARIAVEL)"
    echo "  2. este script"
    echo
    echo "Se a variavel nao vive no config.py de proposito:"
    echo "  bash $0 $VARIAVEL --forcar"
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
if [ "$TEM_VALOR_ARG" = "1" ]; then
    # Veio por argumento: nenhum prompt, nenhum /dev/tty, nada para
    # embaralhar na tela. O caminho existe so para valor publico -- a
    # checagem de segredo ja aconteceu la em cima.
    CHAVE="$VALOR_ARG"
    echo "Valor recebido por --valor (sem prompt)."
elif ! ( exec 3< /dev/tty ) 2>/dev/null; then
    echo "ERRO: sem terminal. Rode com 'ssh -t'."
    echo
    if [ "$SEGREDO" = "0" ]; then
        echo "Ou, para valor publico como este, passe direto:"
        echo "  bash $0 $VARIAVEL --valor SEU_VALOR"
    fi
    desfazer
    exit 1
elif [ "$SEGREDO" = "1" ]; then
    echo "Cole o valor de $VARIAVEL (NAO vai aparecer enquanto voce digita)."
    echo "Enter vazio = nao mexer no valor, so manter a limpeza do CRLF."
    printf '  valor: '
    read -rs CHAVE < /dev/tty
    echo
else
    echo "Digite o valor de $VARIAVEL -- ele APARECE na tela, de proposito."
    echo "Isto aqui nao e segredo, e ver o que voce colou e a unica defesa"
    echo "contra a area de transferencia ainda estar com a chave anterior."
    echo "Enter vazio = nao mexer no valor, so manter a limpeza do CRLF."
    printf '  valor: '
    read -r CHAVE < /dev/tty
fi

# Cola de painel web costuma trazer espaco, aspas ou quebra de linha
# junto. Limpar aqui e melhor que descobrir depois por um 401.
CHAVE=$(printf '%s' "$CHAVE" | tr -d '\r\n' \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
          -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

if [ -z "$CHAVE" ]; then
    # Enter vazio ja passou despercebido no meio de saida embaralhada de
    # PowerShell + ssh -t, e o valor errado ficou no .env mais uma rodada.
    # Entao isto grita, em vez de sussurrar uma linha.
    echo
    echo "######################################################"
    echo "#  NADA FOI DIGITADO -- $VARIAVEL NAO MUDOU"
    echo "#"
    echo "#  O valor que ja estava no .env continua la, seja ele"
    echo "#  qual for. Se voce esperava trocar, rode de novo."
    echo "######################################################"
    echo
else
    case "$CHAVE" in
        *[![:print:]]*)
            echo "ERRO: o valor tem caractere nao imprimivel no meio."
            echo "Copie de novo do painel, sem selecionar a quebra de linha."
            desfazer
            exit 1 ;;
    esac

    # ── o valor tem cara do que a variavel pede? ──────────────────────
    #
    # Blob longo sem pontuacao e chave, nunca lista de fontes nem URL. A
    # barreira aqui e barata e pega o erro que ja aconteceu: chave colada
    # no lugar de um valor publico.
    if [ "$SEGREDO" = "0" ] \
       && printf '%s' "$CHAVE" | grep -qE '^[A-Za-z0-9+/=_-]{32,}$'; then
        echo
        echo "ERRO: isso tem cara de chave/token, nao de valor de $VARIAVEL."
        echo "      ${#CHAVE} caracteres, sem ponto, barra nem virgula."
        echo
        echo "A area de transferencia ainda esta com a chave anterior?"
        echo "DIGITE o valor em vez de colar."
        desfazer
        exit 1
    fi

    # ── a lista de fontes existe no codigo que esta rodando? ──────────
    #
    # Fonte desconhecida e IGNORADA em silencio pelo fontes_habilitadas()
    # -- de proposito, para erro de digitacao nao derrubar a API. O preco
    # e que um .env errado nao reclama: o enriquecimento simplesmente
    # para de trazer dado. Entao quem reclama e aqui, na hora de gravar.
    if [ "$VARIAVEL" = "ENRIQUECIMENTO_FONTES" ]; then
        CONHECIDAS=$(sudo grep -oE '^[A-Z_]+ = "[a-z0-9_]+"' "$FONTES_PY" 2>/dev/null \
            | sed 's/.*"\(.*\)"/\1/' | sort -u)
        if [ -z "$CONHECIDAS" ]; then
            echo "AVISO: nao consegui ler as fontes registradas em"
            echo "       $FONTES_PY -- vou gravar sem conferir os nomes."
        else
            DESCONHECIDAS=""
            RESTO="$CHAVE"
            while [ -n "$RESTO" ]; do
                UMA=${RESTO%%,*}
                if [ "$UMA" = "$RESTO" ]; then RESTO=""; else RESTO=${RESTO#*,}; fi
                UMA=$(printf '%s' "$UMA" | tr -d '[:space:]' | tr 'A-Z' 'a-z')
                [ -n "$UMA" ] || continue
                printf '%s\n' "$CONHECIDAS" | grep -qx "$UMA" \
                    || DESCONHECIDAS="$DESCONHECIDAS $UMA"
            done
            if [ -n "$DESCONHECIDAS" ]; then
                echo
                echo "ERRO: o codigo em producao nao conhece:$DESCONHECIDAS"
                echo
                echo "Registradas hoje: $(printf '%s' "$CONHECIDAS" | tr '\n' ' ')"
                echo
                echo "Fonte desconhecida e ignorada em silencio. Gravar isso"
                echo "deixaria o enriquecimento sem fonte nenhuma, e nada"
                echo "na tela diria por que."
                desfazer
                exit 1
            fi
        fi
    fi

    if [ "$SEGREDO" = "1" ]; then
        echo "$VARIAVEL recebida: ${CHAVE:0:4}... (${#CHAVE} caracteres)"
    elif [ "$TEM_VALOR_ARG" = "1" ]; then
        # Sem pergunta: o valor esta no comando que voce mesmo escreveu.
        echo "Vai gravar:  $VARIAVEL=$CHAVE"
    else
        echo
        echo "Vai gravar:  $VARIAVEL=$CHAVE"
        printf '  Confere? [s/N] '
        read -r RESP < /dev/tty
        case "$RESP" in
            s|S) ;;
            *) echo "Nada gravado. O .env ficou como estava."; desfazer; exit 0 ;;
        esac
    fi

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
    # Garante quebra de linha no fim ANTES de acrescentar. Sem isto, um
    # .env que nao termina em \n faria a ultima variavel dele e a nova
    # virarem uma linha so -- corrompendo as duas em silencio.
    if [ -s "$NOVO" ] && [ -n "$(tail -c 1 "$NOVO")" ]; then
        printf '\n' >> "$NOVO"
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

# REINICIO COM REDE DE SEGURANCA.
#
# `is-active` logo apos o restart mente: um servico em crash-loop passa
# por "active" entre as tentativas. Por isso a conferencia olha o contador
# de reinicios, que so sobe quando o processo morre, e espera tempo
# suficiente para o loop aparecer.
#
# E se ficar de pe? Otimo. Se nao ficar, o backup volta SOZINHO. Um script
# que mexe no .env de producao as 22h tem que saber desfazer o proprio
# estrago sem depender de alguem estar acordado para notar.
reinicios() {
    systemctl show "$UNIDADE" -p NRestarts --value 2>/dev/null || echo 0
}

ANTES_R=$(reinicios)
echo "Reiniciando..."
sudo systemctl restart "$UNIDADE"

OK=""
for _ in 1 2 3 4 5 6 7 8; do
    sleep 2
    ESTADO=$(systemctl is-active "$UNIDADE" 2>/dev/null || true)
    if [ "$ESTADO" = "active" ] && [ "$(reinicios)" = "$ANTES_R" ]; then
        OK=1
    else
        OK=""
    fi
done

if [ -n "$OK" ]; then
    echo "OK: $UNIDADE de pe, sem reinicios extras."
    systemctl show "$UNIDADE" -p ActiveState -p SubState \
        -p ExecMainStartTimestamp 2>/dev/null | sed 's/^/  /'
else
    echo
    echo "!! O SERVICO NAO FICOU DE PE. Desfazendo sozinho."
    echo
    sudo journalctl -u "$UNIDADE" -n 12 --no-pager 2>/dev/null \
        | sed 's/^/  /'
    echo
    sudo cp "$BACKUP" "$ENV_PATH"
    sudo systemctl restart "$UNIDADE"
    sleep 4
    echo "Backup restaurado. Estado agora: $(systemctl is-active "$UNIDADE")"
    echo
    echo "O .env voltou ao que era. Leia o erro acima antes de tentar de"
    echo "novo -- a causa mais comum e a variavel nao existir no"
    echo "config.py que esta em producao."
    exit 1
fi

linha
echo " Agora reinicie ja foi feito acima. Para conferir que pegou:"
echo "   bash /tmp/sondar-econodata.sh      # se foi a chave da Econodata"
echo "   bash /tmp/diagnosticar-leadcnpj.sh # se foi a da LeadCNPJ"
echo
echo " E lembre: abrir a aba NAO reconsulta. So o botao ATUALIZAR DADOS"
echo " PUBLICOS ignora o cache -- em fonte paga, abrir aba nao pode"
echo " custar credito."
linha
