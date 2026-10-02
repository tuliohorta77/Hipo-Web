"""
HIPO — Backfill do scorecard: avalia as reuniões que já tinham transcrição.

O timer (scripts/coletar_transcricoes.py) só avalia reuniões dos últimos
3 dias, de propósito: ninguém quer uma conta de IA aparecendo sozinha no
dia do deploy. As reuniões de antes entram por aqui, numa decisão
explícita.

USO
  cd /home/hipo/app/api
  python3 -m scripts.avaliar_reunioes --desde 2026-09-01             # só lista
  python3 -m scripts.avaliar_reunioes --desde 2026-09-01 --aplicar   # avalia
  python3 -m scripts.avaliar_reunioes --desde 2026-09-01 --aplicar --refazer
  python3 -m scripts.avaliar_reunioes --desde 2026-09-01 --aplicar --limite 5

SEM --aplicar NADA É GRAVADO NEM ENVIADO À IA: só mostra a lista. Com --refazer, reavalia também as prontas — nunca as
validadas pela gestão.

IDEMPOTENTE. Rodar de novo sem --refazer só pega o que ainda não tem
avaliação pronta (as que deram erro, por exemplo).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from uuid import UUID

import asyncpg

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])  # permite rodar de api/

from config import settings  # noqa: E402
from services import avaliacao_roteiro  # noqa: E402
from services import coleta_avaliacao  # noqa: E402
from services.tarefa import FUSO_OPERACAO  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("hipo.avaliar_reunioes")


async def _descricao(conn, reuniao_id: UUID) -> str:
    r = await conn.fetchrow(
        """
        SELECT t.prazo, u.nome AS vendedor,
               COALESCE(c.nome_fantasia, c.razao_social) AS empresa
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
          LEFT JOIN usuarios u ON u.id = t.responsavel_id
          LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
          LEFT JOIN contas c ON c.id = o.conta_id
         WHERE r.id = $1
        """,
        reuniao_id,
    )
    quando = r["prazo"].astimezone(FUSO_OPERACAO).strftime("%d/%m %H:%M")
    return f"{quando}  {(r['vendedor'] or '-')[:22]:<22}  {(r['empresa'] or '-')[:40]}"


async def executar(desde: date, aplicar: bool, refazer: bool, limite: int | None) -> int:
    if aplicar and not avaliacao_roteiro.configurado():
        log.error("ANTHROPIC_API_KEY vazia: nada a fazer.")
        return 1

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        ids = await coleta_avaliacao.elegiveis_desde(conn, desde, refazer=refazer)
        if limite is not None:
            ids = ids[:limite]
        print(f"{len(ids)} reuniao(oes) elegivel(is) desde {desde.isoformat()}"
              f"{' (refazendo as prontas)' if refazer else ''}; "
              f"modelo {avaliacao_roteiro.modelo()}")

        if not aplicar:
            for rid in ids:
                print(f"  {await _descricao(conn, rid)}")
            print("Ensaio: nada foi enviado a IA. Rode com --aplicar para avaliar.")
            return 0

        ok = erros = 0
        notas: list[int] = []
        for n, rid in enumerate(ids, start=1):
            desc = await _descricao(conn, rid)
            try:
                estado = await coleta_avaliacao.avaliar(conn, rid)
            except (coleta_avaliacao.AvaliacaoIndisponivel,
                    coleta_avaliacao.EmAndamento) as e:
                print(f"[{n}/{len(ids)}] {desc}  PULADA: {e}")
                continue
            except Exception:
                erros += 1
                log.exception("reuniao %s: falha inesperada", rid)
                continue
            if estado.get("erro") and estado["status"] != "pronta":
                erros += 1
                print(f"[{n}/{len(ids)}] {desc}  ERRO: {estado['erro']}")
                continue
            ok += 1
            notas.append(estado["nota_total"])
            print(f"[{n}/{len(ids)}] {desc}  {estado['nota_total']:>2}/20")

        media = f"{sum(notas) / len(notas):.1f}" if notas else "-"
        print(f"Concluido: {ok} avaliada(s), {erros} com erro; media {media}/20")
        return 1 if (ids and ok == 0) else 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill do scorecard das reunioes")
    p.add_argument("--desde", type=date.fromisoformat, required=True,
                   help="primeiro dia (AAAA-MM-DD), pela data da reuniao")
    p.add_argument("--aplicar", action="store_true",
                   help="avalia de verdade (sem isto, so lista)")
    p.add_argument("--refazer", action="store_true",
                   help="reavalia tambem as prontas (nunca as validadas)")
    p.add_argument("--limite", type=int, help="no maximo N reunioes nesta rodada")
    a = p.parse_args()
    return asyncio.run(executar(a.desde, a.aplicar, a.refazer, a.limite))


if __name__ == "__main__":
    sys.exit(main())
