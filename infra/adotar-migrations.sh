#!/usr/bin/env bash
#
# HIPO - adocao das migrations (entrega 049). RODA UMA VEZ SO.
#
# Ate a 048 as migrations eram aplicadas a mao (psql). A partir da 049 o
# deploy do CI aplica as pendentes sozinho, guiado pela tabela
# schema_migrations. Este script registra, SEM EXECUTAR, que as bases ja
# existentes estao na 029 -- e o que impede o deploy de tentar rodar a 001
# (drop do legado) num banco vivo.
#
# ORDEM: este script -> push da 049. Sem a adocao, o primeiro deploy para
# no passo "Aplicar migrations" com erro de trava (nada e deployado, nada
# quebra -- mas fica vermelho ate a adocao).
#
# Rodar NA EC2, como ec2-user, com terminal (ssh -t), com as migrations e o
# script em /tmp/hipo-adotar/ (o deploy-049 manda por scp):
#   bash /tmp/hipo-adotar/adotar-migrations.sh
#
# Faz as duas bases que existirem (principal e MOS). Idempotente: base ja
# adotada e so conferida. Nao altera nenhuma tabela do app; so cria e
# preenche schema_migrations.
#
# ASCII puro.

set -euo pipefail

DIR=/tmp/hipo-adotar
ATE=029
BASES=(
    "principal:/home/hipo/app/.env"
    "mos:/home/hipo/mos/.env"
)

tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }
perguntar() {
    local r
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then return 0; fi
    tem_tty || { echo "ERRO: sem terminal. Use 'ssh -t' ou HIPO_CONFIRMADO=1."; exit 1; }
    read -r -p "$1 [s/N] " r < /dev/tty
    r="$(printf '%s' "$r" | tr -d '\r[:space:]')"
    [ "$r" = "s" ] || [ "$r" = "S" ]
}

[ -f "$DIR/aplicar_migrations.py" ] && [ -d "$DIR/migrations" ] \
    || { echo "ERRO: faltam $DIR/aplicar_migrations.py e $DIR/migrations/. Mande por scp."; exit 1; }

PY="$(systemctl show -p ExecStart --value hipo-api 2>/dev/null | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
PY="${PY:-/usr/bin/python3}"
echo "python da hipo-api: $PY ($("$PY" --version 2>&1))"

migrar() {  # migrar <env_path> <args...>  -- .env por stdin, URL fora do ps
    local env_path="$1"; shift
    sudo cat "$env_path" | "$PY" "$DIR/aplicar_migrations.py" --pasta "$DIR/migrations" --env-file /dev/stdin "$@"
}

for base in "${BASES[@]}"; do
    nome="${base%%:*}"; env_path="${base#*:}"
    echo
    echo "================================================================"
    echo "  base $nome  ($env_path)"
    echo "================================================================"
    if ! sudo test -f "$env_path"; then
        echo "  nao existe nesta EC2 -- pulando"
        continue
    fi

    url="$(sudo cat "$env_path" | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
    [ -n "$url" ] || { echo "ERRO: $env_path sem DATABASE_URL."; exit 1; }
    echo "  banco: $(echo "$url" | sed 's/:[^:@]*@/:****@/')"

    # Duas consultas: num SELECT so, o Postgres resolve o nome da tabela
    # mesmo no ramo do CASE que nao roda -- e quebra quando ela nao existe.
    registros=0
    if [ "$(psql "$url" -At -c "SELECT to_regclass('public.schema_migrations') IS NOT NULL")" = "t" ]; then
        registros="$(psql "$url" -At -c "SELECT count(*) FROM schema_migrations")"
    fi
    if [ "$registros" != "0" ]; then
        echo "  ja adotada ($registros registros) -- so conferindo:"
        migrar "$env_path" --status | tail -3
        continue
    fi

    # Prova barata de que a base esta mesmo na 029: as marcas da 028 e da
    # 029 tem que estar la. Faltando, a adocao mentiria -- e a migration
    # que falta nunca mais rodaria.
    falta="$(psql "$url" -At <<'SQL'
SELECT string_agg(o, ', ') FROM (
  SELECT 'tabela contas' AS o WHERE to_regclass('public.contas') IS NULL
  UNION ALL SELECT 'tabela pdi_acoes (027)' WHERE to_regclass('public.pdi_acoes') IS NULL
  UNION ALL SELECT 'oportunidade_contatos.papel (028)' WHERE NOT EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_name = 'oportunidade_contatos' AND column_name = 'papel')
  UNION ALL SELECT 'tarefas.confirmacao_de (029)' WHERE NOT EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_name = 'tarefas' AND column_name = 'confirmacao_de')
) x
SQL
)"
    if [ -n "$falta" ]; then
        echo "ERRO: a base $nome NAO esta na $ATE -- falta: $falta"
        echo "      Aplique o que falta (infra/aplicar-NNN-*.sh) e rode de novo."
        exit 1
    fi
    echo "  marcas da 027, 028 e 029 presentes"

    if ! perguntar "  Registrar 000..$ATE como ja aplicadas na base $nome (nada e executado)?"; then
        echo "Cancelado."; exit 3
    fi
    migrar "$env_path" --adotar-ate "$ATE"
    migrar "$env_path" --status | tail -1
done

chmod -R u+w "$DIR" 2>/dev/null || true
rm -rf "$DIR"
echo
echo "OK -- bases adotadas. Daqui em diante o deploy do CI aplica as migrations."
