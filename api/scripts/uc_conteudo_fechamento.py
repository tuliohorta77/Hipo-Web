"""
HIPO — UC: 06 · Fechamento: os três 10 e como pedir o sim (pilar Técnica).

  06 · Fechamento   obrigatória para EV e EC (prazo 52 dias)
                    SDR, ADM e Franqueado veem sem obrigação

Pedido do Tulio (07/10/2026): incluir nos treinamentos da UC as técnicas
dos "três 10" do livro do Jordan Belfort (o método Linha Reta, em inglês
"Way of the Wolf") e as técnicas de fechamento, com orientação de COMO
fazer o fechamento.

Onde se encaixa:
  * 04 · Técnicas de venda consultiva (Técnica) já apresenta os tipos de
    fechamento numa aula só ("Escuta ativa, benefício e fechamento").
  * 02 · Roteiro do EV (Método) aplica o fechamento à reunião de 45 minutos
    ("Fechamento: próximo passo com data").
  * Esta trilha é o APROFUNDAMENTO: a lente dos três 10 (o cliente só diz
    sim quando está seguro do produto, de quem vende e da empresa), o
    limiar de ação e a dor, o looping para o "vou pensar" e o passo a passo
    do fechamento na Controller. Os fatos da casa (45 minutos, 3 minutos de
    fechamento, regra dos verdes, convite na hora, pergunta final, desconto
    só em troca de algo) são os do Roteiro do EV; nada de número novo.

Os conceitos do livro estão explicados com palavras nossas e adaptados à
venda de SST. Não há citação do livro. A aula 1 deixa explícito o limite
ético: certeza construída com verdade, nunca com promessa que a Controller
não cumpre.

Prazo de 52 dias: depois do Roteiro do EV (45) e do Roteiro do EC (50),
antes da Energia 01 (60). Nenhum outro prazo do EV ou do EC é 52.

Formato das aulas igual ao 04 · Técnicas do SDR: O que é · Por que
funciona · Passo a passo · Certo e errado · Erros comuns · Exercício ·
Role-play com critérios sim/não. 7 perguntas por aula.

Este arquivo é só dado. Quem grava é scripts/semear_uc.py.
"""
from __future__ import annotations

from uuid import UUID

OBRIGATORIOS = ("EV", "EC")
OPCIONAIS = ("SDR", "ADM", "Franqueado")


def _id(sufixo: str) -> UUID:
    return UUID(f"7c1d0f4e-5a01-4c0e-9b11-0000000{sufixo}")


# ═════════════════════════════════════════════════════════════════════
# Aula 1 — Os três 10
# ═════════════════════════════════════════════════════════════════════

