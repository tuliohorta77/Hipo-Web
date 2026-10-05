"""
HIPO — RPeR: a coleta.

Aqui só há SQL. Cada função devolve LINHAS de um mês (cada reunião, cada
tarefa, cada venda, com quem fez) e services/rper.py faz as contas. O
motivo está no cabeçalho de lá: o realizado do squad sai das linhas
deduplicadas, não da soma do realizado das pessoas.

AS MESMAS REGRAS DAS OUTRAS TELAS

  * Reunião: desfecho EFETIVO de `services/agenda.desfecho_efetivo`, o
    mesmo que a Agenda, o Monitor e o fechamento diário usam. Reunião de
    parceiro (tarefas.conta_id) é ilha: só entra no EC.
  * Venda: evento de status 'conquistado' de `oportunidade_eventos`, uma
    linha por oportunidade (DISTINCT ON), igual ao Monitor. Nunca
    `atualizado_em`, que qualquer edição move de mês.
  * Agendamento: pela data em que foi MARCADO (`reunioes.criado_em`),
    creditado a `agendado_por` — é métrica de quem marcou, não de quem
    digitou.

Recortar as linhas pelo mês em SQL (e não trazer tudo) mantém o volume
em dezenas ou centenas de linhas por mês, o que cabe em Python com folga.
"""
from __future__ import annotations

from datetime import datetime, timezone

from services import agenda as regras_agenda
from services import rper as regras
from services.tarefa import janela_utc

CARGOS_DOS_SQUADS = regras.SQUADS


async def pessoas_dos_squads(conn) -> dict[str, list[dict]]:
    """
    Quem sai em cada squad: usuários ATIVOS com o cargo do squad, por nome.

    Quem foi desativado no meio do mês sai do slide — o resultado dele
    continua no TOTAL do squad só se outra pessoa do squad estiver na
    mesma linha. É uma limitação consciente: o RPeR é a reunião do time
    que existe hoje.
    """
    rows = await conn.fetch(
        """
        SELECT id, nome, cargo FROM usuarios
         WHERE ativo AND cargo = ANY($1::text[])
         ORDER BY nome
        """,
        list(CARGOS_DOS_SQUADS),
    )
    saida: dict[str, list[dict]] = {s: [] for s in CARGOS_DOS_SQUADS}
    for r in rows:
        saida[r["cargo"]].append({"id": r["id"], "nome": r["nome"]})
    return saida


async def _reunioes(conn, inicio, fim) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT r.id, r.desfecho, r.agendado_por, r.duracao_min,
               t.responsavel_id AS anfitriao_id,
               t.conta_id       AS parceiro_id,
               t.oportunidade_id,
               t.prazo AS inicio, t.concluida_em, t.cancelada_em
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
         WHERE t.prazo >= $1 AND t.prazo < $2
        """,
        inicio, fim,
    )
    linhas = []
    for r in rows:
        d = dict(r)
        d["efetivo"] = regras_agenda.desfecho_efetivo(
            desfecho=d["desfecho"],
            concluida_em=d["concluida_em"],
            cancelada_em=d["cancelada_em"],
            inicio=d["inicio"],
        )
        linhas.append(d)
    return linhas


async def _agendamentos(conn, inicio, fim) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT r.id, r.agendado_por, t.oportunidade_id,
               o.valor_mensalidade AS valor
          FROM reunioes r
          JOIN tarefas t ON t.id = r.tarefa_id
          LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
         WHERE r.criado_em >= $1 AND r.criado_em < $2
           AND t.conta_id IS NULL
        """,
        inicio, fim,
    )
    return [dict(r) for r in rows]


async def _tarefas(conn, inicio, fim) -> list[dict]:
    """
    Tarefas com PRAZO no mês, sem as canceladas. Concluída é a que tem
    `concluida_em` — a qualquer momento: follow-up de 29/08 feito em 02/09
    foi feito, só que atrasado.
    """
    rows = await conn.fetch(
        """
        SELECT t.id, t.responsavel_id, t.oportunidade_id,
               o.conta_id, t.conta_id AS parceiro_id,
               (t.concluida_em IS NOT NULL) AS concluida
          FROM tarefas t
          LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
         WHERE t.prazo >= $1 AND t.prazo < $2
           AND t.cancelada_em IS NULL
        """,
        inicio, fim,
    )
    return [dict(r) for r in rows]


