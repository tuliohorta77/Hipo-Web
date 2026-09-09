"""
HIPO — Dá baixa nas tarefas de e-mail que a carga do CRM Omie subiu em aberto.

POR QUE ESTE SCRIPT EXISTE
  No CRM Omie, o registro de e-mail era só uma anotação: o envio já tinha
  acontecido quando a linha nasceu, e não existia campo "Realizada" para ele.
  A carga trouxe essas linhas como tarefa `tipo='email'` com `concluida_em`
  nulo, então elas apareceram no HIPO como tarefa em aberto — várias já
  atrasadas em quase um ano. É dívida de conversão, não trabalho pendente.

O QUE ELE FAZ
  Mapeia toda tarefa `tipo='email'` que veio da carga (marca de importação na
  descrição) e está em aberto — sem `concluida_em` e sem `cancelada_em` — grava
  o mapeamento num CSV e fecha cada uma com:

      concluida_em = prazo      (a data/hora do e-mail no Omie)
      resultado    = nota curta dizendo que a baixa é retroativa

  `prazo` é a data em que o e-mail foi registrado na origem, que é a mesma
  regra usada para as tarefas que já entraram concluídas. Fechar com a data de
  hoje empilharia dezenas de conclusões num dia só e mentiria no resumo de
  produção.

O QUE ELE NÃO FAZ
  Não encosta em tarefa criada à mão no HIPO: o filtro é a marca da carga.
  Não toca em cancelada, não cria tarefa sucessora (é histórico, não fila) e
  não mexe na oportunidade. Rodar de novo acha 0 — o filtro exige aberta.

USO
  python -m scripts.fechar_tarefas_email_crm_omie            # dry-run
  python -m scripts.fechar_tarefas_email_crm_omie --commit   # grava
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg

MARCA_PADRAO = "[importado do CRM Omie em 2026-09-01 — tarefa:"
TIPO = "email"
FUSO = ZoneInfo("America/Sao_Paulo")
CSV_PADRAO = "/tmp/tarefas_email_baixa.csv"

SELECT_CANDIDATAS = """
    SELECT
        t.id,
        t.titulo,
        t.prazo,
        t.criado_em,
        t.descricao,
        u.nome  AS responsavel,
        o.numero AS oportunidade,
        c_opp.razao_social AS conta_oportunidade,
        c_par.razao_social AS conta_parceiro
    FROM tarefas t
    JOIN usuarios u              ON u.id = t.responsavel_id
    LEFT JOIN oportunidades o    ON o.id = t.oportunidade_id
    LEFT JOIN contas c_opp       ON c_opp.id = o.conta_id
    LEFT JOIN contas c_par       ON c_par.id = t.conta_id
    WHERE t.tipo = $1
      AND t.concluida_em IS NULL
      AND t.cancelada_em IS NULL
      AND t.descricao LIKE '%' || $2 || '%'
    ORDER BY t.prazo
"""

# concluida_em = prazo. O WHERE repete as condicoes de abertura para que a
# corrida com alguem concluindo pela tela nao sobrescreva a conclusao real.
UPDATE_BAIXA = """
    UPDATE tarefas
       SET concluida_em  = prazo,
           resultado     = $2,
           atualizado_em = NOW()
     WHERE id = $1
       AND concluida_em IS NULL
       AND cancelada_em IS NULL
