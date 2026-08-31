#!/usr/bin/env bash
# =====================================================================
# HIPO - Por que a telemetria enxerga no maximo UMA pessoa por dia?
#
# 2927 eventos em 11 dias, e varios dias com 100+ eventos e ZERO pessoas
# identificadas. Se a maioria das linhas tem usuario_id NULL, o relatorio de
# ADOCAO -- que existe justamente para dizer quem usou o sistema -- nasce
# cego. Vale responder antes de ligar o timer.
#
# Tres hipoteses, e cada bloco separa uma:
#   A. sessao expirada / front chamando sem token -> anonimo com 401
#   B. o 'sub' do JWT nao e o e-mail -> a subquery do INSERT devolve NULL
#      em TODA request, inclusive nas autenticadas com sucesso (200)
#   C. e real: so uma pessoa usa mesmo o sistema hoje
#
# SO LE. Nao altera nada.
#   scp -i "$HOME/Downloads/chave-hipo.pem" infra/diagnostico-identidade.sh \
#       ec2-user@63.179.88.212:/tmp/
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/diagnostico-identidade.sh'
# =====================================================================

titulo() { printf '\n==== %s ====\n' "$1"; }
D=$(sudo sed -n 's/^DATABASE_URL=//p' /home/hipo/app/.env)
if [ -z "$D" ]; then echo "DATABASE_URL vazia."; exit 1; fi

titulo "1. Anonimo x identificado - a proporcao"
psql "$D" -c "select
                case when usuario_id is null then 'ANONIMO' else 'identificado' end as tipo,
                count(*) as eventos,
                round(100.0 * count(*) / sum(count(*)) over (), 1) as pct,
                min(criado_em)::date as de,
                max(criado_em)::date as ate
              from uso_eventos group by 1 order by 2 desc;"

titulo "2. DECISIVO: existe evento anonimo com status 2xx?"
# Se SIM, a hipotese B esta viva: a request foi autorizada (passou pelo
# requer_modulo, logo o token era valido) e mesmo assim nao identificou quem
# era. Isso so acontece se o 'sub' do JWT nao casar com usuarios.email.
# Se todo anonimo for 401/403, e sessao expirada -- hipotese A, benigna.
psql "$D" -c "select status, count(*) as eventos
              from uso_eventos where usuario_id is null
              group by 1 order by 2 desc;"

titulo "3. O que os anonimos estao chamando"
psql "$D" -c "select metodo, rota, status, count(*) as eventos
              from uso_eventos where usuario_id is null
              group by 1,2,3 order by 4 desc limit 20;"

titulo "4. Quem o sistema CONSEGUIU identificar"
psql "$D" -c "select u.email, u.cargo, e.cargo as cargo_no_evento,
                     count(*) as eventos, max(e.criado_em) as ultimo
              from uso_eventos e join usuarios u on u.id = e.usuario_id
              group by 1,2,3 order by 4 desc;"

titulo "5. Quantas pessoas existem para serem identificadas"
psql "$D" -c "select cargo, count(*) as usuarios,
                     string_agg(email, ', ' order by email) as quem
              from usuarios group by 1 order by 1;"

titulo "6. Logins bem-sucedidos no periodo (o teto do que era identificavel)"
psql "$D" -c "select (criado_em at time zone 'America/Sao_Paulo')::date as dia,
                     count(*) filter (where status = 200) as login_ok,
                     count(*) filter (where status <> 200) as login_falhou
              from uso_eventos
              where rota like '/auth/login%'
              group by 1 order by 1 desc limit 14;"

titulo "7. O commit 39e943a chegou mesmo no servidor?"
# Estes tres simbolos so existem depois dos dois ultimos commits de 20/08.
# Se algum faltar, o deploy parou num commit anterior e o 'CI vermelho' que o
# subir-telemetria.ps1 reportou era real -- e nao a falha de rede do gh.
for simbolo in descarga_periodica INTERVALO_DESCARGA_S IDADE_MAXIMA_S; do
    if grep -q "$simbolo" /home/hipo/app/api/middleware/telemetria.py 2>/dev/null; then
        echo "  [ok]    $simbolo presente"
    else
        echo "  [FALTA] $simbolo -- deploy desatualizado"
    fi
done
if grep -q 'ciclo_de_vida' /home/hipo/app/api/main.py 2>/dev/null; then
    echo "  [ok]    lifespan ciclo_de_vida presente em main.py"
else
    echo "  [FALTA] lifespan ausente em main.py -- deploy desatualizado"
fi
echo "  -- limiares que estao rodando:"
grep -E '^(LOTE_DESCARGA|IDADE_MAXIMA_S|INTERVALO_DESCARGA_S|LIMITE_BUFFER) *=' \
    /home/hipo/app/api/middleware/telemetria.py 2>/dev/null | sed 's/^/    /'

printf '\n==== FIM ====\n'
