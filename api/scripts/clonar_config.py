"""
HIPO — Copia a CONFIGURAÇÃO de uma base para outra base vazia (entrega 046).

Para que serve: a instância da MOS nasce com o schema completo e nenhum dado
de operação, mas com as mesmas tabelas de apoio da Controller MedSeg —
feriados, listas de domínio, CNAEs mapeados, tipos de reunião, tabela de
preço e todo o conteúdo da Universidade Corporativa. Decisão de 05/10/2026:
"vazia + configs copiadas".

O QUE COPIA (ordem de FK):
  dia_nao_util, verticais, origens, concorrentes, motivos_desfecho, cnaes,
  tipos_reuniao, tabela_preco_faixas,
  uc_trilhas, uc_trilha_cargos, uc_aulas, uc_materiais, uc_perguntas,
  uc_alternativas
  + com --com-base-receita: receita_municipios, receita_cnaes,
    receita_cargas, receita_estabelecimentos (Dados Abertos do CNPJ, que
    alimentam a tela de Prospecção)

O QUE NÃO COPIA, de propósito: usuários, contas, contatos, oportunidades,
tarefas, reuniões, propostas, progresso da UC, PDI, metas, telemetria,
relatórios. É a operação da outra empresa.

AUTORIA: toda coluna com FK para `usuarios` (criado_por, atualizado_por,
mapeado_por...) chega NULL. Os usuários da origem não existem no destino, e
apontar para eles quebraria a FK; NULL é o que o próprio banco faria com
ON DELETE SET NULL.

MATERIAIS DA UC (S3): a linha de `uc_materiais` guarda a chave do objeto.
Copiar só a linha faria as duas bases apontarem para o MESMO objeto — e
apagar o material na MOS apagaria o arquivo da MedSeg (uc_estudio chama
material.remover). Por isso, com --prefixo-s3 mos/, cada objeto é copiado
no S3 para `mos/<chave antiga>` e a linha nova aponta para a cópia. Sem
bucket configurado no destino, os materiais ficam de fora (com aviso) e o
resto da aula vai.

TRAVAS:
  - origem e destino não podem ser o mesmo banco (host + porta + nome);
  - o destino tem que estar VIRGEM de operação (contas, oportunidades,
    tarefas, reuniões, progresso da UC... todas vazias). As tabelas de
    configuração do destino são esvaziadas antes da cópia, e TRUNCATE com
    CASCADE numa base em uso levaria dado junto;
  - sem --executar, só mostra o plano (contagens) e não grava nada.

Tudo numa transação no destino: ou copia tudo, ou nada.

USO (na EC2, como ec2-user):
  cd /home/hipo/mos/api
  # DESTINO = o DATABASE_URL do ambiente (o .env da MOS)
  export DATABASE_URL="$(grep '^DATABASE_URL=' /home/hipo/mos/.env | cut -d= -f2-)"
  export S3_BUCKET_ANEXOS="$(grep '^S3_BUCKET_ANEXOS=' /home/hipo/mos/.env | cut -d= -f2-)"
  python3 -m scripts.clonar_config --origem-env /home/hipo/app/.env \\
      --prefixo-s3 mos/                       # plano
  python3 -m scripts.clonar_config --origem-env /home/hipo/app/.env \\
      --prefixo-s3 mos/ --executar            # grava
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

import asyncpg

TABELAS_CONFIG: tuple[str, ...] = (
    "dia_nao_util",
    "verticais",
    "origens",
    "concorrentes",
    "motivos_desfecho",
    "cnaes",
    "tipos_reuniao",
    "tabela_preco_faixas",
    "uc_trilhas",
    "uc_trilha_cargos",
    "uc_aulas",
    "uc_materiais",
    "uc_perguntas",
    "uc_alternativas",
)

TABELAS_RECEITA: tuple[str, ...] = (
    "receita_municipios",
    "receita_cnaes",
    "receita_cargas",
    "receita_estabelecimentos",
)

# Tabelas de OPERAÇÃO: todas precisam estar vazias no destino. Se alguma
# tiver linha, o destino não é uma base nova e o script se recusa.
TABELAS_OPERACAO: tuple[str, ...] = (
    "contas",
    "contatos",
    "oportunidades",
    "tarefas",
    "reunioes",
    "propostas",
    "parceiro_eventos",
    "uc_progresso",
    "uc_tentativas",
    "pdi_acoes",
    "metas_comerciais",
)

TABELA_MATERIAIS = "uc_materiais"


class CloneRecusado(Exception):
    """Trava de segurança: o clone não deve rodar nestas condições."""


# ── Funções puras ─────────────────────────────────────────────────────────

def ler_env(texto: str) -> dict[str, str]:
    """
    Lê um .env no formato que o systemd aceita (EnvironmentFile): CHAVE=valor
    por linha, # comenta, aspas simples ou duplas em volta são retiradas.
    Sem expansão de variável — o systemd também não faz.
    """
    saida: dict[str, str] = {}
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        if chave.startswith("export "):
            chave = chave[len("export "):].strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        saida[chave] = valor
    return saida


def identidade_do_banco(url: str) -> tuple[str, int, str]:
    """(host, porta, banco) — o que decide se duas URLs são o MESMO banco."""
    u = urlparse(url)
    return ((u.hostname or "localhost").lower(), u.port or 5432, (u.path or "/").lstrip("/"))


def mascarar(url: str) -> str:
    u = urlparse(url)
    if u.password:
        return url.replace(f":{u.password}@", ":****@", 1)
    return url


def validar_origem_destino(origem: str, destino: str) -> None:
    if not origem or not destino:
        raise CloneRecusado("Origem e destino precisam de DATABASE_URL.")
    if identidade_do_banco(origem) == identidade_do_banco(destino):
        raise CloneRecusado(
            "Origem e destino são o MESMO banco "
            f"({'/'.join(map(str, identidade_do_banco(destino)))}). "
            "O destino é o DATABASE_URL do ambiente; carregue o .env da instância nova."
        )


@dataclass(frozen=True)
class Coluna:
    nome: str
    tipo: str            # format_type(), ex.: 'uuid', 'character varying(120)'
    gerada: bool = False
    fk_usuarios: bool = False


def plano_de_colunas(
    origem: list[Coluna], destino: list[Coluna],
) -> tuple[list[str], list[str]]:
    """
    Decide o que vai no COPY: (colunas do destino, expressões do SELECT na
    origem), na mesma ordem.

    - só colunas que existem nos dois lados (uma migration aplicada em uma
      base e não na outra não derruba o clone por coluna a mais);
    - coluna gerada fica de fora: o banco recalcula;
    - FK para usuarios vira NULL tipado (o COPY binário exige o tipo).
    """
    nomes_origem = {c.nome for c in origem}
    colunas: list[str] = []
    exprs: list[str] = []
    for c in destino:
        if c.gerada or c.nome not in nomes_origem:
            continue
        colunas.append(c.nome)
        exprs.append(f"NULL::{c.tipo}" if c.fk_usuarios else _ident(c.nome))
    return colunas, exprs


def nova_chave_s3(prefixo: str, chave: str) -> str:
    """
    'mos/' + 'uc/aulas/<id>/<id>.pdf'. Idempotente: chave que já começa com o
    prefixo não ganha outro (rodar de novo não vira 'mos/mos/...').
    """
    prefixo = (prefixo or "").strip().lstrip("/")
    if prefixo and not prefixo.endswith("/"):
        prefixo += "/"
    if not prefixo or chave.startswith(prefixo):
        return chave
    return prefixo + chave


def _ident(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


# ── Banco ─────────────────────────────────────────────────────────────────

_SQL_COLUNAS = """
SELECT a.attname                                   AS nome,
       format_type(a.atttypid, a.atttypmod)        AS tipo,
       a.attgenerated <> ''                        AS gerada,
       EXISTS (
         SELECT 1 FROM pg_constraint k
          WHERE k.conrelid = a.attrelid
            AND k.contype = 'f'
            AND k.confrelid = 'usuarios'::regclass
            AND a.attnum = ANY (k.conkey)
       )                                           AS fk_usuarios
  FROM pg_attribute a
 WHERE a.attrelid = to_regclass($1)
   AND a.attnum > 0
   AND NOT a.attisdropped
 ORDER BY a.attnum
