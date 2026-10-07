"""
HIPO — Confirmação da véspera para as reuniões JÁ MARCADAS (entrega 048).

A entrega 048 cria a tarefa de confirmação quando a reunião é marcada ou
remarcada. As reuniões marcadas antes do deploy ficaram sem ela: este
script passa por elas e aplica a MESMA regra
(routers.crm_agenda._sincronizar_confirmacao), sem cópia.

QUAIS REUNIÕES
  Futuras, em aberto, de oportunidade, com quem agendou, e que ainda não
  têm confirmação nenhuma (aberta, concluída ou cancelada).

A VÉSPERA PODE SER HOJE
  Na marcação, véspera = hoje não cria (quem acabou de combinar não precisa
  confirmar). Aqui é o contrário: a reunião de amanhã foi marcada dias atrás
  e AINDA dá para confirmar hoje. Por isso o relógio da regra é recuado
  para ontem durante o script — a véspera de hoje passa, a de ontem (reunião
  de hoje) continua de fora. A tarefa nasce para hoje às 09:00.

COMO É SEGURO
  Tudo roda numa transação só. Sem --commit, o script mostra o que seria
  criado e faz ROLLBACK — a simulação é a própria gravação desfeita, então
  o que aparece é exatamente o que o --commit grava. Rodar de novo não
  duplica: reunião que já tem confirmação é pulada.

USO (de dentro de api/, com DATABASE_URL no ambiente)
  python -m scripts.criar_confirmacoes_vespera            # só mostra
  python -m scripts.criar_confirmacoes_vespera --commit   # grava
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import asyncpg

PENDENTES = """
    SELECT r.id AS reuniao_id, t.id AS tarefa_id, t.prazo AS inicio,
           COALESCE(c.nome_fantasia, c.razao_social) AS empresa,
           ag.nome AS agendado_por_nome
      FROM reunioes r
      JOIN tarefas t        ON t.id = r.tarefa_id
      JOIN oportunidades o  ON o.id = t.oportunidade_id
      LEFT JOIN contas c    ON c.id = o.conta_id
      LEFT JOIN usuarios ag ON ag.id = r.agendado_por
     WHERE t.concluida_em IS NULL AND t.cancelada_em IS NULL
       AND t.prazo > NOW()
       AND r.agendado_por IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM tarefas x WHERE x.confirmacao_de = t.id)
     ORDER BY t.prazo
"""


def mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


async def criar(conn) -> list[dict]:
    """
    Cria as confirmações que faltam. Chamar DENTRO de uma transação: quem
    chama decide se grava ou desfaz.

    Devolve uma linha por reunião examinada, com `prazo` None quando a
    regra dos dois dias úteis não deixou criar.
    """
    import routers.crm_agenda as crm_agenda

    agora_real = crm_agenda._agora
    ontem = datetime.now(timezone.utc) - timedelta(days=1)
    crm_agenda._agora = lambda: ontem
    try:
        return await _criar(conn, crm_agenda._sincronizar_confirmacao)
    finally:
        crm_agenda._agora = agora_real


async def _criar(conn, _sincronizar_confirmacao) -> list[dict]:
    saida = []
    for r in await conn.fetch(PENDENTES):
        await _sincronizar_confirmacao(conn, r["reuniao_id"], remarcou=True)
        criada = await conn.fetchrow(
            """
            SELECT t.prazo, u.nome AS responsavel
              FROM tarefas t LEFT JOIN usuarios u ON u.id = t.responsavel_id
             WHERE t.confirmacao_de = $1
            """,
            r["tarefa_id"],
        )
        saida.append({
            "inicio": r["inicio"],
            "empresa": r["empresa"],
            "agendado_por": r["agendado_por_nome"],
            "prazo": criada["prazo"] if criada else None,
        })
    return saida


async def executar(gravar: bool) -> int:
    from services.agenda import no_fuso

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERRO: DATABASE_URL nao definida.", file=sys.stderr)
        return 1
    print(f"Banco: {mascarar(url)}")
    conn = await asyncpg.connect(url)
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            linhas = await criar(conn)
        except BaseException:
            await tx.rollback()
            raise

        criadas = [x for x in linhas if x["prazo"] is not None]
        for x in linhas:
            quando = no_fuso(x["inicio"]).strftime("%d/%m %H:%M")
            if x["prazo"] is None:
                acao = "vespera util ja passou -- nao cria"
            else:
                acao = f"confirmar em {no_fuso(x['prazo']).strftime('%d/%m %H:%M')}"
            print(f"  {quando}  {(x['empresa'] or '?')[:40]:<40}  "
                  f"{(x['agendado_por'] or '?')[:22]:<22}  {acao}")
        print()
        print(f"Reunioes futuras sem confirmacao: {len(linhas)}  |  "
              f"confirmacoes a criar: {len(criadas)}")

        if gravar:
            await tx.commit()
            print("GRAVADO.")
        else:
            await tx.rollback()
            print("Simulacao: nada foi gravado. Rode com --commit para gravar.")
        return 0
    finally:
        await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--commit", action="store_true", help="grava (sem isto, so mostra)")
    args = ap.parse_args()
    sys.exit(asyncio.run(executar(args.commit)))


if __name__ == "__main__":
    main()
