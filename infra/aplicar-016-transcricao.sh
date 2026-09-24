#!/usr/bin/env bash
#
# HIPO - migration 016 (transcricao de reuniao) + timer do coletor.
#
# ORDEM OBRIGATORIA, porque tem migration:
#   1. testes verdes  ->  2. ESTE SCRIPT (parte 1)  ->  3. push  ->
#   4. ESTE SCRIPT de novo com --timer (parte 2)
# Invertido, o codigo novo sobe pedindo uma tabela que ainda nao existe, e a
# grade da agenda (que faz LEFT JOIN nela) estoura 500.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t):
#   bash /tmp/aplicar-016-transcricao.sh            # parte 1: migration
#   bash /tmp/aplicar-016-transcricao.sh --timer    # parte 2: instala o timer
#
# A migration e ADITIVA e IDEMPOTENTE: uma tabela nova e duas colunas
# nulaveis, nenhum DROP, nenhum DELETE. Rodar duas vezes nao faz nada na
# segunda. Por isso NAO exige o export previo em CSV.
#
# POR QUE O TIMER E UMA PARTE SEPARADA
#   A unit chama `python3 -m scripts.coletar_transcricoes`, que e codigo
#   novo: antes do rsync do CI ele nao existe no servidor, e o primeiro
#   disparo falharia. A parte 2 confere que o arquivo chegou antes de
#   instalar.

set -euo pipefail

MODO="${1:-migration}"
SQL=/tmp/016_reuniao_transcricao.sql
ENV_PATH=/home/hipo/app/.env
APP=/home/hipo/app

tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }

perguntar() {  # perguntar "texto" -> 0 se sim
    local texto="$1" resposta
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then
        echo "  ($texto -> sim, por HIPO_CONFIRMADO=1)"
        return 0
    fi
    if ! tem_tty; then
        echo "ERRO: sem terminal para confirmar. Use 'ssh -t' ou HIPO_CONFIRMADO=1."
        exit 1
    fi
    read -r -p "$texto [s/N] " resposta < /dev/tty
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

# -- Parte 2: o timer ----------------------------------------

if [ "$MODO" = "--timer" ]; then
    SCRIPT="$APP/api/scripts/coletar_transcricoes.py"
    if [ ! -f "$SCRIPT" ]; then
        echo "ERRO: $SCRIPT ainda nao esta no servidor."
        echo "O CI nao terminou o deploy. Espere os 3 jobs ficarem verdes e rode de novo."
        exit 1
    fi
    # As units vem por scp para /tmp, junto com este script: o rsync do CI
    # leva so api/ e web/dist/, NUNCA a pasta infra/.
    for u in hipo-transcricoes.service hipo-transcricoes.timer; do
        if [ ! -f "/tmp/$u" ]; then
            echo "ERRO: /tmp/$u nao existe. Mande por scp junto com este script."
            exit 1
        fi
    done

    echo "== bibliotecas do Google, como ec2-user (o User= da unit) =="
    if ! python3 -c "import google.auth.transport.requests, google.oauth2.service_account" 2>/dev/null; then
        echo "ERRO: google-auth nao importa como $(whoami)."
        echo "  sudo pip3 install google-api-python-client==2.149.0 google-auth==2.35.0"
        exit 1
    fi
    echo "  ok"

    echo "== ensaio: o que o coletor olharia agora (nao chama o Google) =="
    # Sem `source` do .env: o config.py le o arquivo sozinho (ec2-user e o
    # dono), e um `source` expandiria `$` dentro de valor -- o mesmo tropeco
    # que o EnvironmentFile do systemd evita por nao expandir nada.
    ( cd "$APP/api" && PYTHONPATH="$APP/api" python3 -m scripts.coletar_transcricoes --so-listar ) \
        || { echo "ERRO: o ensaio falhou -- nao instalo um timer que ia falhar a cada 15 min."; exit 1; }

    if ! perguntar "Instalar e ligar o hipo-transcricoes.timer?"; then
        echo "Cancelado."; exit 0
    fi
    sudo install -o root -g root -m 644 /tmp/hipo-transcricoes.service \
        /tmp/hipo-transcricoes.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now hipo-transcricoes.timer
    echo
    systemctl list-timers hipo-transcricoes.timer --no-pager
    echo
    echo "Rodando uma passada agora..."
    sudo systemctl start hipo-transcricoes.service || true
    journalctl -u hipo-transcricoes.service -n 15 --no-pager
    exit 0
fi

# -- Parte 1: a migration ----------------------------------------

if [ ! -f "$SQL" ]; then
    echo "ERRO: nao achei $SQL. Mande por scp antes."
    exit 1
fi

DATABASE_URL=$(sudo cat "$ENV_PATH" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)
if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERRO: $ENV_PATH sem DATABASE_URL."
    exit 1
fi

# Mascara a senha. Confira o HOST: e a unica barreira contra o banco errado.
echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"
echo

if ! perguntar "Aplicar a migration 016 nesse banco?"; then
    echo "Cancelado."; exit 0
fi

echo "== antes =="
psql "$DATABASE_URL" -At <<'EOF'
SELECT 'tabela reuniao_transcricoes existe: ' || count(*)
  FROM information_schema.tables WHERE table_name = 'reuniao_transcricoes';
SELECT 'reunioes com Meet: ' || count(*)
  FROM reunioes WHERE google_link ILIKE '%meet.google.com/%';
EOF

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$SQL"

echo
echo "== depois =="
psql "$DATABASE_URL" -At <<'EOF'
SELECT 'tabela reuniao_transcricoes existe: ' || count(*)
  FROM information_schema.tables WHERE table_name = 'reuniao_transcricoes';
SELECT 'colunas novas em reunioes: ' || count(*)
  FROM information_schema.columns
 WHERE table_name = 'reunioes'
   AND column_name IN ('transcricao_auto_em', 'transcricao_auto_erro');
EOF

echo
echo "Migration 016 aplicada. Agora o push; depois rode com --timer."
