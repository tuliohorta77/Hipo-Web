#!/usr/bin/env bash
# =====================================================================
# HIPO - Diagnostico do fechamento diario e da telemetria.
#
# SO LE. Nao instala, nao habilita, nao apaga, nao envia e-mail.
# Responde as perguntas que sobraram depois do deploy de 20/08.
#
# Rodar na EC2 como ec2-user:
#   scp -i "$HOME/Downloads/chave-hipo.pem" diagnostico-fechamento.sh \
#       ec2-user@63.179.88.212:/tmp/
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/diagnostico-fechamento.sh'
#
# ASCII puro e sem `set -e`: um item que falha nao pode esconder os outros.
# Cada bloco imprime o proprio resultado e o script segue.
# =====================================================================

titulo() { printf '\n==== %s ====\n' "$1"; }
D=""

titulo "0. Servidor"
hostname
echo "systemd  : $(systemctl --version | head -1)"
echo "data UTC : $(date -u '+%F %T')"
echo "data SP  : $(TZ=America/Sao_Paulo date '+%F %T %Z')"
echo "timedatectl:"
timedatectl 2>/dev/null | sed 's/^/  /' | head -4

titulo "1. API viva e em que versao"
systemctl is-active hipo-api
curl -s --max-time 10 http://127.0.0.1:8001/health; echo

titulo "2. Variaveis do .env que o fechamento precisa"
# So diz se EXISTE. Nunca imprime valor de segredo.
for k in DATABASE_URL JWT_SECRET ANTHROPIC_API_KEY SES_REMETENTE \
         RELATORIO_DESTINATARIOS AWS_REGION TELEMETRIA_ATIVA \
         TELEMETRIA_RETENCAO_DIAS; do
    if sudo grep -q "^${k}=" /home/hipo/app/.env 2>/dev/null; then
        case "$k" in
            ANTHROPIC_API_KEY|JWT_SECRET|DATABASE_URL) echo "  $k = (definida)" ;;
            *) echo "  $k = $(sudo sed -n "s/^${k}=//p" /home/hipo/app/.env)" ;;
        esac
    else
        echo "  $k = AUSENTE"
    fi
done

titulo "3. Host do banco (mascarado) - confirma que nao e o Knotty"
D=$(sudo sed -n 's/^DATABASE_URL=//p' /home/hipo/app/.env)
if [ -z "$D" ]; then
    echo "  DATABASE_URL vazia. Os blocos de banco abaixo vao falhar."
else
    echo "$D" | sed 's/:[^:@]*@/:****@/'
fi

titulo "4. A migration 007 foi aplicada?"
psql "$D" -Atc "select table_name from information_schema.tables
                 where table_name in ('uso_eventos','relatorios_diarios')
                 order by 1;"
echo "  (esperado: as DUAS linhas)"

titulo "5. A telemetria esta gravando?"
psql "$D" -Atc "select 'eventos=' || count(*)
                     || ' | primeiro=' || coalesce(min(criado_em)::text,'-')
                     || ' | ultimo='   || coalesce(max(criado_em)::text,'-')
                  from uso_eventos;"
echo "  -- ultimos 7 dias, por dia (fuso da operacao):"
psql "$D" -c "select (criado_em at time zone 'America/Sao_Paulo')::date as dia,
                      count(*) as eventos,
                      count(distinct usuario_id) as pessoas,
                      count(*) filter (where status >= 500) as erros_5xx
                 from uso_eventos
                where criado_em >= now() - interval '7 days'
                group by 1 order by 1 desc;"

titulo "6. Ja existe algum fechamento gravado?"
psql "$D" -c "select dia, gerado_em, enviado_em,
                      narrativa is not null as tem_narrativa,
                      narrativa_modelo, destinatarios, erro
                 from relatorios_diarios
                order by dia desc limit 10;"

titulo "7. O timer do fechamento existe / esta ligado?"
if [ -f /etc/systemd/system/hipo-fechamento.timer ]; then
    echo "  unit INSTALADA em /etc/systemd/system"
    systemctl is-enabled hipo-fechamento.timer 2>&1 | sed 's/^/  enabled: /'
    systemctl is-active  hipo-fechamento.timer 2>&1 | sed 's/^/  active : /'
    systemctl list-timers hipo-fechamento.timer --all --no-pager
    echo "  -- OnCalendar publicado:"
    systemctl show hipo-fechamento.timer -p TimersCalendar --no-pager
    echo "  -- ultimas execucoes do service:"
    sudo journalctl -u hipo-fechamento.service -n 30 --no-pager 2>/dev/null | sed 's/^/  /'
