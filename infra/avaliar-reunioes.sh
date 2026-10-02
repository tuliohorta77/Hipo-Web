#!/usr/bin/env bash
#
# HIPO - backfill do scorecard (entrega 030).
#
# Avalia contra o Roteiro de Vendas as reunioes de oportunidade que JA
# tinham transcricao pronta antes do deploy. O timer so avalia as dos
# ultimos 3 dias; as antigas entram por aqui, por decisao explicita.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/avaliar-reunioes.sh 2026-09-01              # so lista (ensaio)
#   bash /tmp/avaliar-reunioes.sh 2026-09-01 --aplicar    # avalia
#   bash /tmp/avaliar-reunioes.sh 2026-09-01 --aplicar --refazer
#
# COMO RODA
#   O ensaio roda direto. O --aplicar sobe uma unit transitoria
#   (hipo-scorecard-backfill) e acompanha o journal: cada reuniao leva ate
#   dois minutos na IA, e uma queda do SSH no meio NAO interrompe o
#   trabalho. Para ver depois:
#     journalctl -u hipo-scorecard-backfill -o cat --no-pager
#
# IDEMPOTENTE: sem --refazer, so pega o que ainda nao tem avaliacao pronta.
# Avaliacao validada pela gestao nunca e refeita.
#
# ASCII puro.

set -uo pipefail

APP=/home/hipo/app
UNIT=hipo-scorecard-backfill

titulo() { printf '\n==== %s ====\n' "$1"; }
parar()  { printf '\n!! %s\n' "$1"; exit 1; }

DESDE="${1:-}"
case "$DESDE" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
    *) parar "uso: bash $0 AAAA-MM-DD [--aplicar] [--refazer] [--limite N]" ;;
esac
shift

APLICAR=0
EXTRA=()
while [ $# -gt 0 ]; do
    case "$1" in
        --aplicar) APLICAR=1 ;;
        --refazer) EXTRA+=("--refazer") ;;
        --limite)  shift; EXTRA+=("--limite" "${1:-}") ;;
        *) parar "argumento desconhecido: $1" ;;
    esac
    shift
done

D=$(sudo sed -n 's/^DATABASE_URL=//p' "$APP/.env")
[ -n "$D" ] || parar "DATABASE_URL vazia no $APP/.env."
echo "Banco: $(echo "$D" | sed 's/:[^:@]*@/:****@/')"

if ! sudo grep -qE '^ANTHROPIC_API_KEY=.+' "$APP/.env"; then
    parar "ANTHROPIC_API_KEY vazia no .env: sem IA nao ha avaliacao."
fi

[ -f "$APP/api/scripts/avaliar_reunioes.py" ] \
    || parar "o deploy 030 ainda nao chegou neste servidor (falta scripts/avaliar_reunioes.py)."

psql "$D" -Atc "select 1 from information_schema.tables where table_name = 'reuniao_avaliacoes'" \
    | grep -q 1 || parar "a migration 021 nao foi aplicada neste banco."

rodar() {  # rodar <args do script>
    sudo systemd-run \
        --uid=ec2-user --gid=ec2-user \
        --property=EnvironmentFile="$APP/.env" \
        --property=WorkingDirectory="$APP/api" \
        --setenv=PYTHONPATH="$APP/api" \
        --setenv=PYTHONUNBUFFERED=1 \
        "$@"
}

titulo "1. O que entra (ensaio, nada vai para a IA)"
rodar --wait --pipe --quiet \
    /usr/bin/python3 -m scripts.avaliar_reunioes --desde "$DESDE" "${EXTRA[@]}"
[ $? -eq 0 ] || parar "o ensaio falhou."

if [ $APLICAR -eq 0 ]; then
    echo
    echo "Ensaio concluido. Para avaliar de verdade:"
    echo "  bash /tmp/avaliar-reunioes.sh $DESDE --aplicar ${EXTRA[*]}"
    exit 0
fi

if systemctl is-active --quiet "$UNIT"; then
    parar "ja existe um backfill rodando ($UNIT). Acompanhe com: journalctl -fu $UNIT"
fi

titulo "2. Avaliando (unit $UNIT)"
sudo systemctl reset-failed "$UNIT" 2>/dev/null
rodar --unit="$UNIT" --quiet \
    /usr/bin/python3 -m scripts.avaliar_reunioes --desde "$DESDE" --aplicar "${EXTRA[@]}" \
    || parar "nao consegui subir a unit."

sleep 2
sudo journalctl -u "$UNIT" -o cat -f --no-pager &
SEGUIDOR=$!
while systemctl is-active --quiet "$UNIT"; do
    sleep 5
done
sleep 2
kill "$SEGUIDOR" 2>/dev/null
wait "$SEGUIDOR" 2>/dev/null

titulo "3. Como ficou"
psql "$D" -c "
select count(*) filter (where status = 'pronta')     as prontas,
       count(*) filter (where status = 'erro')       as com_erro,
       count(*) filter (where validada_em is not null) as validadas,
       round(avg(nota_total) filter (where status = 'pronta'), 1) as media
  from reuniao_avaliacoes;"

echo
echo "Backfill concluido. O quadro SCORECARD do Monitor ja mostra a media do mes."
