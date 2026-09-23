#!/usr/bin/env bash
#
# HIPO - zera o numero de funcionarios ESTIMADO, para a fonte nova repreencher.
#
# QUANDO USAR
#
# Depois de trocar a fonte de quadro de pessoal (Econodata -> Oportunidados)
# e o deploy estar verde. Roda uma vez. Rodar duas vezes nao faz nada na
# segunda.
#
# Rodar NA EC2, como ec2-user:
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       infra/zerar-funcionarios-estimados.sh ec2-user@hipogestao.com.br:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@hipogestao.com.br \
#       bash /tmp/zerar-funcionarios-estimados.sh
#
# O `-t` e obrigatorio: este script pergunta antes de gravar.
#
# POR QUE ISTO PRECISA EXISTIR
#
# Trocar a fonte NAO conserta o que ja esta gravado. O enriquecimento nao
# sobrescreve campo que JA TEM valor -- e a regra que protege o trabalho
# humano, e ela nao sabe distinguir "digitado por alguem" de "herdado de
# uma fonte que a gente cancelou". A consulta nova chega, ve
# `num_funcionarios = 3`, e devolve o numero certo como DIVERGENCIA em vez
# de corrigir. O 3 fica para sempre, conta por conta, ate alguem clicar.
#
# Nulo e o unico estado que o enriquecimento preenche sozinho. Dai o script.
#
# O QUE ELE NUNCA TOCA
#
# `num_funcionarios_origem = 'declarado'` -- o numero que o CLIENTE
# informou, que e o que precifica. O filtro esta no WHERE do SQL, nao numa
# condicao em Python: o banco recusa a linha errada antes de o script ter
# chance de errar.
#
# O CSV
#
# Regra do projeto para mudanca destrutiva: exportar antes. Aqui nao e
# migration, e UPDATE -- mas descarta dado do mesmo jeito, entao vale
# igual. O CSV sai em /tmp e o caminho aparece na tela; traga ele para a
# sua maquina antes de fechar a sessao.
#
# AS DUAS ARMADILHAS QUE ESTE SCRIPT EXISTE PARA EVITAR
#
#   1. `python` NAO EXISTE na Amazon Linux 2023 -- o binario e `python3`.
#
#   2. `sudo -iu hipo` NAO CARREGA O .env. Quem injeta as variaveis no
#      processo do app e o systemd, lendo o EnvironmentFile como root. Num
#      shell comum elas nao existem, e o pydantic aborta em "DATABASE_URL
#      Field required". Por isso a carga acontece AQUI, no ambiente deste
#      script -- sem passar credencial por linha de comando, que apareceria
#      no `ps` de qualquer usuario da maquina.

set -euo pipefail

APP_DIR=/home/hipo/app/api
ENV_PATH=/home/hipo/app/.env
CARIMBO=$(date +%Y%m%d-%H%M%S)
CSV_SIMULACAO=/tmp/funcionarios_estimados_${CARIMBO}_simulacao.csv
CSV_APAGADOS=/tmp/funcionarios_estimados_${CARIMBO}.csv

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
    for unidade in hipo-api hipo hipo-web; do
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
    systemctl show hipo-api -p ExecStart 2>/dev/null | sed 's/^/  /' \
        || echo "  (unidade 'hipo-api' nao encontrada)"
    echo
    echo "Nada foi alterado no banco."
    exit 1
fi

echo "Python: $PY  (achado via $ORIGEM)"

# ── 3. so zerar se ja houver de onde repreencher ───────────────────────
#
# Zerar antes da fonte nova estar no ar deixa o campo vazio e sem quem o
# preencha -- o usuario perde o numero errado E o numero certo. Duas
# barreiras: o codigo tem que estar deployado E a fonte tem que estar
# ligada no .env.

if [ ! -f "$APP_DIR/scripts/zerar_funcionarios_estimados.py" ]; then
    echo
    echo "ERRO: o script ainda nao esta em $APP_DIR."
    echo "Espere o CI terminar (rsync + restart) e rode de novo."
    exit 1
fi

if ! grep -q "normalizar_oportunidados" \
        "$APP_DIR/services/enriquecimento/persistencia.py" 2>/dev/null; then
    echo
    echo "ERRO: a Oportunidados ainda NAO esta em producao."
    echo
    echo "Zerar agora tiraria o numero errado sem colocar nada no lugar."
    echo "Faca o push, espere o CI ficar verde, e rode depois."
    exit 1
fi

FONTES="${ENRIQUECIMENTO_FONTES:-}"
case ",$FONTES," in
    *,oportunidados,*) ;;
    *)
        echo
        echo "ERRO: ENRIQUECIMENTO_FONTES nao inclui 'oportunidados'."
        echo "  valor atual: '${FONTES:-(vazio)}'"
        echo
        echo "Sem a fonte ligada, os campos zerados ficam vazios para"
        echo "sempre. Ajuste o .env primeiro:"
        echo "  bash /tmp/por-chave-no-env.sh ENRIQUECIMENTO_FONTES"
        exit 1
        ;;
esac

if [ -z "${OPORTUNIDADOS_API_TOKEN:-}" ]; then
    echo
    echo "ERRO: OPORTUNIDADOS_API_TOKEN esta vazio no .env."
    echo "A fonte esta listada mas nao responde -- os campos zerados"
    echo "ficariam vazios. Ponha a chave primeiro:"
    echo "  bash /tmp/por-chave-no-env.sh OPORTUNIDADOS_API_TOKEN"
    exit 1
fi

echo "Fontes: $FONTES"

# `-m` poe o diretorio de trabalho no sys.path, entao o cd nao e decorativo:
# e o que faz `from config import settings` encontrar o config.py do app.
cd "$APP_DIR"
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"

# Sem .pyc: este processo roda como ec2-user, e os __pycache__ que ele
# deixaria ficariam com dono errado dentro da pasta do app.
export PYTHONDONTWRITEBYTECODE=1

# ── 4. confirmar sem depender do stdin ────────────────────────────────
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
"$PY" -m scripts.zerar_funcionarios_estimados --simular --detalhar \
      --csv "$CSV_SIMULACAO"

echo
if perguntar "Zerar esses estimados para valer?"; then
    echo
    echo "== gravando =="
    "$PY" -m scripts.zerar_funcionarios_estimados --csv "$CSV_APAGADOS"
    echo
    echo "============================================================"
    echo " Guarde o CSV antes de fechar a sessao -- /tmp some no reboot:"
    echo
    echo "   scp -i \$HOME/Downloads/chave-hipo.pem \\"
    echo "       ec2-user@hipogestao.com.br:$CSV_APAGADOS ."
    echo "============================================================"
else
    echo "Nada foi gravado. O banco ficou como estava."
    echo "O CSV da simulacao continua em $CSV_SIMULACAO."
fi
