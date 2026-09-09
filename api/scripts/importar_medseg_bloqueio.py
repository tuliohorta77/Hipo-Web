"""
HIPO — Carga única: clientes da MedSeg marcados como "não prospectar".

Isto NÃO é funcionalidade do produto. É migração de uso único, rodada à mão.

O QUE ELE FAZ
  1. Para cada CNPJ da lista, acha a conta. Se não existir, cria — só razão
     social, CNPJ e observações.
  2. Marca a conta com nao_prospectar = TRUE, o motivo e a autoria.

POR QUE CRIAR A CONTA EM VEZ DE GUARDAR SÓ O CNPJ NUMA LISTA
  `contas.cnpj` já é UNIQUE e já produz o 409 com o registro existente. Com a
  conta criada, o SDR que tentar cadastrar essa empresa esbarra no 409 que já
  existe, abre a conta e vê a marca. Numa lista paralela, o mesmo CNPJ
  existiria em dois lugares e o 409 não saberia da lista.

O QUE ELE NÃO FAZ
  Não fecha, não cancela e não toca em oportunidade nenhuma. Se uma conta da
  lista já tiver negócio em andamento, o script AVISA no fim e deixa como
  está: encerrar negócio aberto é decisão do vendedor, não de um script de
  carga. O relatório lista essas contas nominalmente.

IDEMPOTÊNCIA
  Conta que já está com nao_prospectar = TRUE é pulada — inclusive o motivo,
  que não é sobrescrito. Rodar duas vezes não muda nada na segunda.

USO
  cd api
  export DATABASE_URL=...            # confira o host antes!
  echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'

  python -m scripts.importar_medseg_bloqueio                 # dry-run
  python -m scripts.importar_medseg_bloqueio --commit        # grava

  --arquivo CAMINHO      JSON da carga
  --criado-por EMAIL     autor do bloqueio (precisa ser cargo de gestão)

TUDO OU NADA
  Uma transação só. Erro no meio desfaz a carga inteira.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import asyncpg

DEFAULT_JSON = (Path(__file__).resolve().parent / "dados"
                / "medseg_nao_prospectar_2026-09-09.json")
DEFAULT_AUTOR = "tulio.horta@controllermedseg.com"

# Mesmo conjunto de routers/permissions.py. Duplicado de propósito: o script
# não sobe a app, e um bloqueio gravado por quem não poderia fazê-lo pela
# tela criaria um estado que a própria API se recusaria a produzir.
CARGOS_GESTAO = {"Franqueado", "ADM"}


def mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


async def resolver_autor(conn, email: str) -> str:
    row = await conn.fetchrow(
        "SELECT id, cargo FROM usuarios WHERE lower(email) = lower($1)", email
    )
    if row is None:
        raise SystemExit(
            f"Usuário '{email}' não existe. Rode `python -m scripts.seed_usuarios` antes."
        )
    if row["cargo"] not in CARGOS_GESTAO:
        raise SystemExit(
            f"Usuário '{email}' tem cargo '{row['cargo']}'. Bloquear conta para "
            f"prospecção é ação de gestão ({sorted(CARGOS_GESTAO)}) — a API recusa, "
            f"e este script recusa junto para não gravar o que a tela não gravaria."
        )
    return row["id"]


async def importar(args) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL não definida.")

    dados = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
    registros = dados["registros"]
    motivo = args.motivo or dados["motivo"]
    marca = f"[cliente MedSeg — carga de {dados['gerado_em']}]"

    print(f"banco   : {mascarar(url)}")
    print(f"arquivo : {args.arquivo}")
    print(f"modo    : {'COMMIT' if args.commit else 'DRY-RUN (rollback no fim)'}")
    print(f"motivo  : {motivo}")
    print(f"payload : {len(registros)} CNPJ\n")

    conn = await asyncpg.connect(url)
    criadas = marcadas = ja_marcadas = 0
    com_negocio: list[str] = []
    renomeadas: list[str] = []

    try:
        tx = conn.transaction()
        await tx.start()
        autor = await resolver_autor(conn, args.criado_por)

        for r in registros:
            existente = await conn.fetchrow(
                "SELECT id, razao_social, nao_prospectar FROM contas WHERE cnpj = $1",
                r["cnpj"],
            )

            if existente is None:
                conta_id = await conn.fetchval(
                    """
                    INSERT INTO contas (razao_social, cnpj, observacoes, criado_por)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    r["razao_social"], r["cnpj"], marca, autor,
                )
                criadas += 1
            else:
                conta_id = existente["id"]
                if existente["nao_prospectar"]:
                    ja_marcadas += 1
                    continue
                # A razão social do banco manda: se a conta já existia, ela
                # veio de um cadastro feito por gente, e a planilha é uma
                # exportação. Só registro a divergência para conferência.
                if (existente["razao_social"].strip().lower()
                        != r["razao_social"].strip().lower()):
                    renomeadas.append(
                        f"{r['cnpj']}: banco='{existente['razao_social']}' "
                        f"| planilha='{r['razao_social']}'"
                    )

            await conn.execute(
                """
                UPDATE contas
                   SET nao_prospectar        = TRUE,
                       nao_prospectar_motivo = $2,
                       nao_prospectar_em     = NOW(),
                       nao_prospectar_por    = $3,
                       atualizado_em         = NOW()
                 WHERE id = $1
                """,
                conta_id, motivo, autor,
            )
            marcadas += 1

            abertas = await conn.fetchval(
                """
                SELECT count(*) FROM oportunidades
                 WHERE conta_id = $1 AND status IN ('ativa', 'suspensa')
                """,
                conta_id,
            )
            if abertas:
                nome = existente["razao_social"] if existente else r["razao_social"]
                com_negocio.append(f"{r['cnpj']} {nome} — {abertas} em aberto")

        print("contas criadas         :", criadas)
        print("contas marcadas        :", marcadas)
        print("ja estavam marcadas    :", ja_marcadas)
        print("razao social divergente:", len(renomeadas))
        for x in renomeadas[:15]:
            print("   -", x)
        if len(renomeadas) > 15:
            print(f"   ... e mais {len(renomeadas) - 15}")

        print("\nATENCAO — contas bloqueadas que TEM negocio em aberto:", len(com_negocio))
        print("O bloqueio nao fecha nada. Estas oportunidades continuam vivas")
        print("e precisam ser encerradas a mao por quem as conduz:")
        for x in com_negocio:
            print("   -", x)

        if args.commit:
            await tx.commit()
            print("\nCOMMIT feito. Confira em https://hipogestao.com.br")
        else:
            await tx.rollback()
            print("\nDRY-RUN: nada foi gravado. Rode de novo com --commit.")
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(
        description="Marca os clientes da MedSeg como nao prospectar."
    )
    p.add_argument("--arquivo", default=str(DEFAULT_JSON))
    p.add_argument("--criado-por", default=DEFAULT_AUTOR)
    p.add_argument("--motivo", default=None,
                   help="sobrescreve o motivo que vem no JSON")
    p.add_argument("--commit", action="store_true",
                   help="grava de verdade; sem esta flag o script faz rollback")
    args = p.parse_args()
    try:
        asyncio.run(importar(args))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\nFALHOU: {exc}", file=sys.stderr)
        print("Nada foi gravado — a transação inteira foi desfeita.", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
