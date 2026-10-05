"""
HIPO — UC: roteiros do SDR e do EC (pilar Método).

  Método 02 · Roteiro do SDR   obrigatória para SDR   (prazo 50 dias)
  Método 03 · Roteiro do EC    obrigatória para EC    (prazo 50 dias)

ADM e Franqueado veem as duas sem obrigação.

Pedido do Tulio (04/10/2026): "como criamos o script de vendas, precisamos
criar o script de SDR e de EC". O roteiro de vendas (Método 01) cobre a
reunião do EV; estes cobrem o que vem antes dela (SDR) e o canal de
indicação (EC). Decisões dele nas perguntas de 04/10:

  * SDR faz primeiro contato por ligação fria, WhatsApp e e-mail;
  * o SDR marca a reunião para o EV quando tem DECISOR + INTERESSE (sem
    filtro de porte; o resto da qualificação é bônus e é do EV);
  * o contador parceiro recebe COMISSÃO RECORRENTE enquanto o cliente
    indicado estiver ativo. O percentual e as regras de pagamento são da
    gestão: o texto nunca cita número, para não virar promessa.

Mesma voz e mesmos fatos do "Roteiro de Vendas — Controller Med Seg"
(30/09/2026): diagnosticar antes de apresentar, contrato de abertura,
SPIN, LAER, próximo passo com data, o gancho da NR-01 psicossocial.

Algumas aulas trazem `tour` (o "Me mostra no HIPO" da entrega 035): o
roteiro termina no registro, e o registro é no HIPO.

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
# MÉTODO 02 — Roteiro do SDR
# ═════════════════════════════════════════════════════════════════════

METODO_02 = {
    "id": _id("b0500"),
    "titulo": "Método 02 · Roteiro do SDR",
    "pilar": "metodo",
    "reforca": "metas",
    "descricao": (
        "O roteiro do primeiro contato até a reunião marcada para o EV: "
        "pesquisa de três minutos, ligação fria, WhatsApp e e-mail, como "
        "achar o decisor, objeções de telefone, cadência e a passagem de "
        "bastão. A meta de cada conversa é uma só: reunião com decisor e "
        "interesse, na agenda do EV."
    ),
    "prazo_dias": 50,
    "obrigatorios": ("SDR",),
    "opcionais": GESTAO_OPCIONAL,
    "aulas": [
        {
            "id": _id("b0511"),
            "titulo": "O trabalho do SDR em uma frase",
            "resumo": "O SDR não vende: ele abre a porta. O que conta como sucesso, o que não é papel dele e como isso aparece nos números.",
            "duracao_min": 7,
            "conteudo_md": """\
## A frase

**O SDR transforma uma empresa da base em uma reunião com o decisor, na agenda do EV.** Tudo o que você faz no dia serve a isso.

Sucesso, para o SDR, não é a venda. É a reunião certa marcada. Venda é do EV, que conduz a reunião de 45 minutos do Roteiro de Vendas (Método 01).

## O critério para marcar

Você marca a reunião quando tem as duas coisas:

- **Decisor**: falou com quem decide a contratação de SST, ou com quem influencia e leva a conversa para ele (dono, sócio, RH, DP, financeiro ou técnico de segurança, conforme o porte).
- **Interesse**: essa pessoa aceitou conversar com um especialista, com dia e hora.

Não há filtro de porte. Qualquer empresa com empregado CLT precisa de PGR, PCMSO e ASO.

O que você descobrir além disso (fornecedor atual, unidades, vencimento do contrato, dor) é **bônus**, e vale ouro: vai escrito na oportunidade para o EV não perguntar de novo.

## O que não é papel do SDR

- **Falar preço.** O preço depende de vidas, grau de risco e escopo. Quem dá número no telefone perde a reunião e erra o valor.
- **Apresentar a Controller inteira.** Uma frase de credencial basta; a apresentação é do EV, depois do diagnóstico.
- **Mandar proposta.** Proposta sai da reunião, nunca antes.
- **Discutir a norma em profundidade.** Você planta a dúvida; o EV responde.

## Como isso aparece nos números

- **LEAD**: oportunidades que passaram de Suspect para Lead. Você move para **Lead** quando tem decisor + interesse.
- **AGEND MES**: reuniões que você marcou no mês (pela data em que marcou). O crédito vem do campo **Agendado por**.
- **AGEN** e **% NOSHOW**: reunião marcada que não acontece não vale. Reunião bem marcada é a que acontece.

> Uma reunião com decisor vale mais que três com quem "vai repassar". O EV não fecha com quem não decide.
""",
            "quiz": [
                {
                    "enunciado": "Qual é o critério para o SDR marcar a reunião para o EV?",
                    "alternativas": [
                        ("Empresa com mais de 50 funcionários", False),
                        ("Decisor + interesse, com dia e hora aceitos", True),
                        ("Cliente pediu proposta", False),
                        ("Qualquer pessoa atendeu o telefone", False),
                    ],
                },
                {
                    "enunciado": "O cliente pergunta o preço na ligação. O que o SDR faz?",
                    "alternativas": [
                        ("Dá uma faixa aproximada", False),
                        ("Explica que depende de vidas, risco e escopo, e que o especialista monta na reunião", True),
                        ("Manda a tabela por WhatsApp", False),
                        ("Desliga", False),
                    ],
                },
                {
                    "enunciado": "Quando a oportunidade vai de Suspect para Lead?",
                    "alternativas": [
                        ("Quando o SDR liga pela primeira vez", False),
                        ("Quando há decisor + interesse", True),
                        ("Quando a proposta é enviada", False),
                        ("Quando o contrato é assinado", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0512"),
            "titulo": "Antes de discar: a pesquisa de três minutos",
            "resumo": "O que olhar no HIPO antes de cada contato, a hipótese de dor por perfil e quem procurar em cada porte de empresa.",
            "duracao_min": 8,
            "conteudo_md": """\
## Três minutos, não trinta

O EV prepara 15 minutos para uma reunião. O SDR faz dezenas de contatos por dia: a pesquisa é de **três minutos**, e tudo está no HIPO.

Abra a conta (pela oportunidade ou em Contas) e olhe:

- **Atividade e CNAE** (aba Dados públicos): o que a empresa faz.
- **Grau de risco (NR-4)**, de 1 a 4: quanto maior, mais exames e programas obrigatórios.
- **Porte e nº de funcionários**: o nº vindo da fonte é estimativa, use só para se orientar.
- **Cidade** e **matriz ou filial**: várias unidades puxam o argumento de atendimento único.
- **Sócios**: em empresa pequena, o sócio costuma ser o decisor.