async def _leads(conn, inicio, fim) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT e.id, e.usuario_id, e.oportunidade_id
          FROM oportunidade_eventos e
         WHERE e.tipo = 'fase' AND e.de = 'suspect' AND e.para = 'lead'
           AND e.criado_em >= $1 AND e.criado_em < $2
        """,
        inicio, fim,
    )
    return [dict(r) for r in rows]


_ENVOLVIDOS = """
    ARRAY(SELECT DISTINCT oe.usuario_id FROM oportunidade_envolvidos oe
           WHERE oe.oportunidade_id = o.id) AS envolvidos
"""


async def _vendas(conn, inicio, fim) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT * FROM (
            SELECT DISTINCT ON (o.id)
                   o.id, o.numero, e.criado_em AS data,
                   o.valor_mensalidade AS valor,
                   COALESCE(c.nome_fantasia, c.razao_social) AS empresa,
                   {_ENVOLVIDOS}
              FROM oportunidade_eventos e
              JOIN oportunidades o ON o.id = e.oportunidade_id
              JOIN contas c        ON c.id = o.conta_id
             WHERE e.tipo = 'status' AND e.para = 'conquistado'
               AND e.criado_em >= $1 AND e.criado_em < $2
             ORDER BY o.id, e.criado_em
        ) ganhas
        ORDER BY valor DESC NULLS LAST
        """,
        inicio, fim,
    )
    return [dict(r) for r in rows]


async def _propostas(conn, inicio, fim) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT p.id, p.oportunidade_id,
               COALESCE(p.executivo_id, p.criado_por) AS executivo_id
          FROM propostas p
         WHERE p.criado_em >= $1 AND p.criado_em < $2
        """,
        inicio, fim,
    )
    return [dict(r) for r in rows]


async def _ativas(conn, agora: datetime) -> list[dict]:
    """
    Oportunidades ativas COM envolvido — posição agora. Sem envolvido não
    há a quem atribuir, e a carga inicial tem centenas delas paradas: é o
    mesmo ruído que tirou o "Precisa de ação: 947" do e-mail.
    """
    rows = await conn.fetch(
        f"""
        SELECT o.id, o.numero, o.fase, o.valor_mensalidade AS valor,
               COALESCE(c.nome_fantasia, c.razao_social) AS empresa,
               {_ENVOLVIDOS},
               (SELECT max(t.concluida_em) FROM tarefas t
                 WHERE t.oportunidade_id = o.id) AS ultimo_fup,
               (SELECT count(*) FROM tarefas t
                 WHERE t.oportunidade_id = o.id
                   AND t.concluida_em IS NULL AND t.cancelada_em IS NULL
                   AND t.prazo < $1) AS tarefas_atrasadas
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
         WHERE o.status = 'ativa'
           AND EXISTS (SELECT 1 FROM oportunidade_envolvidos oe
                        WHERE oe.oportunidade_id = o.id)
        """,
        agora,
    )
    return [dict(r) for r in rows]


async def _parceiros(conn) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, ec_responsavel_id AS ec_id FROM contas
         WHERE eh_finder AND ec_responsavel_id IS NOT NULL
        """
    )
    return [dict(r) for r in rows]


async def _parcerias(conn, inicio, fim) -> list[dict]:
    """
    Parceiro que ENTROU na carteira de um EC no mês: evento 'atribuido'
    (de ninguém para alguém). 'transferido' fica fora — trocar de dono não
    é parceria nova, é a mesma relação mudando de mão.
    """
    rows = await conn.fetch(
        """
        SELECT id, conta_id, para_usuario_id FROM parceiro_eventos
         WHERE tipo = 'atribuido'
           AND criado_em >= $1 AND criado_em < $2
        """,
        inicio, fim,
    )
    return [dict(r) for r in rows]


