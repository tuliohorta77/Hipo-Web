#!/usr/bin/env bash
#
# HIPO - carga mensal da base de Dados Abertos do CNPJ (Prospeccao).
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t), FORA do horario
# comercial (a carga le dezenas de milhoes de linhas e usa ~300 MB de RAM
# com SP inteiro):
#
#   bash /tmp/carregar-base-receita.sh SP 2026-09 [URL_DO_ESPELHO]
#
# Sem URL: os ZIPs ja precisam estar em $PASTA (baixados a mao do site da
# Receita). Com URL: o script baixa um por vez e apaga depois de ler, para
# o pico de disco ficar em ~1 GB.
#
# Com espelho, a simulacao ja baixa os 10 ZIPs de Estabelecimentos (~2-3 GB)
# e os mantem para a carga reaproveitar; o resto e baixado e apagado um a um.
#
# Antes de gravar, roda --simular e pergunta: a simulacao diz quantas
# empresas vao entrar, que e o que decide o espaco no RDS.
#
# A troca da tabela e atomica: se a carga falhar no meio, a base anterior
# continua no ar, intacta.
#
# ASCII puro.

set -euo pipefail

UFS="${1:-}"
REFERENCIA="${2:-}"
ESPELHO="${3:-}"
PASTA=/home/hipo/receita
ENV_PATH=/home/hipo/app/.env

if [ -z "$UFS" ] || [ -z "$REFERENCIA" ]; then
    echo "Uso: bash $0 <UFS ex. SP ou SP,RJ> <referencia ex. 2026-09> [url-do-espelho]"
    exit 1
fi

tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }
perguntar() {
    local texto="$1" resposta
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then return 0; fi
    if ! tem_tty; then
        echo "ERRO: sem terminal para confirmar. Use 'ssh -t' ou HIPO_CONFIRMADO=1."
        exit 1
    fi
    read -r -p "$texto [s/N] " resposta < /dev/tty
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

DATABASE_URL=$(sudo cat "$ENV_PATH" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"
echo "Disco livre em /home: $(df -h /home | awk 'NR==2 {print $4}')"
echo

sudo mkdir -p "$PASTA"
sudo chown hipo:hipo "$PASTA"

ARGS=(--ufs "$UFS" --referencia "$REFERENCIA" --pasta "$PASTA")
if [ -n "$ESPELHO" ]; then
    ARGS+=(--baixar "$ESPELHO")
fi

rodar() {
    # -i: o mesmo ambiente de login do hipo que os outros scripts usam
    # (python e dependencias da API). O DATABASE_URL vai explicito porque o
    # .env e do ec2-user e o hipo nao consegue le-lo.
    sudo -iu hipo env DATABASE_URL="$DATABASE_URL" \
        bash -c "cd /home/hipo/app/api && python -m scripts.carregar_base_receita $(printf '%q ' "$@")"
}

echo "== simulacao (nao grava) =="
rodar "${ARGS[@]}" --simular
echo

if ! perguntar "Gravar essa base no banco acima?"; then
    echo "Cancelado. Os ZIPs ficam em $PASTA."
    exit 0
fi

echo
echo "== carga =="
if [ -n "$ESPELHO" ]; then
    rodar "${ARGS[@]}" --apagar-depois
else
    rodar "${ARGS[@]}"
fi

echo
psql "$DATABASE_URL" -At <<'SQL_FIM'
SELECT 'ultima carga: ' || referencia || ' | ' || status || ' | '
       || COALESCE(estabelecimentos::text, '-') || ' estabelecimentos | '
       || COALESCE(to_char(concluida_em, 'DD/MM HH24:MI'), '-')
  FROM receita_cargas ORDER BY id DESC LIMIT 1;
SELECT 'tamanho em disco: ' || pg_size_pretty(pg_total_relation_size('receita_estabelecimentos'));
SQL_FIM