## Uma hipótese de dor por perfil

Escreva **uma** hipótese antes de ligar. Ela vira a sua pergunta de abertura.

- **Varejo e alimentação com várias lojas**: turnover alto, admissional demorado atrasando o início do funcionário, cada loja com um fornecedor.
- **Indústria e construção (grau 3 e 4)**: PGR e LTCAT desatualizados, exames complementares (audiometria, espirometria), NR-35 e NR-10.
- **Escritório e serviços (grau 1 e 2)**: "acha que não tem risco"; PGR sem os riscos psicossociais; eSocial de SST enviado com erro.

## O gancho do momento

Desde **26/05/2026** está em vigor a redação da NR-01 que exige os **fatores de risco psicossociais** no PGR. Muitas empresas não revisaram. É uma pergunta, não um sermão: "o PGR de vocês já foi revisado com os riscos psicossociais?"

## Quem procurar

- **Até uns 20 funcionários**: o dono ou sócio. Muitas vezes é ele que atende.
- **Médio porte**: RH ou DP. O financeiro entra quando o assunto é custo.
- **Indústria e obra**: técnico de segurança ou engenheiro de segurança, que sente a dor técnica; o decisor costuma ser o gerente da planta ou o dono.
- **Rede com várias unidades**: RH corporativo.

> Ligação sem hipótese vira "estou ligando para apresentar a Controller". Ligação com hipótese vira uma pergunta que o cliente quer responder.
""",
            "tour": [
                _passo("/crm/contas", "con-360-topo", "A conta antes de discar",
                       "Vertical, nº de funcionários e situação. O nº vindo da fonte é estimativa: serve para se orientar.",
                       clicar=["con-linha"]),
                _passo("/crm/contas", "con-360-topo", "Dados públicos: risco e atividade",
                       "Na aba **Dados públicos**: CNAE, atividade e **grau de risco (NR-4)**. É daqui que sai a sua hipótese de dor.",
                       clicar=["con-linha", "aba-dados-publicos"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Onde a pesquisa fica escrita",
                       "Na oportunidade, aba **Dados**: anote a hipótese e o que descobrir em **Descrição**. É o que o EV vai ler.",
                       clicar=["opo-cartao-abrir", "aba-dados"]),
            ],
            "quiz": [
                {
                    "enunciado": "Onde o SDR vê o grau de risco (NR-4) da empresa?",
                    "alternativas": [
                        ("Na aba Dados públicos da conta", True),
                        ("Pergunta ao cliente na ligação", False),
                        ("No Monitor", False),
                        ("Não precisa saber", False),
                    ],
                },
                {
                    "enunciado": "Escritório de contabilidade com 15 funcionários. Qual é a melhor hipótese de dor?",
                    "alternativas": [
                        ("NR-35 e trabalho em altura", False),
                        ("PGR sem riscos psicossociais e eSocial de SST com erro", True),
                        ("Audiometria de ruído", False),
                        ("LTCAT de agente químico", False),
                    ],
                },
                {
                    "enunciado": "Numa empresa com cerca de 15 funcionários, quem costuma decidir?",
                    "alternativas": [
                        ("O dono ou sócio", True),
                        ("O RH corporativo", False),
                        ("O técnico de segurança", False),
                        ("A recepção", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0513"),
            "titulo": "A ligação fria, fala por fala",
            "resumo": "As cinco partes da ligação de dois minutos: abertura com permissão, motivo, pergunta, pedido da reunião e confirmação.",
            "duracao_min": 10,
            "conteudo_md": """\
## Dois minutos, cinco partes

A ligação fria não é uma reunião curta. É um pedido de reunião bem feito. Fale pouco, pergunte e peça.

## 1. Abertura com permissão (15 s)

> "Oi, [nome], aqui é [seu nome], da Controller Medicina e Segurança do Trabalho, de Guarulhos. Te peguei num momento ruim, ou você me dá dois minutos?"

Pedir permissão baixa a guarda. Se for momento ruim, pergunte quando ligar e marque a tarefa com essa hora.

## 2. O motivo, ligado à hipótese (20 s)

Uma frase de credencial e uma de motivo. Nada de "estou ligando para apresentar".

> "A gente cuida de saúde e segurança do trabalho de mais de 500 empresas. Estou ligando porque, desde maio, a NR-01 passou a exigir os riscos psicossociais no PGR, e muita empresa do seu porte ainda não revisou."

Troque o motivo pela hipótese do perfil: admissional demorado no varejo, PGR e LTCAT na indústria.

## 3. Uma pergunta (30 s)

> "Hoje quem cuida disso para vocês, um fornecedor, alguém interno ou o contador?"

Ouça. Depois, uma segunda pergunta, só se couber:

> "E o PGR de vocês já foi revisado com essa parte nova?"

Anote as palavras exatas. Elas vão para a Descrição da oportunidade.

## 4. O pedido da reunião (20 s)

Peça a reunião com o especialista, com duas opções de horário:

> "Faz sentido um especialista nosso olhar isso com você em 30 minutos, sem compromisso? Terça às 10h ou quarta às 15h, o que fica melhor?"

Duas opções de horário recebem mais "sim" do que "quando você pode?".

## 5. Confirmação (20 s)

- Nome completo, cargo, e-mail e celular do decisor.
- Quem mais participa da decisão: "Mais alguém precisa estar?"
- Online ou presencial.

> "Combinado: [dia] às [hora], com o [EV]. Vou te mandar o convite agora por e-mail. Se aparecer um imprevisto, me avisa por este número?"

## Passando pela recepção

- Peça pelo **setor**, não pela venda: "Com quem falo sobre os exames dos funcionários? É o RH?"
- Seja honesto e breve. Nada de "é particular" ou "ele me pediu para ligar".
- Recepção que barra é aliada: pergunte o nome da pessoa certa e o melhor horário, e agradeça pelo nome.