async def _indicacoes(conn, inicio, fim) -> list[dict]:
    """
    Oportunidades criadas no mês com parceiro indicador, creditadas ao EC
    que é dono do parceiro HOJE — o HIPO não guarda o dono de cada dia sem
    percorrer `parceiro_eventos`, e no 1º dia útil a diferença é nula.
    """
    rows = await conn.fetch(
        """
        SELECT o.id, c.ec_responsavel_id AS ec_id
          FROM oportunidades o
          JOIN contas c ON c.id = o.finder_conta_id
         WHERE o.criado_em >= $1 AND o.criado_em < $2
           AND c.ec_responsavel_id IS NOT NULL
        """,
        inicio, fim,
    )
    return [dict(r) for r in rows]


async def _atrasadas_por_pessoa(conn, agora: datetime) -> dict:
    rows = await conn.fetch(
        """
        SELECT responsavel_id, count(*) AS n FROM tarefas
         WHERE concluida_em IS NULL AND cancelada_em IS NULL AND prazo < $1
         GROUP BY responsavel_id
        """,
        agora,
    )
    return {r["responsavel_id"]: r["n"] for r in rows}


async def coletar(conn, ano: int, mes: int, agora: datetime | None = None) -> dict:
    """Todas as linhas do mês fechado, mais a posição de agora."""
    primeiro, ultimo = regras.janela_do_mes(ano, mes)
    inicio, fim = janela_utc(primeiro, ultimo)
    return await coletar_janela(conn, inicio, fim, agora)


async def coletar_janela(conn, inicio: datetime, fim: datetime,
                         agora: datetime | None = None) -> dict:
    """
    As mesmas linhas de `coletar`, numa janela UTC qualquer [inicio, fim).

    Existe para o Desempenho da Carreira, que mostra o mês CORRENTE até
    hoje (como o Monitor): tarefa com prazo daqui a uma semana ainda não
    pode contar contra a taxa de execução de ninguém.
    """
    agora = agora or datetime.now(timezone.utc)
    return {
        "reunioes": await _reunioes(conn, inicio, fim),
        "agendamentos": await _agendamentos(conn, inicio, fim),
        "tarefas": await _tarefas(conn, inicio, fim),
        "leads": await _leads(conn, inicio, fim),
        "vendas": await _vendas(conn, inicio, fim),
        "propostas": await _propostas(conn, inicio, fim),
        "ativas": await _ativas(conn, agora),
        "parceiros": await _parceiros(conn),
        "parcerias": await _parcerias(conn, inicio, fim),
        "indicacoes": await _indicacoes(conn, inicio, fim),
        "atrasadas": await _atrasadas_por_pessoa(conn, agora),
    }


async def metas(conn, ano: int, mes: int) -> dict:
    """
    As metas do mês: {'squad': {(squad, indicador): valor},
                      'pessoa': {(squad, usuario_id_str, indicador): valor}}
    """
    rows = await conn.fetch(
        """
        SELECT squad, usuario_id, indicador, valor FROM metas_comerciais
         WHERE ano = $1 AND mes = $2
        """,
        ano, mes,
    )
    saida = {"squad": {}, "pessoa": {}}
    for r in rows:
        if r["usuario_id"] is None:
            saida["squad"][(r["squad"], r["indicador"])] = float(r["valor"])
        else:
            saida["pessoa"][(r["squad"], str(r["usuario_id"]), r["indicador"])] = float(r["valor"])
    return saida


def metas_do_squad(tabela: dict, squad: str) -> tuple[dict, dict]:
    """Recorta o resultado de `metas` para o formato de `calcular_squad`."""
    do_squad = {ind: v for (s, ind), v in tabela["squad"].items() if s == squad}
    por_pessoa = {
        (uid, ind): v for (s, uid, ind), v in tabela["pessoa"].items() if s == squad
    }
    return do_squad, por_pessoa
