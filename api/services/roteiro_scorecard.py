"""
HIPO — O Roteiro de Vendas da Controller Med Seg, em forma de código.

Fonte: o documento "Roteiro de Vendas — Controller Med Seg" (30/09/2026),
seções "Estrutura da reunião" e "Padronização e acompanhamento". O
documento é para gente; este módulo é a parte dele que a máquina usa:

  * `ITENS`: os 10 itens do scorecard, com "o que procurar" e o critério de
    0, 1 e 2 pontos. É o que a IA aplica e o que a tela mostra.
  * `ROTEIRO`: o roteiro condensado (etapas, perguntas, objeções,
    fechamento). Vai no prompt da avaliação para a IA julgar a reunião
    contra o MÉTODO da casa, e não contra uma ideia genérica de venda.

VERSIONADO. Mudou um item ou um critério, sobe `VERSAO`. Cada avaliação
grava a versão com que foi feita, e notas de versões diferentes não se
comparam — a média do Monitor só junta avaliações da versão corrente.

Puro: sem banco, sem rede. Um teste trava 10 itens numerados de 1 a 10.
"""
from __future__ import annotations

from dataclasses import dataclass

VERSAO = "2026-09-30"

NOTA_MAXIMA_ITEM = 2
QTD_ITENS = 10
NOTA_MAXIMA = NOTA_MAXIMA_ITEM * QTD_ITENS          # 20

# Meta do roteiro: média 15+ em 60 dias. É o padrão do quadro do Monitor
# enquanto a gestão não gravar outra meta no mês.
META_PADRAO = 15.0

# Meta do tempo de fala do vendedor (indicador, fora da nota).
META_FALA_PCT = 40.0


@dataclass(frozen=True)
class Item:
    numero: int
    nome: str
    etapa: str
    o_que_procurar: str
    criterio_0: str
    criterio_1: str
    criterio_2: str


