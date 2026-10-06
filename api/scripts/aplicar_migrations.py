"""
HIPO -- aplica as migrations pendentes, em ordem, e registra cada uma.

Fonte de verdade do schema: a sequencia de arquivos em api/migrations/.
O CI sobe o banco de teste do zero por aqui, e o deploy aplica por aqui as
pendentes de producao. O api/schema.sql virou snapshot (consulta humana).

Uso:
    python -m scripts.aplicar_migrations                       # aplica pendentes
    python -m scripts.aplicar_migrations --status              # so mostra
    python -m scripts.aplicar_migrations --adotar-ate 029      # banco existente
    python -m scripts.aplicar_migrations --env-file /home/hipo/app/.env

Banco: DATABASE_URL do ambiente, ou a linha DATABASE_URL= do --env-file (o
arquivo e lido aqui dentro: nada de `source`, que interpretaria & ? * da URL,
e a senha nunca passa por linha de comando).

Travas, todas checadas ANTES de aplicar qualquer coisa:
  * nome fora do padrao NNN_nome.sql, ou dois arquivos com o mesmo NNN;
  * migration registrada cujo arquivo mudou (hash SHA-256 diferente) --
    nunca edite migration aplicada, crie outra;
  * migration registrada cujo arquivo sumiu do repositorio;
  * pendente com numero MENOR que a ultima aplicada (merge fora de ordem);
  * banco com tabelas e sem nenhum registro -- e producao antes da adocao:
    rodar dali aplicaria a 001 (drop do legado) num banco vivo;
  * a partir da LIMITE_LEGADO+1: BEGIN/COMMIT/ROLLBACK no arquivo (o script
    e quem abre a transacao, para que DDL e registro entrem juntos ou nao
    entrem) e DROP TABLE / DROP COLUMN / TRUNCATE / DELETE sem o marcador
    `-- hipo:destrutiva-com-export <arquivo.zip>` (regra do projeto: export
    em CSV + ZIP antes de qualquer migration destrutiva).

Uma transacao por migration; a primeira que falhar para tudo. Um advisory
lock impede dois deploys simultaneos de migrarem a mesma base.

Codigos de saida: 0 ok | 1 uso/conexao | 2 trava de consistencia | 3 erro de SQL.

Compativel com Python 3.9 (o /usr/bin/python3 do Amazon Linux 2023) e sem
dependencia do resto do app: o deploy roda este arquivo de uma pasta
temporaria, ANTES de o codigo novo tocar /home/hipo/app.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncpg

PASTA_PADRAO = Path(__file__).resolve().parent.parent / "migrations"

# Ultima migration aplicada a mao (psql) antes deste script existir. Ate ela
# as regras novas (sem BEGIN/COMMIT, marcador de destrutiva) nao se aplicam:
# os arquivos ficam como rodaram em producao.
LIMITE_LEGADO = 29

# Numero arbitrario e fixo: identifica "migrando o HIPO" no pg_locks.
CHAVE_LOCK = 7_310_029

PADRAO_NOME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
_CONTROLE_TX = re.compile(r"^\s*(BEGIN|COMMIT|ROLLBACK|START\s+TRANSACTION)\s*;",
                          re.IGNORECASE | re.MULTILINE)
_DESTRUTIVO = re.compile(r"\b(DROP\s+TABLE|DROP\s+COLUMN|DROP\s+SCHEMA|TRUNCATE|DELETE\s+FROM)\b",
                         re.IGNORECASE)
_MARCADOR_DESTRUTIVA = re.compile(r"^--\s*hipo:destrutiva-com-export\s+\S+\.zip\s*$",
                                  re.IGNORECASE | re.MULTILINE)

DDL_CONTROLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    nome        TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    aplicada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    modo        TEXT NOT NULL DEFAULT 'aplicada'
                CHECK (modo IN ('aplicada', 'adotada'))
)
"""


class Trava(Exception):
    """Inconsistencia entre repositorio e banco. Nada foi aplicado."""


# ---------------------------------------------------------------------------
# Arquivos
# ---------------------------------------------------------------------------

def texto_normalizado(caminho: Path) -> str:
    # BOM e CRLF fora: o mesmo arquivo tirado no Windows (autocrlf) e no
    # runner Linux tem que dar o mesmo hash.
    bruto = caminho.read_bytes()
    if bruto.startswith(b"\xef\xbb\xbf"):
        bruto = bruto[3:]
    return bruto.replace(b"\r\n", b"\n").decode("utf-8")


