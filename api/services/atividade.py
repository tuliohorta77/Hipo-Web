"""
HIPO - Atividade executada: o que cada pessoa LANCOU ou ALTEROU no CRM.

Funcoes puras, sem banco e sem rede: rodam no pytest local do Windows.

POR QUE EXISTE

O fechamento contava "acoes" = toda request autenticada (uso_eventos). Em
15/09 foram 2.285, e 89% eram GET: abrir o kanban dispara lista, resumo e
dominio; abrir um drawer dispara mais tres. O numero media quanto a pessoa
NAVEGOU, e comparava mal: o SDR que filtra muito parecia dez vezes mais
produtivo que o EV que faz pouca coisa demorada.

Atividade e o que muda o dado: escrita (POST/PUT/PATCH/DELETE) que deu
certo (status < 400). "Kethlleen concluiu 24 tarefas" e numero de gestao;
"Kethlleen fez 980 requests" nao e.

O CATALOGO E EXPLICITO, E NAO DEDUZIDO DA ROTA

Traduzir por heuristica ("POST termina em /concluir -> conclui") funciona
para 80% e erra em silencio nos outros 20% -- `POST /contatos/{id}/vinculos`
viraria "cria contato". Cada rota de escrita da API tem aqui o seu rotulo,
escrito a mao, e `tests/test_atividade.py` percorre `app.routes` e falha se
aparecer rota de escrita nova sem entrada no catalogo nem na lista de
ignoradas. A rota nova nao some do relatorio: cai em "outras alteracoes"
com a rota crua ate alguem dar nome a ela -- e o teste obriga a dar.
"""
from __future__ import annotations

from dataclasses import dataclass

METODOS_DE_LEITURA = frozenset({"GET", "HEAD", "OPTIONS"})

# Janela padrao da tabela usuario x hora. Estende sozinha quando alguem
# trabalha antes ou depois: a coluna das 19h so aparece no dia em que
# existe atividade nela.
HORA_INICIO_PADRAO = 8
HORA_FIM_PADRAO = 18


@dataclass(frozen=True)
class Tipo:
    grupo: str
    rotulo: str
    ordem: int


# Ordem dos grupos no detalhe por colaborador: o que mais diz sobre
# producao comercial vem primeiro.
GRUPOS = (
    "Tarefas",
    "Reuniões",
    "Oportunidades",
    "Propostas",
    "Contas e contatos",
    "Parceiros",
    "Anexos",
    "Cadastros",
    "Outras alterações",
)


def _t(grupo: str, rotulo: str, ordem: int) -> Tipo:
    return Tipo(grupo, rotulo, ordem)