ITENS: tuple[Item, ...] = (
    Item(
        1, "Preparação", "Antes da reunião",
        "O vendedor cita um dado da empresa que pesquisou antes (unidades, "
        "segmento, contratações, expansão, fornecedor atual) e usa isso no "
        "rapport ou nas perguntas.",
        "Nenhum dado pesquisado aparece; só \"o SDR te explicou o que é a Controller?\".",
        "Cita um dado (vindo do SDR ou da pesquisa), mas não usa nas perguntas.",
        "Rapport e perguntas usam a pesquisa (\"vi que vocês abriram a unidade de...\").",
    ),
    Item(
        2, "Contrato de abertura", "1. Abertura",
        "Combina tempo, pauta (entender primeiro, apresentar depois) e que no "
        "final se decide junto o próximo passo. Não abre compartilhando tela.",
        "Vai direto para a apresentação, sem combinar nada.",
        "Pede para entender antes de apresentar, mas sem o combinado de decidir o próximo passo no final.",
        "Tempo, pauta e o combinado \"no final a gente decide junto se vale um próximo passo\".",
    ),
    Item(
        3, "Perguntas de Situação", "2. Diagnóstico (SPIN)",
        "Quantidade de perguntas factuais (vidas, CNPJs, fornecedor, quanto "
        "paga, quem envia o eSocial) feitas ANTES da primeira pergunta de "
        "Problema.",
        "Mais de 6 perguntas de situação antes da primeira de problema, ou nenhuma pergunta de problema na reunião.",
        "5 ou 6 perguntas de situação antes da primeira de problema.",
        "Até 4 perguntas de situação e já parte para o problema.",
    ),
    Item(
        4, "Perguntas de Problema", "2. Diagnóstico (SPIN)",
        "\"O que te incomoda no modelo atual?\", \"Se pudesse mudar uma coisa...\", "
        "\"Já aconteceu de...\", \"O PGR já inclui os riscos psicossociais?\". "
        "Perguntas que fazem o cliente falar de dificuldade, não de dado.",
        "Nenhuma pergunta de problema.",
        "Uma pergunta de problema.",
        "Duas ou mais perguntas de problema.",
    ),
    Item(
        5, "Perguntas de Implicação", "2. Diagnóstico (SPIN)",
        "Perguntas que fazem o CLIENTE dizer o custo do problema: \"Quanto custa "
        "um dia de funcionário parado?\", \"Se o fiscal chegasse amanhã, o que "
        "encontraria?\", \"O que acontece se nada mudar?\". Contar o risco como "
        "história ou afirmação NÃO conta: precisa ser pergunta.",
        "Nenhuma pergunta de implicação (afirmar o risco não conta).",
        "Uma pergunta de implicação.",
        "Duas ou mais perguntas de implicação.",
    ),
    Item(
        6, "Resumo de confirmação", "2. Diagnóstico (SPIN)",
        "Antes de apresentar, o vendedor resume o que ouviu (\"Deixa eu ver se "
        "entendi: hoje vocês têm..., o que mais pesa é...\") e o cliente confirma.",
        "Não resume o que ouviu antes de apresentar.",
        "Resume, mas não pede nem recebe a confirmação do cliente.",
        "Resume com as palavras do cliente e o cliente confirma (\"é isso\", \"isso mesmo\").",
    ),
    Item(
        7, "GPCT: prazo, decisor e consequência", "3. Qualificação",
        "O cliente respondeu: QUANDO precisa resolver (ou quando vence o "
        "contrato atual), QUEM decide/aprova, e O QUE ACONTECE se nada mudar.",
        "Nenhum dos três foi respondido.",
        "Um ou dois dos três foram respondidos.",
        "Os três foram respondidos.",
    ),
    Item(
        8, "Apresentação ligada às dores", "4. Solução",
        "Ao mostrar a solução, o vendedor retoma o que o cliente disse "
        "(\"você me falou de...\") e mostra só o que resolve aquilo; "
        "credenciais (30 anos, 100 mil vidas) vêm como prova, depois.",
        "Apresentação inteira e genérica, sem ligar a nada que o cliente disse.",
        "Liga parte da apresentação a uma dor do cliente.",
        "Toda a solução apresentada é ligada a uma dor dita pelo cliente.",
    ),
    Item(
        9, "Objeções com LAER", "5. Objeções",
        "Diante de objeção (\"está caro\", \"já temos fornecedor\", \"o contador "
        "cuida\", \"preciso pensar\", \"manda por e-mail\"), o vendedor ouve, "
        "acolhe e faz uma pergunta de exploração ANTES de responder.",
        "Rebateu direto ou aceitou a objeção sem explorar.",
        "Explorou pouco (uma pergunta rasa) antes de responder.",
        "Explorou a objeção com pergunta e respondeu ligando ao diagnóstico.",
    ),
    Item(
        10, "Próximo passo com data", "6. Fechamento",
        "A reunião termina com dia e hora combinados e aceitos pelo cliente "
        "(reunião com o decisor, apresentação da proposta, assinatura). "
        "\"Vou mandar por e-mail\" e \"a gente vai conversando\" não contam.",
        "Nenhum próximo passo concreto.",
        "Próximo passo sem data e hora (\"semana que vem\", \"te mando a proposta\").",
        "Dia e hora falados e aceitos pelo cliente.",
    ),
)

POR_NUMERO = {i.numero: i for i in ITENS}