> Regra de ouro: quem pergunta conduz. Se você está falando há mais de 30 segundos seguidos, pare e pergunte.
""",
            "quiz": [
                {
                    "enunciado": "Como a ligação fria abre?",
                    "alternativas": [
                        ("Apresentando os 30 anos de história da Controller", False),
                        ("Pedindo permissão: \"te peguei num momento ruim ou você me dá dois minutos?\"", True),
                        ("Falando o preço do exame", False),
                        ("Perguntando se ele quer comprar", False),
                    ],
                },
                {
                    "enunciado": "Por que pedir a reunião com duas opções de horário?",
                    "alternativas": [
                        ("Porque o EV só tem dois horários", False),
                        ("Porque escolher entre duas opções gera mais \"sim\" do que uma pergunta aberta", True),
                        ("Para parecer ocupado", False),
                        ("Não há motivo", False),
                    ],
                },
                {
                    "enunciado": "A recepção pergunta o assunto. Qual é a melhor resposta?",
                    "alternativas": [
                        ("\"É particular\"", False),
                        ("\"Com quem falo sobre os exames dos funcionários? É o RH?\"", True),
                        ("\"Ele me pediu para ligar\"", False),
                        ("Desligar e tentar outro número", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0514"),
            "titulo": "Objeções de telefone",
            "resumo": "LAER em 30 segundos para as sete objeções que mais aparecem na ligação, com a pergunta de exploração e a resposta.",
            "duracao_min": 9,
            "conteudo_md": """\
## LAER em 30 segundos

No telefone o método é o mesmo do Roteiro de Vendas, só mais curto: **Listar** (deixe terminar), **Acolher** ("faz sentido"), **Explorar** (uma pergunta), **Responder** (uma frase) e **pedir a reunião de novo**.

A objeção de telefone quase nunca é contra a Controller: é contra o tempo. Seu trabalho é transformar "não quero" em "não sei se preciso", e "não sei se preciso" em 30 minutos com o especialista.

## As sete mais comuns

**"Não tenho interesse."**
- Explore: "Entendo. É porque já está tudo resolvido ou porque agora não é prioridade?"
- Responda: se está resolvido, pergunte quando o PGR foi revisado; se não é prioridade, marque o retorno com data.

**"Já temos fornecedor."**
- Explore: "Ótimo. E se pudesse melhorar uma coisa nele, o que seria?"
- Responda: não fale mal de ninguém. "A conversa serve justamente para comparar com calma. Se estiver tudo certo, você sai com a confirmação."

**"Manda por e-mail."**
- Explore: "Mando sim. Para não te mandar coisa genérica, posso te fazer uma pergunta?"
- Responda: faça a pergunta e peça os 30 minutos. Se insistir, mande o e-mail e marque a ligação de retorno com data.

**"O contador cuida disso."**
- Explore: "Ele cuida dos exames e do PGR, ou só envia o eSocial?"
- Responda: "O contador envia o evento; o conteúdo técnico, PGR, PCMSO e ASO, é de SST. A gente trabalha junto com o contador."

**"Quanto custa?"**
- Explore: "Depende de quantos funcionários e do risco da atividade. Quantos vocês são hoje?"
- Responda: "O especialista monta o valor certo na conversa, em 30 minutos. Terça ou quarta?"

**"Somos pequenos, não temos risco."**
- Explore: "Vocês têm PGR e PCMSO hoje?"
- Responda: "A NR-01 vale para toda empresa com funcionário CLT, e o risco psicossocial existe em qualquer escritório."

**"Estou sem tempo agora."**
- Explore: "Claro. Qual o melhor horário para eu te ligar, amanhã de manhã ou à tarde?"
- Responda: marque a tarefa com o horário combinado e ligue nele.

> Depois de duas objeções seguidas, não insista na terceira: agradeça, marque o retorno com data e siga a cadência.
""",
            "quiz": [
                {
                    "enunciado": "Qual é a ordem do LAER?",
                    "alternativas": [
                        ("Responder, explorar, acolher, listar", False),
                        ("Listar, acolher, explorar, responder", True),
                        ("Acolher, responder, listar, explorar", False),
                        ("Explorar, responder, listar, acolher", False),
                    ],
                },
                {
                    "enunciado": "\"Já temos fornecedor.\" Qual é a pergunta de exploração?",
                    "alternativas": [
                        ("\"Quanto vocês pagam?\"", False),
                        ("\"E se pudesse melhorar uma coisa nele, o que seria?\"", True),
                        ("\"Sabia que ele é pior que a gente?\"", False),
                        ("\"Quando o contrato vence?\" e desligar", False),
                    ],
                },
                {
                    "enunciado": "Depois de duas objeções seguidas, o que fazer?",
                    "alternativas": [
                        ("Insistir até o cliente aceitar", False),
                        ("Agradecer, marcar o retorno com data e seguir a cadência", True),
                        ("Finalizar a oportunidade como perdida", False),
                        ("Mandar a proposta", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0515"),
            "titulo": "WhatsApp e e-mail que recebem resposta",
            "resumo": "As regras das mensagens escritas e os modelos de primeiro contato, de retorno e de encerramento.",
            "duracao_min": 8,
            "conteudo_md": """\
## As regras

- **Curta.** Cabe na tela do celular sem rolar.
- **Personalizada.** Nome da pessoa e um detalhe da empresa (atividade, cidade, unidade nova).
- **Uma pergunta só**, fácil de responder.
- **Sem anexo** no primeiro contato. PDF de apresentação não é lido.
- **Sem áudio longo.** Se mandar áudio, até 30 segundos, e só depois de uma resposta.
- Horário comercial, de segunda a sexta.

## WhatsApp: primeiro contato (depois da ligação não atendida)

> "Oi, [nome], tudo bem? Aqui é [seu nome], da Controller Medicina e Segurança do Trabalho. Tentei te ligar agora. Vi que vocês trabalham com [atividade] em [cidade]: o PGR de vocês já foi revisado com os riscos psicossociais que a NR-01 passou a exigir em maio?"

## WhatsApp: retorno

> "[Nome], conseguiu ver minha mensagem? Se fizer sentido, um especialista nosso olha o PGR de vocês em 30 minutos. Terça às 10h ou quarta às 15h?"

## E-mail: primeiro contato

**Assunto:** [Empresa] e a revisão do PGR (NR-01)

> "Olá, [nome].
>
> Sou [seu nome], da Controller Medicina e Segurança do Trabalho. Desde 1991 cuidamos da saúde e segurança do trabalho de mais de 500 empresas.
>
> Desde maio a NR-01 exige os riscos psicossociais no PGR, e boa parte das empresas ainda não revisou. Para [atividade], isso costuma aparecer também nos eventos de SST do eSocial.
>
> Faz sentido 30 minutos com um especialista nosso para olhar como está o de vocês? Pode ser [dia] às [hora]?
>
> [assinatura com celular]"

## Mensagem de encerramento

A última da cadência. Costuma ser a que mais recebe resposta:

> "[Nome], imagino que não seja prioridade agora. Posso te procurar de novo em [mês]?"

Com resposta, marque a tarefa para o mês combinado. Sem resposta, siga a regra da próxima aula.

