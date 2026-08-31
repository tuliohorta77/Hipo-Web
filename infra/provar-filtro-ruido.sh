#!/usr/bin/env bash
# =====================================================================
# HIPO - Prova, em producao, que o filtro de varredura esta valendo.
#
# SO LE o banco. As duas requisicoes que ele dispara sao inofensivas: uma
# 404 e uma 401, ambas sem token.
#
# POR QUE UM GRUPO DE CONTROLE
#
# "Nao apareceu nada na tabela" tem duas explicacoes, e elas pedem acoes
# opostas: o filtro funcionou, ou a telemetria parou de gravar. Por isso o
# script dispara DUAS requisicoes:
#
#   A) GET /nao-existe-<carimbo>  -> 404, anonima, SEM rota casada
#      E o caso do filtro. NAO pode aparecer.
#
#   B) GET /crm/contas            -> 401, anonima, COM rota casada
#      E sessao expirada, que o middleware deve capturar de proposito.
#      TEM que aparecer.
#
# So o par prova alguma coisa. A sozinha e ambigua.
#
# Bate direto no uvicorn (127.0.0.1:8001) e nao no nginx: o que esta sob
# teste e o middleware, e tirar o proxy do caminho tira uma variavel.
#
#   scp -i "$HOME/Downloads/chave-hipo.pem" \
#       infra/provar-filtro-ruido.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/provar-filtro-ruido.sh'
# =====================================================================
set -o pipefail

API=http://127.0.0.1:8001
CARIMBO=$(date +%s)
titulo() { printf '\n==== %s ====\n' "$1"; }
parar()  { printf '\n!! %s\n' "$1"; exit 1; }

D=$(sudo sed -n 's/^DATABASE_URL=//p' /home/hipo/app/.env)
[ -n "$D" ] || parar "DATABASE_URL vazia."

titulo "0. Estado antes"
ANTES_RUIDO=$(psql "$D" -Atc "select count(*) from uso_eventos
                               where usuario_id is null and rota = '<sem_rota>';")
ANTES_401=$(psql "$D" -Atc "select count(*) from uso_eventos
                             where usuario_id is null and rota = '/crm/contas';")
echo "  varredura ja gravada .......... $ANTES_RUIDO"
echo "  401 em /crm/contas ja gravados  $ANTES_401"

titulo "1. Disparando as duas requisicoes"
A=$(curl -s -o /dev/null -w '%{http_code}' "$API/nao-existe-$CARIMBO")
echo "  A) GET /nao-existe-$CARIMBO -> HTTP $A   (esperado 404)"
B=$(curl -s -o /dev/null -w '%{http_code}' "$API/crm/contas")
echo "  B) GET /crm/contas          -> HTTP $B   (esperado 401 ou 403)"

titulo "2. Esperando a descarga do buffer"
# INTERVALO_DESCARGA_S = 10.0 no middleware, e sao 4 workers do uvicorn --
# a requisicao pode ter caido em qualquer buffer. 25s cobre com folga.
for i in $(seq 5 5 25); do sleep 5; printf '  %ss...\n' "$i"; done

titulo "3. Veredito"
DEPOIS_RUIDO=$(psql "$D" -Atc "select count(*) from uso_eventos
                                where usuario_id is null and rota = '<sem_rota>';")
DEPOIS_401=$(psql "$D" -Atc "select count(*) from uso_eventos
                              where usuario_id is null and rota = '/crm/contas';")
NOVO_RUIDO=$((DEPOIS_RUIDO - ANTES_RUIDO))
NOVO_401=$((DEPOIS_401 - ANTES_401))

echo "  A) varredura gravada agora .... $NOVO_RUIDO   (esperado 0)"
echo "  B) 401 com rota gravado agora . $NOVO_401   (esperado 1 ou mais)"
echo

if [ "$NOVO_401" -lt 1 ]; then
    echo "  INCONCLUSIVO: o controle nao apareceu."
    echo "  A telemetria nao gravou NEM o evento que deveria gravar, entao o"
    echo "  zero do item A nao prova o filtro -- prova que nada esta chegando"
    echo "  ao banco. Investigar antes de confiar no relatorio:"
    echo "    sudo journalctl -u hipo-api --since '5 min ago' | grep -i telemetria"
    exit 2
fi

if [ "$NOVO_RUIDO" -ne 0 ]; then
    echo "  FILTRO NAO ESTA VALENDO. O evento de varredura foi gravado."
    echo "  O middleware em producao nao e o que foi testado -- conferir se o"
    echo "  deploy chegou:"
    echo "    grep -n 'eh_ruido_externo' /home/hipo/app/api/middleware/telemetria.py"
    exit 1
fi

echo "  FILTRO CONFIRMADO EM PRODUCAO."
echo "  A varredura foi descartada e a sessao expirada foi mantida -- que e"
echo "  exatamente a distincao que o filtro promete."
