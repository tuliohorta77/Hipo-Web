#!/usr/bin/env bash
#
# HIPO -- regera api/schema.sql a partir de um banco com TODAS as migrations
# aplicadas. O schema.sql e snapshot (consulta e emergencia); a fonte de
# verdade e api/migrations/.
#
# Nunca aponte para producao: o pg_dump e so leitura, mas o fluxo abaixo
# comeca apagando o schema do banco de trabalho.
#
# Em banco local descartavel, da raiz do repositorio:
#   export DATABASE_URL=postgresql://hipo_test:hipo_test@localhost:5432/hipo_test
#   psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public"
#   (cd api && python -m scripts.aplicar_migrations)
#   bash api/scripts/gerar_schema_snapshot.sh
#
# O resultado e pg_dump puro: perde os comentarios do schema.sql escrito a
# mao. Para manter a versao comentada, espelhe a migration nela; o CI
# avisa se as duas divergirem (scripts/comparar_schema.py).
#
# Sem Postgres local (Windows): o job "Backend Tests" do CI publica o
# snapshot gerado como artefato "schema-snapshot" a cada run -- baixar e
# copiar por cima de api/schema.sql.
#
# ASCII puro.

set -euo pipefail

: "${DATABASE_URL:?defina DATABASE_URL (banco de trabalho, nunca producao)}"
case "$DATABASE_URL" in
    *amazonaws.com*|*hipo-db*)
        echo "ERRO: DATABASE_URL aponta para o RDS. Use um banco descartavel." >&2
        exit 1 ;;
esac

DESTINO="${1:-api/schema.sql}"
ULTIMA="$(psql "$DATABASE_URL" -At -c "SELECT max(nome) FROM schema_migrations")"
[ -n "$ULTIMA" ] || { echo "ERRO: schema_migrations vazia -- rode o aplicar_migrations antes." >&2; exit 1; }

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

{
    echo "-- ============================================================================"
    echo "-- HIPO -- schema.sql  (SNAPSHOT GERADO -- NAO EDITAR A MAO)"
    echo "--"
    echo "-- Fonte de verdade: a sequencia em api/migrations/. CI e deploy aplicam as"
    echo "-- migrations em ordem (api/scripts/aplicar_migrations.py); este arquivo so"
    echo "-- serve para consulta rapida e restauracao de emergencia."
    echo "--"
    echo "-- Gerado por api/scripts/gerar_schema_snapshot.sh"
    echo "-- Ultima migration incluida: $ULTIMA"
    echo "-- ============================================================================"
    echo
    # \restrict/\unrestrict (pg_dump 16.10+/17.6+) trazem chave aleatoria a
    # cada execucao; SET transaction_timeout (pg_dump 17) quebra no PG 15 do
    # RDS e do CI. Os dois saem, para o snapshot so mudar quando o schema muda.
    pg_dump "$DATABASE_URL" \
        --schema-only \
        --no-owner \
        --no-privileges \
        --exclude-table=schema_migrations \
      | grep -v -E '^(\\(restrict|unrestrict) |SET transaction_timeout)'
} > "$TMP"

mv "$TMP" "$DESTINO"
trap - EXIT
echo "snapshot gravado em $DESTINO (ate $ULTIMA)"