## Onde fica registrado

Cada mensagem enviada é uma tarefa **concluída** (tipo WhatsApp ou E-mail), com o que foi enviado em "O que aconteceu". A resposta do cliente vai no anexo da tarefa: print com **Ctrl+V**.
""",
            "quiz": [
                {
                    "enunciado": "O que NÃO entra no primeiro WhatsApp?",
                    "alternativas": [
                        ("O nome da pessoa", False),
                        ("O PDF da apresentação anexado", True),
                        ("Uma pergunta fácil de responder", False),
                        ("Um detalhe da empresa", False),
                    ],
                },
                {
                    "enunciado": "Quantas perguntas a mensagem escrita deve ter?",
                    "alternativas": [
                        ("Uma só", True),
                        ("Três, para qualificar", False),
                        ("Nenhuma", False),
                        ("Quantas couberem", False),
                    ],
                },
                {
                    "enunciado": "Onde fica o print da resposta do cliente?",
                    "alternativas": [
                        ("No celular do SDR", False),
                        ("No anexo da tarefa no HIPO (Ctrl+V)", True),
                        ("Num grupo de WhatsApp da equipe", False),
                        ("Não precisa guardar", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0516"),
            "titulo": "A cadência do primeiro contato",
            "resumo": "Os toques, em ordem, do dia em que a empresa é puxada até a mensagem de encerramento, e o que fazer quando ninguém responde.",
            "duracao_min": 8,
            "conteudo_md": """\
## Por que cadência

Uma ligação não atendida não é um "não". A maioria das reuniões sai do terceiro ao sexto toque. Cadência é a garantia de que nenhuma empresa puxada fica esquecida, e de que nenhuma é perseguida para sempre.

## A sequência padrão

Conta a partir do dia do primeiro contato (a data que você escolhe ao puxar da Prospecção):

1. **D0 · Ligação.** Não atendeu? WhatsApp de primeiro contato no mesmo dia.
2. **D1 · E-mail** de primeiro contato.
3. **D3 · Ligação**, em outro horário (se a primeira foi de manhã, ligue à tarde).
4. **D5 · WhatsApp** de retorno.
5. **D8 · Ligação.** Tente a recepção e peça pelo setor.
6. **D12 · WhatsApp** de encerramento.

São seis toques em menos de três semanas. Conseguiu falar e marcar? A cadência para ali.

## A cadência no HIPO

Cada toque é uma **tarefa**. Ao concluir uma, o HIPO pede a **próxima**: é aí que você marca o toque seguinte, com o tipo e o dia. A cadência anda sozinha, e a gestão enxerga quem está em qual toque.

- Ligou e não atendeu: conclua a tarefa com "não atendeu" e marque a próxima.
- Combinou retorno: marque a tarefa com o dia e a hora combinados.
- Falou e recusou de vez: finalize a oportunidade como **Perdido**, com o motivo.

## Quando ninguém responde

Seis toques sem nenhuma resposta: **finalize a oportunidade como Perdido**, com o motivo que descreve (sem retorno). Oportunidade aberta indefinidamente infla o funil e esconde o que de fato está andando. A empresa continua na base e pode ser trabalhada de novo mais tarde.

## Ritmo do dia

- **Manhã**: ligações (as atrasadas primeiro, depois as de hoje).
- **Fim da manhã e início da tarde**: WhatsApp e e-mails.
- **Tarde**: segunda rodada de ligações e as reuniões marcadas registradas.
- **Fim do dia**: nenhuma tarefa atrasada sem motivo. Se o prazo mudou, edite o prazo.

> A fila de Tarefas é a sua cadência. Coluna Atrasadas cheia é cadência quebrada: comece o dia por ela.
""",
            "tour": [
                _passo("/crm/tarefas", "tar-area", "A cadência é a sua fila",
                       "Cada toque é uma tarefa. **Atrasadas** é cadência quebrada: o dia começa por ela."),
                _passo("/crm/tarefas", "tar-acoes", "Concluir e marcar o próximo toque",
                       "Conclua com o resultado (\"não atendeu\", \"pediu retorno\") e marque a **próxima** tarefa: "
                       "o tipo e o dia do toque seguinte.",
                       clicar=["tar-cartao"]),
                _passo("/crm/tarefas", "tar-contadores", "A sua produção",
                       "**Realizadas no mês** mostra quantos toques você deu, por tipo."),
            ],
            "quiz": [
                {
                    "enunciado": "Quantos toques tem a cadência padrão do primeiro contato?",
                    "alternativas": [
                        ("Um", False),
                        ("Seis, em menos de três semanas", True),
                        ("Vinte", False),
                        ("Até o cliente responder, sem limite", False),
                    ],
                },
                {
                    "enunciado": "Seis toques sem nenhuma resposta. O que fazer?",
                    "alternativas": [
                        ("Deixar a oportunidade aberta", False),
                        ("Finalizar como Perdido, com o motivo", True),
                        ("Passar para o EV", False),
                        ("Recomeçar a cadência", False),
                    ],
                },
                {
                    "enunciado": "Como a cadência anda no HIPO?",
                    "alternativas": [
                        ("Numa planilha à parte", False),
                        ("Cada toque é uma tarefa; ao concluir, você marca a próxima", True),
                        ("O HIPO liga sozinho", False),
                        ("O gestor distribui todo dia", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0517"),
            "titulo": "Marcar a reunião e passar o bastão",
            "resumo": "Como marcar na agenda do EV, o que escrever para ele, como mover para Lead e como confirmar na véspera para não virar no-show.",
            "duracao_min": 9,
            "conteudo_md": """\
## Marcar

Na **Agenda**, escolha o EV em **Agenda de** e clique no horário livre que o cliente aceitou:

- **Cliente (oportunidade)**: a oportunidade da empresa.
- **Anfitrião**: o EV que vai conduzir.
- **Agendado por**: você. É daqui que sai o seu número de agendamentos.
- **Modalidade**: online (o Google cria o Meet) ou presencial (com endereço).
- **Contato do cliente**: o decisor, para ele receber o convite.

Ou, de dentro da oportunidade, **Agendar reunião**: o formulário já vem preso nela.

## Mover para Lead

Decisor + interesse com reunião marcada: mude a **Fase** para **Lead**. É isso que conta no quadro LEAD.

## O bastão: cinco linhas para o EV

Na **Descrição** da oportunidade, antes de fechar a tela:

