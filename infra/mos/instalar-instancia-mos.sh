#!/usr/bin/env bash
#
# HIPO - instancia MOS (entrega 046). Segunda base do HIPO na mesma EC2.
#
#   mos.hipogestao.com.br -> nginx -> 127.0.0.1:8002 (hipo-mos-api)
#                                     /home/hipo/mos/{api,.env,uploads}
#                                     banco hipo_mos no mesmo RDS (role hipo_mos)
#
# A base principal (hipogestao.com.br, 8001, /home/hipo/app, banco atual)
# NAO e alterada por nenhuma fase daqui: o script so LE o .env e o
# schema.sql dela.
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t), UMA FASE POR VEZ e
# nesta ordem:
#
#   bash /tmp/mos/instalar-instancia-mos.sh estado      # so le; roda quando quiser
#   bash /tmp/mos/instalar-instancia-mos.sh base        # pasta + banco + schema + .env
#   bash /tmp/mos/instalar-instancia-mos.sh app         # codigo + servico 8002 + front
#   bash /tmp/mos/instalar-instancia-mos.sh nginx       # server_name mos.hipogestao.com.br
#   bash /tmp/mos/instalar-instancia-mos.sh tls         # certbot (exige o DNS no ar)
#   bash /tmp/mos/instalar-instancia-mos.sh config      # clona a configuracao da MedSeg
#   bash /tmp/mos/instalar-instancia-mos.sh usuario     # primeiro(s) usuario(s)
#   bash /tmp/mos/instalar-instancia-mos.sh fechamento  # timer do e-mail diario
#
# Toda fase e IDEMPOTENTE: rodar de novo confere o que ja existe e so faz o
# que falta. Cancelar uma confirmacao sai com codigo 3 (nunca 0), para o
# deploy-046 nao confundir "cancelado" com "feito".
#
# ASCII puro.

set -euo pipefail

FASE="${1:-}"

APP_MED=/home/hipo/app
ENV_MED=$APP_MED/.env
MOS=/home/hipo/mos
ENV_MOS=$MOS/.env
WEB_MED=/var/www/hipo
WEB_MOS=/var/www/hipo-mos
DOMINIO=mos.hipogestao.com.br
DOMINIO_MED=hipogestao.com.br
PORTA=8002
UNIDADE=hipo-mos-api
BANCO=hipo_mos
ROLE=hipo_mos
SIGLA=MOS
DIR_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --------------------------------------------------------------------------
# utilitarios
# --------------------------------------------------------------------------

tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }

# Le uma linha do terminal. O `ssh -t` do Windows entrega o Enter como \r:
# sem limpar, "s\r" nunca e "s" (incidente do deploy-045).
ler() {  # ler "pergunta" [padrao] -> ecoa a resposta
    local texto="$1" padrao="${2:-}" r
    if ! tem_tty; then
        echo "ERRO: sem terminal. Use 'ssh -t'." >&2
        exit 1
    fi
    if [ -n "$padrao" ]; then
        read -r -p "$texto [$padrao] " r < /dev/tty
    else
        read -r -p "$texto " r < /dev/tty
    fi
    r="$(printf '%s' "$r" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    printf '%s' "${r:-$padrao}"
}

perguntar() {  # perguntar "texto" -> 0 se sim
    local texto="$1" r
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then
        echo "  ($texto -> sim, por HIPO_CONFIRMADO=1)"
        return 0
    fi
    r="$(ler "$texto [s/N]")"
    [ "$r" = "s" ] || [ "$r" = "S" ]
}

cancelar() { echo "Cancelado."; exit 3; }
titulo()   { echo; echo "== $* =="; }
ok()       { echo "  OK  $*"; }
aviso()    { echo "  !!  $*"; }
erro()     { echo; echo "ERRO: $*" >&2; exit 1; }

