"""
HIPO — Limpa os valores que foram gravados como texto de dicionário.

O QUE ACONTECEU

A LeadCNPJ devolve `{"codigo": "02", "descricao": "Ativa"}` onde a
BrasilAPI devolve `"ATIVA"`. Antes do conserto, o `str()` do dicionário
inteiro ia para a coluna — e, como as colunas são curtas, chegava
cortado:

    porte              = {'codigo': '03', 'descricao': 'Empresa d
    situacao_cadastral = {'codigo': '02', 'descricao': 'Ativa', '

POR QUE "ATUALIZAR DADOS PÚBLICOS" NÃO RESOLVE SOZINHO

Esta é a parte que surpreende. O enriquecimento **não sobrescreve campo
que já tem valor** — é a regra que protege o trabalho humano, e ela não
sabe distinguir "digitado por alguém" de "lixo gravado por um bug".
Então a consulta nova chega, vê que `porte` está preenchido, e devolve a
diferença como *divergência* em vez de corrigir. O campo continua sujo
para sempre, a menos que alguém clique em "usar os dados da fonte" conta
por conta.

Este script desfaz isso em massa.

COMO ELE DECIDE

  * Descrição COMPLETA no texto (o dicionário não foi cortado): extrai e
    grava o texto limpo. Conserta sem gastar consulta.
  * Descrição TRUNCADA: grava NULL. É a única saída honesta — o texto
    completo não está mais lá para recuperar. E NULL tem uma vantagem:
    campo vazio o enriquecimento PREENCHE, então a próxima consulta
    conserta sozinha.

Nunca toca em valor que não tem cara de dicionário. Rodar duas vezes não
faz nada na segunda.

COMO RODAR

    ssh -t ... ec2-user@63.179.88.212
    sudo -iu hipo          # ou use o carregar-verticais.sh como modelo
    cd /home/hipo/app/api
    python3 -m scripts.limpar_dicionarios_gravados --simular
    python3 -m scripts.limpar_dicionarios_gravados

Mais simples: `bash /tmp/limpar-dicionarios.sh`, que acha o Python certo
e carrega o .env sozinho.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys

import asyncpg

from config import settings

# Colunas de texto que o enriquecimento preenche, por tabela. `cnaes` e
# `conta_socios` entram porque a descrição e a qualificação vieram pelo
# mesmo caminho.
ALVOS = {
    "contas": (
        "id",
        ["razao_social", "nome_fantasia", "porte", "situacao_cadastral",
         "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
         "telefone", "telefone_2", "email"],
    ),
    "conta_socios": ("id", ["nome", "qualificacao", "faixa_etaria"]),
    "cnaes": ("codigo", ["descricao"]),
}

# `{'chave': ...` ou `{"chave": ...` — com ou sem o fecha-chaves, porque o
# corte da coluna costuma levar o fim embora.
PARECE_DICT = re.compile(r"^\s*\{\s*['\"]\w+['\"]\s*:")

# A descrição inteira, exigindo a aspa de fechamento: se ela não estiver
# lá, o texto foi cortado no meio e não dá para confiar no que sobrou.
DESCRICAO = re.compile(
    r"['\"](?:descricao|description|nome|name|texto|label)['\"]\s*:\s*"
    r"'([^']*)'\s*[,}]"
    r"|"
    r"['\"](?:descricao|description|nome|name|texto|label)['\"]\s*:\s*"
    r'"([^"]*)"\s*[,}]'
)


def limpar(valor: str | None) -> tuple[bool, str | None]:
    """
    (precisa_mexer, novo_valor).

    >>> limpar("ATIVA")
    (False, None)
    >>> limpar("{'codigo': '49', 'descricao': 'Sócio-Administrador'}")
    (True, 'Sócio-Administrador')
    >>> limpar("{'codigo': '03', 'descricao': 'Empresa d")
    (True, None)
    """
    if not valor or not PARECE_DICT.match(valor):
        return False, None
    achado = DESCRICAO.search(valor)
    if achado:
        texto = achado.group(1) if achado.group(1) is not None else achado.group(2)
        texto = (texto or "").strip()
        if texto:
            return True, texto
    # Cortado antes do fim da descrição: não há texto confiável a salvar.
    return True, None


def mascarar_url(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


async def principal(args) -> int:
    print(f"Banco : {mascarar_url(settings.DATABASE_URL)}")
    print(f"Modo  : {'SIMULAÇÃO (nada será gravado)' if args.simular else 'GRAVANDO'}")
    print()

    conn = await asyncpg.connect(settings.DATABASE_URL)
    total_recuperados = 0
    total_nulos = 0
    try:
        for tabela, (chave, colunas) in ALVOS.items():
            existentes = {
                r["column_name"]
                for r in await conn.fetch(
                    """
                    SELECT column_name FROM information_schema.columns
                     WHERE table_name = $1
                    """,
                    tabela,
                )
            }
            colunas = [c for c in colunas if c in existentes]
            if not colunas:
                continue

            onde = " OR ".join(f"{c} LIKE '{{%'" for c in colunas)
            linhas = await conn.fetch(
                f"SELECT {chave}, {', '.join(colunas)} FROM {tabela} WHERE {onde}"
            )
            if not linhas:
                print(f"{tabela}: nada sujo.")
                continue

            print(f"{tabela}: {len(linhas)} linha(s) com valor de dicionário")
            recuperados = nulos = 0
            for linha in linhas:
                mudancas: dict[str, str | None] = {}
                for coluna in colunas:
                    mexer, novo = limpar(linha[coluna])
                    if not mexer:
                        continue
                    mudancas[coluna] = novo
                    if novo is None:
                        nulos += 1
                    else:
                        recuperados += 1
                    if args.detalhar:
                        cru = (linha[coluna] or "")[:42]
                        print(f"   {coluna:<20} {cru!r}")
                        print(f"   {'':<20} -> {novo!r}")
                if not mudancas or args.simular:
                    continue
                sets = ", ".join(
                    f"{c} = ${i + 2}" for i, c in enumerate(mudancas)
                )
                await conn.execute(
                    f"UPDATE {tabela} SET {sets} WHERE {chave} = $1",
                    linha[chave], *mudancas.values(),
                )
            print(f"   {recuperados} campo(s) recuperado(s) do texto")
            print(f"   {nulos} campo(s) zerado(s) (estavam cortados)")
            total_recuperados += recuperados
            total_nulos += nulos

        print()
        print("=" * 62)
        print(f" {total_recuperados} campo(s) recuperado(s)")
        print(f" {total_nulos} campo(s) zerado(s)")
        print("=" * 62)
        if total_nulos:
            print()
            print(" Os zerados ficaram NULOS de propósito: campo vazio é o")
            print(" único que o enriquecimento preenche. Eles voltam sozinhos")
            print(" na próxima consulta daquela conta.")
        if args.simular:
            print()
            print(" NADA FOI GRAVADO. Rode sem --simular para valer.")
        return 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Limpa valores gravados como texto de dicionário."
    )
    p.add_argument("--simular", action="store_true",
                   help="mostra o que faria, sem gravar")
    p.add_argument("--detalhar", action="store_true",
                   help="mostra cada valor antes e depois")
    return asyncio.run(principal(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