1. **Decisor**: nome, cargo, e quem mais participa da decisão.
2. **O que ele disse**: a dor ou a dúvida, com as palavras dele.
3. **Situação atual**: quem cuida de SST hoje (fornecedor, interno, contador).
4. **Tamanho**: funcionários e unidades que ele informou.
5. **Por que aceitou**: o gancho que funcionou.

O EV prepara a reunião em 15 minutos com isso. Sem isso, ele pergunta de novo, e o cliente percebe que ninguém escutou.

## Confirmar na véspera

O no-show começa no agendamento mal feito. No dia útil anterior, mande um WhatsApp:

> "[Nome], tudo certo para amanhã às [hora] com o [EV]? O link está no convite. Qualquer coisa, me avisa por aqui."

Registre como tarefa concluída. Se o cliente pedir para mudar, edite a reunião com ele ainda na conversa: o horário novo já com o EV.

> Reunião marcada para "qualquer um" vira no-show. Reunião com o decisor, com o motivo escrito e confirmada na véspera, acontece.
""",
            "tour": [
                _passo("/crm/agenda", "age-agenda-de", "A agenda do EV",
                       "Escolha o EV aqui para ver só os horários dele."),
                _passo("/crm/agenda", "reuniao-anfitriao", "Anfitrião: o EV",
                       "Clicando num horário livre abre o formulário. **Anfitrião** é o EV que conduz. Nada é gravado até Marcar e enviar convite.",
                       clicar=["age-celula-livre"]),
                _passo("/crm/agenda", "reuniao-agendado-por", "Agendado por: você",
                       "O crédito do agendamento. Vem com você.",
                       clicar=["age-celula-livre"]),
                _passo("/crm/oportunidades", "opo-det-fase", "Mover para Lead",
                       "Decisor + interesse com reunião marcada: **Fase = Lead**. Muda na hora.",
                       clicar=["opo-cartao-abrir"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "O bastão para o EV",
                       "Em **Descrição**, as cinco linhas: decisor, o que ele disse, situação atual, tamanho e por que aceitou. "
                       "Depois, **Salvar**.",
                       clicar=["opo-cartao-abrir", "aba-dados"]),
            ],
            "quiz": [
                {
                    "enunciado": "Quem vai em Anfitrião quando o SDR marca para o EV?",
                    "alternativas": [
                        ("O SDR", False),
                        ("O EV que vai conduzir", True),
                        ("O decisor do cliente", False),
                        ("O gestor", False),
                    ],
                },
                {
                    "enunciado": "O que entra nas cinco linhas do bastão?",
                    "alternativas": [
                        ("Preço e desconto combinados", False),
                        ("Decisor, o que ele disse, situação atual, tamanho e por que aceitou", True),
                        ("Só o telefone do cliente", False),
                        ("A apresentação da Controller", False),
                    ],
                },
                {
                    "enunciado": "Quando confirmar a reunião com o cliente?",
                    "alternativas": [
                        ("Não precisa confirmar", False),
                        ("No dia útil anterior, por WhatsApp", True),
                        ("Uma semana depois", False),
                        ("Só se o EV pedir", False),
                    ],
                },
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# MÉTODO 03 — Roteiro do EC
# ═════════════════════════════════════════════════════════════════════

METODO_03 = {
    "id": _id("b0600"),
    "titulo": "Método 03 · Roteiro do EC",
    "pilar": "metodo",
    "reforca": "tarefas_no_prazo",
    "descricao": (
        "O roteiro do canal de indicação: por que o contador é o melhor "
        "parceiro, a primeira abordagem ao escritório, a reunião de parceria, "
        "as objeções do contador, como receber e devolver cada indicação e o "
        "ritmo que mantém a carteira ativa."
    ),
    "prazo_dias": 50,
    "obrigatorios": ("EC",),
    "opcionais": GESTAO_OPCIONAL,
    "aulas": [
        {
            "id": _id("b0611"),
            "titulo": "Por que o contador é o melhor canal",
            "resumo": "A dor do escritório de contabilidade com SST, o que a Controller oferece a ele e a meta do EC em uma frase.",
            "duracao_min": 8,
            "conteudo_md": """\
## A meta do EC em uma frase

**O EC transforma escritórios de contabilidade em parceiros que indicam clientes, e mantém essa relação viva.** A métrica que importa é indicação que vira cliente, e o contato que faz a próxima indicação acontecer.

## Por que o contador

- **Ele já está dentro de dezenas de empresas.** Um escritório médio atende muitas empresas com funcionários CLT, todas obrigadas a ter PGR, PCMSO e ASO.
- **Ele envia o eSocial de SST.** Os eventos S-2220 (monitoramento da saúde) e S-2240 (condições ambientais) passam pela mão dele, mas o conteúdo técnico vem do fornecedor de SST.
- **Ele é cobrado quando dá errado.** Evento recusado, dado faltando, ASO que não chegou: o cliente liga para o contador.
- **O cliente confia nele.** Indicação de contador chega com uma credibilidade que nenhuma ligação fria tem.

## A dor do escritório

- Fornecedor de SST que não manda os dados a tempo para o eSocial.
- Retrabalho corrigindo eventos de SST recusados.
- Clientes perguntando sobre a NR-01 e os riscos psicossociais, e o escritório sem resposta.
- Cada cliente com um fornecedor diferente, cada um com um jeito.

## O que a Controller oferece ao parceiro

1. **Um parceiro de SST que resolve o eSocial dos clientes dele**: dados técnicos certos e no prazo, um padrão só para todos os clientes indicados.
2. **Comissão recorrente**: enquanto o cliente indicado estiver ativo, o escritório recebe. O percentual e as regras de pagamento são os da tabela vigente, que a gestão informa. **Nunca prometa outro número.**
3. **Resposta para o cliente dele**: o contador passa a ter o que dizer quando o cliente pergunta da NR-01.
4. **Ninguém mexe na carteira contábil dele.** A Controller não faz contabilidade.

