"""
HIPO — UC: trilhas de uso do HIPO, uma por função (pilar Método).

  HIPO - SDR   obrigatória para SDR   (prazo 15 dias)
  HIPO - EV    obrigatória para EV    (prazo 15 dias)
  HIPO - EC    obrigatória para EC    (prazo 15 dias)

ADM e Franqueado veem as três sem obrigação: é a gestão que revisa o
conteúdo e treina quem chega.

Pedido do Tulio (02/10/2026): ensinar a usar o HIPO por função, e não só
explicar, mas fazer a pessoa NAVEGAR pelo sistema e enxergar o que está
sendo explicado. Por isso toda aula traz um `tour`: o botão "Me mostra no
HIPO" abre a tela real e um balão destaca cada elemento citado no texto.

FORMATO DO TOUR (validado por services/uc.validar_tour)
  rota    tela onde o passo acontece (lista fechada em ROTAS_TOUR)
  alvo    valor do atributo data-tour do elemento a destacar; None = balão
          no centro da tela
  titulo  até 80 caracteres
  texto   até 600 caracteres, aceita **negrito**
  clicar  (opcional) âncoras a clicar antes, a partir da tela limpa, para
          abrir o que o passo mostra: um cartão, uma aba, um formulário em
          branco. NUNCA um botão que grava. O teste
          tests/test_uc_conteudo.py confere que toda âncora usada existe no
          front e que nenhuma âncora de clique está fora da lista de
          ABRIDORES.

Os textos descrevem a tela como ela está no código em 02/10/2026 (rótulos,
regras e mensagens conferidos nas páginas e nos routers). Atualizado em
outubro/2026 com a Carreira (entrega 038): a Universidade virou a aba de
um item novo, Carreira, ao lado do PDI e do Desempenho; cada trilha ganhou
a aula "Carreira: o seu Desempenho" no fim. Tela mudou de
rótulo? Atualize a aula junto, e rode a carga com --atualizar.

Este arquivo é só dado. Quem grava é scripts/semear_uc.py.
"""
from __future__ import annotations

from uuid import UUID

# Âncoras que o tour pode CLICAR. Todas só abrem algo (cartão, aba, painel
# de filtro, formulário em branco); nenhuma grava. O teste recusa clique em
# âncora fora desta lista.
ABRIDORES = frozenset({
    "opo-cartao-abrir", "opo-filtros-botao", "opo-det-finalizar", "opo-det-agendar",
    "tar-cartao", "age-celula-livre", "age-cartao",
    "con-linha", "con-btn-nova", "par-linha",
    "aba-dados", "aba-tarefas", "aba-contatos", "aba-proposta", "aba-envolvidos", "aba-historico",
    "aba-indicacoes", "aba-carteira", "aba-dados-publicos",
})

GESTAO_OPCIONAL = ("ADM", "Franqueado")


def _id(sufixo: str) -> UUID:
    return UUID(f"7c1d0f4e-5a01-4c0e-9b11-0000000{sufixo}")


# ═════════════════════════════════════════════════════════════════════
# Passos reaproveitados pelas três trilhas
# ═════════════════════════════════════════════════════════════════════

def _passo(rota, alvo, titulo, texto, clicar=None):
    p = {"rota": rota, "alvo": alvo, "titulo": titulo, "texto": texto}
    if clicar:
        p["clicar"] = list(clicar)
    return p


PASSO_BARRA = _passo(
    "/crm/tarefas", "nav-principal", "A barra de cima",
    "Todas as telas que você usa ficam aqui, na ordem em que o dia acontece. "
    "O item sublinhado em azul é a tela aberta. Em tela estreita (celular), "
    "a barra vira o menu ☰ no canto esquerdo.",
)
PASSO_PERFIL = _passo(
    "/crm/tarefas", "usuario-menu", "Seu nome e o Perfil",
    "Clicando no seu nome você chega no **Perfil** (troca de senha e o "
    "telefone que sai na proposta) e no **Sair**. Usuário novo entra com a "
    "senha 123456: troque no primeiro dia.",
)
PASSO_UC = _passo(
    "/carreira", "uc-proxima", "Sua próxima aula",
    "Em **Carreira**, a aba Universidade abre sempre na **próxima aula**, "
    "escolhida pelo prazo. Quando terminar este tour, é aqui que você volta "
    "para continuar.",
)
PASSO_CARREIRA = _passo(
    "/carreira", "nav-carreira", "Carreira",
    "Estudo e desenvolvimento num lugar só, em três abas: **Universidade** "
    "(as trilhas), **PDI** (o seu plano de desenvolvimento) e **Desempenho** "
    "(os seus números contra a sua meta).",
)


def _tour_desempenho(principais: str, funil: str) -> list[dict]:
    """O tour da aba Desempenho; muda só o que é de cada função."""
    d = "/carreira/desempenho"
    return [
        PASSO_CARREIRA,
        _passo("/carreira", "carreira-abas", "As três abas",
               "**Universidade** abre na sua próxima aula. **PDI** é o seu plano de "
               "desenvolvimento (chega na próxima entrega). **Desempenho** mostra os "
               "seus números do mês contra a sua meta."),
        _passo(d, "des-mes", "O mês e o ritmo",
               "As setas trocam o mês. No mês atual, cada número é comparado com a "
               "**meta de hoje**, que acompanha os dias úteis como no Monitor. Mês "
               "fechado compara com a meta do mês inteiro."),
        _passo(d, "des-atencao", "Seu ponto de atenção",
               "O indicador mais longe da meta, quanto falta para a meta do mês e o "
               "botão **Agir em**, que leva à tela onde esse número se mexe. Se o "
               "cartão não aparece, está tudo em dia ou a meta ainda não foi cadastrada."),
        _passo(d, "des-principais", "Os principais", principais),
        _passo(d, "des-indicadores", "Todos os indicadores",
               "Os mesmos números da RPeR: realizado, meta de hoje, meta do mês e a "
               "carinha do atingimento. O link no fim da linha abre a tela onde se age."),
        _passo(d, "des-funil", "O funil e as taxas", funil),
        _passo(d, "des-historico", "Últimos meses",
               "Seis meses de realizado e atingimento, contra a meta de cada mês. É "
               "aqui que se vê se o ritmo está melhorando. O mês atual é parcial."),
    ]


TEXTO_CARREIRA_ABAS = """\
## A Carreira

No menu, a Universidade virou **Carreira**. É o lugar do seu desenvolvimento, em três abas:

- **Universidade**: as trilhas, como sempre. Abre na sua próxima aula.
- **PDI**: o seu plano de desenvolvimento individual. Chega na próxima entrega: as ações vão nascer do seu Desempenho e das suas trilhas, combinadas com a gestão.
- **Desempenho**: os seus números do mês contra a sua meta. É o assunto desta aula.

## De onde vêm os números

- **A meta** é a da RPeR, cadastrada pela gestão em **Monitor › RPeR › Metas por squad e pessoa**. Sem meta cadastrada para o mês, a tela avisa e mostra só o realizado.
- **O realizado** sai do que você lança no HIPO: são os mesmos números da RPeR, só que seus. Tarefa sem concluir, reunião sem desfecho e fase desatualizada não contam.

## Mês atual e meses fechados

No mês atual, cada indicador é comparado com a **meta de hoje**, proporcional aos dias úteis que já passaram, como no Monitor: no dia útil 10 de 20, a meta de hoje é metade da do mês. Taxa não acumula: a meta de hoje de uma taxa é a própria meta. Em um mês fechado, a comparação é com a meta do mês inteiro. As setas **‹ ›** trocam o mês.

A carinha segue o Monitor: de 110% para cima, muito feliz; de 100%, feliz; de 70%, neutra; de 50%, triste; abaixo de 50%, brava.
"""

TEXTO_CARREIRA_GESTAO = """\
## A gestão vê a mesma tela

Franqueado e ADM escolhem a pessoa no seletor **Pessoa** e veem o seu Desempenho em modo leitura, sem os botões de ação. A conversa de acompanhamento parte do mesmo número que você vê.

> Clique em **Me mostra no HIPO**: o tour abre a Carreira e aponta cada parte do Desempenho. Ele só mostra, não muda nada.
"""


# ═════════════════════════════════════════════════════════════════════
# HIPO - SDR
# ═════════════════════════════════════════════════════════════════════

