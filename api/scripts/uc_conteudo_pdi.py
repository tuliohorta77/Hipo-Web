"""
HIPO — UC: 05 · PDI: criar e seguir um bom plano (pilar Técnica).

  05 · PDI: criar e seguir um bom plano   obrigatória para SDR, EV, EC, EP e
                                          ADM (prazo 35 dias); Franqueado
                                          sem obrigação

Pedido do Tulio (05/10/2026): "crie um curso de como criar e seguir um bom
PDI". Decisões dele: para todos, com uma parte para a gestão; pilar
Técnica.

O texto descreve o PDI como ele está no HIPO desde a entrega 043
(routers/pdi.py, services/pdi.py): o HIPO sugere (Desempenho abaixo de 70%
da meta, os três piores, mês anterior até o 4º dia útil; trilha
obrigatória atrasada ou vencendo; quiz final reprovado 2+ vezes), a
gestão confirma ajustando, descarta ou cria, e o colaborador marca como
feita (e desfaz a própria). Ação ligada a trilha conclui sozinha. O que
não é regra do sistema aparece como BOA PRÁTICA, dito assim no texto.

Prazo de 35 dias: livre para todos os cargos (as obrigatórias de cada um
não podem empatar no prazo).

Este arquivo é só dado. Quem grava é scripts/semear_uc.py.
"""
from __future__ import annotations

from uuid import UUID

CARGOS_PDI = ("SDR", "EV", "EC", "EP", "ADM")


def _id(sufixo: str) -> UUID:
    return UUID(f"7c1d0f4e-5a01-4c0e-9b11-0000000{sufixo}")


def _passo(rota, alvo, titulo, texto, clicar=None):
    p = {"rota": rota, "alvo": alvo, "titulo": titulo, "texto": texto}
    if clicar:
        p["clicar"] = list(clicar)
    return p


