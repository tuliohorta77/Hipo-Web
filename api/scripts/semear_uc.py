"""
HIPO — UC: carga das trilhas iniciais (scripts/uc_conteudo.py).

Substitui o scripts/semear_uc_nr.py da entrega 029, que carregava só a
trilha de NR. Hoje carrega todas as trilhas de scripts/uc_conteudo.py,
inclusive as de uso do HIPO por função (scripts/uc_conteudo_hipo.py), cujas
aulas trazem o tour guiado (coluna uc_aulas.tour, migration 023).

O QUE A CARGA GARANTE

  * Ids fixos: rodar de novo não duplica trilha, aula nem PDF.
  * Trilha nova nasce em rascunho, recebe as aulas e os cargos e só então é
    publicada (a regra do estúdio: trilha não publica vazia).
  * Trilha que já existe só é tocada com --atualizar: título, descrição e o
    texto das aulas são reescritos SEM subir versão (correção de redação não
    reabre aula para quem concluiu), e as aulas do conteúdo assumem as
    posições 1..n. Aula que a gestão criou pelo estúdio vai para o fim, na
    ordem em que estava.
  * Cargos: só acrescenta o que falta. Prazo e obrigação que a gestão mudou
    no estúdio ficam como estão.
  * PDFs: anexa o que não estiver anexado (pelo nome exibido).
  * Quiz (024): as 7 perguntas de cada aula são regravadas, com ids fixos
    (uuid5 da aula + posição), e a nota mínima vai para 85. Quiz que a
    gestão mexeu no estúdio numa aula DESTA carga volta ao do conteúdo.

USO (na EC2; o infra/semear-uc.sh prepara o ambiente):
  python -m scripts.semear_uc --simular --pdfs /tmp/uc
  python -m scripts.semear_uc --atualizar --pdfs /tmp/uc

DATABASE_URL não tem o safeguard do conftest: o host aparece mascarado e a
gravação pede confirmação.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from uuid import NAMESPACE_URL, UUID, uuid5

from scripts.uc_conteudo import (
    CARGOS_OBRIGATORIOS, CARGOS_OPCIONAIS, PDFS, TRILHAS,
)


# ── Conferência (também usada pelos testes) ──────────────────────────

def conferir() -> list[str]:
    """Problemas de forma no conteúdo. Lista vazia = pronto para carregar."""
    erros: list[str] = []
    ids = [t["id"] for t in TRILHAS] + [a["id"] for t in TRILHAS for a in t["aulas"]]
    if len(ids) != len(set(ids)):
        erros.append("id repetido entre trilhas e aulas")
    from services import uc as regras

    for t in TRILHAS:
        try:
            regras.validar_pilar(t["pilar"])
            regras.validar_reforca(t.get("reforca"))
            for cargo in (*t.get("obrigatorios", CARGOS_OBRIGATORIOS),
                          *t.get("opcionais", CARGOS_OPCIONAIS)):
                regras.validar_cargo(cargo)
        except regras.ConteudoInvalido as e:
            erros.append(f"{t['titulo']}: {e}")
        if set(t.get("obrigatorios", CARGOS_OBRIGATORIOS)) & set(t.get("opcionais", CARGOS_OPCIONAIS)):
            erros.append(f"{t['titulo']}: cargo obrigatório e opcional ao mesmo tempo")
        if not t["titulo"].strip() or len(t["titulo"]) > 160:
            erros.append(f"{t['titulo']!r}: título vazio ou acima de 160")
        if not t["aulas"]:
            erros.append(f"{t['titulo']}: trilha sem aula")
        for i, a in enumerate(t["aulas"], start=1):
            rot = f"{t['titulo']}, aula {i}"
            if not a["titulo"].strip() or len(a["titulo"]) > 160:
                erros.append(f"{rot}: título vazio ou acima de 160")
            if not (1 <= a["duracao_min"] <= 600):
                erros.append(f"{rot}: duração fora de 1..600")
            md = a["conteudo_md"]
            if not md.lstrip().startswith("## "):
                erros.append(f"{rot}: o texto deve abrir com um título de seção")
            if re.search(r"(?m)^# ", md):
                erros.append(f"{rot}: '# ' de nível 1 é o título da aula, não do texto")
            if re.search(r"(?m)^\|", md):
                erros.append(f"{rot}: tabela não é suportada pelo texto da aula")
            if a.get("pdf") and a["pdf"] not in PDFS:
                erros.append(f"{rot}: pdf desconhecido")
            try:
                regras.validar_tour(a.get("tour"))
            except regras.ConteudoInvalido as e:
                erros.append(f"{rot}: {e}")
            try:
                regras.validar_quiz(quiz_do_conteudo(a))
            except regras.ConteudoInvalido as e:
                erros.append(f"{rot}: {e}")
    return erros


def _mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url)


# ── Carga ────────────────────────────────────────────────────────────

def _tour_json(a: dict) -> str | None:
    from services import uc as regras

    tour = regras.validar_tour(a.get("tour"))
    return json.dumps(tour, ensure_ascii=False) if tour else None


def quiz_do_conteudo(a: dict) -> list[dict]:
    """O quiz da aula no formato do estúdio ({texto, correta})."""
    return [
        {"enunciado": q["enunciado"],
         "alternativas": [{"texto": texto, "correta": correta} for texto, correta in q["alternativas"]]}
        for q in a.get("quiz", [])
    ]


def _ids_do_quiz(aula_id: UUID):
    """Ids fixos: rodar a carga de novo não troca o id de pergunta nenhuma."""
    def ids(j: int, k: int | None) -> UUID:
        sufixo = f"p{j}" if k is None else f"p{j}a{k}"
        return uuid5(NAMESPACE_URL, f"hipo:uc:{aula_id}:{sufixo}")
    return ids


async def _gravar_aulas(conn, t: dict) -> None:
    """Upsert das aulas e posições 1..n; aulas de fora do conteúdo vão para o fim."""
    ids = [a["id"] for a in t["aulas"]]
    for ordem, a in enumerate(t["aulas"], start=1):
        await conn.execute(
            """
            INSERT INTO uc_aulas (id, trilha_id, ordem, titulo, resumo,
                                  conteudo_md, duracao_min, tour, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, 'publicada')
            ON CONFLICT (id) DO UPDATE
               SET ordem = EXCLUDED.ordem, titulo = EXCLUDED.titulo,
                   resumo = EXCLUDED.resumo, conteudo_md = EXCLUDED.conteudo_md,
                   duracao_min = EXCLUDED.duracao_min, tour = EXCLUDED.tour,
                   atualizado_em = NOW()
            """,
            a["id"], t["id"], ordem, a["titulo"], a["resumo"],
            a["conteudo_md"], a["duracao_min"], _tour_json(a),
        )
        from routers.uc_estudio import gravar_quiz
        from services import uc as regras

        await gravar_quiz(conn, a["id"], regras.validar_quiz(quiz_do_conteudo(a)),
                          ids=_ids_do_quiz(a["id"]))
    # A UNIQUE (trilha_id, ordem) é DEFERRABLE INITIALLY DEFERRED: dentro da
    # transação as posições podem colidir de passagem; o que vale é o fim.
    await conn.execute(
        """
        UPDATE uc_aulas a SET ordem = n.nova
          FROM (SELECT id, $3::int + row_number() OVER (ORDER BY ordem, criado_em) AS nova
                  FROM uc_aulas
                 WHERE trilha_id = $1 AND NOT (id = ANY($2::uuid[]))) n
         WHERE a.id = n.id
        """,
        t["id"], ids, len(ids),
    )


async def _gravar_cargos(conn, t: dict) -> None:
    for cargo in t.get("obrigatorios", CARGOS_OBRIGATORIOS):
        await conn.execute(
            """
            INSERT INTO uc_trilha_cargos (trilha_id, cargo, obrigatoria, prazo_dias)
            VALUES ($1, $2, TRUE, $3) ON CONFLICT DO NOTHING
            """,
            t["id"], cargo, t["prazo_dias"],
        )
    for cargo in t.get("opcionais", CARGOS_OPCIONAIS):
        await conn.execute(
            """
            INSERT INTO uc_trilha_cargos (trilha_id, cargo, obrigatoria, prazo_dias)
            VALUES ($1, $2, FALSE, NULL) ON CONFLICT DO NOTHING
            """,
            t["id"], cargo,
        )


async def carregar(conn, pasta_pdfs: Path | None, atualizar: bool, simular: bool) -> list[str]:
    """Grava as trilhas. Devolve as linhas do relatório (também impressas)."""
    from services import uc_material

    relatorio: list[str] = []

    def dizer(linha: str) -> None:
        relatorio.append(linha)
        print(linha)

    for t in TRILHAS:
        existe = await conn.fetchval("SELECT 1 FROM uc_trilhas WHERE id = $1", t["id"])
        if existe and not atualizar:
            dizer(f"{t['titulo']}: já existe, não mexi (use --atualizar).")
        elif simular:
            dizer(f"{t['titulo']}: {'atualizaria' if existe else 'criaria'} com {len(t['aulas'])} aulas.")
        else:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO uc_trilhas (id, titulo, descricao, pilar, reforca, status)
                    VALUES ($1, $2, $3, $4, $5, 'rascunho')
                    ON CONFLICT (id) DO UPDATE
                       SET titulo = EXCLUDED.titulo, descricao = EXCLUDED.descricao,
                           reforca = EXCLUDED.reforca, atualizado_em = NOW()
                    """,
                    t["id"], t["titulo"], t["descricao"], t["pilar"], t.get("reforca"),
                )
                await _gravar_aulas(conn, t)
                await _gravar_cargos(conn, t)
                if not existe:
                    await conn.execute(
                        "UPDATE uc_trilhas SET status = 'publicada' WHERE id = $1", t["id"],
                    )
            dizer(f"{t['titulo']}: {'atualizada' if existe else 'criada e publicada'}, {len(t['aulas'])} aulas.")

        for a in t["aulas"]:
            chave = a.get("pdf")
            if not chave:
                continue
            nome_exibido, arquivo = PDFS[chave]
            caminho = pasta_pdfs / arquivo if pasta_pdfs else None
            nome = uc_material.nome_seguro(nome_exibido, ".pdf")
            ja = await conn.fetchval(
                "SELECT 1 FROM uc_materiais WHERE aula_id = $1 AND nome_original = $2",
                a["id"], nome,
            )
            if ja:
                dizer(f"  material já anexado: {nome}")
                continue
            if caminho is None or not caminho.is_file():
                dizer(f"  sem o arquivo {arquivo}: '{a['titulo']}' fica sem material")
                continue
            if simular:
                dizer(f"  anexaria {caminho} em '{a['titulo']}'")
                continue
            if not await conn.fetchval("SELECT 1 FROM uc_aulas WHERE id = $1", a["id"]):
                dizer(f"  aula '{a['titulo']}' não existe no banco: material não anexado")
                continue
            problemas = uc_material.problemas()
            if problemas:
                dizer("  S3 indisponível, PDF não anexado: " + "; ".join(problemas))
                continue
            conteudo = caminho.read_bytes()
            uc_material.validar_tamanho(len(conteudo))
            material_id = await conn.fetchval("SELECT gen_random_uuid()")
            chave_s3 = uc_material.chave_do_objeto(a["id"], material_id, ".pdf")
            uc_material.subir(chave_s3, conteudo, "application/pdf")
            await conn.execute(
                """
                INSERT INTO uc_materiais (id, aula_id, chave_s3, nome_original, tipo_mime, bytes)
                VALUES ($1, $2, $3, $4, 'application/pdf', $5)
                """,
                material_id, a["id"], chave_s3, nome, len(conteudo),
            )
            dizer(f"  anexado: {nome} ({len(conteudo) // 1024} KB)")
    return relatorio


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Carga das trilhas iniciais da UC.")
    ap.add_argument("--pdfs", type=Path, help="pasta com os PDFs de apoio")
    ap.add_argument("--atualizar", action="store_true")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--sim", action="store_true", help="não pergunta (para scripts)")
    args = ap.parse_args(argv)

    erros = conferir()
    if erros:
        print("Conteúdo com problema:\n  " + "\n  ".join(erros))
        return 1
    if args.pdfs is not None and not args.pdfs.is_dir():
        print(f"Pasta de PDFs não encontrada: {args.pdfs}")
        return 1

    import asyncpg
    from config import settings

    print(f"Banco: {_mascarar(settings.DATABASE_URL)}")
    if not args.simular and not args.sim:
        if input("Gravar nesse banco? [s/N] ").strip().lower() != "s":
            print("Cancelado.")
            return 0

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        await carregar(conn, args.pdfs, args.atualizar, args.simular)
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