> O contador não compra SST. Ele compra tranquilidade com os clientes dele, e uma receita a mais. É isso que o EC vende.
""",
            "quiz": [
                {
                    "enunciado": "Por que o contador é um bom canal de indicação?",
                    "alternativas": [
                        ("Porque faz o PGR dos clientes", False),
                        ("Porque está dentro de dezenas de empresas, envia o eSocial de SST e é cobrado quando dá errado", True),
                        ("Porque é obrigado por lei a indicar", False),
                        ("Porque compra SST para os clientes", False),
                    ],
                },
                {
                    "enunciado": "O contador pergunta o percentual da comissão. O que o EC responde?",
                    "alternativas": [
                        ("Um número que pareça atraente", False),
                        ("O percentual da tabela vigente informada pela gestão, sem prometer outro número", True),
                        ("Que não existe comissão", False),
                        ("Que depende do humor do gestor", False),
                    ],
                },
                {
                    "enunciado": "Quais eventos do eSocial de SST passam pela mão do contador?",
                    "alternativas": [
                        ("S-1200 e S-1210", False),
                        ("S-2220 e S-2240", True),
                        ("S-1000 e S-1005", False),
                        ("Nenhum", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0612"),
            "titulo": "A primeira abordagem ao escritório",
            "resumo": "De onde vêm os escritórios, quem procurar, a ligação e o WhatsApp para conseguir a reunião com o sócio.",
            "duracao_min": 8,
            "conteudo_md": """\
## De onde vêm os escritórios

- **Base da Receita**: CNAE **6920-6/01** (atividades de contabilidade). Peça à gestão ou ao SDR a fatia da sua região na Prospecção.
- **Indicação de cliente**: todo cliente da Controller tem um contador. Pergunte qual é.
- **Contador que já aparece nas conversas**: "o contador cuida disso" é uma pista. Pergunte o nome do escritório.

Escritório que ainda não existe no HIPO: cadastre em **Contas** e marque **Finder**. Ele entra na sua carteira em Parceiros.

## Quem procurar

O **sócio** do escritório, ou o responsável pelo departamento pessoal (DP), que é quem envia o eSocial. A decisão de indicar é do sócio.

## A ligação

> "Oi, [nome], aqui é [seu nome], da Controller Medicina e Segurança do Trabalho, de Guarulhos. Te peguei num momento ruim?"
>
> "A gente cuida da saúde e segurança do trabalho de mais de 500 empresas, e trabalha junto com vários escritórios de contabilidade no eSocial de SST. Uma pergunta: hoje, quando um cliente seu precisa de PGR ou de exame, para quem vocês mandam?"

Ouça. Depois:

> "E os eventos S-2220 e S-2240 chegam certinhos desses fornecedores, ou dá retrabalho?"

O pedido:

> "Queria te mostrar em 30 minutos como a gente trabalha com escritórios parceiros, inclusive a parte de comissão. Terça às 10h ou quinta às 15h?"

## O WhatsApp

> "Oi, [nome], tudo bem? Aqui é [seu nome], da Controller Medicina e Segurança do Trabalho. Trabalhamos com escritórios de contabilidade no eSocial de SST dos clientes deles, com comissão recorrente para o escritório. Os eventos S-2220 e S-2240 dos seus clientes chegam sem retrabalho hoje?"

## Registre

Cada contato é uma **tarefa do parceiro** (aba Tarefas do parceiro). A reunião vai na agenda com **Parceiro (contador)**. É isso que deixa o farol verde.

> Escritório não é cliente: não fale de exame nem de preço de exame. Fale do eSocial dele e da tranquilidade com os clientes dele.
""",
            "quiz": [
                {
                    "enunciado": "Qual CNAE identifica escritórios de contabilidade na base da Receita?",
                    "alternativas": [
                        ("6920-6/01", True),
                        ("8630-5/03", False),
                        ("4120-4/00", False),
                        ("6201-5/01", False),
                    ],
                },
                {
                    "enunciado": "Quem decide a parceria no escritório?",
                    "alternativas": [
                        ("O estagiário", False),
                        ("O sócio", True),
                        ("A recepção", False),
                        ("O cliente do escritório", False),
                    ],
                },
                {
                    "enunciado": "O escritório não existe no HIPO. Como ele entra na carteira?",
                    "alternativas": [
                        ("Pedindo para a TI cadastrar", False),
                        ("Cadastrando em Contas e marcando Finder", True),
                        ("Importando uma planilha", False),
                        ("Só quando fechar a primeira venda", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0613"),
            "titulo": "A reunião de parceria",
            "resumo": "Os 30 minutos com o sócio: contrato de abertura, diagnóstico do escritório, o programa de parceria e o fechamento com a primeira indicação nomeada.",
            "duracao_min": 10,
            "conteudo_md": """\
## A estrutura (30 minutos)

1. **Abertura · 3 min.** Rapport e contrato de abertura.
2. **Diagnóstico · 12 min.** O sócio diz, com as palavras dele, onde SST dá trabalho no escritório.
3. **Programa · 8 min.** Como a parceria funciona, ligado ao que ele disse.
4. **Objeções · 4 min.** LAER.
5. **Fechamento · 3 min.** Parceria aceita e **a primeira indicação com nome**.

## Abertura

> "Obrigado pelo tempo, [nome]. Combinamos 30 minutos, ainda está bom? A ideia é eu entender como vocês lidam hoje com a parte de SST dos clientes, e depois mostrar como funciona a parceria. No final a gente decide junto se faz sentido. Pode ser?"

## Diagnóstico (SPIN para escritório)

- **Situação**: "Quantos clientes vocês atendem com funcionário CLT? Quem envia o eSocial de SST?"
- **Problema**: "O que mais dá trabalho nos eventos S-2220 e S-2240? Algum fornecedor que atrasa?"
- **Implicação**: "Quando um evento é recusado, quantas horas o DP gasta correndo atrás? E quem o cliente cobra?"
- **Necessidade**: "Se os clientes que vocês indicassem tivessem o SST num padrão só, com os dados no prazo, o que mudaria para o DP?"

Feche com o resumo: "Deixa eu ver se entendi: [situação], o que mais pesa é [problema], e isso custa [implicação]. É isso?"

## O programa

- **Como indicar**: o contador passa o nome da empresa e o contato; o EC registra e o especialista (EV) conduz a reunião com o cliente.
- **Devolutiva**: o contador fica sabendo de cada passo (reunião marcada, proposta, fechamento).
- **eSocial**: os dados técnicos dos clientes indicados saem no padrão da Controller, no prazo.
- **Comissão recorrente** enquanto o cliente indicado estiver ativo, pela tabela vigente.
- **A Controller não faz contabilidade**: o cliente continua dele.

## Fechamento: a primeira indicação

A parceria só existe de verdade quando a primeira indicação tem nome. Peça na reunião:

> "Pensando no que você me contou, qual cliente seu hoje tem mais dor com isso? Consegue me apresentar a ele esta semana?"

Saia com: nome da empresa, contato, e o combinado de como o contador vai apresentar (mensagem dele, e-mail com cópia, ou ligação a três).

