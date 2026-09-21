"""
HIPO — Amostra de enriquecimento: o plano pago se paga?

POR QUE ESTE SCRIPT EXISTE

A LeadCNPJ cobra por mês. O que decide se vale é UM número: em quantas
empresas da SUA carteira a fonte devolve o que você não tem — quadro de
pessoal, acima de tudo. Material comercial não responde isso; uma amostra
da base real responde.

Ele roda contra as contas que já estão no HIPO, mede o preenchimento campo
a campo e escreve um CSV. Com 100 CNPJs você sabe a taxa de verdade antes
de renovar a assinatura.

O QUE ELE NÃO FAZ

Não altera nenhuma conta. Só lê. As consultas ficam registradas em
`conta_enriquecimentos` (é o cache), então o que for medido aqui não será
pago de novo quando alguém abrir a conta na tela dentro do TTL.

COMO RODAR

Na EC2, como o usuário do app:

    sudo -iu hipo
    cd /home/hipo/app/api
    # Confira o banco ANTES. O seed não tem safeguard como o conftest tem.
    echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'
    python -m scripts.amostrar_enriquecimento --quantidade 100

Opções:
    --quantidade N     quantas contas consultar (padrão 50)
    --fontes a,b       sobrepõe ENRIQUECIMENTO_FONTES só nesta execução
    --pausa S          segundos entre consultas (padrão 2.5 — o plano
                       Growth permite 30 por minuto)
    --saida arquivo    CSV de saída (padrão amostra_enriquecimento.csv)
    --sem-cache        ignora o cache e vai à fonte em todas
    --so-sem-dado      só contas sem nº de funcionários e sem CNAE, que é
                       onde o enriquecimento tem o que acrescentar
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from collections import Counter

import asyncpg

from config import settings
from services import cnpj as cnpj_svc
from services.enriquecimento import fontes as fontes_mod
from services.enriquecimento import modelo
from services.enriquecimento.persistencia import NORMALIZADORES, _do_cache, _registrar

# Os campos medidos. A ordem é a do CSV, e `num_funcionarios` vem primeiro
# porque é o único que a fonte gratuita não tem — é ele que justifica pagar.
CAMPOS = (
    "num_funcionarios",
    "cnae_codigo",
    "razao_social",
    "nome_fantasia",
    "porte",
    "situacao_cadastral",
    "data_abertura",
    "capital_social",
    "cep",
    "cidade",
    "uf",
    "telefone",
    "email",
)


def mascarar_url(url: str) -> str:
    """Esconde a senha antes de qualquer coisa ir para a tela ou para o log."""
    return re.sub(r":[^:@/]*@", ":****@", url or "")


async def consultar_sem_gravar(conn, cnpj: str, fontes: list[str], usar_cache: bool):
    """
    Igual ao fluxo da aplicação, mas sem tocar em `contas`.

    Devolve (dados, avisos, foi_a_rede).
    """
    resultados = []
    avisos = []
    foi_a_rede = False
    ttl = int(getattr(settings, "ENRIQUECIMENTO_TTL_DIAS", 90) or 0)

    for fonte in fontes:
        payload = await _do_cache(conn, cnpj, fonte, ttl) if usar_cache else None
        if payload is None:
            buscador = fontes_mod.BUSCADORES.get(fonte)
            if buscador is None:
                continue
            payload, erro = await buscador(cnpj)
            foi_a_rede = True
            await _registrar(conn, cnpj, fonte, payload is not None, payload, erro, None)
            if payload is None:
                avisos.append(f"{fonte}: {erro}")
                continue
        normalizador = NORMALIZADORES.get(fonte)
        if normalizador:
            try:
                resultados.append(normalizador(payload))
            except Exception as e:  # pragma: no cover - script operacional
                avisos.append(f"{fonte}: falhou ao ler o payload ({type(e).__name__})")

    return modelo.mesclar(*resultados), avisos, foi_a_rede


async def principal(args) -> int:
    fontes = (
        [f.strip() for f in args.fontes.split(",") if f.strip()]
        if args.fontes
        else fontes_mod.fontes_habilitadas()
    )
    fontes = [f for f in fontes if fontes_mod.configurada(f)]
    if not fontes:
        print("Nenhuma fonte configurada. Confira ENRIQUECIMENTO_FONTES e "
              "LEADCNPJ_API_KEY no .env.")
        return 1

    print(f"Banco : {mascarar_url(settings.DATABASE_URL)}")
    print(f"Fontes: {', '.join(fontes)}")
    print(f"Amostra: {args.quantidade} conta(s), pausa de {args.pausa}s\n")

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        filtro = ""
        if args.so_sem_dado:
            filtro = "AND num_funcionarios IS NULL AND cnae_codigo IS NULL"
        linhas = await conn.fetch(
            f"""
            SELECT id, cnpj, razao_social, num_funcionarios, cnae_codigo
              FROM contas
             WHERE ativo {filtro}
             ORDER BY criado_em DESC
             LIMIT $1
            """,
            args.quantidade,
        )
        if not linhas:
            print("Nenhuma conta encontrada com esse filtro.")
            return 1

        preenchidos = Counter()
        consultadas = 0
        nao_encontradas = 0
        idas_a_rede = 0
        saida = []

        for i, linha in enumerate(linhas, start=1):
            cnpj = linha["cnpj"]
            # O DV é conferido aqui pelo mesmo motivo da tela: consulta com
            # CNPJ errado custa crédito e volta 404. A carga da Oraculus
            # tinha sete desses.
            if not cnpj_svc.valido(cnpj):
                print(f"[{i}/{len(linhas)}] {cnpj} — DV inválido, pulando")
                continue

            dados, avisos, foi_a_rede = await consultar_sem_gravar(
                conn, cnpj, fontes, usar_cache=not args.sem_cache
            )
            consultadas += 1
            idas_a_rede += 1 if foi_a_rede else 0

            registro = {
                "cnpj": cnpj,
                "razao_social_hipo": linha["razao_social"],
                "encontrado": "sim" if dados else "nao",
                "fonte": dados.fonte if dados else "",
                "avisos": " | ".join(avisos),
                "socios": len(dados.socios) if dados else 0,
            }

            if dados is None:
                nao_encontradas += 1
            else:
                for campo in CAMPOS:
                    valor = getattr(dados, campo, None)
                    if valor is not None:
                        preenchidos[campo] += 1
                    registro[campo] = valor if valor is not None else ""

            saida.append(registro)

            marca = "ok " if dados else "-- "
            func = (dados.num_funcionarios if dados else None)
            print(
                f"[{i}/{len(linhas)}] {marca}{cnpj_svc.formatar(cnpj)} "
                f"{(linha['razao_social'] or '')[:40]:<40} "
                f"funcionarios={func if func is not None else '-'}"
            )

            if foi_a_rede and i < len(linhas):
                await asyncio.sleep(args.pausa)

        campos_csv = ["cnpj", "razao_social_hipo", "encontrado", "fonte",
                      "socios", *CAMPOS, "avisos"]
        with open(args.saida, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=campos_csv, extrasaction="ignore")
            escritor.writeheader()
            for registro in saida:
                escritor.writerow(registro)

        print("\n" + "=" * 62)
        print(f" RESULTADO — {consultadas} consulta(s), {idas_a_rede} ida(s) à rede")
        print("=" * 62)
        if consultadas:
            print(f" CNPJ não encontrado na fonte: {nao_encontradas}")
            print("\n Preenchimento por campo:")
            for campo in CAMPOS:
                qtd = preenchidos[campo]
                pct = 100 * qtd / consultadas
                barra = "#" * int(pct / 5)
                print(f"   {campo:<22} {qtd:>4}/{consultadas}  {pct:5.1f}%  {barra}")

            func = preenchidos["num_funcionarios"]
            pct_func = 100 * func / consultadas
            print("\n" + "-" * 62)
            print(" O NÚMERO QUE DECIDE A ASSINATURA")
            print(f"   Quadro de pessoal veio em {func} de {consultadas} "
                  f"({pct_func:.1f}%).")
            if pct_func >= 60:
                print("   Cobertura alta: a fonte paga está entregando o que a")
                print("   Receita não tem.")
            elif pct_func >= 30:
                print("   Cobertura média: vale conferir se as que vieram são as")
                print("   empresas que você realmente prospecta.")
            else:
                print("   Cobertura baixa: o plano está entregando pouco além do")
                print("   que a BrasilAPI entrega de graça.")
            print("-" * 62)

        print(f"\n CSV: {args.saida}")
        return 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Mede o enriquecimento numa amostra real.")
    p.add_argument("--quantidade", type=int, default=50)
    p.add_argument("--fontes", default="")
    p.add_argument("--pausa", type=float, default=2.5)
    p.add_argument("--saida", default="amostra_enriquecimento.csv")
    p.add_argument("--sem-cache", action="store_true", dest="sem_cache")
    p.add_argument("--so-sem-dado", action="store_true", dest="so_sem_dado")
    args = p.parse_args()
    return asyncio.run(principal(args))


if __name__ == "__main__":
    sys.exit(main())
