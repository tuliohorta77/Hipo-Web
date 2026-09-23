"""
HIPO — Zera o nº de funcionários ESTIMADO, para a fonte nova repreencher.

POR QUE ISTO PRECISA EXISTIR

Trocar a fonte não conserta o que já está no banco. O enriquecimento **não
sobrescreve campo preenchido** — é a regra que protege o trabalho humano, e
ela não sabe distinguir "digitado por alguém" de "herdado de uma fonte que
a gente cancelou". Então a consulta nova chega, vê `num_funcionarios = 3`,
e devolve o número certo como *divergência* em vez de corrigir. O 3 fica
para sempre, a menos que alguém clique em "usar os dados da fonte" conta
por conta.

Nulo é o único estado que o enriquecimento preenche sozinho. Daí o script.

O QUE ELE NUNCA TOCA

`num_funcionarios_origem = 'declarado'`. Esse é o número que o CLIENTE
informou — é ele que precifica, e a distinção declarado × estimado existe
justamente para protegê-lo. O filtro está no WHERE, não numa condição em
Python: o banco recusa a linha errada antes de o script ter chance de
errar.

ANTES DE APAGAR, EXPORTA

Regra do projeto para mudança destrutiva: CSV primeiro. Aqui não é
migration, é UPDATE — mas descarta dado do mesmo jeito, então vale igual.
O CSV sai com conta, CNPJ, o número que estava lá e quando foi gravado.

COMO RODAR

    bash /tmp/zerar-funcionarios-estimados.sh --simular
    bash /tmp/zerar-funcionarios-estimados.sh

O wrapper acha o Python certo e carrega o .env — `sudo -iu hipo` NÃO
carrega, e o pydantic aborta em "DATABASE_URL Field required".
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import asyncpg

from config import settings

ESTIMADO = "estimado"


def mascarar_url(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


async def principal(args) -> int:
    url = settings.DATABASE_URL
    print(f"Banco : {mascarar_url(url)}")
    print(f"Modo  : {'SIMULAÇÃO (nada será gravado)' if args.simular else 'GRAVANDO'}")
    print()

    conn = await asyncpg.connect(url)
    try:
        # O filtro vive no SQL de propósito: 'declarado' nunca chega ao
        # Python, então não há caminho de código que o atinja por engano.
        linhas = await conn.fetch(
            """
            SELECT c.id,
                   c.razao_social,
                   c.cnpj,
                   c.num_funcionarios,
                   c.num_funcionarios_origem,
                   c.num_funcionarios_em
              FROM contas c
             WHERE c.num_funcionarios_origem = $1
               AND c.num_funcionarios IS NOT NULL
             ORDER BY c.razao_social
            """,
            ESTIMADO,
        )

        declarados = await conn.fetchval(
            """
            SELECT count(*) FROM contas
             WHERE num_funcionarios_origem = 'declarado'
               AND num_funcionarios IS NOT NULL
            """
        )

        print(f"Estimados a zerar  : {len(linhas)}")
        print(f"Declarados intactos: {declarados}  (nunca tocados)")
        print()

        if not linhas:
            print("Nada a fazer.")
            return 0

        # ── o CSV, sempre, mesmo em simulação ─────────────────────────
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = Path(args.csv or f"funcionarios_estimados_{carimbo}.csv")
        with destino.open("w", newline="", encoding="utf-8") as f:
            escritor = csv.writer(f)
            escritor.writerow([
                "conta_id", "razao_social", "cnpj",
                "num_funcionarios", "origem", "gravado_em",
            ])
            for l in linhas:
                escritor.writerow([
                    l["id"], l["razao_social"], l["cnpj"],
                    l["num_funcionarios"], l["num_funcionarios_origem"],
                    l["num_funcionarios_em"],
                ])
        print(f"CSV de segurança: {destino.resolve()}")
        print()

        if args.detalhar:
            for l in linhas[:40]:
                nome = (l["razao_social"] or "")[:40]
                print(f"  {nome:<42} {l['num_funcionarios']:>6}")
            if len(linhas) > 40:
                print(f"  ... e mais {len(linhas) - 40}")
            print()

        if args.simular:
            print("NADA FOI GRAVADO. Rode sem --simular para valer.")
            return 0

        # `execute` devolve a tag do comando ("UPDATE 3"). Interessa o
        # numero, e ele vale mais que o len(linhas): se alguem gravou um
        # estimado entre o SELECT e o UPDATE, e aqui que isso aparece.
        tag = await conn.execute(
            """
            UPDATE contas
               SET num_funcionarios = NULL,
                   num_funcionarios_origem = NULL,
                   num_funcionarios_em = NULL
             WHERE num_funcionarios_origem = $1
               AND num_funcionarios IS NOT NULL
            """,
            ESTIMADO,
        )
        gravadas = tag.rsplit(" ", 1)[-1]

        print("=" * 62)
        print(f" {gravadas} conta(s) com o campo zerado.")
        if gravadas.isdigit() and int(gravadas) != len(linhas):
            print(f" (o CSV listou {len(linhas)} -- o banco mudou no meio)")
        print("=" * 62)
        print()
        print(" Elas voltam a ser preenchidas sozinhas na próxima consulta")
        print(" de dados públicos — campo vazio é o único que o")
        print(" enriquecimento preenche.")
        print()
        print(" O que NÃO volta sozinho: a consulta só acontece quando")
        print(" alguém abre a conta e aperta ATUALIZAR DADOS PÚBLICOS, ou")
        print(" quando o cache de 90 dias vence. Abrir a aba não reconsulta.")
        return 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Zera num_funcionarios de origem 'estimado'."
    )
    p.add_argument("--simular", action="store_true",
                   help="mostra e exporta o CSV, sem gravar")
    p.add_argument("--detalhar", action="store_true",
                   help="lista as contas afetadas")
    p.add_argument("--csv", help="caminho do CSV de segurança")
    return asyncio.run(principal(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