> Reunião de parceria que termina sem um nome de cliente termina em "vou pensar em alguém". Peça o nome enquanto a dor está na mesa.
""",
            "quiz": [
                {
                    "enunciado": "Qual é o fechamento ideal da reunião de parceria?",
                    "alternativas": [
                        ("Mandar o contrato por e-mail", False),
                        ("Parceria aceita e a primeira indicação com nome", True),
                        ("Marcar outra reunião em 3 meses", False),
                        ("Vender exames para o escritório", False),
                    ],
                },
                {
                    "enunciado": "Qual é uma boa pergunta de Implicação para o sócio do escritório?",
                    "alternativas": [
                        ("\"Quantos clientes vocês têm?\"", False),
                        ("\"Quando um evento é recusado, quantas horas o DP gasta correndo atrás? E quem o cliente cobra?\"", True),
                        ("\"Quer ser nosso parceiro?\"", False),
                        ("\"Qual software contábil vocês usam?\"", False),
                    ],
                },
                {
                    "enunciado": "O contador teme perder o cliente. O que o programa garante?",
                    "alternativas": [
                        ("Nada", False),
                        ("A Controller não faz contabilidade: o cliente continua dele", True),
                        ("Que o cliente não pode trocar de contador", False),
                        ("Desconto na mensalidade do escritório", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0614"),
            "titulo": "Objeções do contador",
            "resumo": "As seis objeções que mais aparecem na conversa com escritórios, com a pergunta de exploração e a resposta.",
            "duracao_min": 8,
            "conteudo_md": """\
## O método

O mesmo LAER do Roteiro de Vendas: **Listar** (ouça até o fim), **Acolher**, **Explorar** com uma pergunta e só então **Responder**. Com contador, a objeção quase sempre é sobre **risco de relacionamento**: ele não quer indicar alguém que vai queimá-lo com o cliente.

## As seis mais comuns

**"Meus clientes já têm SST."**
- Explore: "Todos? E os eventos desses fornecedores chegam sem retrabalho?"
- Responda: "Então a parceria vale para os que ainda não têm, e para os que têm e reclamam. Basta um."

**"Não quero indicar e me queimar."**
- Explore: "Entendo. O que faria você se sentir seguro para indicar?"
- Responda: devolutiva de cada passo, o especialista conduz com o roteiro da casa, e a primeira indicação pode ser um cliente que já reclama do fornecedor atual.

**"Já sou parceiro de outra clínica."**
- Explore: "E está funcionando? Os clientes que você indicou estão satisfeitos?"
- Responda: não fale mal de ninguém. "Ótimo ter mais de uma opção para cada perfil de cliente. Cliente com várias unidades, por exemplo, é onde a gente costuma fazer diferença."

**"Não tenho tempo."**
- Explore: "O que leva mais tempo, achar o cliente ou apresentar?"
- Responda: "Você só passa o nome e o contato. O resto é com a gente, e eu te aviso a cada passo."

**"Quanto eu ganho?"**
- Explore: "Você pensa em comissão por cliente ou no total da carteira?"
- Responda: a comissão recorrente pela tabela vigente, enquanto o cliente estiver ativo. Mostre como ela soma com o tempo; não prometa número fora da tabela.

**"Meus clientes são pequenos."**
- Explore: "Têm funcionário CLT?"
- Responda: "A NR-01 vale para toda empresa com funcionário CLT, e o risco psicossocial existe em qualquer escritório. É justamente o cliente pequeno que mais pergunta."

> Contador que objeta está calculando risco. Diminua o risco (devolutiva, primeira indicação fácil) antes de falar de ganho.
""",
            "quiz": [
                {
                    "enunciado": "Qual é a preocupação por trás da maioria das objeções do contador?",
                    "alternativas": [
                        ("Preço do exame", False),
                        ("Risco de se queimar com o cliente", True),
                        ("Falta de interesse em dinheiro", False),
                        ("O software do eSocial", False),
                    ],
                },
                {
                    "enunciado": "\"Já sou parceiro de outra clínica.\" O que NÃO fazer?",
                    "alternativas": [
                        ("Perguntar se está funcionando", False),
                        ("Falar mal da outra clínica", True),
                        ("Mostrar onde a Controller faz diferença", False),
                        ("Acolher a objeção", False),
                    ],
                },
                {
                    "enunciado": "Como diminuir o risco percebido pelo contador?",
                    "alternativas": [
                        ("Prometer comissão maior", False),
                        ("Devolutiva a cada passo e uma primeira indicação de cliente que já reclama do fornecedor", True),
                        ("Pedir exclusividade", False),
                        ("Mandar o contrato antes da reunião", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0615"),
            "titulo": "Receber e devolver cada indicação",
            "resumo": "O caminho da indicação no HIPO, com o parceiro como Finder e você como EC, e a devolutiva que faz o contador indicar de novo.",
            "duracao_min": 9,
            "conteudo_md": """\
## Recebeu um nome

No mesmo dia:

1. **Conta**: a empresa indicada (se não existir, crie em Contas com o CNPJ).
2. **Oportunidade** nessa conta, em **Suspect** ou **Lead** (Lead quando o contador já confirmou o interesse do cliente).
3. Aba **Dados**: **Finder = o escritório parceiro**. É isso que liga a indicação a ele, conta na conversão dele e aparece no mini-funil.
4. Aba **Envolvidos**: você com o papel **EC**. É isso que conta como venda com EC.
5. **Descrição**: o que o contador contou do cliente (dor, fornecedor atual, tamanho, contato).

## Quem marca a reunião com o cliente

O cliente indicado vai para a reunião de 45 minutos com o **EV**, como qualquer cliente. Marque na agenda do EV (anfitrião: o EV; agendado por: você) ou peça ao SDR. Se o contador quiser estar presente, convide.

## A devolutiva

O contador indica de novo quando sabe o que aconteceu com a indicação anterior. Avise em cada passo, por WhatsApp:

- **Reunião marcada**: "Falei com o [cliente], reunião [dia]. Obrigado pela indicação!"
- **Proposta apresentada**: "Apresentamos a proposta, ele vai decidir até [data]."
- **Fechou**: "Fechamos com o [cliente]! Ele entra na sua comissão a partir de [mês]."
- **Não fechou**: "Não foi desta vez, o motivo foi [motivo]. Obrigado pela confiança." (Perda bem explicada mantém a confiança.)

Cada devolutiva é uma **tarefa do parceiro** concluída: conta no farol.

## A conversão do parceiro

Conversão = indicações conquistadas ÷ indicações que chegaram ao fim. **Cancelado** fica fora (é erro de cadastro). Registrar perda como cancelamento infla a conversão e esconde o problema.