CATALOGO: dict[tuple[str, str], Tipo] = {
    # Tarefas
    ("POST", "/crm/tarefas"): _t("Tarefas", "Tarefa criada", 10),
    ("POST", "/crm/tarefas/{tarefa_id}/concluir"): _t("Tarefas", "Tarefa concluída", 11),
    ("PATCH", "/crm/tarefas/{tarefa_id}"): _t("Tarefas", "Tarefa editada", 12),
    ("POST", "/crm/tarefas/{tarefa_id}/cancelar"): _t("Tarefas", "Tarefa cancelada", 13),

    # Reunioes (agenda)
    ("POST", "/crm/agenda/reunioes"): _t("Reuniões", "Reunião agendada", 20),
    ("POST", "/crm/agenda/reunioes/de-tarefa/{tarefa_id}"): _t("Reuniões", "Reunião agendada", 20),
    ("POST", "/crm/agenda/reunioes/{reuniao_id}/desfecho"): _t("Reuniões", "Desfecho de reunião registrado", 21),
    ("POST", "/crm/agenda/tarefas/{tarefa_id}/desfecho"): _t("Reuniões", "Desfecho de reunião registrado", 21),
    ("PATCH", "/crm/agenda/reunioes/{reuniao_id}"): _t("Reuniões", "Reunião editada", 22),
    ("POST", "/crm/agenda/reunioes/{reuniao_id}/cancelar"): _t("Reuniões", "Reunião cancelada", 23),
    ("POST", "/crm/agenda/reunioes/{reuniao_id}/sincronizar"): _t("Reuniões", "Reunião reenviada ao Google", 24),
    ("POST", "/crm/agenda/tarefas/{tarefa_id}/transcricao/buscar"): _t("Reuniões", "Transcrição buscada", 25),
    ("POST", "/crm/agenda/tarefas/{tarefa_id}/transcricao/resumo"): _t("Reuniões", "Resumo de reunião gerado", 26),

    # Oportunidades
    ("POST", "/crm/oportunidades"): _t("Oportunidades", "Oportunidade criada", 30),
    ("PATCH", "/crm/oportunidades/{oportunidade_id}/fase"): _t("Oportunidades", "Fase alterada", 31),
    ("POST", "/crm/oportunidades/{oportunidade_id}/desfecho"): _t("Oportunidades", "Oportunidade finalizada (ganho/perda)", 32),
    ("PATCH", "/crm/oportunidades/{oportunidade_id}/status"): _t("Oportunidades", "Status alterado", 33),
    ("POST", "/crm/oportunidades/{oportunidade_id}/reabrir"): _t("Oportunidades", "Oportunidade reaberta", 34),
    ("PATCH", "/crm/oportunidades/{oportunidade_id}"): _t("Oportunidades", "Oportunidade editada", 35),
    ("PUT", "/crm/oportunidades/{oportunidade_id}/envolvidos"): _t("Oportunidades", "Envolvidos atualizados", 36),
    ("PUT", "/crm/oportunidades/{oportunidade_id}/concorrentes"): _t("Oportunidades", "Concorrentes atualizados", 37),

    # Propostas
    ("POST", "/crm/oportunidades/{oportunidade_id}/propostas"): _t("Propostas", "Proposta gerada", 40),

    # Contas e contatos
    ("POST", "/crm/contas"): _t("Contas e contatos", "Conta criada", 50),
    ("PATCH", "/crm/contas/{conta_id}"): _t("Contas e contatos", "Conta editada", 51),
    ("PATCH", "/crm/contas/{conta_id}/prospeccao"): _t("Contas e contatos", "Prospecção da conta alterada", 52),
    ("DELETE", "/crm/contas/{conta_id}"): _t("Contas e contatos", "Conta excluída", 53),
    ("POST", "/crm/contatos"): _t("Contas e contatos", "Contato criado", 54),
    ("PATCH", "/crm/contatos/{contato_id}"): _t("Contas e contatos", "Contato editado", 55),
    ("DELETE", "/crm/contatos/{contato_id}"): _t("Contas e contatos", "Contato excluído", 56),
    ("POST", "/crm/contatos/{contato_id}/vinculos"): _t("Contas e contatos", "Contato vinculado a conta", 57),
    ("PATCH", "/crm/contatos/{contato_id}/vinculos/{conta_id}"): _t("Contas e contatos", "Vínculo de contato editado", 58),
    ("DELETE", "/crm/contatos/{contato_id}/vinculos/{conta_id}"): _t("Contas e contatos", "Contato desvinculado de conta", 59),

    # Enriquecimento cadastral (014). Aplicar o dado da Receita numa conta é
    # atividade de cadastro como outra qualquer: mudou o registro, e quem
    # apertou o botão assinou a mudança. A CONSULTA não entra — é GET, não
    # grava nada, e contá-la repetiria a armadilha que o `uso_eventos` já
    # tinha: medir quem navega em vez de quem produz.
    ("POST", "/crm/enriquecimento/contas/{conta_id}/aplicar"):
        _t("Contas e contatos", "Conta enriquecida pelo CNPJ", 90),

    # Parceiros
    ("PATCH", "/crm/parceiros/{conta_id}"): _t("Parceiros", "Parceiro editado", 60),
    ("POST", "/crm/parceiros/carteira/transferir"): _t("Parceiros", "Carteira transferida", 61),

    # Anexos
    ("POST", "/crm/tarefas/{tarefa_id}/anexos"): _t("Anexos", "Anexo enviado", 70),
    ("DELETE", "/crm/anexos/{anexo_id}"): _t("Anexos", "Anexo excluído", 71),

    # Monitor (metas e feriados)
    ("PUT", "/monitor/metas"): _t("Cadastros", "Metas do monitor definidas", 83),
    ("POST", "/monitor/metas/copiar"): _t("Cadastros", "Metas copiadas do mes anterior", 84),
    ("POST", "/monitor/feriados"): _t("Cadastros", "Dia sem expediente marcado", 85),
    ("POST", "/monitor/feriados/nacionais"): _t("Cadastros", "Feriados nacionais carregados", 86),
    ("DELETE", "/monitor/feriados/{feriado_id}"): _t("Cadastros", "Dia sem expediente removido", 87),

    # Cadastros de apoio
    ("POST", "/crm/dominio/{tabela}"): _t("Cadastros", "Item de cadastro criado", 80),
    ("POST", "/crm/dominio/motivos/{tipo}"): _t("Cadastros", "Motivo criado", 81),
    ("POST", "/crm/agenda/tipos"): _t("Cadastros", "Tipo de reunião criado", 82),
    # Mapear um CNAE classifica TODAS as contas futuras com aquele código —
    # é cadastro de apoio com alcance largo, e por isso aparece nominalmente
    # no fechamento em vez de virar "outras alterações".
    ("PATCH", "/crm/enriquecimento/cnaes/{codigo}"):
        _t("Cadastros", "CNAE mapeado (vertical e grau de risco)", 88),
}

