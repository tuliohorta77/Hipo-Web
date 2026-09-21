#!/usr/bin/env bash
# Agendamentos CRIADOS na janela, por pessoa que agendou.
#
# Diferença para a tela Agenda -> Produtividade:
#   a tela recorta pela semana da GRADE (reuniões que acontecem na semana)
#   e depois agrupa por quem marcou. Este script recorta por reunioes.criado_em
#   — ou seja, o trabalho de agendar feito DENTRO da janela, mesmo que a reunião
#   tenha sido marcada para daqui a três semanas.
#
# Uso (no EC2, como usuário hipo):
#   bash agendamentos-criados-na-semana.sh                      # semana corrente (seg a dom, hora de Brasília)
#   bash agendamentos-criados-na-semana.sh 2026-09-14 2026-09-20
#   bash agendamentos-criados-na-semana.sh 2026-09-01 2026-09-21
#
# Só lê. Nenhuma escrita no banco.
set -euo pipefail

DE="${1:-}"
ATE="${2:-}"

ENV_FILE="${ENV_FILE:-/home/hipo/app/.env}"

if [ -z "${DATABASE_URL:-}" ]; then
  if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  else
    echo "ERRO: DATABASE_URL não está no ambiente e $ENV_FILE não é legível." >&2
    echo "      Rode como o usuário hipo (sudo -iu hipo) ou exporte DATABASE_URL." >&2
    exit 1
  fi
fi

# Confirma contra qual banco vai rodar, com a senha mascarada.
echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

PY=""
for candidato in /home/hipo/app/.venv/bin/python /home/hipo/app/venv/bin/python /usr/bin/python3 python3; do
  if [ -x "$candidato" ] || command -v "$candidato" >/dev/null 2>&1; then
    if "$candidato" -c 'import asyncpg' >/dev/null 2>&1; then
      PY="$candidato"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "ERRO: não achei um python com asyncpg. Tente: sudo -iu hipo /home/hipo/app/.venv/bin/python -c 'import asyncpg'" >&2
  exit 1
fi

"$PY" - "$DE" "$ATE" <<'PYCODE'
import asyncio
import os
import sys
from datetime import date

import asyncpg

TZ = "America/Sao_Paulo"
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


def dsn_limpo(url: str) -> str:
    for prefixo in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefixo):
            return "postgresql://" + url[len(prefixo):]
    return url


async def colunas(conn, tabela: str) -> dict:
    linhas = await conn.fetch(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        tabela,
    )
    return {r["column_name"]: r["data_type"] for r in linhas}


def primeira(disponiveis: dict, *candidatas):
    for c in candidatas:
        if c in disponiveis:
            return c
    return None


def tabela_texto(cabecalho, linhas) -> str:
    larguras = [len(str(c)) for c in cabecalho]
    for linha in linhas:
        for i, celula in enumerate(linha):
            larguras[i] = max(larguras[i], len(str(celula)))

    def formata(valores):
        partes = []
        for i, v in enumerate(valores):
            v = str(v)
            partes.append(v.ljust(larguras[i]) if i < 2 else v.rjust(larguras[i]))
        return "  ".join(partes).rstrip()

    saida = [formata(cabecalho), "  ".join("-" * w for w in larguras)]
    saida.extend(formata(l) for l in linhas)
    return "\n".join(saida)


