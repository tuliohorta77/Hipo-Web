"""
HIPO - Relatorios: catalogo de campos e motor da tabela dinamica.

Funcoes puras, sem banco: o catalogo e a montagem do SQL rodam no pytest
local do Windows. Quem executa o SQL e routers/crm_relatorios.py.

POR QUE UM CATALOGO, E NAO "QUALQUER COLUNA DO BANCO"

Tres motivos, e nenhum e estetico:

  1. Seguranca. O usuario escolhe CHAVES ("fase", "vertical"); o SQL de cada
     chave e escrito aqui, a mao. Nada que vem do cliente vira identificador
     SQL -- so vira parametro ($n). Nao existe caminho para injetar coluna,
     tabela ou funcao.

  2. Nome claro. "valor_mensalidade" e "Mensalidade (R$)"; "fase_desfecho"
     e "Fase em que foi finalizada". Quem monta relatorio e a operacao, nao
     quem escreveu o schema.

  3. Recorte. Cada fonte declara o seu recorte por envolvimento (a mesma
     regra de filtro-por-envolvimento.md). Relatorio sem recorte seria a
     porta dos fundos que a especificacao proibiu: a tabela dinamica
     mostraria, agregado, exatamente o que a tela de oportunidades esconde.

O MOTOR

A tabela dinamica e calculada no BANCO, com GROUPING SETS: uma consulta so
devolve as celulas, os subtotais de cada nivel de linha e os totais de
coluna e geral. O navegador so arruma a grade. Somar no navegador daria
subtotal errado para media e contagem distinta -- media de medias nao e
media.

Todo valor de DIMENSAO sai como TEXTO (`::text`). E o que deixa o clique
numa celula (drilldown) e o filtro "em" compararem exatamente o que a tela
mostrou, sem conversao de tipo no caminho: '2026-09-01', 'true', '30'. A
tela formata pelo tipo declarado no catalogo.

PARAMETROS FIXOS

  $1 -- escopo (uuid do usuario, ou NULL para gestao). Sempre presente,
        para que todo fragmento de SQL do catalogo possa usar `:escopo`.
  $2 -- inicio do periodo (date)
  $3 -- fim do periodo (date)
  $4... -- filtros

Periodo e obrigatorio: relatorio sem periodo e o SELECT da base inteira
esperando para acontecer, e a pergunta "de quando?" e a primeira que
qualquer numero precisa responder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

FUSO = "America/Sao_Paulo"

# ── Limites ──────────────────────────────────────────────────────────

MAX_LINHAS = 4
MAX_COLUNAS = 2
MAX_VALORES = 6
MAX_FILTROS = 15
MAX_VALORES_POR_FILTRO = 500
MAX_DIAS_PERIODO = 3700          # ~10 anos
MAX_CELULAS = 20_000             # linhas devolvidas pelo GROUPING SETS
MAX_COMBINACOES_COLUNA = 100     # colunas distintas na grade
MAX_REGISTROS_PAGINA = 200
MAX_VALORES_DISTINTOS = 500

GRANULARIDADES = {
    "dia": "Dia",
    "semana": "Semana",
    "mes": "Mês",
    "trimestre": "Trimestre",
    "ano": "Ano",
}
_GRAN_SQL = {"semana": "week", "mes": "month", "trimestre": "quarter", "ano": "year"}
GRANULARIDADE_PADRAO = "mes"

AGREGACOES = {
    "contagem": "Quantidade",
    "soma": "Soma",
    "media": "Média",
    "minimo": "Mínimo",
    "maximo": "Máximo",
    "contagem_distinta": "Qtd. distinta",
    "percentual": "% com Sim",
}

OPERADORES = {
    "em": "é um destes",
    "nao_em": "não é nenhum destes",
    "entre": "está entre",
    "contem": "contém o texto",
}

# Periodos relativos que um relatorio salvo pode guardar. A conversao em
# datas e feita na TELA (web/src/components/relatorios/periodo.js), no fuso
# de quem abre; a API so recebe datas. A lista mora aqui para a API recusar
# relatorio salvo com preset que a tela nao sabe resolver.
PRESETS_PERIODO = {
    "hoje": "Hoje",
    "ontem": "Ontem",
    "ultimos_7": "Últimos 7 dias",
    "ultimos_30": "Últimos 30 dias",
    "ultimos_90": "Últimos 90 dias",
    "semana_atual": "Esta semana",
    "mes_atual": "Este mês",
    "mes_anterior": "Mês passado",
    "trimestre_atual": "Este trimestre",
    "ano_atual": "Este ano",
    "ano_anterior": "Ano passado",
    "ultimos_12_meses": "Últimos 12 meses",
}

TIPOS = ("texto", "numero", "moeda", "data", "booleano")


class ConsultaInvalida(ValueError):
    """Erro de montagem com mensagem em portugues, pronta para a tela."""


# ── Estruturas do catalogo ───────────────────────────────────────────

@dataclass(frozen=True)
class Campo:
    chave: str
    rotulo: str
    tipo: str
    sql: str
    grupo: str
    joins: tuple[str, ...] = ()
    ajuda: str = ""
    # Vocabulario fechado: ((valor_bruto, rotulo), ...) na ordem natural
    # (a ordem do funil, nao a alfabetica).
    valores: tuple[tuple[str, str], ...] = ()
    # Data com hora (timestamptz): o dia e o do fuso da operacao.
    com_hora: bool = False
    # Pode ser a data que recorta o periodo.
    referencia: bool = False
    dimensao: bool = True

    @property
    def medida(self) -> bool:
        return self.tipo in ("numero", "moeda", "booleano")

    def agregacoes(self) -> tuple[str, ...]:
        if self.tipo in ("numero", "moeda"):
            base = ("soma", "media", "minimo", "maximo")
        elif self.tipo == "booleano":
            base = ("soma", "percentual")
        else:
            base = ()
        if self.dimensao:
            base = base + ("contagem_distinta",)
        return base


@dataclass(frozen=True)
class Fonte:
    chave: str
    rotulo: str
    descricao: str
    rotulo_registro: str          # "oportunidades" em "Quantidade de oportunidades"
    from_sql: str
    joins: dict                    # nome -> (sql, dependencias)
    campos: tuple[Campo, ...]
    recorte: str                   # clausula com :escopo
    data_padrao: str
    colunas_registro: tuple[str, ...]
    # (tipo, expressao do id) -- o que o drilldown abre
    abrir: tuple[tuple[str, str], ...]
    joins_recorte: tuple[str, ...] = ()
    joins_abrir: tuple[str, ...] = ()
    _por_chave: dict = field(default_factory=dict, compare=False, repr=False)

    def campo(self, chave: str) -> Campo:
        if not self._por_chave:
            self._por_chave.update({c.chave: c for c in self.campos})
        c = self._por_chave.get(chave)
        if c is None:
            raise ConsultaInvalida(
                f"O campo '{chave}' não existe em {self.rotulo}. "
                f"Ele pode ter sido renomeado ou removido — refaça o relatório."
            )
        return c


# ── Vocabularios ─────────────────────────────────────────────────────

FASES = (
    ("suspect", "Suspect"),
    ("lead", "Lead"),
    ("qualificacao", "Qualificação"),
    ("apresentacao", "Apresentação"),
    ("negociacao", "Negociação"),
    ("finalizado", "Finalizado"),
)
SITUACOES_OPP = (
    ("ativa", "Ativa"),
    ("suspensa", "Suspensa"),
    ("conquistado", "Conquistada (ganha)"),
    ("perdido", "Perdida"),
    ("cancelado", "Cancelada"),
)
TIPOS_TAREFA = (
    ("ligacao", "Ligação"),
    ("reuniao", "Reunião"),
    ("visita", "Visita"),
    ("proposta", "Proposta"),
    ("email", "E-mail"),
    ("whatsapp", "WhatsApp"),
    ("outro", "Outro"),
)
SITUACOES_TAREFA = (
    ("pendente", "Pendente (no prazo)"),
    ("atrasada", "Atrasada"),
    ("concluida", "Concluída"),
    ("cancelada", "Cancelada"),
)
DESFECHOS_REUNIAO = (
    ("sem_desfecho", "Sem desfecho registrado"),
    ("realizada", "Realizada"),
    ("no_show", "No-show (cliente faltou)"),
    ("cancelada", "Cancelada"),
)
MODALIDADES = (("online", "Online"), ("presencial", "Presencial"))
PAPEIS_ENVOLVIDO = (("EC", "EC"), ("SDR", "SDR"), ("EV", "EV"))
FAIXAS_FUNCIONARIOS = (
    ("01-19", "1 a 19"),
    ("02-20-49", "20 a 49"),
    ("03-50-99", "50 a 99"),
    ("04-100-249", "100 a 249"),
    ("05-250-499", "250 a 499"),
    ("06-500+", "500 ou mais"),
)
ORIGENS_FUNCIONARIOS = (("declarado", "Declarado pelo cliente"), ("estimado", "Estimado (base pública)"))
TIPOS_EVENTO = (
    ("criacao", "Criação"),
    ("fase", "Mudança de fase"),
    ("status", "Mudança de situação"),
    ("reabertura", "Reabertura"),
)
ESTADOS_EVENTO = FASES + SITUACOES_OPP
TRANSCRICAO_STATUS = (
    ("sem", "Sem transcrição"),
    ("aguardando", "Aguardando"),
    ("pronta", "Pronta"),
    ("indisponivel", "Indisponível"),
)


# ── Blocos reaproveitados ────────────────────────────────────────────

def _faixa_funcionarios(expr: str) -> str:
    return (
        f"CASE WHEN {expr} IS NULL THEN NULL"
        f" WHEN {expr} < 20 THEN '01-19'"
        f" WHEN {expr} < 50 THEN '02-20-49'"
        f" WHEN {expr} < 100 THEN '03-50-99'"
        f" WHEN {expr} < 250 THEN '04-100-249'"
        f" WHEN {expr} < 500 THEN '05-250-499'"
        f" ELSE '06-500+' END"
    )


def _nome_empresa(alias: str) -> str:
    return f"COALESCE(NULLIF(btrim({alias}.nome_fantasia), ''), {alias}.razao_social)"


# Joins de empresa. Toda fonte que tem empresa define a join 'c' do seu
# jeito (direta, via oportunidade, via tarefa); as demais dependem de 'c'.
def _joins_empresa() -> dict:
    return {
        "v": ("LEFT JOIN verticais v ON v.id = c.vertical_id", ("c",)),
        "cn": ("LEFT JOIN cnaes cn ON cn.codigo = c.cnae_codigo", ("c",)),
        "ecr": ("LEFT JOIN usuarios ecr ON ecr.id = c.ec_responsavel_id", ("c",)),
    }


def _campos_empresa(grupo: str = "Empresa") -> tuple[Campo, ...]:
    j = ("c",)
    return (
        Campo("empresa", "Empresa (razão social)", "texto", "c.razao_social", grupo, j),
        Campo("empresa_fantasia", "Empresa (nome fantasia ou razão)", "texto", _nome_empresa("c"), grupo, j,
              ajuda="Nome fantasia quando existe; senão, a razão social."),
        Campo("empresa_cnpj", "CNPJ da empresa", "texto", "c.cnpj", grupo, j),
        Campo("empresa_vertical", "Vertical (segmento)", "texto", "v.nome", grupo, ("c", "v")),
        Campo("empresa_cidade", "Cidade da empresa", "texto", "c.cidade", grupo, j),
        Campo("empresa_uf", "UF da empresa", "texto", "c.uf", grupo, j),
        Campo("empresa_bairro", "Bairro da empresa", "texto", "c.bairro", grupo, j),
        Campo("empresa_porte", "Porte (Receita)", "texto", "c.porte", grupo, j,
              ajuda="Faixa de faturamento declarada à Receita — não é número de funcionários."),
        Campo("empresa_funcionarios", "Nº de funcionários da empresa", "numero", "c.num_funcionarios", grupo, j),
        Campo("empresa_faixa_funcionarios", "Faixa de funcionários", "texto",
              _faixa_funcionarios("c.num_funcionarios"), grupo, j, valores=FAIXAS_FUNCIONARIOS),
        Campo("empresa_cnae", "CNAE principal", "texto",
              "CASE WHEN c.cnae_codigo IS NULL THEN NULL ELSE c.cnae_codigo || COALESCE(' - ' || cn.descricao, '') END",
              grupo, ("c", "cn")),
        Campo("empresa_grau_risco", "Grau de risco (NR-4)", "numero", "cn.grau_risco", grupo, ("c", "cn")),
        Campo("empresa_eh_parceiro", "Empresa é parceira indicadora", "booleano", "c.eh_finder", grupo, j),
        Campo("empresa_nao_prospectar", "Empresa bloqueada para prospecção", "booleano", "c.nao_prospectar", grupo, j),
    )


def _envolvidos_lateral(opp_alias: str) -> str:
    return (
        "LEFT JOIN LATERAL ("
        " SELECT string_agg(u.nome, ', ' ORDER BY u.nome) FILTER (WHERE oe.papel = 'EV')  AS ev,"
        "        string_agg(u.nome, ', ' ORDER BY u.nome) FILTER (WHERE oe.papel = 'SDR') AS sdr,"
        "        string_agg(u.nome, ', ' ORDER BY u.nome) FILTER (WHERE oe.papel = 'EC')  AS ec"
        "   FROM oportunidade_envolvidos oe JOIN usuarios u ON u.id = oe.usuario_id"
        f"  WHERE oe.oportunidade_id = {opp_alias}.id"
        ") env ON TRUE"
    )


def _recorte_envolvido(opp_id_expr: str) -> str:
    return (
        "(:escopo IS NULL OR EXISTS (SELECT 1 FROM oportunidade_envolvidos oe_r"
        f" WHERE oe_r.oportunidade_id = {opp_id_expr} AND oe_r.usuario_id = :escopo))"
    )


def _campos_envolvidos(grupo: str, dep: tuple[str, ...]) -> tuple[Campo, ...]:
    j = dep + ("env",)
    return (
        Campo("ev", "Executivo de vendas (EV)", "texto", "env.ev", grupo, j,
              ajuda="Quando há mais de um, aparecem juntos, separados por vírgula."),
        Campo("sdr", "SDR", "texto", "env.sdr", grupo, j),
        Campo("ec", "Executivo de contas (EC)", "texto", "env.ec", grupo, j),
    )


# Data do desfecho: a ultima transicao de status para um estado final. Vem
# da trilha de eventos porque `atualizado_em` muda a cada edicao.
def _desfecho_lateral(opp_alias: str) -> str:
    return (
        "LEFT JOIN LATERAL ("
        " SELECT max(e.criado_em) AS em FROM oportunidade_eventos e"
        f"  WHERE e.oportunidade_id = {opp_alias}.id AND e.tipo = 'status'"
        "    AND e.para IN ('conquistado', 'perdido', 'cancelado')"
        f"    AND {opp_alias}.status IN ('conquistado', 'perdido', 'cancelado')"
        ") des ON TRUE"
    )


# ── Fonte: Oportunidades ─────────────────────────────────────────────

_OPP_JOINS = {
    "c": ("JOIN contas c ON c.id = o.conta_id", ()),
    **_joins_empresa(),
    "org": ("LEFT JOIN origens org ON org.id = o.origem_id", ()),
    "md": ("LEFT JOIN motivos_desfecho md ON md.id = o.motivo_desfecho_id", ()),
    "fnd": ("LEFT JOIN contas fnd ON fnd.id = o.finder_conta_id", ()),
    "ct": ("LEFT JOIN contatos ct ON ct.id = o.contato_id", ()),
    "uc": ("LEFT JOIN usuarios uc ON uc.id = o.criado_por", ()),
    "env": (_envolvidos_lateral("o"), ()),
    "des": (_desfecho_lateral("o"), ()),
    "prop": (
        "LEFT JOIN LATERAL ("
        " SELECT count(*) AS qtd,"
        "        (array_agg(p.vidas ORDER BY p.versao DESC))[1] AS vidas,"
        "        (array_agg(p.valor_por_vida ORDER BY p.versao DESC))[1] AS valor_por_vida,"
        "        (array_agg(p.treinamentos ORDER BY p.versao DESC))[1] AS treinamentos,"
        "        (array_agg(p.laudos ORDER BY p.versao DESC))[1] AS laudos"
        "   FROM propostas p WHERE p.oportunidade_id = o.id"
        ") prop ON TRUE",
        (),
    ),
    "tar": (
        "LEFT JOIN LATERAL ("
        " SELECT count(*) AS total,"
        "        count(*) FILTER (WHERE t.concluida_em IS NOT NULL) AS concluidas,"
        "        count(*) FILTER (WHERE t.concluida_em IS NULL AND t.cancelada_em IS NULL) AS abertas"
        "   FROM tarefas t WHERE t.oportunidade_id = o.id"
        ") tar ON TRUE",
        (),
    ),
}

_OPP_CAMPOS = (
    Campo("numero", "Número da oportunidade", "texto", "o.numero", "Oportunidade"),
    Campo("fase", "Fase", "texto", "o.fase", "Oportunidade", valores=FASES),
    Campo("situacao", "Situação", "texto", "o.status", "Oportunidade", valores=SITUACOES_OPP,
          ajuda="Ativa, suspensa, ou o desfecho: conquistada, perdida ou cancelada."),
    Campo("fase_desfecho", "Fase em que foi finalizada", "texto", "o.fase_desfecho", "Oportunidade",
          valores=FASES[:-1], ajuda="De qual fase saiu o ganho ou a perda. Vazio enquanto está aberta."),
    Campo("motivo_desfecho", "Motivo da perda/cancelamento", "texto", "md.nome", "Oportunidade", ("md",)),
    Campo("temperatura", "Temperatura (%)", "numero", "o.temperatura", "Oportunidade",
          ajuda="Chance de fechar, de 0 a 90%, informada por quem conduz."),
    Campo("mensalidade", "Mensalidade (R$)", "moeda", "o.valor_mensalidade", "Valores"),
    Campo("valor_anual", "Valor anual (mensalidade × 12)", "moeda", "(o.valor_mensalidade * 12)", "Valores"),
    Campo("mensalidade_ponderada", "Mensalidade ponderada pela temperatura (R$)", "moeda",
          "round(o.valor_mensalidade * COALESCE(o.temperatura, 0) / 100.0, 2)", "Valores",
          ajuda="Mensalidade × temperatura. Soma = previsão realista do funil."),
    Campo("foi_conquistada", "Foi conquistada", "booleano", "(o.status = 'conquistado')", "Resultado",
          ajuda="Use '% com Sim' para ter a taxa de conversão."),
    Campo("foi_perdida", "Foi perdida ou cancelada", "booleano", "(o.status IN ('perdido','cancelado'))", "Resultado"),
    Campo("esta_aberta", "Está em aberto", "booleano", "(o.status IN ('ativa','suspensa'))", "Resultado"),
    Campo("dias_ciclo", "Duração (dias da criação ao desfecho ou até hoje)", "numero",
          "round((extract(epoch FROM (COALESCE(des.em, now()) - o.criado_em)) / 86400.0)::numeric, 1)",
          "Resultado", ("des",), ajuda="Use 'Média' para o ciclo médio de venda."),
    Campo("origem", "Origem do lead", "texto", "org.nome", "Origem", ("org",)),
    Campo("parceiro_indicador", "Parceiro que indicou", "texto", _nome_empresa("fnd"), "Origem", ("fnd",)),
    Campo("veio_de_parceiro", "Veio de indicação de parceiro", "booleano", "(o.finder_conta_id IS NOT NULL)", "Origem"),
    *_campos_envolvidos("Equipe", ()),
    Campo("cadastrada_por", "Cadastrada por", "texto", "uc.nome", "Equipe", ("uc",)),
    Campo("contato", "Contato da oportunidade", "texto", "ct.nome", "Oportunidade", ("ct",)),
    Campo("data_criacao", "Data de criação", "data", "o.criado_em", "Datas", com_hora=True, referencia=True),
    Campo("data_previsao", "Previsão de fechamento", "data", "o.previsao_fechamento", "Datas", referencia=True),
    Campo("data_desfecho", "Data do desfecho (ganho/perda)", "data", "des.em", "Datas", ("des",),
          com_hora=True, referencia=True,
          ajuda="Quando foi finalizada. Vazio para as que ainda estão abertas."),
    Campo("data_atualizacao", "Última atualização", "data", "o.atualizado_em", "Datas", com_hora=True, referencia=True),
    Campo("qtd_propostas", "Qtd. de propostas geradas", "numero", "prop.qtd", "Proposta", ("prop",)),
    Campo("tem_proposta", "Tem proposta gerada", "booleano", "(prop.qtd > 0)", "Proposta", ("prop",)),
    Campo("proposta_vidas", "Vidas (última proposta)", "numero", "prop.vidas", "Proposta", ("prop",)),
    Campo("proposta_valor_vida", "Valor por vida (última proposta)", "moeda", "prop.valor_por_vida", "Proposta", ("prop",)),
    Campo("proposta_treinamentos", "Treinamentos (última proposta)", "moeda", "prop.treinamentos", "Proposta", ("prop",)),
    Campo("proposta_laudos", "Laudos (última proposta)", "moeda", "prop.laudos", "Proposta", ("prop",)),
    Campo("qtd_tarefas", "Qtd. de tarefas", "numero", "tar.total", "Atividades", ("tar",)),
    Campo("qtd_tarefas_concluidas", "Qtd. de tarefas concluídas", "numero", "tar.concluidas", "Atividades", ("tar",)),
    Campo("qtd_tarefas_abertas", "Qtd. de tarefas em aberto", "numero", "tar.abertas", "Atividades", ("tar",)),
    *_campos_empresa(),
)

OPORTUNIDADES = Fonte(
    chave="oportunidades",
    rotulo="Oportunidades",
    descricao="Cada linha é uma oportunidade do funil, com empresa, equipe, valores e desfecho.",
    rotulo_registro="oportunidades",
    from_sql="oportunidades o",
    joins=_OPP_JOINS,
    campos=_OPP_CAMPOS,
    recorte=_recorte_envolvido("o.id"),
    data_padrao="data_criacao",
    colunas_registro=("numero", "empresa_fantasia", "fase", "situacao", "mensalidade", "ev", "data_criacao"),
    abrir=(("oportunidade", "o.id"),),
)


# ── Fonte: Tarefas ───────────────────────────────────────────────────

_SITUACAO_TAREFA_SQL = (
    "CASE WHEN t.concluida_em IS NOT NULL THEN 'concluida'"
    " WHEN t.cancelada_em IS NOT NULL THEN 'cancelada'"
    " WHEN t.prazo < now() THEN 'atrasada'"
    " ELSE 'pendente' END"
)

_TAR_JOINS = {
    "o": ("LEFT JOIN oportunidades o ON o.id = t.oportunidade_id", ()),
    "c": ("LEFT JOIN contas c ON c.id = COALESCE(t.conta_id, o.conta_id)", ("o",)),
    **_joins_empresa(),
    "ur": ("JOIN usuarios ur ON ur.id = t.responsavel_id", ()),
    "uc": ("LEFT JOIN usuarios uc ON uc.id = t.criado_por", ()),
    "r": ("LEFT JOIN reunioes r ON r.tarefa_id = t.id", ()),
    "env": (_envolvidos_lateral("o"), ("o",)),
}

_TAR_CAMPOS = (
    Campo("tipo", "Tipo de tarefa", "texto", "t.tipo", "Tarefa", valores=TIPOS_TAREFA),
    Campo("situacao", "Situação da tarefa", "texto", _SITUACAO_TAREFA_SQL, "Tarefa", valores=SITUACOES_TAREFA,
          ajuda="Atrasada = prazo já passou e não foi concluída nem cancelada."),
    Campo("titulo", "Título da tarefa", "texto", "t.titulo", "Tarefa"),
    Campo("responsavel", "Responsável", "texto", "ur.nome", "Equipe", ("ur",)),
    Campo("responsavel_cargo", "Cargo do responsável", "texto", "ur.cargo", "Equipe", ("ur",)),
    Campo("criada_por", "Criada por", "texto", "uc.nome", "Equipe", ("uc",)),
    Campo("vinculo", "Vinculada a", "texto",
          "CASE WHEN t.oportunidade_id IS NOT NULL THEN 'oportunidade' ELSE 'parceiro' END", "Tarefa",
          valores=(("oportunidade", "Oportunidade"), ("parceiro", "Parceiro (relacionamento)"))),
    Campo("concluida", "Foi concluída", "booleano", "(t.concluida_em IS NOT NULL)", "Resultado"),
    Campo("cancelada", "Foi cancelada", "booleano", "(t.cancelada_em IS NOT NULL)", "Resultado"),
    Campo("atrasada", "Está atrasada", "booleano",
          "(t.concluida_em IS NULL AND t.cancelada_em IS NULL AND t.prazo < now())", "Resultado"),
    Campo("concluida_no_prazo", "Concluída no prazo", "booleano",
          "(t.concluida_em IS NOT NULL AND t.concluida_em <= t.prazo)", "Resultado",
          ajuda="Use '% com Sim' para medir pontualidade."),
    Campo("dias_atraso_conclusao", "Dias entre o prazo e a conclusão", "numero",
          "CASE WHEN t.concluida_em IS NULL THEN NULL"
          " ELSE round((extract(epoch FROM (t.concluida_em - t.prazo)) / 86400.0)::numeric, 1) END",
          "Resultado", ajuda="Negativo = concluiu antes do prazo."),
    Campo("tem_resultado", "Tem resultado registrado", "booleano",
          "(t.resultado IS NOT NULL AND btrim(t.resultado) <> '')", "Resultado"),
    Campo("eh_reuniao_agendada", "Está na agenda (reunião)", "booleano", "(r.id IS NOT NULL)", "Tarefa", ("r",)),
    Campo("data_criacao", "Data de criação", "data", "t.criado_em", "Datas", com_hora=True, referencia=True),
    Campo("data_prazo", "Prazo (data agendada)", "data", "t.prazo", "Datas", com_hora=True, referencia=True),
    Campo("data_conclusao", "Data de conclusão", "data", "t.concluida_em", "Datas", com_hora=True, referencia=True),
    Campo("data_cancelamento", "Data de cancelamento", "data", "t.cancelada_em", "Datas", com_hora=True, referencia=True),
    Campo("oportunidade_numero", "Número da oportunidade", "texto", "o.numero", "Oportunidade", ("o",)),
    Campo("oportunidade_fase", "Fase da oportunidade", "texto", "o.fase", "Oportunidade", ("o",), valores=FASES),
    Campo("oportunidade_situacao", "Situação da oportunidade", "texto", "o.status", "Oportunidade", ("o",),
          valores=SITUACOES_OPP),
    Campo("oportunidade_mensalidade", "Mensalidade da oportunidade (R$)", "moeda", "o.valor_mensalidade",
          "Oportunidade", ("o",)),
    *_campos_envolvidos("Oportunidade", ("o",)),
    *_campos_empresa(),
)

TAREFAS = Fonte(
    chave="tarefas",
    rotulo="Tarefas e atividades",
    descricao="Cada linha é uma tarefa (ligação, e-mail, visita, reunião...), de oportunidade ou de parceiro.",
    rotulo_registro="tarefas",
    from_sql="tarefas t",
    joins=_TAR_JOINS,
    campos=_TAR_CAMPOS,
    recorte="(:escopo IS NULL OR t.responsavel_id = :escopo)",
    data_padrao="data_prazo",
    colunas_registro=("titulo", "tipo", "situacao", "responsavel", "empresa_fantasia", "data_prazo"),
    abrir=(("oportunidade", "t.oportunidade_id"), ("conta", "c.id")),
    joins_abrir=("c",),
)


# ── Fonte: Reunioes ──────────────────────────────────────────────────

_REU_JOINS = {
    "o": ("LEFT JOIN oportunidades o ON o.id = t.oportunidade_id", ()),
    "c": ("LEFT JOIN contas c ON c.id = COALESCE(t.conta_id, o.conta_id)", ("o",)),
    **_joins_empresa(),
    "ur": ("JOIN usuarios ur ON ur.id = t.responsavel_id", ()),
    "ua": ("LEFT JOIN usuarios ua ON ua.id = r.agendado_por", ()),
    "tr": ("LEFT JOIN tipos_reuniao tr ON tr.id = r.tipo_id", ()),
    "trc": ("LEFT JOIN reuniao_transcricoes trc ON trc.reuniao_id = r.id", ()),
    "env": (_envolvidos_lateral("o"), ("o",)),
    "part": (
        "LEFT JOIN LATERAL (SELECT count(*) AS qtd FROM reuniao_participantes rp"
        " WHERE rp.reuniao_id = r.id) part ON TRUE",
        (),
    ),
}

_REU_CAMPOS = (
    Campo("tipo_reuniao", "Tipo de reunião", "texto", "tr.nome", "Reunião", ("tr",)),
    Campo("modalidade", "Modalidade", "texto", "r.modalidade", "Reunião", valores=MODALIDADES),
    Campo("desfecho", "Desfecho da reunião", "texto", "COALESCE(r.desfecho, 'sem_desfecho')", "Resultado",
          valores=DESFECHOS_REUNIAO),
    Campo("foi_realizada", "Foi realizada", "booleano", "(r.desfecho = 'realizada')", "Resultado",
          ajuda="Use '% com Sim' para a taxa de comparecimento."),
    Campo("foi_no_show", "Foi no-show", "booleano", "(r.desfecho = 'no_show')", "Resultado"),
    Campo("antecedencia_aviso_h", "Antecedência do aviso de desfecho (horas)", "numero",
          "r.desfecho_antecedencia_horas", "Resultado",
          ajuda="Horas entre o registro do desfecho e o horário da reunião."),
    Campo("anfitriao", "Anfitrião (quem conduz)", "texto", "ur.nome", "Equipe", ("ur",)),
    Campo("anfitriao_cargo", "Cargo do anfitrião", "texto", "ur.cargo", "Equipe", ("ur",)),
    Campo("agendada_por", "Agendada por", "texto", "ua.nome", "Equipe", ("ua",),
          ajuda="Quem tem o crédito do agendamento (ex.: o SDR que marcou)."),
    Campo("qtd_participantes", "Qtd. de participantes internos (além do anfitrião)", "numero",
          "part.qtd", "Equipe", ("part",)),
    Campo("duracao_min", "Duração prevista (minutos)", "numero", "r.duracao_min", "Reunião"),
    Campo("convite_google", "Convite enviado ao Google Agenda", "booleano", "(r.google_event_id IS NOT NULL)", "Reunião"),
    Campo("transcricao", "Transcrição", "texto", "COALESCE(trc.status, 'sem')", "Reunião", ("trc",),
          valores=TRANSCRICAO_STATUS),
    Campo("data_reuniao", "Data da reunião", "data", "t.prazo", "Datas", com_hora=True, referencia=True),
    Campo("data_agendamento", "Data em que foi agendada", "data", "r.criado_em", "Datas", com_hora=True, referencia=True,
          ajuda="O dia em que o agendamento foi FEITO — é a data da produção do SDR."),
    Campo("data_desfecho", "Data do registro do desfecho", "data", "r.desfecho_em", "Datas",
          com_hora=True, referencia=True),
    Campo("oportunidade_numero", "Número da oportunidade", "texto", "o.numero", "Oportunidade", ("o",)),
    Campo("oportunidade_fase", "Fase da oportunidade", "texto", "o.fase", "Oportunidade", ("o",), valores=FASES),
    Campo("oportunidade_situacao", "Situação da oportunidade", "texto", "o.status", "Oportunidade", ("o",),
          valores=SITUACOES_OPP),
    *_campos_envolvidos("Oportunidade", ("o",)),
    *_campos_empresa(),
)

REUNIOES = Fonte(
    chave="reunioes",
    rotulo="Reuniões",
    descricao="Cada linha é uma reunião da agenda, com tipo, anfitrião, quem agendou e o desfecho.",
    rotulo_registro="reuniões",
    from_sql="reunioes r JOIN tarefas t ON t.id = r.tarefa_id",
    joins=_REU_JOINS,
    campos=_REU_CAMPOS,
    recorte=(
        "(:escopo IS NULL OR t.responsavel_id = :escopo OR r.agendado_por = :escopo"
        " OR EXISTS (SELECT 1 FROM reuniao_participantes rp_r"
        " WHERE rp_r.reuniao_id = r.id AND rp_r.usuario_id = :escopo))"
    ),
    data_padrao="data_reuniao",
    colunas_registro=("data_reuniao", "tipo_reuniao", "empresa_fantasia", "anfitriao", "agendada_por", "desfecho"),
    abrir=(("oportunidade", "t.oportunidade_id"), ("conta", "c.id")),
    joins_abrir=("c",),
)


# ── Fonte: Propostas ─────────────────────────────────────────────────

_PROP_JOINS = {
    "o": ("JOIN oportunidades o ON o.id = p.oportunidade_id", ()),
    "c": ("JOIN contas c ON c.id = o.conta_id", ("o",)),
    **_joins_empresa(),
    "ue": ("LEFT JOIN usuarios ue ON ue.id = p.executivo_id", ()),
    "ult": (
        "LEFT JOIN LATERAL (SELECT max(p2.versao) AS versao FROM propostas p2"
        " WHERE p2.oportunidade_id = p.oportunidade_id) ult ON TRUE",
        (),
    ),
    "env": (_envolvidos_lateral("o"), ("o",)),
}

_PROP_CAMPOS = (
    Campo("versao", "Versão da proposta", "numero", "p.versao", "Proposta"),
    Campo("eh_ultima_versao", "É a versão mais recente", "booleano", "(p.versao = ult.versao)", "Proposta", ("ult",),
          ajuda="Filtre por 'Sim' para contar cada negociação uma vez só."),
    Campo("executivo", "Executivo da proposta", "texto", "p.executivo_nome", "Equipe"),
    Campo("cidade_proposta", "Cidade da proposta", "texto", "p.cidade", "Proposta"),
    Campo("vidas", "Vidas", "numero", "p.vidas", "Valores"),
    Campo("valor_por_vida", "Valor por vida (R$)", "moeda", "p.valor_por_vida", "Valores"),
    Campo("mensalidade", "Mensalidade proposta (R$)", "moeda", "(p.vidas * p.valor_por_vida)", "Valores",
          ajuda="Vidas × valor por vida."),
    Campo("treinamentos", "Treinamentos (R$)", "moeda", "p.treinamentos", "Valores"),
    Campo("laudos", "Laudos (R$)", "moeda", "p.laudos", "Valores"),
    Campo("investimento", "Investimento total (R$)", "moeda",
          "(p.vidas * p.valor_por_vida + p.treinamentos + p.laudos)", "Valores",
          ajuda="Mensalidade + treinamentos + laudos, como no quadro da proposta."),
    Campo("dias_validade", "Validade (dias)", "numero", "(p.validade - p.data_proposta)", "Proposta"),
    Campo("data_proposta", "Data da proposta", "data", "p.data_proposta", "Datas", referencia=True),
    Campo("data_geracao", "Data em que foi gerada", "data", "p.criado_em", "Datas", com_hora=True, referencia=True),
    Campo("data_validade", "Válida até", "data", "p.validade", "Datas", referencia=True),
    Campo("oportunidade_numero", "Número da oportunidade", "texto", "o.numero", "Oportunidade", ("o",)),
    Campo("oportunidade_fase", "Fase da oportunidade", "texto", "o.fase", "Oportunidade", ("o",), valores=FASES),
    Campo("oportunidade_situacao", "Situação da oportunidade", "texto", "o.status", "Oportunidade", ("o",),
          valores=SITUACOES_OPP),
    Campo("foi_conquistada", "Oportunidade foi conquistada", "booleano", "(o.status = 'conquistado')",
          "Oportunidade", ("o",)),
    *_campos_envolvidos("Oportunidade", ("o",)),
    *_campos_empresa(),
)

PROPOSTAS = Fonte(
    chave="propostas",
    rotulo="Propostas comerciais",
    descricao="Cada linha é uma versão de proposta gerada, com vidas, valores e a oportunidade de origem.",
    rotulo_registro="propostas",
    from_sql="propostas p",
    joins=_PROP_JOINS,
    campos=_PROP_CAMPOS,
    recorte=_recorte_envolvido("p.oportunidade_id"),
    data_padrao="data_proposta",
    colunas_registro=("oportunidade_numero", "empresa_fantasia", "versao", "vidas", "mensalidade", "executivo", "data_proposta"),
    abrir=(("oportunidade", "p.oportunidade_id"),),
)


# ── Fonte: Contas ────────────────────────────────────────────────────
#
# Contas sao base compartilhada (decisao D5): todo mundo ve o cadastro. Mas
# os NUMEROS DE NEGOCIACAO dentro da conta respeitam o escopo -- o lateral
# abaixo so conta as oportunidades que quem esta olhando enxerga.

_CONTA_JOINS = {
    "c": ("", ()),  # a propria base
    **_joins_empresa(),
    "uc": ("LEFT JOIN usuarios uc ON uc.id = c.criado_por", ()),
    "opp": (
        "LEFT JOIN LATERAL ("
        " SELECT count(*) AS total,"
        "        count(*) FILTER (WHERE o2.status IN ('ativa','suspensa')) AS abertas,"
        "        count(*) FILTER (WHERE o2.status = 'conquistado') AS conquistadas,"
        "        COALESCE(sum(o2.valor_mensalidade) FILTER (WHERE o2.status = 'conquistado'), 0) AS mensal_conquistada,"
        "        COALESCE(sum(o2.valor_mensalidade) FILTER (WHERE o2.status IN ('ativa','suspensa')), 0) AS mensal_aberta"
        "   FROM oportunidades o2 WHERE o2.conta_id = c.id AND " + _recorte_envolvido("o2.id") +
        ") opp ON TRUE",
        (),
    ),
    "ind": (
        "LEFT JOIN LATERAL (SELECT count(*) AS qtd FROM oportunidades o3"
        " WHERE o3.finder_conta_id = c.id) ind ON TRUE",
        (),
    ),
    "cts": (
        "LEFT JOIN LATERAL (SELECT count(*) AS qtd FROM conta_contatos cc"
        " WHERE cc.conta_id = c.id AND cc.ativo) cts ON TRUE",
        (),
    ),
}

_CONTA_CAMPOS = (
    *_campos_empresa("Cadastro"),
    Campo("situacao_cadastral", "Situação cadastral (Receita)", "texto", "c.situacao_cadastral", "Cadastro"),
    Campo("origem_funcionarios", "Origem do nº de funcionários", "texto", "c.num_funcionarios_origem", "Cadastro",
          valores=ORIGENS_FUNCIONARIOS),
    Campo("capital_social", "Capital social (R$)", "moeda", "c.capital_social", "Cadastro"),
    Campo("ec_responsavel", "EC responsável (parceiro)", "texto", "ecr.nome", "Parceria", ("ecr",)),
    Campo("motivo_nao_prospectar", "Motivo do bloqueio de prospecção", "texto", "c.nao_prospectar_motivo", "Cadastro"),
    Campo("conta_ativa", "Conta ativa", "booleano", "c.ativo", "Cadastro"),
    Campo("dados_receita", "Dados da Receita aplicados", "booleano", "(c.enriquecida_em IS NOT NULL)", "Cadastro"),
    Campo("cadastrada_por", "Cadastrada por", "texto", "uc.nome", "Cadastro", ("uc",)),
    Campo("qtd_oportunidades", "Qtd. de oportunidades", "numero", "opp.total", "Negócios", ("opp",)),
    Campo("qtd_oportunidades_abertas", "Qtd. de oportunidades em aberto", "numero", "opp.abertas", "Negócios", ("opp",)),
    Campo("qtd_conquistadas", "Qtd. de oportunidades conquistadas", "numero", "opp.conquistadas", "Negócios", ("opp",)),
    Campo("eh_cliente", "É cliente (tem oportunidade conquistada)", "booleano", "(opp.conquistadas > 0)",
          "Negócios", ("opp",)),
    Campo("mensalidade_conquistada", "Mensalidade conquistada (R$)", "moeda", "opp.mensal_conquistada",
          "Negócios", ("opp",)),
    Campo("mensalidade_em_aberto", "Mensalidade em negociação (R$)", "moeda", "opp.mensal_aberta",
          "Negócios", ("opp",)),
    Campo("qtd_indicacoes", "Qtd. de indicações feitas (como parceiro)", "numero", "ind.qtd", "Parceria", ("ind",)),
    Campo("qtd_contatos", "Qtd. de contatos ativos", "numero", "cts.qtd", "Cadastro", ("cts",)),
    Campo("data_cadastro", "Data de cadastro no HIPO", "data", "c.criado_em", "Datas", com_hora=True, referencia=True),
    Campo("data_abertura_empresa", "Data de abertura da empresa (Receita)", "data", "c.data_abertura", "Datas",
          referencia=True),
    Campo("data_atualizacao", "Última atualização do cadastro", "data", "c.atualizado_em", "Datas",
          com_hora=True, referencia=True),
    Campo("data_bloqueio", "Data do bloqueio de prospecção", "data", "c.nao_prospectar_em", "Datas",
          com_hora=True, referencia=True),
)

CONTAS = Fonte(
    chave="contas",
    rotulo="Contas (empresas)",
    descricao="Cada linha é uma empresa cadastrada: dados da Receita, parceria e resumo dos negócios.",
    rotulo_registro="contas",
    from_sql="contas c",
    joins=_CONTA_JOINS,
    campos=_CONTA_CAMPOS,
    # Base compartilhada: sem recorte. O `:escopo` fica citado mesmo assim
    # porque o Postgres recusa parametro ($1) que o SQL nao usa.
    recorte="(:escopo IS NULL OR TRUE)",
    data_padrao="data_cadastro",
    colunas_registro=("empresa_fantasia", "empresa_cnpj", "empresa_vertical", "empresa_cidade",
                      "qtd_oportunidades", "data_cadastro"),
    abrir=(("conta", "c.id"),),
)


# ── Fonte: Contatos ──────────────────────────────────────────────────
#
# Um contato pode estar em mais de uma empresa. Para nao duplicar linha, a
# empresa do contato e a do vinculo PRINCIPAL (ou, sem principal, o vinculo
# ativo mais antigo).

_CTT_JOINS = {
    "vin": (
        "LEFT JOIN LATERAL (SELECT cc.conta_id, cc.cargo FROM conta_contatos cc"
        " WHERE cc.contato_id = k.id AND cc.ativo"
        " ORDER BY cc.principal DESC, cc.criado_em LIMIT 1) vin ON TRUE",
        (),
    ),
    "c": ("LEFT JOIN contas c ON c.id = vin.conta_id", ("vin",)),
    **_joins_empresa(),
    "uc": ("LEFT JOIN usuarios uc ON uc.id = k.criado_por", ()),
    "nvin": (
        "LEFT JOIN LATERAL (SELECT count(*) AS qtd FROM conta_contatos cc2"
        " WHERE cc2.contato_id = k.id AND cc2.ativo) nvin ON TRUE",
        (),
    ),
}

_MESES = (
    ("01", "Janeiro"), ("02", "Fevereiro"), ("03", "Março"), ("04", "Abril"),
    ("05", "Maio"), ("06", "Junho"), ("07", "Julho"), ("08", "Agosto"),
    ("09", "Setembro"), ("10", "Outubro"), ("11", "Novembro"), ("12", "Dezembro"),
)

_CTT_CAMPOS = (
    Campo("nome", "Nome do contato", "texto", "k.nome", "Contato"),
    Campo("cargo", "Cargo na empresa", "texto", "vin.cargo", "Contato", ("vin",)),
    Campo("tem_email", "Tem e-mail", "booleano", "(k.email IS NOT NULL AND btrim(k.email) <> '')", "Contato"),
    Campo("tem_telefone", "Tem telefone", "booleano", "(k.telefone IS NOT NULL AND btrim(k.telefone) <> '')", "Contato"),
    Campo("mes_aniversario", "Mês de aniversário", "texto", "to_char(k.data_nascimento, 'MM')", "Contato",
          valores=_MESES),
    Campo("contato_ativo", "Contato ativo", "booleano", "k.ativo", "Contato"),
    Campo("qtd_empresas", "Qtd. de empresas vinculadas", "numero", "nvin.qtd", "Contato", ("nvin",)),
    Campo("cadastrado_por", "Cadastrado por", "texto", "uc.nome", "Contato", ("uc",)),
    Campo("data_cadastro", "Data de cadastro", "data", "k.criado_em", "Datas", com_hora=True, referencia=True),
    *(
        Campo(c.chave, c.rotulo, c.tipo, c.sql, "Empresa principal", ("vin",) + c.joins,
              c.ajuda, c.valores, c.com_hora, c.referencia, c.dimensao)
        for c in _campos_empresa()
    ),
)

CONTATOS = Fonte(
    chave="contatos",
    rotulo="Contatos",
    descricao="Cada linha é uma pessoa de contato, com a empresa principal a que está vinculada.",
    rotulo_registro="contatos",
    from_sql="contatos k",
    joins=_CTT_JOINS,
    campos=_CTT_CAMPOS,
    # Base compartilhada: sem recorte. O `:escopo` fica citado mesmo assim
    # porque o Postgres recusa parametro ($1) que o SQL nao usa.
    recorte="(:escopo IS NULL OR TRUE)",
    data_padrao="data_cadastro",
    colunas_registro=("nome", "cargo", "empresa_fantasia", "data_cadastro"),
    abrir=(("conta", "c.id"),),
    joins_abrir=("c",),
)


# ── Fonte: Movimentacoes do funil ────────────────────────────────────

_MOV_JOINS = {
    "o": ("JOIN oportunidades o ON o.id = e.oportunidade_id", ()),
    "c": ("JOIN contas c ON c.id = o.conta_id", ("o",)),
    **_joins_empresa(),
    "ue": ("LEFT JOIN usuarios ue ON ue.id = e.usuario_id", ()),
    "env": (_envolvidos_lateral("o"), ("o",)),
}

_MOV_CAMPOS = (
    Campo("tipo", "Tipo de movimentação", "texto", "e.tipo", "Movimentação", valores=TIPOS_EVENTO),
    Campo("de", "De", "texto", "e.de", "Movimentação", valores=ESTADOS_EVENTO,
          ajuda="Fase ou situação de onde a oportunidade saiu."),
    Campo("para", "Para", "texto", "e.para", "Movimentação", valores=ESTADOS_EVENTO,
          ajuda="Fase ou situação para onde foi. Ex.: 'Para = Negociação' conta quem chegou à negociação."),
    Campo("feita_por", "Feita por", "texto", "ue.nome", "Movimentação", ("ue",)),
    Campo("data_movimentacao", "Data da movimentação", "data", "e.criado_em", "Datas", com_hora=True, referencia=True),
    Campo("oportunidade_numero", "Número da oportunidade", "texto", "o.numero", "Oportunidade", ("o",)),
    Campo("oportunidade_fase", "Fase atual da oportunidade", "texto", "o.fase", "Oportunidade", ("o",), valores=FASES),
    Campo("oportunidade_situacao", "Situação atual da oportunidade", "texto", "o.status", "Oportunidade", ("o",),
          valores=SITUACOES_OPP),
    Campo("oportunidade_mensalidade", "Mensalidade da oportunidade (R$)", "moeda", "o.valor_mensalidade",
          "Oportunidade", ("o",)),
    *_campos_envolvidos("Oportunidade", ("o",)),
    *_campos_empresa(),
)

MOVIMENTACOES = Fonte(
    chave="movimentacoes",
    rotulo="Movimentações do funil",
    descricao="Cada linha é uma mudança de fase ou de situação de uma oportunidade — a trilha do funil.",
    rotulo_registro="movimentações",
    from_sql="oportunidade_eventos e",
    joins=_MOV_JOINS,
    campos=_MOV_CAMPOS,
    recorte=_recorte_envolvido("e.oportunidade_id"),
    data_padrao="data_movimentacao",
    colunas_registro=("data_movimentacao", "oportunidade_numero", "empresa_fantasia", "tipo", "de", "para", "feita_por"),
    abrir=(("oportunidade", "e.oportunidade_id"),),
)


FONTES: dict[str, Fonte] = {
    f.chave: f
    for f in (OPORTUNIDADES, TAREFAS, REUNIOES, PROPOSTAS, MOVIMENTACOES, CONTAS, CONTATOS)
}


def fonte(chave: str) -> Fonte:
    f = FONTES.get(chave)
    if f is None:
        raise ConsultaInvalida(f"Fonte de dados '{chave}' não existe.")
    return f


# ── Catalogo para a tela ─────────────────────────────────────────────

def catalogo() -> dict:
    """O que a tela precisa para montar o construtor. Nunca inclui SQL."""
    fontes = []
    for f in FONTES.values():
        campos = []
        for c in f.campos:
            campos.append({
                "chave": c.chave,
                "rotulo": c.rotulo,
                "tipo": c.tipo,
                "grupo": c.grupo,
                "ajuda": c.ajuda,
                "valores": [{"valor": v, "rotulo": r} for v, r in c.valores],
                "referencia": c.referencia,
                "dimensao": c.dimensao,
                "agregacoes": list(c.agregacoes()),
            })
        fontes.append({
            "chave": f.chave,
            "rotulo": f.rotulo,
            "descricao": f.descricao,
            "rotulo_registro": f.rotulo_registro,
            "data_padrao": f.data_padrao,
            "colunas_registro": list(f.colunas_registro),
            "campos": campos,
        })
    return {
        "fontes": fontes,
        "agregacoes": AGREGACOES,
        "granularidades": GRANULARIDADES,
        "operadores": OPERADORES,
        "presets_periodo": PRESETS_PERIODO,
        "limites": {
            "linhas": MAX_LINHAS,
            "colunas": MAX_COLUNAS,
            "valores": MAX_VALORES,
            "filtros": MAX_FILTROS,
            "dias_periodo": MAX_DIAS_PERIODO,
            "combinacoes_coluna": MAX_COMBINACOES_COLUNA,
        },
    }


# ── Rotulos ──────────────────────────────────────────────────────────

def rotulo_dimensao(f: Fonte, campo: str, granularidade: str | None) -> str:
    c = f.campo(campo)
    if c.tipo == "data" and granularidade:
        return f"{c.rotulo} ({GRANULARIDADES[granularidade].lower()})"
    return c.rotulo


def rotulo_medida(f: Fonte, campo: str, agregacao: str) -> str:
    if campo == "*":
        return f"Quantidade de {f.rotulo_registro}"
    c = f.campo(campo)
    if agregacao == "percentual":
        return f"% {c.rotulo}"
    if agregacao == "soma" and c.tipo == "booleano":
        return f"Qtd. com '{c.rotulo}'"
    return f"{AGREGACOES[agregacao]} de {c.rotulo}"


def formato_medida(f: Fonte, campo: str, agregacao: str) -> str:
    """Como a tela formata o numero: inteiro, decimal, moeda ou percentual."""
    if campo == "*" or agregacao in ("contagem", "contagem_distinta"):
        return "inteiro"
    c = f.campo(campo)
    if agregacao == "percentual":
        return "percentual"
    if c.tipo == "booleano":
        return "inteiro"
    if c.tipo == "moeda":
        return "moeda"
    return "decimal" if agregacao == "media" else "numero"


# ── Montagem do SQL ──────────────────────────────────────────────────

class _Params:
    """Numeracao posicional. $1..$3 sao fixos (escopo, inicio, fim)."""

    def __init__(self, escopo, inicio: date, fim: date):
        self.valores: list = [escopo, inicio, fim]

    def add(self, valor) -> str:
        self.valores.append(valor)
        return f"${len(self.valores)}"


def _sql_escopo(sql: str) -> str:
    return sql.replace(":escopo", "$1::uuid")


def _expr_dimensao(c: Campo, granularidade: str | None) -> str:
    """Expressao TIPADA da dimensao (antes do ::text)."""
    if c.tipo != "data":
        return c.sql
    base = f"({c.sql} AT TIME ZONE '{FUSO}')" if c.com_hora else f"({c.sql})::timestamp"
    g = granularidade or GRANULARIDADE_PADRAO
    if g == "dia":
        return f"({base})::date"
    return f"date_trunc('{_GRAN_SQL[g]}', {base})::date"


def _expr_texto(c: Campo, granularidade: str | None) -> str:
    return f"({_expr_dimensao(c, granularidade)})::text"


def _expr_data_local(c: Campo) -> str:
    if c.com_hora:
        return f"({c.sql} AT TIME ZONE '{FUSO}')::date"
    return f"({c.sql})::date"


def validar_granularidade(c: Campo, granularidade: str | None) -> str | None:
    if c.tipo == "data":
        g = granularidade or GRANULARIDADE_PADRAO
        if g not in GRANULARIDADES:
            raise ConsultaInvalida(f"Agrupamento de data '{g}' não existe.")
        return g
    if granularidade:
        raise ConsultaInvalida(f"'{c.rotulo}' não é data — não aceita agrupamento por período.")
    return None


def _resolver_joins(f: Fonte, pedidos: set[str]) -> list[str]:
    """Fecha as dependencias e devolve os JOINs na ordem declarada."""
    necessarios: set[str] = set()

    def visitar(nome: str) -> None:
        if nome in necessarios:
            return
        if nome not in f.joins:
            raise ConsultaInvalida(f"Junção interna '{nome}' não declarada em {f.rotulo}.")
        necessarios.add(nome)
        for dep in f.joins[nome][1]:
            visitar(dep)

    for p in pedidos:
        visitar(p)
    return [f.joins[n][0] for n in f.joins if n in necessarios and f.joins[n][0]]


def _clausula_periodo(c: Campo, p: _Params) -> str:
    # Timestamptz: faixa semiaberta no fuso da operacao, que usa indice.
    # O dia 'fim' entra inteiro (ate a meia-noite do dia seguinte).
    if c.com_hora:
        return (
            f"{c.sql} >= ($2::date::timestamp AT TIME ZONE '{FUSO}')"
            f" AND {c.sql} < (($3::date + 1)::timestamp AT TIME ZONE '{FUSO}')"
        )
    return f"{c.sql} BETWEEN $2::date AND $3::date"


def validar_periodo(f: Fonte, data_ref: str, inicio: date, fim: date) -> Campo:
    c = f.campo(data_ref)
    if c.tipo != "data" or not c.referencia:
        raise ConsultaInvalida(f"'{c.rotulo}' não pode ser usada como data do período.")
    if inicio > fim:
        raise ConsultaInvalida("A data inicial do período é depois da final.")
    if (fim - inicio).days > MAX_DIAS_PERIODO:
        raise ConsultaInvalida("Período longo demais: o limite é de 10 anos.")
    return c


def _clausula_filtro(f: Fonte, filtro: dict, p: _Params) -> tuple[str, tuple[str, ...]]:
    c = f.campo(filtro["campo"])
    if not c.dimensao:
        raise ConsultaInvalida(f"'{c.rotulo}' não pode ser usado como filtro.")
    g = validar_granularidade(c, filtro.get("granularidade"))
    op = filtro.get("operador") or "em"
    if op not in OPERADORES:
        raise ConsultaInvalida(f"Operador de filtro '{op}' não existe.")

    if op in ("em", "nao_em"):
        valores = filtro.get("valores") or []
        if not valores:
            raise ConsultaInvalida(f"O filtro de '{c.rotulo}' está sem nenhum valor marcado.")
        if len(valores) > MAX_VALORES_POR_FILTRO:
            raise ConsultaInvalida(f"Valores demais no filtro de '{c.rotulo}'.")
        texto = _expr_texto(c, g)
        nao_nulos = [str(v) for v in valores if v is not None]
        tem_nulo = any(v is None for v in valores)
        partes = []
        if nao_nulos:
            partes.append(f"{texto} = ANY({p.add(nao_nulos)}::text[])")
        if tem_nulo:
            partes.append(f"{texto} IS NULL")
        positivo = "(" + " OR ".join(partes) + ")"
        if op == "em":
            return positivo, c.joins
        # "nao e nenhum destes": NULL fica de fora so se "(em branco)" foi marcado.
        if tem_nulo:
            return f"NOT COALESCE({positivo}, FALSE)", c.joins
        return f"({texto} IS NULL OR NOT {positivo})", c.joins

    if op == "entre":
        if c.tipo not in ("numero", "moeda", "data"):
            raise ConsultaInvalida(f"'{c.rotulo}' não é número nem data — use 'é um destes'.")
        minimo, maximo = filtro.get("minimo"), filtro.get("maximo")
        if minimo in (None, "") and maximo in (None, ""):
            raise ConsultaInvalida(f"O filtro de '{c.rotulo}' está sem mínimo e sem máximo.")
        if c.tipo == "data":
            expr, cast = _expr_data_local(c), "date"
        else:
            expr, cast = f"({c.sql})", "numeric"
        partes = []
        try:
            if minimo not in (None, ""):
                partes.append(f"{expr} >= {p.add(_converter(minimo, cast))}::{cast}")
            if maximo not in (None, ""):
                partes.append(f"{expr} <= {p.add(_converter(maximo, cast))}::{cast}")
        except ValueError:
            raise ConsultaInvalida(f"Valor inválido no filtro de '{c.rotulo}'.")
        return "(" + " AND ".join(partes) + ")", c.joins

    # contem
    texto_busca = (filtro.get("texto") or "").strip()
    if not texto_busca:
        raise ConsultaInvalida(f"O filtro de '{c.rotulo}' está sem texto.")
    return f"({c.sql})::text ILIKE {p.add('%' + texto_busca + '%')}", c.joins


def _converter(valor, cast: str):
    from decimal import Decimal, InvalidOperation
    if cast == "date":
        return date.fromisoformat(str(valor))
    try:
        return Decimal(str(valor).replace(",", "."))
    except InvalidOperation as e:
        raise ValueError(str(e))


def _base(
    f: Fonte, consulta: dict, escopo, dims: list[tuple[Campo, str | None]],
    selects_extra: list[tuple[str, tuple[str, ...]]], filtros_extra: list[dict] | None = None,
    ignorar_filtro_campo: str | None = None,
) -> tuple[str, _Params]:
    """
    Monta o `FROM ... WHERE ...` comum a consulta, drilldown e valores.

    Devolve o corpo do CTE `base` (SELECT ... FROM ... WHERE ...) e os
    parametros. `selects_extra` sao (expressao AS alias, joins).
    """
    per = consulta["periodo"]
    c_ref = validar_periodo(f, per["data_ref"], per["inicio"], per["fim"])
    p = _Params(escopo, per["inicio"], per["fim"])

    joins: set[str] = set(c_ref.joins) | set(f.joins_recorte)
    where = [f.recorte, _clausula_periodo(c_ref, p)]

    filtros = list(consulta.get("filtros") or [])
    if len(filtros) > MAX_FILTROS:
        raise ConsultaInvalida(f"Filtros demais: o limite é {MAX_FILTROS}.")
    for filtro in filtros + list(filtros_extra or []):
        if ignorar_filtro_campo and filtro.get("campo") == ignorar_filtro_campo:
            continue
        clausula, j = _clausula_filtro(f, filtro, p)
        where.append(clausula)
        joins |= set(j)

    selects = []
    for i, (c, g) in enumerate(dims):
        selects.append(f"{_expr_texto(c, g)} AS d{i}")
        joins |= set(c.joins)
    for expr, j in selects_extra:
        selects.append(expr)
        joins |= set(j)
    if not selects:
        selects.append("1 AS um")

    sql = (
        "SELECT " + ", ".join(selects)
        + f" FROM {f.from_sql} "
        + " ".join(_resolver_joins(f, joins))
        + " WHERE " + " AND ".join(where)
    )
    # `:escopo` aparece no recorte e tambem dentro de joins (o lateral de
    # negocios da conta). Substituido no SQL montado inteiro, de uma vez.
    return _sql_escopo(sql), p


def _dims(f: Fonte, refs: list[dict], onde: str) -> list[tuple[Campo, str | None]]:
    saida = []
    for r in refs:
        c = f.campo(r["campo"])
        if not c.dimensao:
            raise ConsultaInvalida(f"'{c.rotulo}' não pode ir em {onde}.")
        saida.append((c, validar_granularidade(c, r.get("granularidade"))))
    return saida


def _medidas(f: Fonte, valores: list[dict]) -> list[tuple[str, str, Campo | None]]:
    if not valores:
        valores = [{"campo": "*", "agregacao": "contagem"}]
    if len(valores) > MAX_VALORES:
        raise ConsultaInvalida(f"Valores demais: o limite é {MAX_VALORES}.")
    saida = []
    for v in valores:
        campo, ag = v.get("campo"), v.get("agregacao")
        if campo == "*":
            if ag != "contagem":
                raise ConsultaInvalida("Contagem de registros só aceita 'Quantidade'.")
            saida.append((campo, ag, None))
            continue
        c = f.campo(campo)
        if ag not in c.agregacoes():
            raise ConsultaInvalida(
                f"'{c.rotulo}' não aceita '{AGREGACOES.get(ag, ag)}'. "
                f"Opções: {', '.join(AGREGACOES[a] for a in c.agregacoes()) or 'nenhuma'}."
            )
        saida.append((campo, ag, c))
    return saida


def _agregado(ag: str, alias: str, c: Campo | None) -> str:
    if ag == "contagem":
        return "count(*)"
    if ag == "contagem_distinta":
        return f"count(DISTINCT {alias})"
    if ag == "percentual":
        return f"round(avg(({alias})::int) * 100, 1)"
    if c is not None and c.tipo == "booleano":  # soma de booleano
        return f"sum(({alias})::int)"
    fn = {"soma": "sum", "media": "avg", "minimo": "min", "maximo": "max"}[ag]
    if ag == "media":
        return f"round(avg({alias})::numeric, 2)"
    return f"{fn}({alias})"


def grouping_sets(n_linhas: int, n_colunas: int) -> list[tuple[int, ...]]:
    """
    Conjuntos de agrupamento, em indices de dimensao (linhas primeiro).

    Para cada prefixo das linhas (do total geral ate o detalhe), um conjunto
    COM as colunas (a celula) e, havendo colunas, um SEM (o total da linha).

    >>> grouping_sets(2, 1)
    [(2,), (), (0, 2), (0,), (0, 1, 2), (0, 1)]
    >>> grouping_sets(1, 0)
    [(), (0,)]
    """
    cols = tuple(range(n_linhas, n_linhas + n_colunas))
    sets: list[tuple[int, ...]] = []
    for k in range(n_linhas + 1):
        pref = tuple(range(k))
        for s in ((pref + cols), pref) if cols else (pref,):
            if s not in sets:
                sets.append(s)
    return sets


def montar_consulta(consulta: dict, escopo) -> tuple[str, list, dict]:
    """
    SQL da tabela dinamica. Devolve (sql, params, meta).

    Cada linha do resultado tem d0..dn (texto ou NULL), g0..gn (1 quando a
    dimensao foi 'somada' naquele nivel -- subtotal/total), n (registros)
    e m0..mk (as medidas).
    """
    f = fonte(consulta["fonte"])
    linhas = _dims(f, consulta.get("linhas") or [], "linhas")
    colunas = _dims(f, consulta.get("colunas") or [], "colunas")
    if len(linhas) > MAX_LINHAS:
        raise ConsultaInvalida(f"Campos demais em linhas: o limite é {MAX_LINHAS}.")
    if len(colunas) > MAX_COLUNAS:
        raise ConsultaInvalida(f"Campos demais em colunas: o limite é {MAX_COLUNAS}.")
    chaves = [(c.chave, g) for c, g in linhas + colunas]
    if len(set(chaves)) != len(chaves):
        raise ConsultaInvalida("O mesmo campo aparece duas vezes entre linhas e colunas.")

    medidas = _medidas(f, consulta.get("valores") or [])
    dims = linhas + colunas

    extras: list[tuple[str, tuple[str, ...]]] = []
    for j, (campo, ag, c) in enumerate(medidas):
        if c is None:
            continue
        expr = f"({c.sql})::text" if ag == "contagem_distinta" else f"({c.sql})"
        extras.append((f"{expr} AS x{j}", c.joins))

    base_sql, p = _base(f, consulta, escopo, dims, extras)

    aggs = [f"{_agregado(ag, f'x{j}', c)} AS m{j}" for j, (_, ag, c) in enumerate(medidas)]
    cols_d = [f"d{i}" for i in range(len(dims))]
    cols_g = [f"GROUPING(d{i}) AS g{i}" for i in range(len(dims))]

    if dims:
        sets = grouping_sets(len(linhas), len(colunas))
        sets_sql = ", ".join("(" + ", ".join(f"d{i}" for i in s) + ")" for s in sets)
        sql = (
            f"WITH base AS ({base_sql}) "
            f"SELECT {', '.join(cols_d + cols_g)}, count(*) AS n, {', '.join(aggs)} "
            f"FROM base GROUP BY GROUPING SETS ({sets_sql}) "
            f"ORDER BY {', '.join(f'd{i} NULLS LAST' for i in range(len(dims)))} "
            f"LIMIT {MAX_CELULAS + 1}"
        )
    else:
        sql = f"WITH base AS ({base_sql}) SELECT count(*) AS n, {', '.join(aggs)} FROM base"

    meta = {
        "fonte": f,
        "linhas": linhas,
        "colunas": colunas,
        "medidas": medidas,
    }
    return sql, p.valores, meta


def descrever_resultado(meta: dict, consulta: dict) -> dict:
    """Cabecalho da resposta: rotulos e formatos que a tela usa."""
    f: Fonte = meta["fonte"]

    def dim(c: Campo, g):
        return {
            "campo": c.chave,
            "granularidade": g,
            "rotulo": rotulo_dimensao(f, c.chave, g),
            "tipo": c.tipo,
            "valores": [{"valor": v, "rotulo": r} for v, r in c.valores],
        }

    return {
        "fonte": f.chave,
        "fonte_rotulo": f.rotulo,
        "periodo": {
            "data_ref": consulta["periodo"]["data_ref"],
            "data_ref_rotulo": f.campo(consulta["periodo"]["data_ref"]).rotulo,
            "inicio": consulta["periodo"]["inicio"].isoformat(),
            "fim": consulta["periodo"]["fim"].isoformat(),
        },
        "linhas": [dim(c, g) for c, g in meta["linhas"]],
        "colunas": [dim(c, g) for c, g in meta["colunas"]],
        "valores": [
            {
                "campo": campo,
                "agregacao": ag,
                "rotulo": rotulo_medida(f, campo, ag),
                "formato": formato_medida(f, campo, ag),
            }
            for campo, ag, _ in meta["medidas"]
        ],
    }


def contar_combinacoes_coluna(celulas: list[dict], n_linhas: int, n_colunas: int) -> int:
    """Quantas colunas distintas a grade teria (o conjunto so-de-colunas)."""
    if not n_colunas:
        return 0
    return sum(
        1 for c in celulas
        if all(c["g"][:n_linhas]) and not any(c["g"][n_linhas:])
    )


def montar_registros(
    consulta: dict, escopo, celula: list[dict], limite: int, deslocamento: int,
) -> tuple[str, list, dict]:
    """
    Drilldown: os registros por tras de uma celula. `celula` e a lista de
    {campo, granularidade, valor} que identifica a celula clicada -- cada
    um vira um filtro 'em' com um valor so (NULL incluso).
    """
    f = fonte(consulta["fonte"])
    extras_filtro = [
        {"campo": x["campo"], "granularidade": x.get("granularidade"),
         "operador": "em", "valores": [x.get("valor")]}
        for x in celula
    ]
    cols = [(f.campo(k), None) for k in f.colunas_registro]
    c_ref = f.campo(consulta["periodo"]["data_ref"])

    selects: list[tuple[str, tuple[str, ...]]] = []
    for i, (c, _) in enumerate(cols):
        # Datas no drilldown saem com a hora local (ou so o dia).
        if c.tipo == "data":
            expr = (f"to_char({c.sql} AT TIME ZONE '{FUSO}', 'YYYY-MM-DD\"T\"HH24:MI')"
                    if c.com_hora else f"({c.sql})::text")
        else:
            expr = f"({c.sql})::text"
        selects.append((f"{expr} AS r{i}", c.joins))
    for i, (tipo, expr) in enumerate(f.abrir):
        selects.append((f"({expr})::text AS a{i}", f.joins_abrir))
    selects.append((f"{c_ref.sql} AS ordem_ref", c_ref.joins))

    base_sql, p = _base(f, consulta, escopo, [], selects, filtros_extra=extras_filtro)
    lim = p.add(min(max(int(limite), 1), MAX_REGISTROS_PAGINA))
    desl = p.add(max(int(deslocamento), 0))
    sql = (
        f"WITH base AS ({base_sql}) "
        f"SELECT *, count(*) OVER () AS total FROM base "
        f"ORDER BY ordem_ref DESC NULLS LAST LIMIT {lim} OFFSET {desl}"
    )
    meta = {
        "colunas": [
            {"campo": c.chave, "rotulo": c.rotulo, "tipo": c.tipo,
             "valores": [{"valor": v, "rotulo": r} for v, r in c.valores]}
            for c, _ in cols
        ],
        "abrir": [t for t, _ in f.abrir],
    }
    return sql, p.valores, meta


def montar_valores(
    consulta: dict, escopo, campo: str, granularidade: str | None, busca: str | None,
) -> tuple[str, list]:
    """
    Valores distintos de um campo, com a contagem, para a lista do filtro.
    Respeita periodo, recorte e os OUTROS filtros -- como o autofiltro do
    Excel, que so oferece o que sobra depois dos demais.
    """
    f = fonte(consulta["fonte"])
    c = f.campo(campo)
    if not c.dimensao:
        raise ConsultaInvalida(f"'{c.rotulo}' não pode ser usado como filtro.")
    g = validar_granularidade(c, granularidade)
    base_sql, p = _base(f, consulta, escopo, [(c, g)], [], ignorar_filtro_campo=campo)
    filtro_busca = ""
    if busca and busca.strip():
        filtro_busca = f"WHERE d0 ILIKE {p.add('%' + busca.strip() + '%')} "
    sql = (
        f"WITH base AS ({base_sql}) "
        f"SELECT d0 AS valor, count(*) AS n FROM base {filtro_busca}"
        f"GROUP BY d0 ORDER BY count(*) DESC, d0 NULLS LAST "
        f"LIMIT {MAX_VALORES_DISTINTOS + 1}"
    )
    return sql, p.valores


# ── Configuracao salva ───────────────────────────────────────────────

def validar_config_salva(config: dict) -> dict:
    """
    Valida a montagem que vai para `relatorios_salvos.config`.

    O periodo salvo e RELATIVO (preset) ou FIXO (datas). Relativo e o caso
    comum: "vendas deste mes" salvo em setembro tem que mostrar outubro em
    outubro. Valida campo a campo contra o catalogo atual, montando uma
    consulta de mentira -- o mesmo caminho que a execucao vai percorrer.
    """
    if not isinstance(config, dict):
        raise ConsultaInvalida("Configuração do relatório inválida.")
    per = config.get("periodo") or {}
    tipo = per.get("tipo")
    if tipo == "relativo":
        if per.get("preset") not in PRESETS_PERIODO:
            raise ConsultaInvalida("Período relativo desconhecido.")
        inicio = fim = date(2000, 1, 1)
    elif tipo == "fixo":
        try:
            inicio = date.fromisoformat(str(per.get("inicio")))
            fim = date.fromisoformat(str(per.get("fim")))
        except ValueError:
            raise ConsultaInvalida("Datas do período fixo inválidas.")
    else:
        raise ConsultaInvalida("O período precisa ser 'relativo' ou 'fixo'.")

    consulta = {
        "fonte": config.get("fonte"),
        "periodo": {"data_ref": per.get("data_ref"), "inicio": inicio, "fim": fim},
        "linhas": config.get("linhas") or [],
        "colunas": config.get("colunas") or [],
        "valores": config.get("valores") or [],
        "filtros": config.get("filtros") or [],
    }
    montar_consulta(consulta, None)  # levanta ConsultaInvalida se algo nao existe
    return config