AULA_1 = {
    "id": _id("b0811"),
    "titulo": "O que é o PDI e como ele funciona no HIPO",
    "resumo": "Plano de desenvolvimento individual: poucas ações, com objetivo, prazo e dono. Quem sugere, quem confirma e quem conclui.",
    "duracao_min": 8,
    "conteudo_md": """\
## Em uma frase

**PDI é o plano de desenvolvimento individual: as poucas ações que vão fazer você melhorar no próximo mês, cada uma com objetivo, o que fazer e prazo.** Não é avaliação, não é lista de desejos e não é castigo. É o combinado entre você e a gestão sobre o que treinar agora.

## Por que ter um PDI

- **Sem plano, o desenvolvimento fica no "vou melhorar".** Com plano, fica "até dia 20, confirmar toda reunião na véspera".
- **O seu número já diz onde está a oportunidade.** O PDI transforma o Desempenho e a Universidade em ação.
- **A conversa com a gestão fica objetiva.** Em vez de opinião, vocês olham a mesma tela.

## Onde fica

Em **Carreira**, na aba **PDI**, ao lado da Universidade e do Desempenho. Ela abre na **sua próxima ação**: a de prazo mais curto. Embaixo, quantas ações estão abertas, atrasadas e feitas no mês, e a lista das ações.

## Quem faz o quê

O PDI do HIPO é **misto**:

1. **O HIPO sugere.** Ele lê o seu Desempenho e a sua Universidade e propõe ações (a próxima aula explica de onde).
2. **A gestão monta.** Confirma a sugestão (ajustando o texto, a trilha e o prazo), descarta o que não faz sentido ou cria uma ação do zero.
3. **Você executa e marca como feita.** Se marcou por engano, você mesmo desfaz.

Você não edita o objetivo nem o prazo: isso se combina com a gestão. Se uma ação está difícil, a conversa vem **antes** do prazo vencer (aula 4).

## O que tem em cada ação

- **Objetivo:** o resultado que se quer, de preferência com número.
- **O que fazer:** o comportamento, no dia a dia.
- **Trilha de reforço (opcional):** uma trilha da Universidade ligada ao objetivo.
- **Prazo.**
- **Situação:** Em dia, Vence logo (até 3 dias), Atrasada, Feita ou Cancelada.

Ação ligada a uma trilha **se conclui sozinha** quando você termina a trilha (aulas e quiz final).

> O PDI não mede quem é bom. Ele diz o que treinar agora, e mostra que você treinou.
""",
    "tour": [
        _passo("/carreira", "nav-carreira", "Carreira",
               "Estudo e desenvolvimento num lugar só: Universidade, PDI e Desempenho."),
        _passo("/carreira", "carreira-abas", "A aba PDI",
               "O seu plano fica na aba **PDI**, entre a Universidade e o Desempenho."),
        _passo("/carreira/pdi", "pdi-proxima", "A sua próxima ação",
               "A aba abre na ação de **prazo mais curto**, com o botão **Feita**. Sem ação aberta, o cartão diz isso."),
        _passo("/carreira/pdi", "pdi-numeros", "O panorama",
               "Quantas ações estão **abertas**, **atrasadas** e **feitas no mês**."),
    ],
    "quiz": [
        {
            "enunciado": "O que é o PDI, segundo a aula?",
            "alternativas": [
                ("As poucas ações para melhorar no próximo mês, com objetivo, o que fazer e prazo", True),
                ("A avaliação de desempenho do ano", False),
                ("A lista de cursos que a pessoa gostaria de fazer", False),
                ("Uma advertência formal da gestão", False),
            ],
        },
        {
            "enunciado": "Onde fica o PDI no HIPO?",
            "alternativas": [
                ("Em Tarefas, na coluna Atrasadas", False),
                ("Em Carreira, na aba PDI", True),
                ("No Monitor da sala", False),
                ("Em Relatórios", False),
            ],
        },
        {
            "enunciado": "Quem confirma uma sugestão do HIPO e a transforma em ação?",
            "alternativas": [
                ("O próprio HIPO, automaticamente", False),
                ("O colaborador", False),
                ("A gestão", True),
                ("O EV responsável pela conta", False),
            ],
        },
        {
            "enunciado": "Você acha o prazo de uma ação curto demais. Pode mudar o prazo no HIPO?",
            "alternativas": [
                ("Sim, a qualquer momento", False),
                ("Sim, mas só uma vez", False),
                ("Não existe prazo no PDI", False),
                ("Não: prazo e objetivo se combinam com a gestão, antes de vencer", True),
            ],
        },
        {
            "enunciado": "Qual ação aparece no topo da aba PDI?",
            "alternativas": [
                ("A de prazo mais curto, entre as abertas", True),
                ("A mais antiga", False),
                ("A criada pela gestão por último", False),
                ("A já feita mais recente", False),
            ],
        },
        {
            "enunciado": "Você marcou uma ação como feita por engano. O que fazer?",
            "alternativas": [
                ("Pedir para apagar o PDI inteiro", False),
                ("Desfazer você mesmo: dá para desfazer o que você marcou", True),
                ("Criar uma ação nova igual", False),
                ("Nada: não tem como voltar", False),
            ],
        },
        {
            "enunciado": "Uma ação está ligada a uma trilha da Universidade. Quando ela se conclui sozinha?",
            "alternativas": [
                ("Quando você abre a primeira aula", False),
                ("No fim do mês, sempre", False),
                ("Quando você termina a trilha, com as aulas e o quiz final", True),
                ("Quando a gestão vê a trilha", False),
            ],
        },
    ],
}


