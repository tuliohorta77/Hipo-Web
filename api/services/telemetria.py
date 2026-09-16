"""
HIPO — Métricas do dia: adoção do sistema + resultado da operação.

Duas perguntas, uma página:

  ADOÇÃO   — quem entrou, o que abriu, quanto mexeu, quem sumiu.
             Fonte: uso_eventos (middleware).
  OPERAÇÃO — o que efetivamente andou no funil e na carteira.
             Fonte: as trilhas de negócio que já existiam.

Separar as duas importa porque elas falham de formas diferentes. Uma equipe
pode passar o dia dentro do sistema sem mover uma oportunidade (adoção alta,
operação parada), ou fechar negócio inteiro por WhatsApp e lançar no fim do
mês (operação existe, adoção não). Um número só esconderia as duas coisas.

O recorte de dia usa o fuso da operação (America/Sao_Paulo), não UTC: um
lançamento das 21h em Guarulhos é do dia 17, e em UTC já seria dia 18.
"""
from __future__ import annotations

from datetime import date

_DIAS_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)

from services import relatorio_conteudo

FUSO_OPERACAO = "America/Sao_Paulo"

# Janela do dia local convertida para o timestamptz do banco. Escrita uma vez
# e reaproveitada: repetir a expressão em cada query é como o recorte começa
# a divergir entre uma métrica e outra.
_JANELA = f"""
    criado_em >= (($1::date)::timestamp AT TIME ZONE '{FUSO_OPERACAO}')
AND criado_em <  (($1::date + 1)::timestamp AT TIME ZONE '{FUSO_OPERACAO}')
"""


def _pct(parte: int, total: int) -> float | None:
    return round(parte * 100 / total, 1) if total else None


async def adocao(conn, dia: date) -> dict:
    """Uso do sistema no dia: volume, pessoas, telas, erros e latência."""
    geral = await conn.fetchrow(f"""
        SELECT
            count(*)                                             AS acoes,
            count(DISTINCT usuario_id)                           AS pessoas,
            count(*) FILTER (WHERE status >= 400)                AS erros,
            count(*) FILTER (WHERE usuario_id IS NULL)           AS anonimas,
            coalesce(round(avg(duracao_ms))::int, 0)             AS media_ms,
            coalesce(
                percentile_disc(0.95) WITHIN GROUP (ORDER BY duracao_ms), 0
            )::int                                               AS p95_ms
        FROM uso_eventos
        WHERE {_JANELA}
    """, dia)

    por_pessoa = await conn.fetch(f"""
        SELECT u.nome, e.cargo,
               count(*)                          AS acoes,
               count(DISTINCT e.rota)            AS telas,
               min(e.criado_em)                  AS primeira,
               max(e.criado_em)                  AS ultima,
               count(*) FILTER (WHERE e.status >= 400) AS erros
        FROM uso_eventos e
        JOIN usuarios u ON u.id = e.usuario_id
        WHERE {_JANELA} AND e.usuario_id IS NOT NULL
        GROUP BY u.nome, e.cargo
        ORDER BY acoes DESC
    """, dia)

    por_modulo = await conn.fetch(f"""
        SELECT coalesce(modulo, 'sem_modulo') AS modulo, count(*) AS acoes
        FROM uso_eventos
        WHERE {_JANELA}
        GROUP BY 1 ORDER BY acoes DESC
    """, dia)

    rotas = await conn.fetch(f"""
        SELECT metodo, rota, count(*) AS acoes,
               coalesce(round(avg(duracao_ms))::int, 0) AS media_ms
        FROM uso_eventos
        WHERE {_JANELA}
        GROUP BY metodo, rota
        ORDER BY acoes DESC
        LIMIT 15
    """, dia)

    # Erros agrupados por rota: 40 vezes o mesmo 422 é um problema de tela,
    # não quarenta incidentes.
    erros = await conn.fetch(f"""
        SELECT metodo, rota, status, count(*) AS ocorrencias
        FROM uso_eventos
        WHERE {_JANELA} AND status >= 400
        GROUP BY metodo, rota, status
        ORDER BY ocorrencias DESC
        LIMIT 10
    """, dia)

    # Quem não apareceu. É a métrica que justifica a telemetria existir:
    # ninguém abre um relatório para descobrir o que já viu acontecer.
    ausentes = await conn.fetch(f"""
        SELECT u.nome, u.cargo
        FROM usuarios u
        WHERE u.ativo
          AND NOT EXISTS (
              SELECT 1 FROM uso_eventos e
              WHERE e.usuario_id = u.id AND {_JANELA.replace('criado_em', 'e.criado_em')}
          )
        ORDER BY u.cargo, u.nome
    """, dia)

    # Telemetria AUSENTE não é telemetria ZERADA.
    #
    # Antes de o middleware existir, uso_eventos não tinha uma linha — e um dia
    # daqueles fecharia afirmando que as sete pessoas não acessaram o sistema,
    # num dia em que 34 tarefas foram criadas. É a mesma regra que
    # taxa_conversao aplica em services/parceiro.py: 0% e "ainda não dá para
    # saber" são coisas diferentes, e a segunda não pode se disfarçar da
    # primeira.
    #
    # Ressalva: a retenção apaga eventos antigos, então este mínimo anda para
    # frente com o tempo. Reprocessar um dia já fechado, meses depois, pode
    # marcá-lo como indisponível. Um dia é fechado no dia seguinte, quando o
    # dado ainda está fresco, então o caminho normal não sofre.
    primeiro_dia = await conn.fetchval(f"""
        SELECT (min(criado_em) AT TIME ZONE '{FUSO_OPERACAO}')::date
        FROM uso_eventos
    """)
    disponivel = primeiro_dia is not None and primeiro_dia <= dia

    acoes = geral["acoes"] or 0
    return {
        "disponivel": disponivel,
        "acoes": acoes,
        "pessoas_ativas": geral["pessoas"] or 0,
        "erros": geral["erros"] or 0,
        "taxa_erro_pct": _pct(geral["erros"] or 0, acoes),
        "requests_anonimas": geral["anonimas"] or 0,
        "latencia_media_ms": geral["media_ms"],
        "latencia_p95_ms": geral["p95_ms"],
        "por_pessoa": [
            {
                "nome": r["nome"],
                "cargo": r["cargo"],
                "acoes": r["acoes"],
                "telas": r["telas"],
                "primeira": r["primeira"].isoformat() if r["primeira"] else None,
                "ultima": r["ultima"].isoformat() if r["ultima"] else None,
                "erros": r["erros"],
            }
            for r in por_pessoa
        ],
        "por_modulo": [{"modulo": r["modulo"], "acoes": r["acoes"]} for r in por_modulo],
        "rotas_mais_usadas": [
            {"metodo": r["metodo"], "rota": r["rota"], "acoes": r["acoes"],
             "media_ms": r["media_ms"]}
            for r in rotas
        ],
        "erros_por_rota": [
            {"metodo": r["metodo"], "rota": r["rota"], "status": r["status"],
             "ocorrencias": r["ocorrencias"]}
            for r in erros
        ],
        # Sem medição, ninguém está ausente: a lista só significa alguma coisa
        # quando a captura estava rodando naquele dia.
        "sem_acesso_hoje": (
            [{"nome": r["nome"], "cargo": r["cargo"]} for r in ausentes]
            if disponivel else []
        ),
    }