"""


def mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


def chave_importacao(descricao: str | None, marca: str) -> str:
    """Extrai `tarefa:<hash>` da marca, para o CSV virar índice auditável."""
    if not descricao:
        return ""
    pos = descricao.rfind(marca)
    if pos < 0:
        return ""
    resto = descricao[pos + len(marca):]
    fim = resto.find("]")
    return "tarefa:" + (resto if fim < 0 else resto[:fim]).strip()


def local(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(FUSO).strftime("%Y-%m-%d %H:%M")


async def fechar(args) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL não definida.")

    hoje = datetime.now(FUSO).strftime("%d/%m/%Y")
    resultado = (
        "Baixa retroativa em "
        f"{hoje}: registro de e-mail importado do CRM Omie, onde era apenas "
        "anotação de envio e não tinha status de realizada. Concluída com a "
        "data do próprio envio."
    )

    print(f"banco   : {mascarar(url)}")
    print(f"tipo    : {TIPO}")
    print(f"marca   : {args.marca}")
    print(f"modo    : {'COMMIT' if args.commit else 'DRY-RUN (rollback no fim)'}\n")

    conn = await asyncpg.connect(url)

    try:
        tx = conn.transaction()
        await tx.start()

        linhas = await conn.fetch(SELECT_CANDIDATAS, TIPO, args.marca)

        por_responsavel = Counter()
        por_mes = Counter()
        sem_chave = 0

        # O CSV nasce sempre, nem que seja só o cabeçalho: quem chamou por scp
        # espera um arquivo, e "não achei nada" também é resultado.
        caminho = Path(args.csv)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow([
                "tarefa_id", "chave_importacao", "oportunidade", "conta",
                "responsavel", "titulo", "prazo_local", "criado_em_local",
                "concluida_em_aplicada",
            ])
            for r in linhas:
                chave = chave_importacao(r["descricao"], args.marca)
                if not chave:
                    sem_chave += 1
                conta = r["conta_oportunidade"] or r["conta_parceiro"] or ""
                w.writerow([
                    str(r["id"]),
                    chave,
                    r["oportunidade"] or "(parceiro)",
                    conta,
                    r["responsavel"],
                    (r["titulo"] or "").replace("\n", " "),
                    local(r["prazo"]),
                    local(r["criado_em"]),
                    local(r["prazo"]),
                ])
                por_responsavel[r["responsavel"]] += 1
                por_mes[local(r["prazo"])[:7]] += 1

        print(f"tarefas de e-mail em aberto vindas da carga : {len(linhas)}")
        print(f"mapeamento gravado em                       : {caminho}\n")

        if not linhas:
            print("Nenhuma tarefa de e-mail em aberto vinda da carga. Nada a fazer.")
            await tx.rollback()
            return

        print("por responsável:")
        for nome, n in sorted(por_responsavel.items(), key=lambda x: -x[1]):
            print(f"  {nome:40s} {n}")

        print("\npor mês do e-mail (prazo):")
        for mes, n in sorted(por_mes.items()):
            print(f"  {mes}  {n}")

        if sem_chave:
            print(f"\nAVISO: {sem_chave} sem chave legível na marca — fechadas do mesmo jeito.")

        print("\namostra (as 5 mais antigas):")
        for r in linhas[:5]:
            print(f"  {local(r['prazo'])}  {r['responsavel']:22s} {(r['titulo'] or '')[:60]}")

        baixadas = 0
        for r in linhas:
            status = await conn.execute(UPDATE_BAIXA, r["id"], resultado)
            if status.endswith(" 1"):
                baixadas += 1

        perdidas = len(linhas) - baixadas
        print(f"\nbaixadas : {baixadas}")
        if perdidas:
            print(f"AVISO: {perdidas} mudaram de estado durante a execução e foram deixadas de lado.")

        if args.commit:
            await tx.commit()
            print("\nCOMMIT feito.")
        else:
            await tx.rollback()
            print("\nDRY-RUN: nada foi gravado. O CSV continua valendo. Rode de novo com --commit.")
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(
        description="Fecha as tarefas de e-mail que a carga do CRM Omie subiu em aberto."
    )
    p.add_argument("--marca", default=MARCA_PADRAO,
                   help="Marca de importação que identifica o que veio da carga.")
    p.add_argument("--csv", default=CSV_PADRAO,
                   help="Onde gravar o mapeamento das tarefas encontradas.")
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    try:
        asyncio.run(fechar(args))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\nFALHOU: {exc}", file=sys.stderr)
        print("Nada foi gravado.", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