ROTEIRO = """ROTEIRO DE VENDAS — CONTROLLER MED SEG (resumo usado na avaliação)

Regra única: diagnosticar antes de apresentar. O vendedor fala no máximo
30% do tempo (meta de acompanhamento: até 40%). A apresentação só entra
depois que o cliente disse, com as próprias palavras, qual é o problema e
quanto ele custa. Metodologia: contrato de abertura (Sandler), SPIN Selling
no diagnóstico, GPCT + BA/CI na qualificação, toque Challenger (um insight
que o cliente não tinha, ex.: risco psicossocial no PGR pela NR-1,
divergência no eSocial), objeções pelo método LAER.

Estrutura da reunião (45 min):
1. Abertura (5 min): rapport curto ligado à pesquisa (nunca ao clima);
   contrato de abertura ("combinamos 45 minutos... a ideia é eu entender
   primeiro como vocês cuidam hoje da saúde e segurança... no final a gente
   decide junto se vale um próximo passo ou se não é o momento"); credencial
   em UMA frase, sem slide; transição "para eu não te mostrar coisa que não
   serve, posso te fazer algumas perguntas?". Erros: abrir compartilhando a
   tela; falar da empresa por mais de 1 minuto; pular o combinado do final.
2. Diagnóstico SPIN (15 min): Situação (máx. 4, só o que a pesquisa não
   respondeu); Problema ("o que te incomoda no modelo atual?", "já aconteceu
   de um admissional atrasar?", "consegue saber em 5 minutos quais
   periódicos vencem?", "o PGR já inclui os riscos psicossociais?");
   Implicação, o bloco que mais converte ("quanto custa um dia de
   funcionário parado?", "se um fiscal chegasse amanhã e pedisse PGR, PCMSO
   e ASOs, o que encontraria?", "se houver afastamento com PGR desatualizado,
   como fica numa ação trabalhista?", "quantas horas o RH gasta corrigindo
   eSocial?"); Necessidade ("se tivesse tudo num lugar só, o que mudaria?").
   Resumo de confirmação obrigatório antes de apresentar. Técnicas: anotar
   as palavras exatas do cliente; "como assim?", "me dá um exemplo".
3. Qualificação GPCT + BA/CI (5 min): Metas, Planos, Desafios, Prazo
   ("quando precisa estar resolvido? o contrato atual vence quando?"),
   Orçamento (perguntar DEPOIS das implicações), Autoridade ("além de você,
   quem participa da decisão?"), Consequências ("o que acontece se nada
   mudar nos próximos 6 meses?"), Implicações. Proposta só com Prazo,
   Autoridade e Consequência respondidos; sem isso vira nutrição.
4. Solução (12 min): ordem dor » solução » prova. Benefício, não recurso
   ("você vê todos os vencimentos em tempo real", não "temos o SOC"). Usar
   as palavras do cliente. Pergunta de confirmação a cada bloco ("isso
   resolveria o que você comentou?"). Uma história de cliente do mesmo porte
   ou setor.
5. Objeções (5 min), LAER: Listar (ouvir até o fim), Acolher, Explorar
   (pergunta para achar a objeção real), Responder (com fato do
   diagnóstico). Nunca responder antes de explorar.
   - "Está caro": "caro comparado a quê? estão inclusos PGR, eSocial e
     gestão?" » comparar custo total; retomar a implicação.
   - "Já temos fornecedor": "e como está sendo? se pudesse melhorar uma
     coisa?" » não falar mal; oferecer diagnóstico da documentação.
   - "Nosso contador cuida": "ele cuida dos exames e do PGR ou só do envio
     do eSocial?" » o contador envia; o conteúdo técnico é de SST.
   - "Somos pequenos / não temos risco": NR-1 vale para todo CLT; risco
     psicossocial existe em qualquer escritório.
   - "Preciso pensar": "o que exatamente quer avaliar — preço, escopo ou o
     momento?" » fechar com data.
   - "Manda proposta por e-mail": nunca enviar sem reunião de apresentação
     marcada.
   - "O dono precisa aprovar": reunião de 20 min com o decisor.
   Desconto: antes, reduzir escopo; sempre em troca de algo (prazo maior,
   antecipação, indicação).
6. Fechamento (3 min): nenhuma reunião termina sem próximo passo com data e
   hora na agenda do cliente. Resumo de valor retomando o contrato de
   abertura; fechamento conforme a situação (direto; alternativa de
   horários; reunião com decisor; passo de baixo risco = diagnóstico da
   documentação; contrato vigente = marcar revisão 60 dias antes do
   vencimento). Convite de calendário ainda na reunião. Pergunta final:
   "tem alguma coisa que possa impedir a gente de avançar que eu ainda não
   sei?".

Produto (para conferir precisão técnica): plano por faixa de vidas com
exames clínicos (admissional, periódico, demissional, mudança de risco,
retorno) ilimitados, laudos PGR, PCMSO e LTCAT, NR-1 (gerenciamento de
riscos no PGR, inclusive psicossociais — não é um treinamento), envio dos
eventos de SST ao eSocial (S-2210, S-2220, S-2240), SOC e assessoria.
À parte: exames complementares e de laboratório, treinamentos de NR
específicos. Atendimento nacional por clínicas credenciadas próximas.
"""


