"""
HIPO — UC: 04 · Técnicas do SDR na prática (pilar Técnica).

  04 · Técnicas do SDR na prática   obrigatória para SDR (prazo 55 dias)

ADM e Franqueado veem sem obrigação.

Pedido do Tulio (05/10/2026): "com base no script de SDR, monte um curso
das técnicas apresentadas no script, detalhando e ensinando a executar as
técnicas". Decisões dele: só a trilha no HIPO (sem PDF) e, em cada
técnica, exercício + role-play.

O Método 02 é o ROTEIRO (o que dizer, em que ordem). Este é o TREINO de
cada técnica que o roteiro usa: o que é, por que funciona, o passo a passo,
o certo e o errado, os erros comuns, um exercício individual e um role-play
em dupla com critérios de avaliação. Os fatos (credencial, gancho da NR-01,
cadência D0–D12, critério decisor + interesse, as cinco linhas do bastão)
são os do Método 02; nada de número novo.

Prazo de 55 dias: depois do Método 02 (50) e antes da Energia 01 (60). A
prova é o quiz final da trilha (sorteia 10 do banco de 7 de cada aula).

Este arquivo é só dado. Quem grava é scripts/semear_uc.py.
"""
from __future__ import annotations

from uuid import UUID

GESTAO_OPCIONAL = ("ADM", "Franqueado")


def _id(sufixo: str) -> UUID:
    return UUID(f"7c1d0f4e-5a01-4c0e-9b11-0000000{sufixo}")


def _passo(rota, alvo, titulo, texto, clicar=None):
    p = {"rota": rota, "alvo": alvo, "titulo": titulo, "texto": texto}
    if clicar:
        p["clicar"] = list(clicar)
    return p


# ═════════════════════════════════════════════════════════════════════
# Aula 1 — Pesquisa de três minutos e hipótese de dor
# ═════════════════════════════════════════════════════════════════════