# Valor de uma chave num .env (600, dono ec2-user). Cascata de leitura como
# nos outros scripts: direto, depois sudo.
var_env() {  # var_env arquivo CHAVE
    local arq="$1" chave="$2" conteudo
    conteudo="$(cat "$arq" 2>/dev/null || sudo cat "$arq" 2>/dev/null || true)"
    # `|| true`: chave ausente e resposta valida (vazio), nao erro -- com
    # `set -eo pipefail`, o grep sem achado mataria o script calado.
    { printf '%s\n' "$conteudo" | grep -E "^${chave}=" | tail -1 | cut -d= -f2- \
        | sed -E "s/^['\"](.*)['\"]$/\1/"; } || true
}

mascarar() { sed 's/:[^:@]*@/:****@/'; }

# Troca o banco (e opcionalmente usuario/senha) de uma URL postgres sem
# perder host, porta e parametros (?sslmode=...). Senha entra pelo ambiente,
# nunca por argumento (apareceria no `ps`).
url_trocar() {  # NOVO_BANCO=x [NOVO_USUARIO=y NOVA_SENHA=z] url_trocar URL
    URL_BASE="$1" python3 - <<'PY'
import os
from urllib.parse import urlparse, urlunparse, quote
u = urlparse(os.environ["URL_BASE"])
usuario = os.environ.get("NOVO_USUARIO") or u.username or ""
senha = os.environ.get("NOVA_SENHA") if os.environ.get("NOVO_USUARIO") else u.password
netloc = quote(usuario, safe="")
if senha:
    netloc += ":" + quote(senha, safe="")
netloc += "@" + (u.hostname or "localhost")
if u.port:
    netloc += f":{u.port}"
print(urlunparse(u._replace(netloc=netloc, path="/" + os.environ["NOVO_BANCO"])))
PY
}

# Grava/atualiza chaves num .env preservando dono e modo. Valores entram por
# variaveis de ambiente HIPO_SET_<CHAVE>, nunca por argumento. Sem sudo: os
# dois .env sao de ec2-user, que e quem roda este script.
env_gravar() {  # env_gravar arquivo CHAVE1 CHAVE2 ...
    local arq="$1"; shift
    ARQ="$arq" CHAVES="$*" python3 - <<'PY'
import os, stat
p = os.environ["ARQ"]
chaves = os.environ["CHAVES"].split()
st = os.stat(p)
linhas = open(p, encoding="utf-8").read().splitlines()
novos = {c: os.environ[f"HIPO_SET_{c}"] for c in chaves}
saida, vistos = [], set()
for l in linhas:
    c = l.split("=", 1)[0].strip() if "=" in l else None
    if c in novos:
        if c not in vistos:
            saida.append(f"{c}={novos[c]}"); vistos.add(c)
    else:
        saida.append(l)
for c in chaves:
    if c not in vistos:
        saida.append(f"{c}={novos[c]}")
with open(p, "w", encoding="utf-8") as f:
    f.write("\n".join(saida) + "\n")
os.chown(p, st.st_uid, st.st_gid)
os.chmod(p, stat.S_IMODE(st.st_mode))
PY
}

reinicios() { systemctl show -p NRestarts --value "$UNIDADE" 2>/dev/null || echo 0; }

# active E sem reinicio novo: `is-active` mente durante crash-loop.
esperar_api() {
    local antes i
    antes="$(reinicios)"
    for i in $(seq 1 30); do
        if curl -sf "http://127.0.0.1:$PORTA/health" >/dev/null 2>&1 \
           && [ "$(reinicios)" = "$antes" ]; then
            return 0
        fi
        sleep 2
    done
    return 1
}

python_da_principal() {
    # O mesmo interpretador da hipo-api: e la que estao os pacotes. O deploy
    # nao roda pip, entao interpretador diferente = ModuleNotFoundError.
    local exe
    exe="$(systemctl show -p ExecStart --value hipo-api 2>/dev/null \
        | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
    printf '%s' "${exe:-/usr/bin/python3}"
}