HIPO_SDR = {
    "id": _id("b0200"),
    "titulo": "01 · HIPO - SDR",
    "pilar": "metodo",
    "reforca": "tarefas_no_prazo",
    "descricao": (
        "Como o SDR usa o HIPO de ponta a ponta: puxar empresas da base da "
        "Receita, trabalhar a fila de primeiro contato, qualificar no funil, "
        "marcar a reunião para o EV e acompanhar seus números. Cada aula tem "
        "o botão \"Me mostra no HIPO\", que abre a tela real e aponta o que "
        "foi explicado."
    ),
    "prazo_dias": 15,
    "obrigatorios": ("SDR",),
    "opcionais": GESTAO_OPCIONAL,
    "aulas": [
        {
            "id": _id("b0211"),
            "titulo": "O HIPO no dia do SDR",
            "resumo": "As telas que você usa, a ordem do seu dia e as duas regras que o sistema cobra de todo mundo.",
            "duracao_min": 8,
            "conteudo_md": """\
## O HIPO é a fonte da verdade

Tudo o que acontece com uma empresa, do primeiro telefonema ao contrato, é lançado no HIPO, por você, na hora. Não existe planilha paralela nem "depois eu atualizo". O que não está no HIPO não aconteceu: não conta no seu número, não aparece para o EV que vai conduzir a reunião e não entra no Monitor.

## As telas do SDR

Na barra de cima, da esquerda para a direita:

- **Prospecção**: fatiar a base da Receita e puxar empresas para o funil. Só SDR e gestão veem esta tela.
- **Oportunidades**: o funil. É onde a empresa anda de fase.
- **Tarefas**: tudo o que está em aberto, começando pelo que é seu.
- **Agenda**: a semana da equipe, onde você marca a reunião para o EV.
- **Contas**: o cadastro das empresas.
- **Relatórios** e **Monitor**: números e o painel da sala.
- **Carreira**: a Universidade, o seu PDI e o seu Desempenho contra a meta.

## O seu dia, na ordem

1. **Tarefas**: abre nas suas. Atrasadas primeiro, depois as de hoje.
2. **Prospecção**: quando a fila de primeiro contato está curta, puxe mais empresas.
3. **Oportunidades**: a cada conversa, a fase e os dados da empresa ficam em dia.
4. **Agenda**: interesse confirmado vira reunião marcada para o EV.
5. **Monitor**: no fim do dia, como estão LEAD, AGEN e no-show.

## As duas regras que o sistema cobra

- **Toda tarefa concluída pede a próxima.** Se você conclui a última tarefa aberta de uma oportunidade viva, o HIPO não deixa fechar sem marcar o próximo passo. Sem próximo passo, o caminho é finalizar a oportunidade.
- **Toda reunião tem desfecho.** Realizada, cancelada ou no-show: alguém registra. Reunião sem desfecho aparece como pendência na Agenda.

> Clique em **Me mostra no HIPO** abaixo: o sistema abre as telas reais e aponta cada item. Ele só mostra, não muda nada.
""",
            "tour": [
                PASSO_BARRA,
                _passo("/crm/prospeccao", "nav-prospeccao", "Prospecção",
                       "A boca do funil. Aqui você fatia a base da Receita (UF, CNAE, cidade, porte) "
                       "e puxa as empresas para o HIPO. Só SDR e gestão enxergam este item."),
                _passo("/crm/oportunidades", "nav-oportunidades", "Oportunidades",
                       "O funil de vendas: Suspect, Lead, Qualificação, Apresentação, Negociação e "
                       "Finalizado. Toda empresa que você puxa nasce aqui, em **Suspect**."),
                _passo("/crm/tarefas", "nav-tarefas", "Tarefas",
                       "Sua fila de trabalho. Abre já filtrada em você, com as atrasadas na primeira coluna."),
                _passo("/crm/agenda", "nav-agenda", "Agenda",
                       "A semana da equipe, de 30 em 30 minutos. É aqui que você marca a reunião para o EV."),
                _passo("/crm/contas", "nav-contas", "Contas",
                       "O cadastro das empresas: CNPJ, dados da Receita, contatos e histórico."),
                _passo("/monitor", "mon-quadros", "Monitor",
                       "O painel da sala: dez quadros com a meta de hoje e o resultado do mês. "
                       "LEAD, AGEN e % NOSHOW contam muito do seu trabalho."),
                PASSO_CARREIRA,
                PASSO_PERFIL,
            ],
            "quiz": [
                {
                    "enunciado": "O que acontece quando você conclui a última tarefa aberta de uma oportunidade ativa?",
                    "alternativas": [
                        ("Nada, a oportunidade fica sem tarefa", False),
                        ("O HIPO exige que você marque a próxima tarefa", True),
                        ("A oportunidade é finalizada automaticamente", False),
                        ("A tarefa vai para o EV", False),
                    ],
                },
                {
                    "enunciado": "Qual tela só SDR e gestão enxergam?",
                    "alternativas": [
                        ("Prospecção", True),
                        ("Agenda", False),
                        ("Tarefas", False),
                        ("Contas", False),
                    ],
                },
                {
                    "enunciado": "Em que fase nasce a empresa que você puxa para o HIPO?",
                    "alternativas": [
                        ("Lead", False),
                        ("Qualificação", False),
                        ("Suspect", True),
                        ("Apresentação", False),
                    ],
                },
                {
                    "enunciado": "Você ligou para uma empresa e combinou um retorno, mas não lançou nada no HIPO. Segundo a aula, o que vale para esse contato?",
                    "alternativas": [
                        ("Conta no seu número assim que a planilha da equipe for atualizada", False),
                        ("Entra no seu número no fim do dia, de forma automática", False),
                        ("Para o HIPO não aconteceu: não conta no seu número nem aparece para o EV", True),
                        ("Aparece no Monitor como pendência para a gestão lançar por você", False),
                    ],
                },
                {
                    "enunciado": "Pela ordem do dia do SDR proposta na aula, por qual tela você começa?",
                    "alternativas": [
                        ("Tarefas: atrasadas primeiro, depois as de hoje", True),
                        ("Prospecção: puxar empresas novas para o funil", False),
                        ("Monitor: conferir LEAD, AGEN e no-show", False),
                        ("Agenda: rever as reuniões marcadas para o EV", False),
                    ],
                },
                {
                    "enunciado": "Uma reunião de cliente aconteceu ontem e ninguém registrou se foi realizada, cancelada ou no-show. Onde isso aparece?",
                    "alternativas": [
                        ("Na fila de Prospecção, como empresa a contatar", False),
                        ("Em nenhum lugar: a reunião some da semana", False),
                        ("Na aba Histórico da conta, como alerta", False),
                        ("Como pendência na Agenda", True),
                    ],
                },
                {
                    "enunciado": "Você é usuário novo e entrou com a senha 123456. Onde troca a senha?",
                    "alternativas": [
                        ("Na Carreira, aba PDI", False),
                        ("No Perfil, clicando no seu nome", True),
                        ("Na tela Contas, no seu cadastro", False),
                        ("No Monitor, no canto da tela", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0212"),
            "titulo": "Prospecção: fatiar a base e puxar para o HIPO",
            "resumo": "Como montar o recorte, ler o resumo da fatia e puxar até 50 empresas com a tarefa de primeiro contato já marcada.",
            "duracao_min": 10,
            "conteudo_md": """\
## O que é a base da Receita

A gestão carrega uma vez por mês a base pública de CNPJs da Receita Federal (as UFs aparecem no subtítulo da tela). Você não digita empresa nenhuma: escolhe um recorte e puxa.

## Montar o recorte

No card **Recorte**:

- **UF**: obrigatória. Se a base tem uma UF só, ela já vem marcada.
- **CNAE**: obrigatório, pelo menos um. Digite um código ou parte da atividade. Código curto pega a família inteira: **41** traz toda a divisão de construção. Até 30 CNAEs.
- **Cidade**: opcional. Sem cidade, vale a UF inteira.
- **Porte** (ME, EPP, Demais) e **Regime** (Simples ou fora dele).
- **Aberta há (anos)**, **Capital mínimo (R$)** e **Buscar na fatia** (nome ou CNPJ).
- Marcadores: **Incluir CNAE secundário**, **Com telefone**, **Com e-mail**, **Só matriz**.

Dica: **Com telefone** economiza seu tempo. Empresa sem telefone na base vira pesquisa antes da ligação.

## Ler o resumo da fatia

Com UF e CNAE escolhidos, aparecem os números:

- **Na fatia**: quantas empresas o recorte achou.
- **Puxáveis**: as que ainda não estão em negociação. É o que a lista mostra por padrão.
- **Em negociação**: clique para ver a fatia inteira, com a situação de cada empresa.
- **Clientes** e **Não prospectar**: ficam de fora.
- **Seus suspects abertos**: quantos Suspects estão com você. Fica amarelo a partir de 100: antes de puxar mais, trabalhe os que tem.

## Puxar

1. Marque as empresas na lista (a seleção sobrevive à troca de página).
2. Na barra de baixo, escolha **Primeiro contato em**. Hoje = agora; outro dia = 9h.
3. Clique em **Puxar para o HIPO**. São **até 50 por vez**.

Para cada empresa o HIPO cria (ou reaproveita) a **conta**, abre uma **oportunidade em Suspect** com você como **SDR** envolvido e origem **Base da Receita**, e marca a **tarefa de primeiro contato** para você. Sócios e CNAEs secundários chegam da Receita alguns instantes depois.

Empresa que já é cliente, já tem oportunidade aberta ou está marcada como não prospectar fica de fora, com o motivo na tela.

> Puxe o que você consegue ligar. 50 empresas puxadas e não trabalhadas viram 50 tarefas atrasadas amanhã.
""",
            "tour": [
                _passo("/crm/prospeccao", "pro-recorte", "UF, CNAE e cidade",
                       "Comece por aqui: **UF** e pelo menos um **CNAE** são obrigatórios. "
                       "Digite 41 para pegar toda a construção, ou parte do nome da atividade. Cidade é opcional."),
                _passo("/crm/prospeccao", "pro-porte", "Porte",
                       "ME, EPP ou Demais. Combine com o regime (Simples ou não) para chegar no perfil de cliente que a Controller atende."),
                _passo("/crm/prospeccao", "pro-opcoes", "Os marcadores",
                       "**Com telefone** e **Com e-mail** deixam na lista só quem dá para contatar. "
                       "**Só matriz** tira as filiais; **CNAE secundário** amplia a busca."),
                _passo("/crm/prospeccao", "pro-resumo", "O resumo da fatia",
                       "Com UF e CNAE escolhidos aparecem: Na fatia, **Puxáveis**, Em negociação, Clientes, "
                       "Não prospectar e **Seus suspects abertos**, que fica amarelo a partir de 100."),
                _passo("/crm/prospeccao", None, "Marcar e puxar",
                       "Marque as empresas na lista e use a barra que aparece no rodapé: escolha "
                       "**Primeiro contato em** e clique em **Puxar para o HIPO**. Até 50 por vez. "
                       "Cada uma vira conta + oportunidade em Suspect + tarefa de primeiro contato para você."),
                _passo("/crm/tarefas", "tar-area", "Onde as empresas puxadas aparecem",
                       "As tarefas de primeiro contato caem aqui, em **Para hoje** ou **Futuras**, conforme a data escolhida."),
            ],
            "quiz": [
                {
                    "enunciado": "Quais filtros são obrigatórios para a Prospecção mostrar a fatia?",
                    "alternativas": [
                        ("Cidade e porte", False),
                        ("UF e pelo menos um CNAE", True),
                        ("Capital mínimo e regime", False),
                        ("Nenhum", False),
                    ],
                },
                {
                    "enunciado": "Quantas empresas dá para puxar de uma vez?",
                    "alternativas": [
                        ("10", False),
                        ("Até 50", True),
                        ("Até 500", False),
                        ("Sem limite", False),
                    ],
                },
                {
                    "enunciado": "O que o HIPO cria para cada empresa puxada?",
                    "alternativas": [
                        ("Só a conta", False),
                        ("Conta, oportunidade em Suspect com você como SDR e tarefa de primeiro contato", True),
                        ("Uma reunião na agenda do EV", False),
                        ("Uma proposta em rascunho", False),
                    ],
                },
                {
                    "enunciado": "Você quer toda a divisão de construção sem escolher código por código. O que digitar no campo CNAE?",
                    "alternativas": [
                        ("Construção, no campo Buscar na fatia", False),
                        ("Todos os códigos de 4100 a 4399, um a um", False),
                        ("41: código curto pega a família inteira", True),
                        ("Nada: deixar o CNAE vazio e escolher a cidade", False),
                    ],
                },
                {
                    "enunciado": "O contador Seus suspects abertos ficou amarelo. O que a aula recomenda?",
                    "alternativas": [
                        ("Trabalhar os Suspects que você já tem antes de puxar mais", True),
                        ("Puxar mais 50 para manter a fila sempre cheia", False),
                        ("Pedir à gestão para liberar um limite maior", False),
                        ("Marcar os Suspects antigos como Não prospectar", False),
                    ],
                },
                {
                    "enunciado": "Na barra de baixo, em Primeiro contato em, você escolhe um dia diferente de hoje. Para que horário a tarefa é marcada?",
                    "alternativas": [
                        ("8h do dia escolhido", False),
                        ("13h do dia escolhido", False),
                        ("O mesmo horário em que você puxou", False),
                        ("9h do dia escolhido", True),
                    ],
                },
                {
                    "enunciado": "Você marca na lista uma empresa que já tem oportunidade aberta e clica em Puxar para o HIPO. O que acontece com ela?",
                    "alternativas": [
                        ("Ganha uma segunda oportunidade em Suspect", False),
                        ("Fica de fora, com o motivo mostrado na tela", True),
                        ("Passa para você como SDR da oportunidade aberta", False),
                        ("É marcada como Não prospectar automaticamente", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0213"),
            "titulo": "Tarefas: a sua fila de contato",
            "resumo": "Como ler as quatro colunas, abrir uma tarefa, concluir com a próxima já marcada e acompanhar a sua produção do mês.",
            "duracao_min": 8,
            "conteudo_md": """\
## A tela abre no que é seu

Tarefas abre filtrada em **você**. Para ver a equipe, troque o seletor **Responsável** para "Todos os responsáveis". A busca acha por empresa, número da oportunidade ou título da tarefa.

## As quatro colunas

- **Atrasadas**: o prazo passou. É por onde o dia começa.
- **Para hoje**.
- **Futuras**.
- **Concluídas**: as dos últimos 7 dias, só para consulta.

No topo, os contadores de **atrasadas** e **em aberto**, e o **Realizadas em (mês)**: clique para abrir a produção do mês por tipo e por responsável.

## Abrir e agir

Clique no cartão. A janela da tarefa mostra tipo, situação, prazo, responsável e os botões:

- **Concluir**: escreva em "O que aconteceu" o resultado do contato. Se esta é a última tarefa aberta da oportunidade, o HIPO pede a **próxima**: título, tipo, prazo e responsável. Padrão: ligação amanhã às 9h, com o mesmo responsável.
- **Editar**: mudar prazo, título ou responsável.
- **Cancelar**: a tarefa não faz mais sentido (com motivo opcional).
- **Colocar na agenda**: para tarefa do tipo reunião ou visita que ainda não está na agenda.

A faixa azul no topo da janela abre a **oportunidade** da tarefa, sem sair da tela.

## Anexos

Print de WhatsApp, e-mail do cliente, PDF: cole com **Ctrl+V** na área de anexos, arraste o arquivo ou use **Anexar**. Imagem ou PDF até 10 MB.

## Tipos de tarefa

Ligação, Reunião, Visita, Proposta, E-mail, WhatsApp e Outro. Reunião e Visita vão para a agenda ao salvar, e o horário precisa estar livre para o responsável, em dia útil.

> Tarefa concluída sem "O que aconteceu" é uma ligação que ninguém mais consegue usar. Duas linhas bastam: com quem falou e o que ficou combinado.
""",
            "tour": [
                _passo("/crm/tarefas", "tar-contadores", "Atrasadas, em aberto e produção",
                       "Os contadores mostram o que está parado. **Realizadas no mês** é o que andou: "
                       "clique nele para ver a produção por tipo e por responsável."),
                _passo("/crm/tarefas", "tar-busca", "Buscar",
                       "Empresa, número da oportunidade ou título da tarefa."),
                _passo("/crm/tarefas", "tar-responsavel", "De quem são as tarefas",
                       "A tela abre em você. Troque para \"Todos os responsáveis\" para ver a equipe."),
                _passo("/crm/tarefas", "tar-area", "As colunas",
                       "**Atrasadas**, **Para hoje**, **Futuras** e **Concluídas** (últimos 7 dias). "
                       "Comece sempre pela esquerda."),
                _passo("/crm/tarefas", "tar-modal-dados", "Dentro da tarefa",
                       "Clicando num cartão abre a tarefa: tipo, situação, prazo e responsável.",
                       clicar=["tar-cartao"]),
                _passo("/crm/tarefas", "tar-acoes", "Concluir, editar, cancelar",
                       "**Concluir** pede \"O que aconteceu\" e, se for a última tarefa aberta da oportunidade, "
                       "a **próxima tarefa**. Sem próximo passo, o caminho é finalizar a oportunidade.",
                       clicar=["tar-cartao"]),
            ],
            "quiz": [
                {
                    "enunciado": "Em quem a tela de Tarefas abre filtrada?",
                    "alternativas": [
                        ("Na equipe inteira", False),
                        ("Em você", True),
                        ("No seu gestor", False),
                        ("No EV da oportunidade", False),
                    ],
                },
                {
                    "enunciado": "O que a coluna Concluídas mostra?",
                    "alternativas": [
                        ("Todas as tarefas concluídas desde sempre", False),
                        ("As concluídas nos últimos 7 dias", True),
                        ("Só as canceladas", False),
                        ("As do mês anterior", False),
                    ],
                },
                {
                    "enunciado": "Você conclui a última tarefa aberta de uma oportunidade ativa. O que o HIPO pede?",
                    "alternativas": [
                        ("Nada", False),
                        ("A próxima tarefa (título, tipo, prazo e responsável)", True),
                        ("A senha do gestor", False),
                        ("Uma proposta", False),
                    ],
                },
                {
                    "enunciado": "Você precisa ver as tarefas da equipe toda, e não só as suas. O que fazer?",
                    "alternativas": [
                        ("Abrir a coluna Concluídas", False),
                        ("Clicar em Realizadas em (mês)", False),
                        ("Trocar o seletor Responsável para \"Todos os responsáveis\"", True),
                        ("Digitar o nome do colega na busca", False),
                    ],
                },
                {
                    "enunciado": "O cliente mandou um print no WhatsApp confirmando o interesse. Como guardar isso na tarefa?",
                    "alternativas": [
                        ("Colar com Ctrl+V na área de anexos da tarefa", True),
                        ("Copiar o texto do print para o título da tarefa", False),
                        ("Mandar o print por e-mail para o EV", False),
                        ("Guardar na aba Histórico da conta", False),
                    ],
                },
                {
                    "enunciado": "Você cria uma tarefa do tipo Visita. O que o HIPO exige ao salvar?",
                    "alternativas": [
                        ("Aprovação da gestão para a visita", False),
                        ("Que a oportunidade já esteja em Apresentação", False),
                        ("O endereço confirmado da empresa na conta", False),
                        ("Horário livre para o responsável, em dia útil, porque ela vai para a agenda", True),
                    ],
                },
                {
                    "enunciado": "Ao concluir a última tarefa aberta de uma oportunidade, que próxima tarefa vem sugerida por padrão?",
                    "alternativas": [
                        ("Reunião em 7 dias, com o EV como responsável", False),
                        ("Ligação amanhã às 9h, com o mesmo responsável", True),
                        ("E-mail hoje às 17h, com o mesmo responsável", False),
                        ("WhatsApp em 2 dias, com o gestor como responsável", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0214"),
            "titulo": "Oportunidades: do Suspect ao Lead",
            "resumo": "Como achar a sua oportunidade no funil, abrir o detalhe, mudar a fase e deixar o registro pronto para o EV.",
            "duracao_min": 9,
            "conteudo_md": """\
## O funil

As fases, em ordem: **Suspect → Lead → Qualificação → Apresentação → Negociação → Finalizado**.

O SDR trabalha a boca: a empresa puxada nasce em **Suspect**, e o quadro **LEAD** do Monitor conta as oportunidades que **passaram de Suspect para Lead** no mês. Mover a fase é registrar o avanço da conversa, não um enfeite.

## A barra de cima

- **Em aberto**, **Previsto no mês** e **Ganhas no mês**. Clicar em Em aberto filtra só as ativas e suspensas.
- **Busca**: número, empresa, contato ou CNPJ.
- **Filtros**: situação, fase, período, temperatura, mensalidade, **Equipe** (pessoa e papel), origem do lead, vertical e indicação de parceiro. Para ver só as suas: Equipe = você, papel = SDR.
- **Kanban | Tabela | Funil**: três jeitos de ver o mesmo funil. A escolha fica salva para você.
- **+ Nova oportunidade**.

## Mover de fase

Três jeitos, mesmo resultado:

- arrastar o cartão para outra coluna;
- o seletor de fase no rodapé do cartão;
- o campo **Fase** dentro da oportunidade.

A fase muda na hora (não precisa Salvar) e fica registrada no **Histórico**.

## Dentro da oportunidade

Clique no nome da empresa no cartão. À esquerda ficam a empresa (abre a conta), **Fase**, **Temp.** e as abas:

- **Dados**: origem, previsão de fechamento, Finder (parceiro que indicou), descrição e observações. O contato principal aparece aqui; clicar nele abre a aba Contatos.
- **Tarefas**: as tarefas desta oportunidade, com **Nova tarefa**. Ligação, reunião, visita, WhatsApp e e-mail pedem **o contato**: com quem vai ser a conversa.
- **Contatos** (047): as pessoas da empresa nesta negociação, cada uma com o **papel** (decisor, campeão, operacional...), o **principal** e o **sinal de temperatura** (**Quente**, **Morno**, **Frio**). O farol no topo mostra se a oportunidade tem de 2 a 4 pessoas envolvidas e se o decisor já foi mapeado.
- **Envolvidos**: quem é o SDR, o EV e o EC desta oportunidade.
- **Histórico**: tudo o que aconteceu, com data e autor.

Dados, temperatura e mensalidade só gravam com **Salvar** (lá em cima, ao lado de "Alterações não salvas").

## O que o EV precisa encontrar

O que você descobriu na qualificação (fornecedor atual, número de unidades, quem decide) vai em **Descrição** ou **Observações**. O que não está escrito, o EV vai perguntar de novo na reunião, e o cliente percebe.
""",
            "tour": [
                _passo("/crm/oportunidades", "opo-kpis", "Os números do funil",
                       "**Em aberto** (clique para filtrar), **Previsto no mês** e **Ganhas no mês**."),
                _passo("/crm/oportunidades", "opo-busca", "Buscar",
                       "Número, empresa, contato ou CNPJ. Também procura pelo nome fantasia."),
                _passo("/crm/oportunidades", "opo-filtros", "Filtros",
                       "Para ver só as suas: abra os Filtros e, em **Equipe**, escolha você com o papel **SDR**."),
                _passo("/crm/oportunidades", "opo-visoes", "Kanban, Tabela, Funil",
                       "Três jeitos de ver o mesmo funil. A escolha fica salva para você."),
                _passo("/crm/oportunidades", "opo-area-visao", "As fases",
                       "Suspect, Lead, Qualificação, Apresentação, Negociação e Finalizado. "
                       "No kanban, cada coluna mostra a quantidade e a soma em R$."),
                _passo("/crm/oportunidades", "opo-cartao-acoes", "Mover pelo cartão",
                       "Arraste o cartão ou use este seletor de fase. **Fechar** abre o desfecho (ganho, perda ou cancelamento)."),
                _passo("/crm/oportunidades", "opo-det-trilho", "Dentro da oportunidade",
                       "Clicando no nome da empresa abre o detalhe. Aqui à esquerda: a empresa, a **Fase** "
                       "(muda na hora), a **Temp.** e as abas.",
                       clicar=["opo-cartao-abrir"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Contatos e temperatura",
                       "As pessoas da empresa nesta negociação, com papel e principal. O sinal ao lado do nome diz se a "
                       "conversa está **Quente**, **Morna** ou **Fria**; clique nele para ver o porquê. Ideal: 2 a 4 pessoas.",
                       clicar=["opo-cartao-abrir", "aba-contatos"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Envolvidos",
                       "Quem é o SDR, o EV e o EC desta oportunidade. Empresa puxada pela Prospecção já vem com você como SDR.",
                       clicar=["opo-cartao-abrir", "aba-envolvidos"]),
                _passo("/crm/oportunidades", "opo-det-acoes", "Salvar e agir",
                       "Dados, temperatura e mensalidade só gravam com **Salvar**. Daqui também saem "
                       "**Agendar reunião** e **Finalizar**.",
                       clicar=["opo-cartao-abrir"]),
            ],
            "quiz": [
                {
                    "enunciado": "Qual a ordem correta das fases do funil?",
                    "alternativas": [
                        ("Lead → Suspect → Apresentação → Qualificação → Negociação", False),
                        ("Suspect → Lead → Qualificação → Apresentação → Negociação → Finalizado", True),
                        ("Qualificação → Lead → Suspect → Negociação", False),
                        ("Suspect → Apresentação → Lead → Finalizado", False),
                    ],
                },
                {
                    "enunciado": "Você muda a Fase dentro da oportunidade. Precisa clicar em Salvar?",
                    "alternativas": [
                        ("Sim, senão a fase volta", False),
                        ("Não: a fase muda na hora e vai para o Histórico", True),
                        ("Só se a temperatura mudar junto", False),
                        ("Só o gestor pode mudar a fase", False),
                    ],
                },
                {
                    "enunciado": "Como ver no funil só as oportunidades em que você é o SDR?",
                    "alternativas": [
                        ("Não dá, o funil mostra tudo", False),
                        ("Filtros → Equipe: você, papel SDR", True),
                        ("Trocar para a visão Funil", False),
                        ("Pedir um relatório ao gestor", False),
                    ],
                },
                {
                    "enunciado": "Na qualificação você descobriu o fornecedor atual, o número de unidades e quem decide. Onde registrar para o EV encontrar?",
                    "alternativas": [
                        ("No título da próxima tarefa", False),
                        ("Na aba Envolvidos da oportunidade", False),
                        ("Em Descrição ou Observações, na aba Dados", True),
                        ("Num comentário no Histórico da conta", False),
                    ],
                },
                {
                    "enunciado": "Você mudou a temperatura e a mensalidade e fechou a janela da oportunidade sem clicar em mais nada. O que aconteceu com essas mudanças?",
                    "alternativas": [
                        ("Gravaram na hora, como acontece com a Fase", False),
                        ("Não foram gravadas: esses campos só gravam com Salvar", True),
                        ("Ficaram aguardando a aprovação do EV", False),
                        ("Gravaram, mas só aparecem no dia seguinte", False),
                    ],
                },
                {
                    "enunciado": "Dentro da oportunidade, o que a aba Envolvidos mostra?",
                    "alternativas": [
                        ("Quem é o SDR, o EV e o EC da oportunidade", True),
                        ("Os contatos do cliente e quem decide", False),
                        ("Os concorrentes que o cliente está avaliando", False),
                        ("Os sócios da empresa vindos da Receita", False),
                    ],
                },
                {
                    "enunciado": "Na barra de cima de Oportunidades, o que acontece ao clicar em Em aberto?",
                    "alternativas": [
                        ("Abre o formulário de nova oportunidade", False),
                        ("Troca a visão para Tabela", False),
                        ("Mostra só as oportunidades ganhas no mês", False),
                        ("Filtra só as oportunidades ativas e suspensas", True),
                    ],
                },
            ],
        },
        {
            "id": _id("b0215"),
            "titulo": "Agenda: marcar a reunião para o EV",
            "resumo": "Como achar um horário livre, marcar a reunião em nome do EV com o crédito do agendamento para você, e o que acontece depois.",
            "duracao_min": 9,
            "conteudo_md": """\
## A grade

A Agenda mostra a semana em dias úteis, de **8h às 11h30** e de **13h às 17h30**, de 30 em 30 minutos. Não existe botão "Nova reunião": **você clica no horário livre**, e o formulário abre já com o dia e a hora.

## Escolher de quem é a agenda

- **Agenda de**: a agenda de uma pessoa (abre na sua) ou **Toda a equipe**. Para marcar para um EV, escolha o EV: você vê só os horários dele.
- **Agendado por**: filtra as reuniões que uma pessoa marcou.
- **Parceiros | Oportunidades**: o assunto das reuniões. Clicar de novo no ativo mostra tudo.
- Os números do topo: **Marcadas**, **Slots livres**, **Sem desfecho** e reuniões **sem convite**.

## Marcar a reunião

No formulário **Marcar reunião**:

1. **Cliente (oportunidade)**: busque pela empresa, número ou CNPJ.
2. **Data e hora** e **Duração** (padrão 30 min).
3. **Anfitrião**: **de quem é a reunião**, o EV que vai conduzir.
4. **Agendado por**: **de quem é o crédito**. Vem preenchido com você. É desta linha que sai o seu número de agendamentos.
5. **Modalidade**: online ou presencial. Online sem link: o Google cria o Meet.
6. **Convite**: contato do cliente, a nossa equipe e convidados externos. O Google manda o convite para todo mundo desta seção, mais o anfitrião.
7. **Marcar e enviar convite**.

O horário precisa estar livre para o anfitrião. Reunião é uma tarefa do anfitrião: aparece nas Tarefas dele e na oportunidade.

## Depois de marcada

- O EV conduz e registra o desfecho: **Realizada**, **Cancelada** (desmarcada com 24h ou mais) ou **No-show** (em cima da hora, ou o cliente não apareceu).
- No Monitor, **AGEN** conta as reuniões de cliente do mês pela data da reunião; **AGEND MES** conta pela data em que você marcou; **% NOSHOW** quanto menor, melhor.
- O botão de **Produtividade da agenda** mostra os **Agendamentos por SDR** da semana.

> Reunião bem marcada tem contato confirmado, horário no convite e o motivo da conversa escrito no detalhe. No-show começa no agendamento mal feito.
""",
            "tour": [
                _passo("/crm/agenda", "age-navegacao", "A semana",
                       "Semana anterior, próxima e **Hoje**. A faixa mostra os dias da semana na tela."),
                _passo("/crm/agenda", "age-agenda-de", "De quem é a agenda",
                       "Abre na sua. Para marcar para um EV, escolha o EV aqui e veja só os horários dele. "
                       "\"Toda a equipe\" mostra todo mundo junto."),
                _passo("/crm/agenda", "age-assunto", "Oportunidades ou parceiros",
                       "O assunto das reuniões. Clicar de novo no ativo desliga o filtro."),
                _passo("/crm/agenda", "age-kpis", "Os números da semana",
                       "**Marcadas**, **Slots livres** (com uma agenda escolhida), **Sem desfecho** e as que estão **sem convite**."),
                _passo("/crm/agenda", "age-grade", "A grade",
                       "8h às 11h30 e 13h às 17h30, de 30 em 30 minutos. **Clique num horário livre** para marcar."),
                _passo("/crm/agenda", "reuniao-com-quem", "Cliente ou parceiro",
                       "Clicando num horário livre abre o formulário. Reunião de cliente = **Cliente (oportunidade)**. "
                       "Nada é gravado até você clicar em Marcar e enviar convite.",
                       clicar=["age-celula-livre"]),
                _passo("/crm/agenda", "reuniao-anfitriao", "Anfitrião",
                       "**De quem é a reunião**: o EV que vai conduzir.",
                       clicar=["age-celula-livre"]),
                _passo("/crm/agenda", "reuniao-agendado-por", "Agendado por",
                       "**De quem é o crédito**: vem com você. É daqui que sai o seu número de agendamentos.",
                       clicar=["age-celula-livre"]),
                _passo("/crm/agenda", "age-produtividade", "Produtividade da agenda",
                       "Agendamentos por SDR e reuniões por EV na semana da tela, com realizadas, canceladas e no-show."),
                _passo("/crm/agenda", "age-agendado-por", "Só as que você marcou",
                       "Filtre por **Agendado por** para conferir as suas reuniões da semana."),
            ],
            "quiz": [
                {
                    "enunciado": "Como se marca uma reunião na Agenda?",
                    "alternativas": [
                        ("Pelo botão Nova reunião", False),
                        ("Clicando num horário livre da grade", True),
                        ("Só de dentro da oportunidade", False),
                        ("Pedindo ao EV", False),
                    ],
                },
                {
                    "enunciado": "Você marca uma reunião para o EV. Quem vai em Anfitrião e quem vai em Agendado por?",
                    "alternativas": [
                        ("Você nos dois", False),
                        ("Anfitrião: o EV. Agendado por: você", True),
                        ("Anfitrião: você. Agendado por: o EV", False),
                        ("O gestor nos dois", False),
                    ],
                },
                {
                    "enunciado": "Qual é a diferença entre Cancelada e No-show?",
                    "alternativas": [
                        ("Não há diferença", False),
                        ("Cancelada: desmarcada com 24h ou mais. No-show: em cima da hora ou o cliente não apareceu", True),
                        ("No-show é quando o EV falta", False),
                        ("Cancelada só vale para reunião presencial", False),
                    ],
                },
                {
                    "enunciado": "Em que horários a grade da Agenda permite marcar reunião?",
                    "alternativas": [
                        ("Das 8h às 18h, direto, de hora em hora", False),
                        ("Das 9h às 12h e das 14h às 18h, de 15 em 15 minutos", False),
                        ("Das 8h às 11h30 e das 13h às 17h30, de 30 em 30 minutos", True),
                        ("Das 7h às 19h, de segunda a sábado", False),
                    ],
                },
                {
                    "enunciado": "Você marca uma reunião online e não informa nenhum link. O que acontece?",
                    "alternativas": [
                        ("O Google cria o Meet", True),
                        ("O HIPO não deixa marcar sem link", False),
                        ("A reunião vira presencial", False),
                        ("O EV precisa criar o link depois", False),
                    ],
                },
                {
                    "enunciado": "Você quer marcar para um EV específico e ver só os horários dele. O que fazer?",
                    "alternativas": [
                        ("Escolher o EV em Agendado por", False),
                        ("Escolher Toda a equipe e procurar o nome dele", False),
                        ("Clicar em Oportunidades, no filtro de assunto", False),
                        ("Escolher o EV em Agenda de", True),
                    ],
                },
                {
                    "enunciado": "Onde você vê os Agendamentos por SDR da semana na Agenda?",
                    "alternativas": [
                        ("No número Slots livres do topo", False),
                        ("No botão Produtividade da agenda", True),
                        ("Na tela Contas, em Sem oportunidade aberta", False),
                        ("No formulário Marcar reunião", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0216"),
            "titulo": "Contas: CNPJ, Receita e não prospectar",
            "resumo": "Como cadastrar uma empresa à mão, buscar os dados na Receita, achar o grau de risco e respeitar o bloqueio de prospecção.",
            "duracao_min": 7,
            "conteudo_md": """\
## Conta é a empresa

Toda oportunidade é de uma **conta**. A empresa puxada pela Prospecção já vira conta sozinha. Quando o contato chega por outro caminho (indicação, site, telefone), você cadastra.

## Nova conta

Botão **Nova conta**:

- **Razão social** e **CNPJ** são obrigatórios. O CNPJ precisa ter dígito verificador válido.
- **Buscar na Receita** só libera com o CNPJ completo e válido (a consulta gasta crédito). Ela preenche só os campos vazios e mostra situação cadastral, cidade, porte e o CNAE.
- CNPJ que já existe: o HIPO avisa e oferece **Abrir a conta existente**. Não cadastre de novo.
- Nº de funcionários vindo da fonte é **estimativa**: confirme com o cliente antes de usar numa proposta.

## A visão 360

Clicando na linha abre a conta: vertical, nº de funcionários, vendedor (o EV das oportunidades ativas), situação e as abas Oportunidades, Contatos, Endereço, Telefones e e-mail, Dados cadastrais, **Dados públicos**, Sócios, Observações e Histórico.

Em **Dados públicos** fica o **grau de risco (NR-4)** da empresa, de 1 a 4, que vem do CNAE. É uma informação de ouro para a conversa: quanto maior o grau, mais obrigações de SST.

## Não prospectar

Conta marcada como **Não prospectar** (por exemplo, já é cliente) recusa oportunidade nova. Só a gestão bloqueia e libera. Se você acha que uma conta está bloqueada por engano, fale com a gestão, não crie outra conta para contornar.

## Os números de cima

**Contas ativas**, **Sem oportunidade aberta** (carteira parada), **Parceiros indicadores**, **Sem vertical** (cadastro incompleto) e **Nao prospectar**. Cada um é clicável e filtra a lista.
""",
            "tour": [
                _passo("/crm/contas", "con-kpis", "Os números das contas",
                       "Clique em qualquer um para filtrar a lista. **Sem oportunidade aberta** é carteira parada."),
                _passo("/crm/contas", "con-filtros", "Buscar e filtrar",
                       "Razão social, fantasia ou CNPJ; vertical e UF."),
                _passo("/crm/contas", "con-cnpj", "Nova conta",
                       "Razão social e **CNPJ** são obrigatórios. Nada é gravado até clicar em Criar conta.",
                       clicar=["con-btn-nova"]),
                _passo("/crm/contas", "con-buscar-receita", "Buscar na Receita",
                       "Libera com o CNPJ válido. Preenche só o que estiver vazio e avisa se o CNPJ já está cadastrado.",
                       clicar=["con-btn-nova"]),
                _passo("/crm/contas", "con-360-topo", "A visão 360",
                       "Clicando numa linha abre a conta: vertical, funcionários, vendedor e situação.",
                       clicar=["con-linha"]),
                _passo("/crm/contas", "con-360-topo", "Dados públicos e grau de risco",
                       "Na aba **Dados públicos** ficam o CNAE, a atividade e o **grau de risco (NR-4)**.",
                       clicar=["con-linha", "aba-dados-publicos"]),
            ],
            "quiz": [
                {
                    "enunciado": "Ao cadastrar uma conta, o HIPO avisa que o CNPJ já existe. O que fazer?",
                    "alternativas": [
                        ("Cadastrar de novo com outro nome", False),
                        ("Abrir a conta existente", True),
                        ("Trocar um dígito do CNPJ", False),
                        ("Desistir da empresa", False),
                    ],
                },
                {
                    "enunciado": "Onde está o grau de risco (NR-4) da empresa?",
                    "alternativas": [
                        ("Na aba Dados públicos da conta", True),
                        ("Na Agenda", False),
                        ("No Monitor", False),
                        ("Não existe no HIPO", False),
                    ],
                },
                {
                    "enunciado": "Quem pode bloquear ou liberar uma conta para prospecção?",
                    "alternativas": [
                        ("Qualquer SDR", False),
                        ("Só a gestão", True),
                        ("O EV da conta", False),
                        ("O próprio cliente", False),
                    ],
                },
                {
                    "enunciado": "No cadastro de nova conta, o botão Buscar na Receita está desabilitado. Qual é o motivo?",
                    "alternativas": [
                        ("Só a gestão pode consultar a Receita", False),
                        ("A razão social ainda está em branco", False),
                        ("O CNPJ ainda não está completo e válido", True),
                        ("A conta precisa ser salva antes", False),
                    ],
                },
                {
                    "enunciado": "Você já tinha digitado alguns campos e clicou em Buscar na Receita. O que acontece com eles?",
                    "alternativas": [
                        ("Ficam como estão: a busca preenche só os campos vazios", True),
                        ("São substituídos pelos dados da Receita", False),
                        ("São apagados e o HIPO pede para digitar de novo", False),
                        ("Vão para a aba Observações como histórico", False),
                    ],
                },
                {
                    "enunciado": "Na aba Dados públicos, uma empresa tem grau de risco 4 e outra grau 1. O que isso diz para a conversa?",
                    "alternativas": [
                        ("A de grau 1 tem mais obrigações de SST", False),
                        ("As duas têm as mesmas obrigações de SST", False),
                        ("O grau só indica o porte da empresa", False),
                        ("A de grau 4 tem mais obrigações de SST", True),
                    ],
                },
                {
                    "enunciado": "Uma empresa chegou por indicação, por telefone, e não está no HIPO. O que fazer?",
                    "alternativas": [
                        ("Criar a oportunidade sem conta e cadastrar depois", False),
                        ("Cadastrar pelo botão Nova conta, com razão social e CNPJ", True),
                        ("Pedir ao EV para cadastrar na reunião", False),
                        ("Esperar a base da Receita do mês seguinte", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0217"),
            "titulo": "Seus números: Monitor e Universidade",
            "resumo": "Como ler os quadros que medem o trabalho do SDR e onde continuar estudando.",
            "duracao_min": 6,
            "conteudo_md": """\
## O Monitor

O painel da sala mostra dez quadros do mês, com a **meta de hoje** e o resultado. A meta de hoje é proporcional aos dias úteis que já passaram: no dia útil 10 de 20, a meta de hoje é metade da do mês. A carinha diz o ritmo: 100% da meta de hoje é feliz; abaixo de 70%, triste.

Os quadros onde o SDR pesa mais:

- **LEAD**: oportunidades que passaram de Suspect para Lead no mês.
- **AGEN**: reuniões de cliente do mês (pela data da reunião), sem as desmarcadas.
- **AGEND MES**: reuniões de cliente pela data em que foram **marcadas**.
- **% NOSHOW**: quanto menor, melhor.

Clique num quadro para ver o que compõe o número. O painel se atualiza sozinho a cada minuto.

## A sua avaliação

A gestão acompanha o squad de SDR por agendamentos e reuniões realizadas (os principais), no-show, leads gerados, tarefas de prospecção e taxa de execução. Tudo sai do que você lança no HIPO. Lançou certo, o número é seu.

## Continuar estudando

Em **Carreira**, a aba **Universidade** abre na sua próxima aula, e a aba **Desempenho** mostra os seus números contra a sua meta (a próxima aula). Depois desta trilha, a **02 · Roteiro do EV** mostra o que fazer em cada contato.
""",
            "tour": [
                _passo("/monitor", "mon-barra", "O mês e o ritmo",
                       "O mês, o **dia útil** em que estamos e quanto do mês já passou. A meta de hoje acompanha esse ritmo."),
                _passo("/monitor", "mon-quadros", "Os quadros",
                       "Cada quadro tem resultado, meta de hoje e a carinha. Os seus: **LEAD**, **AGEN**, "
                       "**AGEND MES** e **% NOSHOW**. Clique num quadro para ver os itens que compõem o número."),
                PASSO_UC,
            ],
            "quiz": [
                {
                    "enunciado": "O que o quadro LEAD conta?",
                    "alternativas": [
                        ("Empresas puxadas da Receita", False),
                        ("Oportunidades que passaram de Suspect para Lead no mês", True),
                        ("Ligações feitas", False),
                        ("Contratos fechados", False),
                    ],
                },
                {
                    "enunciado": "No dia útil 10 de 20, qual é a meta de hoje de um quadro com meta mensal 40?",
                    "alternativas": [
                        ("40", False),
                        ("20", True),
                        ("10", False),
                        ("4", False),
                    ],
                },
                {
                    "enunciado": "Qual a diferença entre AGEN e AGEND MES?",
                    "alternativas": [
                        ("Nenhuma", False),
                        ("AGEN conta pela data da reunião; AGEND MES pela data em que foi marcada", True),
                        ("AGEN é do EV e AGEND MES do EC", False),
                        ("AGEND MES conta só no-show", False),
                    ],
                },
                {
                    "enunciado": "Um quadro do Monitor está em 65% da meta de hoje. Que carinha aparece?",
                    "alternativas": [
                        ("Feliz, porque o mês ainda não acabou", False),
                        ("Nenhuma: a carinha só aparece no fim do mês", False),
                        ("Triste, porque está abaixo de 70%", True),
                        ("Feliz, porque passou da metade da meta", False),
                    ],
                },
                {
                    "enunciado": "Você quer saber quais reuniões formam o número do quadro AGEN. O que fazer?",
                    "alternativas": [
                        ("Clicar no quadro no Monitor", True),
                        ("Pedir um relatório à gestão", False),
                        ("Abrir a aba Desempenho e esperar o fim do mês", False),
                        ("Recarregar a página do Monitor", False),
                    ],
                },
                {
                    "enunciado": "Com que frequência o Monitor atualiza os números?",
                    "alternativas": [
                        ("Só quando alguém aperta F5", False),
                        ("Uma vez por dia, de madrugada", False),
                        ("Quando a gestão publica o fechamento", False),
                        ("Sozinho, a cada minuto", True),
                    ],
                },
                {
                    "enunciado": "Na avaliação do squad de SDR, quais são os indicadores principais?",
                    "alternativas": [
                        ("Leads gerados e contas prospectadas", False),
                        ("Agendamentos e reuniões realizadas", True),
                        ("No-show e taxa de execução", False),
                        ("Tarefas de prospecção e ticket gerado", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0218"),
            "titulo": "Carreira: o seu Desempenho",
            "resumo": "A Carreira e as três abas, e como ler o seu Desempenho de SDR: meta de hoje, ponto de atenção, funil e histórico.",
            "duracao_min": 7,
            "conteudo_md": TEXTO_CARREIRA_ABAS + """\
## A tela, de cima para baixo

1. **Ponto de atenção**: o indicador mais longe da meta, com o percentual, quanto falta para a meta do mês e o botão **Agir em**, que leva à tela certa (Agenda, Tarefas, Oportunidades ou Prospecção).
2. **Os principais do SDR**: **AGENDAMENTOS** (reuniões marcadas por você no mês) e **REUNIÕES REALIZADAS** (as que você agendou e aconteceram).
3. **Indicadores do mês**: todos os da RPeR do SDR. Além dos principais: no-show, leads gerados, tarefas de prospecção, contas prospectadas, taxa de execução, ticket gerado e NMRR gerado.
4. **Funil**: Tarefas de prospecção → Empresas contatadas → Reuniões agendadas → Reuniões realizadas, com a taxa de cada passagem. "Agendamentos por empresa contatada" aparece como razão: 0,3 quer dizer 3 reuniões a cada 10 empresas. É conversão dentro do mês, para enxergar onde o funil afina.
5. **Últimos meses**: seis meses de realizado e atingimento.

## O que fazer com isso

O funil diz o que treinar:

- **Muita tarefa, pouco contato**: cadência. Volte à **01 · Rotina, volume e metas**, do pilar Energia (rotina e mínimo diário).
- **Muito contato, pouco agendamento**: abordagem. Revise o **02 · Roteiro do SDR**.
- **Muito agendamento, pouca reunião realizada**: no-show. Confirme a reunião na véspera e registre o desfecho no mesmo dia.

""" + TEXTO_CARREIRA_GESTAO,
            "tour": _tour_desempenho(
                "Os dois números que mais pesam no SDR: **AGENDAMENTOS** e **REUNIÕES "
                "REALIZADAS**, com a meta e a barra do atingimento.",
                "Tarefas de prospecção → empresas contatadas → reuniões agendadas → "
                "reuniões realizadas. A taxa de cada passagem mostra onde o seu funil afina.",
            ),
            "quiz": [
                {
                    "enunciado": "Dia útil 10 de 20. Sua meta do mês é 40 agendamentos e você tem 14. Qual é o atingimento da meta de hoje?",
                    "alternativas": [
                        ("35%", False),
                        ("70%", True),
                        ("140%", False),
                        ("14%", False),
                    ],
                },
                {
                    "enunciado": "Onde a gestão cadastra a sua meta individual?",
                    "alternativas": [
                        ("No seu Perfil", False),
                        ("Em Monitor › RPeR › Metas por squad e pessoa", True),
                        ("Na Universidade", False),
                        ("Em lugar nenhum: o HIPO calcula sozinho", False),
                    ],
                },
                {
                    "enunciado": "A meta de no-show é 15%. No dia útil 5 de 20, qual é a meta de hoje?",
                    "alternativas": [
                        ("15%: taxa não acumula", True),
                        ("3,75%", False),
                        ("0%", False),
                        ("60%", False),
                    ],
                },
                {
                    "enunciado": "Seu funil mostra muitos agendamentos e poucas reuniões realizadas. Onde está o problema?",
                    "alternativas": [
                        ("Na prospecção: faltam empresas", False),
                        ("No no-show: confirmar a reunião e registrar o desfecho", True),
                        ("Na proposta do EV", False),
                        ("Em nada: agendar é o que conta", False),
                    ],
                },
                {
                    "enunciado": "No funil do seu Desempenho, \"Agendamentos por empresa contatada\" está em 0,3. O que isso quer dizer?",
                    "alternativas": [
                        ("3 reuniões a cada 10 empresas contatadas", True),
                        ("3 empresas contatadas para cada reunião", False),
                        ("0,3% das empresas viraram reunião", False),
                        ("30 reuniões para cada empresa contatada", False),
                    ],
                },
                {
                    "enunciado": "Seu funil mostra muitas tarefas de prospecção e poucas empresas contatadas. O que a aula manda treinar?",
                    "alternativas": [
                        ("Abordagem: revisar o 02 · Roteiro do SDR", False),
                        ("No-show: confirmar a reunião na véspera", False),
                        ("Cadência: voltar à Rotina, volume e metas, do pilar Energia", True),
                        ("Proposta: rever o Roteiro do EV com o EV", False),
                    ],
                },
                {
                    "enunciado": "O que o cartão Ponto de atenção mostra no topo do Desempenho?",
                    "alternativas": [
                        ("O indicador mais perto de bater a meta", False),
                        ("O último indicador que você lançou", False),
                        ("O indicador de maior peso na RPeR", False),
                        ("O indicador mais longe da meta, com o botão Agir em", True),
                    ],
                },
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# HIPO - EV
# ═════════════════════════════════════════════════════════════════════

HIPO_EV = {
    "id": _id("b0300"),
    "titulo": "01 · HIPO - EV",
    "pilar": "metodo",
    "reforca": "desfecho_em_dia",
    "descricao": (
        "Como o Executivo de Vendas usa o HIPO: o funil nas três visões, a "
        "oportunidade por dentro, proposta e fechamento, tarefas com próximo "
        "passo, a agenda das suas reuniões com desfecho, transcrição e "
        "scorecard, e os números do mês. Cada aula tem o botão \"Me mostra no "
        "HIPO\", que abre a tela real e aponta o que foi explicado."
    ),
    "prazo_dias": 15,
    "obrigatorios": ("EV",),
    "opcionais": GESTAO_OPCIONAL,
    "aulas": [
        {
            "id": _id("b0311"),
            "titulo": "O HIPO no dia do EV",
            "resumo": "As telas do EV, a ordem do dia e as regras que o sistema cobra: próximo passo sempre, desfecho sempre.",
            "duracao_min": 7,
            "conteudo_md": """\
## O HIPO é a fonte da verdade

A negociação inteira vive no HIPO: fase, temperatura, proposta, cada contato e cada reunião. O que não está lançado não aparece no Monitor, não entra no seu número e some quando você sair de férias.

## As telas do EV

- **Oportunidades**: o funil. É a sua tela principal.
- **Tarefas**: o que está em aberto, começando pelo que é seu.
- **Agenda**: as suas reuniões da semana. Muitas foram marcadas para você pelo SDR.
- **Contas**: o cadastro das empresas, com dados da Receita e grau de risco.
- **Relatórios** e **Monitor**.
- **Carreira**: a Universidade, o seu PDI e o seu Desempenho contra a meta.

## O seu dia, na ordem

1. **Agenda**: as reuniões de hoje, e o desfecho das de ontem.
2. **Tarefas**: atrasadas primeiro. Follow-up é tarefa.
3. **Oportunidades**: fase, temperatura e previsão em dia; propostas da semana.
4. **Monitor**: NMRR, contratos e scorecard.

## As regras que o sistema cobra

- **Toda tarefa concluída pede a próxima.** A última tarefa aberta de uma oportunidade viva só fecha com o próximo passo marcado. Sem próximo passo, finalize a oportunidade.
- **Toda reunião tem desfecho**: realizada, cancelada ou no-show. Reunião realizada também pede a próxima tarefa.
- **Todo fechamento tem registro**: ao finalizar, você escreve o que aconteceu. Perda e cancelamento pedem o motivo.

> Use **Me mostra no HIPO** abaixo para ver cada tela. O tour só mostra; nada é criado nem alterado.
""",
            "tour": [
                PASSO_BARRA,
                _passo("/crm/oportunidades", "nav-oportunidades", "Oportunidades",
                       "O funil de vendas. É a sua tela principal: onde a negociação anda de fase."),
                _passo("/crm/tarefas", "nav-tarefas", "Tarefas",
                       "O que está em aberto, começando pelo que é seu. Follow-up é tarefa."),
                _passo("/crm/agenda", "nav-agenda", "Agenda",
                       "As suas reuniões da semana. O SDR marca com você como **anfitrião**."),
                _passo("/crm/contas", "nav-contas", "Contas",
                       "As empresas: dados da Receita, grau de risco, contatos e as outras oportunidades da mesma empresa."),
                _passo("/crm/relatorios", "nav-relatorios", "Relatórios",
                       "Tabelas dinâmicas sobre a base do HIPO. Todo número abre os registros que o compõem."),
                _passo("/monitor", "mon-quadros", "Monitor",
                       "O painel da sala: **NMRR**, **CONTRATOS**, **TICK MED**, **APRE** e **SCORECARD** falam do seu trabalho."),
                PASSO_CARREIRA,
                PASSO_PERFIL,
            ],
            "quiz": [
                {
                    "enunciado": "Você registra uma reunião como Realizada e ela era a última tarefa aberta da oportunidade. O que o HIPO pede?",
                    "alternativas": [
                        ("Nada", False),
                        ("A próxima tarefa", True),
                        ("A proposta assinada", False),
                        ("A aprovação do gestor", False),
                    ],
                },
                {
                    "enunciado": "Qual é a tela principal do EV?",
                    "alternativas": [
                        ("Prospecção", False),
                        ("Oportunidades", True),
                        ("Parceiros", False),
                        ("Perfil", False),
                    ],
                },
                {
                    "enunciado": "Ao finalizar uma oportunidade como perdida, o que é obrigatório?",
                    "alternativas": [
                        ("Nada", False),
                        ("O motivo e o registro do que aconteceu", True),
                        ("Uma nova proposta", False),
                        ("Apagar a oportunidade", False),
                    ],
                },
                {
                    "enunciado": "Pela ordem do dia do EV proposta na aula, por onde você começa?",
                    "alternativas": [
                        ("Tarefas: atrasadas primeiro", False),
                        ("Agenda: as reuniões de hoje e o desfecho das de ontem", True),
                        ("Oportunidades: fase e temperatura em dia", False),
                        ("Monitor: NMRR, contratos e scorecard", False),
                    ],
                },
                {
                    "enunciado": "O SDR marcou uma reunião de cliente para você conduzir. Como você aparece nela?",
                    "alternativas": [
                        ("Como Agendado por", False),
                        ("Como convidado externo", False),
                        ("Como anfitrião", True),
                        ("Como EC nos Envolvidos", False),
                    ],
                },
                {
                    "enunciado": "Quais quadros do Monitor falam do trabalho do EV?",
                    "alternativas": [
                        ("NMRR, CONTRATOS, TICK MED, APRE e SCORECARD", True),
                        ("LEAD, AGEN, AGEND MES e % NOSHOW", False),
                        ("PARCERIAS, LEAD e AGEN", False),
                        ("AGEND MES, PARCERIAS e % NOSHOW", False),
                    ],
                },
                {
                    "enunciado": "Uma negociação está anotada só no seu caderno, não no HIPO. Segundo a aula, o que acontece com ela?",
                    "alternativas": [
                        ("A gestão lança por você no fim do mês", False),
                        ("Entra no seu número quando a oportunidade fechar", False),
                        ("Aparece no Monitor como previsão", False),
                        ("Não entra no seu número e some quando você sair de férias", True),
                    ],
                },
            ],
        },
        {
            "id": _id("b0312"),
            "titulo": "O funil: Kanban, Tabela e Funil",
            "resumo": "Os números do topo, os filtros que importam para o EV, as três visões e como mover uma oportunidade.",
            "duracao_min": 9,
            "conteudo_md": """\
## Os números do topo

- **Em aberto**: quantidade e valor das oportunidades ativas e suspensas. Clique para filtrar só elas.
- **Previsto no mês**: soma da mensalidade das ativas com **previsão de fechamento neste mês**. Previsão errada estraga este número; mantenha em dia.
- **Ganhas no mês**: quantas, e quantas perdidas.

## Filtros

O botão **Filtros** abre o painel. Nada muda até você clicar em **Aplicar filtros**:

- **Situação**: Ativa, Suspensa, Conquistada, Perdida, Cancelada.
- **Fase** e **Período** (criação, previsão de fechamento, desfecho ou última atualização; atalhos Este mês, Mês passado, Últimos 30 dias).
- **Temperatura** e **Mensalidade**.
- **Equipe**: pessoa e papel. **Você + EV** = a sua carteira.
- **Origem do lead**, **Vertical** e **Indicação de parceiro**.

O **X** ao lado limpa tudo, inclusive a busca.

## As três visões

- **Kanban**: uma coluna por fase, com quantidade e soma. Arraste para mover. A coluna **Finalizado** é só leitura e mostra o que fechou no mês. Coluna grande carrega de 100 em 100 (**Carregar mais**).
- **Tabela**: número, empresa, fase, status, mensalidade, temperatura, previsão e envolvidos, 50 por página.
- **Funil**: uma faixa por fase, com o % de passagem entre elas. Clique numa faixa para ver as oportunidades dela.

## Temperatura

De 0 a 90, de 10 em 10. No cartão: vermelho a partir de 70, amarelo a partir de 40, azul abaixo disso. Temperatura é a sua leitura da chance de fechar; ajuste a cada contato.

## Mover e fechar pelo cartão

Arraste para outra coluna ou use o seletor de fase do cartão. Soltar em **Finalizado** não move: abre o desfecho. O botão **Fechar** do cartão faz o mesmo.
""",
            "tour": [
                _passo("/crm/oportunidades", "opo-kpis", "Em aberto, previsto, ganhas",
                       "**Previsto no mês** soma as ativas com previsão de fechamento neste mês: mantenha a previsão em dia."),
                _passo("/crm/oportunidades", "opo-filtros", "Filtros",
                       "Situação, fase, período, temperatura, mensalidade, **Equipe**, origem, vertical e indicação de parceiro."),
                _passo("/crm/oportunidades", "opo-filtros", "O painel de filtros",
                       "Para a sua carteira: **Equipe** = você, papel **EV**. Nada muda até **Aplicar filtros**.",
                       clicar=["opo-filtros-botao"]),
                _passo("/crm/oportunidades", "opo-visoes", "Três visões",
                       "**Kanban** para trabalhar, **Tabela** para conferir em lista, **Funil** para ver a passagem entre fases."),
                _passo("/crm/oportunidades", "opo-area-visao", "As colunas",
                       "Cada fase com quantidade e soma em R$. **Finalizado** é só leitura e mostra o que fechou no mês."),
                _passo("/crm/oportunidades", "opo-cartao", "O cartão",
                       "Empresa, número, valor, **temperatura** (vermelho a partir de 70), previsão e o EV."),
                _passo("/crm/oportunidades", "opo-cartao-acoes", "Mover e fechar",
                       "Seletor de fase e **Fechar**, que abre o desfecho. Também dá para arrastar o cartão."),
            ],
            "quiz": [
                {
                    "enunciado": "O que soma o número Previsto no mês?",
                    "alternativas": [
                        ("Tudo o que está em aberto", False),
                        ("A mensalidade das ativas com previsão de fechamento neste mês", True),
                        ("O que foi ganho no mês", False),
                        ("As propostas geradas", False),
                    ],
                },
                {
                    "enunciado": "O que acontece ao soltar um cartão na coluna Finalizado?",
                    "alternativas": [
                        ("A oportunidade é ganha", False),
                        ("Abre o desfecho para escolher conquistado, perdido ou cancelado", True),
                        ("O cartão some", False),
                        ("Nada", False),
                    ],
                },
                {
                    "enunciado": "Como ver só a sua carteira de EV no funil?",
                    "alternativas": [
                        ("Filtros → Equipe: você, papel EV → Aplicar filtros", True),
                        ("Clicar em Ganhas no mês", False),
                        ("Trocar para Tabela", False),
                        ("Não é possível", False),
                    ],
                },
                {
                    "enunciado": "Uma oportunidade está com temperatura 50. Que cor ela mostra no cartão?",
                    "alternativas": [
                        ("Vermelho", False),
                        ("Azul", False),
                        ("Amarelo", True),
                        ("Verde", False),
                    ],
                },
                {
                    "enunciado": "Você ajustou vários campos no painel de Filtros e a lista não mudou. O que falta?",
                    "alternativas": [
                        ("Clicar em Aplicar filtros", True),
                        ("Clicar em Salvar na oportunidade", False),
                        ("Trocar para a visão Tabela", False),
                        ("Clicar no X ao lado dos Filtros", False),
                    ],
                },
                {
                    "enunciado": "Você quer ver o percentual de passagem entre as fases. Qual visão usar?",
                    "alternativas": [
                        ("Kanban", False),
                        ("Tabela", False),
                        ("Previsto no mês", False),
                        ("Funil", True),
                    ],
                },
                {
                    "enunciado": "A coluna Negociação do kanban é grande e não mostra todas as oportunidades. O que fazer?",
                    "alternativas": [
                        ("Trocar para a visão Funil", False),
                        ("Clicar em Carregar mais, que traz de 100 em 100", True),
                        ("Arrastar os cartões para Finalizado", False),
                        ("Limpar os filtros com o X", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0313"),
            "titulo": "A oportunidade por dentro",
            "resumo": "O trilho da esquerda, as abas, o que grava na hora e o que espera o Salvar, e as ações do topo.",
            "duracao_min": 9,
            "conteudo_md": """\
## Abrir

No kanban, clique no nome da empresa no cartão; na tabela, na linha. A oportunidade abre por cima da tela, sem perder o filtro.

## O trilho da esquerda

- **A empresa**: abre a conta por cima, editável (contatos, endereço, dados públicos, outras oportunidades). Fechar a conta volta para a oportunidade como estava.
- **Fase**: muda **na hora** e vai para o Histórico.
- **Temp.**: precisa de **Salvar**. Só com a oportunidade ativa.
- As abas.

## As abas

- **Dados**: origem, previsão de fechamento, **Finder** (parceiro que indicou), descrição e observações. O contato principal aparece aqui; clicar nele abre a aba Contatos.
- **Tarefas**: atrasadas, em aberto e **Nova tarefa**. Reunião ou visita criada aqui vai direto para a agenda (**Marcar na agenda**). Ligação, reunião, visita, WhatsApp e e-mail pedem **o contato**.
- **Contatos** (047): as pessoas da empresa nesta negociação, cada uma com o **papel** (decisor, campeão, operacional...), o **principal** e o **sinal de temperatura** (**Quente**, **Morno**, **Frio**). O farol no topo mostra se a oportunidade tem de 2 a 4 pessoas envolvidas e se o decisor já foi mapeado.
- **Proposta**: mensalidade e a geração da proposta (próxima aula).
- **Envolvidos**: quem é o SDR, o EV e o EC. Se você assumiu uma oportunidade, confira se está aqui como EV.
- **Concorrentes**: com quem o cliente está comparando.
- **Histórico**: criação, mudanças de fase e de status, reabertura.

## As ações do topo

- **Agendar reunião**: abre o formulário já preso nesta oportunidade.
- **Suspender / Reativar**: oportunidade que parou por um motivo do cliente, mas não morreu.
- **Finalizar**: o desfecho.
- **Salvar**: grava Dados, temperatura e mensalidade. Do lado aparece "Alterações não salvas" ou "Tudo salvo".

> Antes de toda reunião, abra a oportunidade e leia Dados, Tarefas e Histórico. O que o SDR registrou na qualificação está lá.
""",
            "tour": [
                _passo("/crm/oportunidades", "opo-det-trilho", "O trilho",
                       "A empresa (abre a conta por cima), a **Fase** (muda na hora), a **Temp.** (espera o Salvar) e as abas.",
                       clicar=["opo-cartao-abrir"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Dados",
                       "Contato, origem, previsão de fechamento, **Finder** (parceiro que indicou), descrição e observações.",
                       clicar=["opo-cartao-abrir", "aba-dados"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Tarefas da oportunidade",
                       "Atrasadas, em aberto e **Nova tarefa**. Reunião ou visita vai direto para a agenda.",
                       clicar=["opo-cartao-abrir", "aba-tarefas"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Contatos e temperatura",
                       "As pessoas da empresa nesta negociação, com papel e principal. O sinal ao lado do nome diz se a "
                       "conversa está **Quente**, **Morna** ou **Fria**; clique nele para ver o porquê. Ideal: 2 a 4 pessoas.",
                       clicar=["opo-cartao-abrir", "aba-contatos"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Envolvidos",
                       "SDR, EV e EC desta oportunidade. Confira se você está como **EV**.",
                       clicar=["opo-cartao-abrir", "aba-envolvidos"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Histórico",
                       "Tudo o que aconteceu, com data e autor.",
                       clicar=["opo-cartao-abrir", "aba-historico"]),
                _passo("/crm/oportunidades", "opo-det-acoes", "As ações",
                       "**Agendar reunião**, **Suspender**, **Finalizar** e **Salvar**. Repare em \"Tudo salvo\" ou \"Alterações não salvas\".",
                       clicar=["opo-cartao-abrir"]),
            ],
            "quiz": [
                {
                    "enunciado": "O que precisa de Salvar dentro da oportunidade?",
                    "alternativas": [
                        ("A fase", False),
                        ("Dados, temperatura e mensalidade", True),
                        ("Suspender", False),
                        ("Finalizar", False),
                    ],
                },
                {
                    "enunciado": "Onde fica o parceiro que indicou a oportunidade?",
                    "alternativas": [
                        ("No campo Finder da aba Dados", True),
                        ("Na aba Concorrentes", False),
                        ("No Histórico", False),
                        ("Em lugar nenhum", False),
                    ],
                },
                {
                    "enunciado": "Para que serve Suspender?",
                    "alternativas": [
                        ("Apagar a oportunidade", False),
                        ("Oportunidade parada por motivo do cliente, que não morreu", True),
                        ("Marcar como ganha", False),
                        ("Trocar o EV", False),
                    ],
                },
                {
                    "enunciado": "Você abriu a conta pelo trilho da oportunidade e editou um contato. Ao fechar a conta, onde você fica?",
                    "alternativas": [
                        ("Na lista de Contas, com a conta salva", False),
                        ("Na tela de Oportunidades, sem o filtro", False),
                        ("Na oportunidade, como ela estava", True),
                        ("Na aba Histórico da conta", False),
                    ],
                },
                {
                    "enunciado": "O cliente contou que está comparando a Controller com outra empresa. Onde registrar isso?",
                    "alternativas": [
                        ("Na aba Concorrentes", True),
                        ("Na aba Envolvidos", False),
                        ("No campo Finder", False),
                        ("Na aba Histórico", False),
                    ],
                },
                {
                    "enunciado": "Você assumiu uma oportunidade que era de outro EV. O que a aula manda conferir?",
                    "alternativas": [
                        ("Se a temperatura foi zerada", False),
                        ("Se a fase voltou para Lead", False),
                        ("Se o Finder mudou para o seu nome", False),
                        ("Se você está na aba Envolvidos como EV", True),
                    ],
                },
                {
                    "enunciado": "Você tem uma reunião daqui a pouco. O que a aula manda fazer antes?",
                    "alternativas": [
                        ("Gerar uma proposta nova para levar pronta", False),
                        ("Abrir a oportunidade e ler Dados, Tarefas e Histórico", True),
                        ("Mudar a fase para Apresentação", False),
                        ("Suspender a oportunidade até o fim da reunião", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0314"),
            "titulo": "Proposta e fechamento",
            "resumo": "Como gerar a proposta com versões em PPTX e PDF e como finalizar: conquistado, perdido ou cancelado, sempre com o registro do fechamento.",
            "duracao_min": 9,
            "conteudo_md": """\
## Gerar a proposta

Na aba **Proposta** da oportunidade:

- **Modalidade**: **Tabela por faixa** (até 5 vidas R$ 180, 6 a 10 R$ 220, 11 a 15 R$ 260, 16 a 20 R$ 300, acima de 20 R$ 15 por vida) ou **Valor por vida**.
- **CNPJs da proposta**: o CNPJ da oportunidade já vem. Cliente com vários CNPJs é **uma oportunidade só**: use **Adicionar CNPJ do mesmo cliente**. Cada CNPJ tem as suas **vidas**; na tabela, o valor vem sugerido e pode ser negociado (a tela mostra o desconto).
- **Treinamentos (R$)** e **Laudos / outros (R$)**.
- **Data da proposta** e **Válida até** (não pode ser antes da data).
- **Cidade** e o **Escopo**: pelo menos um item (**+ Item**).

**Gerar proposta** cria uma nova versão, baixa o PPTX consolidado e recalcula a mensalidade da oportunidade (soma dos CNPJs). Em **Versões geradas** ficam todas, com **PPTX** e **PDF**; em **Proposta por CNPJ**, cada CNPJ baixa a sua. O seu telefone no slide de fechamento vem do **Perfil**.

O CNPJ adicionado fica **vinculado** à oportunidade: a conta dele mostra o aviso com o número da oportunidade, e o HIPO não deixa abrir outra oportunidade para ele enquanto esta estiver aberta.

Pelo roteiro de vendas, a proposta sai em **até 48h** depois da reunião e é **apresentada**, nunca só enviada.

## Finalizar

Pelo botão **Finalizar** da oportunidade, **Fechar** no cartão ou arrastando para Finalizado. Abre **Finalizar oportunidade**:

- **Conquistado**: o cliente fechou. Entra como ganho na conversão e no NMRR.
- **Perdido**: o cliente recusou. **Motivo obrigatório.** Entra na taxa de conversão.
- **Cancelado**: erro nosso de cadastro (duplicada, empresa errada). **Motivo obrigatório.** Fica fora da conversão. Não use para esconder perda.

Em todos, o **Registro do fechamento** é obrigatório: **O que aconteceu**, tipo, quando e quem fez. Ele vira uma tarefa já concluída na linha do tempo.

## Reabrir

Finalizada por engano? **Reabrir** no topo da oportunidade. Fica registrado no Histórico.

> Perda bem registrada vale tanto quanto ganho: é ela que mostra onde o funil vaza.
""",
            "tour": [
                _passo("/crm/oportunidades", "opo-det-conteudo", "A aba Proposta",
                       "Modalidade (tabela por faixa ou valor por vida), os CNPJs com as vidas de cada um, extras, datas e "
                       "escopo. **Gerar proposta** cria a versão nova (consolidada ou por CNPJ) e recalcula a mensalidade. "
                       "(O tour não gera nada.)",
                       clicar=["opo-cartao-abrir", "aba-proposta"]),
                _passo("/crm/oportunidades", "opo-det-finalizar", "Finalizar",
                       "Abre o desfecho da oportunidade.",
                       clicar=["opo-cartao-abrir"]),
                _passo("/crm/oportunidades", "opo-desfecho-opcoes", "Conquistado, perdido, cancelado",
                       "**Perdido** e **Cancelado** pedem motivo. Cancelado é erro de cadastro e fica fora da conversão. "
                       "Nada é gravado até você clicar em Finalizar lá embaixo.",
                       clicar=["opo-cartao-abrir", "opo-det-finalizar"]),
                _passo("/crm/oportunidades", None, "O registro do fechamento",
                       "Escolhido o desfecho, aparece o **Registro do fechamento**: \"O que aconteceu\" é obrigatório, "
                       "e ele vira uma tarefa concluída na linha do tempo da oportunidade."),
            ],
            "quiz": [
                {
                    "enunciado": "Quando usar o desfecho Cancelado?",
                    "alternativas": [
                        ("Quando o cliente recusou", False),
                        ("Quando foi erro nosso de cadastro, como oportunidade duplicada", True),
                        ("Para não estragar a conversão", False),
                        ("Quando o cliente pediu para esperar", False),
                    ],
                },
                {
                    "enunciado": "O que a geração da proposta exige?",
                    "alternativas": [
                        ("Só o nome do cliente", False),
                        ("Pelo menos um CNPJ com vidas, datas válidas e pelo menos um item de escopo", True),
                        ("Aprovação do gestor", False),
                        ("A oportunidade em Negociação", False),
                    ],
                },
                {
                    "enunciado": "O que é obrigatório em TODO desfecho, inclusive no Conquistado?",
                    "alternativas": [
                        ("O motivo", False),
                        ("O registro do fechamento (o que aconteceu)", True),
                        ("Anexar o contrato", False),
                        ("Uma nova proposta", False),
                    ],
                },
                {
                    "enunciado": "Você finalizou uma oportunidade por engano. O que fazer?",
                    "alternativas": [
                        ("Criar outra oportunidade para a mesma empresa", False),
                        ("Clicar em Reabrir no topo da oportunidade", True),
                        ("Pedir à gestão para apagar o desfecho", False),
                        ("Arrastar o cartão de Finalizado para Negociação", False),
                    ],
                },
                {
                    "enunciado": "Onde você encontra as propostas que já gerou, em PPTX e PDF?",
                    "alternativas": [
                        ("Em Versões geradas, na aba Proposta", True),
                        ("Na aba Histórico da oportunidade", False),
                        ("Nos anexos da conta", False),
                        ("Em Relatórios, fonte Propostas", False),
                    ],
                },
                {
                    "enunciado": "O telefone que aparece no slide de fechamento da proposta está errado. Onde corrigir?",
                    "alternativas": [
                        ("Na aba Proposta, campo Cidade", False),
                        ("Na conta do cliente, aba Telefones", False),
                        ("Na aba Envolvidos da oportunidade", False),
                        ("No seu Perfil", True),
                    ],
                },
                {
                    "enunciado": "Pelo roteiro de vendas citado na aula, quando e como a proposta deve chegar ao cliente?",
                    "alternativas": [
                        ("Em até 7 dias, enviada por e-mail", False),
                        ("No mesmo dia, enviada por WhatsApp", False),
                        ("Em até 48h depois da reunião, apresentada e não só enviada", True),
                        ("Quando o cliente pedir, enviada em PDF", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0315"),
            "titulo": "Tarefas: follow-up com próximo passo",
            "resumo": "Como a tela de Tarefas organiza o seu follow-up e como concluir uma tarefa sem deixar a negociação parar.",
            "duracao_min": 7,
            "conteudo_md": """\
## Follow-up é tarefa

Cada toque da cadência (WhatsApp de confirmação, ligação, e-mail de valor) é uma tarefa com prazo. Cada tarefa concluída pede a próxima, e assim a cadência anda sozinha e a gestão enxerga no funil quem está em follow-up e há quanto tempo.

## A tela

- Abre nas **suas** tarefas. O seletor **Responsável** mostra a equipe.
- Colunas **Atrasadas**, **Para hoje**, **Futuras** e **Concluídas** (7 dias).
- **Realizadas em (mês)** abre a sua produção por tipo.

## Concluir

Abra o cartão, clique em **Concluir** e escreva **O que aconteceu**. Se for a última tarefa aberta da oportunidade, preencha a **Próxima**: título, tipo, prazo e responsável. Próxima do tipo **Reunião** ou **Visita** vai para a agenda; o horário precisa estar livre e em dia útil. Se não couber, a tarefa é criada e o HIPO avisa para usar **Colocar na agenda** nela.

Quando não há próximo passo, o certo não é inventar uma tarefa: é **finalizar a oportunidade**.

## Reunião aberta nas Tarefas

Tarefa de reunião mostra **O que aconteceu?**, que leva ao desfecho (próxima aula), e **Editar reunião**.

> Tarefa atrasada é promessa ao cliente que não foi cumprida. Se o prazo mudou, edite o prazo; não deixe vencer.
""",
            "tour": [
                _passo("/crm/tarefas", "tar-responsavel", "As suas tarefas",
                       "Abre em você. \"Todos os responsáveis\" mostra a equipe."),
                _passo("/crm/tarefas", "tar-area", "Atrasadas, hoje, futuras",
                       "Comece pela esquerda. **Concluídas** mostra só os últimos 7 dias."),
                _passo("/crm/tarefas", "tar-modal-dados", "A tarefa aberta",
                       "Tipo, situação, prazo e responsável. A faixa azul acima abre a oportunidade.",
                       clicar=["tar-cartao"]),
                _passo("/crm/tarefas", "tar-acoes", "Concluir com a próxima",
                       "**Concluir** pede o que aconteceu e, se for a última aberta, a **próxima tarefa**. "
                       "Sem próximo passo, finalize a oportunidade.",
                       clicar=["tar-cartao"]),
                _passo("/crm/tarefas", "tar-contadores", "A sua produção",
                       "**Realizadas no mês**: clique para ver por tipo e por responsável."),
            ],
            "quiz": [
                {
                    "enunciado": "O cliente não tem mais próximo passo. O que fazer com a última tarefa?",
                    "alternativas": [
                        ("Criar uma tarefa qualquer para daqui a 6 meses", False),
                        ("Finalizar a oportunidade", True),
                        ("Deixar a tarefa atrasar", False),
                        ("Passar a tarefa para o SDR", False),
                    ],
                },
                {
                    "enunciado": "A próxima tarefa é uma Reunião. O que acontece ao concluir?",
                    "alternativas": [
                        ("Ela vai para a agenda, se o horário estiver livre e em dia útil", True),
                        ("Nada, reunião só se marca na Agenda", False),
                        ("O SDR é avisado para marcar", False),
                        ("A oportunidade vai para Apresentação", False),
                    ],
                },
                {
                    "enunciado": "O prazo combinado com o cliente mudou. O certo é:",
                    "alternativas": [
                        ("Deixar a tarefa atrasar", False),
                        ("Editar o prazo da tarefa", True),
                        ("Cancelar e esquecer", False),
                        ("Concluir sem escrever nada", False),
                    ],
                },
                {
                    "enunciado": "Ao concluir, você marca a próxima como Reunião, mas o horário não está livre. O que o HIPO faz?",
                    "alternativas": [
                        ("Cancela a próxima tarefa", False),
                        ("Cria a tarefa e avisa para usar Colocar na agenda nela", True),
                        ("Marca a reunião assim mesmo, por cima da outra", False),
                        ("Impede de concluir a tarefa atual", False),
                    ],
                },
                {
                    "enunciado": "Por que cada toque da cadência de follow-up deve ser uma tarefa com prazo?",
                    "alternativas": [
                        ("Porque só tarefas aparecem na proposta", False),
                        ("Porque o cliente recebe um aviso a cada tarefa", False),
                        ("Porque tarefa conta como reunião no Monitor", False),
                        ("Porque a cadência anda sozinha e a gestão vê quem está em follow-up e há quanto tempo", True),
                    ],
                },
                {
                    "enunciado": "Você abre uma tarefa de reunião na tela Tarefas. Qual botão leva ao registro do desfecho?",
                    "alternativas": [
                        ("O que aconteceu?", True),
                        ("Editar reunião", False),
                        ("Colocar na agenda", False),
                        ("Cancelar", False),
                    ],
                },
                {
                    "enunciado": "Você quer ver a sua produção do mês separada por tipo de tarefa. Onde clicar?",
                    "alternativas": [
                        ("Na coluna Concluídas", False),
                        ("No seletor Responsável", False),
                        ("No contador Realizadas em (mês)", True),
                        ("Na faixa azul da tarefa", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0316"),
            "titulo": "Agenda: reuniões, desfecho, transcrição e scorecard",
            "resumo": "As suas reuniões na grade, o desfecho em dia, a reunião ao vivo, a transcrição do Meet e o scorecard do roteiro.",
            "duracao_min": 10,
            "conteudo_md": """\
## As suas reuniões

A Agenda abre na **sua** semana. Cada cartão é uma reunião: azul (futura), amarelo (hoje), verde (concluída), vermelho (atrasada ou no-show), riscado (cancelada). **Borda tracejada = falta registrar o desfecho.** Reunião no almoço ou depois das 18h aparece na faixa **Fora da grade**.

Você também pode marcar: clique num horário livre. **Anfitrião** é de quem é a reunião; **Agendado por** é de quem é o crédito.

## O desfecho

Clique no cartão e, no fim do painel, registre:

- **Realizada**: a reunião aconteceu. Conclui a tarefa e, se era a última aberta, pede a **próxima**.
- **Cancelada**: desmarcada com **24h ou mais** de antecedência.
- **No-show**: desmarcada em cima da hora, ou o cliente não apareceu.

O HIPO sugere pela régua das 24h, mas vale o que você registra. Cancelada e no-show tiram o evento da agenda de todo mundo, e o Google avisa o cliente.

## Reunião ao vivo

Em reunião online, o painel da reunião tem o link **Reunião ao vivo (transcrição durante a call)**. Ele abre uma aba que transcreve a conversa no Chrome (você e o cliente), mostra quanto você está falando e permite dar **Realizada** ou **No-show** dali. Abre 1 hora antes do início. Na hora: escolha a aba do Meet e deixe marcado **Compartilhar áudio da guia**.

## Transcrição e scorecard

Depois da call, a transcrição do Meet chega sozinha na tarefa da reunião (ou use **Buscar agora**). **Gerar resumo** traz resumo e próximos passos combinados; confira antes de registrar o desfecho.

Com a transcrição pronta, o **Scorecard do roteiro** avalia 10 itens de 0 a 2 (total 20, meta 15): preparação, contrato de abertura, perguntas de situação, problema e implicação, resumo, GPCT, apresentação ligada às dores, objeções com LAER e próximo passo com data. Vem com pontos fortes, pontos a melhorar e o foco da próxima reunião. A gestão pode ajustar e validar.

> No Monitor, **APRE** conta as reuniões realizadas e **SCORECARD** é a média do mês. Desfecho em dia é o que mantém esses números verdadeiros.
""",
            "tour": [
                _passo("/crm/agenda", "age-agenda-de", "A sua agenda",
                       "Abre na sua semana. Escolha outra pessoa ou \"Toda a equipe\" para ver os horários de todo mundo."),
                _passo("/crm/agenda", "age-kpis", "Sem desfecho",
                       "**Sem desfecho** aparece quando há reunião sem registro. Clique nele para ver a produtividade da semana."),
                _passo("/crm/agenda", "age-grade", "Os cartões",
                       "Cor pela situação; **borda tracejada = falta o desfecho**. Horário livre: clique para marcar."),
                _passo("/crm/agenda", "reuniao-desfecho", "Registrar o desfecho",
                       "Clicando numa reunião, o desfecho fica no fim do painel: **Realizada**, **Cancelada** ou **No-show**. "
                       "Se não houver reunião sua nesta semana, este passo fica sem destaque.",
                       clicar=["age-cartao"]),
                _passo("/crm/agenda", "age-produtividade", "Produtividade",
                       "Reuniões por EV na semana: realizadas, canceladas, no-show e pendentes."),
                _passo("/crm/agenda", None, "Ao vivo, transcrição e scorecard",
                       "No painel de uma reunião online: o link **Reunião ao vivo** (abre 1h antes), a **Transcrição** do Meet "
                       "com **Gerar resumo**, e o **Scorecard do roteiro** (10 itens, total 20, meta 15)."),
            ],
            "quiz": [
                {
                    "enunciado": "O que significa a borda tracejada num cartão da Agenda?",
                    "alternativas": [
                        ("Reunião cancelada", False),
                        ("Falta registrar o desfecho", True),
                        ("Reunião presencial", False),
                        ("Convite não enviado", False),
                    ],
                },
                {
                    "enunciado": "O cliente desmarcou 2 horas antes. Qual desfecho?",
                    "alternativas": [
                        ("Cancelada", False),
                        ("No-show", True),
                        ("Realizada", False),
                        ("Nenhum, apaga a reunião", False),
                    ],
                },
                {
                    "enunciado": "Qual é a meta do scorecard do roteiro?",
                    "alternativas": [
                        ("10 de 20", False),
                        ("15 de 20", True),
                        ("20 de 20", False),
                        ("Não há meta", False),
                    ],
                },
                {
                    "enunciado": "Uma reunião marcada para as 12h30 não aparece na grade. Onde ela está?",
                    "alternativas": [
                        ("Na faixa Fora da grade", True),
                        ("Na coluna Futuras da tela Tarefas", False),
                        ("Em lugar nenhum: a Agenda não aceita esse horário", False),
                        ("Na semana seguinte", False),
                    ],
                },
                {
                    "enunciado": "O cliente avisou com dois dias de antecedência que precisa desmarcar. Qual desfecho, e o que acontece?",
                    "alternativas": [
                        ("No-show; o evento continua na agenda", False),
                        ("Realizada; a tarefa é concluída", False),
                        ("Cancelada; o evento continua só na sua agenda", False),
                        ("Cancelada; o evento sai da agenda de todos e o Google avisa o cliente", True),
                    ],
                },
                {
                    "enunciado": "A partir de quando o link Reunião ao vivo (transcrição durante a call) fica disponível?",
                    "alternativas": [
                        ("Na hora exata do início", False),
                        ("1 hora antes do início", True),
                        ("No dia anterior", False),
                        ("Só depois que a reunião termina", False),
                    ],
                },
                {
                    "enunciado": "A call terminou e a transcrição do Meet ainda não apareceu na tarefa da reunião. O que fazer?",
                    "alternativas": [
                        ("Digitar a transcrição à mão", False),
                        ("Registrar No-show até ela chegar", False),
                        ("Clicar em Buscar agora", True),
                        ("Gerar o scorecard sem transcrição", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0317"),
            "titulo": "Contas, Relatórios e Monitor",
            "resumo": "A conta como apoio da negociação, como montar um relatório em três cliques e os quadros que medem o EV.",
            "duracao_min": 8,
            "conteudo_md": """\
## Contas

A conta é a empresa. Abra pela oportunidade (o nome da empresa no trilho) ou pela tela **Contas**. O que importa para o EV:

- **Dados públicos**: CNAE, atividade e **grau de risco (NR-4)**, porte e situação na Receita. Base para o diagnóstico e para o escopo da proposta.
- **Contatos**: quem decide, quem usa, quem paga. Um contato pode ser o **principal**.
- **Oportunidades**: as outras negociações com a mesma empresa.
- **Sócios**: e as outras empresas deles, dentro e fora do HIPO.

Nº de funcionários vindo da fonte é **estimativa**. Confirme com o cliente antes de usar na proposta.

## Relatórios

1. Escolha **o que analisar** (oportunidades, tarefas, reuniões, propostas, contas, contatos ou movimentações do funil).
2. Escolha **o período**.
3. **Montar relatório**. Depois arraste os campos para Filtros, Linhas, Colunas e Valores.

Todo número abre os registros que o compõem, e cada registro abre a oportunidade ou a conta. Salve no seu perfil e, se quiser, compartilhe com a equipe.

## Monitor

Os quadros do EV: **APRE** (reuniões realizadas), **NMRR** (mensalidade das conquistadas), **CONTRATOS**, **TICK MED** e **SCORECARD**. A meta de hoje acompanha os dias úteis do mês. Clique num quadro para ver o que compõe o número.

Na avaliação do squad de EV, os principais são **NMRR** e **pipeline**, junto com follow-ups, propostas, reuniões realizadas, vendas e conversão.
""",
            "tour": [
                _passo("/crm/contas", "con-360-topo", "A conta",
                       "Vertical, nº de funcionários, vendedor e situação, com as abas abaixo.",
                       clicar=["con-linha"]),
                _passo("/crm/contas", "con-360-topo", "Dados públicos",
                       "CNAE, atividade, porte e **grau de risco (NR-4)**: base do diagnóstico.",
                       clicar=["con-linha", "aba-dados-publicos"]),
                _passo("/crm/relatorios", "rel-fontes", "1. O que analisar",
                       "Oportunidades, tarefas, reuniões, propostas, contas, contatos ou movimentações do funil."),
                _passo("/crm/relatorios", "rel-montar", "2. Período e montar",
                       "Escolha o período e clique em **Montar relatório**. Depois é arrastar campos para linhas, colunas e valores."),
                _passo("/crm/relatorios", "rel-salvos", "Os salvos",
                       "Os seus relatórios e os compartilhados pela equipe."),
                _passo("/monitor", "mon-quadros", "Os quadros do EV",
                       "**APRE**, **NMRR**, **CONTRATOS**, **TICK MED** e **SCORECARD**. Clique num quadro para ver os itens."),
                PASSO_UC,
            ],
            "quiz": [
                {
                    "enunciado": "O nº de funcionários veio da fonte pública. Pode ir direto para a proposta?",
                    "alternativas": [
                        ("Sim, é dado oficial", False),
                        ("Não: é estimativa, confirme com o cliente", True),
                        ("Só se for maior que 100", False),
                        ("Só com aprovação do gestor", False),
                    ],
                },
                {
                    "enunciado": "Num relatório, o que acontece ao clicar num número?",
                    "alternativas": [
                        ("Nada", False),
                        ("Abre os registros que compõem o número", True),
                        ("Apaga o relatório", False),
                        ("Exporta para Excel", False),
                    ],
                },
                {
                    "enunciado": "Qual quadro do Monitor mede a mensalidade das oportunidades conquistadas?",
                    "alternativas": [
                        ("LEAD", False),
                        ("NMRR", True),
                        ("AGEN", False),
                        ("% NOSHOW", False),
                    ],
                },
                {
                    "enunciado": "Na tela Relatórios, qual é a ordem para montar um relatório?",
                    "alternativas": [
                        ("Arrastar os campos, escolher o período e depois a fonte", False),
                        ("Escolher o que analisar, o período, Montar relatório e arrastar os campos", True),
                        ("Escolher o período, salvar e depois escolher a fonte", False),
                        ("Montar relatório e só então escolher o que analisar", False),
                    ],
                },
                {
                    "enunciado": "Na conta, onde você vê as outras negociações com a mesma empresa?",
                    "alternativas": [
                        ("Na aba Sócios", False),
                        ("Na aba Dados públicos", False),
                        ("Na aba Contatos", False),
                        ("Na aba Oportunidades", True),
                    ],
                },
                {
                    "enunciado": "Na avaliação do squad de EV, quais são os indicadores principais?",
                    "alternativas": [
                        ("NMRR e pipeline", True),
                        ("Follow-ups e propostas", False),
                        ("Reuniões realizadas e scorecard", False),
                        ("Ticket médio e contratos", False),
                    ],
                },
                {
                    "enunciado": "Você montou um relatório que vai usar toda semana. O que dá para fazer com ele?",
                    "alternativas": [
                        ("Só exportar, porque relatório não fica salvo", False),
                        ("Mandar para a gestão publicar no Monitor", False),
                        ("Salvar no seu perfil e, se quiser, compartilhar com a equipe", True),
                        ("Fixar como quadro novo no Monitor", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0318"),
            "titulo": "Carreira: o seu Desempenho",
            "resumo": "A Carreira e as três abas, e como ler o seu Desempenho de EV: NMRR, pipeline, funil de reunião a venda e histórico.",
            "duracao_min": 7,
            "conteudo_md": TEXTO_CARREIRA_ABAS + """\
## A tela, de cima para baixo

1. **Ponto de atenção**: o indicador mais longe da meta, com o percentual, quanto falta para a meta do mês e o botão **Agir em**, que leva à tela certa (Oportunidades, Tarefas ou Agenda).
2. **Os principais do EV**: **NMRR** (a mensalidade das vendas do mês) e **PIPELINE (TICKET MENSAL)** (a mensalidade das oportunidades em negociação).
3. **Indicadores do mês**: todos os da RPeR do EV. Além dos principais: follow-ups realizados, taxa de execução, oportunidades trabalhadas, propostas enviadas, reuniões realizadas, vendas fechadas, taxa de conversão, ticket médio e em negociação.
4. **Funil**: Reuniões realizadas → Propostas → Vendas, com a taxa de cada passagem. É conversão dentro do mês, para enxergar onde o funil afina.
5. **Últimos meses**: seis meses de realizado e atingimento.

## Posição não é acumulado

**PIPELINE** e **EM NEGOCIAÇÃO** são uma fotografia do que está aberto agora, não uma soma ao longo do mês. Por isso são comparados com a meta cheia mesmo no mês aberto. Os demais seguem a meta de hoje.

## O que fazer com isso

- **Muita reunião, pouca proposta**: diagnóstico. Revise o **02 · Roteiro do EV**, nas aulas de diagnóstico e proposta.
- **Muita proposta, pouca venda**: negociação e follow-up. Toda proposta com próximo passo marcado.
- **Pipeline baixo**: falta reunião. Converse com o SDR e com a gestão sobre a agenda da semana.

""" + TEXTO_CARREIRA_GESTAO,
            "tour": _tour_desempenho(
                "Os dois números que mais pesam no EV: **NMRR** (vendas do mês) e "
                "**PIPELINE** (a mensalidade em negociação), com a meta e a barra do atingimento.",
                "Reuniões realizadas → propostas → vendas. A taxa de cada passagem mostra "
                "se o funil afina no diagnóstico ou na negociação.",
            ),
            "quiz": [
                {
                    "enunciado": "Dia útil 10 de 20. Sua meta de NMRR do mês é R$ 4.000 e você vendeu R$ 1.000. Qual é o atingimento da meta de hoje?",
                    "alternativas": [
                        ("25%", False),
                        ("50%", True),
                        ("100%", False),
                        ("10%", False),
                    ],
                },
                {
                    "enunciado": "Por que o PIPELINE é comparado com a meta cheia mesmo no meio do mês?",
                    "alternativas": [
                        ("Porque é posição: a fotografia do que está aberto agora, não uma soma", True),
                        ("Porque é o indicador mais importante", False),
                        ("Porque a gestão escolheu assim no Perfil", False),
                        ("Não é: segue a meta de hoje", False),
                    ],
                },
                {
                    "enunciado": "Seu funil mostra muitas reuniões realizadas e poucas propostas. O que revisar?",
                    "alternativas": [
                        ("O diagnóstico da reunião, no Roteiro de vendas", True),
                        ("A prospecção do SDR", False),
                        ("O cadastro da conta", False),
                        ("Nada: proposta não conta", False),
                    ],
                },
                {
                    "enunciado": "Onde a gestão cadastra a sua meta individual?",
                    "alternativas": [
                        ("No seu Perfil", False),
                        ("Em Monitor › RPeR › Metas por squad e pessoa", True),
                        ("Na proposta", False),
                        ("Em lugar nenhum: o HIPO calcula sozinho", False),
                    ],
                },
                {
                    "enunciado": "Seu funil mostra muitas propostas e poucas vendas. O que a aula manda trabalhar?",
                    "alternativas": [
                        ("Negociação e follow-up: toda proposta com próximo passo marcado", True),
                        ("Diagnóstico: revisar as perguntas da reunião", False),
                        ("Prospecção: pedir mais empresas ao SDR", False),
                        ("Cadastro: conferir as contas", False),
                    ],
                },
                {
                    "enunciado": "O seu PIPELINE está baixo. O que isso indica, segundo a aula?",
                    "alternativas": [
                        ("Que as propostas estão caras", False),
                        ("Que a meta foi mal cadastrada", False),
                        ("Que o follow-up está atrasado", False),
                        ("Falta reunião: converse com o SDR e a gestão sobre a agenda da semana", True),
                    ],
                },
                {
                    "enunciado": "Quais passagens aparecem no Funil do Desempenho do EV?",
                    "alternativas": [
                        ("Tarefas de prospecção → Empresas contatadas → Reuniões agendadas", False),
                        ("Reuniões realizadas → Propostas → Vendas", True),
                        ("Suspect → Lead → Qualificação → Negociação", False),
                        ("Parceiros → Indicações → Vendas", False),
                    ],
                },
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# HIPO - EC
# ═════════════════════════════════════════════════════════════════════

HIPO_EC = {
    "id": _id("b0400"),
    "titulo": "01 · HIPO - EC",
    "pilar": "metodo",
    "reforca": "tarefas_no_prazo",
    "descricao": (
        "Como o Executivo de Contas usa o HIPO: a carteira de parceiros "
        "(escritórios de contabilidade que indicam clientes), o farol de "
        "contato, as tarefas e reuniões de parceiro, as indicações que viram "
        "oportunidade e os números da carteira. Cada aula tem o botão \"Me "
        "mostra no HIPO\", que abre a tela real e aponta o que foi explicado."
    ),
    "prazo_dias": 15,
    "obrigatorios": ("EC",),
    "opcionais": GESTAO_OPCIONAL,
    "aulas": [
        {
            "id": _id("b0411"),
            "titulo": "O HIPO no dia do EC",
            "resumo": "As telas do EC, a ordem do dia e as regras que o sistema cobra da carteira de parceiros.",
            "duracao_min": 7,
            "conteudo_md": """\
## O trabalho do EC no HIPO

O EC cuida da **carteira de parceiros**: escritórios de contabilidade (e outras empresas) que **indicam** clientes para a Controller. Parceiro bem cuidado indica; parceiro esquecido esfria. O HIPO mede as duas coisas: contato com o parceiro e indicações que chegam.

## As telas do EC

- **Parceiros**: a sua carteira. Só EC e gestão veem esta tela.
- **Tarefas**: o que está em aberto, inclusive as tarefas de parceiro.
- **Agenda**: abre em **Parceiros**, com as reuniões da carteira.
- **Oportunidades**: as indicações que viraram negociação.
- **Contas**: o cadastro das empresas, onde se marca o **Finder**.
- **Relatórios** e **Monitor**.
- **Carreira**: a Universidade, o seu PDI e o seu Desempenho contra a meta.

## O seu dia, na ordem

1. **Parceiros**: quem está **Sem contato** nesta semana e quem está esfriando.
2. **Tarefas**: atrasadas primeiro.
3. **Agenda**: reuniões de carteira da semana e o desfecho das que passaram.
4. **Oportunidades**: como andam as indicações dos seus parceiros.

## As regras que o sistema cobra

- **A última tarefa aberta de um parceiro só se conclui com a próxima marcada.** Parceiro não fica sem próximo contato. Se a parceria acabou, cancele a tarefa ou tire o parceiro da carteira.
- **Toda reunião tem desfecho**: realizada, cancelada ou no-show.

> Clique em **Me mostra no HIPO**: o tour abre as telas e aponta cada item, sem mudar nada.
""",
            "tour": [
                PASSO_BARRA,
                _passo("/crm/parceiros", "nav-parceiros", "Parceiros",
                       "A sua carteira de parceiros indicadores. Só EC e gestão enxergam este item."),
                _passo("/crm/tarefas", "nav-tarefas", "Tarefas",
                       "O que está em aberto, inclusive as tarefas de parceiro."),
                _passo("/crm/agenda", "nav-agenda", "Agenda",
                       "Para o EC, abre filtrada nas reuniões de **Parceiros**."),
                _passo("/crm/oportunidades", "nav-oportunidades", "Oportunidades",
                       "As indicações dos seus parceiros, depois que viram negociação."),
                _passo("/crm/contas", "nav-contas", "Contas",
                       "O cadastro das empresas. É marcando **Finder** numa conta que ela vira parceiro."),
                _passo("/monitor", "mon-quadros", "Monitor",
                       "O quadro **PARCERIAS** conta as reuniões de parceiro realizadas no mês."),
                PASSO_CARREIRA,
                PASSO_PERFIL,
            ],
            "quiz": [
                {
                    "enunciado": "Quem enxerga a tela Parceiros?",
                    "alternativas": [
                        ("Todo mundo", False),
                        ("EC e gestão", True),
                        ("Só o SDR", False),
                        ("Só o EV", False),
                    ],
                },
                {
                    "enunciado": "Você quer concluir a última tarefa aberta de um parceiro. O que o HIPO pede?",
                    "alternativas": [
                        ("Nada", False),
                        ("A próxima tarefa com o parceiro", True),
                        ("Uma indicação nova", False),
                        ("A aprovação do gestor", False),
                    ],
                },
                {
                    "enunciado": "Em que assunto a Agenda abre para o EC?",
                    "alternativas": [
                        ("Oportunidades", False),
                        ("Parceiros", True),
                        ("Toda a equipe", False),
                        ("No-show", False),
                    ],
                },
                {
                    "enunciado": "Para que o EC usa a tela Oportunidades?",
                    "alternativas": [
                        ("Para cadastrar parceiros novos", False),
                        ("Para puxar empresas da base da Receita", False),
                        ("Para acompanhar as indicações que viraram negociação", True),
                        ("Para marcar as reuniões de carteira", False),
                    ],
                },
                {
                    "enunciado": "Pela ordem do dia do EC proposta na aula, por onde você começa?",
                    "alternativas": [
                        ("Parceiros: quem está Sem contato nesta semana e quem está esfriando", True),
                        ("Tarefas: atrasadas primeiro", False),
                        ("Agenda: reuniões de carteira da semana", False),
                        ("Oportunidades: como andam as indicações", False),
                    ],
                },
                {
                    "enunciado": "Em que tela se marca uma empresa como Finder, para ela virar parceiro?",
                    "alternativas": [
                        ("Em Parceiros, botão Novo parceiro", False),
                        ("Em Monitor, quadro PARCERIAS", False),
                        ("Em Agenda, no formulário de reunião", False),
                        ("Em Contas", True),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, quais duas coisas o HIPO mede no trabalho do EC?",
                    "alternativas": [
                        ("Ligações feitas e propostas enviadas", False),
                        ("Contato com o parceiro e indicações que chegam", True),
                        ("Empresas puxadas e reuniões agendadas", False),
                        ("No-show e ticket médio", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0412"),
            "titulo": "Parceiros: ler a carteira",
            "resumo": "Os números da carteira, os filtros, o farol de 4 semanas, o mini-funil e a situação de cada parceiro.",
            "duracao_min": 9,
            "conteudo_md": """\
## O que é um parceiro

Parceiro é uma **conta** marcada como **Finder** (indicadora). Não existe cadastro separado: a conta vira parceiro quando é usada como **Finder** numa oportunidade, ou quando alguém marca **Finder** na tela de Contas.

## Os números do topo

- **Parceiros**: o tamanho da carteira (com os filtros da tela).
- **Sem EC**: parceiros sem responsável. Clique para ver a fila.
- **Sem contato**: nesta semana, nenhuma tarefa feita nem marcada. É a sua lista do dia.
- **Dormentes**: sem indicar há mais de 180 dias.
- **Conversão**: das indicações que chegaram ao fim, quantas viraram cliente. Cancelado fica fora.

## Os filtros

**EC responsável** (escolha você para ver só a sua carteira), **Situação**, **Período** (desde sempre, últimos 90 dias, ano corrente) e a busca por empresa ou CNPJ.

## A situação do parceiro

Pela última indicação, em toda a história:

- **Ativo**: indicou nos últimos 90 dias.
- **Esfriando**: entre 90 e 180 dias.
- **Dormente**: mais de 180 dias.
- **Sem indicação**: nunca indicou.

## O farol de 4 semanas

Na coluna **Contato**, quatro bolinhas, uma por semana (a atual tem um anel):

- **Verde**: tarefa concluída com o parceiro naquela semana.
- **Amarelo**: tarefa agendada e não feita.
- **Vermelho**: nada.

Embaixo, a próxima tarefa marcada, ou "atrasada", ou "nada agendado".

## O mini-funil

Na coluna **Em aberto**, as indicações do parceiro por fase (S, L, Q, A, N) com quantidade e valor. Mostra se o que ele indica está andando.

> Quatro semanas verdes sem indicação é problema de mercado; quatro vermelhas é abandono.
""",
            "tour": [
                _passo("/crm/parceiros", "par-kpis", "Os números da carteira",
                       "Parceiros, **Sem EC**, **Sem contato** (a sua lista do dia), **Dormentes** e **Conversão**. Os três do meio filtram a lista."),
                _passo("/crm/parceiros", "par-filtro-ec", "A sua carteira",
                       "Escolha você em **EC responsável** para ver só os seus parceiros."),
                _passo("/crm/parceiros", "par-filtros", "Situação e período",
                       "Situação (sem indicação, ativo, esfriando, dormente), período e a busca."),
                _passo("/crm/parceiros", "par-lista", "A lista",
                       "EC responsável (troca direto na linha), o **farol** de contato das 4 semanas, o **mini-funil** "
                       "das indicações em aberto, situação, conversão e ticket."),
                _passo("/crm/parceiros", "par-transferir", "Transferir carteira",
                       "Move todos os parceiros de uma pessoa para outra de uma vez. Cada parceiro registra o evento no histórico."),
            ],
            "quiz": [
                {
                    "enunciado": "Um parceiro indicou pela última vez há 120 dias. Qual é a situação dele?",
                    "alternativas": [
                        ("Ativo", False),
                        ("Esfriando", True),
                        ("Dormente", False),
                        ("Sem indicação", False),
                    ],
                },
                {
                    "enunciado": "No farol de 4 semanas, o que significa amarelo?",
                    "alternativas": [
                        ("Tarefa concluída na semana", False),
                        ("Tarefa agendada e não feita", True),
                        ("Nenhum contato", False),
                        ("Parceiro dormente", False),
                    ],
                },
                {
                    "enunciado": "Como uma conta vira parceiro no HIPO?",
                    "alternativas": [
                        ("Pelo botão Novo parceiro", False),
                        ("Sendo usada como Finder numa oportunidade, ou marcada como Finder em Contas", True),
                        ("Só a gestão cadastra", False),
                        ("Importando uma planilha", False),
                    ],
                },
                {
                    "enunciado": "O que o número Sem contato, no topo de Parceiros, mostra?",
                    "alternativas": [
                        ("Parceiros que nunca indicaram", False),
                        ("Parceiros sem EC responsável", False),
                        ("Parceiros sem indicar há mais de 180 dias", False),
                        ("Parceiros sem tarefa feita nem marcada nesta semana", True),
                    ],
                },
                {
                    "enunciado": "O que mostra o mini-funil da coluna Em aberto?",
                    "alternativas": [
                        ("As indicações do parceiro por fase (S, L, Q, A, N), com quantidade e valor", True),
                        ("As tarefas do parceiro nas últimas 4 semanas", False),
                        ("A conversão do parceiro mês a mês", False),
                        ("Os contatos do escritório por cargo", False),
                    ],
                },
                {
                    "enunciado": "Um parceiro tem quatro semanas verdes no farol e nenhuma indicação. Como a aula lê isso?",
                    "alternativas": [
                        ("Abandono do parceiro pelo EC", False),
                        ("Problema de mercado, não de contato", True),
                        ("Erro de cadastro do Finder", False),
                        ("Parceiro pronto para sair da carteira", False),
                    ],
                },
                {
                    "enunciado": "Um EC vai sair de férias e todos os parceiros dele precisam passar para você. O que usar?",
                    "alternativas": [
                        ("Remover da carteira em cada parceiro", False),
                        ("Filtro EC responsável com o seu nome", False),
                        ("Transferir carteira, que move todos de uma vez e registra no histórico", True),
                        ("Marcar Finder de novo em cada conta", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0413"),
            "titulo": "Dentro do parceiro",
            "resumo": "O painel do parceiro: EC responsável, relação, abas de dados, tarefas, indicações e carteira, e as ações do rodapé.",
            "duracao_min": 8,
            "conteudo_md": """\
## Abrir

Clique na linha do parceiro. O painel abre por cima da lista.

## O trilho da esquerda

- **EC**: o responsável. Trocar grava **na hora** e registra o evento.
- **Relação**: a situação (ativo, esfriando, dormente, sem indicação).
- As abas.

## As abas

- **Dados**: o **Contato nas 4 semanas** (farol com frase, como "Sem contato há 3 semanas") e as **Indicações em aberto** (mini-funil); conversão, cancelamento, ticket ganho e a última indicação; cidade, telefone e e-mail. Razão social, endereço e contatos se editam na tela de Contas.
- **Tarefas**: igual à da oportunidade. **Nova tarefa** com tipo, título, prazo e responsável. Reunião ou visita vai para a agenda (**Marcar na agenda**).
- **Indicações**: as oportunidades que o parceiro indicou, com status, fase e mensalidade. **Abrir** leva ao funil.
- **Carteira**: a trilha da carteira (virou parceiro, assumido por, transferido, saiu da carteira), com data e autor.

## O rodapé

- **Agendar reunião**: abre o formulário já preso no parceiro, com o EC responsável como anfitrião.
- **Remover da carteira**: o parceiro deixa de ser Finder. Use quando a parceria acabou de verdade.

> Antes de ligar para o parceiro, abra **Indicações**: falar do cliente que ele indicou e já fechou é a melhor abertura que existe.
""",
            "tour": [
                _passo("/crm/parceiros", "par-det-trilho", "O trilho",
                       "**EC** (troca grava na hora), **Relação** e as abas.",
                       clicar=["par-linha"]),
                _passo("/crm/parceiros", "par-det-farol-funil", "Contato e indicações",
                       "O farol das 4 semanas com a frase do momento e o mini-funil das indicações em aberto.",
                       clicar=["par-linha", "aba-dados"]),
                _passo("/crm/parceiros", "par-det-conteudo", "Tarefas do parceiro",
                       "Atrasadas, em aberto e **Nova tarefa**. Concluir a última aberta pede a próxima.",
                       clicar=["par-linha", "aba-tarefas"]),
                _passo("/crm/parceiros", "par-det-conteudo", "Indicações",
                       "As oportunidades que o parceiro indicou. **Abrir** leva direto ao funil.",
                       clicar=["par-linha", "aba-indicacoes"]),
                _passo("/crm/parceiros", "par-det-conteudo", "Carteira",
                       "Quem assumiu, quando foi transferido, quando saiu da carteira.",
                       clicar=["par-linha", "aba-carteira"]),
                _passo("/crm/parceiros", "par-det-acoes", "Agendar e remover",
                       "**Agendar reunião** já vem preso no parceiro. **Remover da carteira** tira o Finder.",
                       clicar=["par-linha"]),
            ],
            "quiz": [
                {
                    "enunciado": "Onde se edita o endereço e os contatos do parceiro?",
                    "alternativas": [
                        ("Na aba Dados do parceiro", False),
                        ("Na tela de Contas", True),
                        ("Na aba Carteira", False),
                        ("Não dá para editar", False),
                    ],
                },
                {
                    "enunciado": "O que a aba Indicações mostra?",
                    "alternativas": [
                        ("As oportunidades que o parceiro indicou", True),
                        ("Os sócios do escritório", False),
                        ("As tarefas atrasadas", False),
                        ("As reuniões da semana", False),
                    ],
                },
                {
                    "enunciado": "Quando usar Remover da carteira?",
                    "alternativas": [
                        ("Para não ter tarefa com o parceiro esta semana", False),
                        ("Quando a parceria acabou de verdade", True),
                        ("Para transferir para outro EC", False),
                        ("Toda vez que o farol fica vermelho", False),
                    ],
                },
                {
                    "enunciado": "No trilho do parceiro, você troca o EC responsável. Precisa salvar?",
                    "alternativas": [
                        ("Sim, no botão Salvar do rodapé", False),
                        ("Sim, e a gestão precisa aprovar", False),
                        ("Só se o parceiro tiver tarefa aberta", False),
                        ("Não: grava na hora e registra o evento", True),
                    ],
                },
                {
                    "enunciado": "Antes de ligar para um parceiro, o que a aula sugere abrir?",
                    "alternativas": [
                        ("A aba Carteira, para ver quem assumiu", False),
                        ("A aba Indicações, para falar do cliente que ele indicou e já fechou", True),
                        ("O Monitor, para ver o quadro PARCERIAS", False),
                        ("A tela de Contas, para conferir o endereço", False),
                    ],
                },
                {
                    "enunciado": "Onde você vê quando o parceiro virou parceiro, quem o assumiu e quando foi transferido?",
                    "alternativas": [
                        ("Na aba Carteira", True),
                        ("Na aba Dados", False),
                        ("Na aba Tarefas", False),
                        ("Na aba Indicações", False),
                    ],
                },
                {
                    "enunciado": "Você usa Agendar reunião no rodapé do parceiro. Quem vem como anfitrião?",
                    "alternativas": [
                        ("O EV da última indicação", False),
                        ("Quem estiver livre no horário", False),
                        ("O EC responsável pelo parceiro", True),
                        ("A gestão", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0414"),
            "titulo": "Tarefas e reuniões de parceiro",
            "resumo": "Como manter o farol verde: tarefas de parceiro com próximo passo, reuniões de carteira na agenda e desfecho em dia.",
            "duracao_min": 9,
            "conteudo_md": """\
## O farol fica verde com tarefa feita

Verde é **tarefa concluída** com o parceiro na semana. Ligação, WhatsApp, visita: tudo é tarefa, e só conta quando é concluída no HIPO.

## Tarefas de parceiro

Criadas na aba **Tarefas** do parceiro. Na tela **Tarefas**, o cartão de parceiro mostra "Parceiro" no lugar do número da oportunidade.

Ao **concluir** a última tarefa aberta de um parceiro, o HIPO pede a **próxima**. A parceria não fica sem próximo contato. Se não há mais o que fazer com ele: **cancele a tarefa** em vez de concluir, ou **tire o parceiro da carteira**.

## Reuniões de carteira

A Agenda do EC abre filtrada em **Parceiros**. Para marcar:

1. Clique num horário livre.
2. Em **Reunião com**, escolha **Parceiro (contador)** e busque o escritório (só aparecem contas marcadas como parceiras).
3. **Anfitrião**: você. **Agendado por**: você.
4. **Marcar e enviar convite**.

Ou, de dentro do parceiro, **Agendar reunião**: o formulário já vem preso nele.

## Desfecho

Igual a qualquer reunião: **Realizada**, **Cancelada** (24h ou mais de antecedência) ou **No-show**. Realizada conclui a tarefa e pede a próxima. O quadro **PARCERIAS** do Monitor conta as reuniões de parceiro **realizadas** no mês: reunião sem desfecho não conta.
""",
            "tour": [
                _passo("/crm/tarefas", "tar-area", "As suas tarefas",
                       "Tarefas de parceiro aparecem aqui junto com as de oportunidade, marcadas como \"Parceiro\"."),
                _passo("/crm/tarefas", "tar-acoes", "Concluir com a próxima",
                       "A última tarefa aberta de um parceiro só se conclui com a **próxima** marcada. "
                       "Sem próximo contato: cancele a tarefa ou tire o parceiro da carteira.",
                       clicar=["tar-cartao"]),
                _passo("/crm/agenda", "age-assunto", "Agenda em Parceiros",
                       "Para o EC a Agenda abre aqui, em **Parceiros**. Clique de novo para ver tudo."),
                _passo("/crm/agenda", "reuniao-com-quem", "Reunião com parceiro",
                       "Clicando num horário livre, escolha **Parceiro (contador)** e busque o escritório. "
                       "Nada é gravado até Marcar e enviar convite.",
                       clicar=["age-celula-livre"]),
                _passo("/crm/agenda", "reuniao-anfitriao", "Anfitrião",
                       "Você: a reunião é sua.",
                       clicar=["age-celula-livre"]),
                _passo("/crm/agenda", "age-kpis", "Sem desfecho",
                       "Reunião sem desfecho não conta no quadro PARCERIAS. Fique de olho neste número."),
            ],
            "quiz": [
                {
                    "enunciado": "O que deixa a semana verde no farol do parceiro?",
                    "alternativas": [
                        ("Uma tarefa marcada", False),
                        ("Uma tarefa concluída com o parceiro naquela semana", True),
                        ("Uma indicação nova", False),
                        ("Abrir o painel do parceiro", False),
                    ],
                },
                {
                    "enunciado": "Não há mais o que fazer com um parceiro. O que fazer com a última tarefa?",
                    "alternativas": [
                        ("Concluir e marcar uma tarefa falsa", False),
                        ("Cancelar a tarefa, ou tirar o parceiro da carteira", True),
                        ("Deixar atrasar", False),
                        ("Passar para o SDR", False),
                    ],
                },
                {
                    "enunciado": "O que o quadro PARCERIAS do Monitor conta?",
                    "alternativas": [
                        ("Parceiros na carteira", False),
                        ("Reuniões de parceiro realizadas no mês", True),
                        ("Indicações recebidas", False),
                        ("Tarefas de parceiro criadas", False),
                    ],
                },
                {
                    "enunciado": "Na tela Tarefas, como você reconhece o cartão de uma tarefa de parceiro?",
                    "alternativas": [
                        ("Ele aparece numa coluna própria, Parceiros", False),
                        ("Ele mostra \"Parceiro\" no lugar do número da oportunidade", True),
                        ("Ele vem sempre em vermelho", False),
                        ("Ele só aparece na aba Tarefas do parceiro", False),
                    ],
                },
                {
                    "enunciado": "Você vai marcar uma reunião com um escritório parceiro pela Agenda. O que escolher em Reunião com?",
                    "alternativas": [
                        ("Cliente (oportunidade), buscando pelo CNPJ", False),
                        ("Convidado externo, digitando o e-mail", False),
                        ("Toda a equipe, para ver os horários", False),
                        ("Parceiro (contador), buscando o escritório", True),
                    ],
                },
                {
                    "enunciado": "Na busca de Parceiro (contador), o escritório que você procura não aparece. Qual é a causa mais provável?",
                    "alternativas": [
                        ("A conta não está marcada como parceira (Finder)", True),
                        ("O escritório já tem reunião na semana", False),
                        ("A Agenda está filtrada em Oportunidades", False),
                        ("O escritório não tem CNPJ válido na Receita", False),
                    ],
                },
                {
                    "enunciado": "Na reunião de carteira marcada pela Agenda, quem vai em Anfitrião e quem vai em Agendado por?",
                    "alternativas": [
                        ("Anfitrião: o EV. Agendado por: você", False),
                        ("Anfitrião: o parceiro. Agendado por: você", False),
                        ("Você nos dois", True),
                        ("Anfitrião: você. Agendado por: a gestão", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0415"),
            "titulo": "Indicações que viram oportunidade",
            "resumo": "Como registrar a indicação no funil com o parceiro como Finder, o papel de EC nos envolvidos e como acompanhar a conversão.",
            "duracao_min": 8,
            "conteudo_md": """\
## O caminho da indicação

1. O parceiro indica uma empresa.
2. A empresa vira **conta** (se ainda não existir) e ganha uma **oportunidade**.
3. Na aba **Dados** da oportunidade, o campo **Finder** recebe o **parceiro**. É isso que liga a indicação ao parceiro: conta na conversão dele, aparece em **Indicações** e no mini-funil.
4. Na aba **Envolvidos**, você entra com o papel **EC**.

Conta usada como Finder vira parceiro automaticamente, se ainda não era.

## Acompanhar no funil

Nos **Filtros** de Oportunidades:

- **Indicação de parceiro: Veio de parceiro** mostra só as indicações.
- **Equipe: você, papel EC** mostra as oportunidades em que você está envolvido.

## A conversão do parceiro

**Conversão** = indicações conquistadas ÷ indicações que chegaram ao fim. **Cancelado** fica fora (é erro de cadastro, não perda). É por isso que o desfecho certo importa: perda registrada como cancelamento infla a conversão do parceiro e esconde o problema.

## Contas: o Finder

Na visão 360 de uma conta, a **Situação** tem os marcadores **Ativa** e **Finder**. Marcar Finder transforma a conta em parceiro, sem esperar uma indicação.

> Indicação sem Finder preenchido é indicação perdida para o parceiro e para você: não entra na carteira nem na sua avaliação de vendas com EC.
""",
            "tour": [
                _passo("/crm/oportunidades", "opo-filtros", "Filtrar as indicações",
                       "Em **Indicação de parceiro**, escolha \"Veio de parceiro\". Em **Equipe**, você com o papel **EC**.",
                       clicar=["opo-filtros-botao"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "O campo Finder",
                       "Na aba **Dados** da oportunidade, o **Finder** é o parceiro que indicou. É isso que liga a indicação a ele.",
                       clicar=["opo-cartao-abrir", "aba-dados"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Você como EC",
                       "Na aba **Envolvidos**, entre com o papel **EC**.",
                       clicar=["opo-cartao-abrir", "aba-envolvidos"]),
                _passo("/crm/contas", "con-360-situacao", "Finder na conta",
                       "Na conta, o marcador **Finder** transforma a empresa em parceiro.",
                       clicar=["con-linha"]),
            ],
            "quiz": [
                {
                    "enunciado": "O que liga uma oportunidade ao parceiro que indicou?",
                    "alternativas": [
                        ("O nome do parceiro na descrição", False),
                        ("O campo Finder na aba Dados", True),
                        ("Uma tarefa de parceiro", False),
                        ("Nada, é automático", False),
                    ],
                },
                {
                    "enunciado": "Por que registrar perda como Cancelado é um problema?",
                    "alternativas": [
                        ("Não é problema", False),
                        ("Cancelado fica fora da conversão e esconde a perda", True),
                        ("Apaga a oportunidade", False),
                        ("Tira o parceiro da carteira", False),
                    ],
                },
                {
                    "enunciado": "Como ver no funil só as oportunidades que vieram de parceiro?",
                    "alternativas": [
                        ("Filtros → Indicação de parceiro: Veio de parceiro", True),
                        ("Visão Funil", False),
                        ("Clicar em Ganhas no mês", False),
                        ("Pela Agenda", False),
                    ],
                },
                {
                    "enunciado": "Uma indicação virou oportunidade, mas o campo Finder ficou vazio. Qual é a consequência?",
                    "alternativas": [
                        ("O parceiro é removido da carteira", False),
                        ("A oportunidade não pode ser finalizada", False),
                        ("O EV recebe a indicação como dele", False),
                        ("Não entra na carteira do parceiro nem na sua avaliação de vendas com EC", True),
                    ],
                },
                {
                    "enunciado": "Na aba Envolvidos de uma oportunidade indicada pelo seu parceiro, com que papel você entra?",
                    "alternativas": [
                        ("SDR", False),
                        ("EC", True),
                        ("EV", False),
                        ("Finder", False),
                    ],
                },
                {
                    "enunciado": "Uma conta que ainda não era parceiro é usada como Finder numa oportunidade. O que acontece com ela?",
                    "alternativas": [
                        ("Vira parceiro automaticamente", True),
                        ("Precisa ser aprovada pela gestão", False),
                        ("Fica marcada como Não prospectar", False),
                        ("Nada, até alguém marcar Finder em Contas", False),
                    ],
                },
                {
                    "enunciado": "Como o HIPO calcula a Conversão do parceiro?",
                    "alternativas": [
                        ("Indicações ganhas ÷ todas as indicações, inclusive as abertas", False),
                        ("Reuniões realizadas ÷ indicações recebidas", False),
                        ("Indicações conquistadas ÷ indicações que chegaram ao fim, sem os cancelados", True),
                        ("Indicações do mês ÷ parceiros na carteira", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0416"),
            "titulo": "Os números da carteira",
            "resumo": "Os quadros do Monitor e o que a gestão olha no squad de EC, mais um relatório pronto para a sua carteira.",
            "duracao_min": 6,
            "conteudo_md": """\
## Monitor

O painel da sala tem dez quadros com a meta de hoje (proporcional aos dias úteis) e o resultado do mês. O do EC é **PARCERIAS**: reuniões de parceiro **realizadas** no mês. Clique no quadro para ver quais.

## O que a gestão olha no squad de EC

Contas sob gestão (parceiros), **reuniões de carteira** (reuniões de parceiro realizadas em que você foi o anfitrião; principal), parcerias novas, leads indicados, tarefas, taxa de execução, vendas com EC e **MRR fechado** (principal). Tudo sai do que você lança: tarefa concluída, reunião com desfecho, Finder preenchido, você nos Envolvidos.

## Um relatório útil

Em **Relatórios**: fonte **Oportunidades**, período **Este ano**, **Montar relatório**. Em Filtros, coloque **Veio de indicação de parceiro**; em Linhas, **Parceiro que indicou**; em Valores, a mensalidade. Salve como "Indicações por parceiro". Todo número abre as oportunidades que o compõem.
""",
            "tour": [
                _passo("/monitor", "mon-quadros", "PARCERIAS",
                       "Reuniões de parceiro realizadas no mês, contra a meta de hoje. Clique no quadro para ver quais."),
                _passo("/crm/relatorios", "rel-fontes", "Um relatório da carteira",
                       "Comece por **Oportunidades**, escolha o período e monte. Depois: **Parceiro que indicou** nas linhas, mensalidade nos valores."),
                _passo("/crm/parceiros", "par-kpis", "De volta à carteira",
                       "**Sem contato** é por onde a semana começa. Quem está nele hoje vira tarefa hoje."),
                PASSO_UC,
            ],
            "quiz": [
                {
                    "enunciado": "Qual é o quadro do Monitor que mede o EC?",
                    "alternativas": [
                        ("LEAD", False),
                        ("PARCERIAS", True),
                        ("AGEND MES", False),
                        ("TICK MED", False),
                    ],
                },
                {
                    "enunciado": "Quais são os indicadores principais do squad de EC?",
                    "alternativas": [
                        ("Leads e no-show", False),
                        ("Reuniões de carteira e MRR fechado", True),
                        ("Propostas e ticket médio", False),
                        ("Agendamentos e contas prospectadas", False),
                    ],
                },
                {
                    "enunciado": "O que faz uma venda contar como \"venda com EC\"?",
                    "alternativas": [
                        ("Você estar nos Envolvidos da oportunidade com o papel EC", True),
                        ("A empresa ser da sua cidade", False),
                        ("O gestor marcar no fim do mês", False),
                        ("Nada, toda venda conta", False),
                    ],
                },
                {
                    "enunciado": "Para a gestão, o que conta como reunião de carteira?",
                    "alternativas": [
                        ("Qualquer reunião marcada com parceiro", False),
                        ("Reunião de parceiro realizada em que você foi o anfitrião", True),
                        ("Reunião de cliente indicada por parceiro", False),
                        ("Tarefa de ligação concluída com parceiro", False),
                    ],
                },
                {
                    "enunciado": "No relatório \"Indicações por parceiro\" sugerido na aula, o que vai em Linhas?",
                    "alternativas": [
                        ("A mensalidade", False),
                        ("Veio de indicação de parceiro", False),
                        ("A fase da oportunidade", False),
                        ("Parceiro que indicou", True),
                    ],
                },
                {
                    "enunciado": "Para montar esse relatório, que fonte e que período a aula indica?",
                    "alternativas": [
                        ("Oportunidades, período Este ano", True),
                        ("Contas, período Este mês", False),
                        ("Reuniões, últimos 30 dias", False),
                        ("Tarefas, desde sempre", False),
                    ],
                },
                {
                    "enunciado": "Pelo tour, por onde a semana do EC começa?",
                    "alternativas": [
                        ("Pelo quadro PARCERIAS do Monitor", False),
                        ("Pelo relatório Indicações por parceiro", False),
                        ("Pelo número Sem contato em Parceiros: quem está nele vira tarefa hoje", True),
                        ("Pela coluna Concluídas em Tarefas", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0417"),
            "titulo": "Carreira: o seu Desempenho",
            "resumo": "A Carreira e as três abas, e como ler o seu Desempenho de EC: reuniões de carteira, MRR, funil de parceiro a venda e histórico.",
            "duracao_min": 7,
            "conteudo_md": TEXTO_CARREIRA_ABAS + """\
## A tela, de cima para baixo

1. **Ponto de atenção**: o indicador mais longe da meta, com o percentual, quanto falta para a meta do mês e o botão **Agir em**, que leva à tela certa (Parceiros, Agenda, Tarefas ou Oportunidades).
2. **Os principais do EC**: **REUNIÕES DE CARTEIRA** (reuniões de parceiro realizadas em que você foi o anfitrião) e **MRR FECHADO** (a mensalidade das vendas em que você está nos Envolvidos como EC).
3. **Indicadores do mês**: todos os da RPeR do EC. Além dos principais: contas sob gestão, parcerias novas, leads indicados, tarefas, taxa de execução e vendas com EC.
4. **Funil**: Parceiros na carteira → Reuniões de carteira → Indicações recebidas → Vendas com EC. "Reuniões por parceiro" e "indicações por reunião" aparecem como razão: 0,5 indicação por reunião quer dizer 1 indicação a cada 2 reuniões. É conversão dentro do mês.
5. **Últimos meses**: seis meses de realizado e atingimento.

**CONTAS SOB GESTÃO** é posição (a carteira de hoje, não uma soma), por isso é comparada com a meta cheia mesmo no mês aberto.

## O que fazer com isso

- **Poucas reuniões por parceiro**: cadência da carteira. Comece a semana pelo **Sem contato** em Parceiros e revise o **02 · Roteiro do EC**.
- **Muitas reuniões, poucas indicações**: o pedido de indicação. Toda reunião de carteira termina com um pedido concreto.
- **Indicações que não viram venda**: acompanhe com o EV e confira se você está nos **Envolvidos** da oportunidade, com o papel EC.

""" + TEXTO_CARREIRA_GESTAO,
            "tour": _tour_desempenho(
                "Os dois números que mais pesam no EC: **REUNIÕES DE CARTEIRA** e "
                "**MRR FECHADO**, com a meta e a barra do atingimento.",
                "Parceiros na carteira → reuniões de carteira → indicações recebidas → "
                "vendas com EC. As razões mostram se falta reunião ou falta pedido de indicação.",
            ),
            "quiz": [
                {
                    "enunciado": "Dia útil 10 de 20. Sua meta do mês é 20 reuniões de carteira e você fez 8. Qual é o atingimento da meta de hoje?",
                    "alternativas": [
                        ("40%", False),
                        ("80%", True),
                        ("160%", False),
                        ("8%", False),
                    ],
                },
                {
                    "enunciado": "Você faz muitas reuniões de carteira, mas recebe poucas indicações. O que o funil está dizendo?",
                    "alternativas": [
                        ("Falta o pedido de indicação nas reuniões", True),
                        ("Falta parceiro na carteira", False),
                        ("O EV não está vendendo", False),
                        ("Nada: reunião é o que conta", False),
                    ],
                },
                {
                    "enunciado": "O que faz uma venda entrar no seu MRR FECHADO?",
                    "alternativas": [
                        ("Você estar nos Envolvidos da oportunidade com o papel EC", True),
                        ("A empresa ser da sua cidade", False),
                        ("O gestor marcar no fim do mês", False),
                        ("Toda venda do mês entra", False),
                    ],
                },
                {
                    "enunciado": "Onde a gestão cadastra a sua meta individual?",
                    "alternativas": [
                        ("No seu Perfil", False),
                        ("Em Monitor › RPeR › Metas por squad e pessoa", True),
                        ("Em Parceiros", False),
                        ("Em lugar nenhum: o HIPO calcula sozinho", False),
                    ],
                },
                {
                    "enunciado": "No funil do seu Desempenho, \"indicações por reunião\" está em 0,5. O que isso quer dizer?",
                    "alternativas": [
                        ("5 indicações a cada reunião", False),
                        ("0,5% das reuniões geraram indicação", False),
                        ("2 indicações a cada reunião", False),
                        ("1 indicação a cada 2 reuniões", True),
                    ],
                },
                {
                    "enunciado": "Por que CONTAS SOB GESTÃO é comparada com a meta cheia mesmo no meio do mês?",
                    "alternativas": [
                        ("Porque é o indicador principal do EC", False),
                        ("Porque é posição: a carteira de hoje, não uma soma", True),
                        ("Porque a gestão cadastra só a meta anual", False),
                        ("Porque taxa não acumula", False),
                    ],
                },
                {
                    "enunciado": "Seu funil mostra poucas reuniões por parceiro. O que a aula manda fazer?",
                    "alternativas": [
                        ("Começar a semana pelo Sem contato em Parceiros e revisar o 02 · Roteiro do EC", True),
                        ("Pedir indicação concreta no fim de toda reunião", False),
                        ("Conferir se você está nos Envolvidos das oportunidades", False),
                        ("Acompanhar as indicações com o EV", False),
                    ],
                },
            ],
        },
    ],
}


TRILHAS_HIPO: list[dict] = [HIPO_SDR, HIPO_EV, HIPO_EC]
