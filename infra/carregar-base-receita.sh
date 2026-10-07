#!/usr/bin/env bash
#
# HIPO - carga mensal da base de Dados Abertos do CNPJ (Prospeccao).
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#
#   bash /tmp/carregar-base-receita.sh SP 2026-09 [URL_DO_ESPELHO]
#
# COM ESPELHO: baixa um ZIP por vez e apaga depois de ler. O pico de disco
# fica no maior arquivo (~1,5 GB). Sem simulacao previa: ela teria que
# baixar os 10 de Estabelecimentos e manter, e a /home desta maquina nao
# comporta (2,9 GB livres em 02/10/2026).
#
# SEM ESPELHO: os ZIPs ja precisam estar em $PASTA. Roda --simular antes e
# pergunta.
#
# A carga roda como unit transitoria do systemd (hipo-carga-receita), como
# o avaliar-reunioes.sh: se o SSH cair no meio, ela continua. Para voltar a
# acompanhar:  sudo journalctl -fu hipo-carga-receita
#
# A troca da tabela e atomica: se a carga falhar no meio, a base anterior
# continua no ar, intacta.
#
# ASCII puro.

set -uo pipefail

UFS="${1:-}"
REFERENCIA="${2:-}"
ESPELHO="${3:-}"
APP=/home/hipo/app
ENV_PATH=$APP/.env
PASTA=/home/ec2-user/receita
UNIT=hipo-carga-receita

parar() { echo; echo "ERRO: $1"; exit 1; }

if [ -z "$UFS" ] || [ -z "$REFERENCIA" ]; then
    echo "Uso: bash $0 <UFS ex. SP ou SP,RJ> <referencia ex. 2026-09> [url-do-espelho]"
    exit 1
fi

tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }
perguntar() {
    local texto="$1" resposta
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then return 0; fi
    tem_tty || parar "sem terminal para confirmar. Use 'ssh -t' ou HIPO_CONFIRMADO=1."
    read -r -p "$texto [s/N] " resposta < /dev/tty
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

[ -f "$APP/api/scripts/carregar_base_receita.py" ] \
    || parar "o deploy 033 ainda nao chegou neste servidor."
grep -q encoding_pelo_bom "$APP/api/scripts/carregar_base_receita.py" \
    || parar "o servidor esta sem a correcao de encoding (BOM). Faca o push dela antes."

DATABASE_URL=$(sudo cat "$ENV_PATH" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
[ -n "$DATABASE_URL" ] || parar "$ENV_PATH sem DATABASE_URL."
psql "$DATABASE_URL" -Atc "select 1 from information_schema.tables where table_name = 'receita_cargas'" \
    | grep -q 1 || parar "a migration 022 nao foi aplicada neste banco."

# O mesmo python que os outros scripts do HIPO usam: o primeiro que tiver as
# bibliotecas da API. `python` sozinho nao existe nesta maquina.
PY=""
tem_libs() { [ -x "$1" ] && "$1" -c 'import asyncpg, httpx, pydantic_settings' >/dev/null 2>&1; }
for c in "$APP/venv/bin/python" "$APP/.venv/bin/python" \
         "$APP/api/venv/bin/python" "$APP/api/.venv/bin/python" \
         /usr/bin/python3.11 /usr/bin/python3; do
    if tem_libs "$c"; then PY="$c"; break; fi
done
[ -n "$PY" ] || parar "nenhum python com asyncpg, httpx e pydantic_settings encontrado."

mkdir -p "$PASTA"

echo "Banco      : $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"
echo "Python     : $PY"
echo "Pasta      : $PASTA"
echo "Disco livre: $(df -h "$PASTA" | awk 'NR==2 {print $4}')"
echo

rodar() {  # rodar <opcoes do systemd-run> -- <args do script>
    sudo systemd-run \
        --uid=ec2-user --gid=ec2-user \
        --property=EnvironmentFile="$ENV_PATH" \
        --property=WorkingDirectory="$APP/api" \
        --setenv=PYTHONPATH="$APP/api" \
        --setenv=PYTHONUNBUFFERED=1 \
        "$@"
}

ARGS=(--ufs "$UFS" --referencia "$REFERENCIA" --pasta "$PASTA")

if [ -n "$ESPELHO" ]; then
    ARGS+=(--baixar "$ESPELHO" --apagar-depois)
    echo "Espelho    : $ESPELHO"
    echo
    echo "Vai baixar ~5 GB, um arquivo por vez, e gravar em seguida (30 a 60 min)."
    echo "Sem simulacao previa: o disco desta maquina nao comporta os ZIPs juntos."
    perguntar "Gravar a base $REFERENCIA ($UFS) no banco acima?" || { echo "Cancelado."; exit 0; }
else
    ls "$PASTA"/*.zip >/dev/null 2>&1 || parar "nenhum ZIP em $PASTA e nenhum espelho informado."
    echo "== simulacao (nao grava) =="
    rodar --wait --pipe --quiet "$PY" -m scripts.carregar_base_receita "${ARGS[@]}" --simular \
        || parar "a simulacao falhou."
    echo
    perguntar "Gravar essa base no banco acima?" || { echo "Cancelado. Os ZIPs ficam em $PASTA."; exit 0; }
fi

if systemctl is-active --quiet "$UNIT"; then
    parar "ja existe uma carga rodando ($UNIT). Acompanhe com: sudo journalctl -fu $UNIT"
fi
sudo systemctl reset-failed "$UNIT" 2>/dev/null

echo
echo "== carga (unit $UNIT) =="
echo "Se o SSH cair, a carga continua. Para voltar a acompanhar:"
echo "  sudo journalctl -fu $UNIT"
echo
rodar --unit="$UNIT" --quiet "$PY" -m scripts.carregar_base_receita "${ARGS[@]}" \
    || parar "nao consegui subir a unit."

sleep 2
sudo journalctl -u "$UNIT" -o cat -f --no-pager &
SEGUE=$!
while systemctl is-active --quiet "$UNIT"; do sleep 5; done
sleep 2
kill "$SEGUE" 2>/dev/null

RESULTADO=$(systemctl show "$UNIT" -p Result --value 2>/dev/null)
echo
psql "$DATABASE_URL" -At <<'SQL_FIM'
SELECT 'ultima carga: ' || referencia || ' | ' || status || ' | '
       || COALESCE(estabelecimentos::text, '-') || ' estabelecimentos | '
       || COALESCE(to_char(concluida_em, 'DD/MM HH24:MI'), '-')
       || COALESCE(' | ' || observacao, '')
  FROM receita_cargas ORDER BY id DESC LIMIT 1;
SELECT 'tamanho em disco no RDS: ' || pg_size_pretty(pg_total_relation_size('receita_estabelecimentos'));
SQL_FIM

[ "$RESULTADO" = "success" ] || parar "a carga terminou com falha ($RESULTADO). Veja o log acima."
echo
echo "Base no ar. F5 na tela de Prospeccao."