# So o que os scripts leem por os.environ. O resto o proprio config.py le do
# /home/hipo/mos/.env (pai de /home/hipo/mos/api). Dar `source` no .env seria
# pior: o bash interpretaria & ? * de URLs e chaves.
carregar_env_mos() {
    [ -f "$ENV_MOS" ] || erro "$ENV_MOS nao existe. Rode a fase base."
    DATABASE_URL="$(var_env "$ENV_MOS" DATABASE_URL)"
    S3_BUCKET_ANEXOS="$(var_env "$ENV_MOS" S3_BUCKET_ANEXOS)"
    AWS_REGION="$(var_env "$ENV_MOS" AWS_REGION)"
    export DATABASE_URL S3_BUCKET_ANEXOS AWS_REGION="${AWS_REGION:-eu-central-1}"
    [ -n "$DATABASE_URL" ] || erro "$ENV_MOS sem DATABASE_URL."
}

conferir_banco_mos() {
    local id
    id="$(python3 -c 'import os,sys;from urllib.parse import urlparse;print(urlparse(sys.argv[1]).path.lstrip("/"))' "$DATABASE_URL")"
    [ "$id" = "$BANCO" ] || erro "DATABASE_URL carregado aponta para o banco '$id', e nao '$BANCO'. Parei."
    echo "  Banco: $(echo "$DATABASE_URL" | mascarar)"
}

# --------------------------------------------------------------------------
# fases
# --------------------------------------------------------------------------

fase_estado() {
    titulo "estado da instancia MOS"
    printf '  %-34s %s\n' "pasta $MOS" "$([ -d $MOS ] && echo existe || echo NAO)"
    printf '  %-34s %s\n' ".env da MOS" "$([ -f $ENV_MOS ] && echo existe || echo NAO)"
    printf '  %-34s %s\n' "codigo em $MOS/api" "$([ -f $MOS/api/main.py ] && echo existe || echo NAO)"
    printf '  %-34s %s\n' "servico $UNIDADE" "$(systemctl is-active $UNIDADE 2>/dev/null || true)"
    printf '  %-34s %s\n' "health 127.0.0.1:$PORTA" "$(curl -s --max-time 5 http://127.0.0.1:$PORTA/health || echo 'sem resposta')"
    printf '  %-34s %s\n' "front $WEB_MOS" "$([ -f $WEB_MOS/index.html ] && echo existe || echo NAO)"
    printf '  %-34s %s\n' "nginx conf.d/hipo-mos.conf" "$([ -f /etc/nginx/conf.d/hipo-mos.conf ] && echo existe || echo NAO)"
    printf '  %-34s %s\n' "DNS $DOMINIO" "$(timeout 5 getent ahostsv4 $DOMINIO | awk 'NR==1{print $1}' || true)"
    printf '  %-34s %s\n' "DNS $DOMINIO_MED" "$(timeout 5 getent ahostsv4 $DOMINIO_MED | awk 'NR==1{print $1}' || true)"
    printf '  %-34s %s\n' "certificado" "$(sudo test -d /etc/letsencrypt/live/$DOMINIO && echo emitido || echo NAO)"
    printf '  %-34s %s\n' "timer fechamento" "$(systemctl is-enabled hipo-mos-fechamento.timer 2>/dev/null || echo NAO)"
    printf '  %-34s %s\n' "base principal (8001)" "$(curl -s --max-time 5 http://127.0.0.1:8001/health || echo 'sem resposta')"
    if [ -f "$ENV_MOS" ]; then
        local url; url="$(var_env "$ENV_MOS" DATABASE_URL)"
        echo "  DATABASE_URL da MOS: $(echo "$url" | mascarar)"
        if [ -n "$url" ]; then
            psql "$url" -At -c "SELECT '  usuarios: ' || count(*) FROM usuarios" 2>/dev/null || true
            psql "$url" -At -c "SELECT '  trilhas UC: ' || count(*) FROM uc_trilhas" 2>/dev/null || true
            psql "$url" -At -c "SELECT '  contas: ' || count(*) FROM contas" 2>/dev/null || true
        fi
    fi
}

