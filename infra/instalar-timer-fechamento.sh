#!/usr/bin/env bash
# =====================================================================
# HIPO - Instala o timer do fechamento diario e faz o ensaio a SECO.
#
# NAO habilita nada e NAO envia e-mail. Para de proposito antes disso: o
# ultimo passo e uma decisao sua, depois de olhar o JSON que este script
# imprime.
#
# POR QUE OS ARQUIVOS VEM JUNTO, E NAO DE /home/hipo/app/infra
#
# O deploy do CI (.github/workflows/ci-cd.yml, linha 151) faz rsync SO de
# `api/` e de `web/dist/`. A pasta `infra/` NUNCA sobe. Um push com o timer
# corrigido nao coloca o arquivo corrigido no servidor -- ele so existe la se
# alguem copiar a mao. Por isso as tres pecas viajam juntas.
#
# Rodar da raiz do repositorio, no Windows:
#   $K = "$HOME\Downloads\chave-hipo.pem"
#   scp -i $K infra\hipo-fechamento.service infra\hipo-fechamento.timer `
#             infra\instalar-timer-fechamento.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i $K ec2-user@63.179.88.212 "bash /tmp/instalar-timer-fechamento.sh"
# =====================================================================
set -o pipefail

APP=/home/hipo/app
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
titulo() { printf '\n==== %s ====\n' "$1"; }
parar()  { printf '\n!! %s\n' "$1"; exit 1; }

titulo "0. Normalizando as units (scp do Windows traz CRLF)"
# O systemd tolera o \r, mas `sed`, `grep -E ... $` e qualquer leitura por
# script nao toleram -- e um diagnostico que falha por causa de um \r e pior
# que nenhum, porque parece um problema de verdade.
TMP=$(mktemp -d) || parar "mktemp falhou"
trap 'rm -rf "$TMP"' EXIT
for u in hipo-fechamento.service hipo-fechamento.timer; do
    [ -f "$AQUI/$u" ] || parar "nao achei $AQUI/$u -- mande as duas units no mesmo scp"
    tr -d '\r' < "$AQUI/$u" > "$TMP/$u" || parar "falha ao normalizar $u"
done
T="$TMP/hipo-fechamento.timer"
echo "  [ok] service e timer normalizados em $TMP"

titulo "1. E a versao corrigida?"
# Instalar a versao antiga recria exatamente o bug que acabamos de corrigir.
if grep -q '^Timezone=' "$T"; then
    parar "este timer ainda tem a chave Timezone=. E a versao velha."
fi
if ! grep -qE '^OnCalendar=Tue\.\.Sat .*America/Sao_Paulo$' "$T"; then
    echo "  OnCalendar encontrado:"
    grep '^OnCalendar=' "$T" | sed 's/^/    /'
    parar "esperava 'Tue..Sat ... America/Sao_Paulo'."
fi
grep '^OnCalendar=' "$T" | sed 's/^/  /'
echo "  [ok] versao corrigida"

titulo "2. As duas units carregam sem aviso?"
systemd-analyze verify "$TMP/hipo-fechamento.service" 2>&1 | sed 's/^/  /'
systemd-analyze verify "$T" 2>&1 | sed 's/^/  /'
echo "  (nenhuma linha acima = as duas limpas)"

titulo "3. Quando ele vai disparar"
systemd-analyze calendar --iterations=6 \
    "$(sed -n 's/^OnCalendar=//p' "$T")" | sed 's/^/  /'
echo "  Confira: TER a SAB, 06:10 UTC = 03:10 em Sao Paulo."

titulo "4. Instalando as units (ainda sem habilitar)"
sudo install -m 0644 -o root -g root \
    "$TMP/hipo-fechamento.service" "$T" /etc/systemd/system/ \
    || parar "install falhou"
sudo systemctl daemon-reload || parar "daemon-reload falhou"
echo "  [ok] copiadas e recarregadas"
systemctl is-enabled hipo-fechamento.timer 2>&1 | sed 's/^/  enabled: /'

titulo "5. ENSAIO A SECO - no MESMO contexto que a unit vai usar"
# systemd-run reproduz User=, EnvironmentFile= e WorkingDirectory= da unit.
# Rodar 'python3 ...' na mao como root provaria que o CODIGO funciona e nao
# provaria nada sobre a unit -- e e na unit que moram os erros de permissao e
# de variavel que so aparecem na primeira execucao real.
#
# --so-imprime: nao grava, nao chama a IA, nao envia e-mail.
sudo systemd-run \
    --uid=hipo --gid=hipo \
    --property=EnvironmentFile="$APP/.env" \
    --property=WorkingDirectory="$APP/api" \
    --setenv=PYTHONPATH="$APP/api" \
    --setenv=PYTHONUNBUFFERED=1 \
    --wait --pipe --quiet \
    /usr/bin/python3 -m scripts.fechamento_diario --so-imprime
CODIGO=$?
if [ $CODIGO -ne 0 ]; then
    parar "o ensaio a seco falhou (codigo $CODIGO). NAO habilite o timer."
fi

cat <<'FIM'

==== ENSAIO PASSOU ====

Leia o JSON acima antes de seguir. O que importa:

  adocao.disponivel ...... tem que ser true
  adocao.acoes ........... o volume do dia, ja SEM a varredura da internet
  adocao.pessoas_ativas .. quantas pessoas de verdade
  adocao.sem_acesso_hoje . quem nao entrou
  operacao.* ............. o que andou no funil e na carteira

Se estiver com cara boa, faltam dois passos, nesta ordem:

  1. Gravar o fechamento de ontem SEM enviar e-mail. Prova a escrita em
     relatorios_diarios e continua idempotente:

       sudo systemd-run --uid=hipo --gid=hipo \
         --property=EnvironmentFile=/home/hipo/app/.env \
         --property=WorkingDirectory=/home/hipo/app/api \
         --setenv=PYTHONPATH=/home/hipo/app/api --wait --pipe --quiet \
         /usr/bin/python3 -m scripts.fechamento_diario --sem-email

       psql "$(sudo sed -n 's/^DATABASE_URL=//p' /home/hipo/app/.env)" \
         -c "select dia, gerado_em, enviado_em, narrativa_modelo
               from relatorios_diarios order by dia desc;"

     enviado_em NULO aqui e o esperado -- e o que deixa o e-mail daquele
     dia ainda sair depois.

  2. So entao habilitar:

       sudo systemctl enable --now hipo-fechamento.timer
       systemctl list-timers hipo-fechamento.timer

LEMBRETE: `infra/` nao entra no deploy. Toda vez que o timer ou o service
mudarem no repositorio, e preciso rodar este script de novo -- push nenhum
leva essas duas units para o servidor.

FIM