def texto_dos_itens() -> str:
    """Os 10 itens com critério, no formato que vai para o prompt."""
    linhas = []
    for i in ITENS:
        linhas.append(
            f"{i.numero}. {i.nome} ({i.etapa})\n"
            f"   O que procurar: {i.o_que_procurar}\n"
            f"   0 = {i.criterio_0}\n"
            f"   1 = {i.criterio_1}\n"
            f"   2 = {i.criterio_2}"
        )
    return "\n".join(linhas)


def faixa(total: float | None) -> str | None:
    """
    A faixa da nota para a cor da tela. Mesma régua do relatório: 15+ é a
    meta do roteiro.

    >>> faixa(16), faixa(12), faixa(7), faixa(None)
    ('boa', 'media', 'baixa', None)
    """
    if total is None:
        return None
    if total >= META_PADRAO:
        return "boa"
    if total >= 10:
        return "media"
    return "baixa"


# ═════════════════════════════════════════════════════════════════════
# Guia rápido do vendedor (botão "Guia do roteiro" na reunião da Agenda)
# ═════════════════════════════════════════════════════════════════════
#
# Pedido do Tulio (07/10/2026): dentro da reunião, um botão que abre o
# script resumido do scorecard, com exemplos rápidos, para o EV usar como
# guia durante a call.
#
# Mora aqui, ao lado dos ITENS, para que guia e avaliação nunca divirjam:
# o vendedor lê na tela exatamente os 10 itens em que vai ser avaliado.
# Um teste trava um guia por item. O guia NÃO entra no prompt da avaliação:
# é material de apoio, e mudá-lo não muda nota nenhuma (por isso não sobe
# `VERSAO`).
#
# Os três 10 e as técnicas de fechamento são os da trilha
# "06 · Fechamento" da UC (scripts/uc_conteudo_fechamento.py).


@dataclass(frozen=True)
class Etapa:
    nome: str          # igual ao `Item.etapa`, para agrupar
    minutos: int | None


ETAPAS: tuple[Etapa, ...] = (
    Etapa("Antes da reunião", None),
    Etapa("1. Abertura", 5),
    Etapa("2. Diagnóstico (SPIN)", 15),
    Etapa("3. Qualificação", 5),
    Etapa("4. Solução", 12),
    Etapa("5. Objeções", 5),
    Etapa("6. Fechamento", 3),
)

DURACAO_REUNIAO_MIN = 45


@dataclass(frozen=True)
class Guia:
    item: int
    fazer: str
    exemplos: tuple[str, ...]
    evitar: str