fase_base() {
    titulo "base: pasta, banco $BANCO, schema e .env"

    # A 046 tem que estar no ar ANTES: o .env da MOS leva EMPRESA_NOME e
    # EMPRESA_SIGLA, e o Settings e extra="forbid" -- com o config.py velho a
    # API da MOS morreria no import (claude/env-ordem-de-deploy-e-extra-forbid.md).
    grep -qE '^[[:space:]]*EMPRESA_SIGLA[[:space:]]*:' "$APP_MED/api/config.py" \
        || erro "o config.py em producao nao declara EMPRESA_SIGLA. O deploy da 046 ainda nao chegou."
    ok "config.py de producao ja e o da 046"

    local master
    master="$(var_env "$ENV_MED" DATABASE_URL)"
    [ -n "$master" ] || erro "$ENV_MED sem DATABASE_URL."
    echo "  Conexao administrativa (a da base principal): $(echo "$master" | mascarar)"

    local pode
    pode="$(psql "$master" -At -c "SELECT rolcreatedb::text || rolcreaterole::text FROM pg_roles WHERE rolname = current_user")"
    if [ "$pode" != "truetrue" ]; then
        aviso "o usuario do DATABASE_URL principal nao tem CREATEDB + CREATEROLE."
        echo "  Cole a URL do usuario MASTER do RDS (nao aparece na tela):"
        read -rs master < /dev/tty; echo
        master="$(printf '%s' "$master" | tr -d '\r')"
        pode="$(psql "$master" -At -c "SELECT rolcreatedb::text || rolcreaterole::text FROM pg_roles WHERE rolname = current_user")"
        [ "$pode" = "truetrue" ] || erro "esse usuario tambem nao pode criar banco e role."
    fi
    ok "usuario administrativo pode criar banco e role"

    sudo mkdir -p "$MOS/api" "$MOS/uploads"
    sudo chown -R ec2-user:ec2-user "$MOS"
    ok "pasta $MOS (dono ec2-user)"

    local existe_banco existe_role url_mos=""
    existe_banco="$(psql "$master" -At -c "SELECT 1 FROM pg_database WHERE datname = '$BANCO'")"
    existe_role="$(psql "$master" -At -c "SELECT 1 FROM pg_roles WHERE rolname = '$ROLE'")"
    [ -f "$ENV_MOS" ] && url_mos="$(var_env "$ENV_MOS" DATABASE_URL)"

    if [ "$existe_banco" = "1" ] && [ -n "$url_mos" ] && psql "$url_mos" -At -c "SELECT 1" >/dev/null 2>&1; then
        ok "banco $BANCO ja existe e o .env da MOS conecta nele"
    else
        echo
        echo "  Vai criar (ou reaproveitar) a role '$ROLE' e o banco '$BANCO' no RDS:"
        echo "    $(echo "$master" | mascarar | sed -E 's#/[^/?]*(\?|$)#/'$BANCO'\1#')"
        perguntar "Seguir?" || cancelar

        local senha
        senha="$(openssl rand -hex 24)"
        if [ "$existe_role" = "1" ]; then
            psql "$master" -v ON_ERROR_STOP=1 -q -v senha="$senha" <<SQL
ALTER ROLE $ROLE WITH LOGIN PASSWORD :'senha';
SQL
            ok "role $ROLE ja existia -- senha nova gerada"
        else
            psql "$master" -v ON_ERROR_STOP=1 -q -v senha="$senha" <<SQL
CREATE ROLE $ROLE WITH LOGIN PASSWORD :'senha';
SQL
            ok "role $ROLE criada"
        fi
        # No RDS o master nao e superusuario de verdade: para dar o banco a
        # outra role, precisa ser membro dela.
        psql "$master" -v ON_ERROR_STOP=1 -q -c "GRANT $ROLE TO CURRENT_USER" >/dev/null 2>&1 || true
        if [ "$existe_banco" != "1" ]; then
            psql "$master" -v ON_ERROR_STOP=1 -q -c "CREATE DATABASE $BANCO OWNER $ROLE"
            ok "banco $BANCO criado (dono $ROLE)"
        fi
        # Ninguem alem da dona (e do master) conecta na base da MOS.
        psql "$master" -v ON_ERROR_STOP=1 -q -c "REVOKE ALL ON DATABASE $BANCO FROM PUBLIC"
        psql "$master" -v ON_ERROR_STOP=1 -q -c "GRANT CONNECT, TEMPORARY ON DATABASE $BANCO TO $ROLE"

        url_mos="$(NOVO_BANCO=$BANCO NOVO_USUARIO=$ROLE NOVA_SENHA="$senha" url_trocar "$master")"
        unset senha
    fi

    # pg_trgm pelo master: no RDS e extensao confiavel, mas criar como master
    # nao depende disso.
    psql "$(NOVO_BANCO=$BANCO url_trocar "$master")" -v ON_ERROR_STOP=1 -q \
        -c "CREATE EXTENSION IF NOT EXISTS pg_trgm" 2>&1 | grep -v NOTICE || true

    if [ "$(psql "$url_mos" -At -c "SELECT to_regclass('public.usuarios') IS NOT NULL")" = "t" ]; then
        ok "schema ja aplicado em $BANCO"
    else
        psql "$url_mos" -v ON_ERROR_STOP=1 -q -f "$APP_MED/api/schema.sql" 2>&1 | grep -v NOTICE || true
        [ "$(psql "$url_mos" -At -c "SELECT to_regclass('public.usuarios') IS NOT NULL")" = "t" ] \
            || erro "o schema.sql nao criou as tabelas em $BANCO."
        ok "schema.sql aplicado em $BANCO ($(psql "$url_mos" -At -c "SELECT count(*) FROM pg_tables WHERE schemaname='public'") tabelas)"
    fi

    if [ -f "$ENV_MOS" ]; then
        HIPO_SET_DATABASE_URL="$url_mos" env_gravar "$ENV_MOS" DATABASE_URL
        ok ".env da MOS ja existia -- so o DATABASE_URL foi conferido"
        return 0
    fi

    echo
    echo "  Nome da empresa como o CLIENTE le (vai no convite do Google Calendar"
    echo "  e no nome do arquivo do RPeR). Sem acento problematico, sem \$ # ' \"."
    local nome
    while :; do
        nome="$(ler "  EMPRESA_NOME:" "MOS")"
        if printf '%s' "$nome" | grep -qE "[\$#'\"\\\\]"; then
            aviso "caractere nao permitido (o systemd le o .env sem escape)"
        elif [ -z "$nome" ]; then
            aviso "vazio"
        else
            break
        fi
    done

    # O .env da MOS nasce do da principal (chaves da IA, SES, S3, fontes de
    # enriquecimento) MENOS o que e da MedSeg ou tem que ser proprio.
    ( umask 077; : > "$ENV_MOS" )
    chmod 600 "$ENV_MOS"
    ORIGEM="$ENV_MED" DESTINO="$ENV_MOS" \
    HIPO_URL="$url_mos" HIPO_JWT="$(openssl rand -hex 32)" HIPO_NOME="$nome" \
    HIPO_SIGLA="$SIGLA" HIPO_UPLOAD="$MOS/uploads" HIPO_CORS="https://$DOMINIO" \
    python3 - <<'PY'
import os
FORA = {
    # proprios da instancia (sobrescritos abaixo)
    "DATABASE_URL", "JWT_SECRET", "UPLOAD_DIR", "CORS_ORIGINS",
    "EMPRESA_NOME", "EMPRESA_SIGLA", "PROPOSTA_MODELO_ARQUIVO",
    "DB_POOL_MIN", "DB_POOL_MAX",
    # da MedSeg: e-mail diario da equipe dela; conta de servico do Google
    # com delegacao no dominio dela; token da ponte dela
    "RELATORIO_DESTINATARIOS", "GOOGLE_SA_ARQUIVO", "BRIDGE_TOKEN",
}
origem = open(os.environ["ORIGEM"], encoding="utf-8").read().splitlines()
saida = ["# HIPO -- instancia MOS (046). Gerado a partir do .env da base principal.",
         "# Proprio desta base: DATABASE_URL, JWT_SECRET, UPLOAD_DIR, CORS, EMPRESA_*.",
         "# Ordem para chave NOVA: codigo declarando no config.py primeiro, .env depois."]
for l in origem:
    s = l.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    if s.split("=", 1)[0].strip() in FORA:
        continue
    saida.append(s)
saida += [
    "DATABASE_URL=" + os.environ["HIPO_URL"],
    "JWT_SECRET=" + os.environ["HIPO_JWT"],
    "UPLOAD_DIR=" + os.environ["HIPO_UPLOAD"],
    "CORS_ORIGINS=" + os.environ["HIPO_CORS"],
    # Entre aspas: o systemd e o pydantic tiram as aspas, e um `source` do
    # .env no bash nao quebra no espaco do nome.
    'EMPRESA_NOME="' + os.environ["HIPO_NOME"] + '"',
    "EMPRESA_SIGLA=" + os.environ["HIPO_SIGLA"],
    "DB_POOL_MAX=3",
    "RELATORIO_DESTINATARIOS=",
]
with open(os.environ["DESTINO"], "w", encoding="utf-8") as f:
    f.write("\n".join(saida) + "\n")
PY
    ls -l "$ENV_MOS"
    ok ".env da MOS criado (JWT proprio: login de uma base nao vale na outra)"
    echo "  Chaves: $(cut -d= -f1 "$ENV_MOS" | grep -v '^#' | tr '\n' ' ')"
}