async def operacao(conn, dia: date) -> dict:
    """O que andou no negócio no dia, direto das trilhas que já existiam."""
    contas = await conn.fetchval(f"""
        SELECT count(*) FROM contas WHERE {_JANELA}
    """, dia)

    contatos = await conn.fetchval(f"""
        SELECT count(*) FROM contatos WHERE {_JANELA}
    """, dia)

    opp = await conn.fetchrow(f"""
        SELECT
            count(*) FILTER (WHERE tipo = 'criacao')    AS criadas,
            count(*) FILTER (WHERE tipo = 'fase')       AS mudancas_fase,
            count(*) FILTER (WHERE tipo = 'reabertura') AS reaberturas,
            count(*) FILTER (WHERE tipo = 'status' AND para = 'conquistado') AS conquistadas,
            count(*) FILTER (WHERE tipo = 'status' AND para = 'perdido')     AS perdidas
        FROM oportunidade_eventos
        WHERE {_JANELA}
    """, dia)

    tarefas = await conn.fetchrow(f"""
        SELECT
            count(*) FILTER (WHERE {_JANELA})                              AS criadas,
            count(*) FILTER (WHERE concluida_em IS NOT NULL
                AND concluida_em >= (($1::date)::timestamp AT TIME ZONE '{FUSO_OPERACAO}')
                AND concluida_em <  (($1::date + 1)::timestamp AT TIME ZONE '{FUSO_OPERACAO}')
            )                                                              AS concluidas,
            count(*) FILTER (WHERE concluida_em IS NULL AND cancelada_em IS NULL
                AND prazo < (($1::date + 1)::timestamp AT TIME ZONE '{FUSO_OPERACAO}')
            )                                                              AS em_atraso
        FROM tarefas
    """, dia)

    parceiros = await conn.fetchrow(f"""
        SELECT
            count(*) FILTER (WHERE tipo = 'marcado')      AS marcados,
            count(*) FILTER (WHERE tipo = 'transferido')  AS transferidos,
            count(*) FILTER (WHERE tipo = 'atribuido')    AS atribuidos
        FROM parceiro_eventos
        WHERE {_JANELA}
    """, dia)

    carteira = await conn.fetchrow("""
        SELECT count(*) FILTER (WHERE eh_finder)                                AS parceiros,
               count(*) FILTER (WHERE eh_finder AND ec_responsavel_id IS NULL)  AS sem_ec
        FROM contas
    """)

    return {
        "contas_criadas": contas or 0,
        "contatos_criados": contatos or 0,
        "oportunidades_criadas": opp["criadas"] or 0,
        "mudancas_de_fase": opp["mudancas_fase"] or 0,
        "reaberturas": opp["reaberturas"] or 0,
        "conquistadas": opp["conquistadas"] or 0,
        "perdidas": opp["perdidas"] or 0,
        "tarefas_criadas": tarefas["criadas"] or 0,
        "tarefas_concluidas": tarefas["concluidas"] or 0,
        "tarefas_em_atraso": tarefas["em_atraso"] or 0,
        "parceiros_marcados": parceiros["marcados"] or 0,
        "parceiros_transferidos": parceiros["transferidos"] or 0,
        "parceiros_atribuidos": parceiros["atribuidos"] or 0,
        "carteira_parceiros": carteira["parceiros"] or 0,
        "parceiros_sem_ec": carteira["sem_ec"] or 0,
    }


