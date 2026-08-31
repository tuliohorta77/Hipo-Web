#!/usr/bin/env bash
# =====================================================================
# HIPO - Apaga de uso_eventos a varredura da internet ja gravada.
#
# POR QUE PRECISA EXISTIR
#
# O filtro `eh_ruido_externo` impede linhas NOVAS. Ele nao volta no tempo: os
# 1104 eventos de varredura gravados entre 20 e 31/08 continuam na tabela, e
# o fechamento LE a tabela.
#
# O ensaio a seco de 31/08 mostrou o efeito, fechando 30/08:
#
#     "acoes": 102, "pessoas_ativas": 0, "erros": 102,
#     "taxa_erro_pct": 100.0,
#     "rotas_mais_usadas": [ {"rota": "<sem_rota>", "acoes": 93}, ... ]
#
# O primeiro e-mail fecharia 31/08, que tem ruido da manha (antes do deploy)
# e dado limpo da tarde. Relatorio que estreia com taxa de erro inventada e
# relatorio que ninguem abre no segundo dia.
#
# O QUE ELE APAGA
#
# Exatamente o mesmo criterio do filtro no middleware, nem um a mais:
#
#     usuario_id IS NULL AND rota = '<sem_rota>'
#
# Nao toca em 401 de sessao expirada (tem rota), nem em 404 de gente
# autenticada (tem usuario), nem em login.
#
# USO -- por padrao SO MOSTRA. Nada e apagado sem --confirmar:
#   scp -i "$HOME/Downloads/chave-hipo.pem" \
#       infra/limpar-ruido-telemetria.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/limpar-ruido-telemetria.sh'
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/limpar-ruido-telemetria.sh --confirmar'
# =====================================================================
set -o pipefail

CONFIRMAR=0
[ "$1" = "--confirmar" ] && CONFIRMAR=1

CRITERIO="usuario_id IS NULL AND rota = '<sem_rota>'"
CARIMBO=$(date +%Y%m%d-%H%M%S)
CSV="/tmp/uso_eventos_ruido_${CARIMBO}.csv"

titulo() { printf '\n==== %s ====\n' "$1"; }
parar()  { printf '\n!! %s\n' "$1"; exit 1; }

D=$(sudo sed -n 's/^DATABASE_URL=//p' /home/hipo/app/.env)
[ -n "$D" ] || parar "DATABASE_URL vazia."
echo "banco: $(echo "$D" | sed 's/:[^:@]*@/:****@/')"

titulo "1. O que sai, e o que fica"
psql "$D" -c "select
                case when $CRITERIO then 'SAI (varredura)'
                     when usuario_id is null then 'fica (anonima com rota)'
                     else 'fica (identificada)' end as destino,
                count(*) as eventos,
                min(criado_em)::date as de, max(criado_em)::date as ate
              from uso_eventos group by 1 order by 2 desc;" || parar "consulta falhou"

titulo "2. Por dia, o antes e o depois"
psql "$D" -c "select (criado_em at time zone 'America/Sao_Paulo')::date as dia,
                     count(*) as hoje_tem,
                     count(*) filter (where not ($CRITERIO)) as vai_ficar,
                     count(distinct usuario_id) as pessoas
              from uso_eventos
              group by 1 order by 1 desc limit 14;" || parar "consulta falhou"

if [ $CONFIRMAR -eq 0 ]; then
    cat <<'FIM'

==== NADA FOI APAGADO ====

Isto foi so a previsao. Confira a coluna `vai_ficar`: ela e o que o relatorio
vai enxergar depois da limpeza. Dia de fim de semana caindo para 0 e o
resultado certo -- ninguem trabalhou.

Para valer, com export em CSV antes do DELETE:

    bash /tmp/limpar-ruido-telemetria.sh --confirmar

FIM
    exit 0
fi

titulo "3. Export em CSV antes de apagar"
# A regra do projeto pede export antes de migration destrutiva. Isto e um
# DELETE de linhas, nao um DROP, mas o custo de exportar 1104 linhas e zero e
# o custo de descobrir depois que fazia falta nao e.
psql "$D" -v ON_ERROR_STOP=1 \
    -c "\copy (select * from uso_eventos where $CRITERIO order by criado_em) to '$CSV' with (format csv, header true)" \
    || parar "export falhou -- NADA foi apagado"
gzip -f "$CSV" || parar "gzip falhou -- NADA foi apagado"
ls -lh "${CSV}.gz" | sed 's/^/  /'
LINHAS=$(zcat "${CSV}.gz" | wc -l)
echo "  $((LINHAS - 1)) linha(s) exportada(s), fora o cabecalho"
[ "$LINHAS" -gt 1 ] || parar "o CSV saiu vazio -- NADA foi apagado"

titulo "4. DELETE"
psql "$D" -v ON_ERROR_STOP=1 \
    -c "with removidos as (delete from uso_eventos where $CRITERIO returning 1)
        select count(*) as apagados from removidos;" || parar "delete falhou"

titulo "5. Como a tabela ficou"
psql "$D" -c "select (criado_em at time zone 'America/Sao_Paulo')::date as dia,
                     count(*) as eventos,
                     count(distinct usuario_id) as pessoas,
                     count(*) filter (where status >= 400) as erros
              from uso_eventos
              group by 1 order by 1 desc limit 14;"
psql "$D" -Atc "select 'restou ' || count(*) || ' evento(s) de varredura (esperado: 0)'
                  from uso_eventos where $CRITERIO;"

cat <<FIM

==== PRONTO ====

O backup ficou em ${CSV}.gz -- no /tmp, que a maquina limpa sozinha. Se
quiser guardar, traga antes:

    scp -i "\$HOME/Downloads/chave-hipo.pem" \\
        ec2-user@63.179.88.212:${CSV}.gz .

FIM