else
    echo "  unit NAO instalada -- o fechamento nunca rodou sozinho."
fi

titulo "8. O systemd aceita o sufixo de fuso? (precisa de >= 252)"
systemd-analyze calendar '*-*-* 03:10:00 America/Sao_Paulo' 2>&1 | sed 's/^/  /'
echo "  -- e como esta hoje no repo (sem sufixo, com Timezone= ignorada):"
systemd-analyze calendar '*-*-* 03:10:00' 2>&1 | sed 's/^/  /'

titulo "9. O usuario 'hipo' consegue rodar o fechamento?"
# A unit declara User=hipo. As instrucoes do project dizem que /home/hipo/app
# e do ec2-user. Se este bloco disser NAO, a unit precisa de User=ec2-user.
id hipo 2>&1 | sed 's/^/  /'
ls -ld /home/hipo/app /home/hipo/app/api 2>&1 | sed 's/^/  /'
sudo -u hipo test -r /home/hipo/app/api/scripts/fechamento_diario.py \
  && echo "  hipo LE o script -- User=hipo serve" \
  || echo "  hipo NAO LE o script -- trocar para User=ec2-user"

titulo "10. Telemetria reclamando no log da API?"
sudo journalctl -u hipo-api --since '24 hours ago' --no-pager 2>/dev/null \
  | grep -i 'telemetria' | tail -20
echo "  (vazio aqui e boa noticia)"

titulo "11. boto3 / httpx no python que o systemd usa"
/usr/bin/python3 - <<'PY' 2>&1 | sed 's/^/  /'
for m in ("boto3", "botocore", "httpx", "asyncpg", "jose"):
    try:
        mod = __import__(m)
        print(f"{m:10} {getattr(mod, '__version__', '?')}")
    except Exception as e:
        print(f"{m:10} AUSENTE ({type(e).__name__})")
PY
echo "  requirements.txt pina boto3==1.34.162"

titulo "12. SES e IAM ainda de pe"
/usr/bin/python3 - <<'PY' 2>&1 | sed 's/^/  /'
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
R = "eu-central-1"
def tenta(rotulo, fn):
    try:
        print(f"{rotulo:16} -> {fn()}")
    except ClientError as e:
        err = e.response["Error"]
        print(f'{rotulo:16} -> ERRO {err["Code"]}: {err.get("Message","")}')
    except NoCredentialsError:
        print(f"{rotulo:16} -> SEM CREDENCIAL")
    except Exception as e:
        print(f"{rotulo:16} -> ERRO {type(e).__name__}: {e}")

tenta("identidade", lambda: boto3.client("sts", region_name=R)
      .get_caller_identity()["Arn"])
v2 = boto3.client("sesv2", region_name=R)
tenta("conta SES", lambda: {k: v2.get_account()[k]
      for k in ("ProductionAccessEnabled", "SendingEnabled")})
tenta("dominio DKIM", lambda: v2.get_email_identity(
      EmailIdentity="hipogestao.com.br")["DkimAttributes"]["Status"])
PY

titulo "13. O alias de modelo do config.py existe na conta?"
# config.py usa ANTHROPIC_MODEL="claude-haiku-4-5" (alias, sem data). A conta
# lista IDs datados. Se o alias nao resolver, `ia.narrar` falha em silencio e o
# e-mail sai so com os numeros -- que e o fallback previsto, mas por engano.
# GET /v1/models nao consome credito.
MODELO=$(sudo sed -n 's/^ANTHROPIC_MODEL=//p' /home/hipo/app/.env)
MODELO=${MODELO:-claude-haiku-4-5}
echo "  modelo configurado: $MODELO"
KEY=$(sudo sed -n 's/^ANTHROPIC_API_KEY=//p' /home/hipo/app/.env)
if [ -z "$KEY" ]; then
    echo "  ANTHROPIC_API_KEY ausente -- narrativa desligada."
else
    curl -s --max-time 15 "https://api.anthropic.com/v1/models/$MODELO" \
        -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" \
        | head -c 400 | sed 's/^/  /'
    echo
fi
unset KEY

titulo "14. DMARC do dominio"
dig +short TXT _dmarc.hipogestao.com.br 2>/dev/null | sed 's/^/  /'
echo "  (vazio = registro DMARC ainda nao existe)"

printf '\n==== FIM ====\n'
