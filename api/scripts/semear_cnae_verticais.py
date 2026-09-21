"""
HIPO — Classifica de uma vez os CNAEs que já estão na base.

O QUE ESTE SCRIPT FAZ

A partir da 015, todo CNAE novo já nasce com a vertical derivada da seção
da CNAE 2.0. Este script faz o mesmo com os que ENTRARAM ANTES — e aplica
a vertical nas contas que estavam esperando.

Em uma passada:
  1. cria (ou reaproveita) as 21 verticais das seções da CNAE 2.0;
  2. deriva a vertical de todo CNAE sem decisão humana e sem vertical;
  3. preenche `contas.vertical_id` onde está vazio.

O QUE ELE NUNCA FAZ

  * Não toca em CNAE com `mapeamento_origem = 'humano'`. Decisão de gente
    não é sobrescrita por regra automática — é a mesma lei do
    enriquecimento.
  * Não toca em conta que já tem vertical.
  * Não inventa grau de risco. O grau vale por subclasse no Anexo I da
    NR-4; derivar por seção seria inventar o número que decide
    dimensionamento de SESMT.

COMO RODAR

Sempre com `--simular` primeiro: ele mostra o que faria, conta por conta,
sem gravar nada.

    sudo -iu hipo
    cd /home/hipo/app/api
    echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'   # confira o host
    python -m scripts.semear_cnae_verticais --simular
    python -m scripts.semear_cnae_verticais

Rodar duas vezes não faz nada na segunda.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter

import asyncpg

from config import settings
from services.enriquecimento import cnae_estrutura


def mascarar_url(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


async def principal(args) -> int:
    print(f"Banco : {mascarar_url(settings.DATABASE_URL)}")
    print(f"Modo  : {'SIMULAÇÃO (nada será gravado)' if args.simular else 'GRAVANDO'}")
    print()

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        # ── 1. verticais ────────────────────────────────────────────────
        verticais: dict[str, int] = {}
        criadas = 0
        for slug, nome in cnae_estrutura.verticais_derivadas():
            existente = await conn.fetchval(
                "SELECT id FROM verticais WHERE slug = $1", slug
            )
            if existente:
                verticais[slug] = existente
                continue
            if args.simular:
                # Id de mentira só para o relatório seguir.
                verticais[slug] = -1
                criadas += 1
                continue
            verticais[slug] = await conn.fetchval(
                "INSERT INTO verticais (nome, slug) VALUES ($1, $2) RETURNING id",
                nome, slug,
            )
            criadas += 1
        print(f"Verticais: {criadas} criada(s), "
              f"{len(verticais) - criadas} já existia(m)")

        # ── 2. CNAEs ────────────────────────────────────────────────────
        pendentes = await conn.fetch(
            """
            SELECT c.codigo, c.descricao,
                   (SELECT count(*) FROM contas ct
                     WHERE ct.cnae_codigo = c.codigo
                       AND ct.vertical_id IS NULL AND ct.ativo) AS contas_sem_vertical
              FROM cnaes c
             WHERE c.vertical_id IS NULL
               AND c.mapeamento_origem IS DISTINCT FROM 'humano'
             ORDER BY 3 DESC, c.codigo
            """
        )
        print(f"CNAEs sem vertical: {len(pendentes)}")
        print()

        por_secao = Counter()
        sem_secao: list[str] = []
        cnaes_ok = 0
        contas_tocadas = 0

        for linha in pendentes:
            codigo = linha["codigo"]
            secao = cnae_estrutura.secao_de(codigo)
            if not secao:
                sem_secao.append(codigo)
                continue
            _, slug, nome = secao
            vertical_id = verticais[slug]
            por_secao[nome] += 1
            cnaes_ok += 1

            if not args.simular:
                await conn.execute(
                    """
                    UPDATE cnaes
                       SET vertical_id = $2,
                           mapeado_em = NOW(),
                           mapeamento_origem = 'derivado'
                     WHERE codigo = $1 AND vertical_id IS NULL
                    """,
                    codigo, vertical_id,
                )
                resultado = await conn.execute(
                    """
                    UPDATE contas
                       SET vertical_id = $2, atualizado_em = NOW()
                     WHERE cnae_codigo = $1 AND vertical_id IS NULL AND ativo
                    """,
                    codigo, vertical_id,
                )
                partes = resultado.split()
                contas_tocadas += (
                    int(partes[-1]) if partes and partes[-1].isdigit() else 0
                )
            else:
                contas_tocadas += linha["contas_sem_vertical"]

            if args.detalhar:
                print(f"  {codigo}  {nome:<28} "
                      f"{linha['contas_sem_vertical']} conta(s)  "
                      f"{(linha['descricao'] or '')[:45]}")

        # ── 3. relatório ────────────────────────────────────────────────
        print()
        print("=" * 62)
        print(f" {cnaes_ok} CNAE(s) classificado(s) por seção")
        print(f" {contas_tocadas} conta(s) {'seriam' if args.simular else 'foram'} "
              f"classificada(s)")
        print("=" * 62)
        if por_secao:
            print()
            print(" Por vertical:")
            for nome, qtd in por_secao.most_common():
                print(f"   {nome:<30} {qtd:>4} CNAE(s)")

        if sem_secao:
            print()
            print(f" {len(sem_secao)} código(s) fora da estrutura da CNAE 2.0 "
                  f"(divisão inexistente):")
            for codigo in sem_secao[:15]:
                print(f"   {codigo}")
            print("   Esses continuam sem vertical — e é o certo: código com")
            print("   divisão que não existe costuma ser erro de origem.")

        restantes = await conn.fetchval(
            """
            SELECT count(*) FROM contas
             WHERE ativo AND vertical_id IS NULL AND cnae_codigo IS NOT NULL
            """
        )
        sem_cnae = await conn.fetchval(
            "SELECT count(*) FROM contas WHERE ativo AND cnae_codigo IS NULL"
        )
        print()
        print(f" Ainda sem vertical, COM CNAE conhecido: {restantes}")
        print(f" Ainda sem CNAE nenhum (nunca consultadas): {sem_cnae}")
        if sem_cnae:
            print("   Essas só ganham CNAE quando forem consultadas por CNPJ.")

        if args.simular:
            print()
            print(" NADA FOI GRAVADO. Rode sem --simular para valer.")
        return 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Deriva a vertical dos CNAEs pela seção da CNAE 2.0."
    )
    p.add_argument("--simular", action="store_true",
                   help="mostra o que faria, sem gravar")
    p.add_argument("--detalhar", action="store_true",
                   help="lista cada CNAE tratado")
    args = p.parse_args()
    return asyncio.run(principal(args))


if __name__ == "__main__":
    sys.exit(main())