def sha256_de(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def numero_de(nome: str) -> int:
    m = PADRAO_NOME.match(nome)
    if not m:
        raise Trava(f"{nome}: nome fora do padrao NNN_nome.sql (minusculas, digitos, _).")
    return int(m.group(1))


def listar_migrations(pasta: Path) -> List[Tuple[int, str, Path]]:
    if not pasta.is_dir():
        raise Trava(f"pasta de migrations nao existe: {pasta}")
    itens = []
    vistos: Dict[int, str] = {}
    for arq in sorted(pasta.glob("*.sql")):
        n = numero_de(arq.name)
        if n in vistos:
            raise Trava(f"numero {n:03d} repetido: {vistos[n]} e {arq.name}. Renumere a mais nova.")
        vistos[n] = arq.name
        itens.append((n, arq.name, arq))
    return itens


def _sem_comentarios(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _sem_corpos_dollar(sql: str) -> str:
    # Corpo de funcao / DO block: o BEGIN ... END; de PL/pgSQL nao e
    # controle de transacao.
    return re.sub(r"(\$[A-Za-z_]*\$).*?\1", " ", sql, flags=re.DOTALL)


def conferir_regras_novas(numero: int, nome: str, texto: str) -> None:
    """Regras que valem da LIMITE_LEGADO+1 em diante."""
    if numero <= LIMITE_LEGADO:
        return
    codigo = _sem_comentarios(texto)
    if _CONTROLE_TX.search(_sem_corpos_dollar(codigo)):
        raise Trava(
            f"{nome}: tem BEGIN/COMMIT/ROLLBACK. Tire -- o aplicar_migrations abre "
            f"a transacao e grava o registro dentro dela."
        )
    if _DESTRUTIVO.search(codigo) and not _MARCADOR_DESTRUTIVA.search(texto):
        raise Trava(
            f"{nome}: e destrutiva (DROP TABLE/COLUMN, TRUNCATE ou DELETE). Exporte as "
            f"tabelas afetadas em CSV + ZIP antes e marque o arquivo com a linha\n"
            f"    -- hipo:destrutiva-com-export <nome-do-zip>.zip"
        )


# ---------------------------------------------------------------------------
# Banco
# ---------------------------------------------------------------------------

def url_do_env_file(caminho: str) -> str:
    try:
        linhas = Path(caminho).read_text(encoding="utf-8-sig").splitlines()
    except OSError as e:
        raise SystemExit(f"ERRO: nao consegui ler {caminho}: {e}")
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("DATABASE_URL="):
            valor = linha.split("=", 1)[1].strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
                valor = valor[1:-1]
            if valor:
                return valor
    raise SystemExit(f"ERRO: {caminho} sem DATABASE_URL.")


def mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url)


async def tabelas_de_usuario(conn) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' "
        "AND tablename <> 'schema_migrations'"
    )


async def registradas(conn) -> Dict[str, str]:
    return {r["nome"]: r["sha256"] for r in await conn.fetch("SELECT nome, sha256 FROM schema_migrations")}


def planejar(arquivos, aplicadas: Dict[str, str]):
    """Devolve (pendentes, textos). Levanta Trava em qualquer inconsistencia."""
    nomes_repo = {nome for _, nome, _ in arquivos}
    sumidas = sorted(set(aplicadas) - nomes_repo)
    if sumidas:
        raise Trava(
            "registradas no banco mas ausentes do repositorio: " + ", ".join(sumidas)
            + ". Migration aplicada nao sai do repositorio."
        )

    textos: Dict[str, str] = {}
    pendentes = []
    ultima_aplicada = max((numero_de(n) for n in aplicadas), default=-1)

    for numero, nome, caminho in arquivos:
        texto = texto_normalizado(caminho)
        textos[nome] = texto
        if nome in aplicadas:
            if aplicadas[nome] != sha256_de(texto):
                raise Trava(
                    f"{nome} ja aplicada mas o arquivo mudou "
                    f"(hash {aplicadas[nome][:8]} -> {sha256_de(texto)[:8]}). "
                    f"Nunca edite migration aplicada: desfaca a edicao e crie uma nova."
                )
            continue
        if numero < ultima_aplicada:
            raise Trava(
                f"{nome} esta pendente mas a {ultima_aplicada:03d} ja foi aplicada. "
                f"Renumere-a para depois da ultima."
            )
        conferir_regras_novas(numero, nome, texto)
        pendentes.append((numero, nome))
    return pendentes, textos