fase_app() {
    titulo "app: codigo, servico $UNIDADE e front"
    [ -f "$ENV_MOS" ] || erro "sem $ENV_MOS. Rode a fase base."

    rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' \
        "$APP_MED/api/" "$MOS/api/"
    ok "codigo copiado de $APP_MED/api (o CI assume nos proximos deploys)"

    local py unit=/etc/systemd/system/$UNIDADE.service
    py="$(python_da_principal)"
    sed "s#/usr/bin/python3 -m uvicorn#$py -m uvicorn#" "$DIR_SCRIPT/hipo-mos-api.service" \
        | sudo tee "$unit" >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable "$UNIDADE" >/dev/null 2>&1
    sudo systemctl restart "$UNIDADE"
    if ! esperar_api; then
        sudo systemctl status "$UNIDADE" --no-pager || true
        sudo journalctl -u "$UNIDADE" -n 60 --no-pager || true
        erro "a API da MOS nao ficou de pe na $PORTA."
    fi
    local h; h="$(curl -s http://127.0.0.1:$PORTA/health)"
    echo "  $h"
    echo "$h" | grep -q "\"instancia\":\"$SIGLA\"" || erro "a 8002 respondeu, mas nao como $SIGLA."
    ok "$UNIDADE de pe na $PORTA (interpretador $py)"

    sudo mkdir -p "$WEB_MOS"
    sudo chown ec2-user:ec2-user "$WEB_MOS"
    rsync -a --delete "$WEB_MED/" "$WEB_MOS/"
    sudo chmod -R 755 "$WEB_MOS"
    ok "front copiado para $WEB_MOS"

    curl -sf http://127.0.0.1:8001/health >/dev/null && ok "base principal (8001) segue de pe" \
        || aviso "a 8001 nao respondeu -- confira a base principal AGORA"
}