AULA_2 = {
    "id": _id("b0812"),
    "titulo": "De onde vêm as ações: o Desempenho e a Universidade",
    "resumo": "Como o HIPO escolhe o que sugerir e como você mesmo antecipa a conversa olhando os seus números.",
    "duracao_min": 9,
    "conteudo_md": """\
## O HIPO olha dois lugares

O PDI não começa numa folha em branco. O HIPO sugere ações a partir do que já está no sistema, e você pode olhar os mesmos lugares antes da conversa.

## 1. O Desempenho

Na aba **Desempenho**, cada indicador do seu squad (SDR, EV ou EC) aparece contra a sua meta. O HIPO sugere uma ação para cada indicador **com meta** que está **abaixo de 70%**:

- No mês aberto, a comparação é com a **meta de hoje** (a parte da meta que já devia estar feita, pelos dias úteis). Taxas (como no-show) e posições (como Pipeline) comparam com a meta cheia.
- Entram **os três piores**. No empate, o indicador principal vem primeiro.
- **Até o 4º dia útil** o mês ainda não diz nada, e o HIPO olha o **mês anterior**, já fechado.
- A sugestão diz onde agir: Tarefas, Agenda, Oportunidades, Parceiros ou Prospecção, conforme o indicador.

Abaixo de 70% é a carinha triste (ou brava) do Monitor. Não é bronca: é o lugar onde uma ação dá mais resultado.

## 2. A Universidade

- **Trilha obrigatória atrasada ou vencendo:** o HIPO sugere "Concluir a trilha", já com a trilha ligada e prazo de uma semana.
- **Quiz final reprovado duas ou mais vezes**, sem aprovação: o HIPO sugere "Ser aprovado no quiz final", com as aulas que você errou na última tentativa.

## O que fica de fora

- Indicador **sem meta** não gera sugestão: sem meta, não há com o que comparar.
- Cargo sem squad (EP, ADM) recebe só as sugestões da Universidade e as ações que a gestão criar.
- Sugestão que a gestão **descartou** não volta naquele mês (Desempenho) nem para aquela trilha (Universidade).

## Como antecipar a conversa (boa prática)

Antes de falar com a gestão, faça você mesmo a leitura:

1. Abra o **Desempenho** e olhe o **ponto de atenção** (o indicador mais longe da meta).
2. Olhe o **funil**: onde ele afina?
3. Abra a **Universidade**: alguma trilha atrasada?
4. Escreva **uma frase** sobre o que você acha que trava o número.

Quem chega com essa leitura monta um PDI melhor do que quem só ouve.

> O HIPO sugere o que os números mostram. O que trava o número, quem sabe é você: leve isso para a conversa.
""",
    "tour": [
        _passo("/carreira/desempenho", "des-atencao", "O ponto de atenção",
               "O indicador mais longe da meta. Abaixo de 70%, vira sugestão de PDI."),
        _passo("/carreira/desempenho", "des-funil", "Onde o funil afina",
               "As taxas entre as etapas. É a melhor pista do que treinar."),
        _passo("/carreira", "uc-proxima", "A Universidade",
               "Trilha obrigatória atrasada ou vencendo também vira sugestão."),
    ],
    "quiz": [
        {
            "enunciado": "A partir de que atingimento um indicador vira sugestão de PDI?",
            "alternativas": [
                ("Abaixo de 100%", False),
                ("Abaixo de 70%", True),
                ("Abaixo de 50%", False),
                ("Qualquer um, mesmo acima da meta", False),
            ],
        },
        {
            "enunciado": "No mês aberto, o atingimento é comparado com o quê?",
            "alternativas": [
                ("Com a meta do mês inteiro", False),
                ("Com a média do time", False),
                ("Com a meta de hoje, pelos dias úteis já passados", True),
                ("Com o mês anterior", False),
            ],
        },
        {
            "enunciado": "Quantos indicadores do Desempenho o HIPO sugere, no máximo?",
            "alternativas": [
                ("Todos os que estiverem abaixo da meta", False),
                ("Um só", False),
                ("Cinco", False),
                ("Os três piores", True),
            ],
        },
        {
            "enunciado": "É o 3º dia útil do mês. Que mês o HIPO usa para sugerir?",
            "alternativas": [
                ("O mês anterior, já fechado", True),
                ("O mês corrente, mesmo começando", False),
                ("Nenhum: não sugere nada", False),
                ("A média dos últimos seis meses", False),
            ],
        },
        {
            "enunciado": "Um indicador está em zero, mas não tem meta cadastrada. Vira sugestão?",
            "alternativas": [
                ("Sim, sempre", False),
                ("Não: sem meta não há com o que comparar", True),
                ("Só se for o principal", False),
                ("Só no fim do mês", False),
            ],
        },
        {
            "enunciado": "O que gera sugestão a partir da Universidade?",
            "alternativas": [
                ("Abrir uma aula e não terminar no mesmo dia", False),
                ("Fazer uma trilha opcional", False),
                ("Trilha obrigatória atrasada ou vencendo, e quiz final reprovado 2+ vezes", True),
                ("Tirar menos de 100% no quiz", False),
            ],
        },
        {
            "enunciado": "Antes da conversa de PDI, qual é a boa prática da aula?",
            "alternativas": [
                ("Esperar a gestão dizer o que fazer", False),
                ("Pedir para descartar todas as sugestões", False),
                ("Comparar o seu número com o dos colegas", False),
                ("Olhar o ponto de atenção, o funil e as trilhas, e escrever o que trava o número", True),
            ],
        },
    ],
}


