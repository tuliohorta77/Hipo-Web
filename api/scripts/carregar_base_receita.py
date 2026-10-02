"""
HIPO — Carga mensal da base de Dados Abertos do CNPJ (022).

O QUE ESTE SCRIPT FAZ

Lê os ZIPs da Receita, guarda só os estabelecimentos ATIVOS das UFs pedidas
(e, por padrão, sem MEI) e troca a tabela `receita_estabelecimentos` inteira
pela nova, junto com `receita_municipios` e `receita_cnaes`. A tela de
Prospecção passa a fatiar o dado novo no instante da troca.

A base é fonte de consulta: nada aqui cria conta, oportunidade ou tarefa.

OS ARQUIVOS

A Receita publica todo mês, em partes:

    Estabelecimentos0.zip .. Estabelecimentos9.zip
    Empresas0.zip         .. Empresas9.zip
    Simples.zip   Municipios.zip   Cnaes.zip

O endereço oficial mudou em janeiro/2026 e passou a ser um compartilhamento
que não é listável por script com estabilidade. Por isso há dois modos:

    --pasta DIR                os ZIPs já baixados (de qualquer lugar)
    --pasta DIR --baixar URL   baixa de um espelho que publique os nomes
                               acima em URL/<nome> (Casa dos Dados, por ex.)

COMO RODAR (na EC2, como hipo)

    sudo -iu hipo
    cd /home/hipo/app/api
    echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'   # confira o host
    python -m scripts.carregar_base_receita --ufs SP --referencia 2026-09 \\
        --pasta /home/hipo/receita --simular
    python -m scripts.carregar_base_receita --ufs SP --referencia 2026-09 \\
        --pasta /home/hipo/receita

`--simular` lê só os estabelecimentos e conta, sem tocar no banco. Use para
saber o tamanho antes de gastar disco do RDS.

`--apagar-depois` apaga cada ZIP depois de lido: o pico de disco fica em um
arquivo (~1 GB) em vez da base inteira (~7 GB).

POR QUE A TABELA É TROCADA, E NÃO ATUALIZADA

TRUNCATE + COPY na tabela viva deixaria a tela de Prospecção vazia (ou
travada, esperando o lock) durante a carga inteira, que leva dezenas de
minutos. A carga monta `receita_estabelecimentos_carga` ao lado, cria os
índices nela e só no fim, numa transação curta, apaga a velha e renomeia a
nova. A tela não vê o meio do caminho.

O DROP é permitido sem o export prévio em CSV porque o conteúdo é público e
reproduzível a partir dos ZIPs — não é trabalho de ninguém. Os nomes dos
índices aqui precisam bater com os de migrations/022_base_receita.sql; o
teste `test_receita_carga.py` confere.

MEMÓRIA

O script guarda o conjunto de CNPJs básicos que entraram (para filtrar o
arquivo de Empresas, que é nacional). Com SP inteiro são ~4 milhões de
inteiros — algo como 300 MB. Cabe na t3.medium com a API rodando; mais UFs
juntas, rodar fora do horário.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Iterable, Iterator

import asyncpg

from config import settings
from services import receita_carga as rc

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

LOTE_COPY = 50_000

ESTAB = "estabelecimentos"
EMPRESAS = "empresas"
SIMPLES = "simples"
MUNICIPIOS = "municipios"
CNAES = "cnaes"

ARQUIVOS_PADRAO = (
    [f"Estabelecimentos{i}.zip" for i in range(10)]
    + [f"Empresas{i}.zip" for i in range(10)]
    + ["Simples.zip", "Municipios.zip", "Cnaes.zip"]
)

TABELA = "receita_estabelecimentos"
CARGA = "receita_estabelecimentos_carga"

# (nome final, definição). Precisam bater com migrations/022_base_receita.sql.
INDICES = (
    ("idx_receita_uf_cnae", "(uf, cnae_principal)"),
    ("idx_receita_uf_municipio_cnae", "(uf, municipio_codigo, cnae_principal)"),
    ("idx_receita_cnaes_sec", "USING gin (cnaes_secundarios)"),
)

STAGING_DDL = """
DROP TABLE IF EXISTS receita_stg_estab, receita_stg_empresas,
                     receita_stg_simples, receita_stg_municipios,
                     receita_stg_cnaes;