AULA_1 = {
    "id": _id("b0711"),
    "titulo": "Técnica 1 · Pesquisa de três minutos e hipótese de dor",
    "resumo": "Ler a conta no HIPO com um roteiro fixo e sair dela com uma hipótese de dor escrita em uma frase.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

A pesquisa de três minutos é a leitura rápida da empresa **antes de discar**. Ela termina numa coisa só: **uma hipótese de dor escrita em uma frase**. A hipótese é um palpite sobre o problema que aquela empresa provavelmente tem, e é ela que vira o motivo da sua ligação e a sua primeira pergunta.

## Por que funciona

- **Troca o "estou ligando para apresentar" por um assunto do cliente.** Quem ouve um assunto dele responde; quem ouve uma apresentação desliga.
- **Cabe no seu volume.** O SDR faz dezenas de contatos por dia. Três minutos por empresa é o que o dia comporta; trinta minutos não.
- **Mesmo errada, a hipótese ajuda.** Se o cliente diz "isso não é problema aqui", ele costuma dizer qual é. Você ganhou a informação do mesmo jeito.

## Passo a passo (cronometre)

1. **0:00 a 0:30 · O que a empresa faz.** Na conta, aba **Dados públicos**: atividade e CNAE.
2. **0:30 a 1:00 · O risco.** O **grau de risco (NR-4)**, de 1 a 4. Quanto maior, mais exames e programas obrigatórios.
3. **1:00 a 1:30 · O tamanho e o desenho.** Porte, nº de funcionários (da fonte é **estimativa**, use só para se orientar), cidade, **matriz ou filial**. Várias unidades puxam o argumento de atendimento único.
4. **1:30 a 2:00 · Quem procurar.** Até uns 20 funcionários: dono ou sócio (veja os **Sócios**). Médio porte: RH ou DP. Indústria e obra: técnico ou engenheiro de segurança, com o gerente da planta ou o dono decidindo. Rede: RH corporativo.
5. **2:00 a 3:00 · Escreva a hipótese.** Uma frase na **Descrição** da oportunidade, no formato: *"[perfil]: provável [dor]; procurar [quem]; perguntar [pergunta]"*.

## As três hipóteses de partida

- **Varejo e alimentação com várias lojas**: turnover alto, admissional demorado atrasando o início do funcionário, cada loja com um fornecedor.
- **Indústria e construção (grau 3 e 4)**: PGR e LTCAT desatualizados, exames complementares (audiometria, espirometria), NR-35 e NR-10.
- **Escritório e serviços (grau 1 e 2)**: "acha que não tem risco"; PGR sem os riscos psicossociais; eSocial de SST enviado com erro.

E o gancho que vale para todas: desde **26/05/2026** a NR-01 exige os **fatores de risco psicossociais** no PGR, e muita empresa não revisou.

## Certo e errado

- **Errado:** "Rede de padarias, 4 unidades, Guarulhos." É um resumo, não uma hipótese.
- **Errado:** passar dez minutos no site da empresa lendo a história do fundador.
- **Certo:** "Varejo de alimentação, 4 lojas: provável admissional demorado e um fornecedor por loja; procurar o RH; perguntar quanto tempo leva hoje para um contratado começar."
- **Certo:** "Escritório contábil, grau 1: provável PGR sem psicossocial; procurar o sócio; perguntar se o PGR já foi revisado com a parte nova."

## Erros comuns

- **Pesquisar demais.** Passou dos três minutos, ligue com o que tem.
- **Não escrever.** Hipótese só na cabeça some na terceira ligação do dia e não chega ao EV.
- **Tratar estimativa como dado.** O nº de funcionários da fonte não vai para a fala ("vocês têm 47 funcionários"); vira pergunta ("quantos vocês são hoje?").
- **Hipótese em forma de afirmação.** "Vocês estão irregulares" é acusação. Hipótese vira **pergunta**.

## Exercício (individual, 15 minutos)

Pegue **cinco empresas** da sua fila de primeiro contato. Para cada uma, cronometre três minutos e escreva a hipótese na Descrição, no formato da aula. No fim, releia as cinco e marque as que viraram **pergunta** que o cliente consegue responder em uma frase. A meta é cinco de cinco.

## Role-play em dupla (10 minutos)

- **Quem faz o SDR** recebe o nome de uma empresa da base e tem três minutos no HIPO para escrever a hipótese.
- **Quem faz o avaliador** cronometra e, no fim, lê a hipótese em voz alta.
- Troquem de papel com outra empresa.

**Critérios (o avaliador marca sim ou não):**

1. Terminou em até três minutos.
2. A hipótese cita o perfil (atividade, risco ou desenho).
3. A dor é uma das hipóteses de partida, ou outra que os dados sustentam.
4. Termina numa pergunta que o cliente responde em uma frase.
5. Indica quem procurar.

> Ligação sem hipótese vira "estou ligando para apresentar a Controller". Ligação com hipótese vira uma pergunta que o cliente quer responder.
""",
    "tour": [
        _passo("/crm/contas", "con-360-topo", "Os três minutos começam aqui",
               "A conta: vertical, nº de funcionários (estimativa) e situação.",
               clicar=["con-linha"]),
        _passo("/crm/contas", "con-360-topo", "Atividade e risco",
               "Aba **Dados públicos**: CNAE, atividade e **grau de risco (NR-4)**. Daqui sai a hipótese.",
               clicar=["con-linha", "aba-dados-publicos"]),
        _passo("/crm/oportunidades", "opo-det-conteudo", "Onde a hipótese fica escrita",
               "Na oportunidade, aba **Dados**, campo **Descrição**: a hipótese em uma frase.",
               clicar=["opo-cartao-abrir", "aba-dados"]),
    ],
    "quiz": [
        {
            "enunciado": "Em que termina a pesquisa de três minutos?",
            "alternativas": [
                ("Numa hipótese de dor escrita em uma frase", True),
                ("Num resumo completo da história da empresa", False),
                ("Na lista de todos os sócios e filiais", False),
                ("Numa proposta de preço para mandar depois", False),
            ],
        },
        {
            "enunciado": "Onde a hipótese deve ficar escrita, segundo a aula?",
            "alternativas": [
                ("Num caderno pessoal do SDR", False),
                ("Na Descrição da oportunidade", True),
                ("No WhatsApp do EV", False),
                ("Em lugar nenhum: basta lembrar na hora", False),
            ],
        },
        {
            "enunciado": "A fonte diz que a empresa tem 47 funcionários. Como usar esse número na ligação?",
            "alternativas": [
                ("Afirmar: \"vocês têm 47 funcionários\"", False),
                ("Ignorar a empresa, porque o dado pode estar errado", False),
                ("Transformar em pergunta: \"quantos vocês são hoje?\"", True),
                ("Usar o número para calcular o preço na hora", False),
            ],
        },
        {
            "enunciado": "Qual destas é uma hipótese de dor bem escrita?",
            "alternativas": [
                ("\"Rede de padarias, 4 unidades, Guarulhos.\"", False),
                ("\"Vocês estão irregulares com a NR-01.\"", False),
                ("\"Empresa interessante, ligar de manhã.\"", False),
                ("\"Varejo, 4 lojas: provável admissional demorado; procurar o RH; perguntar quanto tempo leva para um contratado começar.\"", True),
            ],
        },
        {
            "enunciado": "Para uma indústria de grau de risco 3 ou 4, qual é a hipótese de partida da aula?",
            "alternativas": [
                ("PGR e LTCAT desatualizados e exames complementares", True),
                ("Achar que não tem risco nenhum", False),
                ("Turnover alto em várias lojas", False),
                ("Falta de sistema de ponto eletrônico", False),
            ],
        },
        {
            "enunciado": "Numa empresa com uns 15 funcionários, quem a aula indica procurar?",
            "alternativas": [
                ("O RH corporativo", False),
                ("O dono ou sócio", True),
                ("O técnico de segurança", False),
                ("O contador da empresa", False),
            ],
        },
        {
            "enunciado": "Passaram os três minutos e você ainda não achou tudo o que queria. O que fazer?",
            "alternativas": [
                ("Pesquisar mais dez minutos no site da empresa", False),
                ("Pular a empresa e voltar outro dia", False),
                ("Ligar com o que tem, com a hipótese escrita", True),
                ("Pedir ao EV que pesquise por você", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 2 — Abertura com permissão e o motivo
# ═════════════════════════════════════════════════════════════════════

AULA_2 = {
    "id": _id("b0712"),
    "titulo": "Técnica 2 · Abertura com permissão e o motivo em uma frase",
    "resumo": "Os primeiros 35 segundos da ligação fria: pedir licença, dar a credencial e dizer por que você ligou, ligado à hipótese.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

São as duas primeiras partes da ligação fria do Roteiro do SDR:

1. **Abertura com permissão (15 s):** você se apresenta e **pede licença** para falar.
2. **O motivo (20 s):** **uma** frase de credencial e **uma** frase de motivo, ligada à sua hipótese.

Em 35 segundos o cliente precisa saber quem você é, por que ligou e que a conversa vai ser curta.

## Por que funciona

- **Pedir permissão baixa a guarda.** Quem é interrompido sem aviso se defende; quem é consultado tende a ceder dois minutos.
- **Dar a saída ("te peguei num momento ruim?") aumenta o sim.** A pessoa sente que escolheu continuar.
- **Credencial curta dá motivo para ouvir;** credencial longa vira propaganda.
- **O motivo ligado à hipótese** faz a ligação ser sobre o cliente, não sobre a Controller.

## Passo a passo

**Abertura, palavra por palavra:**

> "Oi, [nome], aqui é [seu nome], da Controller Medicina e Segurança do Trabalho, de Guarulhos. Te peguei num momento ruim, ou você me dá dois minutos?"

- Diga o **nome da pessoa** primeiro. Se não sabe o nome, é recepção (técnica 5).
- **Pare depois da pergunta.** O silêncio é dele. Não emende "é rapidinho".
- **Momento ruim?** "Sem problema. Qual o melhor horário para eu te ligar, amanhã de manhã ou à tarde?" Marque a tarefa com essa hora e desligue. Você não perdeu a ligação: ganhou um horário combinado.

**Motivo, palavra por palavra:**

> "A gente cuida de saúde e segurança do trabalho de mais de 500 empresas. Estou ligando porque, desde maio, a NR-01 passou a exigir os riscos psicossociais no PGR, e muita empresa do seu porte ainda não revisou."

A primeira frase (credencial) é fixa. A segunda (motivo) **troca conforme a hipótese**:

- **Varejo com lojas:** "...porque em rede de loja o admissional costuma atrasar o início do funcionário, e queria entender como está aí."
- **Indústria grau 3 e 4:** "...porque com a NR-01 nova muita indústria está revisando PGR e LTCAT, e queria saber como está o de vocês."

## Certo e errado

- **Errado:** "Bom dia, tudo bem? Eu sou da Controller, a gente é uma empresa que faz medicina do trabalho, segurança, exames, PGR, PCMSO, treinamentos, e eu estou ligando para apresentar..." (40 segundos de monólogo, nenhuma pergunta).
- **Errado:** "Posso tomar só um minutinho do seu tempo?" sem dizer quem é.
- **Certo:** nome dele, seu nome, empresa, pergunta de permissão, **silêncio**. Depois, credencial + motivo em duas frases.

## Erros comuns

- **Pular a permissão** porque "a pessoa vai dizer não". Ela diz não **mais** quando não é consultada.
- **Credencial em lista** (anos, vidas, clientes, serviços). Uma frase basta; a apresentação é do EV.
- **"Estou ligando para apresentar a Controller."** É o motivo que faz desligar.
- **Falar rápido para "aproveitar" os dois minutos.** Ritmo calmo transmite segurança.

## Exercício (individual, 20 minutos)

1. Grave no celular a sua abertura e o seu motivo, três vezes, com três hipóteses diferentes (varejo, indústria, escritório).
2. Ouça e cronometre. Abertura até 15 s; motivo até 20 s.
3. Marque onde você emendou depois da pergunta de permissão, em vez de esperar a resposta. Grave de novo até não emendar.

## Role-play em dupla (15 minutos)

**Cenário:** o "cliente" é sócio de uma empresa de serviços com uns 30 funcionários. Ele atende sem saber quem é.

Rodadas de 1 minuto, trocando o comportamento do cliente:

1. Cliente receptivo: "pode falar".
2. Cliente apressado: "estou entrando numa reunião".
3. Cliente seco: "do que se trata?"

**Critérios (o avaliador marca sim ou não):**

1. Disse o nome do cliente, o próprio nome e a Controller.
2. Pediu permissão e **esperou** a resposta.
3. No "momento ruim", combinou um horário com duas opções.
4. Credencial em uma frase.
5. Motivo ligado à hipótese, sem "apresentar a Controller".
6. Abertura + motivo em até 35 segundos.

> Os primeiros segundos não vendem nada. Eles só compram os próximos dois minutos.
""",
    "quiz": [
        {
            "enunciado": "Quanto tempo a aula dá para a abertura com permissão?",
            "alternativas": [
                ("Uns 15 segundos", True),
                ("Uns 2 minutos", False),
                ("O tempo que o cliente quiser", False),
                ("Uns 5 segundos", False),
            ],
        },
        {
            "enunciado": "Você perguntou \"te peguei num momento ruim, ou você me dá dois minutos?\". O que fazer em seguida?",
            "alternativas": [
                ("Emendar \"é rapidinho\" antes que ele responda", False),
                ("Ficar em silêncio e esperar a resposta", True),
                ("Começar a apresentar os serviços", False),
                ("Repetir a pergunta mais alto", False),
            ],
        },
        {
            "enunciado": "O cliente diz que é um momento ruim. Qual é a conduta da aula?",
            "alternativas": [
                ("Insistir: \"são só dois minutos\"", False),
                ("Desligar e tirar a empresa da fila", False),
                ("Mandar a proposta por e-mail", False),
                ("Combinar um horário com duas opções e marcar a tarefa com essa hora", True),
            ],
        },
        {
            "enunciado": "Quantas frases tem o motivo da ligação?",
            "alternativas": [
                ("Uma de credencial e uma de motivo", True),
                ("Uma lista com todos os serviços", False),
                ("Nenhuma: vai direto para o preço", False),
                ("Cinco, uma para cada parte da ligação", False),
            ],
        },
        {
            "enunciado": "Qual frase a aula manda evitar como motivo da ligação?",
            "alternativas": [
                ("\"Desde maio a NR-01 exige os riscos psicossociais no PGR.\"", False),
                ("\"Em rede de loja o admissional costuma atrasar.\"", False),
                ("\"Estou ligando para apresentar a Controller.\"", True),
                ("\"Queria saber como está o PGR de vocês.\"", False),
            ],
        },
        {
            "enunciado": "Na frase de motivo, o que muda de uma empresa para outra?",
            "alternativas": [
                ("O nome da Controller", False),
                ("A credencial de mais de 500 empresas", False),
                ("Nada: a frase é sempre a mesma", False),
                ("A parte ligada à hipótese de dor do perfil", True),
            ],
        },
        {
            "enunciado": "Por que pedir permissão no começo funciona, segundo a aula?",
            "alternativas": [
                ("Porque obriga o cliente a ouvir até o fim", False),
                ("Porque baixa a guarda: quem é consultado tende a ceder dois minutos", True),
                ("Porque é exigência da LGPD", False),
                ("Porque o cliente sempre diz sim", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 3 — Perguntar e escutar
# ═════════════════════════════════════════════════════════════════════

AULA_3 = {
    "id": _id("b0713"),
    "titulo": "Técnica 3 · Perguntar, escutar e anotar as palavras do cliente",
    "resumo": "A pergunta de situação, a segunda pergunta só se couber, a regra dos 30 segundos e como anotar o que o EV vai usar.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

É a terceira parte da ligação fria (30 s): **uma pergunta**, a escuta, e uma segunda pergunta **só se couber**. Junto vem a regra de ouro do Roteiro do SDR: **quem pergunta conduz**. Se você está falando há mais de 30 segundos seguidos, pare e pergunte.

## Por que funciona

- **Pergunta transforma monólogo em conversa.** Quem responde se envolve; quem só ouve se defende.
- **A primeira pergunta é fácil de propósito.** "Quem cuida disso hoje?" se responde sem pensar, e a resposta já diz muito (fornecedor, interno ou contador).
- **As palavras exatas do cliente valem ouro para o EV.** Ele abre a reunião usando o que o cliente disse, e o cliente percebe que alguém escutou.

## Passo a passo

**A pergunta de situação (sempre a mesma):**

> "Hoje quem cuida disso para vocês, um fornecedor, alguém interno ou o contador?"

Ela já traz as três respostas possíveis. O cliente só escolhe.

**Escutar de verdade:**

1. Deixe terminar. Conte "um, dois" em silêncio depois que ele parar: muita gente completa o raciocínio nesse intervalo.
2. Reaja com uma palavra que mostre que ouviu ("entendi", "faz sentido") e **repita uma palavra dele**: "Fornecedor que atende a matriz e as lojas, então."
3. Anote **as palavras exatas**, entre aspas, não o seu resumo.

**A segunda pergunta, só se couber:**

> "E o PGR de vocês já foi revisado com essa parte nova?"

Cabe quando o cliente está falando à vontade. Não cabe quando ele está com pressa: aí você vai direto ao pedido (técnica 4).

**Anotar para o EV:** na **Descrição** da oportunidade, as frases do cliente entre aspas. Exemplo: *"o fornecedor demora uma semana para agendar o admissional"*. Essa frase vira a linha 2 do bastão (técnica 9).

## Certo e errado

- **Errado:** "Vocês sabem que a NR-01 mudou, né? Então, a gente faz PGR, PCMSO, LTCAT, treinamentos... e o nosso diferencial é..." (você falou um minuto, o cliente nenhum segundo).
- **Errado:** "Vocês estão satisfeitos com o fornecedor atual?" (pergunta de sim ou não, que fecha a conversa).
- **Certo:** "Hoje quem cuida disso para vocês...?" — silêncio — "Entendi, o contador. E o PGR já foi revisado com a parte nova?"

## Erros comuns

- **Fazer a pergunta e responder por ele** ("...imagino que seja o contador, né?").
- **Emendar três perguntas seguidas.** Uma por vez.
- **Anotar o resumo em vez da frase.** "Cliente insatisfeito" não ajuda o EV; "o fornecedor demora uma semana" ajuda.
- **Corrigir o cliente.** Se ele diz algo impreciso sobre a norma, você planta a dúvida e deixa o EV responder.

## Exercício (individual, 15 minutos)

Ouça uma gravação ou transcrição de reunião (ou peça uma à gestão). Em cada trecho em que o cliente fala do problema dele, copie **a frase exata** entre aspas. Depois, escreva como você resumiria a mesma coisa. Compare: qual das duas o EV usaria na abertura da reunião?

## Role-play em dupla (15 minutos)

**Cenário:** o "cliente" é o RH de uma indústria de 80 funcionários. O avaliador entrega a ele, num papel, a situação real: *"fornecedor atual, atende bem a matriz, mas os exames complementares demoram; PGR não foi revisado"*. O SDR não vê o papel.

O SDR tem 2 minutos para descobrir o máximo **só perguntando**. O avaliador cronometra quanto tempo o SDR fala seguido.

**Critérios (o avaliador marca sim ou não):**

1. Abriu com a pergunta de situação.
2. Esperou o cliente terminar antes de falar.
3. Repetiu uma palavra do cliente.
4. Nenhum trecho do SDR passou de 30 segundos seguidos.
5. Fez a segunda pergunta só depois de ouvir a primeira resposta.
6. Anotou pelo menos duas frases exatas, entre aspas.
7. Descobriu a situação do papel (quem cuida, o que incomoda, se o PGR foi revisado).

> Regra de ouro: quem pergunta conduz. Se você está falando há mais de 30 segundos seguidos, pare e pergunte.
""",
    "quiz": [
        {
            "enunciado": "Qual é a pergunta de situação da ligação fria?",
            "alternativas": [
                ("\"Vocês estão satisfeitos com o fornecedor atual?\"", False),
                ("\"Hoje quem cuida disso para vocês, um fornecedor, alguém interno ou o contador?\"", True),
                ("\"Quanto vocês pagam hoje?\"", False),
                ("\"Posso te mandar uma apresentação?\"", False),
            ],
        },
        {
            "enunciado": "O que diz a regra de ouro do SDR?",
            "alternativas": [
                ("Quem pergunta conduz: falou mais de 30 segundos seguidos, pare e pergunte", True),
                ("Quem fala mais convence mais", False),
                ("Nunca faça mais de uma pergunta por ligação", False),
                ("Responda pelo cliente para ganhar tempo", False),
            ],
        },
        {
            "enunciado": "Quando cabe a segunda pergunta (\"o PGR já foi revisado com a parte nova?\")?",
            "alternativas": [
                ("Sempre, antes mesmo da primeira", False),
                ("Nunca: é papel do EV", False),
                ("Só se couber: quando o cliente está falando à vontade", True),
                ("Só depois de marcar a reunião", False),
            ],
        },
        {
            "enunciado": "O que anotar na Descrição da oportunidade?",
            "alternativas": [
                ("Um resumo seu, como \"cliente insatisfeito\"", False),
                ("Só o nome e o telefone", False),
                ("O preço que o cliente paga hoje", False),
                ("As palavras exatas do cliente, entre aspas", True),
            ],
        },
        {
            "enunciado": "Por que \"Vocês estão satisfeitos com o fornecedor atual?\" é um exemplo errado?",
            "alternativas": [
                ("Porque é pergunta de sim ou não, que fecha a conversa", True),
                ("Porque fala mal do concorrente", False),
                ("Porque é longa demais", False),
                ("Porque deveria ser feita só pelo EV", False),
            ],
        },
        {
            "enunciado": "O cliente terminou de falar. Qual é a técnica de escuta da aula?",
            "alternativas": [
                ("Interromper com a próxima pergunta na hora", False),
                ("Contar \"um, dois\" em silêncio e depois reagir repetindo uma palavra dele", True),
                ("Explicar a norma para corrigir o que ele disse", False),
                ("Ler a lista de serviços da Controller", False),
            ],
        },
        {
            "enunciado": "O cliente diz algo impreciso sobre a NR-01. O que o SDR faz?",
            "alternativas": [
                ("Corrige na hora com o texto da norma", False),
                ("Desliga, porque o cliente não entende do assunto", False),
                ("Concorda para não criar atrito e muda de assunto", False),
                ("Planta a dúvida e deixa o EV responder na reunião", True),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 4 — Pedido com duas opções e confirmação
# ═════════════════════════════════════════════════════════════════════

AULA_4 = {
    "id": _id("b0714"),
    "titulo": "Técnica 4 · O pedido com duas opções e a confirmação",
    "resumo": "Pedir a reunião com o especialista em uma frase, oferecer dois horários e fechar os cinco dados antes de desligar.",
    "duracao_min": 11,
    "conteudo_md": """\
## O que é

São as duas últimas partes da ligação fria:

- **O pedido (20 s):** você pede 30 minutos com o especialista, sem compromisso, e oferece **dois horários**.
- **A confirmação (20 s):** antes de desligar, você fecha os dados que fazem a reunião acontecer.

O critério para pedir é o do Roteiro do SDR: **decisor + interesse**. Você não precisa saber tudo; precisa estar falando com quem decide (ou leva a conversa para quem decide) e ter percebido abertura.

## Por que funciona

- **Duas opções de horário recebem mais "sim" do que "quando você pode?".** A pergunta aberta pede ao cliente que pense na agenda inteira; a escolha entre dois horários pede só que ele escolha.
- **"Sem compromisso" e "30 minutos" diminuem o tamanho do pedido.** Ninguém está comprando nada; está só ouvindo um especialista.
- **Quem pede uma coisa só recebe resposta.** Pedido em três partes ("posso mandar material, ligar depois e marcar?") vira "manda o material".

## Passo a passo

**O pedido, palavra por palavra:**

> "Faz sentido um especialista nosso olhar isso com você em 30 minutos, sem compromisso? Terça às 10h ou quarta às 15h, o que fica melhor?"

- **"Isso"** é a dor que o cliente acabou de dizer. Se ele falou do admissional, é o admissional.
- Antes de ligar, **olhe a Agenda do EV** e escolha dois horários livres dele, em dias diferentes.
- Depois da pergunta, **silêncio**.

**Se nenhum dos dois serve:** "Qual dia da semana costuma ser melhor para você, de manhã ou à tarde?" Volte com dois horários dentro do que ele disse.

**A confirmação, item por item:**

1. **Nome completo, cargo, e-mail e celular** do decisor.
2. **Quem mais participa da decisão:** "Mais alguém precisa estar?"
3. **Online ou presencial.**
4. **O fechamento em voz alta:**

> "Combinado: [dia] às [hora], com o [EV]. Vou te mandar o convite agora por e-mail. Se aparecer um imprevisto, me avisa por este número?"

Mande o convite **ainda com o cliente na linha ou logo depois**, marcando a reunião na Agenda do EV.

## Certo e errado

- **Errado:** "Quando seria um bom momento para a gente conversar?" (pergunta aberta: "me liga semana que vem").
- **Errado:** "Posso te mandar uma proposta?" (proposta sai da reunião, nunca antes).
- **Errado:** marcar e desligar sem e-mail, sem celular e sem saber quem mais decide.
- **Certo:** pedido de 30 minutos com o especialista, dois horários, silêncio, e a confirmação completa: contato do decisor, quem mais decide, online ou presencial e o fechamento em voz alta.

## Erros comuns

- **Falar preço para "facilitar" o sim.** O preço depende de vidas, grau de risco e escopo; quem dá número no telefone perde a reunião e erra o valor.
- **Oferecer horário que o EV não tem.** Olhe a Agenda antes.
- **Não perguntar quem mais decide.** O sócio que não estava na reunião é o "vou ver com meu sócio" do fim.
- **Esquecer o "me avisa por este número?".** É ele que transforma um imprevisto em remarcação, em vez de no-show.

## Exercício (individual, 10 minutos)

Abra a Agenda e escolha um EV. Escreva **três pedidos completos**, cada um com dois horários livres reais dele, em dias diferentes, e com "isso" trocado por uma dor diferente (admissional, PGR psicossocial, exames complementares). Leia em voz alta: cada pedido deve caber em 20 segundos.

## Role-play em dupla (15 minutos)

**Cenário:** o "cliente" já respondeu às perguntas e demonstrou interesse. O avaliador escolhe, sem contar, uma reação para o pedido:

1. Aceita um dos horários.
2. "Nenhum desses dá."
3. "Me manda uma proposta antes."

**Critérios (o avaliador marca sim ou não):**

1. Pediu com "30 minutos", "especialista" e "sem compromisso".
2. Ofereceu dois horários, em dias diferentes.
3. Ficou em silêncio depois do pedido.
4. Em "nenhum dá", perguntou o melhor dia e período e voltou com duas opções.
5. Em "manda proposta", não prometeu proposta e voltou ao pedido da conversa.
6. Confirmou nome, cargo, e-mail, celular, quem mais decide e se é online ou presencial.
7. Fechou com dia, hora, nome do EV e "me avisa por este número?".

> Quem pede uma coisa só, com duas opções, recebe uma resposta. Quem pede "um momento", recebe "me liga depois".
""",
    "quiz": [
        {
            "enunciado": "Qual é o pedido de reunião ensinado na aula?",
            "alternativas": [
                ("\"Quando seria um bom momento para a gente conversar?\"", False),
                ("\"Posso te mandar uma proposta?\"", False),
                ("\"Faz sentido um especialista olhar isso em 30 minutos, sem compromisso? Terça às 10h ou quarta às 15h?\"", True),
                ("\"Você tem interesse em conhecer todos os nossos serviços?\"", False),
            ],
        },
        {
            "enunciado": "Por que oferecer dois horários em vez de perguntar \"quando você pode?\"",
            "alternativas": [
                ("Porque escolher entre dois é mais fácil que pensar na agenda inteira", True),
                ("Porque o cliente não pode recusar", False),
                ("Porque o EV só trabalha nesses horários", False),
                ("Porque é regra do Google Agenda", False),
            ],
        },
        {
            "enunciado": "O cliente diz que nenhum dos dois horários serve. O que fazer?",
            "alternativas": [
                ("Desistir e marcar a empresa como perdida", False),
                ("Pedir que ele mande os horários por e-mail", False),
                ("Oferecer o primeiro horário livre de qualquer EV", False),
                ("Perguntar o melhor dia e período e voltar com duas opções dentro disso", True),
            ],
        },
        {
            "enunciado": "Qual destes itens faz parte da confirmação antes de desligar?",
            "alternativas": [
                ("O faturamento da empresa", False),
                ("Quem mais participa da decisão", True),
                ("O preço que o cliente paga hoje", False),
                ("O CNPJ do fornecedor atual", False),
            ],
        },
        {
            "enunciado": "O cliente pergunta o preço antes de aceitar a reunião. Qual é a conduta?",
            "alternativas": [
                ("Dar uma faixa de preço para facilitar o sim", False),
                ("Dizer que é barato e mudar de assunto", False),
                ("Não dar número: o preço depende de vidas, risco e escopo, e sai na reunião", True),
                ("Prometer o menor preço do mercado", False),
            ],
        },
        {
            "enunciado": "O que deve ser olhado antes de oferecer os dois horários?",
            "alternativas": [
                ("A Agenda do EV, para oferecer horários livres dele", True),
                ("O LinkedIn do cliente", False),
                ("O ranking de vendas do mês", False),
                ("O relatório de no-show", False),
            ],
        },
        {
            "enunciado": "Por que fechar com \"Se aparecer um imprevisto, me avisa por este número?\"",
            "alternativas": [
                ("Para conseguir o celular pessoal do cliente", False),
                ("Para poder ligar todo dia até a reunião", False),
                ("Porque é exigência do contrato", False),
                ("Para um imprevisto virar remarcação em vez de no-show", True),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 5 — Passar pela recepção
# ═════════════════════════════════════════════════════════════════════

AULA_5 = {
    "id": _id("b0715"),
    "titulo": "Técnica 5 · Passar pela recepção e chegar ao decisor",
    "resumo": "Pedir pelo setor, ser honesto e breve, e transformar a recepção em aliada que diz o nome certo e o melhor horário.",
    "duracao_min": 10,
    "conteudo_md": """\
## O que é

Na maior parte das empresas acima de uns 20 funcionários, quem atende não é o decisor: é a recepção, uma telefonista ou um ramal geral. A técnica é **chegar à pessoa certa com a ajuda de quem atende**, e não apesar dela.

## Por que funciona

- **Quem atende sabe quem cuida de quê.** É a pessoa mais bem informada da empresa sobre "com quem falo".
- **Pedir pelo setor soa como assunto de trabalho;** pedir "o responsável" soa como venda.
- **Honestidade breve gera ajuda;** truque gera bloqueio, e a recepção se lembra de você na próxima ligação.

## Passo a passo

1. **Cumprimente e pergunte o nome de quem atendeu.** "Bom dia, com quem eu falo?" Use o nome dali em diante.
2. **Peça pelo setor, não pela venda:**

> "Com quem falo sobre os exames dos funcionários? É o RH?"

Varie conforme o perfil: "sobre o PGR de vocês, é o técnico de segurança?", "sobre saúde ocupacional das lojas, é o RH da matriz?".

3. **Se perguntarem do que se trata, seja honesto e breve:**

> "Sou da Controller, de medicina e segurança do trabalho. É sobre a revisão do PGR que a NR-01 passou a exigir."

4. **Se a pessoa não estiver ou não puder atender, colete três coisas:** o **nome** da pessoa certa, o **cargo** e o **melhor horário** para ligar. Se der, o ramal ou o e-mail.
5. **Agradeça pelo nome** e registre tudo na oportunidade: o nome de quem atendeu, o nome do decisor e o horário. A próxima tarefa da cadência vai ser **naquele horário**.

## Certo e errado

- **Errado:** "É particular." / "Ele me pediu para ligar." (mentira descoberta na primeira frase do decisor, e a recepção não passa mais a sua ligação).
- **Errado:** "Quero falar com o responsável." (soa como venda e recebe "ele não está").
- **Errado:** desligar sem o nome de ninguém.
- **Certo:** "Bom dia, com quem eu falo? ... Obrigado, Marta. Com quem falo sobre os exames dos funcionários, é o RH? ... Qual o melhor horário para encontrar a Juliana?"

## Erros comuns

- **Tratar a recepção como obstáculo.** Ela vai atender você de novo no D3 e no D8 da cadência.
- **Explicar tudo para a recepção.** Uma frase. A conversa é com o decisor.
- **Não registrar o que descobriu.** O nome do decisor e o melhor horário são a informação mais cara da ligação.
- **Ligar de novo no mesmo horário em que ele "nunca está".** Use o horário que a recepção indicou.

## Exercício (individual, 10 minutos)

Escreva, para três perfis (varejo com lojas, indústria grau 3, escritório de serviços), a sua **frase de setor** ("com quem falo sobre...?") e a sua **frase honesta** ("é sobre..."). Cada uma em uma frase curta, de até 25 palavras.

## Role-play em dupla (15 minutos)

**Cenário:** o "cliente" é a recepção de uma indústria com 80 funcionários. O avaliador escolhe, sem contar, uma postura:

1. Prestativa: passa a ligação.
2. Protetora: "do que se trata?" e "ele está em reunião".
3. Bloqueio firme: "não passamos ligação de fornecedor".

**Critérios (o avaliador marca sim ou não):**

1. Perguntou e usou o nome de quem atendeu.
2. Pediu pelo setor, não "pelo responsável".
3. Explicou o motivo em uma frase honesta.
4. Sem truque ("é particular", "ele pediu").
5. Saiu com nome e cargo da pessoa certa.
6. Saiu com o melhor horário para ligar (ou e-mail).
7. Agradeceu pelo nome.

> A recepção que barra é aliada: ela sabe o nome certo e o melhor horário. Pergunte, agradeça e ligue na hora que ela disse.
""",
    "quiz": [
        {
            "enunciado": "Como a aula manda pedir a ligação para a recepção?",
            "alternativas": [
                ("\"Quero falar com o responsável.\"", False),
                ("\"Com quem falo sobre os exames dos funcionários? É o RH?\"", True),
                ("\"É particular, pode passar?\"", False),
                ("\"Ele me pediu para ligar.\"", False),
            ],
        },
        {
            "enunciado": "A recepção pergunta do que se trata. O que responder?",
            "alternativas": [
                ("Uma frase honesta: quem você é e o assunto", True),
                ("Que é um assunto pessoal", False),
                ("A apresentação completa da Controller", False),
                ("Que você só fala com o dono", False),
            ],
        },
        {
            "enunciado": "O decisor não está. Quais três coisas você tenta sair sabendo?",
            "alternativas": [
                ("O faturamento, o fornecedor e o preço atual", False),
                ("O CNPJ, o endereço e o horário de almoço", False),
                ("O nome da pessoa certa, o cargo e o melhor horário para ligar", True),
                ("O e-mail do dono, do contador e do RH", False),
            ],
        },
        {
            "enunciado": "Por que não usar \"é particular\" ou \"ele me pediu para ligar\"?",
            "alternativas": [
                ("Porque demora mais", False),
                ("Porque é proibido por lei", False),
                ("Porque o decisor não atende ligação particular", False),
                ("Porque a mentira é descoberta e a recepção deixa de passar suas ligações", True),
            ],
        },
        {
            "enunciado": "Qual é a primeira coisa a fazer quando a recepção atende?",
            "alternativas": [
                ("Cumprimentar e perguntar o nome de quem atendeu", True),
                ("Pedir o celular do dono", False),
                ("Explicar a NR-01 em detalhe", False),
                ("Pedir para falar com o responsável", False),
            ],
        },
        {
            "enunciado": "A recepção disse que a decisora costuma estar livre depois das 16h. O que fazer com isso?",
            "alternativas": [
                ("Ligar de novo amanhã às 9h, para variar", False),
                ("Registrar e marcar a próxima tarefa da cadência nesse horário", True),
                ("Mandar um áudio longo para a recepção", False),
                ("Ignorar e seguir a ordem da fila", False),
            ],
        },
        {
            "enunciado": "Por que a aula diz que a recepção é aliada?",
            "alternativas": [
                ("Porque ela decide a contratação de SST", False),
                ("Porque ela recebe comissão pela indicação", False),
                ("Porque ela pode assinar o contrato", False),
                ("Porque ela sabe quem cuida de quê e o melhor horário de cada um", True),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 6 — LAER no telefone
# ═════════════════════════════════════════════════════════════════════

AULA_6 = {
    "id": _id("b0716"),
    "titulo": "Técnica 6 · LAER em 30 segundos: objeções no telefone",
    "resumo": "Listar, Acolher, Explorar e Responder em uma frase cada, e voltar ao pedido da reunião. As sete objeções, treinadas.",
    "duracao_min": 14,
    "conteudo_md": """\
## O que é

LAER é o método de objeções do Roteiro de Vendas, encurtado para o telefone:

1. **Listar:** deixe a pessoa terminar a objeção, sem interromper.
2. **Acolher:** mostre que ouviu ("faz sentido", "entendo").
3. **Explorar:** **uma** pergunta para entender o que está por trás.
4. **Responder:** **uma** frase.
5. **Pedir a reunião de novo**, com duas opções.

Tudo em uns 30 segundos.

## Por que funciona

- **A objeção de telefone quase nunca é contra a Controller: é contra o tempo.** Quem atende uma ligação fria está ocupado e quer encerrar.
- **Acolher desarma.** Rebater ("mas a NR-01 obriga!") vira discussão; acolher faz a pessoa continuar falando.
- **Explorar descobre a objeção real.** "Não tenho interesse" pode ser "já está resolvido" ou "agora não é prioridade", e cada uma tem um caminho.
- **O objetivo não é vencer a objeção:** é transformar "não quero" em "não sei se preciso", e "não sei se preciso" em 30 minutos com o especialista.

## As sete objeções, com o Explorar e o Responder

- **"Não tenho interesse."** Explore: "Entendo. É porque já está tudo resolvido ou porque agora não é prioridade?" Responda: resolvido, pergunte quando o PGR foi revisado; não é prioridade, marque o retorno com data.
- **"Já temos fornecedor."** Explore: "Ótimo. E se pudesse melhorar uma coisa nele, o que seria?" Responda, sem falar mal de ninguém: "A conversa serve justamente para comparar com calma. Se estiver tudo certo, você sai com a confirmação."
- **"Manda por e-mail."** Explore: "Mando sim. Para não te mandar coisa genérica, posso te fazer uma pergunta?" Responda: faça a pergunta e peça os 30 minutos. Se insistir, mande o e-mail e marque a ligação de retorno com data.
- **"O contador cuida disso."** Explore: "Ele cuida dos exames e do PGR, ou só envia o eSocial?" Responda: "O contador envia o evento; o conteúdo técnico, PGR, PCMSO e ASO, é de SST. A gente trabalha junto com o contador."
- **"Quanto custa?"** Explore: "Depende de quantos funcionários e do risco da atividade. Quantos vocês são hoje?" Responda: "O especialista monta o valor certo na conversa, em 30 minutos. Terça ou quarta?"
- **"Somos pequenos, não temos risco."** Explore: "Vocês têm PGR e PCMSO hoje?" Responda: "A NR-01 vale para toda empresa com funcionário CLT, e o risco psicossocial existe em qualquer escritório."
- **"Estou sem tempo agora."** Explore: "Claro. Qual o melhor horário para eu te ligar, amanhã de manhã ou à tarde?" Responda: marque a tarefa com o horário combinado e ligue nele.

## O limite

**Depois de duas objeções seguidas, não insista na terceira:** agradeça, marque o retorno com data e siga a cadência. Insistir queima a empresa para os próximos toques.

## Certo e errado

- **Errado:** "Já temos fornecedor." — "Mas o nosso é melhor, a gente tem mais de 500 clientes e..." (rebateu, não explorou, falou mal por tabela).
- **Errado:** "Quanto custa?" — "Fica em torno de..." (deu número no telefone).
- **Certo:** "Já temos fornecedor." — "Ótimo, faz sentido. E se pudesse melhorar uma coisa nele, o que seria?" — "O agendamento demora." — "A conversa serve justamente para comparar com calma. Terça às 10h ou quarta às 15h?"

## Erros comuns

- **Pular o Acolher.** Sem ele, o Explorar soa como interrogatório.
- **Explorar com duas ou três perguntas.** Uma.
- **Responder com um parágrafo.** Uma frase, e volte ao pedido.
- **Esquecer de pedir de novo.** A objeção tratada sem novo pedido termina em "vou pensar".

## Exercício (individual, 20 minutos)

Escreva as sete objeções em cartões (ou num papel dobrado). Sorteie uma, cronometre e responda em voz alta com os cinco passos. Repita até que cada uma caiba em 30 segundos. Anote as duas em que você mais travou: são as do role-play.

## Role-play em dupla (20 minutos)

**Cenário:** o "cliente" é dono de uma empresa de serviços. O avaliador entrega a ele uma sequência de **duas objeções** sorteadas, a serem ditas uma depois da outra.

Três rodadas, trocando os papéis e as objeções.

**Critérios (o avaliador marca sim ou não, por objeção):**

1. Deixou terminar (Listar).
2. Acolheu antes de perguntar.
3. Uma pergunta só no Explorar.
4. Respondeu em uma frase, sem falar mal de ninguém e sem dar preço.
5. Pediu a reunião de novo, com duas opções (ou, em "sem tempo" e em "manda por e-mail" com insistência, marcou o retorno com data).
6. Na segunda objeção seguida sem avanço, agradeceu, marcou o retorno com data e encerrou.

> Objeção de telefone é contra o tempo, não contra você. Acolha, pergunte uma vez, responda em uma frase e peça de novo.
""",
    "quiz": [
        {
            "enunciado": "O que significam as letras de LAER?",
            "alternativas": [
                ("Ligar, Apresentar, Enviar, Repetir", False),
                ("Listar, Acolher, Explorar, Responder", True),
                ("Levantar, Argumentar, Explicar, Rebater", False),
                ("Listar, Apresentar, Esperar, Retornar", False),
            ],
        },
        {
            "enunciado": "Segundo a aula, contra o que é quase sempre a objeção de telefone?",
            "alternativas": [
                ("Contra o preço da Controller", False),
                ("Contra o SDR", False),
                ("Contra o tempo", True),
                ("Contra a NR-01", False),
            ],
        },
        {
            "enunciado": "\"Não tenho interesse.\" Qual é o Explorar ensinado?",
            "alternativas": [
                ("\"Entendo. É porque já está tudo resolvido ou porque agora não é prioridade?\"", True),
                ("\"Mas a NR-01 obriga, sabia?\"", False),
                ("\"Posso te mandar a apresentação?\"", False),
                ("\"Quanto vocês pagam hoje?\"", False),
            ],
        },
        {
            "enunciado": "\"O contador cuida disso.\" Qual é a resposta da aula?",
            "alternativas": [
                ("Que o contador está errado e deve ser trocado", False),
                ("Que a Controller substitui o contador", False),
                ("Que então não há o que fazer", False),
                ("Que o contador envia o evento, o conteúdo técnico é de SST, e a Controller trabalha junto com ele", True),
            ],
        },
        {
            "enunciado": "Você tratou duas objeções seguidas e o cliente não avançou. O que fazer?",
            "alternativas": [
                ("Tentar uma terceira com mais argumentos", False),
                ("Agradecer, marcar o retorno com data e seguir a cadência", True),
                ("Oferecer desconto para fechar a reunião", False),
                ("Finalizar a oportunidade como perdida na hora", False),
            ],
        },
        {
            "enunciado": "O que vem depois do Responder?",
            "alternativas": [
                ("Desligar e mandar e-mail", False),
                ("Explicar todos os serviços da Controller", False),
                ("Pedir a reunião de novo, com duas opções", True),
                ("Perguntar o preço que ele paga hoje", False),
            ],
        },
        {
            "enunciado": "\"Já temos fornecedor.\" Qual atitude a aula proíbe?",
            "alternativas": [
                ("Perguntar o que ele melhoraria no fornecedor", False),
                ("Acolher dizendo \"ótimo\"", False),
                ("Oferecer a conversa para comparar com calma", False),
                ("Falar mal do fornecedor atual", True),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 7 — Mensagem escrita que recebe resposta
# ═════════════════════════════════════════════════════════════════════

AULA_7 = {
    "id": _id("b0717"),
    "titulo": "Técnica 7 · Mensagem escrita que recebe resposta",
    "resumo": "WhatsApp e e-mail em quatro peças: gancho pessoal, uma pergunta, pedido com duas opções e a mensagem de encerramento.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

É a técnica de escrever WhatsApp e e-mail de prospecção que **a pessoa responde**. A mensagem de primeiro contato (WhatsApp ou e-mail) é montada com três peças:

1. **Quem é você**, em uma linha.
2. **Um detalhe da empresa dela** (atividade, cidade, unidade nova): a prova de que não é mensagem em massa.
3. **Uma pergunta só**, fácil de responder.

Na mensagem de **retorno**, o foco é o **pedido com duas opções**. Na de **encerramento**, devolver o controle ao cliente.

## Por que funciona

- **Curta é lida.** Mensagem que cabe na tela do celular sem rolar é lida inteira; a que não cabe é deixada para depois, e depois não chega.
- **Personalizada é respondida.** Nome e um detalhe real mostram que alguém olhou a empresa dela.
- **Uma pergunta tem resposta;** três perguntas têm silêncio.
- **A mensagem de encerramento devolve o controle ao cliente.** Dar a ele a opção de dizer "agora não" costuma ser o que mais gera resposta na cadência.

## As regras

- **Curta:** cabe na tela sem rolar.
- **Personalizada:** nome e um detalhe da empresa.
- **Uma pergunta só.**
- **Sem anexo** no primeiro contato. PDF de apresentação não é lido.
- **Sem áudio longo.** Áudio só depois de uma resposta, e até 30 segundos.
- **Horário comercial**, de segunda a sexta.

## Passo a passo: montar a mensagem

1. Abra a hipótese que você escreveu na Descrição (técnica 1).
2. Escreva a linha de quem você é.
3. Escreva o detalhe da empresa dela, com uma palavra da atividade ou da cidade.
4. Transforme a hipótese em **uma pergunta**.
5. Releia no celular: cabe na tela? Tem uma pergunta só? Tem o nome dela?

**Modelo de WhatsApp (depois da ligação não atendida):**

> "Oi, [nome], tudo bem? Aqui é [seu nome], da Controller Medicina e Segurança do Trabalho. Tentei te ligar agora. Vi que vocês trabalham com [atividade] em [cidade]: o PGR de vocês já foi revisado com os riscos psicossociais que a NR-01 passou a exigir em maio?"

**Modelo de retorno:**

> "[Nome], conseguiu ver minha mensagem? Se fizer sentido, um especialista nosso olha o PGR de vocês em 30 minutos. Terça às 10h ou quarta às 15h?"

**E-mail:** mesmo esqueleto, com um assunto que tem o nome da empresa dela: *"[Empresa] e a revisão do PGR (NR-01)"*. Assinatura com o seu celular.

**Mensagem de encerramento (a última da cadência):**

> "[Nome], imagino que não seja prioridade agora. Posso te procurar de novo em [mês]?"

## Certo e errado

- **Errado:** "Olá! Somos a Controller, empresa líder em medicina e segurança do trabalho, com soluções completas em PGR, PCMSO, LTCAT, ASO, treinamentos... Segue nossa apresentação em anexo. Aguardo retorno!" (genérica, longa, com anexo e sem pergunta).
- **Errado:** áudio de dois minutos no primeiro contato.
- **Certo:** o modelo de primeiro contato com o nome, a atividade e a cidade dela, e uma pergunta.

## Erros comuns

- **Trocar o nome e esquecer o resto.** "Vocês trabalham com [atividade]" sem trocar a atividade é pior do que não personalizar.
- **Duas perguntas na mesma mensagem.**
- **Mandar fora do horário comercial** ou no fim de semana.
- **Não registrar.** Cada mensagem enviada é uma tarefa **concluída** (tipo WhatsApp ou E-mail), com o que foi enviado em "O que aconteceu"; a resposta do cliente vai como print no anexo da tarefa (**Ctrl+V**).

## Exercício (individual, 20 minutos)

Para **três empresas** da sua fila, de perfis diferentes, escreva o WhatsApp de primeiro contato, o de retorno e o e-mail. Depois, passe cada uma pelo checklist: cabe na tela, nome, detalhe real da empresa (no primeiro contato), uma pergunta só (no retorno, só o pedido com duas opções), sem anexo. Reescreva o que falhar.

## Role-play em dupla (15 minutos)

**Formato escrito.** Cada um escreve, em 5 minutos, um WhatsApp de primeiro contato para a mesma empresa (o avaliador escolhe uma da base). Troquem os celulares.

O "cliente" lê como se tivesse recebido no meio do expediente e responde o que responderia de verdade. Depois, o SDR escreve a resposta com o pedido de duas opções.

**Critérios (o avaliador marca sim ou não):**

1. Cabe na tela sem rolar.
2. Tem o nome da pessoa e um detalhe real da empresa.
3. Uma pergunta só, que se responde em uma frase.
4. Sem anexo e sem áudio.
5. Na resposta, pediu a reunião com duas opções.
6. Registrou como tarefa concluída, com o texto em "O que aconteceu".

> Mensagem que recebe resposta é curta, tem o nome da pessoa, um detalhe dela e uma pergunta só.
""",
    "quiz": [
        {
            "enunciado": "Quantas perguntas deve ter uma mensagem de prospecção?",
            "alternativas": [
                ("Três, para cobrir tudo de uma vez", False),
                ("Nenhuma: só informação", False),
                ("Uma só, fácil de responder", True),
                ("Quantas couberem na tela", False),
            ],
        },
        {
            "enunciado": "Pode mandar o PDF de apresentação no primeiro contato?",
            "alternativas": [
                ("Não: sem anexo no primeiro contato, PDF de apresentação não é lido", True),
                ("Sim, sempre, para o cliente conhecer a Controller", False),
                ("Só se for menor que 1 MB", False),
                ("Só por e-mail, nunca por WhatsApp", False),
            ],
        },
        {
            "enunciado": "Quando o áudio é aceitável, segundo a aula?",
            "alternativas": [
                ("No primeiro contato, para mostrar simpatia", False),
                ("Sempre que o texto ficar longo", False),
                ("Nunca, em hipótese nenhuma", False),
                ("Só depois de uma resposta, e com até 30 segundos", True),
            ],
        },
        {
            "enunciado": "O que torna a mensagem personalizada, segundo a aula?",
            "alternativas": [
                ("Usar emojis e exclamações", False),
                ("O nome da pessoa e um detalhe real da empresa dela", True),
                ("Mandar às 22h, quando ela está em casa", False),
                ("Colocar o logo da Controller", False),
            ],
        },
        {
            "enunciado": "Qual é a mensagem de encerramento da cadência?",
            "alternativas": [
                ("\"Última chance: a oferta acaba hoje.\"", False),
                ("\"Vou tirar vocês da nossa lista.\"", False),
                ("\"[Nome], imagino que não seja prioridade agora. Posso te procurar de novo em [mês]?\"", True),
                ("\"Segue a proposta em anexo.\"", False),
            ],
        },
        {
            "enunciado": "Onde fica a resposta do cliente no HIPO?",
            "alternativas": [
                ("Em lugar nenhum: o WhatsApp já guarda", False),
                ("Num grupo da equipe", False),
                ("No Monitor", False),
                ("Como print no anexo da tarefa (Ctrl+V)", True),
            ],
        },
        {
            "enunciado": "Qual o assunto de e-mail sugerido na aula?",
            "alternativas": [
                ("\"[Empresa] e a revisão do PGR (NR-01)\"", True),
                ("\"Apresentação Controller\"", False),
                ("\"URGENTE: regularize sua empresa\"", False),
                ("\"Proposta comercial\"", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 8 — Cadência multicanal
# ═════════════════════════════════════════════════════════════════════

AULA_8 = {
    "id": _id("b0718"),
    "titulo": "Técnica 8 · Cadência: seis toques sem esquecer ninguém",
    "resumo": "A sequência D0 a D12, por que alternar canal e horário, como a cadência anda pelas tarefas do HIPO e quando parar.",
    "duracao_min": 12,
    "conteudo_md": """\
## O que é

Cadência é a **sequência planejada de toques** em uma empresa: ligação, WhatsApp e e-mail, em dias e horários definidos, até você falar com o decisor ou encerrar. No Roteiro do SDR são seis toques em menos de três semanas.

## Por que funciona

- **Ligação não atendida não é "não".** A maioria das reuniões sai do terceiro ao sexto toque.
- **Canal diferente alcança de outro jeito.** Quem não atende ligação lê WhatsApp; quem não lê WhatsApp abre e-mail no computador.
- **Horário diferente acha a pessoa livre.** Se a primeira ligação foi de manhã, a segunda é à tarde.
- **Ter um fim protege a empresa e o funil.** Ninguém é esquecido, e ninguém é perseguido para sempre.

## A sequência

Conta a partir do dia do primeiro contato:

1. **D0 · Ligação.** Não atendeu? WhatsApp de primeiro contato no mesmo dia.
2. **D1 · E-mail** de primeiro contato.
3. **D3 · Ligação**, em outro horário.
4. **D5 · WhatsApp** de retorno.
5. **D8 · Ligação.** Tente a recepção e peça pelo setor (técnica 5).
6. **D12 · WhatsApp** de encerramento (técnica 7).

Conseguiu falar e marcar? **A cadência para ali.**

## Passo a passo no HIPO

A cadência anda pelas **tarefas**:

1. Cada toque é uma tarefa, com tipo (Ligação, WhatsApp, E-mail) e dia.
2. Ao **concluir** um toque, escreva o resultado em "O que aconteceu" ("não atendeu", "recepção: falar com Juliana depois das 16h").
3. O HIPO pede a **próxima tarefa**: marque o toque seguinte, com o tipo e o dia da sequência.
4. **Combinou retorno?** A próxima tarefa vai no dia e na hora combinados, não no D da sequência.
5. **Falou e recusou de vez?** Finalize a oportunidade como **Perdido**, com o motivo.
6. **Seis toques sem nenhuma resposta?** Finalize como **Perdido**, com o motivo que descreve (sem retorno). A empresa continua na base e pode ser trabalhada de novo mais tarde.

## O ritmo do dia

- **Manhã:** ligações (as atrasadas primeiro, depois as de hoje).
- **Fim da manhã e início da tarde:** WhatsApp e e-mails.
- **Tarde:** segunda rodada de ligações e as reuniões marcadas registradas.
- **Fim do dia:** nenhuma tarefa atrasada sem motivo. Se o prazo mudou, edite o prazo.

## Certo e errado

- **Errado:** ligar três vezes no mesmo dia, sempre às 9h, e desistir.
- **Errado:** deixar a oportunidade aberta por dois meses "para tentar de novo um dia".
- **Errado:** concluir a tarefa sem marcar a próxima (o HIPO pede; não pule com uma data qualquer).
- **Certo:** D0 ligação de manhã + WhatsApp; D1 e-mail; D3 ligação à tarde; D5 WhatsApp; D8 recepção; D12 encerramento; sem resposta, Perdido com motivo.

## Erros comuns

- **Coluna Atrasadas cheia.** É cadência quebrada: o dia começa por ela.
- **Mesmo horário em todos os toques.** Alterne manhã e tarde.
- **Mesma mensagem copiada nos WhatsApps.** O primeiro contato traz a pergunta; o retorno, o pedido com duas opções; o encerramento devolve o controle.
- **"O que aconteceu" vazio.** Sem ele, a gestão e você mesmo não sabem em que toque a empresa está.

## Exercício (individual, 15 minutos)

Pegue **uma empresa nova** da sua fila e escreva a cadência inteira dela numa folha: as seis datas reais (contando os dias a partir de hoje), o canal e o horário de cada toque, e o texto dos três WhatsApps e do e-mail. Depois, crie no HIPO só a **primeira** tarefa: as próximas nascem quando você concluir cada uma.

## Role-play em dupla (15 minutos)

**Formato de mesa.** O avaliador conta uma "história" de uma empresa, toque a toque, e o SDR diz o que faz em cada um:

- D0: ligação, ninguém atende.
- D1: e-mail sem resposta.
- D3: a recepção diz "ela só chega depois das 14h".
- D5: WhatsApp visualizado, sem resposta.
- D8: a decisora atende e diz "agora não, me procura em março".

**Critérios (o avaliador marca sim ou não):**

1. Disse o canal certo de cada D.
2. No D0, mandou WhatsApp no mesmo dia.
3. No D3, marcou o próximo toque de ligação depois das 14h.
4. Registrou o resultado de cada toque em "O que aconteceu".
5. No D8, marcou a tarefa para março (e não seguiu para o D12).
6. Sabe o que fazer se a história terminasse com seis toques sem resposta (Perdido com motivo).

> A fila de Tarefas é a sua cadência. Coluna Atrasadas cheia é cadência quebrada: comece o dia por ela.
""",
    "tour": [
        _passo("/crm/tarefas", "tar-area", "A cadência é a sua fila",
               "Cada toque é uma tarefa. **Atrasadas** é cadência quebrada: o dia começa por ela."),
        _passo("/crm/tarefas", "tar-acoes", "Concluir e marcar o próximo toque",
               "Conclua com o resultado e marque a **próxima** tarefa: o tipo e o dia do toque seguinte.",
               clicar=["tar-cartao"]),
    ],
    "quiz": [
        {
            "enunciado": "Quantos toques tem a cadência padrão do SDR?",
            "alternativas": [
                ("Três", False),
                ("Seis, em menos de três semanas", True),
                ("Dez, em um mês", False),
                ("Quantos forem precisos, sem limite", False),
            ],
        },
        {
            "enunciado": "O que acontece no D0 se a ligação não é atendida?",
            "alternativas": [
                ("WhatsApp de primeiro contato no mesmo dia", True),
                ("Nada até o D3", False),
                ("Uma nova ligação 10 minutos depois", False),
                ("O e-mail com a proposta", False),
            ],
        },
        {
            "enunciado": "Qual é o toque do D8?",
            "alternativas": [
                ("E-mail de encerramento", False),
                ("WhatsApp de retorno", False),
                ("Áudio de 2 minutos", False),
                ("Ligação, tentando a recepção e pedindo pelo setor", True),
            ],
        },
        {
            "enunciado": "Por que a ligação do D3 deve ser em outro horário?",
            "alternativas": [
                ("Porque o HIPO bloqueia o mesmo horário", False),
                ("Porque horário diferente aumenta a chance de achar a pessoa livre", True),
                ("Porque é regra da operadora", False),
                ("Porque o EV liga no mesmo horário", False),
            ],
        },
        {
            "enunciado": "Seis toques e nenhuma resposta. O que fazer com a oportunidade?",
            "alternativas": [
                ("Deixar aberta para tentar um dia", False),
                ("Apagar a empresa da base", False),
                ("Finalizar como Perdido, com o motivo (sem retorno)", True),
                ("Passar para o EV ligar", False),
            ],
        },
        {
            "enunciado": "No D3 a decisora atende e pede para você ligar em março. O que fazer?",
            "alternativas": [
                ("Seguir a sequência e mandar o WhatsApp do D5", False),
                ("Finalizar como Perdido", False),
                ("Ligar de novo amanhã para insistir", False),
                ("Marcar a próxima tarefa para março, no combinado", True),
            ],
        },
        {
            "enunciado": "Como a cadência anda dentro do HIPO?",
            "alternativas": [
                ("Por tarefas: ao concluir um toque, o HIPO pede a próxima", True),
                ("Por uma planilha separada", False),
                ("Pelo Monitor, que manda lembretes", False),
                ("Pela Agenda do EV", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# Aula 9 — Bastão e confirmação da véspera
# ═════════════════════════════════════════════════════════════════════

AULA_9 = {
    "id": _id("b0719"),
    "titulo": "Técnica 9 · O bastão em cinco linhas e a confirmação da véspera",
    "resumo": "Passar para o EV o que o cliente disse, em cinco linhas, e confirmar na véspera para a reunião acontecer.",
    "duracao_min": 11,
    "conteudo_md": """\
## O que é

Duas técnicas que fecham o trabalho do SDR depois da reunião marcada:

- **O bastão:** cinco linhas na **Descrição** da oportunidade, para o EV preparar a reunião em 15 minutos sem perguntar de novo o que você já descobriu.
- **A confirmação da véspera:** um WhatsApp no dia útil anterior, para a reunião acontecer.

## Por que funciona

- **O cliente percebe quando ninguém escutou.** Se o EV abre a reunião perguntando o que o cliente já contou ao SDR, a confiança cai no primeiro minuto. Se o EV abre com a frase do cliente, ela sobe.
- **O no-show começa no agendamento mal feito.** Reunião com o decisor, com o motivo escrito e confirmada na véspera acontece; reunião marcada para "qualquer um" vira no-show.
- **Reunião marcada que não acontece não vale.** AGEN e % NOSHOW medem isso.

## Passo a passo: o bastão

Logo depois de marcar (Fase = **Lead**), escreva na **Descrição**, abaixo da hipótese que você anotou antes de ligar:

1. **Decisor:** nome, cargo, e quem mais participa da decisão.
2. **O que ele disse:** a dor ou a dúvida, **com as palavras dele**, entre aspas.
3. **Situação atual:** quem cuida de SST hoje (fornecedor, interno, contador).
4. **Tamanho:** funcionários e unidades que **ele** informou.
5. **Por que aceitou:** o gancho que funcionou.

**Exemplo:**

> 1. Juliana Souza, gerente de RH; o sócio Marcos também participa.
> 2. "O admissional demora uma semana e o funcionário começa atrasado."
> 3. Fornecedor atual, um por loja.
> 4. 4 lojas, uns 60 funcionários (ela informou).
> 5. Aceitou quando falei do admissional atrasando o início.

## Passo a passo: a confirmação da véspera

1. No **dia útil anterior** à reunião, mande:

> "[Nome], tudo certo para amanhã às [hora] com o [EV]? O link está no convite. Qualquer coisa, me avisa por aqui."

Se a véspera útil for sexta, diga o dia ("tudo certo para segunda às [hora]"), não "amanhã".

2. Registre como **tarefa concluída**.
3. **O cliente pediu para mudar?** Edite a reunião **ainda na conversa**, com o horário novo já na agenda do EV.
4. **Sem resposta?** A reunião segue. Registre na tarefa concluída, em "O que aconteceu", que não houve confirmação.

## Certo e errado

- **Errado (bastão):** "Cliente interessado, ligar." (o EV não sabe nada).
- **Errado (bastão):** "Empresa com problemas de SST." (resumo seu, sem as palavras do cliente).
- **Errado (véspera):** confirmar na própria manhã da reunião, ou não confirmar.
- **Certo:** as cinco linhas, com a frase do cliente entre aspas, e o WhatsApp no dia útil anterior.

## Erros comuns

- **Deixar o bastão para depois.** Depois de dez ligações, as palavras exatas já se perderam.
- **Tamanho tirado da fonte.** O tamanho do bastão é o que **o cliente informou**; o nº da fonte é estimativa.
- **Esquecer quem mais decide.** O EV precisa saber se o sócio vai estar.
- **Contar o fim de semana como véspera.** A reunião de segunda se confirma na **sexta**, o dia útil anterior.

## Exercício (individual, 15 minutos)

Pegue as **três últimas reuniões** que você marcou. Releia a Descrição de cada uma e dê nota de 0 a 5: um ponto por linha do bastão que está lá, com as palavras do cliente na linha 2. Complete o que faltar, com o que você ainda lembra, e combine com você mesmo: a próxima já sai com 5.

## Role-play em dupla (20 minutos)

**Parte 1 (bastão, 10 min).** O avaliador faz o papel de um cliente numa ligação de 2 minutos, já aceitando a reunião no fim. Depois, o SDR tem 3 minutos para escrever as cinco linhas. O avaliador lê **como se fosse o EV** e responde: "consigo preparar a reunião só com isso?"

**Parte 2 (véspera, 10 min).** O avaliador responde ao WhatsApp da véspera com uma de três reações: "confirmado", "preciso mudar para quinta" ou silêncio.

**Critérios (o avaliador marca sim ou não):**

1. As cinco linhas estão lá, na ordem.
2. A linha 2 tem as palavras exatas do cliente, entre aspas.
3. O tamanho é o que o cliente informou.
4. Diz quem mais participa da decisão.
5. Mandou a confirmação no dia útil anterior, com dia, hora e nome do EV.
6. No "preciso mudar", remarcou na conversa, já na agenda do EV.
7. No silêncio, registrou que não houve confirmação.

> Reunião marcada para "qualquer um" vira no-show. Reunião com o decisor, com o motivo escrito e confirmada na véspera, acontece.
""",
    "tour": [
        _passo("/crm/oportunidades", "opo-det-fase", "Mover para Lead",
               "Decisor + interesse com reunião marcada: **Fase = Lead**.",
               clicar=["opo-cartao-abrir"]),
        _passo("/crm/oportunidades", "opo-det-conteudo", "O bastão para o EV",
               "Em **Descrição**, as cinco linhas: decisor, o que ele disse, situação atual, tamanho e por que aceitou.",
               clicar=["opo-cartao-abrir", "aba-dados"]),
    ],
    "quiz": [
        {
            "enunciado": "Onde fica o bastão para o EV?",
            "alternativas": [
                ("Num WhatsApp para o EV", False),
                ("No convite da reunião", False),
                ("Na Descrição da oportunidade", True),
                ("No Monitor", False),
            ],
        },
        {
            "enunciado": "O que vai na linha 2 do bastão (\"o que ele disse\")?",
            "alternativas": [
                ("A dor ou a dúvida, com as palavras do cliente entre aspas", True),
                ("O seu resumo da situação", False),
                ("O preço que você estimou", False),
                ("O CNPJ da empresa", False),
            ],
        },
        {
            "enunciado": "De onde sai o \"tamanho\" do bastão?",
            "alternativas": [
                ("Do nº de funcionários da fonte pública", False),
                ("Do porte no CNPJ", False),
                ("Da estimativa do SDR", False),
                ("Do que o cliente informou na ligação", True),
            ],
        },
        {
            "enunciado": "Quando mandar a confirmação da reunião?",
            "alternativas": [
                ("Uma semana antes", False),
                ("No dia útil anterior à reunião", True),
                ("Cinco minutos antes de começar", False),
                ("Não é preciso confirmar", False),
            ],
        },
        {
            "enunciado": "Na confirmação, o cliente pede para mudar o horário. O que fazer?",
            "alternativas": [
                ("Pedir que ele fale direto com o EV", False),
                ("Cancelar e recomeçar a cadência", False),
                ("Editar a reunião ainda na conversa, com o horário novo já na agenda do EV", True),
                ("Responder no dia seguinte", False),
            ],
        },
        {
            "enunciado": "Por que o bastão importa para o cliente, segundo a aula?",
            "alternativas": [
                ("Porque o cliente lê a Descrição", False),
                ("Porque é exigência da NR-01", False),
                ("Porque reduz o preço da proposta", False),
                ("Porque, sem ele, o EV pergunta de novo e o cliente percebe que ninguém escutou", True),
            ],
        },
        {
            "enunciado": "Qual destas é uma linha 1 (decisor) bem escrita?",
            "alternativas": [
                ("\"Juliana Souza, gerente de RH; o sócio Marcos também participa.\"", True),
                ("\"Falei com alguém do RH.\"", False),
                ("\"Cliente interessado, ligar.\"", False),
                ("\"Decisor a confirmar.\"", False),
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# A trilha
# ═════════════════════════════════════════════════════════════════════

METODO_04 = {
    "id": _id("b0700"),
    "titulo": "04 · Técnicas do SDR na prática",
    "pilar": "tecnica",
    "reforca": "metas",
    "descricao": (
        "O treino de cada técnica do 02 · Roteiro do SDR: pesquisa e "
        "hipótese de dor, abertura com permissão, perguntar e escutar, pedido "
        "com duas opções, recepção, LAER no telefone, mensagem escrita, "
        "cadência e o bastão para o EV. Cada aula ensina o passo a passo, "
        "mostra o certo e o errado e termina com exercício e role-play em "
        "dupla, com critérios de avaliação."
    ),
    "prazo_dias": 55,
    "obrigatorios": ("SDR",),
    "opcionais": GESTAO_OPCIONAL,
    "aulas": [AULA_1, AULA_2, AULA_3, AULA_4, AULA_5, AULA_6, AULA_7, AULA_8, AULA_9],
}

TRILHAS_TECNICAS_SDR: list[dict] = [METODO_04]