AULA_3 = {
    "id": _id("b0813"),
    "titulo": "Como escrever uma boa ação",
    "resumo": "Objetivo com número, o que fazer como comportamento, prazo realista e poucas ações de cada vez.",
    "duracao_min": 10,
    "conteudo_md": """\
## As quatro partes

Uma ação de PDI tem **objetivo**, **o que fazer**, **prazo** e, se ajudar, **trilha de reforço**. Cada uma tem um teste simples.

## 1. Objetivo: o resultado, com número

Teste: **dá para saber, no prazo, se aconteceu?**

- **Ruim:** "Melhorar a prospecção." (quando está melhor?)
- **Bom:** "Agendamentos: sair de 40% e chegar a 100% da meta de hoje até o fim do mês."
- **Bom:** "No-show abaixo da meta em outubro."

As sugestões do HIPO já vêm nesse formato ("NMRR: sair de 45% e chegar a 100% da meta"). Na hora de confirmar, a gestão pode reescrever com as palavras de vocês dois.

## 2. O que fazer: o comportamento, não a intenção

Teste: **outra pessoa conseguiria ver você fazendo?**

- **Ruim:** "Me dedicar mais." / "Ter mais foco."
- **Bom:** "Confirmar toda reunião por WhatsApp no dia útil anterior."
- **Bom:** "Começar o dia pela coluna Atrasadas e zerar até as 10h."
- **Bom:** "Fazer as aulas 3 e 4 do Roteiro do SDR e treinar o role-play com um colega."

Comportamento com **frequência** ("todo dia", "toda segunda") é o que vira hábito.

## 3. Prazo: curto e realista

- Ao criar a ação, o HIPO não aceita prazo no passado, e nunca aceita prazo acima de um ano.
- **Boa prática:** de duas a quatro semanas. Prazo longo demais vira "depois eu faço".
- Ação grande? Quebre em duas, com prazos em sequência.

## 4. Trilha de reforço: quando o problema é saber fazer

Se o que trava é **técnica** (não sabe como), ligue uma trilha: o Roteiro do SDR, as Técnicas do SDR na prática, o Roteiro do EV. Se o que trava é **rotina** (sabe, mas não faz), a trilha ajuda menos: o "o que fazer" é que resolve.

## Poucas ações (boa prática)

**Até três ações abertas ao mesmo tempo.** Com dez, nenhuma é prioridade. Terminou uma, entra a próxima.

## Certo e errado, lado a lado

- **Errado:** Objetivo "Ser um SDR melhor"; O que fazer "Estudar mais"; prazo em seis meses.
- **Certo:** Objetivo "Agendamentos na meta de hoje até 31/10"; O que fazer "Cadência completa em toda empresa puxada: seis toques, ligações alternando manhã e tarde"; Trilha "04 · Técnicas do SDR na prática"; prazo 31/10.

> Se não dá para saber se aconteceu, não é objetivo. Se ninguém consegue ver você fazendo, não é ação.
""",
    "quiz": [
        {
            "enunciado": "Qual é o teste de um bom objetivo?",
            "alternativas": [
                ("Ser inspirador", False),
                ("Dar para saber, no prazo, se aconteceu", True),
                ("Ter mais de uma frase", False),
                ("Ser igual ao de todo o time", False),
            ],
        },
        {
            "enunciado": "Qual destes é um bom \"o que fazer\"?",
            "alternativas": [
                ("\"Me dedicar mais.\"", False),
                ("\"Ter mais foco no trabalho.\"", False),
                ("\"Confirmar toda reunião por WhatsApp no dia útil anterior.\"", True),
                ("\"Melhorar a prospecção.\"", False),
            ],
        },
        {
            "enunciado": "Qual é o teste de um bom \"o que fazer\"?",
            "alternativas": [
                ("Outra pessoa conseguiria ver você fazendo", True),
                ("Cabe em uma palavra", False),
                ("Foi escrito pela gestão", False),
                ("Tem uma trilha ligada", False),
            ],
        },
        {
            "enunciado": "Qual prazo a aula recomenda como boa prática?",
            "alternativas": [
                ("Seis meses", False),
                ("Um ano", False),
                ("Sem prazo", False),
                ("De duas a quatro semanas", True),
            ],
        },
        {
            "enunciado": "Quando faz mais sentido ligar uma trilha de reforço à ação?",
            "alternativas": [
                ("Sempre, em toda ação", False),
                ("Quando o que trava é técnica: a pessoa não sabe como fazer", True),
                ("Quando o problema é falta de rotina", False),
                ("Nunca: trilha não tem a ver com PDI", False),
            ],
        },
        {
            "enunciado": "Quantas ações abertas ao mesmo tempo a aula recomenda?",
            "alternativas": [
                ("Até três", True),
                ("Dez ou mais", False),
                ("Uma por indicador do squad", False),
                ("Nenhuma: o PDI é só para fim de ano", False),
            ],
        },
        {
            "enunciado": "A ação é grande demais para o prazo. O que a aula sugere?",
            "alternativas": [
                ("Esticar o prazo para um ano", False),
                ("Deixar sem prazo", False),
                ("Quebrar em duas ações, com prazos em sequência", True),
                ("Cancelar e não fazer", False),
            ],
        },
    ],
}