fase_nginx() {
    titulo "nginx: $DOMINIO -> 127.0.0.1:$PORTA"
    [ -f "$WEB_MOS/index.html" ] || erro "front ausente em $WEB_MOS. Rode a fase app."

    # Mesmo limite de upload da base principal (material da UC, anexo).
    local limite
    limite="$(sudo nginx -T 2>/dev/null | grep -oE 'client_max_body_size[[:space:]]+[0-9]+[mMkKgG]?' \
        | awk '{print $2}' | sort -h | tail -1)"
    limite="${limite:-50M}"

    local conf=/etc/nginx/conf.d/hipo-mos.conf
    if sudo test -f "$conf" && sudo grep -q 'listen 443' "$conf"; then
        ok "$conf ja tem TLS (certbot) -- nao vou sobrescrever"
    else
        sed "s/client_max_body_size 50M;/client_max_body_size $limite;/" \
            "$DIR_SCRIPT/hipo-mos.nginx.conf" | sudo tee "$conf" >/dev/null
        ok "$conf gravado (client_max_body_size $limite)"
    fi
    sudo nginx -t
    sudo systemctl reload nginx

    local r
    r="$(curl -s -H "Host: $DOMINIO" http://127.0.0.1/api/health || true)"
    echo "  via nginx, Host $DOMINIO: $r"
    echo "$r" | grep -q "\"instancia\":\"$SIGLA\"" || erro "o nginx nao entregou $DOMINIO para a $PORTA."
    r="$(curl -s -H "Host: $DOMINIO_MED" http://127.0.0.1/api/health || true)"
    echo "  via nginx, Host $DOMINIO_MED: $r"
    if echo "$r" | grep -q "\"instancia\":\"$SIGLA\""; then
        erro "a base principal passou a cair na MOS. Remova $conf e recarregue o nginx."
    fi
    ok "cada dominio no seu servico"
}