AULA_1 = {
    "id": _id("b0911"),
    "titulo": "Fechamento 1 · Os três 10: a certeza que fecha",
    "resumo": "O cliente só diz sim quando está seguro do produto, de você e da Controller. A régua de 0 a 10 para cada uma.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

No método Linha Reta, de Jordan Belfort, a decisão de compra é explicada por **três certezas**. O cliente só fecha quando está perto do **10** (numa régua de 0 a 10) nas três ao mesmo tempo:

1. **10 no produto.** "Isso resolve o meu problema." Na Controller: o plano cobre o que ele disse que dói (o admissional que atrasa, o PGR sem os riscos psicossociais, o eSocial com erro).
2. **10 em você.** "Essa pessoa entende do assunto e está do meu lado." Você é o especialista em SST que ouviu antes de falar, e não um vendedor querendo bater meta.
3. **10 na empresa.** "Essa empresa entrega." A Controller existe desde **1991**, atende **mais de 100 mil vidas** e **mais de 500 clientes**, com atendimento nacional por clínicas credenciadas.

Basta uma das três baixa para o "sim" virar "vou pensar". O cliente quase nunca diz qual está baixa: ele diz "vou pensar", "está caro" ou "me manda por e-mail".

## Por que funciona

- **Troca o "como convenço?" por "qual certeza está faltando?"** É uma pergunta que tem resposta e diz o que fazer em seguida.
- **Explica as objeções.** "Está caro" quase sempre é certeza baixa no produto (ele ainda não viu o valor). "Vou falar com meu sócio" pode ser certeza baixa em você ou na empresa, ou só falta de decisor.
- **Casa com o nosso roteiro.** O diagnóstico SPIN constrói o 10 no produto; a preparação, o contrato de abertura e a escuta constroem o 10 em você; as credenciais como **prova, depois** do diagnóstico, constroem o 10 na empresa.

## Passo a passo

1. **Antes da reunião**, escreva para cada certeza o que você vai usar: a dor provável (produto), o dado da pesquisa que vai citar (você), o caso parecido do mesmo setor (empresa).
2. **Durante**, a cada bloco, pergunte-se: em qual das três ele está mais baixo agora?
3. **No fechamento**, só peça o sim quando as três estiverem altas. Se uma não estiver, volte a ela antes de pedir (aula 2 e 5).

## O limite ético

Certeza se constrói com **verdade**. Nada de prometer prazo, preço ou serviço que a Controller não entrega, nem de inventar urgência. Um cliente fechado com promessa falsa vira cancelamento, reclamação e uma indicação a menos. A régua dos três 10 serve para descobrir **o que o cliente ainda não sabe**, não para empurrar.

## Certo e errado

- **Errado:** o cliente diz "vou pensar" e você repete a apresentação inteira.
- **Certo:** você percebe que ele nunca falou do custo do problema (produto baixo) e volta à implicação: "Você comentou que o admissional atrasa. Quanto custa um contratado parado esperando o ASO?"
- **Errado:** abrir a reunião com 10 minutos de credenciais para "subir o 10 na empresa".
- **Certo:** credencial em uma frase na abertura; a prova completa entra depois do diagnóstico, ligada à dor que ele contou.

## Erros comuns

- **Achar que um 10 compensa outro.** Produto perfeito com vendedor que não inspira confiança não fecha.
- **Pedir o sim cedo demais.** Pedir antes das três certezas transforma o fechamento em pressão.
- **Ler a objeção ao pé da letra.** "Está caro" raramente é sobre o número.

## Exercício (individual, 15 minutos)

Pegue as **três últimas reuniões** que terminaram sem próximo passo com data. Para cada uma, dê uma nota de 0 a 10 para as três certezas, do ponto de vista do cliente, e escreva **qual estava mais baixa** e **o que você poderia ter feito** para subir. Releia a transcrição no HIPO se houver.

## Role-play em dupla (10 minutos)

- **Quem faz o cliente** escolhe em segredo uma das três certezas para deixar baixa (anote num papel).
- **Quem faz o EV** conduz 5 minutos de conversa e, no fim, diz qual certeza acha que estava baixa e por quê.
- Troquem de papel.

**Critérios (o avaliador marca sim ou não):**

1. O EV identificou a certeza certa.
2. Ele explicou com algo que o cliente disse (e não com um palpite).
3. Ele propôs uma ação concreta para subir essa certeza.
4. Ele não pediu o sim antes de tratar a certeza baixa.

> O cliente não compra quando você termina de falar. Compra quando está seguro das três coisas.
""",
    "quiz": [
        {
            "enunciado": "Quais são as três certezas dos \"três 10\"?",
            "alternativas": [
                ("Produto, você (quem vende) e a empresa", True),
                ("Preço, prazo e desconto", False),
                ("Decisor, orçamento e urgência", False),
                ("Abertura, diagnóstico e apresentação", False),
            ],
        },
        {
            "enunciado": "O cliente está 10 no produto e 10 na Controller, mas 4 em você. O que tende a acontecer?",
            "alternativas": [
                ("Fecha, porque dois 10 compensam a nota baixa", False),
                ("Adia ou trava: basta uma certeza baixa para o sim virar \"vou pensar\"", True),
                ("Pede desconto, porque o preço é o problema", False),
                ("Fecha, desde que a proposta saia em 48h", False),
            ],
        },
        {
            "enunciado": "Na Controller, o que constrói o 10 no PRODUTO durante a reunião?",
            "alternativas": [
                ("Mostrar todos os slides logo no início", False),
                ("O diagnóstico SPIN e a solução ligada à dor que o cliente disse", True),
                ("Falar dos 30 anos de história", False),
                ("Oferecer desconto antes da objeção", False),
            ],
        },
        {
            "enunciado": "Onde entram as credenciais da Controller (desde 1991, mais de 100 mil vidas, mais de 500 clientes) para subir o 10 na empresa?",
            "alternativas": [
                ("Abrindo a reunião, por 10 minutos", False),
                ("Em uma frase na abertura e como prova depois do diagnóstico", True),
                ("Só no e-mail da proposta", False),
                ("Nunca: credencial não ajuda a fechar", False),
            ],
        },
        {
            "enunciado": "O cliente diz \"está caro\". Pela lente dos três 10, o que isso costuma indicar?",
            "alternativas": [
                ("Que o preço precisa cair na hora", False),
                ("Certeza ainda baixa no produto: ele não viu o valor frente ao custo do problema", True),
                ("Que a empresa não tem orçamento nenhum", False),
                ("Que a reunião deve ser encerrada", False),
            ],
        },
        {
            "enunciado": "Qual é o limite ético dos três 10, segundo a aula?",
            "alternativas": [
                ("Vale tudo para chegar ao 10, inclusive prometer prazo", False),
                ("Certeza se constrói com verdade, sem prometer o que a Controller não entrega", True),
                ("Criar urgência falsa é aceitável se o cliente precisar", False),
                ("Só o produto precisa de verdade; o resto é persuasão", False),
            ],
        },
        {
            "enunciado": "Quando pedir o sim, segundo a aula?",
            "alternativas": [
                ("Logo depois da abertura, para testar", False),
                ("Quando as três certezas estiverem altas; se uma estiver baixa, voltar a ela antes", True),
                ("Só depois que o cliente pedir a proposta por e-mail", False),
                ("Sempre no minuto 40, independentemente da conversa", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 2 — Medir as certezas na conversa
# ═════════════════════════════════════════════════════════════════════

AULA_2 = {
    "id": _id("b0912"),
    "titulo": "Fechamento 2 · Medir as três certezas sem adivinhar",
    "resumo": "A pergunta de 0 a 10, o \"o que falta para ser 10?\" e os sinais de cada certeza na fala do cliente.",
    "duracao_min": 10,
    "conteudo_md": """\
## O que é

Medir é descobrir, **durante** a reunião, em que ponto o cliente está em cada certeza. Duas ferramentas:

- **A pergunta de calibração:** "De 0 a 10, quanto isso que eu mostrei resolve o que você me contou sobre [dor]?"
- **A pergunta do que falta:** "O que faltaria para ser um 10?"

A primeira dá o número. A segunda dá o caminho.

## Por que funciona

- **O cliente se ouve.** Dar uma nota faz ele pensar no valor, e não no preço.
- **Nota abaixo de 10 não é derrota, é mapa.** "Um 7" seguido de "o que falta?" revela a objeção real enquanto ainda dá para tratar.
- **É um pequeno fechamento.** Cada nota alta é um "sim" parcial; vários "sim" parciais tornam o final natural.

## Os sinais de cada certeza

- **Produto.** Alta: pergunta "como funciona a implantação?", "o periódico entra?". Baixa: "mas isso a gente já tem", "não sei se precisa".
- **Você.** Alta: conta detalhes do problema, pede a sua opinião. Baixa: respostas curtas, câmera fechada, "manda por e-mail".
- **Empresa.** Alta: pergunta de atendimento em outra cidade, de prazo do ASO. Baixa: "nunca ouvi falar", "e se a clínica não atender?".

## Passo a passo

1. **Depois de cada bloco da solução**, faça a pergunta de confirmação do roteiro: "Isso resolveria o que você comentou sobre…?"
2. **Antes do fechamento**, faça a calibração de 0 a 10 sobre o produto.
3. **Nota 8 ou menos:** pergunte o que falta e **escute até o fim** (é o L do LAER).
4. **Nota 9 ou 10:** passe para a pergunta de teste do fechamento (aula 6).
5. **Para você e para a empresa**, observe os sinais da tabela; se aparecer o lado baixo, volte nele antes de pedir.

## Certo e errado

- **Errado:** "Gostou?" (o cliente diz "gostei" por educação e você não aprende nada).
- **Certo:** "De 0 a 10, quanto isso resolve o atraso do admissional que você contou?" — "Uns 7." — "O que faltaria para ser 10?"
- **Errado:** ouvir "uns 7" e rebater na hora com mais slides.
- **Certo:** ouvir, anotar as palavras dele, explorar com "como assim?" e só depois responder.

## Erros comuns

- **Perguntar a nota e não perguntar o que falta.** O número sozinho não ajuda.
- **Discutir a nota.** "Mas é 10, olha só…" fecha o cliente. A nota é dele.
- **Calibrar só no fim.** No fim não há tempo para subir uma certeza; calibre durante a solução.

## Exercício (individual, 10 minutos)

Escreva a sua versão das duas perguntas (calibração e o que falta) para as três hipóteses de dor da casa: **admissional demorado**, **PGR sem os riscos psicossociais** e **eSocial de SST com erro**. Leia em voz alta até sair natural.

## Role-play em dupla (10 minutos)

- **Quem faz o cliente** dá uma nota de 6 a 8 e tem uma razão escondida (prazo de implantação, uma unidade em outro estado, desconfiança da clínica).
- **Quem faz o EV** calibra, pergunta o que falta e descobre a razão.

**Critérios (o avaliador marca sim ou não):**

1. Fez a pergunta de 0 a 10 ligada a uma dor dita pelo cliente.
2. Perguntou o que faltava para ser 10.
3. Ouviu até o fim, sem interromper.
4. Descobriu a razão escondida.
5. Não discutiu a nota.

> Nota baixa dita em voz alta é a melhor notícia da reunião: ela aparece enquanto você ainda pode agir.
""",
    "quiz": [
        {
            "enunciado": "Qual é a pergunta de calibração ensinada na aula?",
            "alternativas": [
                ("\"Gostou da apresentação?\"", False),
                ("\"De 0 a 10, quanto isso resolve o que você me contou sobre [dor]?\"", True),
                ("\"Posso mandar a proposta por e-mail?\"", False),
                ("\"Qual é o seu orçamento?\"", False),
            ],
        },
        {
            "enunciado": "O cliente deu nota 7. Qual é o próximo passo?",
            "alternativas": [
                ("Pedir o sim mesmo assim", False),
                ("Perguntar o que faltaria para ser 10 e escutar até o fim", True),
                ("Mostrar de novo todos os slides", False),
                ("Oferecer desconto", False),
            ],
        },
        {
            "enunciado": "Por que \"Gostou?\" é uma pergunta fraca?",
            "alternativas": [
                ("Porque o cliente responde \"gostei\" por educação e você não aprende nada", True),
                ("Porque é longa demais", False),
                ("Porque fala de preço", False),
                ("Porque só serve para o SDR", False),
            ],
        },
        {
            "enunciado": "\"Manda por e-mail\", câmera fechada e respostas curtas são sinais de certeza baixa em quê?",
            "alternativas": [
                ("No produto", False),
                ("Em você (quem está vendendo)", True),
                ("No preço", False),
                ("No contrato atual", False),
            ],
        },
        {
            "enunciado": "Quando é melhor calibrar as certezas?",
            "alternativas": [
                ("Só no último minuto da reunião", False),
                ("Durante a solução e antes de pedir o sim, para ainda dar tempo de agir", True),
                ("Só depois que a proposta for enviada", False),
                ("Nunca na reunião: só por e-mail", False),
            ],
        },
        {
            "enunciado": "O cliente pergunta \"e se a clínica da minha cidade não atender bem?\". Qual certeza está baixa?",
            "alternativas": [
                ("Na empresa (se a Controller entrega)", True),
                ("No produto", False),
                ("Em você", False),
                ("Nenhuma: é só curiosidade", False),
            ],
        },
        {
            "enunciado": "O que NÃO fazer depois que o cliente dá uma nota abaixo de 10?",
            "alternativas": [
                ("Anotar as palavras dele", False),
                ("Explorar com \"como assim?\"", False),
                ("Discutir a nota: \"mas é 10, olha só...\"", True),
                ("Perguntar o que falta para ser 10", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 3 — Subir cada certeza
# ═════════════════════════════════════════════════════════════════════

AULA_3 = {
    "id": _id("b0913"),
    "titulo": "Fechamento 3 · Como subir cada um dos três 10",
    "resumo": "O que fazer quando o produto, você ou a Controller estão abaixo de 10 — com a ferramenta certa para cada um.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

Cada certeza sobe com uma ferramenta diferente. Usar a ferramenta errada (mais credencial quando falta valor, mais produto quando falta confiança) gasta tempo e não muda a nota.

## Por que funciona

O cliente não precisa de **mais informação**; precisa da **informação que falta** na certeza que está baixa. Atacar só a certeza baixa encurta a reunião e deixa o cliente com a sensação de ter sido entendido.

## Passo a passo: produto baixo

1. **Volte à dor, não ao slide.** "Você me contou que [dor nas palavras dele]."
2. **Faça uma pergunta de implicação**: "O que acontece se isso continuar mais seis meses?" O cliente que diz o custo do problema sobe o próprio 10.
3. **Benefício, não recurso**: "Você vê todos os vencimentos em tempo real", e não "temos o SOC".
4. **Confirme**: "Isso resolveria?"

## Passo a passo: você baixo

1. **Mostre que ouviu**: o resumo de confirmação com as palavras dele ("Deixa eu ver se entendi…").
2. **Mostre que sabe**: um insight que ele não tinha (por exemplo, os riscos psicossociais no PGR pela NR-01).
3. **Mostre que está do lado dele**: diga o que **não** recomenda. "Treinamento de NR específico não precisa agora; foque no PGR."
4. **Ritmo e tom**: calmo, sem pressa, falando menos do que ele (a meta da casa é até 40% do tempo).

## Passo a passo: empresa baixa

1. **Prova do mesmo setor ou porte**: uma história curta de cliente parecido.
2. **Responda a dúvida concreta**: atendimento nacional, prazo do ASO, como funciona a clínica credenciada perto da unidade dele.
3. **Números como resposta, não como propaganda**: mais de 500 clientes e mais de 100 mil vidas entram quando ele duvida, não no começo.

## Certo e errado

- **Errado (empresa baixa):** responder "nunca ouvi falar de vocês" com a lista completa de serviços.
- **Certo:** "Faz sentido. Estamos desde 1991, começamos aqui em Guarulhos, e hoje são mais de 500 clientes. Tem um do seu setor com três lojas como vocês; quer que eu conte como foi a troca?"
- **Errado (você baixo):** falar mais rápido e mais alto para parecer seguro.
- **Certo:** parar, resumir o que ouviu e perguntar se entendeu certo.

## Erros comuns

- **Remédio único.** Responder qualquer dúvida com o slide de credenciais.
- **Esquecer a confirmação.** Subiu a certeza? Pergunte de novo a nota.
- **Falar mal do fornecedor atual** para subir a Controller. Derruba o 10 em você.

## Exercício (individual, 15 minutos)

Monte a sua **ficha de bolso** com três linhas, uma por certeza: a pergunta ou frase que você usa para subir cada uma. Teste numa reunião real esta semana e anote o que aconteceu.

## Role-play em dupla (10 minutos)

- **Quem faz o cliente** sorteia uma certeza baixa e solta uma frase-pista ("já temos fornecedor", "nunca ouvi falar", "não sei se preciso").
- **Quem faz o EV** identifica a certeza e usa o passo a passo daquela certeza.

**Critérios (o avaliador marca sim ou não):**

1. Identificou a certeza certa pela frase-pista.
2. Usou a ferramenta daquela certeza (e não outra).
3. Usou as palavras do cliente.
4. Confirmou no fim ("isso resolve?" ou nova nota).
5. Não falou mal do fornecedor atual.

> Cada certeza tem a sua chave. Mais do mesmo não abre a porta errada.
""",
    "quiz": [
        {
            "enunciado": "O produto está baixo. Qual é o primeiro passo?",
            "alternativas": [
                ("Voltar à dor que o cliente disse, com as palavras dele", True),
                ("Mostrar os 30 anos de história", False),
                ("Oferecer desconto", False),
                ("Mandar a proposta por e-mail", False),
            ],
        },
        {
            "enunciado": "Qual frase é benefício, e não recurso?",
            "alternativas": [
                ("\"Temos o SOC.\"", False),
                ("\"Você vê todos os vencimentos em tempo real.\"", True),
                ("\"Trabalhamos com clínicas credenciadas.\"", False),
                ("\"Fazemos PGR e PCMSO.\"", False),
            ],
        },
        {
            "enunciado": "Como subir a certeza em VOCÊ, segundo a aula?",
            "alternativas": [
                ("Falar mais rápido e mais alto", False),
                ("Resumir o que ouviu, trazer um insight e dizer também o que não recomenda", True),
                ("Mostrar mais slides de serviço", False),
                ("Falar mal do fornecedor atual", False),
            ],
        },
        {
            "enunciado": "O cliente diz \"nunca ouvi falar de vocês\". Qual certeza trabalhar?",
            "alternativas": [
                ("Produto", False),
                ("Você", False),
                ("Empresa, com prova do mesmo setor ou porte", True),
                ("Nenhuma: encerrar a reunião", False),
            ],
        },
        {
            "enunciado": "Quando os números da Controller (mais de 500 clientes, mais de 100 mil vidas) funcionam melhor?",
            "alternativas": [
                ("Como resposta a uma dúvida que o cliente mostrou", True),
                ("Logo no primeiro minuto, como propaganda", False),
                ("Só na proposta escrita", False),
                ("Nunca", False),
            ],
        },
        {
            "enunciado": "Por que falar mal do fornecedor atual atrapalha o fechamento?",
            "alternativas": [
                ("Porque derruba a certeza do cliente em você", True),
                ("Porque é proibido pelo eSocial", False),
                ("Porque aumenta o preço", False),
                ("Não atrapalha: ajuda a ganhar", False),
            ],
        },
        {
            "enunciado": "Depois de trabalhar a certeza baixa, o que fazer?",
            "alternativas": [
                ("Pedir o sim sem confirmar", False),
                ("Confirmar: perguntar se resolve ou pedir a nota de novo", True),
                ("Mudar de assunto", False),
                ("Repetir a apresentação inteira", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 4 — Limiar de ação e dor
# ═════════════════════════════════════════════════════════════════════

AULA_4 = {
    "id": _id("b0914"),
    "titulo": "Fechamento 4 · Limiar de ação e dor: quando o 10 não basta",
    "resumo": "Por que alguns clientes seguros ainda não decidem, e como a dor e o passo de baixo risco destravam.",
    "duracao_min": 10,
    "conteudo_md": """\
## O que é

Além dos três 10, o método fala de mais duas forças:

- **Limiar de ação:** o quanto de certeza cada pessoa precisa para agir. Tem cliente que decide com 8; tem quem precise de 10 e ainda hesite. Não se muda a personalidade de ninguém, mas dá para **baixar o tamanho do passo**.
- **Dor:** o desconforto de ficar como está. Quanto mais o cliente sente o custo de não mudar, mais fácil é agir. Na nossa metodologia, a dor vem das **perguntas de implicação** do SPIN.

## Por que funciona

- **Explica o "adorei, mas vou ver depois".** Certeza alta, dor baixa: nada empurra a decisão para agora.
- **Dá duas alavancas éticas.** Aumentar a percepção de um custo **real** (multa, afastamento, retrabalho no eSocial) e **diminuir o risco percebido** do primeiro passo.

## Passo a passo: trazer a dor à tona

1. Pergunte, não afirme: "Se um fiscal chegasse amanhã e pedisse PGR, PCMSO e ASOs, o que encontraria?"
2. Deixe o cliente responder e calcular: "Quanto custa um dia de funcionário parado esperando o ASO?"
3. Volte a essa resposta no resumo de valor do fechamento.

## Passo a passo: baixar o limiar

1. **Passo de baixo risco:** "Que tal começarmos com um diagnóstico da documentação atual? Em poucos dias você sabe exatamente onde está exposto."
2. **Reunião com o decisor:** quando o medo é decidir sozinho, o próximo passo é levar quem decide para a mesa.
3. **Fechamento futuro:** contrato vigente com outro fornecedor? Marque agora a revisão para 60 dias antes do vencimento.

O que **não** se usa para baixar o limiar: desconto sem contrapartida e urgência inventada. Desconto, na casa, só em troca de algo (prazo maior, antecipação, indicação) e depois de reduzir escopo.

## Certo e errado

- **Errado:** "A multa é altíssima, vocês vão ser autuados." (Afirmação, soa como ameaça.)
- **Certo:** "Se houver um afastamento com o PGR desatualizado, como isso fica numa ação trabalhista?"
- **Errado:** "Fecho com 20% se assinar hoje."
- **Certo:** "Começamos pelo diagnóstico da documentação; se fizer sentido, seguimos com o plano."

## Erros comuns

- **Confundir dor com medo.** Dor é o custo que o cliente reconhece; medo inventado some quando ele desliga a call.
- **Pular a implicação** para ganhar tempo. Sem dor, até o cliente 10 adia.
- **Oferecer o passo pequeno cedo demais**, antes de tentar o passo cheio quando a qualificação permite.

## Exercício (individual, 10 minutos)

Para cada uma das três hipóteses de dor da casa, escreva **uma pergunta de implicação** e **um passo de baixo risco** possível. Revise: nenhuma das perguntas pode ser uma afirmação disfarçada.

## Role-play em dupla (10 minutos)

- **Quem faz o cliente** está "10 em tudo", mas diz "vamos ver isso no ano que vem".
- **Quem faz o EV** traz a dor com perguntas e, se não destravar, propõe um passo de baixo risco com data.

**Critérios (o avaliador marca sim ou não):**

1. Fez pelo menos uma pergunta de implicação (e não afirmação).
2. O cliente disse, com as palavras dele, um custo do problema.
3. Se não destravou, ofereceu um passo menor com data.
4. Não ofereceu desconto sem contrapartida.

> Certeza diz que vale a pena. Dor diz que vale a pena agora.
""",
    "quiz": [
        {
            "enunciado": "O que é o limiar de ação?",
            "alternativas": [
                ("O quanto de certeza cada pessoa precisa para agir", True),
                ("O preço mínimo da proposta", False),
                ("O tempo máximo da reunião", False),
                ("A quantidade de vidas do plano", False),
            ],
        },
        {
            "enunciado": "Certeza alta e dor baixa costumam dar em quê?",
            "alternativas": [
                ("Fechamento imediato", False),
                ("\"Adorei, mas vou ver depois\": nada empurra a decisão para agora", True),
                ("Pedido de desconto", False),
                ("Cancelamento do contrato atual", False),
            ],
        },
        {
            "enunciado": "Na nossa metodologia, de onde vem a dor?",
            "alternativas": [
                ("Das perguntas de implicação do SPIN", True),
                ("Do slide de credenciais", False),
                ("Da ameaça de multa", False),
                ("Do desconto", False),
            ],
        },
        {
            "enunciado": "Qual destas é uma forma correta de trazer a dor?",
            "alternativas": [
                ("\"Vocês vão ser autuados.\"", False),
                ("\"Se um fiscal chegasse amanhã, o que encontraria?\"", True),
                ("\"A multa é altíssima.\"", False),
                ("\"Todo mundo está irregular.\"", False),
            ],
        },
        {
            "enunciado": "Qual destes BAIXA o limiar de ação de forma ética?",
            "alternativas": [
                ("Desconto de 20% só se assinar hoje", False),
                ("Um passo de baixo risco, como o diagnóstico da documentação", True),
                ("Dizer que a vaga na agenda acaba amanhã sem ser verdade", False),
                ("Insistir até o cliente aceitar", False),
            ],
        },
        {
            "enunciado": "O cliente tem contrato vigente até março com outro fornecedor. O que fazer?",
            "alternativas": [
                ("Fechamento futuro: marcar agora a revisão para 60 dias antes do vencimento", True),
                ("Desistir da oportunidade", False),
                ("Pressionar para quebrar o contrato", False),
                ("Mandar a proposta e esperar", False),
            ],
        },
        {
            "enunciado": "Na Controller, quando o desconto pode entrar?",
            "alternativas": [
                ("Sempre que o cliente hesitar", False),
                ("Depois de reduzir escopo e sempre em troca de algo (prazo, antecipação, indicação)", True),
                ("No início da reunião, para gerar interesse", False),
                ("Nunca, em nenhuma hipótese", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 5 — Looping
# ═════════════════════════════════════════════════════════════════════

AULA_5 = {
    "id": _id("b0915"),
    "titulo": "Fechamento 5 · O looping: do \"vou pensar\" de volta ao sim",
    "resumo": "Acolher a objeção, voltar à certeza que está baixa, subir e pedir de novo — junto com o LAER da casa.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

**Looping** é o nome que o método Linha Reta dá ao movimento depois de um "não ainda": em vez de discutir a objeção, você **acolhe**, **volta** à certeza que está baixa, **sobe** essa certeza e **pede de novo**, com outro tipo de fechamento.

Na Controller, o looping anda junto com o **LAER**: o LAER (Listar, Acolher, Explorar, Responder) descobre **qual** é a objeção real; o looping usa essa descoberta para voltar às três certezas e refazer o pedido.

## Por que funciona

- **A primeira objeção quase nunca é a real.** "Vou pensar" esconde preço, decisor, confiança ou momento.
- **Discutir cria lados.** Voltar à certeza mantém você e o cliente do mesmo lado da mesa.
- **Um novo pedido, mais leve,** dá ao cliente uma saída para dizer sim sem parecer que "perdeu a discussão".

## Passo a passo (o ciclo)

1. **Acolha.** "Faz todo sentido querer pensar; é uma decisão importante."
2. **Explore (o E do LAER).** "Para eu te ajudar: o que exatamente você quer avaliar, o preço, o escopo ou o momento?"
3. **Volte à certeza baixa.** Preço/escopo → produto (implicação e custo total). Confiança → você ou a empresa (resumo, prova). Momento → dor e limiar (aula 4).
4. **Calibre de novo.** "E agora, de 0 a 10?"
5. **Peça de novo, com um fechamento diferente.** Se o primeiro foi direto, agora é alternativa de horários ou passo de baixo risco.

## O limite

- **Até duas voltas** na mesma reunião. Se depois disso a resposta ainda for "não agora", feche o **próximo passo com data** (reunião com o decisor, revisão, diagnóstico) e encerre bem.
- O cliente pode dizer não. Respeitar o não com elegância mantém o 10 em você para a próxima conversa.

## Certo e errado

- **Errado:** "Pensar em quê? Está tudo aí." (Discute e pressiona.)
- **Certo:** "Claro. O que pesa mais para você agora: o investimento, o que está incluso ou o momento?" — "O investimento." — "Comparado a quê? No que vocês pagam hoje estão inclusos o PGR, o eSocial e a gestão?"
- **Errado:** fazer o mesmo pedido, do mesmo jeito, três vezes.
- **Certo:** depois de subir o produto, trocar o pedido: "Te apresento a proposta fechada na quinta às 10h ou na sexta às 15h?"

## Erros comuns

- **Pular o explorar** e responder a objeção que você imaginou.
- **Voltar à certeza errada** (mais credencial quando a dúvida é de escopo).
- **Loop infinito.** Mais de duas voltas vira pressão e derruba o 10 em você.
- **Sair sem próximo passo** depois de um "não agora".

## Exercício (individual, 15 minutos)

Escreva o ciclo completo (acolher, explorar, certeza, calibrar, novo pedido) para três objeções do roteiro: **"vou pensar"**, **"está caro"** e **"manda a proposta por e-mail"**. Lembre: proposta por e-mail só com a reunião de apresentação marcada.

## Role-play em dupla (15 minutos)

- **Quem faz o cliente** começa com "vou pensar" e tem uma razão real escondida.
- **Quem faz o EV** faz até duas voltas de looping.

**Critérios (o avaliador marca sim ou não):**

1. Acolheu antes de responder.
2. Fez a pergunta de exploração e descobriu a razão real.
3. Voltou à certeza certa.
4. O segundo pedido foi diferente do primeiro.
5. Parou em no máximo duas voltas.
6. A reunião terminou com próximo passo com data.

> O "vou pensar" não é o fim da conversa; é o começo da parte que interessa.
""",
    "quiz": [
        {
            "enunciado": "O que é o looping?",
            "alternativas": [
                ("Repetir a apresentação inteira até o cliente aceitar", False),
                ("Acolher, voltar à certeza baixa, subir essa certeza e pedir de novo", True),
                ("Ligar todo dia até o cliente responder", False),
                ("Dar desconto a cada objeção", False),
            ],
        },
        {
            "enunciado": "Como o looping se combina com o LAER da casa?",
            "alternativas": [
                ("O LAER descobre a objeção real; o looping usa isso para voltar às certezas e pedir de novo", True),
                ("Um substitui o outro: escolha só um", False),
                ("O LAER é para o SDR, o looping é só para o EC", False),
                ("Não se combinam", False),
            ],
        },
        {
            "enunciado": "O cliente disse \"vou pensar\". Qual é a pergunta de exploração da aula?",
            "alternativas": [
                ("\"Pensar em quê? Está tudo aí.\"", False),
                ("\"O que exatamente você quer avaliar: o preço, o escopo ou o momento?\"", True),
                ("\"Posso te ligar amanhã?\"", False),
                ("\"Quer um desconto?\"", False),
            ],
        },
        {
            "enunciado": "Quantas voltas de looping, no máximo, na mesma reunião?",
            "alternativas": [
                ("Uma", False),
                ("Duas", True),
                ("Cinco", False),
                ("Quantas forem precisas", False),
            ],
        },
        {
            "enunciado": "Depois de subir a certeza, como deve ser o novo pedido?",
            "alternativas": [
                ("Idêntico ao primeiro, para mostrar firmeza", False),
                ("Diferente do primeiro (por exemplo, alternativa de horários ou passo de baixo risco)", True),
                ("Por e-mail, no dia seguinte", False),
                ("Não deve haver novo pedido", False),
            ],
        },
        {
            "enunciado": "A objeção real é o escopo. Para qual certeza voltar?",
            "alternativas": [
                ("Empresa, com mais credenciais", False),
                ("Produto, mostrando o que está incluso e o custo total", True),
                ("Você, contando sua experiência pessoal", False),
                ("Nenhuma: encerrar", False),
            ],
        },
        {
            "enunciado": "Depois de duas voltas, o cliente ainda diz \"não agora\". O que fazer?",
            "alternativas": [
                ("Fazer a terceira, quarta e quinta volta", False),
                ("Fechar um próximo passo com data e encerrar bem", True),
                ("Desligar sem combinar nada", False),
                ("Mandar a proposta por e-mail sem reunião marcada", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 6 — As técnicas de fechamento
# ═════════════════════════════════════════════════════════════════════

AULA_6 = {
    "id": _id("b0916"),
    "titulo": "Fechamento 6 · As técnicas de fechamento e quando usar cada uma",
    "resumo": "Pergunta de teste, resumo de valor, direto, alternativa, presumido, decisor, baixo risco e futuro — com a frase de cada uma.",
    "duracao_min": 14,
    "conteudo_md": """\
## O que é

Fechar é **pedir um compromisso claro**. As técnicas abaixo são jeitos diferentes de pedir, e cada uma serve a uma situação. Nenhuma funciona se as três certezas estiverem baixas: técnica não substitui diagnóstico.

## Por que funciona

- **Tira o peso do "sim ou não".** Uma boa técnica dá ao cliente um passo claro, do tamanho certo para ele.
- **Combina com a regra da casa:** nenhuma reunião termina sem próximo passo com **data e hora** na agenda do cliente.

## As técnicas

**1. Pergunta de teste (fechamento experimental).** Sonda sem pedir. "Se começarmos este mês, faz sentido pela unidade de Guarulhos primeiro?" A resposta mostra se dá para pedir o sim.

**2. Resumo de valor.** Abre o fechamento retomando o contrato de abertura. "Você me contou que [dor 1] e [dor 2] estão custando [implicação]. Vimos que com [solução] isso se resolve. Combinamos no início que decidiríamos juntos o próximo passo. Faz sentido seguirmos?"

**3. Direto.** Decisor presente, **6 ou mais verdes** na qualificação. "Podemos começar a implantação no dia [X]? Preciso só dos dados para o contrato."

**4. Alternativa.** Duas opções, as duas positivas. "Te apresento a proposta na quinta às 10h ou na sexta às 15h?"

**5. Presumido.** Fala do próximo passo como natural, quando os sinais de compra já estão claros. "Para a implantação, quem do RH vai ser o nosso contato?" Use só com certeza alta; com certeza baixa, soa como pressão.

**6. Reunião com o decisor.** Quem decide não está. "Vamos marcar 20 minutos com o [diretor] esta semana? Eu levo a proposta pronta."

**7. Passo de baixo risco.** Cliente inseguro sobre trocar. "Que tal começarmos com um diagnóstico da documentação atual?"

**8. Futuro.** Contrato vigente. "Seu contrato vence em [mês]. Vamos marcar agora a revisão para 60 dias antes?"

E sempre, no fim: **a pergunta final**. "Tem alguma coisa que possa impedir a gente de avançar que eu ainda não sei?"

## Qual usar (resumo)

- **Sinais de compra, quero confirmar** → pergunta de teste.
- **Toda abertura de fechamento** → resumo de valor.
- **Decisor presente, 6 ou mais verdes** → direto (ou presumido).
- **Decisor presente, quer ver números** → alternativa.
- **Decisor ausente** → reunião com o decisor.
- **Inseguro sobre trocar** → passo de baixo risco.
- **Contrato vigente** → futuro.

## Certo e errado

- **Errado:** "Então, o que você achou? Me avisa qualquer coisa." (Não pede nada.)
- **Certo:** resumo de valor + "Podemos começar no dia 3? Preciso só dos dados para o contrato." E **silêncio**.
- **Errado:** usar o presumido com um cliente que acabou de dizer "não sei se preciso".
- **Certo:** com esse cliente, voltar ao produto (aula 3) e depois oferecer o passo de baixo risco.

## Erros comuns

- **Falar depois de pedir.** Depois do pedido, quem fala primeiro cede. Espere a resposta.
- **Técnica sem resumo de valor.** O pedido solto parece pressão.
- **Aceitar "semana que vem" como próximo passo.** Sem dia e hora, o item 10 do scorecard vale 1, e a oportunidade esfria.

## Exercício (individual, 15 minutos)

Escreva a sua frase para cada uma das oito técnicas, adaptada às suas reuniões. Depois, para três oportunidades abertas no seu HIPO, diga qual técnica usaria no próximo contato e por quê.

## Role-play em dupla (15 minutos)

- **Quem faz o cliente** recebe um cartão de situação (decisor ausente, contrato vigente, inseguro, 6 verdes, quer ver números).
- **Quem faz o EV** abre com o resumo de valor e usa a técnica certa.

**Critérios (o avaliador marca sim ou não):**

1. Abriu com o resumo de valor.
2. Escolheu a técnica que combina com a situação.
3. Pediu de forma clara e ficou em silêncio depois.
4. Terminou com dia e hora aceitos.
5. Fez a pergunta final.

> Fechar não é o que você diz no fim. É o compromisso claro que o cliente assume no fim.
""",
    "quiz": [
        {
            "enunciado": "Para que serve a pergunta de teste?",
            "alternativas": [
                ("Para sondar se dá para pedir o sim, sem pedir ainda", True),
                ("Para pedir desconto ao gestor", False),
                ("Para encerrar a reunião", False),
                ("Para substituir o diagnóstico", False),
            ],
        },
        {
            "enunciado": "Decisor presente, 6 ou mais verdes na qualificação. Qual técnica?",
            "alternativas": [
                ("Futuro", False),
                ("Direto (ou presumido)", True),
                ("Passo de baixo risco", False),
                ("Reunião com o decisor", False),
            ],
        },
        {
            "enunciado": "Qual destas é a técnica da alternativa?",
            "alternativas": [
                ("\"Me avisa qualquer coisa.\"", False),
                ("\"Te apresento a proposta na quinta às 10h ou na sexta às 15h?\"", True),
                ("\"Vou te mandar por e-mail.\"", False),
                ("\"Você quer ou não quer?\"", False),
            ],
        },
        {
            "enunciado": "Quando o fechamento presumido é arriscado?",
            "alternativas": [
                ("Quando as certezas ainda estão baixas: soa como pressão", True),
                ("Quando o decisor está presente", False),
                ("Quando há 6 ou mais verdes", False),
                ("Nunca é arriscado", False),
            ],
        },
        {
            "enunciado": "O que fazer logo depois de fazer o pedido de fechamento?",
            "alternativas": [
                ("Continuar falando para justificar o preço", False),
                ("Ficar em silêncio e esperar a resposta", True),
                ("Oferecer desconto preventivo", False),
                ("Encerrar a chamada", False),
            ],
        },
        {
            "enunciado": "Com o que toda abertura de fechamento deve começar?",
            "alternativas": [
                ("Com o preço", False),
                ("Com o resumo de valor, retomando o contrato de abertura", True),
                ("Com as credenciais da Controller", False),
                ("Com a lista de serviços", False),
            ],
        },
        {
            "enunciado": "O cliente aceitou \"falar semana que vem\", sem dia e hora. Quanto vale o item 10 do scorecard?",
            "alternativas": [
                ("2", False),
                ("1", True),
                ("0", False),
                ("Não é avaliado", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 7 — O fechamento na Controller, passo a passo
# ═════════════════════════════════════════════════════════════════════

AULA_7 = {
    "id": _id("b0917"),
    "titulo": "Fechamento 7 · O fechamento na Controller, passo a passo",
    "resumo": "Os 3 minutos finais da reunião, do sinal de compra ao convite enviado e à próxima tarefa no HIPO.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

Esta aula junta tudo num roteiro só, para os **3 minutos de fechamento** da reunião de **45 minutos**. É o que você deve conseguir fazer sem pensar.

## Por que funciona

Um roteiro fixo tira a ansiedade do fim da reunião. Você sabe o que vem em seguida, o cliente sente segurança (sobe o 10 em você) e nada fica para "a gente vai conversando".

## Passo a passo

1. **Perceba o sinal de compra.** Perguntas de implantação, de prazo, de quem vai cuidar; o cliente usando "quando" em vez de "se".
2. **Calibre.** "De 0 a 10, quanto isso resolve o que você me contou?" Abaixo de 9: pergunte o que falta e use o looping (no máximo duas voltas).
3. **Resumo de valor.** As dores e as implicações **nas palavras dele**, a solução em uma frase, e a retomada do combinado da abertura: "Combinamos que decidiríamos juntos o próximo passo."
4. **Peça, com a técnica da situação.** Direto, alternativa, decisor, baixo risco ou futuro (aula 6).
5. **Silêncio.** Espere a resposta, mesmo que demore.
6. **Trate o que vier com LAER.** Desconto só depois de reduzir escopo e sempre em troca de algo.
7. **Convite na hora.** Mande o convite de calendário **ainda na reunião**, com pauta e participantes. Pergunte quem mais precisa estar.
8. **Pergunta final.** "Tem alguma coisa que possa impedir a gente de avançar que eu ainda não sei?"

## No HIPO, logo depois

- **Registre o desfecho** da reunião e crie o **próximo passo como próxima tarefa** da oportunidade, com a data e a hora que o cliente aceitou.
- Prometeu proposta? Ela sai em até **48h**, e a reunião de apresentação já está marcada.
- Dentro da reunião, na Agenda, o botão **Guia do roteiro** abre o resumo do scorecard com exemplos rápidos de fala, inclusive os três 10 e as frases de fechamento. Deixe aberto ao lado do Meet.

## Certo e errado

- **Errado:** "Bom, era isso. Te mando a proposta e a gente se fala."
- **Certo:** "Você me contou que o admissional leva dez dias e que isso atrasa a abertura da loja nova. Com o plano, o ASO sai na clínica perto da loja e você acompanha tudo num painel só. Combinamos que decidiríamos juntos o próximo passo: te apresento a proposta fechada na quinta às 10h ou na sexta às 15h?" (silêncio) "Quinta." "Já estou mandando o convite. Mais alguém precisa estar? E tem alguma coisa que possa impedir a gente de avançar que eu ainda não sei?"

## Erros comuns

- **Deixar o fechamento para o minuto 44.** Comece a fechar aos 40; o fechamento cabe em 3 minutos, mas o looping precisa de folga.
- **Esquecer o convite.** Combinado sem convite é combinado esquecido.
- **Não lançar a próxima tarefa.** Oportunidade viva nunca fica sem próximo passo aberto no HIPO.

## Exercício (individual, 15 minutos)

Grave (no celular) o seu fechamento completo para uma oportunidade real, seguindo os oito passos, em até 3 minutos. Ouça e marque quais passos ficaram de fora.

## Role-play em dupla (15 minutos)

- **Quem faz o cliente** decide em segredo se vai aceitar de primeira, pedir para pensar ou dizer que o decisor não está.
- **Quem faz o EV** conduz o fechamento completo; o avaliador cronometra.

**Critérios (o avaliador marca sim ou não):**

1. Calibrou antes de pedir.
2. Fez o resumo de valor com as palavras do cliente e retomou o combinado da abertura.
3. Usou a técnica certa para a situação.
4. Ficou em silêncio depois do pedido.
5. Terminou com dia e hora aceitos e o convite enviado na hora.
6. Fez a pergunta final.
7. Coube em até 3 minutos (mais o looping, se houve).

> Quem sabe exatamente como vai terminar a reunião conduz a reunião inteira com mais calma.
""",
    "quiz": [
        {
            "enunciado": "Quanto tempo o fechamento ocupa na reunião de 45 minutos da Controller?",
            "alternativas": [
                ("3 minutos", True),
                ("15 minutos", False),
                ("30 segundos", False),
                ("O tempo que sobrar", False),
            ],
        },
        {
            "enunciado": "Qual destes é um sinal de compra?",
            "alternativas": [
                ("O cliente pergunta como funciona a implantação e quem vai cuidar", True),
                ("O cliente fecha a câmera", False),
                ("O cliente diz \"me manda por e-mail\"", False),
                ("O cliente pergunta se vocês existem há muito tempo", False),
            ],
        },
        {
            "enunciado": "Na ordem do passo a passo, o que vem logo antes do pedido?",
            "alternativas": [
                ("O convite de calendário", False),
                ("O resumo de valor nas palavras do cliente", True),
                ("A pergunta final", False),
                ("O envio da proposta", False),
            ],
        },
        {
            "enunciado": "Quando mandar o convite do próximo passo?",
            "alternativas": [
                ("Ainda na reunião", True),
                ("No dia seguinte", False),
                ("Depois que a proposta for aceita", False),
                ("Quando o cliente pedir", False),
            ],
        },
        {
            "enunciado": "Prometeu proposta na reunião. Em quanto tempo ela sai?",
            "alternativas": [
                ("Em até 48h, com a reunião de apresentação já marcada", True),
                ("Em até 30 dias", False),
                ("Só quando o cliente cobrar", False),
                ("No mesmo minuto, por e-mail, sem reunião", False),
            ],
        },
        {
            "enunciado": "O que registrar no HIPO logo depois da reunião?",
            "alternativas": [
                ("O desfecho e o próximo passo como próxima tarefa, com a data e a hora aceitas", True),
                ("Nada: o Meet já grava tudo", False),
                ("Só uma observação sem data", False),
                ("Só o valor da proposta", False),
            ],
        },
        {
            "enunciado": "Onde fica, dentro da reunião na Agenda, o resumo do scorecard com exemplos de fala?",
            "alternativas": [
                ("No botão Guia do roteiro", True),
                ("Na aba Dados públicos da conta", False),
                ("No Monitor de parede", False),
                ("Só no PDF da UC", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# A trilha
# ═════════════════════════════════════════════════════════════════════

TECNICA_06_FECHAMENTO = {
    "id": _id("b0900"),
    "titulo": "06 · Fechamento: os três 10 e como pedir o sim",
    "pilar": "tecnica",
    "reforca": "roteiro",
    "descricao": (
        "O aprofundamento do fechamento: os três 10 do método Linha Reta, de "
        "Jordan Belfort (o cliente só decide seguro do produto, de quem vende "
        "e da empresa), como medir e subir cada certeza, limiar de ação e dor, "
        "o looping junto com o LAER, as técnicas de fechamento e o passo a "
        "passo dos 3 minutos finais da reunião na Controller. Cada aula termina "
        "com exercício e role-play em dupla, com critérios de avaliação."
    ),
    "prazo_dias": 52,
    "obrigatorios": OBRIGATORIOS,
    "opcionais": OPCIONAIS,
    "aulas": [AULA_1, AULA_2, AULA_3, AULA_4, AULA_5, AULA_6, AULA_7],
}

TRILHAS_FECHAMENTO: list[dict] = [TECNICA_06_FECHAMENTO]