AULA_4 = {
    "id": _id("b0814"),
    "titulo": "Seguir o PDI no dia a dia",
    "resumo": "Levar a ação para a agenda, marcar como feita quando o \"o que fazer\" aconteceu e avisar antes de atrasar.",
    "duracao_min": 9,
    "conteudo_md": """\
## O PDI que funciona é o que entra na semana

Ação de PDI que só vive na aba PDI é esquecida. A execução acontece nas telas onde você já trabalha: Tarefas, Agenda, Oportunidades, Universidade.

## Passo a passo

1. **Abra a aba PDI na segunda-feira** (boa prática). Leia a próxima ação e as abertas.
2. **Leve cada ação para a rotina.** "Confirmar na véspera" vira um bloco fixo no fim da tarde. "Fazer as aulas 3 e 4" vira um horário na agenda. Se a ação tem trilha, o botão **Abrir trilha** (na próxima ação) ou o nome da trilha (na lista) leva direto a ela.
3. **Faça o que está escrito**, não uma versão parecida.
4. **Marque como feita** quando o "o que fazer" aconteceu, no botão **Feita**.
5. **Guarde a evidência** para a conversa com a gestão: "Confirmei as 14 reuniões da semana, 1 no-show."

## Situações da ação

- **Em dia:** faltam mais de 3 dias.
- **Vence logo:** faltam até 3 dias.
- **Atrasada:** passou do prazo e ainda está aberta.
- **Feita** ou **Cancelada** (a gestão cancela quando a ação deixou de fazer sentido).

O número **Atrasadas**, logo abaixo da próxima ação, é o primeiro que a gestão olha.

## Quando não vai dar

O prazo e o objetivo são combinados, e só a gestão muda. Por isso:

- **Avise antes do prazo vencer**, não depois. "Vou precisar de mais uma semana porque..." é conversa; ação atrasada sem aviso é ruído.
- Leve o motivo concreto: faltou volume, a trilha é longa, mudou a prioridade do mês.
- Se a ação deixou de fazer sentido (a meta foi batida, o problema era outro), peça para **cancelar**: ação aberta que ninguém vai fazer só suja o painel.

## Marcou por engano?

Você desfaz o que você mesmo marcou. Ação que **se concluiu sozinha** pela trilha não tem o que desfazer: a trilha está feita.

## Erros comuns

- Marcar como feita porque "fez um pouco". Feita é quando o "o que fazer" aconteceu.
- Deixar todas para a última semana do prazo.
- Esperar a conversa mensal para dizer que uma ação travou.

> PDI se cumpre na agenda, não na aba PDI. A aba é onde você mostra que cumpriu.
""",
    "tour": [
        _passo("/carreira/pdi", "pdi-proxima", "Comece a semana aqui",
               "A próxima ação: objetivo, o que fazer, situação e prazo. **Abrir trilha** leva à trilha ligada; **Feita** conclui."),
        _passo("/carreira/pdi", "pdi-numeros", "Atrasadas",
               "É o primeiro número que a gestão olha. Avise antes de uma ação entrar aqui."),
        _passo("/carreira/pdi", "pdi-abertas", "Todas as abertas",
               "Por prazo. Cada uma com a situação e o botão **Feita**."),
    ],
    "quiz": [
        {
            "enunciado": "Onde a ação de PDI deve acontecer, segundo a aula?",
            "alternativas": [
                ("Só na aba PDI", False),
                ("Nas telas e na agenda em que você já trabalha", True),
                ("No fim do mês, de uma vez", False),
                ("Numa planilha separada", False),
            ],
        },
        {
            "enunciado": "Quando marcar uma ação como feita?",
            "alternativas": [
                ("Quando fez um pouco", False),
                ("Assim que a gestão criar a ação", False),
                ("Quando o \"o que fazer\" aconteceu", True),
                ("Só no último dia do prazo", False),
            ],
        },
        {
            "enunciado": "O que significa a situação \"Vence logo\"?",
            "alternativas": [
                ("Faltam até 3 dias para o prazo", True),
                ("Já passou do prazo", False),
                ("Faltam 30 dias", False),
                ("A ação foi cancelada", False),
            ],
        },
        {
            "enunciado": "Você percebe que não vai cumprir o prazo. O que fazer?",
            "alternativas": [
                ("Mudar o prazo você mesmo", False),
                ("Deixar atrasar e explicar na conversa do mês", False),
                ("Marcar como feita para não ficar atrasada", False),
                ("Avisar a gestão antes do prazo, com o motivo concreto", True),
            ],
        },
        {
            "enunciado": "A meta foi batida e a ação deixou de fazer sentido. O que fazer?",
            "alternativas": [
                ("Pedir à gestão para cancelar a ação", True),
                ("Deixar aberta para sempre", False),
                ("Marcar como feita sem ter feito", False),
                ("Criar outra igual", False),
            ],
        },
        {
            "enunciado": "Para que guardar a evidência do que foi feito?",
            "alternativas": [
                ("Para pedir aumento", False),
                ("Para mostrar à gestão, na conversa, o que aconteceu", True),
                ("Para mudar o prazo", False),
                ("Para avisar o cliente", False),
            ],
        },
        {
            "enunciado": "Uma ação se concluiu sozinha porque você terminou a trilha. Dá para desfazer?",
            "alternativas": [
                ("Sim, sempre", False),
                ("Sim, pedindo ao EV", False),
                ("Não há o que desfazer: a trilha está feita", True),
                ("Só no mês seguinte", False),
            ],
        },
    ],
}


