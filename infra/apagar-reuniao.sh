#!/usr/bin/env bash
# Apaga UMA reuniao do HIPO (tarefa + registro em `reunioes`), para limpar
# teste que polui os numeros do Monitor.
#
# Identifica pela OPORTUNIDADE + DIA (fuso de Sao Paulo) e, opcional, HORA.
# So apaga quando sobra exatamente uma reuniao/visita. Apagar a tarefa leva
# junto, por ON DELETE CASCADE: reunioes, reuniao_participantes e
# tarefa_anexos. Tarefas que nasceram DELA (tarefa_anterior_id) ficam, com
# o vinculo zerado -- a nao ser que se passe --com-proximas.
#
# Antes de apagar, imprime o JSON completo das linhas (copia de seguranca
# na propria saida do terminal).
#
# Uso (no EC2):
#   sudo bash apagar-reuniao.sh OPP-2026-04498 2026-09-23 [10:00]              # SIMULA
#   sudo bash apagar-reuniao.sh OPP-2026-04498 2026-09-23 10:00 --aplicar
#   sudo bash apagar-reuniao.sh OPP-2026-04498 2026-09-23 10:00 --aplicar --com-proximas
set -euo pipefail

ENV_FILE="${ENV_FILE:-/home/hipo/app/.env}"
if [ -z "${DATABASE_URL:-}" ]; then
  if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  else
    echo "ERRO: DATABASE_URL nao esta no ambiente e $ENV_FILE nao e legivel (rode com sudo)." >&2
    exit 1
  fi
fi
echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

PY=""
for candidato in /home/hipo/app/.venv/bin/python /home/hipo/app/venv/bin/python /usr/bin/python3 python3; do
  if [ -x "$candidato" ] || command -v "$candidato" >/dev/null 2>&1; then
    if "$candidato" -c 'import asyncpg' >/dev/null 2>&1; then PY="$candidato"; break; fi
  fi
done
[ -n "$PY" ] || { echo "ERRO: nao achei um python com asyncpg." >&2; exit 1; }

"$PY" - "$@" <<'PYCODE'
import asyncio
import json
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import asyncpg

TZ = "America/Sao_Paulo"
SP = ZoneInfo(TZ)


def dsn_limpo(url: str) -> str:
    for p in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(p):
            return "postgresql://" + url[len(p):]
    return url