# Escritas que NAO sao atividade no CRM. Entrar no sistema, trocar a
# propria senha e guardar a coluna do kanban preferida nao produzem nada
# para a operacao -- e `preferencias` sozinha poderia inflar o numero de
# quem mexe muito na tela.
IGNORADAS: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/auth/login"),
    ("PUT", "/auth/perfil"),
    ("PUT", "/auth/senha"),
    ("PUT", "/crm/dominio/preferencias/{chave}"),
    # Relatorios. A consulta, o drilldown e a lista de valores sao LEITURA
    # que viaja em POST (o corpo nao cabe numa query string). Salvar,
    # editar, compartilhar e duplicar um relatorio e preferencia pessoal,
    # como a coluna do kanban acima: nao produz nada para a operacao.
    ("POST", "/crm/relatorios/consulta"),
    ("POST", "/crm/relatorios/registros"),
    ("POST", "/crm/relatorios/valores"),
    ("POST", "/crm/relatorios/salvos"),
    ("PUT", "/crm/relatorios/salvos/{relatorio_id}"),
    ("DELETE", "/crm/relatorios/salvos/{relatorio_id}"),
    ("POST", "/crm/relatorios/salvos/{relatorio_id}/duplicar"),
})


def eh_escrita(metodo: str) -> bool:
    return (metodo or "").upper() not in METODOS_DE_LEITURA


def conta_como_atividade(metodo: str, rota: str, status: int) -> bool:
    """
    Escrita, com sucesso, fora da lista de ignoradas.

    >>> conta_como_atividade("POST", "/crm/tarefas", 201)
    True
    >>> conta_como_atividade("POST", "/crm/tarefas", 422)
    False
    >>> conta_como_atividade("GET", "/crm/tarefas", 200)
    False
    >>> conta_como_atividade("POST", "/auth/login", 200)
    False
    """
    m = (metodo or "").upper()
    if not eh_escrita(m) or status is None or status >= 400:
        return False
    return (m, rota) not in IGNORADAS


def classificar(metodo: str, rota: str) -> Tipo:
    """
    Tipo da escrita. Rota fora do catalogo nao some: vira 'outras alteracoes'
    com a rota crua no rotulo, para ser nomeada depois.
    """
    m = (metodo or "").upper()
    tipo = CATALOGO.get((m, rota))
    if tipo is not None:
        return tipo
    return Tipo("Outras alterações", f"{m} {rota}", 999)


def janela_de_horas(horas_com_atividade) -> list[int]:
    """
    Colunas da tabela usuario x hora.

    >>> janela_de_horas([])
    [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
    >>> janela_de_horas([7, 19])[0], janela_de_horas([7, 19])[-1]
    (7, 19)
    """
    hs = [h for h in horas_com_atividade if h is not None]
    ini = min([HORA_INICIO_PADRAO, *hs])
    fim = max([HORA_FIM_PADRAO, *hs])
    return list(range(ini, fim + 1))