AULA_5 = {
    "id": _id("b0815"),
    "titulo": "A conversa de PDI: como se preparar",
    "resumo": "Chegar com a sua leitura, propor a ação, combinar o prazo e sair com o PDI fechado na tela.",
    "duracao_min": 8,
    "conteudo_md": """\
## Para que serve a conversa

O PDI se monta numa conversa curta entre você e a gestão, com a aba PDI aberta. O objetivo é sair com **até três ações** que vocês dois acreditam, escritas no HIPO.

**Boa prática de ritmo:** uma conversa por mês, logo depois do fechamento, e uma checagem rápida no meio do mês. Quem define o ritmo da equipe é a gestão.

## Antes: três perguntas para você responder

1. **Qual número eu quero mudar?** (o ponto de atenção do Desempenho ou uma trilha atrasada)
2. **O que eu acho que trava esse número?** (técnica, rotina, volume, outra coisa)
3. **O que eu me comprometo a fazer, toda semana, para mudar?**

Escreva as três respostas. É a sua proposta de ação.

## Durante: o roteiro da conversa

1. **Olhem juntos o Desempenho** e as sugestões do HIPO.
2. **Você fala primeiro** a sua leitura (as três respostas).
3. **Escolham até três ações.** Sugestão que não faz sentido, a gestão descarta.
4. **Escrevam juntos** o objetivo e o "o que fazer", no teste da aula 3.
5. **Combinem o prazo** e se entra uma trilha de reforço.
6. **Repitam em voz alta** o que foi combinado. A gestão confirma no HIPO na hora.

## Depois

- A ação aparece na sua aba PDI. A de prazo mais curto fica no topo.
- Leve as ações para a agenda da semana (aula 4).

## Como receber um número ruim

- **Separe a pessoa do número.** O PDI fala do que fazer, não de quem você é.
- **Pergunte, não justifique.** "O que você vê de diferente em quem bate essa meta?" rende mais que três desculpas.
- **Seja honesto sobre o que trava.** Se o problema é volume (poucas tarefas, pouca prospecção), uma trilha não resolve; diga isso, e a ação precisa mexer na rotina.

## Erros comuns

- Chegar sem leitura e só ouvir.
- Aceitar dez ações para "mostrar boa vontade".
- Sair da conversa sem a ação escrita no HIPO.

> Quem chega com a própria leitura sai com um PDI que é seu. Quem só ouve sai com um PDI que é da gestão.
""",
    "quiz": [
        {
            "enunciado": "Com quantas ações a conversa deve terminar, segundo a aula?",
            "alternativas": [
                ("Até três", True),
                ("Exatamente dez", False),
                ("Uma para cada indicador", False),
                ("Nenhuma: a conversa é só para ouvir", False),
            ],
        },
        {
            "enunciado": "Qual destas é uma das três perguntas para se preparar?",
            "alternativas": [
                ("\"Quanto o meu colega vendeu?\"", False),
                ("\"O que eu acho que trava esse número?\"", True),
                ("\"Como eu justifico o resultado?\"", False),
                ("\"Qual trilha é mais curta?\"", False),
            ],
        },
        {
            "enunciado": "Quem fala primeiro na conversa, no roteiro da aula?",
            "alternativas": [
                ("A gestão, com a avaliação", False),
                ("O EV mais experiente", False),
                ("Ninguém: o HIPO decide", False),
                ("Você, com a sua leitura", True),
            ],
        },
        {
            "enunciado": "Quando a ação deve estar escrita no HIPO?",
            "alternativas": [
                ("No fim do mês", False),
                ("Na própria conversa: a gestão confirma na hora", True),
                ("Quando o colaborador lembrar", False),
                ("Não precisa estar no HIPO", False),
            ],
        },
        {
            "enunciado": "Qual é a boa prática de ritmo sugerida na aula?",
            "alternativas": [
                ("Uma conversa por mês depois do fechamento e uma checagem no meio do mês", True),
                ("Uma conversa por ano", False),
                ("Uma conversa por dia", False),
                ("Só quando houver problema", False),
            ],
        },
        {
            "enunciado": "O problema é volume: poucas tarefas e pouca prospecção. O que a aula recomenda dizer?",
            "alternativas": [
                ("Que uma trilha vai resolver", False),
                ("Que a meta está errada", False),
                ("Que uma trilha não resolve volume, e a ação precisa mudar a rotina", True),
                ("Nada, para não se expor", False),
            ],
        },
        {
            "enunciado": "Qual destes é um erro comum na conversa?",
            "alternativas": [
                ("Escrever o objetivo com número", False),
                ("Combinar o prazo", False),
                ("Olhar o Desempenho junto", False),
                ("Aceitar dez ações para mostrar boa vontade", True),
            ],
        },
    ],
}


