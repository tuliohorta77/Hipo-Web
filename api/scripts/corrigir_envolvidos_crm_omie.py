"""
HIPO — Corrige os envolvidos das oportunidades já importadas do CRM Omie.

POR QUE ESTE SCRIPT EXISTE
  A carga do dia 01/09 subiu com a primeira regra combinada: só SDR, e só
  para Gabriel e Kethlleen. Jakeline e Bruno, que são EV de verdade em 43
  oportunidades, ficaram sem nenhuma. Este script acrescenta o que faltou,
  sem recriar nem tocar em mais nada.

O QUE ELE FAZ
  Para cada oportunidade do JSON da carga, localiza a que está no banco pela
  marca `[importado do CRM Omie ... — omie:<chave>]` e insere os envolvidos
  que estiverem faltando. É `ON CONFLICT DO NOTHING`: quem já está, fica.

O QUE ELE NÃO FAZ
  Não remove envolvido nenhum. Se alguém foi atribuído à mão na tela depois
  da carga, continua lá — o script só acrescenta.

USO
  python -m scripts.corrigir_envolvidos_crm_omie            # dry-run
  python -m scripts.corrigir_envolvidos_crm_omie --commit   # grava
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import asyncpg

DEFAULT_JSON = Path(__file__).resolve().parent / "dados" / "crm_omie_ativas_2026-09-01.json"


def mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


async def corrigir(args) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL não definida.")

    dados = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))

    print(f"banco   : {mascarar(url)}")
    print(f"modo    : {'COMMIT' if args.commit else 'DRY-RUN (rollback no fim)'}\n")

    conn = await asyncpg.connect(url)
    acrescentados = Counter()
    ja_tinham = 0
    nao_achadas = []

    try:
        tx = conn.transaction()
        await tx.start()

        emails = {
            e for op in dados["oportunidades"]
            for e in op["envolvidos_sdr"] + op.get("envolvidos_ev", [])
        }
        ids = {}
        for e in emails:
            uid = await conn.fetchval(
                "SELECT id FROM usuarios WHERE lower(email) = lower($1)", e
            )
            if uid is None:
                raise SystemExit(f"Usuário '{e}' não existe no banco.")
            ids[e] = uid

        for op in dados["oportunidades"]:
            papeis = ([(e, "SDR") for e in op["envolvidos_sdr"]]
                      + [(e, "EV") for e in op.get("envolvidos_ev", [])])
            if not papeis:
                continue

            opp_id = await conn.fetchval(
                "SELECT id FROM oportunidades WHERE observacoes LIKE '%' || $1",
                f"— {op['chave']}]",
            )
            if opp_id is None:
                nao_achadas.append(op["chave"])
                continue

            for email, papel in papeis:
                # O status do INSERT diz se a linha entrou ou colidiu.
                r = await conn.execute(
                    """
                    INSERT INTO oportunidade_envolvidos (oportunidade_id, usuario_id, papel)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    opp_id, ids[email], papel,
                )
                if r.endswith(" 1"):
                    acrescentados[f"{email.split('@')[0]} ({papel})"] += 1
                else:
                    ja_tinham += 1

        print("envolvidos acrescentados:")
        for k, v in sorted(acrescentados.items(), key=lambda x: -x[1]):
            print(f"  {k:40s} {v}")
        print(f"\ntotal acrescentado : {sum(acrescentados.values())}")
        print(f"já estavam lá      : {ja_tinham}")
        print(f"oportunidades não encontradas no banco : {len(nao_achadas)}")
        for c in nao_achadas[:10]:
            print("   -", c)
        if len(nao_achadas) > 10:
            print(f"   ... e mais {len(nao_achadas) - 10}")

        if args.commit:
            await tx.commit()
            print("\nCOMMIT feito.")
        else:
            await tx.rollback()
            print("\nDRY-RUN: nada foi gravado. Rode de novo com --commit.")
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Acrescenta os envolvidos que faltaram na carga.")
    p.add_argument("--arquivo", default=str(DEFAULT_JSON))
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    try:
        asyncio.run(corrigir(args))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\nFALHOU: {exc}", file=sys.stderr)
        print("Nada foi gravado.", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