GUIA: tuple[Guia, ...] = (
    Guia(
        1, "Cite um dado que você pesquisou e use nas perguntas.",
        (
            "Vi que vocês abriram a unidade de Guarulhos. Como ficou o admissional lá?",
            "Vocês são grau de risco 3, então audiometria entra no periódico, certo?",
        ),
        "\"O SDR te explicou o que é a Controller?\"",
    ),
    Guia(
        2, "Combine tempo, pauta e que no final se decide junto o próximo passo.",
        (
            "Combinamos 45 minutos. A ideia é eu entender primeiro como vocês cuidam "
            "hoje da saúde e segurança, depois mostro o que faz sentido, e no final a "
            "gente decide junto se vale um próximo passo ou se não é o momento. Pode ser?",
            "Para eu não te mostrar coisa que não serve, posso te fazer algumas perguntas?",
        ),
        "Abrir compartilhando a tela ou falar da empresa por mais de 1 minuto.",
    ),
    Guia(
        3, "No máximo 4 perguntas de dado, só o que a pesquisa não respondeu.",
        (
            "Quantos funcionários vocês têm hoje, e em quantos CNPJs?",
            "Quem cuida hoje dos exames e do PGR?",
        ),
        "Interrogatório de dados antes de chegar ao problema.",
    ),
    Guia(
        4, "Faça o cliente falar de dificuldade, não de dado.",
        (
            "O que te incomoda no modelo atual?",
            "Já aconteceu de um admissional atrasar o início de alguém?",
            "O PGR de vocês já inclui os riscos psicossociais?",
        ),
        "Pular direto para a solução depois do primeiro problema.",
    ),
    Guia(
        5, "Pergunte, e deixe o CLIENTE dizer o custo do problema.",
        (
            "Quanto custa um dia de funcionário parado esperando o ASO?",
            "Se um fiscal chegasse amanhã e pedisse PGR, PCMSO e ASOs, o que encontraria?",
            "O que acontece se nada mudar nos próximos 6 meses?",
        ),
        "Afirmar o risco (\"vocês podem ser multados\") em vez de perguntar.",
    ),
    Guia(
        6, "Resuma com as palavras dele e peça a confirmação antes de apresentar.",
        (
            "Deixa eu ver se entendi: hoje vocês têm..., e o que mais pesa é... É isso?",
        ),
        "Apresentar sem o \"é isso\" do cliente.",
    ),
    Guia(
        7, "Saia com prazo, decisor e consequência respondidos.",
        (
            "Quando isso precisa estar resolvido? O contrato atual vence quando?",
            "Além de você, quem participa da decisão?",
            "O que acontece se nada mudar?",
        ),
        "Mandar proposta sem saber quem decide e até quando.",
    ),
    Guia(
        8, "Dor » solução » prova. Benefício, não recurso. Confirme a cada bloco.",
        (
            "Você me falou que o admissional atrasa: com o plano, o ASO sai na clínica "
            "perto da unidade e você vê todos os vencimentos em tempo real.",
            "Isso resolveria o que você comentou?",
        ),
        "\"Temos o SOC\" (recurso solto, sem ligar a uma dor).",
    ),
    Guia(
        9, "Ouça até o fim, acolha e explore com uma pergunta ANTES de responder.",
        (
            "Caro comparado a quê? No que vocês pagam hoje estão inclusos PGR, eSocial e gestão?",
            "O contador cuida dos exames e do PGR ou só do envio do eSocial?",
            "O que exatamente você quer avaliar: o preço, o escopo ou o momento?",
        ),
        "Rebater na hora, dar desconto sem contrapartida ou aceitar sem explorar.",
    ),
    Guia(
        10, "Termine com dia e hora aceitos e o convite enviado na hora.",
        (
            "Te apresento a proposta na quinta às 10h ou na sexta às 15h?",
            "Já estou mandando o convite. Mais alguém precisa estar?",
            "Tem alguma coisa que possa impedir a gente de avançar que eu ainda não sei?",
        ),
        "\"Te mando por e-mail e a gente vai conversando.\"",
    ),
)

GUIA_POR_ITEM = {g.item: g for g in GUIA}


@dataclass(frozen=True)
class Certeza:
    nome: str
    sinal_baixo: str
    como_subir: str


