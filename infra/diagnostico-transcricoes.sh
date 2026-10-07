#!/usr/bin/env bash
# Diagnostico (SO LEITURA): por que cada reuniao desde 24/09 tem ou nao
# transcricao. Mostra resumo por anfitriao e o detalhe reuniao a reuniao.
#
# Uso (no EC2):
#   sudo bash diagnostico-transcricoes.sh [AAAA-MM-DD]
set -euo pipefail

DESDE="${1:-2026-09-24}"
ENV_FILE="${ENV_FILE:-/home/hipo/app/.env}"

if [ -z "${DATABASE_URL:-}" ]; then
  if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  else
    echo "ERRO: DATABASE_URL nao esta no ambiente e $ENV_FILE nao e legivel." >&2
    exit 1
  fi
fi

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
  echo "ERRO: nao achei um python com asyncpg." >&2
  exit 1
fi

"$PY" - "$DESDE" <<'PYCODE'
import asyncio
import os
import sys
from datetime import date

import asyncpg

SQL = """
SELECT
    to_char(t.prazo AT TIME ZONE 'America/Sao_Paulo', 'MM-DD HH24:MI') AS quando,
    u.nome                          AS anfitriao,
    coalesce(u.cargo, '?')          AS cargo,
    coalesce(tr.sigla, '--')        AS tipo,
    r.modalidade,
    coalesce(r.desfecho, CASE WHEN t.concluida_em IS NOT NULL THEN 'concluida*'
                              WHEN t.cancelada_em IS NOT NULL THEN 'cancelada*'
                              ELSE 'aberta' END) AS desfecho,
    left(coalesce(c.razao_social, cp.razao_social, ''), 28) AS empresa,
    (r.google_event_id IS NOT NULL) AS tem_evento,
    (r.link_video ILIKE '%meet.google.com%') AS tem_meet,
    r.google_erro,
    r.transcricao_auto_em IS NOT NULL AS auto_ligada,
    r.transcricao_auto_erro,
    x.status                        AS tr_status,
    x.motivo                        AS tr_motivo,
    x.erro                          AS tr_erro,
    x.tentativas
FROM reunioes r
JOIN tarefas t             ON t.id = r.tarefa_id
JOIN usuarios u            ON u.id = t.responsavel_id
LEFT JOIN tipos_reuniao tr ON tr.id = r.tipo_id
LEFT JOIN oportunidades o  ON o.id = t.oportunidade_id
LEFT JOIN contas c         ON c.id = o.conta_id
LEFT JOIN contas cp        ON cp.id = t.conta_id
LEFT JOIN reuniao_transcricoes x ON x.reuniao_id = r.id
WHERE t.prazo >= $1::date AT TIME ZONE 'America/Sao_Paulo'
  AND t.prazo <  NOW()
ORDER BY u.nome, t.prazo
"""


def dsn_limpo(url: str) -> str:
    for prefixo in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefixo):
            return "postgresql://" + url[len(prefixo):]
    return url


def situacao(l) -> str:
    if l["tr_status"] == "pronta":
        return "PRONTA"
    if l["modalidade"] != "online":
        return "presencial"
    if not l["tem_meet"]:
        return "sem link Meet" + (" (google_erro)" if l["google_erro"] else "")
    if l["tr_status"]:
        return l["tr_status"]
    return "sem linha de transcricao"


async def main(desde: str) -> None:
    conn = await asyncpg.connect(dsn_limpo(os.environ["DATABASE_URL"]))
    try:
        async with conn.transaction(readonly=True):
            linhas = await conn.fetch(SQL, date.fromisoformat(desde))
    finally:
        await conn.close()

    print(f"\nReunioes com horario entre {desde} e agora: {len(linhas)}\n")

    resumo = {}
    for l in linhas:
        k = f"{l['anfitriao']} ({l['cargo']})"
        s = situacao(l)
        resumo.setdefault(k, {}).setdefault(s, 0)
        resumo[k][s] += 1
    print("== RESUMO POR ANFITRIAO ==")
    for k, v in resumo.items():
        total = sum(v.values())
        partes = ", ".join(f"{s}: {n}" for s, n in sorted(v.items(), key=lambda kv: -kv[1]))
        print(f"{k:32s} total {total:3d} | {partes}")

    print("\n== DETALHE (so o que NAO esta pronta) ==")
    for l in linhas:
        s = situacao(l)
        if s == "PRONTA":
            continue
        extra = l["tr_motivo"] or l["tr_erro"] or l["transcricao_auto_erro"] or l["google_erro"] or ""
        extra = (extra or "").replace("\n", " ")[:90]
        print(f"{l['quando']} | {l['anfitriao'][:18]:18s} | {l['tipo']:2s} | "
              f"{l['modalidade'][:4]} | {l['desfecho']:11s} | {l['empresa']:28s} | "
              f"auto={'S' if l['auto_ligada'] else 'N'} | {s} | {extra}")


asyncio.run(main(sys.argv[1]))
PYCODE