fase_tls() {
    titulo "tls: certificado de $DOMINIO"
    local ip_mos ip_med
    ip_mos="$(timeout 5 getent ahostsv4 $DOMINIO | awk 'NR==1{print $1}' || true)"
    ip_med="$(timeout 5 getent ahostsv4 $DOMINIO_MED | awk 'NR==1{print $1}' || true)"
    echo "  $DOMINIO -> ${ip_mos:-(nao resolve)}   $DOMINIO_MED -> $ip_med"
    [ -n "$ip_mos" ] || erro "$DOMINIO ainda nao resolve. Crie no Registro.br (CNAME mos -> $DOMINIO_MED) e espere o SOA mudar."
    [ "$ip_mos" = "$ip_med" ] || erro "$DOMINIO aponta para outro IP. O certbot falharia."

    if ! command -v certbot >/dev/null 2>&1; then
        aviso "certbot nao instalado. Certificado da base principal:"
        sudo nginx -T 2>/dev/null | grep -E 'ssl_certificate[^_]' | sort -u || true
        perguntar "Instalar certbot + plugin nginx (dnf)?" || cancelar
        sudo dnf install -y certbot python3-certbot-nginx
    fi

    local email_args=(--register-unsafely-without-email)
    if sudo test -d /etc/letsencrypt/accounts && \
       [ -n "$(sudo find /etc/letsencrypt/accounts -name regr.json 2>/dev/null | head -1)" ]; then
        email_args=()
        ok "conta do Let's Encrypt ja existe nesta maquina"
    else
        local email
        email="$(ler "  E-mail para avisos de expiracao do certificado:" "tulio.horta@controllermedseg.com")"
        email_args=(-m "$email")
    fi

    sudo certbot --nginx -d "$DOMINIO" --non-interactive --agree-tos --redirect \
        --keep-until-expiring "${email_args[@]}"
    sudo nginx -t && sudo systemctl reload nginx

    if systemctl list-timers --all 2>/dev/null | grep -q certbot; then
        ok "renovacao automatica: $(systemctl list-timers --all | grep certbot | awk '{print $NF}' | head -1)"
    elif systemctl list-unit-files 2>/dev/null | grep -q '^certbot-renew.timer'; then
        sudo systemctl enable --now certbot-renew.timer
        ok "certbot-renew.timer ligado"
    else
        aviso "nao achei timer de renovacao. Confira como o certificado de $DOMINIO_MED renova (cron?)."
    fi

    local r
    r="$(curl -s --max-time 15 "https://$DOMINIO/api/health" || true)"
    echo "  https://$DOMINIO/api/health -> $r"
    echo "$r" | grep -q "\"instancia\":\"$SIGLA\"" || aviso "nao consegui provar o https daqui de dentro (hairpin). O smoke do deploy-046 confere de fora."
}