def agregar(linhas: list[dict], presencas: list[dict],
            oportunidades: list[dict] | None = None,
            oportunidades_total: dict | None = None) -> dict:
    """
    Monta o bloco `atividades` do fechamento.

    `linhas`: escritas ja agrupadas pelo banco, cada uma com
      usuario_id, nome, cargo, metodo, rota, status, hora (0-23, fuso da
      operacao), qtd.
    `presencas`: quem teve QUALQUER evento no dia (inclusive so leitura),
      com usuario_id, nome, cargo, entrada, saida ('HH:MM' no fuso).

    `oportunidades`: por responsavel -- usuario_id, nome, cargo, trabalhadas,
      primeira_vez. `oportunidades_total`: trabalhadas, primeira_vez da equipe,
      contadas com DISTINCT no banco. NAO e a soma das pessoas: uma
      oportunidade trabalhada por duas pessoas no mesmo dia conta uma vez no
      total e uma vez para cada uma.

    Quem entrou e nao lancou nada aparece com zero. Esse zero e informacao
    -- "abriu o sistema o dia inteiro e nao registrou nada" -- e some se a
    tabela so listar quem escreveu.
    """
    pessoas: dict[str, dict] = {}

    def _pessoa(uid, nome, cargo):
        chave = str(uid)
        if chave not in pessoas:
            pessoas[chave] = {
                "nome": nome, "cargo": cargo,
                "entrada": None, "saida": None,
                "total": 0, "_hora": {}, "_tipo": {},
                "opp": 0, "opp_primeira": 0,
            }
        return pessoas[chave]

    for p in presencas:
        alvo = _pessoa(p["usuario_id"], p["nome"], p["cargo"])
        alvo["entrada"] = p.get("entrada")
        alvo["saida"] = p.get("saida")

    for o in oportunidades or []:
        alvo = _pessoa(o["usuario_id"], o["nome"], o["cargo"])
        alvo["opp"] = int(o["trabalhadas"])
        alvo["opp_primeira"] = int(o["primeira_vez"])

    horas_vistas: set[int] = set()
    for r in linhas:
        if not conta_como_atividade(r["metodo"], r["rota"], r["status"]):
            continue
        alvo = _pessoa(r["usuario_id"], r["nome"], r["cargo"])
        qtd = int(r["qtd"])
        hora = int(r["hora"])
        horas_vistas.add(hora)
        alvo["total"] += qtd
        alvo["_hora"][hora] = alvo["_hora"].get(hora, 0) + qtd
        tipo = classificar(r["metodo"], r["rota"])
        chave_tipo = (tipo.grupo, tipo.rotulo)
        if chave_tipo not in alvo["_tipo"]:
            alvo["_tipo"][chave_tipo] = {"tipo": tipo, "qtd": 0}
        alvo["_tipo"][chave_tipo]["qtd"] += qtd

    horas = janela_de_horas(horas_vistas)

    saida = []
    for p in pessoas.values():
        tipos = sorted(
            p["_tipo"].values(),
            key=lambda t: (GRUPOS.index(t["tipo"].grupo)
                           if t["tipo"].grupo in GRUPOS else len(GRUPOS),
                           t["tipo"].ordem, t["tipo"].rotulo),
        )
        saida.append({
            "nome": p["nome"],
            "cargo": p["cargo"],
            "entrada": p["entrada"],
            "saida": p["saida"],
            "total": p["total"],
            "oportunidades_trabalhadas": p["opp"],
            "oportunidades_primeira_vez": p["opp_primeira"],
            "por_hora": [p["_hora"].get(h, 0) for h in horas],
            "por_tipo": [
                {"grupo": t["tipo"].grupo, "tipo": t["tipo"].rotulo, "qtd": t["qtd"]}
                for t in tipos
            ],
        })

    saida.sort(key=lambda p: (-p["total"], -p["oportunidades_trabalhadas"], p["nome"] or ""))

    tot = oportunidades_total or {}
    return {
        "total": sum(p["total"] for p in saida),
        "oportunidades_trabalhadas": int(tot.get("trabalhadas") or 0),
        "oportunidades_primeira_vez": int(tot.get("primeira_vez") or 0),
        "horas": horas,
        "total_por_hora": [sum(p["por_hora"][i] for p in saida) for i in range(len(horas))],
        "por_pessoa": saida,
    }