async def executar(url: str, pasta: Path, status: bool, adotar_ate: Optional[int]) -> int:
    arquivos = listar_migrations(pasta)
    print(f"banco: {mascarar(url)}")
    print(f"pasta: {pasta} ({len(arquivos)} arquivos)")

    try:
        conn = await asyncpg.connect(url, timeout=20)
    except Exception as e:  # noqa: BLE001 -- qualquer falha de conexao e saida 1
        print(f"ERRO: nao conectei no banco: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        await conn.execute("SELECT pg_advisory_lock($1)", CHAVE_LOCK)
        await conn.execute(DDL_CONTROLE)
        aplicadas = await registradas(conn)

        if adotar_ate is not None:
            return await adotar(conn, arquivos, aplicadas, adotar_ate)

        if not aplicadas and await tabelas_de_usuario(conn) > 0:
            if status:
                print("banco com tabelas e sem nenhum registro: precisa de --adotar-ate NNN")
                return 0
            raise Trava(
                "o banco tem tabelas mas schema_migrations esta vazia -- e um banco que "
                "recebia migration a mao. Registre o que ja esta nele, uma vez so:\n"
                "    python -m scripts.aplicar_migrations --adotar-ate NNN\n"
                "(NNN = ultima migration que voce aplicou nesse banco)."
            )

        pendentes, textos = planejar(arquivos, aplicadas)

        if status:
            for _, nome, _ in arquivos:
                print(f"  {'ok      ' if nome in aplicadas else 'PENDENTE'}  {nome}")
            print(f"{len(aplicadas)} registrada(s), {len(pendentes)} pendente(s)")
            return 0

        if not pendentes:
            print("nada a aplicar")
            return 0

        for _, nome in pendentes:
            print(f"aplicando {nome}...", flush=True)
            texto = textos[nome]
            try:
                # Os arquivos ate a LIMITE_LEGADO podem ter BEGIN/COMMIT proprios
                # (rodavam por psql). So sobem assim em banco novo -- em
                # producao ja estao adotados --, entao o registro logo depois
                # do COMMIT deles e aceitavel. Da LIMITE_LEGADO+1 em diante a
                # transacao e esta aqui, com o registro dentro.
                async with conn.transaction():
                    await conn.execute(texto)
                    await conn.execute(
                        "INSERT INTO schema_migrations (nome, sha256) VALUES ($1, $2)",
                        nome, sha256_de(texto),
                    )
            except Exception as e:  # noqa: BLE001
                print(f"ERRO em {nome}: {type(e).__name__}: {e}", file=sys.stderr)
                print("nada desta migration ficou no banco; as seguintes nao rodaram.", file=sys.stderr)
                return 3

        print(f"{len(pendentes)} migration(s) aplicada(s)")
        return 0
    except Trava as t:
        print(f"ERRO: {t}", file=sys.stderr)
        print("nada foi aplicado.", file=sys.stderr)
        return 2
    finally:
        await conn.close()


async def adotar(conn, arquivos, aplicadas: Dict[str, str], ate: int) -> int:
    """Registra sem executar as migrations ate `ate` -- uma vez, num banco que
    ja as recebeu a mao. Grava o hash ATUAL: daqui em diante, editar qualquer
    uma delas trava o deploy."""
    if aplicadas:
        raise Trava(f"schema_migrations ja tem {len(aplicadas)} registro(s): adocao e so para banco sem nenhum.")
    if await tabelas_de_usuario(conn) == 0:
        raise Trava("banco vazio nao se adota: rode sem --adotar-ate e as migrations sobem do zero.")
    alvo = [(n, nome, p) for n, nome, p in arquivos if n <= ate]
    if not alvo or alvo[-1][0] != ate:
        raise Trava(f"nao existe migration {ate:03d} no repositorio.")
    async with conn.transaction():
        for _, nome, caminho in alvo:
            await conn.execute(
                "INSERT INTO schema_migrations (nome, sha256, modo) VALUES ($1, $2, 'adotada')",
                nome, sha256_de(texto_normalizado(caminho)),
            )
    print(f"{len(alvo)} migration(s) adotada(s), de {alvo[0][1]} a {alvo[-1][1]}. Nada foi executado.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--env-file", help="le DATABASE_URL deste arquivo em vez do ambiente")
    p.add_argument("--pasta", type=Path, default=PASTA_PADRAO, help="pasta das migrations")
    p.add_argument("--status", action="store_true", help="mostra aplicadas/pendentes e sai")
    p.add_argument("--adotar-ate", type=int, metavar="NNN",
                   help="registra sem executar as migrations ate NNN (uma vez, banco existente)")
    a = p.parse_args(argv)

    if a.env_file:
        url = url_do_env_file(a.env_file)
    else:
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            print("ERRO: defina DATABASE_URL ou passe --env-file.", file=sys.stderr)
            return 1
    try:
        return asyncio.run(executar(url, a.pasta.resolve(), a.status, a.adotar_ate))
    except Trava as t:
        print(f"ERRO: {t}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