async def main() -> int:
    de = (sys.argv[1] or "").strip() if len(sys.argv) > 1 else ""
    ate = (sys.argv[2] or "").strip() if len(sys.argv) > 2 else ""

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERRO: DATABASE_URL vazio.", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(dsn_limpo(url))
    try:
        cols_r = await colunas(conn, "reunioes")
        if not cols_r:
            print("ERRO: tabela 'reunioes' não encontrada no schema public.", file=sys.stderr)
            return 1

        col_data = primeira(cols_r, "criado_em", "created_at")
        if col_data is None:
            print(f"ERRO: 'reunioes' não tem criado_em. Colunas: {sorted(cols_r)}", file=sys.stderr)
            return 1

        # Crédito do agendamento: agendado_por (migration 012) com queda para criado_por.
        col_credito = primeira(cols_r, "agendado_por", "criado_por", "created_by")
        if col_credito is None:
            print(f"ERRO: 'reunioes' não tem agendado_por nem criado_por. Colunas: {sorted(cols_r)}", file=sys.stderr)
            return 1

        # timestamptz converte direto; timestamp naive está gravado em UTC.
        if cols_r[col_data] == "timestamp with time zone":
            local = f"(r.{col_data} AT TIME ZONE '{TZ}')"
        else:
            local = f"(r.{col_data} AT TIME ZONE 'UTC' AT TIME ZONE '{TZ}')"

        cols_u = await colunas(conn, "usuarios")
        col_nome = primeira(cols_u, "nome", "nome_completo", "name", "email")
        col_cargo = primeira(cols_u, "cargo", "funcao", "role")
        nome_sql = f"coalesce(u.{col_nome}::text, '(usuário ' || b.pessoa_id::text || ')')" if col_nome else "b.pessoa_id::text"
        cargo_sql = f"coalesce(u.{col_cargo}::text, '-')" if col_cargo else "'-'"

        if de and ate:
            try:
                de, ate = date.fromisoformat(de), date.fromisoformat(ate)
            except ValueError:
                print("ERRO: datas devem estar em AAAA-MM-DD.", file=sys.stderr)
                return 1
            if ate < de:
                de, ate = ate, de
        else:
            de, ate = await conn.fetchrow(
                f"""
                SELECT date_trunc('week', (now() AT TIME ZONE '{TZ}'))::date AS inicio,
                       (date_trunc('week', (now() AT TIME ZONE '{TZ}'))::date + 6) AS fim
                """
            )

        print(f"Janela (criação, hora de Brasília): {de} a {ate}")
        print(f"Crédito por: reunioes.{col_credito}    data: reunioes.{col_data} ({cols_r[col_data]})")
        print()

        filtros_dia = ",\n".join(
            f"       count(*) FILTER (WHERE extract(isodow from b.dia) = {i + 1}) AS {d}"
            for i, d in enumerate(DIAS)
        )

        sql = f"""
        WITH base AS (
            SELECT r.{col_credito} AS pessoa_id,
                   {local}::date   AS dia
            FROM reunioes r
            WHERE {local}::date BETWEEN $1::date AND $2::date
        )
        SELECT {nome_sql} AS nome,
               {cargo_sql} AS cargo,
               count(*) AS total,
{filtros_dia}
        FROM base b
        LEFT JOIN usuarios u ON u.id = b.pessoa_id
        GROUP BY b.pessoa_id, 1, 2
        ORDER BY total DESC, nome
        """
        linhas = await conn.fetch(sql, de, ate)

        if not linhas:
            print("Nenhum agendamento criado nessa janela.")
            return 0

        cabecalho = ["nome", "cargo", "total"] + DIAS
        corpo = [[r["nome"], r["cargo"], r["total"]] + [r[d] for d in DIAS] for r in linhas]
        total = sum(r["total"] for r in linhas)
        corpo.append(["TOTAL", "", total] + [sum(r[d] for r in linhas) for d in DIAS])
        print(tabela_texto(cabecalho, corpo))
        print()

        if "desfecho" in cols_r:
            desf = await conn.fetch(
                f"""
                SELECT coalesce(r.desfecho::text, '(sem desfecho)') AS desfecho, count(*) AS qtd
                FROM reunioes r
                WHERE {local}::date BETWEEN $1::date AND $2::date
                GROUP BY 1
                ORDER BY 2 DESC
                """,
                de,
                ate,
            )
            print("Desfecho dessas mesmas reuniões (o desfecho pode cair fora da janela):")
            print(tabela_texto(["desfecho", "", "qtd"], [[d["desfecho"], "", d["qtd"]] for d in desf]))
            print()

        print("CSV")
        print(",".join(cabecalho))
        for r in linhas:
            campos = [str(r["nome"]).replace(",", " "), str(r["cargo"]), str(r["total"])] + [str(r[d]) for d in DIAS]
            print(",".join(campos))
        return 0
    finally:
        await conn.close()


sys.exit(asyncio.run(main()))
PYCODE