CREATE UNLOGGED TABLE receita_stg_estab (
    cnpj CHAR(14), cnpj_basico CHAR(8), matriz BOOLEAN,
    nome_fantasia VARCHAR(200), data_abertura DATE, cnae_principal CHAR(7),
    cnaes_secundarios CHAR(7)[], logradouro VARCHAR(200), numero VARCHAR(20),
    complemento VARCHAR(100), bairro VARCHAR(100), cep CHAR(8), uf CHAR(2),
    municipio_codigo CHAR(4), telefone VARCHAR(20), telefone_2 VARCHAR(20),
    email VARCHAR(150)
);
CREATE UNLOGGED TABLE receita_stg_empresas (
    cnpj_basico CHAR(8), razao_social VARCHAR(200), natureza_juridica CHAR(4),
    capital_social NUMERIC(17,2), porte CHAR(2)
);
CREATE UNLOGGED TABLE receita_stg_simples (
    cnpj_basico CHAR(8), simples BOOLEAN, mei BOOLEAN
);
CREATE UNLOGGED TABLE receita_stg_municipios (codigo CHAR(4), nome VARCHAR(100));
CREATE UNLOGGED TABLE receita_stg_cnaes (codigo CHAR(7), descricao VARCHAR(300));
"""

STAGING_DROP = """
DROP TABLE IF EXISTS receita_stg_estab, receita_stg_empresas,
                     receita_stg_simples, receita_stg_municipios,
                     receita_stg_cnaes;