fase_config() {
    titulo "config: clona a configuracao da MedSeg para $BANCO"
    carregar_env_mos
    conferir_banco_mos
    cd "$MOS/api"
    local py; py="$(python_da_principal)"

    local receita=""
    local n_receita
    n_receita="$(psql "$(var_env "$ENV_MED" DATABASE_URL)" -At -c "SELECT count(*) FROM receita_estabelecimentos" 2>/dev/null || echo 0)"
    echo "  Base da Receita na MedSeg: $n_receita estabelecimentos (tela de Prospeccao)."
    if [ "${n_receita:-0}" != "0" ] && perguntar "Copiar a base da Receita tambem?"; then
        receita="--com-base-receita"
    fi

    PYTHONPATH="$MOS/api" "$py" -m scripts.clonar_config --origem-env "$ENV_MED" \
        --prefixo-s3 "mos/" $receita
    echo
    perguntar "Gravar a copia acima em $BANCO?" || cancelar
    PYTHONPATH="$MOS/api" "$py" -m scripts.clonar_config --origem-env "$ENV_MED" \
        --prefixo-s3 "mos/" $receita --executar
}

fase_usuario() {
    titulo "usuario: cadastro na base MOS"
    carregar_env_mos
    conferir_banco_mos
    cd "$MOS/api"
    local py; py="$(python_da_principal)"
    while :; do
        local login nome cargo
        login="$(ler "  E-mail de login:")"
        [ -n "$login" ] || { echo "  (vazio -- fim)"; break; }
        nome="$(ler "  Nome:")"
        cargo="$(ler "  Cargo (Franqueado, ADM, EC, SDR, EV, EP):" "Franqueado")"
        PYTHONPATH="$MOS/api" "$py" -m scripts.criar_usuario "$login" --nome "$nome" --cargo "$cargo" \
            || aviso "nao criado -- confira os dados"
        perguntar "Cadastrar outra pessoa?" || break
    done
    echo "  Senha inicial 123456; troca obrigatoria em /perfil no primeiro login."
}

fase_fechamento() {
    titulo "fechamento: e-mail diario da MOS"
    [ -f "$ENV_MOS" ] || erro "sem $ENV_MOS. Rode a fase base."
    local py; py="$(python_da_principal)"
    local s
    for s in hipo-mos-fechamento.service hipo-mos-fechamento.timer; do
        sed "s#/usr/bin/python3 -m#$py -m#" "$DIR_SCRIPT/$s" | sudo tee "/etc/systemd/system/$s" >/dev/null
    done
    sudo systemctl daemon-reload
    ok "units instaladas"

    local atual
    atual="$(var_env "$ENV_MOS" RELATORIO_DESTINATARIOS)"
    echo "  Destinatarios hoje: ${atual:-(nenhum)}"
    local novos
    novos="$(ler "  Destinatarios (virgula, sem espaco; Enter mantem):" "$atual")"
    novos="$(printf '%s' "$novos" | tr -d ' ')"
    if [ "$novos" != "$atual" ]; then
        HIPO_SET_RELATORIO_DESTINATARIOS="$novos" env_gravar "$ENV_MOS" RELATORIO_DESTINATARIOS
        ok "RELATORIO_DESTINATARIOS gravado (o fechamento rele o .env a cada disparo)"
    fi

    if [ -n "$novos" ]; then
        sudo systemctl enable --now hipo-mos-fechamento.timer
        systemctl list-timers hipo-mos-fechamento.timer --no-pager | head -3
        ok "timer ligado (Ter..Sab 03:15)"
    else
        sudo systemctl disable --now hipo-mos-fechamento.timer >/dev/null 2>&1 || true
        aviso "sem destinatarios: timer desligado. Rode esta fase de novo quando houver."
    fi
}

case "$FASE" in
    estado)     fase_estado ;;
    base)       fase_base ;;
    app)        fase_app ;;
    nginx)      fase_nginx ;;
    tls)        fase_tls ;;
    config)     fase_config ;;
    usuario)    fase_usuario ;;
    fechamento) fase_fechamento ;;
    *)
        sed -n '2,32p' "$0"
        exit 1
        ;;
esac
