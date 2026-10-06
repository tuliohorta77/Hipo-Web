"""
HIPO -- compara a ESTRUTURA de dois bancos (nao os dados).

Uso no CI: banco A subido pelas migrations, banco B subido pelo
api/schema.sql. Diferenca = snapshot desatualizado (alguem criou migration
e nao regerou o schema.sql). Ordem de coluna e comentarios nao contam:
o que entra na comparacao e o que muda comportamento.

    python -m scripts.comparar_schema URL_MIGRATIONS URL_SNAPSHOT

Saida 0 = iguais; 1 = diferentes (lista o que sobra de cada lado).
Compativel com Python 3.9.
"""
from __future__ import annotations

import asyncio
import re
import sys
from typing import List, Set

import asyncpg

IGNORAR = ("schema_migrations",)

CONSULTAS = {
    "coluna": """
        SELECT c.table_name || '.' || c.column_name || ' ' || c.data_type
               || coalesce('(' || c.character_maximum_length || ')', '')
               || CASE WHEN c.is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END
               || coalesce(' DEFAULT ' || c.column_default, '')
          FROM information_schema.columns c
          JOIN information_schema.tables t
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name
         WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
           AND c.table_name <> ALL($1::text[])
    """,
    "constraint": """
        SELECT cl.relname || ' ' || co.conname || ' ' || pg_get_constraintdef(co.oid)
          FROM pg_constraint co
          JOIN pg_class cl ON cl.oid = co.conrelid
          JOIN pg_namespace n ON n.oid = cl.relnamespace
         WHERE n.nspname = 'public' AND cl.relname <> ALL($1::text[])
    """,
    "indice": """
        SELECT indexdef FROM pg_indexes
         WHERE schemaname = 'public' AND tablename <> ALL($1::text[])
    """,
    "view": """
        SELECT viewname || ': ' || regexp_replace(definition, '\\s+', ' ', 'g')
          FROM pg_views WHERE schemaname = 'public' AND $1::text[] IS NOT NULL
    """,
    "funcao": """
        SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ') '
               || md5(pg_get_functiondef(p.oid))
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')
           AND NOT EXISTS (SELECT 1 FROM pg_depend d
                            WHERE d.objid = p.oid AND d.deptype = 'e')
           AND $1::text[] IS NOT NULL
    """,
    "trigger": """
        SELECT pg_get_triggerdef(t.oid)
          FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND NOT t.tgisinternal
           AND c.relname <> ALL($1::text[])
    """,
    "sequencia": """
        SELECT sequencename || ' ' || data_type::text FROM pg_sequences
         WHERE schemaname = 'public' AND $1::text[] IS NOT NULL
    """,
    "extensao": "SELECT extname FROM pg_extension WHERE $1::text[] IS NOT NULL",
}


_CAST = re.compile(r"::[a-z_]+(?: [a-z_]+)*(?:\(\d+(?:,\d+)?\))?(?:\[\])?")


def normalizar_check(definicao: str) -> str:
    """O mesmo CHECK volta do pg_dump com casts e parenteses em outra
    arrumacao (ARRAY[...]::text[] vira ARRAY[('x'::varchar)::text]). Tira
    casts, parenteses e espacos: sobra a logica, que e o que importa aqui."""
    return re.sub(r"[()\s]", "", _CAST.sub("", definicao))


async def impressao(url: str) -> Set[str]:
    conn = await asyncpg.connect(url, timeout=20)
    try:
        itens: Set[str] = set()
        for tipo, sql in CONSULTAS.items():
            for (linha,) in await conn.fetch(sql, list(IGNORAR)):
                if tipo == "constraint" and " CHECK " in linha:
                    nome, _, corpo = linha.partition(" CHECK ")
                    linha = f"{nome} CHECK {normalizar_check(corpo)}"
                itens.add(f"{tipo:<10} {linha}")
        return itens
    finally:
        await conn.close()


async def comparar(url_a: str, url_b: str) -> List[str]:
    a, b = await asyncio.gather(impressao(url_a), impressao(url_b))
    saida = [f"- so nas migrations: {x}" for x in sorted(a - b)]
    saida += [f"+ so no schema.sql:  {x}" for x in sorted(b - a)]
    return saida


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    diferencas = asyncio.run(comparar(argv[0], argv[1]))
    if not diferencas:
        print("estrutura identica")
        return 0
    print(f"{len(diferencas)} diferenca(s):")
    for d in diferencas:
        print("  " + d)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