"""

COLUNAS_ESTAB = (
    "cnpj", "cnpj_basico", "matriz", "nome_fantasia", "data_abertura",
    "cnae_principal", "cnaes_secundarios", "logradouro", "numero",
    "complemento", "bairro", "cep", "uf", "municipio_codigo", "telefone",
    "telefone_2", "email",
)


def mascarar_url(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


# ── Arquivos ─────────────────────────────────────────────────────────────────

def grupo_do_arquivo(nome: str) -> str | None:
    """
    >>> grupo_do_arquivo('Estabelecimentos3.zip')
    'estabelecimentos'
    >>> grupo_do_arquivo('Socios1.zip') is None
    True
    """
    base = nome.lower()
    if not base.endswith(".zip"):
        return None
    for grupo in (ESTAB, EMPRESAS, SIMPLES, MUNICIPIOS, CNAES):
        if base.startswith(grupo):
            return grupo
    return None


def arquivos_por_grupo(pasta: Path) -> dict[str, list[Path]]:
    grupos: dict[str, list[Path]] = {g: [] for g in (ESTAB, EMPRESAS, SIMPLES, MUNICIPIOS, CNAES)}
    for caminho in sorted(pasta.iterdir()):
        g = grupo_do_arquivo(caminho.name)
        if g:
            grupos[g].append(caminho)
    return grupos


def encoding_pelo_bom(inicio: bytes) -> str:
    """
    O encoding do arquivo, pelos primeiros bytes.

    O layout documenta Latin-1, mas depois da migracao de fev/2026 da
    Receita apareceram arquivos em UTF-16 com BOM (e UTF-8 com BOM). Lidos
    como Latin-1, viram lixo com NUL entre cada letra -- e nenhuma linha
    passaria no parser. Sem BOM, continua Latin-1.

    >>> encoding_pelo_bom(b'\\xff\\xfe1\\x00')
    'utf-16'
    >>> encoding_pelo_bom(b'\\xef\\xbb\\xbf"1"')
    'utf-8-sig'
    >>> encoding_pelo_bom(b'"11222333"')
    'latin-1'
    """
    if inicio.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    if inicio.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return "latin-1"


def ler_zip(caminho: Path) -> Iterator[list[str]]:
    """
    Linhas do CSV dentro do ZIP, já quebradas em campos.

    O encoding sai do BOM (ver `encoding_pelo_bom`). O NUL é tirado antes do
    csv: a Receita deixa escapar alguns, o módulo csv recusa a linha
    inteira, e o Postgres não aceitaria o caractere em texto de qualquer
    forma.
    """
    with zipfile.ZipFile(caminho) as zf:
        for nome in zf.namelist():
            if nome.endswith("/"):
                continue
            with zf.open(nome) as espia:
                encoding = encoding_pelo_bom(espia.read(4))
            with zf.open(nome) as bruto:
                texto = io.TextIOWrapper(bruto, encoding=encoding, newline="")
                linhas = (linha.replace("\x00", "") for linha in texto)
                yield from csv.reader(linhas, delimiter=";", quotechar='"')


async def baixar(url_base: str, pasta: Path, nome: str) -> Path:
    """Baixa um arquivo do espelho para a pasta. Pula se já estiver lá."""
    import httpx

    destino = pasta / nome
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    url = f"{url_base.rstrip('/')}/{nome}"
    print(f"  baixando {url}")
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0),
                                 follow_redirects=True) as cliente:
        async with cliente.stream("GET", url) as resp:
            resp.raise_for_status()
            with parcial.open("wb") as saida:
                async for pedaco in resp.aiter_bytes(1 << 20):
                    saida.write(pedaco)
    parcial.rename(destino)
    return destino


# ── Carga ────────────────────────────────────────────────────────────────────

async def copiar(conn, tabela: str, colunas: Iterable[str], registros: list[tuple]) -> None:
    if registros:
        await conn.copy_records_to_table(tabela, records=registros, columns=list(colunas))


async def processar_estabelecimentos(conn, arquivos, ufs, args, basicos: set[int]) -> int:
    total_lido = 0
    total_aceito = 0
    por_uf: dict[str, int] = {}
    inicio = time.monotonic()
    for caminho in arquivos:
        caminho = await _garantir(caminho, args)
        lote: list[tuple] = []
        for campos in ler_zip(caminho):
            total_lido += 1
            est = rc.linha_estabelecimento(campos, ufs)
            if est is not None:
                total_aceito += 1
                por_uf[est.uf] = por_uf.get(est.uf, 0) + 1
                basicos.add(int(est.cnpj_basico))
                if conn is not None:
                    lote.append(est.como_registro())
                    if len(lote) >= LOTE_COPY:
                        await copiar(conn, "receita_stg_estab", COLUNAS_ESTAB, lote)
                        lote = []
            if total_lido % 1_000_000 == 0:
                print(f"    {total_lido:>12,} lidas | {total_aceito:>10,} aceitas "
                      f"| {time.monotonic() - inicio:,.0f}s")
            if args.limite and total_aceito >= args.limite:
                break
        if conn is not None:
            await copiar(conn, "receita_stg_estab", COLUNAS_ESTAB, lote)
        _apagar_se_pedido(caminho, args)
        print(f"  {caminho.name}: acumulado {total_aceito:,} ativos nas UFs pedidas")
        if args.limite and total_aceito >= args.limite:
            break
    for uf, n in sorted(por_uf.items()):
        print(f"    {uf}: {n:,}")
    return total_aceito


async def processar_por_basico(conn, arquivos, args, basicos: set[int], tabela: str,
                               colunas: tuple[str, ...], parser) -> int:
    aceitos = 0
    for caminho in arquivos:
        caminho = await _garantir(caminho, args)
        lote: list[tuple] = []
        for campos in ler_zip(caminho):
            registro = parser(campos)
            if registro is None or int(registro[0]) not in basicos:
                continue
            aceitos += 1
            lote.append(registro)
            if len(lote) >= LOTE_COPY:
                await copiar(conn, tabela, colunas, lote)
                lote = []
        await copiar(conn, tabela, colunas, lote)
        _apagar_se_pedido(caminho, args)
        print(f"  {caminho.name}: acumulado {aceitos:,}")
    return aceitos


async def processar_auxiliar(conn, arquivos, args, tabela: str, coluna: str,
                             digitos: int) -> int:
    registros: dict[str, tuple] = {}
    for caminho in arquivos:
        caminho = await _garantir(caminho, args)
        for campos in ler_zip(caminho):
            r = rc.linha_codigo_descricao(campos, digitos)
            if r:
                registros[r[0]] = r
        _apagar_se_pedido(caminho, args)
    await copiar(conn, tabela, ("codigo", coluna), list(registros.values()))
    return len(registros)


async def _garantir(caminho: Path, args) -> Path:
    if caminho.exists():
        return caminho
    if args.baixar:
        return await baixar(args.baixar, caminho.parent, caminho.name)
    raise FileNotFoundError(f"Arquivo ausente: {caminho}")


def _apagar_se_pedido(caminho: Path, args) -> None:
    # Na simulacao nunca: o ensaio existe para decidir se vale gravar, e
    # apagar os ZIPs obrigaria a baixar tudo de novo.
    if args.apagar_depois and not args.simular and caminho.exists():
        caminho.unlink()


async def montar_tabela_nova(conn, manter_mei: bool) -> int:
    await conn.execute(f"DROP TABLE IF EXISTS {CARGA}")
    await conn.execute(
        f"CREATE TABLE {CARGA} (LIKE {TABELA} INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"
    )
    resultado = await conn.execute(
        f"""
        INSERT INTO {CARGA} (
            cnpj, cnpj_basico, matriz, razao_social, nome_fantasia,
            natureza_juridica, porte, capital_social, simples, mei,
            data_abertura, cnae_principal, cnaes_secundarios, logradouro,
            numero, complemento, bairro, cep, uf, municipio_codigo,
            telefone, telefone_2, email
        )
        SELECT DISTINCT ON (e.cnpj)
               e.cnpj, e.cnpj_basico, e.matriz,
               COALESCE(emp.razao_social, e.nome_fantasia),
               e.nome_fantasia, emp.natureza_juridica, emp.porte,
               emp.capital_social, s.simples, s.mei,
               e.data_abertura, e.cnae_principal,
               COALESCE(e.cnaes_secundarios, '{{}}'), e.logradouro,
               e.numero, e.complemento, e.bairro, e.cep, e.uf,
               e.municipio_codigo, e.telefone, e.telefone_2, e.email
          FROM receita_stg_estab e
          LEFT JOIN (
              SELECT DISTINCT ON (cnpj_basico) *
                FROM receita_stg_empresas ORDER BY cnpj_basico
          ) emp ON emp.cnpj_basico = e.cnpj_basico
          LEFT JOIN (
              SELECT DISTINCT ON (cnpj_basico) *
                FROM receita_stg_simples ORDER BY cnpj_basico
          ) s ON s.cnpj_basico = e.cnpj_basico
         WHERE COALESCE(emp.razao_social, e.nome_fantasia) IS NOT NULL
           AND ($1 OR s.mei IS NOT TRUE)
         ORDER BY e.cnpj
        """,
        manter_mei,
    )
    inseridos = int(resultado.split()[-1])
    print(f"  {inseridos:,} estabelecimentos na tabela nova; criando índices")
    await conn.execute(
        f"ALTER TABLE {CARGA} ADD CONSTRAINT {CARGA}_pkey PRIMARY KEY (cnpj)"
    )
    for nome, definicao in INDICES:
        await conn.execute(f"CREATE INDEX {nome}_carga ON {CARGA} {definicao}")
    await conn.execute(f"ANALYZE {CARGA}")
    return inseridos


async def trocar(conn, carga_id: int, inseridos: int) -> None:
    """A troca: uma transação curta, com teto de espera pelo lock."""
    async with conn.transaction():
        await conn.execute("SET LOCAL lock_timeout = '60s'")
        await conn.execute(f"DROP TABLE {TABELA}")
        await conn.execute(f"ALTER TABLE {CARGA} RENAME TO {TABELA}")
        await conn.execute(
            f"ALTER TABLE {TABELA} RENAME CONSTRAINT {CARGA}_pkey TO {TABELA}_pkey"
        )
        for nome, _ in INDICES:
            await conn.execute(f"ALTER INDEX {nome}_carga RENAME TO {nome}")

        await conn.execute("TRUNCATE receita_municipios, receita_cnaes")
        await conn.execute(
            f"""
            INSERT INTO receita_municipios (codigo, nome, uf)
            SELECT DISTINCT ON (sm.codigo) sm.codigo, sm.nome, x.uf
              FROM receita_stg_municipios sm
              JOIN (SELECT DISTINCT municipio_codigo, uf FROM {TABELA}) x
                ON x.municipio_codigo = sm.codigo
             ORDER BY sm.codigo
            """
        )
        await conn.execute(
            """
            INSERT INTO receita_cnaes (codigo, descricao)
            SELECT DISTINCT ON (codigo) codigo, descricao
              FROM receita_stg_cnaes ORDER BY codigo
            """
        )
        await conn.execute(
            """
            UPDATE receita_cargas
               SET status = 'concluida', concluida_em = NOW(),
                   estabelecimentos = $2
             WHERE id = $1
            """,
            carga_id, inseridos,
        )


async def principal(args) -> int:
    try:
        ufs = rc.ufs_validas(args.ufs)
    except ValueError as e:
        print(f"ERRO: {e}")
        return 2
    pasta = Path(args.pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    if args.baixar:
        # Com espelho, a lista e a padrao: o que nao estiver na pasta e
        # baixado na hora de ler (um por vez, para o --apagar-depois valer).
        grupos = {g: [] for g in (ESTAB, EMPRESAS, SIMPLES, MUNICIPIOS, CNAES)}
        for nome in ARQUIVOS_PADRAO:
            grupos[grupo_do_arquivo(nome)].append(pasta / nome)
    else:
        grupos = arquivos_por_grupo(pasta)

    faltando = [g for g in (ESTAB, EMPRESAS, MUNICIPIOS, CNAES) if not grupos[g]]
    if not args.manter_mei and not grupos[SIMPLES]:
        faltando.append(SIMPLES)
    if faltando:
        print(f"ERRO: faltam arquivos em {pasta}: {', '.join(faltando)}.")
        return 2

    print(f"Banco      : {mascarar_url(settings.DATABASE_URL)}")
    print(f"UFs        : {', '.join(sorted(ufs))}")
    print(f"Referência : {args.referencia}")
    print(f"MEI        : {'mantidos' if args.manter_mei else 'descartados'}")
    print(f"Modo       : {'SIMULAÇÃO (só conta, não grava)' if args.simular else 'GRAVANDO'}")
    print()

    basicos: set[int] = set()
    if args.simular:
        print("== estabelecimentos ==")
        n = await processar_estabelecimentos(None, grupos[ESTAB], ufs, args, basicos)
        print(f"\n{n:,} estabelecimentos ativos ({len(basicos):,} empresas). "
              "MEI ainda incluídos nesta contagem.")
        return 0

    conn = await asyncpg.connect(settings.DATABASE_URL, command_timeout=None)
    carga_id = None
    try:
        carga_id = await conn.fetchval(
            "INSERT INTO receita_cargas (referencia, ufs) VALUES ($1, $2) RETURNING id",
            args.referencia, ",".join(sorted(ufs)),
        )
        await conn.execute(STAGING_DDL)

        print("== estabelecimentos ==")
        await processar_estabelecimentos(conn, grupos[ESTAB], ufs, args, basicos)
        print("== empresas ==")
        await processar_por_basico(
            conn, grupos[EMPRESAS], args, basicos, "receita_stg_empresas",
            ("cnpj_basico", "razao_social", "natureza_juridica", "capital_social", "porte"),
            rc.linha_empresa,
        )
        if grupos[SIMPLES]:
            print("== simples ==")
            await processar_por_basico(
                conn, grupos[SIMPLES], args, basicos, "receita_stg_simples",
                ("cnpj_basico", "simples", "mei"), rc.linha_simples,
            )
        basicos.clear()
        print("== municípios e CNAEs ==")
        await processar_auxiliar(conn, grupos[MUNICIPIOS], args, "receita_stg_municipios", "nome", 4)
        await processar_auxiliar(conn, grupos[CNAES], args, "receita_stg_cnaes", "descricao", 7)

        print("== montando a tabela nova ==")
        inseridos = await montar_tabela_nova(conn, args.manter_mei)
        print("== trocando ==")
        await trocar(conn, carga_id, inseridos)
        await conn.execute(STAGING_DROP)
        print(f"\nBase {args.referencia} no ar: {inseridos:,} estabelecimentos.")
        return 0
    except Exception as e:
        if carga_id is not None:
            await conn.execute(
                """
                UPDATE receita_cargas SET status = 'erro', observacao = $2
                 WHERE id = $1
                """,
                carga_id, f"{type(e).__name__}: {e}"[:500],
            )
        await conn.execute(f"DROP TABLE IF EXISTS {CARGA}")
        await conn.execute(STAGING_DROP)
        print(f"\nERRO: {type(e).__name__}: {e}")
        print("A base anterior continua no ar, intacta.")
        return 1
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Carga mensal da base de Dados Abertos do CNPJ (Prospecção)."
    )
    p.add_argument("--ufs", required=True, help="UFs de atuação, separadas por vírgula (ex.: SP,RJ)")
    p.add_argument("--referencia", required=True, help="Mês da base, para a tela (ex.: 2026-09)")
    p.add_argument("--pasta", required=True, help="Pasta com os ZIPs da Receita")
    p.add_argument("--baixar", metavar="URL", help="Espelho de onde baixar os ZIPs que faltarem")
    p.add_argument("--apagar-depois", action="store_true", help="Apaga cada ZIP depois de lido")
    p.add_argument("--manter-mei", action="store_true", help="Não descarta MEI")
    p.add_argument("--simular", action="store_true", help="Só conta, sem gravar")
    p.add_argument("--limite", type=int, default=0, help="Para depois de N estabelecimentos (ensaio)")
    args = p.parse_args()
    return asyncio.run(principal(args))


if __name__ == "__main__":
    sys.exit(main())