# Os três 10 (método Linha Reta, de Jordan Belfort, adaptado à Controller).
TRES_DEZ: tuple[Certeza, ...] = (
    Certeza(
        "Produto",
        "\"Isso a gente já tem\", \"não sei se precisa\", \"está caro\".",
        "Volte à dor com as palavras dele, faça uma pergunta de implicação e "
        "mostre o benefício.",
    ),
    Certeza(
        "Você",
        "Respostas curtas, câmera fechada, \"manda por e-mail\".",
        "Resumo nas palavras dele, um insight (psicossocial no PGR) e diga também "
        "o que não recomenda.",
    ),
    Certeza(
        "Controller",
        "\"Nunca ouvi falar\", \"e se a clínica não atender?\".",
        "Caso do mesmo setor ou porte; desde 1991, mais de 500 clientes, "
        "atendimento nacional por clínicas credenciadas.",
    ),
)

PERGUNTA_CALIBRACAO = "De 0 a 10, quanto isso resolve o que você me contou sobre [dor]?"
PERGUNTA_O_QUE_FALTA = "O que faltaria para ser um 10?"
LOOPING_MAXIMO = 2


@dataclass(frozen=True)
class Fechamento:
    situacao: str
    tecnica: str
    frase: str


FECHAMENTOS: tuple[Fechamento, ...] = (
    Fechamento(
        "Toda abertura de fechamento", "Resumo de valor",
        "Você me contou que [dor] está custando [implicação]. Com [solução] isso "
        "se resolve. Combinamos decidir juntos o próximo passo: faz sentido seguirmos?",
    ),
    Fechamento(
        "Decisor presente, 6 ou mais verdes", "Direto",
        "Podemos começar a implantação no dia [X]? Preciso só dos dados para o contrato.",
    ),
    Fechamento(
        "Decisor presente, quer ver números", "Alternativa",
        "Te apresento a proposta na quinta às 10h ou na sexta às 15h?",
    ),
    Fechamento(
        "Decisor ausente", "Reunião com o decisor",
        "Vamos marcar 20 minutos com o [diretor] esta semana? Eu levo a proposta pronta.",
    ),
    Fechamento(
        "Inseguro sobre trocar", "Passo de baixo risco",
        "Que tal começarmos com um diagnóstico da documentação atual?",
    ),
    Fechamento(
        "Contrato vigente", "Futuro",
        "Seu contrato vence em [mês]. Vamos marcar agora a revisão para 60 dias antes?",
    ),
)

PERGUNTA_FINAL = "Tem alguma coisa que possa impedir a gente de avançar que eu ainda não sei?"


def guia_rapido() -> dict:
    """
    O guia inteiro, pronto para a tela: as etapas com tempo, os 10 itens do
    scorecard (nome, o que vale 2 pontos, o que fazer, exemplos, o que
    evitar), os três 10, as técnicas de fechamento e a pergunta final.
    """
    etapas = []
    for e in ETAPAS:
        itens = [
            {
                "item": i.numero,
                "nome": i.nome,
                "vale_2": i.criterio_2,
                "fazer": GUIA_POR_ITEM[i.numero].fazer,
                "exemplos": list(GUIA_POR_ITEM[i.numero].exemplos),
                "evitar": GUIA_POR_ITEM[i.numero].evitar,
            }
            for i in ITENS if i.etapa == e.nome
        ]
        etapas.append({"nome": e.nome, "minutos": e.minutos, "itens": itens})
    return {
        "versao_roteiro": VERSAO,
        "duracao_min": DURACAO_REUNIAO_MIN,
        "meta_fala_pct": META_FALA_PCT,
        "nota_maxima": NOTA_MAXIMA,
        "etapas": etapas,
        "tres_dez": {
            "certezas": [
                {"nome": c.nome, "sinal_baixo": c.sinal_baixo, "como_subir": c.como_subir}
                for c in TRES_DEZ
            ],
            "pergunta_calibracao": PERGUNTA_CALIBRACAO,
            "pergunta_o_que_falta": PERGUNTA_O_QUE_FALTA,
            "looping_maximo": LOOPING_MAXIMO,
        },
        "fechamentos": [
            {"situacao": f.situacao, "tecnica": f.tecnica, "frase": f.frase}
            for f in FECHAMENTOS
        ],
        "pergunta_final": PERGUNTA_FINAL,
    }