> Indicação sem Finder é indicação perdida: não entra na carteira, nem na comissão, nem na sua avaliação.
""",
            "tour": [
                _passo("/crm/oportunidades", "opo-det-conteudo", "Finder: o parceiro",
                       "Na aba **Dados**, **Finder** é o escritório que indicou. Sem isso a indicação não conta para ele.",
                       clicar=["opo-cartao-abrir", "aba-dados"]),
                _passo("/crm/oportunidades", "opo-det-conteudo", "Você como EC",
                       "Na aba **Envolvidos**, você com o papel **EC**. É isso que conta como venda com EC.",
                       clicar=["opo-cartao-abrir", "aba-envolvidos"]),
                _passo("/crm/parceiros", "par-det-conteudo", "A devolutiva é tarefa",
                       "Cada aviso ao contador é uma tarefa do parceiro concluída: é isso que deixa o farol verde.",
                       clicar=["par-linha", "aba-tarefas"]),
                _passo("/crm/parceiros", "par-det-conteudo", "As indicações do parceiro",
                       "Tudo o que ele indicou, com status e fase. É daqui que sai a devolutiva.",
                       clicar=["par-linha", "aba-indicacoes"]),
            ],
            "quiz": [
                {
                    "enunciado": "O que liga a oportunidade ao escritório que indicou?",
                    "alternativas": [
                        ("O campo Finder na aba Dados", True),
                        ("O nome do contador na descrição", False),
                        ("Uma tarefa de parceiro", False),
                        ("Nada, é automático", False),
                    ],
                },
                {
                    "enunciado": "A indicação não fechou. O que o EC faz com o contador?",
                    "alternativas": [
                        ("Não fala nada", False),
                        ("Avisa, com o motivo, e agradece pela confiança", True),
                        ("Registra como Cancelado para não estragar a conversão", False),
                        ("Pede outra indicação na mesma mensagem e não explica", False),
                    ],
                },
                {
                    "enunciado": "Quem conduz a reunião com o cliente indicado?",
                    "alternativas": [
                        ("O contador", False),
                        ("O EV, na reunião de 45 minutos do roteiro", True),
                        ("Ninguém, manda a proposta direto", False),
                        ("O SDR", False),
                    ],
                },
            ],
        },
        {
            "id": _id("b0616"),
            "titulo": "O ritmo da carteira",
            "resumo": "Com que frequência falar com cada parceiro conforme a situação, o que levar em cada contato e como usar o farol para planejar a semana.",
            "duracao_min": 8,
            "conteudo_md": """\
## O ritmo pela situação

A situação do parceiro (pela última indicação) diz o ritmo:

- **Ativo** (indicou nos últimos 90 dias): **contato toda semana**. Devolutiva das indicações em andamento, e pedido da próxima.
- **Esfriando** (90 a 180 dias): **reunião de reativação** no mês. "O que mudou? Algum cliente com a dor de NR-01?"
- **Dormente** (mais de 180 dias): **ligação de reengajamento** no mês, com conteúdo útil. Duas tentativas sem resposta: converse com a gestão sobre tirar da carteira.
- **Sem indicação** (nunca indicou): **contato a cada duas semanas** até a primeira indicação com nome.

## O que levar em cada contato

Contato sem motivo vira cobrança. Leve sempre uma coisa útil:

- **Devolutiva** de uma indicação.
- **Calendário do eSocial de SST** e o que vence no mês.
- **Checklist da NR-01 psicossocial** para o contador mandar aos clientes.
- **Novidade de norma** que gera pergunta dos clientes dele.
- **Convite** para uma conversa rápida no escritório dele (visita).

E sempre feche com o pedido: "Algum cliente seu está com essa dor agora?"

## A semana pelo farol

Segunda de manhã, em **Parceiros**:

1. Filtre **EC responsável = você**.
2. Clique em **Sem contato**: são os que ainda não tiveram contato na semana. Cada um vira uma tarefa para esta semana.
3. Olhe os **Dormentes** e os **esfriando**: marque as reativações do mês.
4. Abra os de **mini-funil** cheio: devolutiva das indicações em andamento.

Sexta à tarde: o farol da semana deve estar verde para todos os **ativos**.

## Reunião de carteira

Pelo menos uma reunião por trimestre com cada parceiro ativo, na agenda com **Parceiro (contador)**. É o que conta como **reunião de carteira** e no quadro **PARCERIAS** do Monitor, quando realizada e com desfecho registrado.

> Parceiro que só ouve falar da Controller quando o EC precisa de indicação para de atender. Parceiro que recebe algo útil toda semana lembra da Controller quando o cliente pergunta.
""",
            "tour": [
                _passo("/crm/parceiros", "par-filtro-ec", "A sua carteira",
                       "Segunda de manhã: **EC responsável = você**."),
                _passo("/crm/parceiros", "par-kpis", "Sem contato, Dormentes",
                       "**Sem contato** é a lista da semana; **Dormentes** são as reativações do mês. Os dois filtram a lista."),
                _passo("/crm/parceiros", "par-lista", "Farol e mini-funil",
                       "O farol das 4 semanas mostra o ritmo; o mini-funil mostra as indicações que pedem devolutiva."),
                _passo("/crm/agenda", "age-assunto", "Reunião de carteira",
                       "A Agenda do EC abre em **Parceiros**. Uma reunião por trimestre com cada ativo, com desfecho registrado."),
            ],
            "quiz": [
                {
                    "enunciado": "Com que frequência falar com um parceiro Ativo?",
                    "alternativas": [
                        ("Uma vez por ano", False),
                        ("Toda semana", True),
                        ("Só quando precisar de indicação", False),
                        ("Nunca, ele já indica sozinho", False),
                    ],
                },
                {
                    "enunciado": "O que levar num contato com o parceiro?",
                    "alternativas": [
                        ("Só o pedido de indicação", False),
                        ("Algo útil (devolutiva, calendário do eSocial, checklist NR-01) e o pedido no final", True),
                        ("A tabela de preços dos exames", False),
                        ("Nada, só um \"oi\"", False),
                    ],
                },
                {
                    "enunciado": "Onde começa o planejamento da semana do EC?",
                    "alternativas": [
                        ("Em Parceiros, filtrando você e abrindo Sem contato", True),
                        ("Na Prospecção", False),
                        ("No Relatório anual", False),
                        ("No Perfil", False),
                    ],
                },
            ],
        },
    ],
}


TRILHAS_ROTEIROS: list[dict] = [METODO_02, METODO_03]
