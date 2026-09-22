#!/usr/bin/env bash
#
# HIPO - limpa os valores gravados como texto de dicionario.
#
# QUANDO USAR
#
# A tela mostra coisas como `{'codigo': '02', 'descricao': 'Ativa', '` em
# Porte, Situacao cadastral, Qualificacao do socio ou Atividade do CNAE.
#
# Rodar NA EC2, como ec2-user:
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       infra/limpar-dicionarios.sh ec2-user@63.179.88.212:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212 \
#       bash /tmp/limpar-dicionarios.sh
#
# O `-t` e obrigatorio: este script pergunta antes de gravar.
#
# POR QUE "ATUALIZAR DADOS PUBLICOS" NAO RESOLVE SOZINHO
#
# O enriquecimento nao sobrescreve campo que JA TEM valor -- e a regra que
# protege o trabalho humano, e ela nao sabe distinguir "digitado por
# alguem" de "lixo gravado por um bug". A consulta nova chega, ve o campo
# preenchido, e devolve a diferenca como DIVERGENCIA em vez de corrigir.
#
# O QUE ELE FAZ
#
#   1. descobre qual interpretador Python roda o app;
#   2. carrega o .env de producao no proprio ambiente;
#   3. roda `scripts.limpar_dicionarios_gravados --simular`;
#   4. pergunta, e so entao roda para valer.
#
# Descricao completa no texto vira o texto limpo; descricao cortada vira
# NULL, porque campo vazio e o unico que o enriquecimento preenche. Rodar
# duas vezes nao faz nada na segunda.
#
# AS DUAS ARMADILHAS QUE ESTE SCRIPT EXISTE PARA EVITAR
#
#   1. `python` NAO EXISTE na Amazon Linux 2023 -- o binario e `python3`.
#      Um `sudo -iu hipo bash -lc "python ..."` responde
#      "command not found".
#
#   2. `sudo -iu hipo` NAO CARREGA O .env. Quem injeta as variaveis no
#      processo do app e o systemd, lendo o EnvironmentFile como root. Num
#      shell comum elas simplesmente nao existem, e o pydantic aborta em
#      "DATABASE_URL Field required". Por isso a carga acontece AQUI, no
#      ambiente deste script, com o .env lido e exportado -- sem passar as
#      credenciais por linha de comando, que apareceria no `ps` de
#      qualquer usuario da maquina.

set -euo pipefail

APP_DIR=/home/hipo/app/api
ENV_PATH=/home/hipo/app/.env

# ── 1. ler o .env ─────────────────────────────────────────────────────
#
# O arquivo e 600 e o dono NAO e necessariamente o usuario `hipo`: em
# producao ele e do ec2-user. A cascata cobre os tres estados possiveis em
# vez de apostar num deles.
ler_env() {
    sudo cat "$ENV_PATH" 2>/dev/null && return 0
    sudo -iu hipo cat "$ENV_PATH" 2>/dev/null && return 0
    cat "$ENV_PATH" 2>/dev/null && return 0
    return 1
}

if ! CONTEUDO_ENV=$(ler_env); then
    echo "ERRO: nao consegui ler $ENV_PATH de jeito nenhum."
    echo
    sudo ls -l "$ENV_PATH" 2>/dev/null || ls -l "$ENV_PATH" 2>/dev/null \
        || echo "  (nem o ls funcionou -- o arquivo existe?)"
    echo "Voce esta como: $(whoami)"
    exit 1
fi