async def atividades(conn, dia: date) -> dict:
    """
    O que cada pessoa LANCOU no dia, por hora e por tipo.

    Substitui "acoes" como numero de producao. Ver o cabecalho de
    services/atividade.py para o porque: 89% das requests de 15/09 eram
    leitura.

    A HORA SAI DO BANCO JA NO FUSO DA OPERACAO. O e-mail antigo mostrava a
    entrada da equipe as 11h e a saida as 21h -- era o horario UTC do
    timestamptz formatado sem conversao. Converter aqui, com o mesmo
    AT TIME ZONE que recorta o dia, faz a hora e o dia sairem da mesma
    regra.
    """
    from services import atividade as svc

    janela_e = _JANELA.replace("criado_em", "e.criado_em")

    linhas = await conn.fetch(f"""
        SELECT e.usuario_id, u.nome, e.cargo, e.metodo, e.rota, e.status,
               extract(hour FROM e.criado_em AT TIME ZONE '{FUSO_OPERACAO}')::int AS hora,
               count(*) AS qtd
        FROM uso_eventos e
        JOIN usuarios u ON u.id = e.usuario_id
        WHERE {janela_e}
          AND e.status < 400
          AND e.metodo NOT IN ('GET', 'HEAD', 'OPTIONS')
        GROUP BY e.usuario_id, u.nome, e.cargo, e.metodo, e.rota, e.status, hora
    """, dia)

    presencas = await conn.fetch(f"""
        SELECT e.usuario_id, u.nome, max(e.cargo) AS cargo,
               to_char(min(e.criado_em) AT TIME ZONE '{FUSO_OPERACAO}', 'HH24:MI') AS entrada,
               to_char(max(e.criado_em) AT TIME ZONE '{FUSO_OPERACAO}', 'HH24:MI') AS saida
        FROM uso_eventos e
        JOIN usuarios u ON u.id = e.usuario_id
        WHERE {janela_e}
        GROUP BY e.usuario_id, u.nome
    """, dia)

    return svc.agregar([dict(r) for r in linhas], [dict(r) for r in presencas])


async def reunioes(conn, dia: date, agora=None) -> dict:
    """
    Reunioes que ACONTECERAM no dia (pelo prazo) com o desfecho, e
    agendamentos MARCADOS no dia (pelo criado_em) por quem marcou.

    `agora` e parametro para o teste ser deterministico: o desfecho
    'pendente' depende do relogio.
    """
    from datetime import datetime, timezone

    from services import relatorio_reunioes as svc

    agora = agora or datetime.now(timezone.utc)
    janela_prazo = _JANELA.replace("criado_em", "t.prazo")
    janela_r = _JANELA.replace("criado_em", "r.criado_em")

    linhas = await conn.fetch(f"""
        SELECT t.prazo, t.concluida_em, t.cancelada_em,
               r.duracao_min, r.desfecho, r.modalidade,
               ua.nome  AS anfitriao,
               ua.cargo AS anfitriao_cargo,
               ug.nome  AS agendado_por,
               coalesce(c.nome_fantasia, c.razao_social) AS empresa,
               tr.sigla AS tipo_sigla, tr.nome AS tipo_nome
        FROM reunioes r
        JOIN tarefas t            ON t.id = r.tarefa_id
        LEFT JOIN usuarios ua     ON ua.id = t.responsavel_id
        LEFT JOIN usuarios ug     ON ug.id = r.agendado_por
        LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
        LEFT JOIN contas c        ON c.id = coalesce(t.conta_id, o.conta_id)
        LEFT JOIN tipos_reuniao tr ON tr.id = r.tipo_id
        WHERE {janela_prazo}
    """, dia)

    agendamentos = await conn.fetch(f"""
        SELECT u.nome, u.cargo, count(*) AS qtd
        FROM reunioes r
        LEFT JOIN usuarios u ON u.id = r.agendado_por
        WHERE {janela_r}
        GROUP BY u.nome, u.cargo
    """, dia)

    return svc.montar([dict(r) for r in linhas], [dict(r) for r in agendamentos], agora)


