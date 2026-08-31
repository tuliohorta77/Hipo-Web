#!/usr/bin/env bash
# =====================================================================
# HIPO - Envia DE VERDADE o fechamento de um dia ja calculado.
#
# Este e o unico script da familia que MANDA E-MAIL. Sem --confirmar ele
# apenas mostra o que aconteceria.
#
# O QUE ELE FAZ ALEM DE ENVIAR
#
# Regenera a narrativa. O dia 28/08 foi narrado as 15:53 de 31/08, ANTES de
# a INSTRUCAO ganhar as regras contra alegacao de tendencia e de causa. Ao
# reprocessar, o texto sai do ia.py que estiver em producao -- por isso o
# bloco 1 confere se o deploy do ia.py chegou. Enviar com o prompt velho
# desperdicaria a unica estreia que este relatorio tem.
#
# IDEMPOTENCIA: `enviado_em` preenchido bloqueia o envio. Depois desta
# rodada, repetir exige --forcar-email. E de proposito: cron que reexecuta
# por falha transitoria nao pode virar quatro copias na caixa.
#
#   scp -i "$HOME/Downloads/chave-hipo.pem" \
#       infra/enviar-fechamento.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/enviar-fechamento.sh 2026-08-28'
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/enviar-fechamento.sh 2026-08-28 --confirmar'
# =====================================================================
set -o pipefail

DIA="${1:-}"
CONFIRMAR=0
[ "$2" = "--confirmar" ] && CONFIRMAR=1

titulo() { printf '\n==== %s ====\n' "$1"; }
parar()  { printf '\n!! %s\n' "$1"; exit 1; }

case "$DIA" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
    *) parar "uso: bash $0 AAAA-MM-DD [--confirmar]" ;;
esac

APP=/home/hipo/app
D=$(sudo sed -n 's/^DATABASE_URL=//p' "$APP/.env")
[ -n "$D" ] || parar "DATABASE_URL vazia."

titulo "1. O ia.py em producao ja tem as regras novas?"
# Se o deploy nao chegou, a narrativa sai com o prompt velho -- aquele que
# escreveu "as tarefas atrasadas cresceram" sem ter serie historica.
FALTA=0
for regra in "MOVIMENTO SÓ COM COMPARATIVO" "NÃO EXPLIQUE A CAUSA" "nunca como \"ontem\""; do
    if grep -qF "$regra" "$APP/api/services/ia.py" 2>/dev/null; then
        echo "  [ok]    $regra"
    else
        echo "  [FALTA] $regra"
        FALTA=1
    fi
done
if [ $FALTA -eq 1 ]; then
    echo
    echo "  O deploy do ia.py NAO chegou neste servidor."
    echo "  Commite api/services/ia.py e rode infra/subir-telemetria.ps1 antes."
    [ $CONFIRMAR -eq 1 ] && parar "nada foi enviado."
fi

titulo "2. Estado atual de $DIA"
psql "$D" -c "select dia, gerado_em, enviado_em, narrativa_modelo,
                     length(narrativa) as tam, destinatarios, erro
                from relatorios_diarios where dia = '$DIA'::date;" \
    || parar "consulta falhou"

titulo "3. Para quem vai"
sudo sed -n 's/^RELATORIO_DESTINATARIOS=/  /p' "$APP/.env"
sudo sed -n 's/^SES_REMETENTE=/  remetente: /p' "$APP/.env"

JA=$(psql "$D" -Atc "select enviado_em is not null from relatorios_diarios
                      where dia = '$DIA'::date;")
if [ "$JA" = "t" ]; then
    echo
    echo "  ATENCAO: este dia JA foi enviado. O script vai pular o envio."
    echo "  Para repetir mesmo assim, acrescente --forcar-email no ExecStart."
fi

if [ $CONFIRMAR -eq 0 ]; then
    cat <<FIM

==== NADA FOI ENVIADO ====

Isto foi a previsao. Para enviar de verdade:

    bash /tmp/enviar-fechamento.sh $DIA --confirmar

FIM
    exit 0
fi

titulo "4. Enviando"
sudo systemd-run \
    --uid=ec2-user --gid=ec2-user \
    --property=EnvironmentFile="$APP/.env" \
    --property=WorkingDirectory="$APP/api" \
    --setenv=PYTHONPATH="$APP/api" \
    --setenv=PYTHONUNBUFFERED=1 \
    --wait --pipe --quiet \
    /usr/bin/python3 -m scripts.fechamento_diario --dia "$DIA"
CODIGO=$?
echo "  codigo de saida: $CODIGO"

titulo "5. Como ficou"
psql "$D" -x -c "select dia, enviado_em, narrativa_modelo, destinatarios, erro,
                        narrativa
                   from relatorios_diarios where dia = '$DIA'::date;"

if [ $CODIGO -ne 0 ]; then
    parar "o envio falhou. A coluna 'erro' acima diz o motivo."
fi

cat <<'FIM'

==== ENVIADO ====

Confira na caixa de entrada. E leia a narrativa acima procurando o que a
guarda numerica NAO pega:

  - alguma palavra de MOVIMENTO ("cresceu", "caiu", "vem acumulando")?
    So vale se o comparativo estiver preenchido e o numero estiver la.
  - alguma frase de CAUSA ("por isso", "explica por que")?
    O JSON diz o que aconteceu, nao por que.
  - a palavra "ontem" ou "hoje" para se referir ao dia do relatorio?

Se aparecer, o ajuste e na INSTRUCAO de services/ia.py, nao na guarda.

FIM
