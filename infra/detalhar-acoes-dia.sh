#!/usr/bin/env bash
# detalhar-acoes-dia.sh - quebra as "acoes" da telemetria (uso_eventos) de um dia
# por pessoa: leituras x escritas, rotas mais chamadas e escritas traduzidas.
#
# Somente leitura (SELECT). Nao altera nada no banco.
#
# Uso (na EC2, como ec2-user):
#   bash detalhar-acoes-dia.sh 2026-09-15
#   bash detalhar-acoes-dia.sh            # sem argumento = ontem em Sao Paulo
#
# ASCII puro, LF. Nao entra no deploy: sobe por scp.

set -euo pipefail

DIA="${1:-$(TZ=America/Sao_Paulo date -d yesterday +%F)}"
APP_DIR=/home/hipo/app
ENV_FILE="$APP_DIR/.env"

if ! [[ "$DIA" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERRO: dia invalido '$DIA' (use AAAA-MM-DD)"
  exit 2
fi

# --- DATABASE_URL -----------------------------------------------------------
if [ -z "${DATABASE_URL:-}" ]; then
  if [ ! -r "$ENV_FILE" ]; then
    echo "ERRO: nao consigo ler $ENV_FILE. Rode como ec2-user (dono do .env)."
    exit 2
  fi
  v="$(grep -E '^[[:space:]]*DATABASE_URL[[:space:]]*=' "$ENV_FILE" | tail -n1 | cut -d= -f2- | tr -d '\r')"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  v="${v#\"}"; v="${v%\"}"; v="${v#\'}"; v="${v%\'}"
  DATABASE_URL="$v"
fi

if [ -z "$DATABASE_URL" ]; then
  echo "ERRO: DATABASE_URL vazio."
  exit 2
fi
export DATABASE_URL

echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"
echo "Dia:   $DIA (America/Sao_Paulo)"
echo

# --- Interpretador com asyncpg ----------------------------------------------
PY=""
tem_asyncpg() { [ -x "$1" ] && "$1" -c 'import asyncpg, zoneinfo' >/dev/null 2>&1; }

for c in "$APP_DIR/venv/bin/python" "$APP_DIR/.venv/bin/python" \
         "$APP_DIR/api/venv/bin/python" "$APP_DIR/api/.venv/bin/python"; do
  if tem_asyncpg "$c"; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  EXEC="$(systemctl cat hipo-api 2>/dev/null | grep -E '^ExecStart=' | head -n1 | sed 's/^ExecStart=[-@+!]*//' | awk '{print $1}' || true)"
  if [ -n "$EXEC" ]; then
    d="$(dirname "$EXEC")"
    for c in "$EXEC" "$d/python" "$d/python3"; do
      if tem_asyncpg "$c"; then PY="$c"; break; fi
    done
  fi
fi

if [ -z "$PY" ]; then
  for c in "$(command -v python3.11 || true)" "$(command -v python3 || true)"; do
    if [ -n "$c" ] && tem_asyncpg "$c"; then PY="$c"; break; fi
  done
fi

if [ -z "$PY" ]; then
  echo "ERRO: nenhum python com asyncpg encontrado (venv do app, ExecStart do hipo-api, python3)."
  exit 2
fi
echo "Python: $PY"
echo

# --- Relatorio ----------------------------------------------------------------
"$PY" - "$DIA" <<'PYEOF'
import asyncio
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg

FUSO = ZoneInfo("America/Sao_Paulo")
LEITURA = {"GET", "HEAD", "OPTIONS"}

RECURSOS = {
    "tarefas": "tarefa", "oportunidades": "oportunidade", "contas": "conta",
    "contatos": "contato", "parceiros": "parceiro", "reunioes": "reuniao",
    "agendamentos": "agendamento", "agenda": "agenda", "anexos": "anexo",
    "comentarios": "comentario", "usuarios": "usuario", "propostas": "proposta",
    "eventos": "evento", "notas": "nota", "perfil": "perfil",
}
ACOES_FINAIS = {
    "concluir": "conclui", "cancelar": "cancela", "reabrir": "reabre",
    "finalizar": "finaliza", "fase": "muda fase de", "status": "muda status de",
    "mover": "move", "reagendar": "reagenda", "desfecho": "registra desfecho de",
    "responsavel": "troca responsavel de", "senha": "troca senha de",
}
VERBOS = {"POST": "cria", "PUT": "edita", "PATCH": "edita", "DELETE": "exclui"}


def traduzir(metodo, rota):
    if rota == "/auth/login":
        return "login"
    partes = [p for p in (rota or "").strip("/").split("/") if p]
    if not partes:
        return f"{metodo} {rota}"
    ult = partes[-1]
    recurso = None
    for p in reversed(partes):
        if not p.startswith("{") and p in RECURSOS:
            recurso = RECURSOS[p]
            break
    if recurso is None:
        fixos = [p for p in partes if not p.startswith("{")]
        recurso = fixos[-1] if fixos else rota
    if not ult.startswith("{"):
        if ult in ACOES_FINAIS:
            return f"{ACOES_FINAIS[ult]} {recurso}"
        if ult not in RECURSOS:
            return f"{metodo.lower()} '{ult}' em {recurso}"
    return f"{VERBOS.get(metodo, metodo.lower())} {recurso}"


def escolher(cols, candidatos):
    for c in candidatos:
        if c in cols:
            return c
    return None


async def colunas(conn, tabela):
    rows = await conn.fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = $1",
        tabela,
    )
    return {r["column_name"]: r["data_type"] for r in rows}


def hhmm(ts):
    if ts is None:
        return "--:--"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(FUSO).strftime("%H:%M")


async def main():
    dia = date.fromisoformat(sys.argv[1])
    ini = datetime.combine(dia, time(0), FUSO).astimezone(timezone.utc)
    fim = datetime.combine(dia + timedelta(days=1), time(0), FUSO).astimezone(timezone.utc)

    url = os.environ["DATABASE_URL"]
    for pref in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(pref):
            url = "postgresql://" + url[len(pref):]

    conn = await asyncpg.connect(url)
    try:
        ev = await colunas(conn, "uso_eventos")
        if not ev:
            print("ERRO: tabela uso_eventos nao encontrada.")
            sys.exit(3)

        c_ts = escolher(ev, ["criado_em", "ocorrido_em", "registrado_em", "em", "created_at", "timestamp"])
        c_met = escolher(ev, ["metodo", "method", "http_metodo"])
        c_rota = escolher(ev, ["rota", "rota_template", "path", "endpoint"])
        c_st = escolher(ev, ["status", "status_code", "http_status"])
        c_uid = escolher(ev, ["usuario_id", "user_id"])
        c_mail = escolher(ev, ["email", "usuario_email"])
        c_cargo = escolher(ev, ["cargo", "cargo_no_evento"])

        faltando = [n for n, c in (("data", c_ts), ("metodo", c_met), ("rota", c_rota), ("status", c_st)) if c is None]
        if faltando:
            print(f"ERRO: nao identifiquei as colunas {faltando} em uso_eventos.")
            print("Colunas existentes:", ", ".join(sorted(ev)))
            sys.exit(3)

        us = await colunas(conn, "usuarios")
        u_nome = escolher(us, ["nome", "name"])
        u_mail = escolher(us, ["email"])

        join = ""
        rotulo = []
        if c_uid and "id" in us:
            join = f"LEFT JOIN usuarios u ON u.id = e.{c_uid}"
        elif c_mail and u_mail:
            join = f"LEFT JOIN usuarios u ON lower(u.{u_mail}) = lower(e.{c_mail})"
        if join and u_nome:
            rotulo.append(f"u.{u_nome}")
        if c_mail:
            rotulo.append(f"e.{c_mail}")
        elif join and u_mail:
            rotulo.append(f"u.{u_mail}")
        rotulo_sql = "COALESCE(" + ", ".join(rotulo + ["'(anonimo)'"]) + ")"
        cargo_sql = f"e.{c_cargo}" if c_cargo else "NULL"

        p_ini, p_fim = ini, fim
        if ev[c_ts] == "timestamp without time zone":
            p_ini, p_fim = ini.replace(tzinfo=None), fim.replace(tzinfo=None)

        sql = f"""
            SELECT {rotulo_sql} AS pessoa, {cargo_sql} AS cargo,
                   upper(e.{c_met}) AS metodo, e.{c_rota} AS rota,
                   e.{c_st} AS status, e.{c_ts} AS em
            FROM uso_eventos e
            {join}
            WHERE e.{c_ts} >= $1 AND e.{c_ts} < $2
            ORDER BY e.{c_ts}
        """
        rows = await conn.fetch(sql, p_ini, p_fim)
    finally:
        await conn.close()

    print(f"Colunas usadas: data={c_ts} metodo={c_met} rota={c_rota} status={c_st} "
          f"usuario={c_uid or c_mail or '-'} cargo={c_cargo or '-'}")
    print(f"Eventos no dia: {len(rows)}")
    print()

    por = defaultdict(list)
    for r in rows:
        por[r["pessoa"]].append(r)

    ordem = sorted(por, key=lambda p: -len(por[p]))

    print("=" * 96)
    print(f"{'Pessoa':<28}{'Cargo':<8}{'Total':>7}{'Leit.':>7}{'Escr.':>7}{'Erros':>7}{'Rotas':>7}{'Entrada':>9}{'Saida':>8}")
    print("-" * 96)
    for p in ordem:
        ev_p = por[p]
        leit = sum(1 for r in ev_p if r["metodo"] in LEITURA)
        erros = sum(1 for r in ev_p if (r["status"] or 0) >= 400)
        rotas = len({(r["metodo"], r["rota"]) for r in ev_p})
        cargo = next((r["cargo"] for r in ev_p if r["cargo"]), "-")
        print(f"{str(p)[:27]:<28}{str(cargo)[:7]:<8}{len(ev_p):>7}{leit:>7}{len(ev_p) - leit:>7}"
              f"{erros:>7}{rotas:>7}{hhmm(ev_p[0]['em']):>9}{hhmm(ev_p[-1]['em']):>8}")
    print("=" * 96)
    print("Leit. = GET/HEAD/OPTIONS | Escr. = POST/PUT/PATCH/DELETE | Erros = status >= 400")
    print()

    for p in ordem:
        ev_p = por[p]
        print("#" * 96)
        print(f"# {p}  ({len(ev_p)} eventos)")
        print("#" * 96)

        escritas = [r for r in ev_p if r["metodo"] not in LEITURA]
        ok = Counter((r["metodo"], r["rota"]) for r in escritas if (r["status"] or 0) < 400)
        falhas = Counter((r["metodo"], r["rota"], r["status"]) for r in escritas if (r["status"] or 0) >= 400)

        print(f"\n  ESCRITAS COM SUCESSO ({sum(ok.values())}) - o que a pessoa lancou/alterou")
        if ok:
            resumo = Counter()
            for (m, rota), n in ok.items():
                resumo[traduzir(m, rota)] += n
            for acao, n in resumo.most_common():
                print(f"    {n:>5}  {acao}")
            print("    detalhe por rota:")
            for (m, rota), n in ok.most_common():
                print(f"    {n:>5}  {m:<7}{rota}")
        else:
            print("    (nenhuma)")

        if falhas:
            print(f"\n  ESCRITAS COM ERRO ({sum(falhas.values())})")
            for (m, rota, st), n in falhas.most_common():
                print(f"    {n:>5}  {m:<7}{rota}  -> {st}")

        leit = Counter(r["rota"] for r in ev_p if r["metodo"] in LEITURA)
        print(f"\n  LEITURAS ({sum(leit.values())}) - top 10 rotas")
        for rota, n in leit.most_common(10):
            print(f"    {n:>5}  GET    {rota}")
        resto = sum(leit.values()) - sum(n for _, n in leit.most_common(10))
        if resto:
            print(f"    {resto:>5}  (demais {len(leit) - 10} rotas)")

        horas = Counter(hhmm(r["em"])[:2] for r in ev_p)
        print("\n  EVENTOS POR HORA")
        pico = max(horas.values())
        for h in sorted(horas):
            barra = "#" * max(1, round(horas[h] * 50 / pico))
            print(f"    {h}h {horas[h]:>5}  {barra}")
        print()


asyncio.run(main())
PYEOF