async def comparativo(conn, dia: date) -> dict:
    """
    Mesmos números do dia anterior com dado, para o relatório dizer 'caiu'.

    Lê relatorios_diarios, não uso_eventos: é o que mantém a comparação viva
    depois que a retenção apagou os eventos brutos. Pula fim de semana
    naturalmente ao buscar o último dia COM registro, em vez de 'dia - 1' —
    comparar segunda com domingo produziria uma queda inventada toda semana.
    """
    anterior = await conn.fetchrow("""
        SELECT dia, metricas FROM relatorios_diarios
        WHERE dia < $1 ORDER BY dia DESC LIMIT 1
    """, dia)
    if not anterior:
        return {"disponivel": False}

    import json
    m = anterior["metricas"]
    m = json.loads(m) if isinstance(m, str) else m
    ad = (m or {}).get("adocao", {})
    op = (m or {}).get("operacao", {})
    return {
        "disponivel": True,
        "dia": anterior["dia"].isoformat(),
        # O DIA DA SEMANA VAI PRONTO, e nao deduzido do ISO pela IA.
        #
        # O fechamento de 31/08 chamou 28/08 de "segunda-feira" -- era sexta.
        # Todo numero da frase estava certo, entao a guarda numerica nao viu
        # nada, e a comparacao inteira ficou falsa. Errar dia da semana e
        # facil e passa despercebido; entregar o dado remove a tentacao.
        "dia_semana": _DIAS_SEMANA[anterior["dia"].weekday()],
        "acoes": ad.get("acoes"),
        "pessoas_ativas": ad.get("pessoas_ativas"),
        # Ausente em fechamentos anteriores a 16/09: fica None e o KPI sai
        # sem variacao, em vez de comparar contra um zero que nunca existiu.
        "atividades": (m or {}).get("atividades", {}).get("total"),
        "reunioes_realizadas": (m or {}).get("reunioes", {}).get("realizadas"),
        "oportunidades_criadas": op.get("oportunidades_criadas"),
        "tarefas_concluidas": op.get("tarefas_concluidas"),
    }


async def metricas_do_dia(conn, dia: date) -> dict:
    """
    Payload completo do fechamento. É o que vai para o JSONB e para a IA.

    Quatro blocos, e o quarto é de outra natureza:

      adocao / operacao / comparativo  -> o que aconteceu NAQUELE dia
      conteudo                         -> o que está EM ABERTO agora

    `conteudo` mora em services/relatorio_conteudo.py e não é recortado por
    dia de propósito: uma oportunidade com a previsão vencida em julho
    continua sendo assunto hoje. Ele existe porque contagem não é acionável —
    "22 tarefas em atraso" não diz QUAIS, e sem os itens no JSON a IA não tem
    como apontar nenhum sem inventar.
    """
    return {
        "dia": dia.isoformat(),
        "fuso": FUSO_OPERACAO,
        "adocao": await adocao(conn, dia),
        "operacao": await operacao(conn, dia),
        "atividades": await atividades(conn, dia),
        "reunioes": await reunioes(conn, dia),
        "comparativo": await comparativo(conn, dia),
        "conteudo": await relatorio_conteudo.conteudo(conn, dia, FUSO_OPERACAO),
    }


async def aplicar_retencao(conn, dias: int) -> int:
    """
    Apaga eventos mais antigos que `dias` e devolve quantos apagou.

    Guarda de segurança: `dias` menor que 1 não apaga nada. Um zero vindo de
    variável de ambiente mal preenchida limparia a tabela inteira, incluindo
    o dia que está sendo fechado agora.
    """
    if dias < 1:
        return 0
    apagados = await conn.fetchval("""
        WITH removidos AS (
            DELETE FROM uso_eventos
            WHERE criado_em < NOW() - ($1 || ' days')::interval
            RETURNING 1
        )
        SELECT count(*) FROM removidos
    """, str(dias))
    return apagados or 0