def js(row) -> str:
    return json.dumps(dict(row), default=str, ensure_ascii=False)


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    aplicar = "--aplicar" in sys.argv
    com_proximas = "--com-proximas" in sys.argv
    if len(args) < 2:
        print("Uso: apagar-reuniao.sh NUMERO_OPORTUNIDADE AAAA-MM-DD [HH:MM] [--aplicar] [--com-proximas]")
        return 1
    numero, dia = args[0], date.fromisoformat(args[1])
    hora = args[2] if len(args) > 2 else None

    conn = await asyncpg.connect(dsn_limpo(os.environ["DATABASE_URL"]))
    try:
        opp = await conn.fetchrow(
            """
            SELECT o.id, o.numero, o.status, o.fase,
                   COALESCE(c.nome_fantasia, c.razao_social) AS empresa
              FROM oportunidades o JOIN contas c ON c.id = o.conta_id
             WHERE o.numero = $1
            """,
            numero,
        )
        if opp is None:
            print(f"ERRO: oportunidade {numero} nao existe.")
            return 1
        print(f"Oportunidade: {opp['numero']} - {opp['empresa']} ({opp['fase']}/{opp['status']})")

        filtro_hora = ""
        params = [opp["id"], dia]
        if hora:
            filtro_hora = f" AND to_char(t.prazo AT TIME ZONE '{TZ}', 'HH24:MI') = $3"
            params.append(hora)
        cands = await conn.fetch(
            f"""
            SELECT t.id, t.tipo, t.titulo, t.prazo, t.concluida_em, t.cancelada_em,
                   u.nome AS responsavel, cr.nome AS criado_por_nome,
                   r.id AS reuniao_id, r.desfecho, r.google_event_id
              FROM tarefas t
              LEFT JOIN reunioes r  ON r.tarefa_id = t.id
              LEFT JOIN usuarios u  ON u.id = t.responsavel_id
              LEFT JOIN usuarios cr ON cr.id = t.criado_por
             WHERE t.oportunidade_id = $1
               AND t.tipo IN ('reuniao', 'visita')
               AND (t.prazo AT TIME ZONE '{TZ}')::date = $2
               {filtro_hora}
             ORDER BY t.prazo
            """,
            *params,
        )
        for c in cands:
            estado = c["desfecho"] or ("concluida" if c["concluida_em"] else
                                       "cancelada" if c["cancelada_em"] else "aberta")
            print(f"  {c['prazo'].astimezone(SP):%d/%m %H:%M}  {c['tipo']}  resp={c['responsavel']}  "
                  f"criada por={c['criado_por_nome']}  estado={estado}  titulo={c['titulo']!r}")
        if len(cands) != 1:
            print(f"\nAchei {len(cands)} reunioes -- preciso de exatamente 1. "
                  "Informe a HORA para desempatar. Nada foi apagado.")
            return 1
        alvo = cands[0]

        proximas = await conn.fetch(
            """
            SELECT t.*, u.nome AS responsavel
              FROM tarefas t LEFT JOIN usuarios u ON u.id = t.responsavel_id
             WHERE t.tarefa_anterior_id = $1
            """,
            alvo["id"],
        )
        anexos = await conn.fetchval(
            "SELECT count(*) FROM tarefa_anexos WHERE tarefa_id = $1", alvo["id"]
        )
        print()
        print(f"Tarefas criadas A PARTIR dela (proxima): {len(proximas)}")
        for p in proximas:
            print(f"  {p['prazo'].astimezone(SP):%d/%m %H:%M}  {p['tipo']}  {p['titulo']!r}  resp={p['responsavel']}"
                  + ("  -> SERA APAGADA" if com_proximas else "  -> fica (vinculo zerado)"))
        if anexos:
            print(f"ATENCAO: {anexos} anexo(s) no S3 ficam orfaos (a linha some, o arquivo nao).")
        if alvo["google_event_id"]:
            print("ATENCAO: a reuniao tem evento no Google Calendar -- apague o evento na agenda a mao.")

        print("\n--- COPIA DE SEGURANCA (JSON) ---")
        print("tarefa:", js(await conn.fetchrow("SELECT * FROM tarefas WHERE id = $1", alvo["id"])))
        if alvo["reuniao_id"]:
            print("reuniao:", js(await conn.fetchrow("SELECT * FROM reunioes WHERE id = $1", alvo["reuniao_id"])))
            for p in await conn.fetch(
                "SELECT * FROM reuniao_participantes WHERE reuniao_id = $1", alvo["reuniao_id"]
            ):
                print("participante:", js(p))
        if com_proximas:
            for p in proximas:
                print("proxima:", js(p))
        print("--- FIM DA COPIA ---\n")

        if not aplicar:
            print("SIMULACAO: nada foi apagado. Rode com --aplicar para apagar.")
            return 0

        async with conn.transaction():
            if com_proximas and proximas:
                await conn.execute(
                    "DELETE FROM tarefas WHERE id = ANY($1::uuid[])", [p["id"] for p in proximas]
                )
            status = await conn.execute("DELETE FROM tarefas WHERE id = $1", alvo["id"])
            if status != "DELETE 1":
                raise RuntimeError(f"esperava apagar 1 tarefa, veio: {status}")
        print("OK: reuniao apagada" + (f" junto com {len(proximas)} proxima(s)." if com_proximas and proximas else "."))
        return 0
    finally:
        await conn.close()


sys.exit(asyncio.run(main()))
PYCODE