AULA_6 = {
    "id": _id("b0816"),
    "titulo": "Para a gestão: montar e acompanhar o PDI",
    "resumo": "Revisar as sugestões, confirmar ajustando, descartar com critério, criar do zero e acompanhar sem transformar o PDI em cobrança.",
    "duracao_min": 11,
    "conteudo_md": """\
## O papel da gestão

No PDI do HIPO, **só a gestão** (Franqueado e ADM) confirma, cria, edita e cancela ações. O colaborador executa e marca como feita. Isso dá peso ao combinado, e também responsabilidade: PDI mal montado é PDI que ninguém segue.

## A tela da gestão

Em **Carreira › PDI**, escolha a pessoa no seletor **Pessoa**. Você vê:

- a próxima ação dela e os números (abertas, atrasadas, feitas no mês);
- as **Sugestões do HIPO**, cada uma com **Confirmar** e **Descartar**;
- o botão **Nova ação**, para criar do zero;
- as ações abertas, com **Editar** e **Cancelar**.

## Confirmar uma sugestão

**Confirmar** abre o formulário já preenchido com o objetivo, o que fazer e o prazo sugeridos (e a trilha, quando a sugestão é da Universidade). Antes de salvar:

1. **Reescreva o objetivo** com as palavras que vocês combinaram.
2. **Troque o "o que fazer" genérico pelo comportamento da pessoa.** A sugestão diz a tela onde agir; a conversa diz o que fazer nela.
3. **Ajuste o prazo** (de duas a quatro semanas é boa prática).
4. **Ligue uma trilha** se o problema for técnica.

## Descartar com critério

Descarte quando a sugestão **não é o problema real** (por exemplo, o indicador está baixo porque a meta do mês foi lançada errada) ou quando já existe uma ação cobrindo aquilo. **Sugestão descartada não volta:** a do Desempenho, naquele mês para aquele indicador (no mês seguinte, se o número continuar baixo, ela pode voltar); a da Universidade, não volta mais para aquela trilha.

## Criar do zero

Use **Nova ação** para o que o HIPO não enxerga: comportamento em reunião, organização, uma habilidade combinada na conversa. Mesmo teste da aula 3: objetivo com número, comportamento observável, prazo curto.

## Acompanhar sem virar cobrança

- **Olhe Atrasadas primeiro.** Ação atrasada é assunto de conversa, não de bronca.
- **Até três abertas por pessoa** (boa prática). Antes de criar a quarta, conclua ou cancele uma.
- **Cancele** o que deixou de fazer sentido, em vez de deixar apodrecer aberto.
- **Reconheça o que foi feito.** "Feitas no mês" é o número que mostra evolução.
- Ação ligada a trilha se fecha sozinha quando a pessoa termina a trilha: não precisa conferir.

## A conversa, do lado da gestão

1. Abra o PDI da pessoa antes e leia o Desempenho dela.
2. Deixe a pessoa falar primeiro (as três perguntas da aula 5).
3. Confirme no máximo três ações, escritas juntos, na hora.
4. Feche repetindo o combinado e a data da próxima checagem.

## Erros comuns da gestão

- Confirmar todas as sugestões sem ajustar o texto.
- Criar ação sem número no objetivo ("melhorar a postura").
- Deixar ação atrasada aberta meses a fio.
- Usar o PDI como advertência. PDI é plano, não punição.

> A gestão monta o PDI com a pessoa, não para a pessoa. A ação boa é a que os dois acreditam.
""",
    "tour": [
        _passo("/carreira/pdi", "pdi-numeros", "Os números da pessoa",
               "Abertas, atrasadas e feitas no mês. Na tela da gestão, acima deles ficam o seletor **Pessoa** "
               "e o botão **Nova ação**, e abaixo as **Sugestões do HIPO**."),
        _passo("/carreira/pdi", "pdi-abertas", "Acompanhar",
               "As abertas, por prazo, com **Editar** e **Cancelar**. Atrasada é assunto de conversa."),
    ],
    "quiz": [
        {
            "enunciado": "Quem pode confirmar, criar, editar e cancelar ações de PDI no HIPO?",
            "alternativas": [
                ("Qualquer colaborador", False),
                ("Só a gestão: Franqueado e ADM", True),
                ("O SDR, para o EV", False),
                ("O próprio HIPO, sozinho", False),
            ],
        },
        {
            "enunciado": "O que acontece ao clicar em Confirmar numa sugestão?",
            "alternativas": [
                ("A ação é criada sem revisão", False),
                ("A sugestão some sem criar nada", False),
                ("Abre o formulário já preenchido, para ajustar antes de salvar", True),
                ("O colaborador recebe um e-mail", False),
            ],
        },
        {
            "enunciado": "Quando descartar uma sugestão do HIPO?",
            "alternativas": [
                ("Quando ela não é o problema real ou já existe ação cobrindo aquilo", True),
                ("Sempre que o indicador estiver baixo", False),
                ("Para esconder um número ruim", False),
                ("Nunca: toda sugestão vira ação", False),
            ],
        },
        {
            "enunciado": "A gestão descartou a sugestão de NMRR deste mês. Ela volta amanhã?",
            "alternativas": [
                ("Sim, todo dia", False),
                ("Sim, se o número piorar", False),
                ("Só se o colaborador pedir", False),
                ("Não volta naquele mês: a sugestão do Desempenho é por mês e indicador", True),
            ],
        },
        {
            "enunciado": "Para que serve o botão Nova ação?",
            "alternativas": [
                ("Para duplicar uma sugestão", False),
                ("Para o que o HIPO não enxerga, como comportamento em reunião", True),
                ("Para mudar a meta do mês", False),
                ("Para concluir a ação do colaborador", False),
            ],
        },
        {
            "enunciado": "Uma ação está atrasada há semanas e deixou de fazer sentido. O que a gestão faz?",
            "alternativas": [
                ("Deixa aberta como lembrete", False),
                ("Marca como feita", False),
                ("Cancela a ação", True),
                ("Cria outra igual", False),
            ],
        },
        {
            "enunciado": "Qual é o erro comum da gestão citado na aula?",
            "alternativas": [
                ("Ajustar o texto das sugestões", False),
                ("Confirmar no máximo três ações", False),
                ("Deixar a pessoa falar primeiro", False),
                ("Usar o PDI como advertência", True),
            ],
        },
    ],
}


TECNICA_05_PDI = {
    "id": _id("b0800"),
    "titulo": "05 · PDI: criar e seguir um bom plano",
    "pilar": "tecnica",
    "reforca": "metas",
    "descricao": (
        "O que é o PDI e como ele funciona no HIPO, de onde vêm as sugestões, "
        "como escrever uma boa ação, como seguir o plano no dia a dia e como "
        "se preparar para a conversa. A última aula é para a gestão: montar "
        "e acompanhar o PDI de cada pessoa."
    ),
    "prazo_dias": 35,
    "obrigatorios": CARGOS_PDI,
    "opcionais": ("Franqueado",),
    "aulas": [AULA_1, AULA_2, AULA_3, AULA_4, AULA_5, AULA_6],
}

TRILHAS_PDI: list[dict] = [TECNICA_05_PDI]