"""


async def colunas(conn: asyncpg.Connection, tabela: str) -> list[Coluna]:
    linhas = await conn.fetch(_SQL_COLUNAS, f"public.{tabela}")
    return [Coluna(r["nome"], r["tipo"], r["gerada"], r["fk_usuarios"]) for r in linhas]


async def contar(conn: asyncpg.Connection, tabela: str) -> int | None:
    if await conn.fetchval("SELECT to_regclass($1)", f"public.{tabela}") is None:
        return None
    return await conn.fetchval(f"SELECT count(*) FROM {_ident(tabela)}")


async def conferir_destino_virgem(conn: asyncpg.Connection) -> None:
    com_dado = []
    for t in TABELAS_OPERACAO:
        n = await contar(conn, t)
        if n is None:
            raise CloneRecusado(
                f"O destino não tem a tabela {t}. Aplique o schema.sql antes do clone."
            )
        if n:
            com_dado.append(f"{t}={n}")
    if com_dado:
        raise CloneRecusado(
            "O destino já tem operação (" + ", ".join(com_dado) + "). "
            "O clone só roda numa base nova: ele esvazia as tabelas de configuração "
            "do destino antes de copiar."
        )


async def _acertar_sequencias(conn: asyncpg.Connection, tabela: str) -> None:
    seqs = await conn.fetch(
        """
        SELECT a.attname AS coluna, pg_get_serial_sequence($1, a.attname) AS seq
          FROM pg_attribute a
         WHERE a.attrelid = to_regclass($1) AND a.attnum > 0 AND NOT a.attisdropped
        """,
        f"public.{tabela}",
    )
    for s in seqs:
        if not s["seq"]:
            continue
        col = _ident(s["coluna"])
        await conn.execute(
            f"SELECT setval($1, COALESCE((SELECT max({col}) FROM {_ident(tabela)}), 1), "
            f"(SELECT max({col}) IS NOT NULL FROM {_ident(tabela)}))",
            s["seq"],
        )


# Quantos blocos do COPY ficam em trânsito entre as duas conexões. Cada bloco
# tem algumas dezenas de KB; 64 seguram poucos MB na memória.
_FILA_COPY = 64


async def transmitir(
    origem: asyncpg.Connection, destino: asyncpg.Connection,
    consulta: str, tabela: str, colunas: list[str],
) -> None:
    """
    COPY da origem direto para o COPY do destino, bloco a bloco, sem passar
    por disco nem acumular a tabela na memória.

    Era um arquivo temporário: em 06/10/2026 a base da Receita (4,8 milhões
    de linhas) encheu o /tmp da EC2 (`OSError: [Errno 28] No space left on
    device`). Aqui uma fila limitada faz a leitura esperar a escrita.
    """
    fila: asyncio.Queue = asyncio.Queue(maxsize=_FILA_COPY)
    fim = object()

    async def ler() -> None:
        try:
            await origem.copy_from_query(consulta, output=fila.put, format="binary")
        finally:
            await fila.put(fim)

    async def blocos():
        while True:
            b = await fila.get()
            if b is fim:
                return
            yield b

    leitor = asyncio.create_task(ler())
    try:
        await destino.copy_to_table(tabela, source=blocos(), columns=colunas, format="binary")
    except BaseException:
        leitor.cancel()
        with contextlib.suppress(BaseException):
            await leitor
        raise
    await leitor  # erro do lado da origem sobe aqui


async def copiar_tabela(
    origem: asyncpg.Connection, destino: asyncpg.Connection, tabela: str,
) -> int:
    cols_o = await colunas(origem, tabela)
    cols_d = await colunas(destino, tabela)
    if not cols_o or not cols_d:
        raise CloneRecusado(f"Tabela {tabela} ausente na origem ou no destino.")
    nomes, exprs = plano_de_colunas(cols_o, cols_d)
    consulta = f"SELECT {', '.join(exprs)} FROM {_ident(tabela)}"
    await transmitir(origem, destino, consulta, tabela, nomes)
    await _acertar_sequencias(destino, tabela)
    return await destino.fetchval(f"SELECT count(*) FROM {_ident(tabela)}")


def _cliente_s3(regiao: str):
    import boto3  # import tardio: mesma regra de services/anexo.py
    return boto3.client("s3", region_name=regiao)


async def reapontar_materiais(
    destino: asyncpg.Connection, *, prefixo: str, bucket_origem: str,
    bucket_destino: str, s3=None, regiao: str = "eu-central-1",
) -> int:
    """
    Copia cada objeto de material para a chave com prefixo e atualiza a
    linha. Roda DENTRO da transação do clone: se uma cópia falhar, nenhuma
    linha fica apontando para objeto que não existe.
    """
    s3 = s3 or _cliente_s3(regiao)
    linhas = await destino.fetch(f"SELECT id, chave_s3 FROM {TABELA_MATERIAIS}")
    n = 0
    for r in linhas:
        nova = nova_chave_s3(prefixo, r["chave_s3"])
        if nova == r["chave_s3"] and bucket_origem == bucket_destino:
            continue
        s3.copy_object(
            Bucket=bucket_destino, Key=nova,
            CopySource={"Bucket": bucket_origem, "Key": r["chave_s3"]},
        )
        await destino.execute(
            f"UPDATE {TABELA_MATERIAIS} SET chave_s3 = $1 WHERE id = $2", nova, r["id"],
        )
        n += 1
    return n


@dataclass
class Opcoes:
    com_receita: bool = False
    prefixo_s3: str = ""
    bucket_origem: str = ""
    bucket_destino: str = ""
    regiao: str = "eu-central-1"


def tabelas_do_clone(op: Opcoes) -> list[str]:
    tabelas = list(TABELAS_CONFIG)
    if not op.bucket_destino:
        # Sem bucket no destino a tela não serve o arquivo; copiar a linha
        # só criaria material quebrado.
        tabelas.remove(TABELA_MATERIAIS)
    if op.com_receita:
        tabelas += list(TABELAS_RECEITA)
    return tabelas


async def clonar(
    origem: asyncpg.Connection, destino: asyncpg.Connection, op: Opcoes,
    *, executar: bool, s3=None, log=print,
) -> dict[str, int]:
    await conferir_destino_virgem(destino)
    tabelas = tabelas_do_clone(op)
    if TABELA_MATERIAIS not in tabelas:
        log("AVISO: destino sem S3_BUCKET_ANEXOS -> materiais da UC NAO serao copiados.")
    elif not op.prefixo_s3 and op.bucket_origem == op.bucket_destino:
        raise CloneRecusado(
            "Mesmo bucket na origem e no destino exige --prefixo-s3 (ex.: mos/). "
            "Sem ele, apagar um material numa base apaga o arquivo da outra."
        )

    log(f"{'tabela':28} {'origem':>10} {'destino hoje':>13}")
    for t in tabelas:
        log(f"{t:28} {await contar(origem, t) or 0:>10} {await contar(destino, t) or 0:>13}")
    if not executar:
        log("\nPlano apenas. Nada gravado. Rode de novo com --executar.")
        return {}

    resultado: dict[str, int] = {}
    async with destino.transaction():
        # Esvazia na ordem inversa (filhas antes das mães). O CASCADE só
        # alcança tabelas de operação, que a trava acima garantiu vazias.
        await destino.execute(
            "TRUNCATE TABLE " + ", ".join(_ident(t) for t in reversed(tabelas)) + " CASCADE"
        )
        for t in tabelas:
            resultado[t] = await copiar_tabela(origem, destino, t)
            log(f"  copiada {t}: {resultado[t]}")
        if TABELA_MATERIAIS in tabelas and resultado.get(TABELA_MATERIAIS):
            n = await reapontar_materiais(
                destino, prefixo=op.prefixo_s3, bucket_origem=op.bucket_origem,
                bucket_destino=op.bucket_destino, s3=s3, regiao=op.regiao,
            )
            log(f"  materiais copiados no S3 (prefixo {op.prefixo_s3!r}): {n}")
    return resultado


# ── CLI ───────────────────────────────────────────────────────────────────

async def _principal(args) -> int:
    with open(args.origem_env, encoding="utf-8") as f:
        env_origem = ler_env(f.read())
    url_origem = env_origem.get("DATABASE_URL", "")
    url_destino = os.environ.get("DATABASE_URL", "")
    validar_origem_destino(url_origem, url_destino)

    op = Opcoes(
        com_receita=args.com_base_receita,
        prefixo_s3=args.prefixo_s3,
        bucket_origem=env_origem.get("S3_BUCKET_ANEXOS", ""),
        bucket_destino=os.environ.get("S3_BUCKET_ANEXOS", ""),
        regiao=os.environ.get("AWS_REGION", "eu-central-1"),
    )
    print(f"ORIGEM : {mascarar(url_origem)}")
    print(f"DESTINO: {mascarar(url_destino)}\n")

    origem = await asyncpg.connect(url_origem)
    destino = await asyncpg.connect(url_destino)
    try:
        # A origem é só lida, e numa transação somente-leitura: nenhum erro
        # de código aqui consegue escrever na base da MedSeg.
        async with origem.transaction(readonly=True, isolation="repeatable_read"):
            await clonar(origem, destino, op, executar=args.executar)
    finally:
        await origem.close()
        await destino.close()
    if args.executar:
        print("\nClone concluído.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Copia a configuração de uma base HIPO para outra base nova.")
    ap.add_argument("--origem-env", required=True, help="Caminho do .env da base de ORIGEM")
    ap.add_argument("--prefixo-s3", default="", help="Prefixo dos materiais da UC copiados (ex.: mos/)")
    ap.add_argument("--com-base-receita", action="store_true",
                    help="Copia também a base de Dados Abertos do CNPJ (Prospecção)")
    ap.add_argument("--executar", action="store_true", help="Grava. Sem isto, só mostra o plano.")
    args = ap.parse_args(argv)
    try:
        return asyncio.run(_principal(args))
    except CloneRecusado as e:
        print(f"RECUSADO: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
