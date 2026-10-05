"""
HIPO — UC: pilar Energia, "Energia 01 · Rotina, volume e metas".

Pedido do Tulio (05/10/2026): material do pilar Energia, primeiro em PDF.
Decisões dele:
  * um material só, com base comum e um capítulo de rotina e volume por
    função (SDR, EV, EC);
  * números de volume pela CONTA REVERSA, com exemplo ilustrativo marcado
    como exemplo: os números reais de meta e de taxa vêm da gestão;
  * temas: rotina, volume, gestão do tempo, metas, resiliência e rejeição,
    foco e energia física, autogestão pelo HIPO e ritual do time.

A spec da UC define a Energia como "o esforço necessário para bater a
meta" (rotina, volume de atividade, disciplina, gestão do tempo), medida
pelo atingimento das metas individuais do mês.

O Tulio revisou o PDF e pediu para criar no HIPO (05/10/2026). O mesmo
PDF vai anexado à aula 1 como material de apoio (PDFS["energia"]).
"""
from __future__ import annotations

from uuid import UUID


def _id(sufixo: str) -> UUID:
    return UUID(f"7c1d0f4e-5a01-4c0e-9b11-0000000{sufixo}")


ENERGIA_01 = {
    "id": _id("c0100"),
    "titulo": "Energia 01 · Rotina, volume e metas",
    "pilar": "energia",
    "reforca": "metas",
    "descricao": (
        "O esforço que bate a meta: a conta reversa da meta até a atividade "
        "do dia, a rotina de cada função, gestão do tempo, foco e energia, "
        "como lidar com o \"não\", como se acompanhar pelo HIPO e os rituais "
        "do time. Energia não é trabalhar mais horas: é fazer a atividade "
        "certa, no volume certo, todo dia."
    ),
    "prazo_dias": 60,
    "obrigatorios": ("SDR", "EV", "EC"),
    "opcionais": ("EP", "ADM", "Franqueado"),
    "aulas": [
        {
            "id": _id("c0111"),
            "titulo": "O que é o pilar Energia",
            "resumo": "Técnica é saber, Método é fazer do jeito certo, Energia é fazer o suficiente. Por que constância vence pico, e como a Energia é medida.",
            "duracao_min": 6,
            "pdf": "energia",
            "conteudo_md": """\
## Os três pilares

- **Técnica** é o que você sabe: normas, produto, técnicas de venda.
- **Método** é o jeito certo de fazer: o roteiro, o registro, a regra da próxima tarefa.
- **Energia** é fazer **o suficiente**, **todo dia**, para a meta acontecer.

Quem tem Técnica e Método sem Energia faz poucas reuniões excelentes e não bate a meta. Quem tem Energia sem Método faz muito barulho e pouca venda. A meta sai dos três juntos.

## Energia não é hora extra

Energia não é ficar até mais tarde nem parecer ocupado. É:

- **Volume certo**: a quantidade de atividade que a sua meta exige, calculada (aula 2).
- **Ritmo certo**: distribuído pelos dias úteis, sem deixar para a última semana.
- **Atividade certa**: a que move o funil (contato, reunião, proposta, indicação), não a que só ocupa a agenda.

## Constância vence pico

Um mês de vendas não é ganho na última semana. Funil é cano: o que você planta na semana 1 vira reunião na semana 2 e contrato na semana 4. Quem para de prospectar quando está fechando vive de mês bom e mês ruim, alternados.

A regra prática: **todo dia útil tem um mínimo de atividade que não se negocia**, mesmo no dia ruim. Ela está na aula 3, para cada função.

## Como a Energia é medida

Pelo **atingimento das suas metas do mês**, com os números que já estão no HIPO. Ninguém preenche formulário: o que você lança (tarefa concluída, reunião com desfecho, oportunidade na fase certa) é o que conta.

Por isso Energia e Método andam juntos: atividade que não é registrada não existe para a medida.

> A meta não é um número que aparece no fim do mês. É uma conta que você faz no primeiro dia e acompanha todo dia.
""",
            "quiz": [
                {
                    "enunciado": "O que o pilar Energia mede?",
                    "alternativas": [
                        ("Horas trabalhadas", False),
                        ("O atingimento das metas do mês, com o que está registrado no HIPO", True),
                        ("A nota do quiz", False),
                        ("A opinião do gestor", False),
                    ],
                },
                {
                    "enunciado": "Por que constância vence pico?",
                    "alternativas": [
                        ("Porque o funil leva semanas: o que se planta hoje vira contrato depois", True),
                        ("Porque o gestor prefere", False),
                        ("Porque pico cansa o cliente", False),
                        ("Não vence, o que importa é a última semana", False),
                    ],
                },
                {
                    "enunciado": "Atividade feita e não registrada no HIPO conta para a meta?",
                    "alternativas": [
                        ("Sim, se o gestor souber", False),
                        ("Não: para a medida, o que não está registrado não existe", True),
                        ("Só se for venda", False),
                        ("Conta pela metade", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, o que acontece com quem tem Energia, mas não tem Método?",
                    "alternativas": [
                        ("Faz poucas reuniões excelentes e não bate a meta", False),
                        ("Bate a meta, mas só na última semana", False),
                        ("Vende bem, mas não consegue repetir no mês seguinte", False),
                        ("Faz muito barulho e pouca venda", True),
                    ],
                },
                {
                    "enunciado": "O que define o pilar Técnica?",
                    "alternativas": [
                        ("O jeito certo de fazer: roteiro e registro", False),
                        ("Fazer o suficiente, todo dia, para a meta", False),
                        ("O que você sabe: normas, produto e técnicas de venda", True),
                        ("As horas dedicadas ao trabalho no mês", False),
                    ],
                },
                {
                    "enunciado": "Qual destas é \"atividade certa\" para o pilar Energia?",
                    "alternativas": [
                        ("Reorganizar a agenda várias vezes ao dia", False),
                        ("Contato, reunião, proposta ou indicação que move o funil", True),
                        ("Responder toda mensagem no instante em que chega", False),
                        ("Ficar no escritório até mais tarde", False),
                    ],
                },
                {
                    "enunciado": "O que a aula chama de \"ritmo certo\"?",
                    "alternativas": [
                        ("Esforço concentrado na última semana do mês", False),
                        ("Mais horas nos dias em que você está disposto", False),
                        ("Atividade distribuída pelos dias úteis, sem deixar para a última semana", True),
                        ("O mesmo ritmo do colega com melhor resultado", False),
                    ],
                },
            ],
        },
        {
            "id": _id("c0112"),
            "titulo": "A conta reversa: da meta à atividade do dia",
            "resumo": "Como transformar a meta do mês em atividade por dia útil, usando as taxas do funil, com um exemplo para SDR, EV e EC.",
            "duracao_min": 10,
            "conteudo_md": """\
## A ideia

A meta está no fim do funil (contratos, agendamentos, indicações). O que você controla está no começo (contatos, reuniões, propostas). A conta reversa sobe o funil, etapa por etapa, dividindo pela taxa de cada passagem, até chegar no que você precisa fazer **por dia**.

**Atividade necessária = resultado desejado ÷ taxa de conversão da etapa.**

Repita etapa por etapa e divida o total pelos dias úteis do mês.

## Onde estão as suas taxas

Use as **suas** taxas dos últimos 2 ou 3 meses, não as de outra pessoa. Elas estão no HIPO:

- **Agenda › Produtividade**: agendamentos, realizadas, canceladas e no-show (taxa de realização e de no-show).
- **Oportunidades** e **Relatórios**: quantas propostas viraram contrato, quantas reuniões viraram proposta.
- **Tarefas › Realizadas no mês**: quantos toques você deu, por tipo.

Sem histórico (pessoa nova)? Use as taxas do time, que a gestão informa, e troque pelas suas depois de 60 dias.

> **Atenção:** os números abaixo são um **exemplo ilustrativo** para ensinar a conta. Não são meta nem taxa oficial. As suas metas e taxas reais vêm da gestão e do seu histórico no HIPO.

## Exemplo: EV

- Meta do mês: **6 contratos**.
- Se 1 em cada 3 propostas apresentadas fecha (33%): 6 ÷ 0,33 = **18 propostas**.
- Se 6 em cada 10 reuniões realizadas viram proposta (60%): 18 ÷ 0,6 = **30 reuniões realizadas**.
- Se 2 em cada 10 reuniões agendadas não acontecem (no-show de 20%): 30 ÷ 0,8 = **38 reuniões agendadas**.
- Com 20 dias úteis: **1 a 2 reuniões realizadas por dia** (30 no mês) e **quase 1 proposta por dia** (18 no mês).

## Exemplo: SDR

- Meta do mês: **38 reuniões agendadas** (o que o EV do exemplo precisa).
- Se 1 em cada 8 conversas com decisor vira reunião (12,5%): 38 ÷ 0,125 = **304 conversas com decisor**.
- Se 1 em cada 4 tentativas chega ao decisor (25%): 304 ÷ 0,25 = **1.216 tentativas** (ligações, WhatsApp e e-mails).
- Com 20 dias úteis: **cerca de 60 tentativas e 15 conversas com decisor por dia**.

## Exemplo: EC

- Meta do mês: **8 indicações** que viram oportunidade.
- Se um parceiro ativo indica, em média, 1 vez a cada 2 meses (0,5 por mês): 8 ÷ 0,5 = **16 parceiros ativos**.
- Ativo exige contato toda semana: **16 contatos de carteira por semana**, mais as reativações de quem está esfriando.
- Se 1 em cada 4 escritórios novos vira parceiro ativo: para ganhar 2 parceiros no mês, **8 reuniões de parceria**.

## Use o resultado

A conta vira o seu **mínimo diário**, a atividade que não se negocia (aula 3). Se a taxa de alguma etapa estiver ruim, a conta mostra onde: com taxa baixa de proposta para contrato, mais volume não resolve; o problema é Método (roteiro, objeções, fechamento).

> Volume corrige falta de oportunidade. Método corrige taxa ruim. A conta reversa mostra qual dos dois é o seu caso.
""",
            "quiz": [
                {
                    "enunciado": "Qual é a fórmula da conta reversa em cada etapa?",
                    "alternativas": [
                        ("Resultado × taxa de conversão", False),
                        ("Resultado desejado ÷ taxa de conversão da etapa", True),
                        ("Meta ÷ número de vendedores", False),
                        ("Meta + 20%", False),
                    ],
                },
                {
                    "enunciado": "Meta de 10 contratos e 1 em cada 2 propostas fecha. Quantas propostas são necessárias?",
                    "alternativas": [
                        ("5", False),
                        ("10", False),
                        ("20", True),
                        ("50", False),
                    ],
                },
                {
                    "enunciado": "Seu volume está certo, mas poucas propostas viram contrato. O que a conta reversa indica?",
                    "alternativas": [
                        ("Aumentar o volume de ligações", False),
                        ("O problema é de Método (roteiro, objeções, fechamento), não de volume", True),
                        ("Baixar a meta", False),
                        ("Nada, é azar", False),
                    ],
                },
                {
                    "enunciado": "No exemplo ilustrativo da aula (EV), são 18 propostas e 60% das reuniões realizadas viram proposta. Quantas reuniões realizadas?",
                    "alternativas": [
                        ("11", False),
                        ("18", False),
                        ("30", True),
                        ("38", False),
                    ],
                },
                {
                    "enunciado": "Pessoa nova, sem histórico no HIPO. Quais taxas usar na conta reversa?",
                    "alternativas": [
                        ("As do melhor vendedor do time, para mirar alto", False),
                        ("As do time, informadas pela gestão, trocadas pelas suas depois de 60 dias", True),
                        ("50% em todas as etapas, até ter histórico", False),
                        ("Nenhuma: só fazer a conta depois de três meses", False),
                    ],
                },
                {
                    "enunciado": "Onde, no HIPO, você vê suas reuniões realizadas, canceladas e no-show?",
                    "alternativas": [
                        ("Tarefas › Realizadas no mês", False),
                        ("Contas › Dados públicos", False),
                        ("Agenda › Produtividade", True),
                        ("Perfil", False),
                    ],
                },
                {
                    "enunciado": "No exemplo ilustrativo da aula (EC), a meta é 8 indicações e cada parceiro ativo indica 0,5 por mês. Quantos parceiros ativos?",
                    "alternativas": [
                        ("16", True),
                        ("4", False),
                        ("8", False),
                        ("32", False),
                    ],
                },
            ],
        },
        {
            "id": _id("c0113"),
            "titulo": "A rotina de cada função",
            "resumo": "O dia ideal do SDR, do EV e do EC em blocos, e o mínimo diário que não se negocia nem no dia ruim.",
            "duracao_min": 10,
            "conteudo_md": """\
## Por que blocos

O dia comercial sem estrutura é engolido pelo que chega: WhatsApp, pedido interno, a tarefa mais fácil. Blocos fixos protegem a atividade que move a meta. Os horários abaixo são uma referência; ajuste com a gestão à sua agenda, mas mantenha a ordem e o tamanho dos blocos.

## SDR

- **8h00 · Planejar (15 min).** Tarefas: zerar a leitura de Atrasadas e Para hoje. Separar a lista de ligações do bloco.
- **8h15 · Bloco de ligações (até 11h30).** Celular no silencioso, sem e-mail. As ligações da cadência primeiro.
- **11h30 · Escritos.** WhatsApp e e-mails da cadência, em lote.
- **13h00 · Pesquisa e prospecção.** Pesquisa de três minutos das próximas empresas; puxar da base se a fila estiver curta.
- **14h00 · Segundo bloco de ligações (até 16h30).** Quem não atendeu de manhã, agora em outro horário.
- **16h30 · Fechamento do dia.** Registrar tudo, bastão das reuniões marcadas, confirmações da véspera, nenhuma tarefa atrasada sem motivo.

**Mínimo diário do SDR:** o número de tentativas e de conversas com decisor da sua conta reversa, e nenhuma reunião de amanhã sem confirmação.

## EV

- **8h00 · Planejar.** Agenda do dia e Tarefas. Preparar as reuniões (15 minutos cada, três hipóteses de dor).
- **Reuniões** onde a agenda mandar. Entre uma e outra: o **registro em até 2 horas** (dores, GPCT, próximo passo) e o desfecho.
- **Bloco de propostas (1 a 2 horas).** Proposta em até 48h depois da reunião, sempre com a apresentação marcada.
- **Bloco de follow-up.** A cadência (D+2 a D+21) das propostas em aberto.
- **Fechamento do dia.** Nenhuma reunião sem desfecho, nenhuma oportunidade sem próxima tarefa.

**Mínimo diário do EV:** todas as reuniões do dia com desfecho registrado, as propostas no prazo de 48h e o follow-up do dia feito.

## EC

- **Segunda, 8h00 · Planejar a semana pelo farol.** Parceiros › EC responsável = você › Sem contato. Cada um vira tarefa da semana.
- **Manhã · Contatos de carteira.** Ligações e WhatsApp com algo útil para o parceiro, e o pedido no final.
- **Tarde · Reuniões e visitas.** Reuniões de parceria com escritórios novos e reuniões de carteira.
- **Devolutivas no mesmo dia** em que a indicação anda (reunião marcada, proposta, fechamento).
- **Sexta à tarde · Conferir o farol.** Todos os parceiros ativos com a semana verde.

**Mínimo diário do EC:** os contatos de carteira da conta reversa e nenhuma indicação sem devolutiva.

## O mínimo que não se negocia

Todo mundo tem dia ruim, reunião que cai, imprevisto. Nesses dias, o plano encolhe para o **mínimo diário**, mas o mínimo acontece. É ele que mantém o funil cheio para o mês que vem.

> Planeje o dia antes de abrir o WhatsApp. Quem abre o WhatsApp primeiro trabalha na agenda dos outros.
""",
            "quiz": [
                {
                    "enunciado": "Por que organizar o dia em blocos?",
                    "alternativas": [
                        ("Para parecer organizado", False),
                        ("Para proteger a atividade que move a meta do que chega a toda hora", True),
                        ("Porque o HIPO exige", False),
                        ("Para trabalhar menos", False),
                    ],
                },
                {
                    "enunciado": "Qual é o mínimo diário do EV?",
                    "alternativas": [
                        ("Responder todos os WhatsApps", False),
                        ("Reuniões do dia com desfecho, propostas no prazo de 48h e follow-up do dia feito", True),
                        ("Uma venda por dia", False),
                        ("Atualizar o Perfil", False),
                    ],
                },
                {
                    "enunciado": "Num dia ruim, o que fazer com o plano?",
                    "alternativas": [
                        ("Abandonar e recomeçar amanhã", False),
                        ("Encolher para o mínimo diário, mas cumprir o mínimo", True),
                        ("Dobrar a meta do dia seguinte sem fazer nada hoje", False),
                        ("Pedir para o colega fazer", False),
                    ],
                },
                {
                    "enunciado": "Pela rotina da aula, como começa o dia do SDR às 8h?",
                    "alternativas": [
                        ("Respondendo o WhatsApp acumulado da noite", False),
                        ("Planejando por 15 minutos: Atrasadas, Para hoje e a lista de ligações", True),
                        ("Pesquisando as empresas que vai puxar da base", False),
                        ("Confirmando as reuniões do dia seguinte", False),
                    ],
                },
                {
                    "enunciado": "É 14h na rotina de referência do SDR. O que ele faz?",
                    "alternativas": [
                        ("WhatsApp e e-mails da cadência, em lote", False),
                        ("Segundo bloco de ligações, com quem não atendeu de manhã", True),
                        ("Pesquisa e prospecção de novas empresas", False),
                        ("Fechamento do dia e confirmações da véspera", False),
                    ],
                },
                {
                    "enunciado": "Uma reunião do EV acabou. Em quanto tempo ela deve estar registrada?",
                    "alternativas": [
                        ("Até o fim da semana, na revisão de sexta", False),
                        ("Em até 2 horas, com dores, GPCT e próximo passo", True),
                        ("Só no fechamento do dia, junto com as demais", False),
                        ("Em até 48 horas, junto com a proposta", False),
                    ],
                },
                {
                    "enunciado": "Qual é o mínimo diário do EC?",
                    "alternativas": [
                        ("Uma reunião de parceria com escritório novo por dia", False),
                        ("Uma indicação nova registrada por dia", False),
                        ("Uma visita presencial a escritório por dia", False),
                        ("Os contatos de carteira da conta reversa e nenhuma indicação sem devolutiva", True),
                    ],
                },
            ],
        },
        {
            "id": _id("c0114"),
            "titulo": "Gestão do tempo",
            "resumo": "As ferramentas que mais rendem no comercial: a tarefa difícil primeiro, lotes, a agenda como contrato e o que fazer com as interrupções.",
            "duracao_min": 8,
            "conteudo_md": """\
## A tarefa difícil primeiro

A ligação que você está adiando, o follow-up chato, a proposta complicada: faça primeiro, no começo do bloco. A energia da manhã é a mais alta do dia, e a tarefa difícil adiada pesa a tarde inteira.

## Trabalhe em lotes

Trocar de tipo de tarefa custa tempo e atenção. Junte as parecidas:

- **Ligações** num bloco, uma atrás da outra, com a lista pronta.
- **WhatsApp e e-mail** em dois ou três momentos do dia, não o tempo todo.
- **Registro no HIPO** logo depois de cada conversa (é parte da conversa, não tarefa à parte).

## A agenda é um contrato

O que tem hora marcada acontece; o que fica na lista, nem sempre. Marque na agenda os blocos que importam (ligações, propostas, follow-up), não só as reuniões. No HIPO, tarefa com prazo e hora é compromisso: se o prazo mudou, edite o prazo; não deixe vencer.

## Interrupções

- **Pedido interno** que não é urgente: anote e responda no bloco de escritos.
- **Cliente** é sempre prioridade, mas "prioridade" é responder no dia, não largar o bloco de ligações a cada mensagem.
- **Notificações** desligadas durante os blocos de ligação e de proposta.

## Revisão de 10 minutos

No fim do dia, 10 minutos: o que ficou para trás, o que entra amanhã, qual é a tarefa difícil de amanhã. O dia seguinte começa decidido.

> Tempo não se administra: se escolhe. Cada "sim" a uma interrupção é um "não" a um bloco que move a meta.
""",
            "quiz": [
                {
                    "enunciado": "Por que fazer a tarefa difícil primeiro?",
                    "alternativas": [
                        ("Porque a energia da manhã é a mais alta e a tarefa adiada pesa o dia todo", True),
                        ("Porque o gestor confere de manhã", False),
                        ("Porque as fáceis não importam", False),
                        ("Não é recomendado", False),
                    ],
                },
                {
                    "enunciado": "O que é trabalhar em lotes?",
                    "alternativas": [
                        ("Fazer tudo ao mesmo tempo", False),
                        ("Juntar tarefas parecidas (ligações, mensagens) em blocos", True),
                        ("Deixar tudo para sexta", False),
                        ("Delegar", False),
                    ],
                },
                {
                    "enunciado": "Uma tarefa no HIPO vai vencer porque o combinado mudou. O que fazer?",
                    "alternativas": [
                        ("Deixar vencer", False),
                        ("Editar o prazo", True),
                        ("Cancelar sem motivo", False),
                        ("Concluir sem fazer", False),
                    ],
                },
                {
                    "enunciado": "Um colega faz um pedido interno não urgente no meio do seu bloco de ligações. O que fazer?",
                    "alternativas": [
                        ("Parar o bloco e resolver na hora", False),
                        ("Deixar para responder no fim da semana", False),
                        ("Pedir ao gestor que responda por você", False),
                        ("Anotar e responder no bloco de escritos", True),
                    ],
                },
                {
                    "enunciado": "Um cliente manda mensagem durante o bloco de ligações. O que a aula orienta?",
                    "alternativas": [
                        ("Largar o bloco e responder no mesmo minuto", False),
                        ("Responder só no dia seguinte, no bloco de escritos", False),
                        ("Cliente é prioridade, mas prioridade é responder no dia, sem largar o bloco", True),
                        ("Ignorar mensagens de cliente durante o expediente", False),
                    ],
                },
                {
                    "enunciado": "Quando fazer o registro de uma conversa no HIPO?",
                    "alternativas": [
                        ("No fim do dia, todas de uma vez", False),
                        ("Logo depois de cada conversa, como parte dela", True),
                        ("Na revisão semanal de sexta-feira", False),
                        ("Quando o gestor pedir o relatório", False),
                    ],
                },
                {
                    "enunciado": "O que fazer na revisão de 10 minutos no fim do dia?",
                    "alternativas": [
                        ("Responder as mensagens que acumularam no dia", False),
                        ("Conferir o resultado dos colegas no Monitor", False),
                        ("Ver o que ficou para trás, o que entra amanhã e a tarefa difícil de amanhã", True),
                        ("Planejar a semana inteira pelo farol", False),
                    ],
                },
            ],
        },
        {
            "id": _id("c0115"),
            "titulo": "Foco e energia física",
            "resumo": "Ciclos de foco com pausa, o corpo na ligação e os hábitos básicos que sustentam um dia inteiro de conversas.",
            "duracao_min": 7,
            "conteudo_md": """\
## Foco em ciclos

Ninguém mantém atenção alta por quatro horas seguidas. Trabalhe em ciclos:

- **50 minutos de foco** numa coisa só (ligações, proposta).
- **10 minutos de pausa** de verdade: levantar, andar, beber água, olhar longe da tela.

A pausa não é tempo perdido: é o que mantém a qualidade da 40ª ligação igual à da primeira.

## O corpo na ligação

O cliente não vê você, mas ouve.

- **Fale de pé** ou com a postura ereta: a voz sai mais firme.
- **Sorria ao falar**: muda o tom, e o cliente percebe.
- Fone de ouvido bom e lugar sem barulho de fundo.
- Água por perto. A voz cansa.

## Os básicos que sustentam o dia

Nada aqui é novidade, e por isso mesmo é o que mais se esquece:

- **Sono** regular: o dia de 60 ligações começa na noite anterior.
- **Comer** em horário: fome e queda de energia aparecem na voz e na paciência.
- **Movimento**: a pausa de 10 minutos é para levantar.
- **Celular pessoal** longe durante os blocos.

## Quando a energia cai

Todo mundo tem tarde lenta. Em vez de forçar a tarefa difícil, troque para uma de energia menor e ainda útil: registrar no HIPO, pesquisar as empresas de amanhã, organizar a fila. Volte ao bloco forte depois da pausa.

> Energia é recurso: se gasta e se recupera. Quem não pausa não fica mais produtivo; fica mais lento sem perceber.
""",
            "quiz": [
                {
                    "enunciado": "Qual é o ciclo de foco sugerido?",
                    "alternativas": [
                        ("4 horas seguidas", False),
                        ("50 minutos de foco e 10 de pausa de verdade", True),
                        ("10 minutos de foco e 50 de pausa", False),
                        ("Sem pausa até o almoço", False),
                    ],
                },
                {
                    "enunciado": "Por que falar de pé ou com postura ereta na ligação?",
                    "alternativas": [
                        ("O cliente vê pela câmera", False),
                        ("A voz sai mais firme, e o cliente percebe", True),
                        ("É regra da empresa", False),
                        ("Para cansar menos as pernas", False),
                    ],
                },
                {
                    "enunciado": "A energia caiu à tarde. O que fazer?",
                    "alternativas": [
                        ("Forçar a tarefa mais difícil", False),
                        ("Trocar para uma tarefa útil de energia menor e voltar ao bloco forte depois da pausa", True),
                        ("Ir embora mais cedo", False),
                        ("Ficar no celular até passar", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, para que serve a pausa de 10 minutos a cada ciclo?",
                    "alternativas": [
                        ("Manter a qualidade da 40ª ligação igual à da primeira", True),
                        ("Compensar as horas extras do dia anterior", False),
                        ("Colocar em dia as mensagens do celular pessoal", False),
                        ("Adiantar a proposta que ficou pendente", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, onde começa o dia de 60 ligações?",
                    "alternativas": [
                        ("No café da manhã reforçado", False),
                        ("Na noite anterior, com sono regular", True),
                        ("No bloco de planejamento das 8h", False),
                        ("Na diária do time", False),
                    ],
                },
                {
                    "enunciado": "Onde deve ficar o celular pessoal durante os blocos?",
                    "alternativas": [
                        ("Longe", True),
                        ("No silencioso, sobre a mesa", False),
                        ("Ao lado, para responder rápido", False),
                        ("Na mão, entre uma ligação e outra", False),
                    ],
                },
                {
                    "enunciado": "O que a aula recomenda sobre o ambiente da ligação?",
                    "alternativas": [
                        ("Viva-voz, para ficar com as mãos livres", False),
                        ("Ligar de onde estiver, até na rua", False),
                        ("Fone de ouvido bom e lugar sem barulho de fundo", True),
                        ("Música de fundo para manter o ritmo", False),
                    ],
                },
            ],
        },
        {
            "id": _id("c0116"),
            "titulo": "Resiliência: o \"não\" faz parte da conta",
            "resumo": "Por que a rejeição é estatística, como separar a pessoa do resultado, a rotina de 60 segundos depois de um \"não\" e o que fazer na semana ruim.",
            "duracao_min": 8,
            "conteudo_md": """\
## O \"não\" é estatística

Volte à conta reversa: se 1 em cada 8 conversas vira reunião, as outras 7 são "não" ou "agora não". Elas não são fracasso: **são o caminho para a oitava**. Cada "não" registrado é um passo dado na conta do mês.

## Separe a pessoa do resultado

O cliente diz "não" para a proposta, para o momento, para a ligação no meio de um dia ruim dele. Não para você. Quem leva o "não" para o pessoal liga menos na hora seguinte, e a conta não fecha.

## A rotina de 60 segundos

Depois de um "não" duro:

1. **Respire** fundo, uma vez.
2. **Registre** no HIPO o que aconteceu, em uma linha.
3. **Anote um aprendizado**, se houver: uma objeção nova, uma fala que não funcionou.
4. **Próxima ligação** em até 60 segundos.

Esperar "o ânimo voltar" faz o bloco acabar sem ligações.

## Celebre o que você controla

Você não controla se o cliente fecha. Controla o volume, a qualidade da conversa e o registro. Comemore o dia em que o mínimo foi cumprido, a conversa difícil bem conduzida, a objeção tratada com LAER, não só a venda.

## A semana ruim

Toda carreira comercial tem semanas ruins. O que fazer:

- **Volte ao mínimo diário.** Ele é a âncora.
- **Olhe a conta**, não o sentimento: o problema é volume ou taxa?
- **Leia uma transcrição boa** sua ou do time: lembre como é quando dá certo.
- **Peça ajuda cedo** ao gestor: role-play de 15 minutos resolve mais que uma semana sozinho.

Se o cansaço ou o desânimo durarem muito além de uma semana ruim, converse com a gestão. Pedir ajuda é parte do trabalho, não sinal de fraqueza.

> Resiliência não é não sentir o "não". É fazer a próxima ligação mesmo assim.
""",
            "quiz": [
                {
                    "enunciado": "Se 1 em cada 8 conversas vira reunião, o que são as outras 7?",
                    "alternativas": [
                        ("Fracasso", False),
                        ("O caminho para a oitava: parte da conta", True),
                        ("Tempo perdido", False),
                        ("Culpa do cliente", False),
                    ],
                },
                {
                    "enunciado": "Qual é a rotina depois de um \"não\" duro?",
                    "alternativas": [
                        ("Esperar o ânimo voltar", False),
                        ("Respirar, registrar, anotar um aprendizado e ligar de novo em até 60 segundos", True),
                        ("Parar o bloco e ir tomar café", False),
                        ("Ligar de novo para o mesmo cliente", False),
                    ],
                },
                {
                    "enunciado": "Na semana ruim, qual é a âncora?",
                    "alternativas": [
                        ("O mínimo diário", True),
                        ("A meta do mês inteiro", False),
                        ("O resultado do colega", False),
                        ("Nenhuma", False),
                    ],
                },
                {
                    "enunciado": "Um cliente recusa de forma ríspida, no meio de um dia ruim dele. Como a aula orienta interpretar?",
                    "alternativas": [
                        ("Sinal de que a abordagem deve ser descartada", False),
                        ("Motivo para pausar o bloco até o ânimo voltar", False),
                        ("Prova de que a empresa não tem a dor", False),
                        ("O \"não\" é para a proposta ou o momento, não para você", True),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, o que você controla e deve celebrar?",
                    "alternativas": [
                        ("Se o cliente fecha ou não o contrato", False),
                        ("A taxa de conversão do time inteiro", False),
                        ("O volume, a qualidade da conversa e o registro", True),
                        ("O humor do cliente durante a ligação", False),
                    ],
                },
                {
                    "enunciado": "Semana ruim. Além de voltar ao mínimo diário, o que a aula recomenda olhar?",
                    "alternativas": [
                        ("A conta, não o sentimento: o problema é volume ou taxa?", True),
                        ("O resultado dos colegas, para comparar", False),
                        ("Só o fechamento do mês, para não desanimar", False),
                        ("As metas do mês anterior, para se consolar", False),
                    ],
                },
                {
                    "enunciado": "Na semana ruim, que ajuda do gestor a aula sugere pedir cedo?",
                    "alternativas": [
                        ("A redução da meta do mês", False),
                        ("Um role-play de 15 minutos", True),
                        ("Que ele assuma suas ligações", False),
                        ("A troca da sua carteira", False),
                    ],
                },
            ],
        },
        {
            "id": _id("c0117"),
            "titulo": "Autogestão pelo HIPO",
            "resumo": "O que olhar todo dia, toda semana e todo mês para saber se você está no ritmo, e como corrigir a rota antes do fim do mês.",
            "duracao_min": 8,
            "conteudo_md": """\
## Você é o primeiro gestor dos seus números

A gestão olha o time; você olha você, antes, e todo dia. Tudo o que precisa está no HIPO.

## Todo dia (5 minutos)

- **Tarefas**: a coluna **Atrasadas** zerada no fim do dia, ou com motivo.
- **Realizadas no mês**: quantas atividades você já fez. Compare com a conta reversa.
- **Agenda**: nenhuma reunião sem desfecho (borda tracejada é pendência).

## Toda semana (15 minutos, sexta à tarde)

- **Monitor**: cada quadro mostra o resultado contra a **meta de hoje**, proporcional aos dias úteis que já passaram. Carinha triste no meio do mês ainda é recuperável; no fim, não.
- **Agenda › Produtividade**: suas reuniões realizadas, canceladas e no-show da semana.
- **EC**: o farol de todos os parceiros ativos verde.
- Pergunta da sexta: **estou no ritmo da conta reversa?**

## Todo mês

- No primeiro dia útil: refaça a conta reversa com a meta nova e as suas taxas atualizadas.
- No fechamento: o que funcionou, o que não funcionou, qual etapa do funil pede atenção no próximo mês.

## Corrigir a rota

Atrasado no meio do mês? Refaça a conta só com o que falta:

**Atividade por dia = (meta − realizado) ÷ taxa ÷ dias úteis que faltam.**

Se o número ficou impossível, fale com a gestão **no meio do mês**, não no último dia. No meio do mês ainda dá para mudar o plano; no fim, só dá para explicar.

> Quem só descobre o resultado no fim do mês não gere nada: só assiste.
""",
            "tour": [
                {"rota": "/crm/tarefas", "alvo": "tar-contadores", "titulo": "Todo dia: atrasadas e realizadas",
                 "texto": "**Atrasadas** zeradas no fim do dia; **Realizadas no mês** comparadas com a sua conta reversa."},
                {"rota": "/crm/agenda", "alvo": "age-kpis", "titulo": "Todo dia: desfecho",
                 "texto": "**Sem desfecho** precisa estar zerado. Reunião sem desfecho não conta para a meta."},
                {"rota": "/crm/agenda", "alvo": "age-produtividade", "titulo": "Toda semana: produtividade",
                 "texto": "Realizadas, canceladas e no-show da semana: as suas taxas para a conta reversa."},
                {"rota": "/monitor", "alvo": "mon-barra", "titulo": "Toda semana: o ritmo do mês",
                 "texto": "O **dia útil** em que estamos e quanto do mês já passou. A meta de hoje acompanha esse ritmo."},
                {"rota": "/monitor", "alvo": "mon-quadros", "titulo": "Resultado contra a meta de hoje",
                 "texto": "Carinha triste no meio do mês ainda dá para recuperar. Clique no quadro para ver o que compõe o número."},
            ],
            "quiz": [
                {
                    "enunciado": "No Monitor, a meta de hoje é:",
                    "alternativas": [
                        ("A meta do mês inteiro", False),
                        ("Proporcional aos dias úteis que já passaram", True),
                        ("Sempre zero até o dia 15", False),
                        ("A meta do mês anterior", False),
                    ],
                },
                {
                    "enunciado": "Faltam 10 dias úteis, 12 reuniões realizadas para a meta e 1 em cada 2 agendadas se realiza. Quantas agendar por dia?",
                    "alternativas": [
                        ("0,6", False),
                        ("1,2", False),
                        ("2,4", True),
                        ("12", False),
                    ],
                },
                {
                    "enunciado": "A conta ficou impossível no meio do mês. O que fazer?",
                    "alternativas": [
                        ("Esperar o fim do mês para explicar", False),
                        ("Falar com a gestão no meio do mês, enquanto dá para mudar o plano", True),
                        ("Parar de registrar", False),
                        ("Nada", False),
                    ],
                },
                {
                    "enunciado": "No controle diário de 5 minutos, o que conferir na Agenda?",
                    "alternativas": [
                        ("Se os colegas confirmaram as reuniões deles", False),
                        ("O ranking de reuniões do time no mês", False),
                        ("Nenhuma reunião sem desfecho; borda tracejada é pendência", True),
                        ("As reuniões marcadas para o mês seguinte", False),
                    ],
                },
                {
                    "enunciado": "Quando refazer a conta reversa, segundo a aula?",
                    "alternativas": [
                        ("Só quando a meta do mês não for batida", False),
                        ("No primeiro dia útil do mês, com a meta nova e as taxas atualizadas", True),
                        ("Uma vez por trimestre, junto com a gestão", False),
                        ("No último dia do mês, no fechamento", False),
                    ],
                },
                {
                    "enunciado": "O Monitor mostra carinha triste no meio do mês. O que isso significa?",
                    "alternativas": [
                        ("A meta do mês já está perdida", False),
                        ("Há um erro de registro no HIPO", False),
                        ("É hora de pedir redução de meta", False),
                        ("Ainda é recuperável", True),
                    ],
                },
                {
                    "enunciado": "Qual é a pergunta da revisão semanal de sexta à tarde?",
                    "alternativas": [
                        ("Quantas vendas os colegas fizeram?", False),
                        ("Qual parceiro indicou mais no ano?", False),
                        ("Quantas horas trabalhei na semana?", False),
                        ("Estou no ritmo da conta reversa?", True),
                    ],
                },
            ],
        },
        {
            "id": _id("c0118"),
            "titulo": "Os rituais do time",
            "resumo": "A reunião diária de 15 minutos, a semanal, como celebrar meta sem ranking e por que pedir ajuda cedo é energia, não fraqueza.",
            "duracao_min": 7,
            "conteudo_md": """\
## Por que ritual

Energia individual oscila; energia de time sustenta. Rituais curtos, sempre no mesmo horário, criam o compromisso público com o mínimo diário e fazem os problemas aparecerem cedo.

## A diária (15 minutos, em pé)

Cada um, em até 2 minutos, responde três perguntas com números:

1. **Ontem**: o que fiz, em números (tentativas, conversas, reuniões, propostas, contatos de carteira).
2. **Hoje**: meu mínimo do dia e a tarefa difícil.
3. **Trava**: o que está me impedindo, e de quem preciso.

A trava não se resolve na diária: quem pode ajudar fica depois, com quem precisa.

## A semanal (45 minutos)

- O funil da semana pelo Monitor: o que avançou, o que travou.
- **Trechos de transcrição**: um que funcionou e um que perdeu a venda (do roteiro de vendas).
- O tema de treino da semana: o item mais fraco do scorecard ou a objeção que mais apareceu.
- O plano da semana seguinte, com o mínimo diário de cada um.

## Celebrar sem ranking

Na Controller **não há ranking público**: cada um vê o próprio resultado; a gestão vê o time. Celebramos **conquista**, não posição:

- meta batida;
- a primeira reunião de um SDR novo;
- a primeira indicação de um parceiro;
- a objeção difícil bem tratada.

Ninguém é exposto pelo resultado do outro.

## Pedir ajuda cedo

Ajuda pedida na primeira semana vira ajuste; na última, vira justificativa. Pedir ajuda faz parte do pilar Energia: é a forma mais rápida de voltar ao ritmo.

> Time que se encontra todo dia por 15 minutos descobre os problemas em 24 horas. Time que se encontra no fim do mês descobre em 30 dias.
""",
            "quiz": [
                {
                    "enunciado": "Quais são as três perguntas da diária?",
                    "alternativas": [
                        ("Ontem em números, hoje (mínimo e tarefa difícil) e trava", True),
                        ("Nome, cargo e meta", False),
                        ("O que o colega fez, o que o gestor quer e o que falta", False),
                        ("Quantas vendas, qual o ranking e quem está atrás", False),
                    ],
                },
                {
                    "enunciado": "Como a Controller celebra resultado?",
                    "alternativas": [
                        ("Com ranking público", False),
                        ("Celebrando conquistas, sem ranking e sem expor ninguém", True),
                        ("Só com dinheiro", False),
                        ("Não celebra", False),
                    ],
                },
                {
                    "enunciado": "Por que pedir ajuda cedo?",
                    "alternativas": [
                        ("Ajuda na primeira semana vira ajuste; na última, vira justificativa", True),
                        ("Para dividir a meta", False),
                        ("Porque é obrigatório", False),
                        ("Não se deve pedir ajuda", False),
                    ],
                },
                {
                    "enunciado": "Na diária, alguém levanta uma trava. Como ela é tratada?",
                    "alternativas": [
                        ("O time inteiro discute até resolver", False),
                        ("Fica para a pauta da reunião semanal", False),
                        ("O gestor decide na hora, na frente de todos", False),
                        ("Não se resolve na diária: quem pode ajudar fica depois com quem precisa", True),
                    ],
                },
                {
                    "enunciado": "Como é o formato da diária?",
                    "alternativas": [
                        ("45 minutos, sentados, olhando o funil", False),
                        ("15 minutos, em pé, até 2 minutos por pessoa", True),
                        ("30 minutos, por mensagem no grupo", False),
                        ("15 minutos, em que só o gestor fala", False),
                    ],
                },
                {
                    "enunciado": "Qual destes itens faz parte da reunião semanal de 45 minutos?",
                    "alternativas": [
                        ("O ranking público de vendas do time", False),
                        ("A leitura das tarefas atrasadas de cada um", False),
                        ("Um trecho de transcrição que funcionou e um que perdeu a venda", True),
                        ("A revisão da meta anual da empresa", False),
                    ],
                },
                {
                    "enunciado": "Como é escolhido o tema de treino da semana?",
                    "alternativas": [
                        ("O serviço mais caro do catálogo", False),
                        ("O item mais fraco do scorecard ou a objeção que mais apareceu", True),
                        ("A norma mais recente publicada", False),
                        ("Um assunto sorteado entre o time", False),
                    ],
                },
            ],
        },
    ],
}


TRILHAS_ENERGIA: list[dict] = [ENERGIA_01]