# Exporta linha a linha, sem `eval`: o conteudo do .env nunca vira comando.
# So passa o que tem cara de KEY=valor; comentario e linha solta ficam de
# fora. As aspas em volta do valor, quando existem, sao removidas -- e o
# que o systemd faz ao ler um EnvironmentFile.
while IFS= read -r linha; do
    case "$linha" in
        ''|'#'*) continue ;;
        [A-Za-z_]*=*) ;;
        *) continue ;;
    esac
    chave=${linha%%=*}
    valor=${linha#*=}
    case "$valor" in
        \"*\") valor=${valor#\"}; valor=${valor%\"} ;;
        \'*\') valor=${valor#\'}; valor=${valor%\'} ;;
    esac
    export "$chave=$valor"
done <<EOF
$CONTEUDO_ENV
EOF

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERRO: o $ENV_PATH foi lido, mas nao tem linha DATABASE_URL=."
    exit 1
fi

# Mascara a senha ANTES de qualquer coisa ir para a tela. Confira o host: e
# a unica barreira contra rodar no banco errado.
echo "Banco : $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

# ── 2. achar o Python certo ───────────────────────────────────────────
#
# Do mais confiavel para o mais generico, e o candidato so e aceito se
# importar asyncpg: se o app estiver num virtualenv, o python3 do sistema
# nao tem as dependencias e falharia la na frente com mensagem pior.

candidato_do_systemd() {
    local unidade linha caminho irmao
    for unidade in hipo hipo-api hipo-web; do
        linha=$(systemctl show "$unidade" -p ExecStart 2>/dev/null | head -1) || continue
        [ -n "$linha" ] || continue
        caminho=$(printf '%s\n' "$linha" | sed -n 's/.*path=\([^ ;]*\).*/\1/p')
        case "$caminho" in
            */python*) [ -x "$caminho" ] && { printf '%s\n' "$caminho"; return 0; } ;;
            */bin/*)
                # uvicorn/gunicorn moram no mesmo bin/ do python do venv.
                irmao="${caminho%/*}/python"
                [ -x "$irmao" ] && { printf '%s\n' "$irmao"; return 0; }
                ;;
        esac
    done
    return 1
}

serve() { "$1" -c 'import asyncpg' >/dev/null 2>&1; }

PY=""
ORIGEM=""
if c=$(candidato_do_systemd) && serve "$c"; then PY="$c"; ORIGEM="systemd"; fi

if [ -z "$PY" ]; then
    for c in /home/hipo/app/.venv/bin/python /home/hipo/app/venv/bin/python \
             /home/hipo/.venv/bin/python /home/hipo/venv/bin/python; do
        if [ -x "$c" ] && serve "$c"; then PY="$c"; ORIGEM="venv"; break; fi
    done
fi

if [ -z "$PY" ]; then
    for nome in python3.11 python3 python; do
        c=$(command -v "$nome" 2>/dev/null) || continue
        if serve "$c"; then PY="$c"; ORIGEM="sistema"; break; fi
    done
fi

if [ -z "$PY" ]; then
    echo "ERRO: nao achei um Python que consiga importar asyncpg."
    echo
    echo "O que o systemd executa:"
    systemctl show hipo -p ExecStart 2>/dev/null | sed 's/^/  /' \
        || echo "  (unidade 'hipo' nao encontrada)"
    echo
    echo "A migration 015 JA ESTA APLICADA -- nada a desfazer."
    exit 1
fi

echo "Python: $PY  (achado via $ORIGEM)"

# A limpeza so faz sentido DEPOIS que o desembrulho esta no ar: sem ele,
# a proxima consulta grava o dicionario de novo e o trabalho se desfaz.
if ! grep -q "def desembrulhar" \
        "$APP_DIR/services/enriquecimento/modelo.py" 2>/dev/null; then
    echo
    echo "ERRO: o conserto do desembrulho ainda NAO esta em producao."
    echo
    echo "Limpar agora seria trabalho perdido: a proxima consulta gravaria"
    echo "o dicionario de novo. Faca o push, espere o CI ficar verde, e"
    echo "rode este script depois."
    exit 1
fi

if [ ! -f "$APP_DIR/scripts/limpar_dicionarios_gravados.py" ]; then
    echo
    echo "ERRO: o script ainda nao esta em $APP_DIR."
    echo "Espere o CI terminar (rsync + restart) e rode de novo."
    exit 1
fi

if [ ! -r "$APP_DIR/scripts/limpar_dicionarios_gravados.py" ]; then
    echo
    echo "ERRO: nao consigo LER $APP_DIR como $(whoami)."
    sudo ls -ld "$APP_DIR" 2>/dev/null | sed 's/^/  /'
    exit 1
fi

# `-m` poe o diretorio de trabalho no sys.path, entao o cd nao e decorativo:
# e o que faz `from config import settings` encontrar o config.py do app.
cd "$APP_DIR"
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"

# Sem .pyc: este processo roda como ec2-user, e os __pycache__ que ele
# deixaria ficariam com dono errado dentro da pasta do app.
export PYTHONDONTWRITEBYTECODE=1

# ── 3. confirmar sem depender do stdin ────────────────────────────────
#
# Se este script chegar por `base64 -d | bash`, o stdin do bash E o proprio
# script -- um `read` comum falha na hora e o `set -e` mata tudo em
# silencio. /dev/tty e o terminal de verdade. O teste e ABRIR o /dev/tty
# num subshell: o arquivo existe em qualquer sessao, mas abrir so funciona
# quando ha terminal controlador.
perguntar() {
    local texto="$1" resposta
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then
        echo "  ($texto -> sim, por HIPO_CONFIRMADO=1)"
        return 0
    fi
    if ! ( exec 3< /dev/tty ) 2>/dev/null; then
        echo "ERRO: sem terminal para confirmar (rodando sem tty)."
        echo "Use 'ssh -t', ou rode com HIPO_CONFIRMADO=1."
        exit 1
    fi
    read -r -p "$texto [s/N] " resposta < /dev/tty
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

echo
echo "== simulando (nada sera gravado) =="
echo
"$PY" -m scripts.limpar_dicionarios_gravados --simular --detalhar

echo
if perguntar "Gravar essa limpeza para valer?"; then
    echo
    echo "== gravando =="
    "$PY" -m scripts.limpar_dicionarios_gravados
    echo
    echo "============================================================"
    echo " Limpeza concluida."
    echo
    echo " Os campos que ficaram NULOS voltam sozinhos na proxima"
    echo " consulta daquela conta: campo vazio e o unico que o"
    echo " enriquecimento preenche."
    echo "============================================================"
else
    echo "Nada foi gravado. O banco ficou como estava."
fi
