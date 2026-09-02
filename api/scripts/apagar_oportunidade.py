"""
HIPO — Apaga UMA oportunidade pelo número.

Uso operacional, para tirar do banco registro de teste. Não é rota nem tela:
apagar oportunidade não é operação de produto — o caminho normal é cancelar,
que preserva a trilha.

O QUE SOME JUNTO
  Todas as FKs da oportunidade são ON DELETE CASCADE:
    tarefas, oportunidade_eventos, oportunidade_envolvidos,
    oportunidade_concorrentes
  A CONTA e o CONTATO ficam — são entidades próprias e podem ter outras
  oportunidades. Se a conta de teste também tiver que sair, é outro comando.

ANTES DE APAGAR
  O script grava um backup JSON com a oportunidade e tudo que vai junto, no
  caminho passado em --backup. Sem backup gravado, não apaga.

USO
  python -m scripts.apagar_oportunidade OPP-2026-00001                  # só mostra
  python -m scripts.apagar_oportunidade OPP-2026-00001 --commit         # apaga

  --backup CAMINHO   onde gravar o JSON (default: /tmp/<numero>_backup.json)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import asyncpg


def mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


def serial(v):
    """asyncpg devolve UUID/Decimal/datetime; o json não sabe o que fazer com eles."""
    if isinstance(v, (UUID, Decimal)):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def linhas(rows) -> list[dict]:
    return [{k: serial(v) for k, v in dict(r).items()} for r in rows]


async def executar(args) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL não definida.")

    numero = args.numero.strip().upper()
    destino = Path(args.backup or f"/tmp/{numero.replace('/', '-')}_backup.json")

    print(f"banco   : {mascarar(url)}")
    print(f"alvo    : {numero}")
    print(f"modo    : {'COMMIT (apaga)' if args.commit else 'DRY-RUN (só mostra)'}\n")

    conn = await asyncpg.connect(url)
    try:
        opp = await conn.fetchrow(
            """
            SELECT o.*, c.razao_social, c.cnpj, ct.nome AS contato_nome
            FROM oportunidades o
            JOIN contas c    ON c.id = o.conta_id
            LEFT JOIN contatos ct ON ct.id = o.contato_id
            WHERE o.numero = $1
            """,
            numero,
        )
        if opp is None:
            raise SystemExit(f"{numero} não existe no banco. Nada a fazer.")

        opp_id = opp["id"]
        tarefas = await conn.fetch(
            "SELECT * FROM tarefas WHERE oportunidade_id = $1 ORDER BY prazo", opp_id
        )
        eventos = await conn.fetch(
            "SELECT * FROM oportunidade_eventos WHERE oportunidade_id = $1 ORDER BY criado_em",
            opp_id,
        )
        envolvidos = await conn.fetch(
            """
            SELECT e.papel, u.nome, u.email
            FROM oportunidade_envolvidos e
            JOIN usuarios u ON u.id = e.usuario_id
            WHERE e.oportunidade_id = $1
            """,
            opp_id,
        )
        concorrentes = await conn.fetch(
            "SELECT * FROM oportunidade_concorrentes WHERE oportunidade_id = $1", opp_id
        )
        outras = await conn.fetchval(
            "SELECT count(*) FROM oportunidades WHERE conta_id = $1 AND id <> $2",
            opp["conta_id"], opp_id,
        )

        print(f"conta        : {opp['razao_social']} ({opp['cnpj']})")
        print(f"contato      : {opp['contato_nome'] or '—'}")
        print(f"fase/status  : {opp['fase']} / {opp['status']}")
        print(f"criada em    : {opp['criado_em']:%d/%m/%Y %H:%M}")
        print(f"descrição    : {(opp['descricao'] or '—')[:80]}")
        print()
        print("vai junto (CASCADE):")
        print(f"  tarefas      : {len(tarefas)}")
        print(f"  eventos      : {len(eventos)}")
        print(f"  envolvidos   : {len(envolvidos)}")
        print(f"  concorrentes : {len(concorrentes)}")
        print()
        print(f"a conta FICA — tem outras {outras} oportunidade(s) além desta.")

        backup = {
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "oportunidade": {k: serial(v) for k, v in dict(opp).items()},
            "tarefas": linhas(tarefas),
            "eventos": linhas(eventos),
            "envolvidos": linhas(envolvidos),
            "concorrentes": linhas(concorrentes),
        }
        destino.write_text(json.dumps(backup, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nbackup gravado em {destino}")

        if not args.commit:
            print("\nDRY-RUN: nada foi apagado. Rode de novo com --commit.")
            return

        async with conn.transaction():
            apagadas = await conn.execute(
                "DELETE FROM oportunidades WHERE id = $1", opp_id
            )
        print(f"\nAPAGADA: {numero} ({apagadas}).")
        print("A conta e o contato continuam no banco.")
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Apaga uma oportunidade pelo número.")
    p.add_argument("numero", help="ex.: OPP-2026-00001")
    p.add_argument("--backup", default=None)
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    try:
        asyncio.run(executar(args))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\nFALHOU: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
