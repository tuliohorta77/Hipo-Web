#!/usr/bin/env bash
# Repassa a coleta de transcricoes de TODAS as reunioes desde uma data.
#
# O timer so olha reunioes que terminaram nos ultimos 3 dias (JANELA_TIMER)
# e nunca reavalia as que ja desistiram. Este script faz, reuniao a reuniao,
# a mesma passada do botao "Buscar agora" (coleta.coletar manual=True), que
# reavalia inclusive as indisponiveis, ate o limite de 29 dias da API.
#
# Sem --aplicar: SO DIAGNOSTICO (nao chama o Google, nao grava nada).
#
# Uso (no EC2, como ec2-user -- mesmo usuario do hipo-transcricoes.service):
#   bash repassar-transcricoes.sh 2026-09-24
#   bash repassar-transcricoes.sh 2026-09-24 --aplicar
set -euo pipefail

DESDE="${1:-2026-09-24}"
APLICAR="${2:-}"
ENV_FILE="${ENV_FILE:-/home/hipo/app/.env}"
API_DIR="/home/hipo/app/api"

if [ ! -r "$ENV_FILE" ]; then
  echo "ERRO: $ENV_FILE nao e legivel por $(whoami). Rode como ec2-user." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

cd "$API_DIR"
export PYTHONPATH="$API_DIR"
export PYTHONUNBUFFERED=1

/usr/bin/python3 - "$DESDE" "$APLICAR" <<'PYCODE'
import asyncio
import logging
import sys
from datetime import date, datetime, timezone

import asyncpg

from config import settings
from services import coleta_transcricao as coleta
from services import google_meet, resumo_reuniao
from services import transcricao as regras

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

DESDE = date.fromisoformat(sys.argv[1])
APLICAR = sys.argv[2] == "--aplicar"

SQL = """
SELECT r.id,
       to_char(t.prazo AT TIME ZONE 'America/Sao_Paulo', 'MM-DD HH24:MI') AS quando,
       u.nome AS anfitriao, coalesce(u.cargo, '?') AS cargo,
       coalesce(tr.sigla, '--') AS tipo, r.modalidade,
       coalesce(r.desfecho, CASE WHEN t.concluida_em IS NOT NULL THEN 'concluida*'
                                 WHEN t.cancelada_em IS NOT NULL THEN 'cancelada*'
                                 ELSE 'aberta' END) AS desfecho,
       r.desfecho AS desfecho_bruto, t.cancelada_em,
       left(coalesce(c.razao_social, cp.razao_social, ''), 26) AS empresa,
       r.google_link, r.link_video, r.google_erro,
       r.transcricao_auto_em, r.transcricao_auto_erro,
       x.status AS tr_status, x.motivo AS tr_motivo, x.erro AS tr_erro
  FROM reunioes r
  JOIN tarefas t             ON t.id = r.tarefa_id
  JOIN usuarios u            ON u.id = t.responsavel_id
  LEFT JOIN tipos_reuniao tr ON tr.id = r.tipo_id
  LEFT JOIN oportunidades o  ON o.id = t.oportunidade_id
  LEFT JOIN contas c         ON c.id = o.conta_id
  LEFT JOIN contas cp        ON cp.id = t.conta_id
  LEFT JOIN reuniao_transcricoes x ON x.reuniao_id = r.id
 WHERE t.prazo >= ($1::date)::timestamp AT TIME ZONE 'America/Sao_Paulo'
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
    if l["cancelada_em"] is not None or l["desfecho_bruto"] in ("cancelada", "no_show"):
        return "nao aconteceu"
    if regras.codigo_meet(l["google_link"], l["link_video"]) is None:
        if l["modalidade"] != "online":
            return "presencial"
        return "sem sala Meet" + (" (google_erro)" if l["google_erro"] else "")
    if l["tr_status"]:
        return l["tr_status"]
    return "nunca buscada"


def elegivel(l) -> bool:
    return situacao(l) in ("aguardando", "indisponivel", "nunca buscada")


def linha(l, s, extra="") -> str:
    auto = "S" if l["transcricao_auto_em"] else ("ERRO" if l["transcricao_auto_erro"] else "N")
    extra = (extra or "").replace("\n", " ")[:95]
    return (f"{l['quando']} | {l['anfitriao'][:18]:18s} | {l['tipo']:2s} | "
            f"{l['desfecho'][:11]:11s} | {l['empresa']:26s} | auto={auto:4s} | {s:20s} | {extra}")


def resumo_por_anfitriao(linhas, titulo):
    print(f"\n== {titulo} ==")
    tab = {}
    for l in linhas:
        k = f"{l['anfitriao']} ({l['cargo']})"
        s = situacao(l)
        tab.setdefault(k, {}).setdefault(s, 0)
        tab[k][s] += 1
    for k, v in tab.items():
        total = sum(v.values())
        partes = ", ".join(f"{s}: {n}" for s, n in sorted(v.items(), key=lambda kv: -kv[1]))
        print(f"{k:34s} total {total:3d} | {partes}")


async def carregar(conn):
    return await conn.fetch(SQL, DESDE)


async def main():
    conn = await asyncpg.connect(dsn_limpo(settings.DATABASE_URL))
    try:
        antes = await carregar(conn)
        print(f"\nReunioes com horario entre {DESDE} e agora: {len(antes)}")
        resumo_por_anfitriao(antes, "ANTES - POR ANFITRIAO")

        alvo = [l for l in antes if elegivel(l)]
        print(f"\n== {len(alvo)} REUNIAO(OES) PARA REPASSAR ==")
        for l in alvo:
            print(linha(l, situacao(l), l["tr_motivo"] or l["tr_erro"] or l["transcricao_auto_erro"]))

        print("\n== FORA DO REPASSE (sem sala Meet / presencial) ==")
        for l in antes:
            if situacao(l) in ("presencial",) or situacao(l).startswith("sem sala Meet"):
                print(linha(l, situacao(l), l["google_erro"] or l["link_video"] or ""))

        if not APLICAR:
            print("\nSIMULACAO: nada foi buscado nem gravado. Rode com --aplicar.")
            return

        if not google_meet.configurado():
            print("ERRO: Google nao configurado (GOOGLE_SA_ARQUIVO).", file=sys.stderr)
            sys.exit(1)

        print(f"\n== REPASSANDO {len(alvo)} ==")
        for l in alvo:
            try:
                est = await coleta.coletar(conn, l["id"], manual=True)
                print(linha(l, est["status"], est.get("erro") or est.get("motivo")))
            except Exception as e:  # uma sala ruim nao para as outras
                print(linha(l, "FALHA", repr(e)))

        if resumo_reuniao.configurado():
            faltam = await conn.fetch(
                """
                SELECT x.reuniao_id FROM reuniao_transcricoes x
                  JOIN reunioes r ON r.id = x.reuniao_id
                  JOIN tarefas t  ON t.id = r.tarefa_id
                 WHERE x.status = 'pronta' AND x.resumo IS NULL
                   AND t.prazo >= ($1::date)::timestamp AT TIME ZONE 'America/Sao_Paulo'
                """,
                DESDE,
            )
            for f in faltam:
                try:
                    await coleta.resumir(conn, f["reuniao_id"])
                except Exception as e:
                    print(f"resumo {f['reuniao_id']}: {e!r}")
            print(f"\nResumos gerados/tentados: {len(faltam)}")

        depois = await carregar(conn)
        resumo_por_anfitriao(depois, "DEPOIS - POR ANFITRIAO")
    finally:
        await conn.close()


asyncio.run(main())
PYCODE
