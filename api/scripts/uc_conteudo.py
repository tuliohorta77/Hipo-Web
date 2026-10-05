"""
HIPO — UC: conteúdo das três primeiras trilhas da Universidade Corporativa.

  01 · Boas-vindas à Controller           Técnica  (prazo 10 dias)
  02 · Conceitos gerais de SST            Técnica  (prazo 20 dias)
  03 · Produto e normas                   Técnica  (prazo 30 dias)
  04 · Técnicas de venda consultiva       Técnica  (prazo 40 dias)
  Método 01 · Roteiro de vendas Controller Método  (prazo 45 dias)
  HIPO - SDR / HIPO - EV / HIPO - EC      Método  (prazo 15 dias, uma por
                                                   função; em uc_conteudo_hipo.py)
  Método 02 · Roteiro do SDR / Método 03 · Roteiro do EC
                                          Método  (prazo 50 dias; em
                                                   uc_conteudo_roteiros.py)
  Energia 01 · Rotina, volume e metas     Energia (prazo 60 dias; em
                                                   uc_conteudo_energia.py)

01 a 03 são obrigatórias para SDR, EV, EC, EP e ADM. 04 e Método 01 são
do time comercial (SDR, EV, EC); EP e ADM podem fazer, sem obrigação. O
Franqueado vê todas, sem obrigação, para a gestão conseguir fazer e
revisar. Cada trilha pode declarar `obrigatorios` e `opcionais`; sem
isso valem CARGOS_OBRIGATORIOS e CARGOS_OPCIONAIS.

A divisão entre os pilares segue o pedido do Tulio (02/10/2026): a 04
ensina as técnicas em profundidade (SPIN, GPCT + BA/C&I, LAER, Sandler,
Challenger, escuta e fechamento); a Método 01 ensina a aplicá-las na
Controller, com o resto da metodologia (preparação, apresentação
reordenada, objeções, follow-up, scorecard e métricas), a partir do
"Roteiro de Vendas — Controller Med Seg".

Fontes:
  * trilha 01: a apresentação institucional "Controller Med Seg -
    Apresentação" (anexada à aula 1);
  * trilha 02: o vocabulário das NRs e do eSocial, só no que vale para
    qualquer cliente; prazos de norma ficam no PCMSO de cada cliente;
  * trilha 03: o portfólio ligado às normas + NR-01 (redação da Portaria
    MTE 1.419/2024, item 1.5 em vigor desde 26/05/2026) e NR-04 (Portaria
    MTP 2.318/2022), com os PDFs oficiais anexados.

A trilha 03 reaproveita o id da trilha "Normas Regulamentadoras: NR-01 e
NR-04" carregada na entrega 029: a carga com --atualizar renomeia aquela
trilha e encaixa a aula de produto na frente, sem perder o progresso de
ninguém (as aulas de NR mantêm id e versão).

O QUIZ de cada aula já está escrito e entra na UC-2.

Este arquivo é só dado. Quem grava é scripts/semear_uc.py.
"""
from __future__ import annotations

from uuid import UUID

# Quem faz as trilhas de base. Franqueado entra sem obrigação.
CARGOS_OBRIGATORIOS = ("SDR", "EV", "EC", "EP", "ADM")
CARGOS_OPCIONAIS = ("Franqueado",)

# Material de apoio: chave -> (nome exibido, arquivo esperado na pasta de PDFs).
PDFS: dict[str, tuple[str, str]] = {
    "apresentacao": ("Apresentação institucional Controller.pdf", "apresentacao-controller.pdf"),
    "nr01": ("NR-01 (texto oficial, atualizado 2025).pdf", "nr-01.pdf"),
    "nr04": ("NR-04 (texto oficial, atualizado 2023).pdf", "nr-04.pdf"),
    "roteiro": ("Roteiro de Vendas - Controller Med Seg.pdf", "roteiro-vendas.pdf"),
    "energia": ("Energia 01 - Rotina, volume e metas.pdf", "energia-01.pdf"),
}

# ═════════════════════════════════════════════════════════════════════
# TRILHA 01 — Boas-vindas à Controller
# ═════════════════════════════════════════════════════════════════════
# Fonte: a apresentação institucional "Controller Med Seg - Apresentação"
# (anexada à aula 1). Números e história como estão nela.

TRILHA_01 = {
    "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0100"),
    "titulo": "01 · Boas-vindas à Controller",
    "pilar": "tecnica",
    "descricao": (
        "Quem é a Controller Medicina e Segurança do Trabalho, de onde ela vem, "
        "o que vende, por que os clientes escolhem a gente e como você trabalha aqui."
    ),
    "prazo_dias": 10,
    "aulas": [
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0111"),
            "titulo": "Bem-vindo(a) à Controller",
            "resumo": "Nossa história desde 1991, os números que contamos para o cliente e o que nos move.",
            "duracao_min": 8,
            "pdf": "apresentacao",
            "conteudo_md": """\
## Que bom ter você aqui

A **Controller Medicina e Segurança do Trabalho** cuida da saúde e da segurança de quem trabalha nas empresas que atendemos. A frase que resume o nosso papel está na abertura da nossa apresentação: **organizar as ações de saúde ocupacional do cliente com mais planejamento e suporte**.

Esta trilha é a sua porta de entrada. Ela não ensina norma nem técnica de venda (isso vem nas trilhas 02 e 03): ela conta quem somos, para você falar da empresa com a mesma segurança de quem está aqui há anos.

## Nossa história

- **1991, o início de uma visão.** A empresa foi fundada pelo **Dr. Paulo Dick**, em **Guarulhos**, com a missão de promover saúde, segurança e qualidade de vida no ambiente de trabalho, sempre com excelência e respeito à legislação.
- **Hoje, referência em Medicina Ocupacional.** Atendemos empresas de todo o Brasil, com tecnologia, inovação e o mesmo compromisso que deu origem à empresa: **cuidar das pessoas**.

## Os números que você vai repetir

- **Mais de 30 anos** protegendo o bem mais precioso da empresa do cliente: os colaboradores dela.
- **Mais de 100 mil vidas atendidas.**
- **Mais de 500 clientes atendidos**, incluindo redes conhecidas de alimentação e varejo (os logos estão na apresentação).
- **Cobertura em todo o território nacional.**
- **Atendimento 100% humanizado.**

> Na conversa com o cliente: número sem contexto é propaganda. Use o número para responder a uma dúvida que o cliente já mostrou. "Vocês atendem filial em outro estado?" → "Atendemos o Brasil inteiro, e são mais de 500 clientes hoje. Quantas unidades vocês têm fora de São Paulo?"

## Onde estamos

Rua Tapaciquara, 75, Guarulhos/SP, CEP 07114-220. Telefone e WhatsApp comercial (11) 4268-0032, e-mail comercial@controllermedseg.com.

## O material

A apresentação institucional completa está em **Material de apoio**, logo abaixo. É o mesmo arquivo que o cliente recebe. Leia inteira antes da sua primeira reunião.
""",
            "quiz": [
                {
                    "enunciado": "Em que ano e cidade a Controller foi fundada?",
                    "alternativas": [
                        ("2001, em São Paulo", False),
                        ("1991, em Guarulhos", True),
                        ("1991, em Campinas", False),
                        ("2011, em Guarulhos", False),
                    ],
                },
                {
                    "enunciado": "Quantas vidas a Controller já atendeu, segundo a apresentação institucional?",
                    "alternativas": [
                        ("Mais de 10 mil", False),
                        ("Mais de 100 mil", True),
                        ("Mais de 1 milhão", False),
                        ("Mais de 500", False),
                    ],
                },
                {
                    "enunciado": "Qual destas frases resume o compromisso que deu origem à empresa?",
                    "alternativas": [
                        ("Vender o menor preço do mercado", False),
                        ("Cuidar das pessoas", True),
                        ("Emitir ASO no mesmo dia", False),
                        ("Atender só a região de Guarulhos", False),
                    ],
                },
                {
                    "enunciado": "O cliente pergunta: \"Vocês atendem filial em outro estado?\". Como a aula orienta usar os números da Controller nessa hora?",
                    "alternativas": [
                        ("Usar o número para responder à dúvida dele e seguir com uma pergunta", True),
                        ("Recitar todos os números da empresa logo na abertura da conversa", False),
                        ("Evitar citar números, porque soa como propaganda", False),
                        ("Enviar a apresentação e esperar que ele leia os números", False),
                    ],
                },
                {
                    "enunciado": "Segundo a apresentação institucional, quantos clientes a Controller já atendeu?",
                    "alternativas": [
                        ("Mais de 50", False),
                        ("Mais de 500", True),
                        ("Mais de 5 mil", False),
                        ("Mais de 100 mil", False),
                    ],
                },
                {
                    "enunciado": "O que você deve fazer com a apresentação institucional antes da sua primeira reunião?",
                    "alternativas": [
                        ("Ler só o slide de números, que é o que o cliente pergunta", False),
                        ("Nada, ela é de uso exclusivo da diretoria", False),
                        ("Ler inteira, pois é o mesmo arquivo que o cliente recebe", True),
                        ("Resumir em uma página e enviar no lugar dela", False),
                    ],
                },
                {
                    "enunciado": "Qual frase, na abertura da apresentação, resume o papel da Controller?",
                    "alternativas": [
                        ("Oferecer os exames ocupacionais pelo menor preço da região de Guarulhos", False),
                        ("Assumir toda a gestão de pessoas e da folha de pagamento do cliente", False),
                        ("Fazer exames ocupacionais sem necessidade de agendamento prévio", False),
                        ("Organizar as ações de saúde ocupacional do cliente com mais planejamento e suporte", True),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0112"),
            "titulo": "O que a Controller vende",
            "resumo": "As quatro frentes do portfólio: Medicina Ocupacional, Segurança do Trabalho, Gestão e Compliance, Saúde e Bem-estar.",
            "duracao_min": 10,
            "conteudo_md": """\
## Quatro frentes, um parceiro só

O portfólio da Controller se divide em quatro frentes. Saber a qual frente cada pedido do cliente pertence é o que permite montar uma proposta completa, em vez de vender só o exame que ele pediu.

## 1. Medicina Ocupacional

Os exames que acompanham a vida do trabalhador na empresa:

- exames **admissionais**;
- exames **periódicos**;
- exames **demissionais**;
- **retorno ao trabalho**;
- **mudança de risco**;
- **exames complementares** (os que o médico pede além da consulta, como audiometria ou exames laboratoriais, conforme o risco).

## 2. Segurança do Trabalho

Os programas e laudos que mostram que a empresa conhece e controla os seus riscos:

- **PGR** (Programa de Gerenciamento de Riscos);
- **PCMSO** (Programa de Controle Médico de Saúde Ocupacional);
- **LTCAT** (Laudo Técnico das Condições Ambientais do Trabalho);
- **laudos técnicos**;
- **análises ergonômicas**;
- **avaliações ambientais**;
- atendimento às **NRs diversas**.

## 3. Gestão e Compliance

O que tira o peso da rotina do RH do cliente:

- **gestão do eSocial**;
- **auditorias e diagnósticos**;
- **gestão de documentação**;
- **indicadores e relatórios gerenciais**;
- **suporte técnico especializado**.

## 4. Saúde e Bem-estar

O que vai além da obrigação legal:

- **campanhas de saúde**;
- **programas preventivos**;
- **atendimento ocupacional**;
- **consultoria para RH e gestores**.

> Na conversa com o cliente: quase ninguém liga pedindo "Gestão e Compliance". O cliente liga pedindo um admissional. A pergunta seguinte é sua: "E o PCMSO de vocês, quem faz? Está em dia no eSocial?" É assim que um exame vira um contrato.

O detalhe de cada sigla (o que é, qual norma exige, quem precisa) está na trilha **02 · Conceitos gerais de SST**.
""",
            "quiz": [
                {
                    "enunciado": "Em qual frente do portfólio está a gestão do eSocial?",
                    "alternativas": [
                        ("Medicina Ocupacional", False),
                        ("Segurança do Trabalho", False),
                        ("Gestão e Compliance", True),
                        ("Saúde e Bem-estar", False),
                    ],
                },
                {
                    "enunciado": "O exame de retorno ao trabalho pertence a qual frente?",
                    "alternativas": [
                        ("Medicina Ocupacional", True),
                        ("Gestão e Compliance", False),
                        ("Saúde e Bem-estar", False),
                        ("Nenhuma, não vendemos", False),
                    ],
                },
                {
                    "enunciado": "Um cliente pede só um exame admissional. Qual é a atitude esperada?",
                    "alternativas": [
                        ("Vender o exame e encerrar o atendimento", False),
                        ("Perguntar sobre PCMSO, PGR e eSocial para entender o resto da necessidade", True),
                        ("Recusar, porque só vendemos contrato", False),
                        ("Mandar a apresentação e esperar o retorno", False),
                    ],
                },
                {
                    "enunciado": "O cliente pede um PGR e um LTCAT. A qual frente do portfólio esses serviços pertencem?",
                    "alternativas": [
                        ("Segurança do Trabalho", True),
                        ("Medicina Ocupacional", False),
                        ("Gestão e Compliance", False),
                        ("Saúde e Bem-estar", False),
                    ],
                },
                {
                    "enunciado": "Audiometria e exames laboratoriais pedidos pelo médico conforme o risco são chamados de:",
                    "alternativas": [
                        ("Exames de mudança de risco", False),
                        ("Exames complementares", True),
                        ("Avaliações ambientais", False),
                        ("Programas preventivos", False),
                    ],
                },
                {
                    "enunciado": "Campanhas de saúde e consultoria para RH e gestores ficam em qual frente, a que vai além da obrigação legal?",
                    "alternativas": [
                        ("Segurança do Trabalho", False),
                        ("Gestão e Compliance", False),
                        ("Saúde e Bem-estar", True),
                        ("Medicina Ocupacional", False),
                    ],
                },
                {
                    "enunciado": "Por que é importante saber a qual frente pertence cada pedido do cliente?",
                    "alternativas": [
                        ("Para encaminhar o cliente a outro fornecedor em cada frente", False),
                        ("Para cobrar uma taxa separada por frente contratada", False),
                        ("Para saber qual frente pode ser deixada de fora", False),
                        ("Para montar uma proposta completa em vez de vender só o exame pedido", True),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0113"),
            "titulo": "Por que os clientes escolhem a Controller",
            "resumo": "Os cinco diferenciais e o custo de não ter uma gestão especializada.",
            "duracao_min": 8,
            "conteudo_md": """\
## Os cinco diferenciais

- **Atendimento nacional.** A empresa do cliente conta com um único parceiro para todas as unidades, com padronização, agilidade e suporte em qualquer região do país.
- **Gestão inteligente com o SOC.** Usamos um dos sistemas mais completos do mercado para gerenciar a saúde ocupacional, com controle, rastreabilidade e acesso rápido às informações.
- **Integração com o eSocial.** Gerenciamos os eventos obrigatórios do eSocial com segurança, reduzindo o risco de inconsistências, atrasos e penalidades.
- **Informações em tempo real.** Documentos, exames, vencimentos e indicadores organizados para facilitar a decisão do cliente.
- **Atendimento consultivo.** Mais do que executar exames, acompanhamos a empresa para garantir conformidade, eficiência e tranquilidade.

## O custo de não ter uma gestão especializada

Sem gestão especializada, o cliente convive com:

- documentos vencidos;
- risco de autuações;
- retrabalho constante;
- processos descentralizados;
- dificuldade com o eSocial;
- falta de previsibilidade.

Com a Controller, ele ganha:

- segurança jurídica;
- gestão integrada;
- atendimento nacional;
- eSocial descomplicado;
- informações em tempo real;
- mais produtividade para o RH.

> Na conversa com o cliente: não leia a lista. Pergunte qual dos seis problemas ele já viveu. "Já aconteceu de um ASO vencer sem ninguém perceber?" Quem já passou por isso vende a solução para você.

## Diferencial não é promessa

Fale só do que entregamos. Se o cliente pedir algo fora do portfólio ou um prazo que você não conhece, a resposta certa é "vou confirmar com a equipe técnica e te retorno até amanhã", e a tarefa de retorno vai para o HIPO.
""",
            "quiz": [
                {
                    "enunciado": "Qual sistema a Controller usa para gerenciar a saúde ocupacional dos clientes?",
                    "alternativas": [
                        ("SOC", True),
                        ("HIPO", False),
                        ("Planilha compartilhada", False),
                        ("eSocial", False),
                    ],
                },
                {
                    "enunciado": "Para uma empresa com unidades em vários estados, qual diferencial pesa mais?",
                    "alternativas": [
                        ("Campanhas de saúde", False),
                        ("Atendimento nacional com um único parceiro", True),
                        ("Endereço em Guarulhos", False),
                        ("Atendimento por e-mail", False),
                    ],
                },
                {
                    "enunciado": "O cliente pede um prazo que você não sabe se a operação cumpre. O que fazer?",
                    "alternativas": [
                        ("Prometer o prazo para não perder a venda", False),
                        ("Dizer que vai confirmar com a equipe técnica e registrar a tarefa de retorno no HIPO", True),
                        ("Mudar de assunto", False),
                        ("Dar um desconto no lugar do prazo", False),
                    ],
                },
                {
                    "enunciado": "Como a aula orienta usar a lista de problemas de quem não tem gestão especializada?",
                    "alternativas": [
                        ("Perguntar ao cliente qual desses problemas ele já viveu", True),
                        ("Ler a lista inteira para o cliente no início da reunião", False),
                        ("Enviar a lista por e-mail antes da reunião", False),
                        ("Não mencionar problemas, só os benefícios", False),
                    ],
                },
                {
                    "enunciado": "O diferencial \"Integração com o eSocial\" reduz principalmente quais riscos para o cliente?",
                    "alternativas": [
                        ("Acidentes de trabalho e afastamentos", False),
                        ("Inconsistências, atrasos e penalidades", True),
                        ("Rotatividade e faltas dos empregados", False),
                        ("Custos de exames complementares", False),
                    ],
                },
                {
                    "enunciado": "O que caracteriza o \"atendimento consultivo\" da Controller?",
                    "alternativas": [
                        ("Executar os exames pedidos sem interferir na gestão do cliente", False),
                        ("Cobrar por hora cada consulta feita pela equipe técnica", False),
                        ("Acompanhar a empresa para garantir conformidade, eficiência e tranquilidade", True),
                        ("Atender o cliente apenas quando ele abre um chamado", False),
                    ],
                },
                {
                    "enunciado": "Qual destes é um dos ganhos que o cliente tem com a Controller, segundo a aula?",
                    "alternativas": [
                        ("Dispensa da fiscalização do trabalho", False),
                        ("Isenção de enviar eventos ao eSocial", False),
                        ("Redução dos impostos sobre a folha", False),
                        ("Mais produtividade para o RH", True),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0114"),
            "titulo": "Como você trabalha aqui",
            "resumo": "O HIPO como fonte única da verdade, a próxima tarefa e os três pilares da Universidade.",
            "duracao_min": 6,
            "conteudo_md": """\
## O HIPO é o nosso sistema

Tudo o que acontece na operação comercial é lançado no **HIPO**, por quem fez: conta, contato, oportunidade, tarefa, reunião, desfecho, proposta. O que não está no HIPO, para a empresa, não aconteceu.

- **Uma tela por função.** Cada cargo enxerga o que precisa para trabalhar.
- **Próxima tarefa.** Toda oportunidade viva tem sempre um próximo passo aberto. Ao fechar a última tarefa de uma oportunidade, o HIPO pede a próxima.
- **Desfecho da reunião no mesmo dia.** Realizada, no-show ou desmarcada: é esse registro que alimenta o Monitor da TV e o relatório do dia seguinte.

## A Universidade e os três pilares

Você vai ser acompanhado(a) em três pilares:

- **Técnica**: o que você precisa saber (esta trilha, os conceitos de SST, o produto e as normas).
- **Método**: os processos que precisam ser seguidos (roteiro de vendas, registro no HIPO).
- **Energia**: o esforço necessário para bater as metas.

As trilhas obrigatórias do seu cargo formam o **Manual da função**, com prazo. A Universidade fica no menu **Carreira** e sempre abre na sua **próxima aula**; ao lado ficam o seu **PDI** e o seu **Desempenho** contra a meta.

## Seus próximos passos

1. Conclua esta trilha (prazo de 10 dias).
2. Siga para **02 · Conceitos gerais de SST**.
3. Depois, **03 · Produto e normas**.
""",
            "quiz": [
                {
                    "enunciado": "Um atendimento ao cliente não foi registrado no HIPO. Para a empresa:",
                    "alternativas": [
                        ("Não tem problema, desde que o cliente lembre", False),
                        ("É como se não tivesse acontecido", True),
                        ("Conta igual, se estiver no WhatsApp", False),
                        ("Só importa no fim do mês", False),
                    ],
                },
                {
                    "enunciado": "Quais são os três pilares da Universidade Corporativa?",
                    "alternativas": [
                        ("Produto, Preço e Praça", False),
                        ("Técnica, Método e Energia", True),
                        ("Prospecção, Venda e Pós-venda", False),
                        ("Saúde, Segurança e Bem-estar", False),
                    ],
                },
                {
                    "enunciado": "Quando o HIPO pede a próxima tarefa de uma oportunidade?",
                    "alternativas": [
                        ("Toda vez que você conclui qualquer tarefa", False),
                        ("Quando você fecha a última tarefa aberta de uma oportunidade viva", True),
                        ("Só quando a oportunidade é ganha", False),
                        ("Nunca, é opcional", False),
                    ],
                },
                {
                    "enunciado": "Você acabou de sair de uma reunião em que o cliente não apareceu. O que fazer?",
                    "alternativas": [
                        ("Registrar o desfecho no-show no HIPO no mesmo dia", True),
                        ("Esperar o fim da semana para registrar todos os desfechos", False),
                        ("Apagar a reunião do HIPO, já que ela não aconteceu", False),
                        ("Avisar o gestor no WhatsApp e não registrar nada", False),
                    ],
                },
                {
                    "enunciado": "Qual é o prazo para concluir a trilha 01 · Boas-vindas à Controller?",
                    "alternativas": [
                        ("30 dias", False),
                        ("10 dias", True),
                        ("5 dias", False),
                        ("60 dias", False),
                    ],
                },
                {
                    "enunciado": "Em qual menu fica a Universidade e onde ela abre?",
                    "alternativas": [
                        ("No menu Clientes, abrindo na lista de todas as trilhas", False),
                        ("No menu Agenda, abrindo no calendário de aulas", False),
                        ("No menu Carreira, sempre abrindo na sua próxima aula", True),
                        ("No menu Carreira, abrindo sempre na primeira aula", False),
                    ],
                },
                {
                    "enunciado": "Seguir o roteiro de vendas e registrar tudo no HIPO faz parte de qual pilar da Universidade?",
                    "alternativas": [
                        ("Técnica", False),
                        ("Energia", False),
                        ("Produto", False),
                        ("Método", True),
                    ],
                },
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# TRILHA 02 — Conceitos gerais de SST
# ═════════════════════════════════════════════════════════════════════
# O vocabulário do mercado. Só o que vale para qualquer cliente e que está
# nas normas; números de prazo ficam onde a norma os fixa sem margem.

TRILHA_02 = {
    "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0200"),
    "titulo": "02 · Conceitos gerais de SST",
    "pilar": "tecnica",
    "descricao": (
        "O vocabulário de Segurança e Saúde no Trabalho que o cliente usa: NRs, "
        "quem faz o quê, os programas e laudos, os exames ocupacionais e o eSocial."
    ),
    "prazo_dias": 20,
    "aulas": [
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0211"),
            "titulo": "SST, NRs e quem faz o quê",
            "resumo": "O que são as Normas Regulamentadoras, medicina × segurança do trabalho e os profissionais envolvidos.",
            "duracao_min": 8,
            "conteudo_md": """\
## Segurança e Saúde no Trabalho (SST)

**SST** é o conjunto de medidas que uma empresa adota para que o trabalho não machuque nem adoeça quem o faz. Ela tem duas metades que andam juntas:

- **Segurança do Trabalho**: olha para o **ambiente e a atividade**. Identifica perigos, avalia riscos e define como controlá-los (máquina protegida, ventilação, procedimento, EPI).
- **Medicina do Trabalho**: olha para a **pessoa**. Acompanha a saúde do trabalhador com exames, para detectar cedo qualquer efeito do trabalho sobre ele.

## As Normas Regulamentadoras

As **NRs** são as regras de SST do Ministério do Trabalho e Emprego. Nasceram com a **Portaria nº 3.214, de 1978**, e são atualizadas desde então. Valem para toda organização com empregados **CLT**. Algumas que você vai ouvir sempre:

- **NR-01**: disposições gerais e gerenciamento de riscos (o PGR).
- **NR-04**: SESMT, a equipe própria de SST das empresas maiores.
- **NR-05**: CIPA, a comissão interna de prevenção de acidentes e de assédio.
- **NR-06**: EPI, o equipamento de proteção individual.
- **NR-07**: PCMSO, o programa de exames médicos.
- **NR-09**: avaliação das exposições a agentes físicos, químicos e biológicos.
- **NR-15 e NR-16**: atividades insalubres e perigosas (os adicionais).
- **NR-17**: ergonomia.

As NR-01 e NR-04 têm aula própria na trilha 03.

## Quem faz o quê

- **Médico do trabalho**: coordena o PCMSO, faz os exames clínicos ocupacionais e emite o ASO.
- **Engenheiro de segurança do trabalho**: elabora laudos (como o LTCAT e os de insalubridade e periculosidade) e responde tecnicamente pelos programas de segurança.
- **Técnico de segurança do trabalho**: vai a campo, inspeciona, treina, acompanha as medidas de prevenção.
- **Enfermeiro e técnico de enfermagem do trabalho**: apoiam o médico na rotina de saúde ocupacional.

Empresa pequena não tem essa equipe dentro de casa. É por isso que ela contrata a Controller.

## Grau de risco

Toda atividade econômica (o **CNAE** do CNPJ) tem um **grau de risco de 1 a 4**, definido na NR-04. Quanto maior, mais perigosa a atividade, e mais obrigações a empresa tem. O HIPO mostra o grau de risco na conta do cliente.
""",
            "quiz": [
                {
                    "enunciado": "Qual a diferença entre Segurança e Medicina do Trabalho?",
                    "alternativas": [
                        ("Não há diferença", False),
                        ("Segurança olha o ambiente e a atividade; Medicina olha a saúde da pessoa", True),
                        ("Segurança é para indústria; Medicina é para escritório", False),
                        ("Medicina cuida dos EPIs", False),
                    ],
                },
                {
                    "enunciado": "Quem emite o ASO?",
                    "alternativas": [
                        ("O técnico de segurança", False),
                        ("O médico que fez o exame clínico ocupacional", True),
                        ("O RH da empresa", False),
                        ("O engenheiro de segurança", False),
                    ],
                },
                {
                    "enunciado": "De onde vem o grau de risco de uma empresa?",
                    "alternativas": [
                        ("Do número de acidentes do ano anterior", False),
                        ("Do CNAE da atividade, conforme a tabela da NR-04", True),
                        ("Da escolha do próprio empresário", False),
                        ("Do porte da empresa", False),
                    ],
                },
                {
                    "enunciado": "O cliente fala da comissão interna de prevenção de acidentes e de assédio. Qual NR trata dela?",
                    "alternativas": [
                        ("NR-05", True),
                        ("NR-04", False),
                        ("NR-06", False),
                        ("NR-17", False),
                    ],
                },
                {
                    "enunciado": "Para quais organizações valem as NRs?",
                    "alternativas": [
                        ("Só para indústrias e construção civil", False),
                        ("Para toda organização com empregados CLT", True),
                        ("Só para empresas com mais de 50 empregados", False),
                        ("Só para empresas de grau de risco 3 e 4", False),
                    ],
                },
                {
                    "enunciado": "Quem, na equipe de SST, elabora laudos como o LTCAT e os de insalubridade e periculosidade?",
                    "alternativas": [
                        ("O técnico de enfermagem do trabalho", False),
                        ("O médico que emite o ASO", False),
                        ("O engenheiro de segurança do trabalho", True),
                        ("O RH da empresa cliente", False),
                    ],
                },
                {
                    "enunciado": "Uma empresa tem grau de risco 4 e outra tem grau de risco 1. O que isso indica?",
                    "alternativas": [
                        ("A de grau 4 tem mais empregados que a de grau 1", False),
                        ("A de grau 1 teve mais acidentes no ano anterior", False),
                        ("As duas têm as mesmas obrigações de SST", False),
                        ("A de grau 4 tem atividade mais perigosa e mais obrigações", True),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0212"),
            "titulo": "Programas e laudos: PGR, PCMSO, LTCAT e cia.",
            "resumo": "O que é cada documento, qual norma pede e como eles se conectam.",
            "duracao_min": 10,
            "conteudo_md": """\
## A ordem lógica

Os documentos de SST não são uma pilha solta. Eles seguem uma ordem: **primeiro se conhece o risco, depois se cuida da saúde de quem está exposto a ele**.

1. **PGR** levanta e avalia os riscos.
2. **PCMSO** usa esses riscos para decidir quais exames cada função faz.
3. **ASO** é o resultado de cada exame.
4. **LTCAT** e laudos registram as exposições para fins previdenciários e trabalhistas.

## PGR (Programa de Gerenciamento de Riscos)

Exigido pela **NR-01**. É o documento do gerenciamento de riscos: **inventário de riscos** e **plano de ação**. Cobre riscos físicos, químicos, biológicos, de acidentes e ergonômicos, incluindo os psicossociais. Substituiu o antigo PPRA.

## PCMSO (Programa de Controle Médico de Saúde Ocupacional)

Exigido pela **NR-07**. Define, a partir dos riscos do PGR, **quais exames cada função faz e com que frequência**. Tem um médico responsável.

## ASO (Atestado de Saúde Ocupacional)

O documento emitido a cada exame ocupacional, dizendo se o trabalhador está **apto ou inapto** para a função. É o que o RH arquiva e informa no eSocial.

## LTCAT (Laudo Técnico das Condições Ambientais do Trabalho)

Laudo **previdenciário**: registra a exposição a agentes nocivos para fins de **aposentadoria especial** junto ao INSS. É elaborado por médico do trabalho ou engenheiro de segurança.

## Laudos de insalubridade e periculosidade

Caracterizam se a atividade dá direito a **adicional de insalubridade** (NR-15) ou de **periculosidade** (NR-16). São os laudos que o cliente pede quando há pedido de adicional ou processo trabalhista.

## Análise ergonômica

Avalia a adequação do trabalho às pessoas, nos termos da **NR-17**: mobiliário, postura, ritmo, organização do trabalho.

> Na conversa com o cliente: quando ele disser "eu só preciso do PCMSO", lembre a ordem lógica. O PCMSO depende dos riscos do PGR. Sem PGR atualizado, o PCMSO está montado em cima de nada.
""",
            "quiz": [
                {
                    "enunciado": "Qual documento define quais exames cada função faz?",
                    "alternativas": [
                        ("PGR", False),
                        ("PCMSO", True),
                        ("LTCAT", False),
                        ("ASO", False),
                    ],
                },
                {
                    "enunciado": "Para que serve o LTCAT?",
                    "alternativas": [
                        ("Para definir o valor do plano de saúde", False),
                        ("Para registrar exposição a agentes nocivos para fins de aposentadoria especial", True),
                        ("Para substituir o PGR", False),
                        ("Para atestar que o trabalhador está apto", False),
                    ],
                },
                {
                    "enunciado": "Por que o PCMSO depende do PGR?",
                    "alternativas": [
                        ("Porque são o mesmo documento", False),
                        ("Porque os exames são definidos a partir dos riscos que o PGR levanta", True),
                        ("Porque o PGR é feito pelo médico", False),
                        ("Não depende", False),
                    ],
                },
                {
                    "enunciado": "Qual programa substituiu o antigo PPRA?",
                    "alternativas": [
                        ("PGR", True),
                        ("PCMSO", False),
                        ("LTCAT", False),
                        ("ASO", False),
                    ],
                },
                {
                    "enunciado": "O que o ASO diz sobre o trabalhador?",
                    "alternativas": [
                        ("A que agentes nocivos ele está exposto", False),
                        ("Se ele está apto ou inapto para a função", True),
                        ("Quais riscos existem no setor dele", False),
                        ("Se ele tem direito a aposentadoria especial", False),
                    ],
                },
                {
                    "enunciado": "Um ex-empregado abriu processo pedindo adicional de periculosidade. Qual laudo o cliente precisa e qual NR o baseia?",
                    "alternativas": [
                        ("Laudo de insalubridade, com base na NR-17", False),
                        ("LTCAT, com base na NR-07", False),
                        ("Laudo de periculosidade, com base na NR-16", True),
                        ("Análise ergonômica, com base na NR-15", False),
                    ],
                },
                {
                    "enunciado": "O que a análise ergonômica avalia, nos termos da NR-17?",
                    "alternativas": [
                        ("Ruído, poeira e agentes químicos do ambiente", False),
                        ("Exames clínicos e complementares de cada função", False),
                        ("Exposição a agentes nocivos para o INSS", False),
                        ("Mobiliário, postura, ritmo e organização do trabalho", True),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0213"),
            "titulo": "Os exames ocupacionais",
            "resumo": "Admissional, periódico, retorno ao trabalho, mudança de risco, demissional e complementares.",
            "duracao_min": 8,
            "conteudo_md": """\
## Um exame para cada momento da vida do trabalhador

Os exames ocupacionais são previstos na **NR-07** e organizados no PCMSO da empresa. Cada um gera um **ASO**.

- **Admissional**: feito **antes** de o trabalhador começar a trabalhar. Confirma que ele está apto para a função.
- **Periódico**: repetido ao longo do contrato. A **frequência é definida no PCMSO** pelo médico responsável, conforme os riscos da função.
- **Retorno ao trabalho**: feito antes de o trabalhador voltar de um afastamento por doença ou acidente, de natureza ocupacional ou não, de **30 dias ou mais**.
- **Mudança de risco**: feito **antes** de o trabalhador mudar para uma função ou setor com riscos diferentes.
- **Demissional**: feito no desligamento. A NR-07 permite dispensá-lo quando o último exame clínico ocupacional é recente, dentro de um prazo que depende do grau de risco da empresa.

## Exames complementares

Além da consulta clínica, o PCMSO pode exigir exames conforme o risco da função: **audiometria** para quem trabalha com ruído, **espirometria** para poeiras, **exames laboratoriais** para agentes químicos, **acuidade visual**, entre outros. É aqui que o ticket de um contrato cresce, e é o médico do PCMSO, não o vendedor, quem define o que cada função faz.

> Na conversa com o cliente: "Vocês fazem o periódico de todo mundo no mesmo mês ou cada um no seu aniversário de admissão?" A resposta mostra o grau de organização dele e abre espaço para a gestão de vencimentos.

## O que o cliente precisa entender

- Trabalhador sem admissional não deveria começar a trabalhar.
- ASO vencido é exposição da empresa em fiscalização e em processo.
- Todo ASO vira informação no **eSocial** (próxima aula).
""",
            "quiz": [
                {
                    "enunciado": "Quando o exame de retorno ao trabalho é obrigatório?",
                    "alternativas": [
                        ("Depois de qualquer férias", False),
                        ("Antes da volta de afastamento por doença ou acidente de 30 dias ou mais", True),
                        ("Só depois de acidente de trabalho", False),
                        ("A cada 6 meses", False),
                    ],
                },
                {
                    "enunciado": "Quem define a frequência do exame periódico?",
                    "alternativas": [
                        ("O vendedor, na proposta", False),
                        ("O médico responsável, no PCMSO, conforme os riscos da função", True),
                        ("O próprio trabalhador", False),
                        ("O sindicato", False),
                    ],
                },
                {
                    "enunciado": "O exame de mudança de risco deve ser feito:",
                    "alternativas": [
                        ("Antes da mudança de função ou setor com riscos diferentes", True),
                        ("Um ano depois da mudança", False),
                        ("Só se o trabalhador pedir", False),
                        ("Junto com o demissional", False),
                    ],
                },
                {
                    "enunciado": "Em que situação a NR-07 permite dispensar o exame demissional?",
                    "alternativas": [
                        ("Quando o último exame clínico ocupacional é recente, num prazo que depende do grau de risco", True),
                        ("Quando o trabalhador pede demissão por vontade própria", False),
                        ("Quando a empresa é ME ou EPP de qualquer grau de risco", False),
                        ("Quando o trabalhador ficou menos de um ano na empresa", False),
                    ],
                },
                {
                    "enunciado": "Um trabalhador atua exposto a ruído. Qual exame complementar a aula cita para esse caso?",
                    "alternativas": [
                        ("Espirometria", False),
                        ("Audiometria", True),
                        ("Acuidade visual", False),
                        ("Exame laboratorial", False),
                    ],
                },
                {
                    "enunciado": "Quem define quais exames complementares cada função faz?",
                    "alternativas": [
                        ("O vendedor, conforme o pacote fechado", False),
                        ("O RH do cliente, conforme o orçamento", False),
                        ("O médico do PCMSO", True),
                        ("O próprio trabalhador, no exame clínico", False),
                    ],
                },
                {
                    "enunciado": "O cliente quer que um novo empregado comece a trabalhar hoje e faça o admissional na semana que vem. O que a aula diz?",
                    "alternativas": [
                        ("Pode, desde que seja feito em até 30 dias", False),
                        ("Pode, porque o admissional é opcional", False),
                        ("Pode, se ele já tiver ASO de outra empresa", False),
                        ("O admissional deve ser feito antes de ele começar a trabalhar", True),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0214"),
            "titulo": "eSocial: os eventos de SST",
            "resumo": "S-2210, S-2220 e S-2240: o que cada evento informa e por que o cliente precisa de ajuda.",
            "duracao_min": 7,
            "conteudo_md": """\
## O que é o eSocial

O **eSocial** é o sistema do governo em que o empregador informa, de forma digital, as obrigações trabalhistas, previdenciárias e fiscais. A parte de SST tem três eventos que todo cliente com empregado CLT precisa enviar.

## Os três eventos de SST

- **S-2210 · Comunicação de Acidente de Trabalho (CAT).** Informa acidentes de trabalho e doenças ocupacionais.
- **S-2220 · Monitoramento da Saúde do Trabalhador.** Informa os exames ocupacionais e os ASOs. Sai do PCMSO.
- **S-2240 · Condições Ambientais do Trabalho · Agentes Nocivos.** Informa a que agentes nocivos cada trabalhador está exposto. Sai do PGR e do LTCAT.

Esses eventos substituíram o PPP em papel: o histórico de exposição do trabalhador agora é montado a partir do que a empresa envia.

## Por que isso vende

- Evento enviado com atraso ou com informação errada gera **inconsistência e risco de penalidade**.
- O S-2240 só fica certo se o **PGR e o LTCAT** estiverem certos. O S-2220 só fica certo se o **PCMSO** estiver certo. Quem resolve um resolve os outros.
- O RH do cliente raramente domina os códigos e as regras desses eventos. É aqui que entra a **gestão do eSocial** da Controller, integrada ao SOC.

> Na conversa com o cliente: "Quem envia hoje os eventos de SST de vocês no eSocial? Já tiveram algum evento rejeitado?" Se a resposta for "o contador manda" ou "não sei", você encontrou um problema.
""",
            "quiz": [
                {
                    "enunciado": "Qual evento do eSocial informa os exames ocupacionais e os ASOs?",
                    "alternativas": [
                        ("S-2210", False),
                        ("S-2220", True),
                        ("S-2240", False),
                        ("S-1200", False),
                    ],
                },
                {
                    "enunciado": "O S-2240 (agentes nocivos) depende principalmente de quais documentos?",
                    "alternativas": [
                        ("Folha de pagamento", False),
                        ("PGR e LTCAT", True),
                        ("Contrato social", False),
                        ("ASO admissional", False),
                    ],
                },
                {
                    "enunciado": "O S-2210 informa:",
                    "alternativas": [
                        ("Férias", False),
                        ("Acidentes de trabalho e doenças ocupacionais (CAT)", True),
                        ("Admissões", False),
                        ("Treinamentos de NR", False),
                    ],
                },
                {
                    "enunciado": "Os eventos de SST do eSocial substituíram qual documento em papel?",
                    "alternativas": [
                        ("O PPP", True),
                        ("O PGR", False),
                        ("O ASO", False),
                        ("O PCMSO", False),
                    ],
                },
                {
                    "enunciado": "Você pergunta quem envia os eventos de SST e o cliente responde \"o contador manda\". O que isso indica?",
                    "alternativas": [
                        ("Que o cliente já está resolvido e não precisa de nada", False),
                        ("Que você encontrou um problema e uma oportunidade para a gestão do eSocial", True),
                        ("Que esses eventos não são obrigatórios para ele", False),
                        ("Que a conversa deve ser feita só com o contador", False),
                    ],
                },
                {
                    "enunciado": "Se o PCMSO do cliente estiver errado, qual evento do eSocial tende a sair errado também?",
                    "alternativas": [
                        ("S-2210", False),
                        ("S-2240", False),
                        ("S-2220", True),
                        ("S-1200", False),
                    ],
                },
                {
                    "enunciado": "Quem precisa enviar os eventos de SST do eSocial?",
                    "alternativas": [
                        ("Só empresas com SESMT próprio", False),
                        ("Só empresas de grau de risco 3 e 4", False),
                        ("Só empresas que já tiveram acidente", False),
                        ("Todo cliente com empregado CLT", True),
                    ],
                },
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════════
# TRILHA 03 — Produto e normas
# ═════════════════════════════════════════════════════════════════════
# Aula 1: o portfólio ligado às normas. Aulas 2 a 7: NR-01 e NR-04, as
# mesmas da trilha carregada na entrega 029 (mesmos ids).

AULA_PRODUTO = {
    "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0300"),
    "titulo": "O produto: de cada serviço à norma que o exige",
    "resumo": "Para cada serviço do portfólio, a norma por trás, quem precisa e o sinal de oportunidade na conversa.",
    "duracao_min": 10,
    "conteudo_md": """\
## Por que ligar produto e norma

O cliente não compra PGR porque gosta de documento. Compra porque **uma norma exige** e porque **o problema de não ter** custa caro. Quem sabe qual norma está por trás de cada serviço vende com o argumento certo e não promete o que a norma não pede.

## Medicina Ocupacional

- **Exames admissional, periódico, retorno, mudança de risco e demissional.** Norma: **NR-07**. Quem precisa: toda empresa com empregado CLT, inclusive as dispensadas de PCMSO (a dispensa não tira o ASO). Sinal de oportunidade: "estamos contratando", "vou desligar gente", "tenho funcionário voltando de afastamento".
- **Exames complementares.** Norma: **NR-07**, conforme o PCMSO. Quem precisa: funções expostas a ruído, poeira, químicos, altura, direção. Sinal: o cliente tem operação (fábrica, cozinha, oficina, obra, frota).

## Segurança do Trabalho

- **PGR.** Norma: **NR-01**. Quem precisa: toda organização com empregado CLT, salvo as dispensas estreitas do item 1.8. Sinal: PGR com mais de 2 anos, ou sem revisão depois de 26/05/2026 (riscos psicossociais).
- **PCMSO.** Norma: **NR-07**. Quem precisa: quem tem empregado CLT, salvo a dispensa de ME/EPP grau 1 e 2 sem exposição. Sinal: "quem é o médico responsável pelo PCMSO de vocês?" sem resposta clara.
- **LTCAT.** Base: legislação **previdenciária** (aposentadoria especial). Quem precisa: empresas com exposição a agentes nocivos. Sinal: atividade com ruído, químicos, calor; pedido de PPP.
- **Laudos de insalubridade e periculosidade.** Normas: **NR-15** e **NR-16**. Sinal: pedido de adicional, reclamação trabalhista, sindicato cobrando.
- **Análise ergonômica.** Norma: **NR-17**. Sinal: queixas de dor, afastamentos por LER/DORT, call center, linha de produção, e agora os fatores psicossociais do PGR.
- **NRs diversas.** Treinamentos e adequações específicas (por exemplo, trabalho em altura, máquinas, eletricidade). Sinal: a atividade do cliente tem um risco que tem NR própria.

## Gestão e Compliance

- **Gestão do eSocial.** Eventos **S-2210, S-2220 e S-2240**. Sinal: "o contador manda", evento rejeitado, ninguém sabe quem envia.
- **Auditorias, diagnósticos e gestão de documentação.** Sinal: fiscalização à vista, documentos espalhados, troca de fornecedor.
- **Indicadores e relatórios.** Sinal: cliente com várias unidades que não enxerga o todo.

## Saúde e Bem-estar

- **Campanhas, programas preventivos, atendimento ocupacional, consultoria para RH.** Não são exigência de norma: são valor a mais. Sinal: RH estruturado que já cumpre o básico e quer reduzir afastamentos.

> Na conversa com o cliente: cada sinal acima é uma pergunta de **Problema** do roteiro. Anote no HIPO o que o cliente respondeu: a proposta nasce dessas respostas, não da tabela de preços.

## O que vem a seguir nesta trilha

As próximas aulas aprofundam as duas normas que sustentam quase toda venda: **NR-01** (gerenciamento de riscos, PGR, treinamentos, pequenas empresas) e **NR-04** (SESMT). Os textos oficiais estão anexados como material de apoio.
""",
    "quiz": [
        {
            "enunciado": "Qual norma exige os exames ocupacionais (admissional, periódico, demissional)?",
            "alternativas": [
                ("NR-01", False),
                ("NR-07", True),
                ("NR-15", False),
                ("NR-04", False),
            ],
        },
        {
            "enunciado": "O cliente diz que o funcionário entrou com pedido de adicional de insalubridade. Qual serviço resolve?",
            "alternativas": [
                ("Campanha de saúde", False),
                ("Laudo de insalubridade (NR-15)", True),
                ("Exame admissional", False),
                ("Gestão de documentação", False),
            ],
        },
        {
            "enunciado": "Campanhas de saúde e programas preventivos são:",
            "alternativas": [
                ("Exigidos pela NR-01", False),
                ("Valor a mais, não exigência de norma", True),
                ("Exigidos pela NR-04 para todas as empresas", False),
                ("Obrigatórios no eSocial", False),
            ],
        },
        {
            "enunciado": "O cliente comenta: \"estamos contratando bastante este mês\". Qual serviço esse sinal indica?",
            "alternativas": [
                ("Exames admissionais, exigidos pela NR-07", True),
                ("Laudo de periculosidade, exigido pela NR-16", False),
                ("Análise ergonômica, exigida pela NR-17", False),
                ("Campanha de saúde, exigida pela NR-01", False),
            ],
        },
        {
            "enunciado": "Qual é a base legal do LTCAT, segundo a aula?",
            "alternativas": [
                ("A NR-04, ligada ao dimensionamento do SESMT", False),
                ("A legislação previdenciária, ligada à aposentadoria especial", True),
                ("A NR-07, ligada aos exames periódicos", False),
                ("A NR-17, ligada à ergonomia", False),
            ],
        },
        {
            "enunciado": "Qual destes é sinal de oportunidade para revisar o PGR do cliente?",
            "alternativas": [
                ("PGR feito no mesmo ano do PCMSO", False),
                ("Empresa com menos de 10 empregados", False),
                ("PGR com mais de 2 anos ou sem revisão depois de 26/05/2026", True),
                ("Empresa que já envia o S-2220 em dia", False),
            ],
        },
        {
            "enunciado": "Segundo a aula, de onde nasce a proposta para o cliente?",
            "alternativas": [
                ("Da tabela de preços, aplicada ao número de empregados", False),
                ("Do pacote mais vendido no mês anterior", False),
                ("Da lista completa de serviços do portfólio", False),
                ("Das respostas do cliente às perguntas de Problema, anotadas no HIPO", True),
            ],
        },
    ],
}


_AULAS_NR: list[dict] = [
    # ── 1 ────────────────────────────────────────────────────────────
    {
        "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0201"),
        "titulo": "NR-01: a base de todas as normas",
        "resumo": "Para que serve a NR-01, a quem se aplica e o que ela cobra do empregador e do trabalhador.",
        "duracao_min": 12,
        "pdf": "nr01",
        "conteudo_md": """\
## Por que começar pela NR-01

A NR-01 é a porta de entrada das Normas Regulamentadoras. Ela define o campo de aplicação, os termos usados por todas as outras NR e as regras do **gerenciamento de riscos ocupacionais**, que é o coração do que a MedSeg entrega.

## A quem se aplica

- A toda organização que tenha empregados regidos pela **CLT**: empresa privada, órgão público da administração direta e indireta, Legislativo, Judiciário e Ministério Público.
- Cumprir as NR **não dispensa** o que vier de código de obras, regulamento sanitário de estado ou município e de convenção ou acordo coletivo.

## O que cabe ao empregador (item 1.4.1)

- Cumprir e fazer cumprir as normas de segurança e saúde no trabalho.
- Informar aos trabalhadores os riscos do local de trabalho, as medidas de prevenção, os resultados dos **exames médicos** a que foram submetidos e os resultados das avaliações ambientais.
- Emitir **ordens de serviço** de segurança e saúde e dar ciência delas.
- Definir o que fazer em caso de acidente ou doença relacionada ao trabalho, incluindo a análise das causas.
- Implementar medidas de prevenção, ouvidos os trabalhadores, **nesta ordem de prioridade**:

1. eliminar o fator de risco;
2. minimizar e controlar com **proteção coletiva**;
3. minimizar e controlar com medidas **administrativas ou de organização do trabalho**;
4. adotar **proteção individual** (EPI).

> Na conversa com o cliente: EPI é o último recurso, não o primeiro. Empresa que "resolve tudo com EPI" está pulando três degraus da própria NR-01.

## Assédio e violência (empresas com CIPA)

Quem é obrigado a ter CIPA pela NR-05 precisa ter regras de conduta sobre assédio sexual e outras violências, um canal de denúncia com anonimato garantido e ações de capacitação **pelo menos a cada 12 meses** para todos os níveis da empresa.

## O que cabe ao trabalhador (item 1.4.2)

- Cumprir as normas e as ordens de serviço.
- **Submeter-se aos exames médicos** previstos nas NR.
- Colaborar com a aplicação das NR e usar o EPI fornecido.

Recusar isso sem justificativa é **ato faltoso**.

## Direito de interromper o trabalho (item 1.4.3)

O trabalhador pode interromper a atividade quando, por motivos razoáveis, enxergar **risco grave e iminente** para a vida ou a saúde, avisando o superior na hora. O empregador não pode exigir a volta enquanto a situação não for corrigida, e o trabalhador deve ser protegido de consequências injustificadas por ter parado.

## Informação na admissão e na mudança de função (item 1.4.4)

Ao ser admitido, ou ao mudar para função com risco diferente, o trabalhador deve receber informação sobre os riscos, como preveni-los, as medidas adotadas pela empresa e os procedimentos de emergência. Pode ser em treinamento, diálogo de segurança ou documento físico ou eletrônico.
""",
        "quiz": [
            {
                "enunciado": "Pela NR-01, qual é a PRIMEIRA medida de prevenção que o empregador deve buscar?",
                "alternativas": [
                    ("Fornecer EPI a todos os expostos", False),
                    ("Eliminar o fator de risco", True),
                    ("Adotar medidas administrativas", False),
                    ("Treinar os trabalhadores", False),
                ],
            },
            {
                "enunciado": "Recusar sem justificativa os exames médicos previstos nas NR é, para o trabalhador:",
                "alternativas": [
                    ("Um direito, se ele assinar termo", False),
                    ("Ato faltoso", True),
                    ("Permitido em empresa de grau de risco 1", False),
                    ("Indiferente para a norma", False),
                ],
            },
            {
                "enunciado": "Empresas obrigadas a ter CIPA devem fazer ações de capacitação sobre assédio e violência com qual frequência mínima?",
                "alternativas": [
                    ("A cada 6 meses", False),
                    ("A cada 12 meses", True),
                    ("A cada 2 anos", False),
                    ("Só na admissão", False),
                ],
            },
            {
                "enunciado": "Um órgão público da administração indireta tem empregados CLT. A NR-01 se aplica a ele?",
                "alternativas": [
                    ("Sim, a NR-01 vale para órgãos públicos com empregados CLT", True),
                    ("Não, a NR-01 vale só para empresas privadas", False),
                    ("Só se ele tiver mais de 50 empregados", False),
                    ("Só se ele for obrigado a ter CIPA", False),
                ],
            },
            {
                "enunciado": "Um trabalhador vê risco grave e iminente à sua vida na atividade. O que a NR-01 garante?",
                "alternativas": [
                    ("Ele deve continuar até o fim do turno e depois avisar", False),
                    ("Ele pode interromper a atividade, avisando o superior na hora", True),
                    ("Ele só pode parar com autorização escrita do gestor", False),
                    ("Ele pode parar, mas perde o dia de trabalho", False),
                ],
            },
            {
                "enunciado": "O cliente diz: \"cumprimos as NR, então a convenção coletiva não importa\". O que a NR-01 diz?",
                "alternativas": [
                    ("A convenção coletiva só vale se for mais branda que as NR", False),
                    ("Quem cumpre as NR fica dispensado da convenção coletiva", False),
                    ("Cumprir as NR não dispensa o que vier de convenção ou acordo coletivo", True),
                    ("A convenção coletiva substitui a NR-01 quando existir", False),
                ],
            },
            {
                "enunciado": "Ao ser admitido ou mudar para função com risco diferente, o trabalhador deve receber:",
                "alternativas": [
                    ("Apenas o EPI da nova função, sem outras informações", False),
                    ("Uma cópia do contrato social da empresa", False),
                    ("Somente o resultado do último exame periódico", False),
                    ("Informação sobre os riscos, a prevenção, as medidas adotadas e a emergência", True),
                ],
            },
        ],
    },
    # ── 2 ────────────────────────────────────────────────────────────
    {
        "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0202"),
        "titulo": "NR-01: GRO e PGR, passo a passo",
        "resumo": "O que é o gerenciamento de riscos, o que o PGR precisa conter e quando ele tem de ser revisado.",
        "duracao_min": 15,
        "conteudo_md": """\
## GRO e PGR: a diferença

- **GRO** (Gerenciamento de Riscos Ocupacionais) é o **processo** contínuo de identificar perigos, avaliar e controlar riscos.
- **PGR** (Programa de Gerenciamento de Riscos) é o **documento** desse processo: um conjunto coordenado de ações, formalmente documentado.

Toda organização deve implementar o GRO nos seus estabelecimentos, e ele deve constituir um PGR. O PGR é feito **por estabelecimento** (pode ser por unidade operacional, setor ou atividade) e precisa conversar com os demais programas de SST, como o PCMSO da NR-07.

## Quais riscos entram

Agentes **físicos, químicos e biológicos**, riscos de **acidentes** e riscos ligados a **fatores ergonômicos**, **incluindo os fatores de risco psicossociais** relacionados ao trabalho (item 1.5.3.1.4). Este último ponto tem aula própria nesta trilha.

## As etapas

1. **Levantamento preliminar de perigos e riscos**: antes de abrir o estabelecimento, para as atividades existentes e sempre que mudar processo. Serve para eliminar o que dá para eliminar e agir já no risco evidente.
2. **Identificação de perigos**: descrever o perigo e as possíveis lesões, as fontes ou circunstâncias e o grupo de trabalhadores exposto, incluindo perigos externos previsíveis.
3. **Avaliação de riscos**: o **nível de risco** é a combinação da **severidade** da lesão possível com a **probabilidade** de ocorrer. Os critérios precisam estar escritos.
4. **Classificação**: define se é preciso adotar ou manter medida de prevenção.
5. **Plano de ação**: medidas com **cronograma, responsáveis, forma de acompanhamento e de aferição** de resultado. Quanto mais trabalhadores atingidos, maior a prioridade.

## Documentação mínima (item 1.5.7)

- **Inventário de riscos** e **plano de ação**, datados e assinados.
- Sempre disponíveis para os trabalhadores, o sindicato e a fiscalização.
- O histórico das atualizações do inventário deve ser guardado por no mínimo **20 anos**.

## Quando revisar

A avaliação de riscos é contínua e deve ser **revista a cada 2 anos** (até **3 anos** para quem tem certificação em sistema de gestão de SST) e também:

- depois de implantar medidas de prevenção (risco residual);
- quando mudar tecnologia, ambiente, processo ou organização do trabalho;
- quando as medidas se mostrarem insuficientes;
- quando houver acidente ou doença relacionada ao trabalho;
- **quando mudarem os requisitos legais aplicáveis**;
- a pedido justificado dos trabalhadores ou da CIPA.

> Na conversa com o cliente: "Quando o PGR de vocês foi revisado pela última vez?" é uma pergunta de Situação que abre a de Problema sozinha. Mais de 2 anos, ou nenhuma revisão depois de 26/05/2026, é PGR fora da norma.

## Prestadores de serviço (item 1.5.8)

O PGR da **contratante** inclui as medidas de prevenção para as contratadas que trabalham nas dependências dela, ou usa os programas das contratadas, que então entregam inventário e plano de ação. Contratante e contratada trocam informação sobre os riscos que um causa ao outro.

## Saúde ocupacional

O PGR não anda sozinho: o controle da saúde dos empregados é um processo preventivo, planejado e contínuo, de acordo com a classificação de riscos e **nos termos da NR-07** (PCMSO).
""",
        "quiz": [
            {
                "enunciado": "Qual é a diferença entre GRO e PGR?",
                "alternativas": [
                    ("São a mesma coisa com nomes diferentes", False),
                    ("GRO é o processo; PGR é o programa documentado desse processo", True),
                    ("PGR é só para empresas com SESMT", False),
                    ("GRO substitui o PCMSO", False),
                ],
            },
            {
                "enunciado": "Os documentos mínimos do PGR são:",
                "alternativas": [
                    ("ASO e PCMSO", False),
                    ("Inventário de riscos e plano de ação", True),
                    ("Laudo de insalubridade e LTCAT", False),
                    ("Ordem de serviço e ficha de EPI", False),
                ],
            },
            {
                "enunciado": "Sem certificação em sistema de gestão de SST, a avaliação de riscos deve ser revista no máximo a cada:",
                "alternativas": [
                    ("1 ano", False),
                    ("2 anos", True),
                    ("3 anos", False),
                    ("5 anos", False),
                ],
            },
            {
                "enunciado": "O nível de risco ocupacional é determinado pela combinação de:",
                "alternativas": [
                    ("Número de empregados e grau de risco do CNAE", False),
                    ("Severidade da lesão possível e probabilidade de ocorrer", True),
                    ("Custo da medida e prazo para implantar", False),
                    ("Tempo de exposição e uso de EPI", False),
                ],
            },
            {
                "enunciado": "Por quanto tempo, no mínimo, deve ser guardado o histórico das atualizações do inventário de riscos?",
                "alternativas": [
                    ("20 anos", True),
                    ("5 anos", False),
                    ("2 anos", False),
                    ("10 anos", False),
                ],
            },
            {
                "enunciado": "Uma prestadora de serviço trabalha dentro da fábrica do cliente. Como fica o PGR?",
                "alternativas": [
                    ("A contratada fica fora de qualquer PGR enquanto estiver na fábrica", False),
                    ("O PGR da contratante inclui medidas para a contratada ou usa os programas dela", True),
                    ("Só a contratada faz PGR, e a contratante não troca informação", False),
                    ("A contratante precisa fazer um PGR novo a cada contrato", False),
                ],
            },
            {
                "enunciado": "O que o plano de ação do PGR precisa ter, segundo a aula?",
                "alternativas": [
                    ("Apenas a lista de EPIs entregues a cada trabalhador", False),
                    ("Orçamento aprovado e assinatura do sindicato", False),
                    ("Cronograma, responsáveis, forma de acompanhamento e de aferição", True),
                    ("Somente as medidas para riscos de acidente", False),
                ],
            },
        ],
    },
    # ── 3 ────────────────────────────────────────────────────────────
    {
        "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0203"),
        "titulo": "Riscos psicossociais: o que mudou em 2026",
        "resumo": "A nova redação do item 1.5 está em vigor desde 26/05/2026. O que a norma diz e o que isso significa para o cliente.",
        "duracao_min": 8,
        "conteudo_md": """\
## O que mudou

A redação do item 1.5 da NR-01 dada pela **Portaria MTE nº 1.419/2024** entrou em vigor em **26 de maio de 2026** (prazo definido pela Portaria MTE nº 765/2025). Com ela, o gerenciamento de riscos passa a dizer, com todas as letras, que abrange os riscos relacionados aos fatores ergonômicos, **incluindo os fatores de risco psicossociais relacionados ao trabalho**.

## Onde isso aparece no texto

- **1.5.3.1.4**: o GRO deve abranger os riscos psicossociais.
- **1.5.3.2.1**: a organização deve considerar as condições de trabalho nos termos da **NR-17** (ergonomia), incluindo os fatores psicossociais.
- **1.5.4.4.5.3**: para avaliar a probabilidade nesses riscos, a empresa considera as **exigências da atividade de trabalho** e a **eficácia das medidas** de prevenção.

## O que isso significa para o cliente

- O inventário de riscos precisa tratar os fatores psicossociais. Um PGR que só fala de ruído, poeira e queda está incompleto.
- A própria NR-01 manda revisar a avaliação de riscos **quando mudam os requisitos legais aplicáveis**. A mudança de 26/05/2026 é exatamente isso.
- O fator psicossocial é avaliado pelo **trabalho** (exigências da atividade, organização, condições), não pela vida pessoal do trabalhador.

> Na conversa com o cliente: não venda medo, venda o texto. "A NR-01 mudou em maio, e ela mesma pede revisão do PGR quando a lei muda. O de vocês já trata os fatores psicossociais?" Se a resposta for "não sei", você já tem a pergunta de Implicação: o que acontece se a fiscalização pedir o inventário amanhã?

## Cuidado com o que prometer

A norma diz **o que** gerenciar, não impõe um questionário ou ferramenta específica. Quem define método e instrumentos é o técnico responsável pelo PGR. Não prometa ao cliente "o formulário oficial do governo": ele não existe na NR-01.
""",
        "quiz": [
            {
                "enunciado": "Desde quando está em vigor a redação da NR-01 que inclui expressamente os riscos psicossociais no gerenciamento de riscos?",
                "alternativas": [
                    ("Desde 2020", False),
                    ("26 de maio de 2025", False),
                    ("26 de maio de 2026", True),
                    ("Ainda não está em vigor", False),
                ],
            },
            {
                "enunciado": "Por que a mudança de 2026 é motivo para revisar o PGR do cliente?",
                "alternativas": [
                    ("Porque todo PGR vence em maio", False),
                    ("Porque a NR-01 manda revisar quando mudam os requisitos legais aplicáveis", True),
                    ("Porque o eSocial exige um PGR novo por ano", False),
                    ("Porque o PGR antigo deixou de valer automaticamente", False),
                ],
            },
            {
                "enunciado": "Fatores de risco psicossociais, na NR-01, são avaliados a partir de:",
                "alternativas": [
                    ("Questionário oficial do Ministério do Trabalho", False),
                    ("Exigências da atividade de trabalho e eficácia das medidas de prevenção", True),
                    ("Histórico pessoal e familiar do trabalhador", False),
                    ("Laudo psiquiátrico de cada empregado", False),
                ],
            },
            {
                "enunciado": "O cliente pede \"o formulário oficial do governo\" para avaliar riscos psicossociais. O que responder?",
                "alternativas": [
                    ("Que a Controller envia o formulário oficial junto com o PGR", False),
                    ("Que o formulário oficial é preenchido no eSocial", False),
                    ("Que cada trabalhador baixa o formulário no gov.br", False),
                    ("Esse formulário não existe na NR-01; o método é definido pelo técnico responsável", True),
                ],
            },
            {
                "enunciado": "O PGR do cliente trata só de ruído, poeira e queda. Pela aula, ele está:",
                "alternativas": [
                    ("Incompleto, porque precisa tratar os fatores psicossociais", True),
                    ("Completo, porque cobre os riscos físicos e de acidente", False),
                    ("Completo, se tiver sido feito antes de 2026", False),
                    ("Incompleto, porque precisa de laudo psiquiátrico", False),
                ],
            },
            {
                "enunciado": "Ao considerar as condições de trabalho, incluindo fatores psicossociais, a NR-01 remete a qual norma?",
                "alternativas": [
                    ("NR-05", False),
                    ("NR-17", True),
                    ("NR-07", False),
                    ("NR-15", False),
                ],
            },
            {
                "enunciado": "Como a aula recomenda abordar os riscos psicossociais com o cliente?",
                "alternativas": [
                    ("Destacar o valor das multas logo de início", False),
                    ("Evitar o tema até o cliente perguntar", False),
                    ("Não vender medo, vender o texto da norma", True),
                    ("Prometer o formulário oficial do governo", False),
                ],
            },
        ],
    },
    # ── 4 ────────────────────────────────────────────────────────────
    {
        "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0204"),
        "titulo": "NR-01: treinamentos e capacitação",
        "resumo": "Treinamento inicial, periódico e eventual, o que o certificado precisa ter e as regras do EAD.",
        "duracao_min": 10,
        "conteudo_md": """\
## Três tipos de treinamento (item 1.7.1.2)

- **Inicial**: antes de o trabalhador começar na função, ou no prazo da NR específica.
- **Periódico**: na periodicidade da NR específica ou, se ela não fixar, no prazo que o empregador definir.
- **Eventual**: quando mudam procedimentos ou condições de trabalho de forma que altere os riscos, depois de **acidente grave ou fatal** que indique necessidade, ou na **volta de afastamento superior a 180 dias**.

## O certificado

Ao final, a empresa emite certificado com: nome e assinatura do trabalhador, **conteúdo programático, carga horária, data e local**, nome e qualificação dos instrutores e assinatura do **responsável técnico** do treinamento. Uma via vai para o trabalhador, outra fica arquivada, e a capacitação é registrada nos documentos funcionais.

O tempo gasto em treinamento previsto em NR é **tempo de trabalho efetivo**.

## Aproveitamento

- **Na mesma empresa**: dá para aproveitar conteúdo de treinamento anterior se o conteúdo e a carga estiverem contidos, se foi dado dentro do prazo da NR (ou há menos de 2 anos, se a NR não fixar prazo) e se o responsável técnico validar. A validade passa a contar do treinamento mais antigo aproveitado.
- **De outra empresa**: o treinamento pode ser avaliado e convalidado ou complementado, considerando o que a pessoa fazia, o que vai fazer, conteúdo e carga cumpridos e exigidos.

## EAD e semipresencial (Anexo II)

Permitido, desde que cumpra o Anexo II da NR-01:

- **projeto pedagógico** com objetivo, conteúdo, carga horária, público, material, prazo máximo e avaliação, revalidado a cada 2 anos ou quando a NR mudar;
- carga horária **no mínimo igual** à do presencial;
- tempo de curso **exclusivo** para o curso, sem concorrer com o trabalho do dia;
- canal de dúvidas funcionando durante o curso;
- avaliação de aprendizagem com conceito satisfatório ou insatisfatório, com identificação e senha individual quando online, e situações práticas da rotina;
- **logs de acesso** guardados por no mínimo 2 anos depois do fim da validade do curso;
- realizado em um Ambiente Virtual de Aprendizagem (AVA).

A parte **prática** só pode ser a distância se a NR específica permitir.
""",
        "quiz": [
            {
                "enunciado": "Qual destas situações obriga treinamento EVENTUAL?",
                "alternativas": [
                    ("Férias de 30 dias", False),
                    ("Retorno de afastamento superior a 180 dias", True),
                    ("Aniversário de admissão", False),
                    ("Troca de gestor imediato", False),
                ],
            },
            {
                "enunciado": "O tempo gasto em treinamento previsto em NR é:",
                "alternativas": [
                    ("Banco de horas do trabalhador", False),
                    ("Tempo de trabalho efetivo", True),
                    ("Compensável no fim do mês", False),
                    ("Voluntário", False),
                ],
            },
            {
                "enunciado": "Num treinamento de NR em EAD, a carga horária deve ser:",
                "alternativas": [
                    ("Metade da presencial", False),
                    ("No mínimo igual à presencial", True),
                    ("Livre, definida pelo aluno", False),
                    ("Sempre de 8 horas", False),
                ],
            },
            {
                "enunciado": "Quais informações devem constar no certificado de um treinamento de NR?",
                "alternativas": [
                    ("Apenas o nome do trabalhador e a data", False),
                    ("Nota da prova, salário e cargo do trabalhador", False),
                    ("Nome da empresa e assinatura do sindicato", False),
                    ("Conteúdo programático, carga horária, data, local, instrutores e responsável técnico", True),
                ],
            },
            {
                "enunciado": "Se a NR específica não fixa a periodicidade do treinamento periódico, quem define o prazo?",
                "alternativas": [
                    ("O empregador", True),
                    ("O sindicato", False),
                    ("O próprio trabalhador", False),
                    ("A CIPA", False),
                ],
            },
            {
                "enunciado": "Num aproveitamento de treinamento na mesma empresa, a partir de quando conta a validade?",
                "alternativas": [
                    ("Do treinamento mais recente aproveitado", False),
                    ("Do treinamento mais antigo aproveitado", True),
                    ("Da data de admissão do trabalhador", False),
                    ("Da data em que o responsável técnico validou", False),
                ],
            },
            {
                "enunciado": "A parte prática de um treinamento de NR pode ser feita a distância?",
                "alternativas": [
                    ("Sim, sempre que houver projeto pedagógico", False),
                    ("Não, em nenhuma hipótese", False),
                    ("Só se a NR específica permitir", True),
                    ("Sim, se a carga horária for dobrada", False),
                ],
            },
        ],
    },
    # ── 5 ────────────────────────────────────────────────────────────
    {
        "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0205"),
        "titulo": "Pequenas empresas: a objeção \"sou pequeno, não preciso\"",
        "resumo": "O que a NR-01 dispensa para MEI, ME e EPP, o que ela não dispensa e como qualificar o cliente.",
        "duracao_min": 10,
        "conteudo_md": """\
## O tratamento diferenciado existe, mas é estreito

A NR-01 (item 1.8) alivia **documentos**, não obrigações. Saber exatamente o que ela dispensa é o que separa o vendedor que concorda com a objeção do que a desmonta com o texto.

## MEI

- Está **dispensado de elaborar o PGR**.
- Mas a **empresa que contrata o MEI** e o coloca para trabalhar nas suas dependências tem de incluí-lo nas próprias ações de prevenção e no próprio PGR.

## ME e EPP: dispensa do PGR (item 1.8.4)

Só vale se **todas** as condições forem verdadeiras:

1. grau de risco **1 ou 2** (pela NR-04);
2. no levantamento preliminar, **nenhuma exposição** a agentes **físicos, químicos ou biológicos**;
3. a empresa **declarou as informações digitais** de SST no formato oficial.

## ME e EPP: dispensa do PCMSO (item 1.8.6)

Grau de risco 1 ou 2, informações digitais declaradas e **nenhuma exposição** a agentes físicos, químicos, biológicos **e a riscos ergonômicos**.

E aqui está o ponto que mais se perde: **a dispensa do PCMSO não desobriga a empresa dos exames médicos nem da emissão do ASO**.

## O que nenhuma dispensa afasta

- As **demais disposições das NR** continuam valendo (item 1.8.5).
- Quem declara as informações e responde por elas é o **empregador**.

> Na conversa com o cliente: "Vocês são ME de grau de risco 2? Então a pergunta é: o levantamento preliminar de vocês foi feito e registrado? Sem ele, não há como afirmar que não existe exposição, e sem essa afirmação não existe dispensa. E os exames admissionais e o ASO continuam obrigatórios de qualquer jeito."

## Como qualificar no HIPO

1. Abra a conta e veja o **grau de risco** do CNAE (aba de dados públicos).
2. ME ou EPP de grau 3 ou 4: as dispensas de PGR e de PCMSO dos itens 1.8.4 e 1.8.6 não se aplicam.
3. Grau 1 ou 2: pergunte pelas atividades. Cozinha, oficina, limpeza com produto químico, atendimento de saúde, ruído de máquina: provável exposição, e a dispensa cai.
4. Em qualquer caso, quem tem empregado CLT faz exame admissional e emite ASO.
""",
        "quiz": [
            {
                "enunciado": "Uma ME de grau de risco 2 está dispensada do PCMSO. Ela precisa fazer exames médicos e emitir ASO?",
                "alternativas": [
                    ("Não, a dispensa cobre tudo", False),
                    ("Sim, a dispensa do PCMSO não desobriga dos exames nem do ASO", True),
                    ("Só se tiver mais de 20 empregados", False),
                    ("Só a cada 2 anos", False),
                ],
            },
            {
                "enunciado": "Uma EPP de grau de risco 3 pode usar a dispensa de PGR do item 1.8.4?",
                "alternativas": [
                    ("Sim, toda EPP pode", False),
                    ("Não, a dispensa é só para graus de risco 1 e 2", True),
                    ("Sim, se não tiver CIPA", False),
                    ("Sim, se declarar no eSocial", False),
                ],
            },
            {
                "enunciado": "O MEI está dispensado de elaborar PGR. Quando ele trabalha nas dependências de quem o contratou:",
                "alternativas": [
                    ("Ninguém precisa considerá-lo no PGR", False),
                    ("A contratante deve incluí-lo nas suas ações de prevenção e no seu PGR", True),
                    ("O MEI passa a ter de fazer PGR", False),
                    ("O sindicato faz o PGR dele", False),
                ],
            },
            {
                "enunciado": "Uma ME de grau de risco 2 tem cozinha e limpeza com produto químico. O que provavelmente acontece com a dispensa de PGR?",
                "alternativas": [
                    ("Continua valendo, porque o grau de risco é 2", False),
                    ("Continua valendo, porque é ME", False),
                    ("Cai só se ela tiver mais de 20 empregados", False),
                    ("Cai, porque há provável exposição a agentes", True),
                ],
            },
            {
                "enunciado": "Que condição a dispensa do PCMSO exige a mais que a dispensa do PGR?",
                "alternativas": [
                    ("Nenhuma exposição a riscos ergonômicos", True),
                    ("Ter menos de 10 empregados", False),
                    ("Ter CIPA constituída", False),
                    ("Ter SESMT próprio", False),
                ],
            },
            {
                "enunciado": "Numa ME que usa a dispensa, quem declara as informações de SST e responde por elas?",
                "alternativas": [
                    ("O contador da empresa", False),
                    ("O empregador", True),
                    ("A empresa de medicina ocupacional", False),
                    ("O sindicato da categoria", False),
                ],
            },
            {
                "enunciado": "O que o tratamento diferenciado do item 1.8 da NR-01 alivia?",
                "alternativas": [
                    ("As obrigações de SST da pequena empresa, por completo", False),
                    ("Os exames médicos, mas não os documentos", False),
                    ("Documentos, não obrigações; as demais NR continuam valendo", True),
                    ("As multas, mas não os documentos", False),
                ],
            },
        ],
    },
    # ── 6 ────────────────────────────────────────────────────────────
    {
        "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0206"),
        "titulo": "NR-04: SESMT, quem precisa e de quem",
        "resumo": "O que é o SESMT, como ele é dimensionado pelo grau de risco e pelo número de empregados, e onde a MedSeg entra.",
        "duracao_min": 15,
        "pdf": "nr04",
        "conteudo_md": """\
## O que é o SESMT

O **Serviço Especializado em Segurança e em Medicina do Trabalho** é a equipe própria de SST que a empresa é obrigada a manter quando atinge certo porte e grau de risco. Pode ter **médico do trabalho, engenheiro de segurança, técnico de segurança, enfermeiro do trabalho e auxiliar ou técnico de enfermagem do trabalho**, conforme o Anexo II da NR-04.

## O que o SESMT faz (item 4.3.1)

Elabora ou participa do **inventário de riscos**, acompanha o **plano de ação do PGR**, implanta as medidas de prevenção na ordem da NR-01, monitora metas e indicadores de SST, orienta sobre as NR aplicáveis, interage com a CIPA, investiga acidentes e doenças, pode propor a **interrupção imediata** de atividade em risco grave e iminente e participa do **PCMSO** (NR-07). Um dos médicos do SESMT é o responsável pelo PCMSO.

## Como se dimensiona (item 4.5.1)

Duas variáveis:

1. **Número de empregados** do estabelecimento.
2. **Grau de risco (GR)**, de 1 a 4: vale o **maior** entre o da atividade **principal** (o CNAE do CNPJ) e o da atividade **preponderante** (a que ocupa mais gente). A tabela CNAE x grau de risco é o **Anexo I** da NR-04, e é dela que vem o grau de risco que o HIPO mostra na conta.

## A partir de quando o SESMT é obrigatório

Pelo Anexo II da NR-04, o primeiro profissional (técnico de segurança) aparece a partir de:

- **GR 4**: 50 empregados;
- **GR 3**: 101 empregados;
- **GR 1 e 2**: 501 empregados.

E o **médico do trabalho** entra no SESMT a partir de:

- **GR 4**: 101 empregados (tempo parcial até 500);
- **GR 3**: 501 empregados (tempo parcial até 1.000);
- **GR 1 e 2**: 1.001 empregados.

Carga horária: técnico de segurança e auxiliar ou técnico de enfermagem, **44 horas semanais**; engenheiro, médico e enfermeiro, no mínimo **15 horas semanais (parcial) ou 30 horas (integral)**.

## Modalidades (item 4.4)

- **Individual**: o estabelecimento se enquadra no Anexo II.
- **Regionalizado**: um estabelecimento se enquadra e estende o atendimento aos outros da mesma UF, somando os trabalhadores.
- **Estadual**: nenhum estabelecimento se enquadra sozinho, mas a soma na UF alcança o Anexo II.
- **Compartilhado**: empresas da mesma atividade econômica, no mesmo município ou em municípios vizinhos.

Na soma do regionalizado ou estadual, estabelecimentos GR 1 e 2 de ME e EPP entram pela **metade** dos trabalhadores.

**Terceiros contam**: trabalhadores de contratadas que atuam de forma não eventual nas dependências da contratante entram no dimensionamento dela, salvo se já atendidos pelo SESMT da própria contratada.

O SESMT é **registrado** em sistema eletrônico no gov.br, com CPF, qualificação e registro dos profissionais, grau de risco, número de trabalhadores e horários.

## Onde a MedSeg entra

A grande maioria das empresas que atendemos **não chega** ao Anexo II: tem menos de 50 empregados, ou é GR 1 ou 2 com menos de 501. Elas **não têm SESMT**, mas continuam obrigadas a ter **PGR** (NR-01), **PCMSO** (NR-07), exames e ASO. Sem equipe própria, alguém de fora precisa elaborar e conduzir esses programas.

> Na conversa com o cliente: "Vocês têm 80 pessoas e o CNAE é grau de risco 3. Pela NR-04 ainda não precisam de SESMT próprio, o que é bom: não precisam contratar técnico em tempo integral. Mas o PGR e o PCMSO continuam obrigatórios. Hoje quem cuida disso para vocês?"
""",
        "quiz": [
            {
                "enunciado": "Para dimensionar o SESMT, qual grau de risco vale?",
                "alternativas": [
                    ("Sempre o do CNAE principal do CNPJ", False),
                    ("O maior entre o da atividade principal e o da preponderante", True),
                    ("O menor entre os dois", False),
                    ("O que a empresa declarar", False),
                ],
            },
            {
                "enunciado": "Uma empresa de grau de risco 3 com 80 empregados precisa de SESMT próprio?",
                "alternativas": [
                    ("Sim, com médico do trabalho", False),
                    ("Não; pelo Anexo II, no GR 3 o SESMT começa em 101 empregados", True),
                    ("Sim, com técnico de segurança", False),
                    ("Só se tiver CIPA", False),
                ],
            },
            {
                "enunciado": "Trabalhadores de uma prestadora de serviço que atuam de forma não eventual na contratante:",
                "alternativas": [
                    ("Nunca entram no dimensionamento da contratante", False),
                    ("Entram no dimensionamento da contratante, salvo se já atendidos pelo SESMT da contratada", True),
                    ("Contam em dobro", False),
                    ("Só entram se forem mais de 50", False),
                ],
            },
            {
                "enunciado": "Uma empresa sem SESMT (abaixo do Anexo II) está dispensada de PGR e PCMSO?",
                "alternativas": [
                    ("Sim, SESMT, PGR e PCMSO andam juntos", False),
                    ("Não; PGR (NR-01) e PCMSO (NR-07) continuam obrigatórios", True),
                    ("Sim, se for grau de risco 1", False),
                    ("Só está dispensada do PCMSO", False),
                ],
            },
            {
                "enunciado": "Uma empresa de grau de risco 4 tem 60 empregados. Pelo Anexo II da NR-04, como fica o SESMT?",
                "alternativas": [
                    ("Não precisa de SESMT, que começa em 101", False),
                    ("Precisa de técnico e de médico do trabalho", False),
                    ("Precisa só de médico do trabalho em tempo parcial", False),
                    ("Precisa de técnico de segurança; o médico só entra a partir de 101", True),
                ],
            },
            {
                "enunciado": "Nenhum estabelecimento se enquadra sozinho no Anexo II, mas a soma na mesma UF alcança. Qual modalidade de SESMT?",
                "alternativas": [
                    ("Estadual", True),
                    ("Individual", False),
                    ("Compartilhado", False),
                    ("Regionalizado", False),
                ],
            },
            {
                "enunciado": "Qual é a carga horária semanal do técnico de segurança no SESMT?",
                "alternativas": [
                    ("15 horas", False),
                    ("44 horas", True),
                    ("30 horas", False),
                    ("20 horas", False),
                ],
            },
        ],
    },
]


TRILHA_03 = {
    # Mesmo id da trilha "Normas Regulamentadoras: NR-01 e NR-04" (029).
    "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0101"),
    "titulo": "03 · Produto e normas",
    "pilar": "tecnica",
    "descricao": (
        "Cada serviço do portfólio ligado à norma que o exige, e as duas normas "
        "que sustentam quase toda venda: NR-01 (gerenciamento de riscos, PGR, "
        "riscos psicossociais, treinamentos, pequenas empresas) e NR-04 (SESMT)."
    ),
    "prazo_dias": 30,
    "aulas": [AULA_PRODUTO, *_AULAS_NR],
}




# ═════════════════════════════════════════════════════════════════════
# TRILHA 04 — Técnicas de venda consultiva (pilar Técnica)
# ═════════════════════════════════════════════════════════════════════
# A teoria, com profundidade: de onde vem cada técnica, o que ela diz e
# por que funciona. A APLICAÇÃO na Controller (falas, perguntas, regras,
# scorecard) está na trilha de Método "Roteiro de vendas Controller".

TRILHA_04 = {
    "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0400"),
    "titulo": "04 · Técnicas de venda consultiva",
    "pilar": "tecnica",
    "descricao": (
        "As técnicas que sustentam o roteiro de vendas da Controller, em "
        "profundidade: venda consultiva, contrato de abertura (Sandler), SPIN "
        "Selling, GPCT + BA/C&I, o insight Challenger, LAER para objeções, "
        "escuta ativa e fechamento."
    ),
    "prazo_dias": 40,
    "obrigatorios": ("SDR", "EV", "EC"),
    "opcionais": ("EP", "ADM", "Franqueado"),
    "aulas": [
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0411"),
            "titulo": "Venda consultiva: diagnosticar antes de apresentar",
            "resumo": "Por que a reunião começa pelo problema do cliente e não pela empresa, e como as técnicas se encaixam.",
            "duracao_min": 8,
            "conteudo_md": """\
## A ideia central

**Venda consultiva** é vender como um médico atende: primeiro o diagnóstico, depois a receita. Um médico que receita antes de examinar perde a confiança do paciente, mesmo que acerte o remédio. Um vendedor que apresenta antes de entender o problema do cliente faz o mesmo: mostra um catálogo, e o cliente compara preço.

A regra que resume tudo: **diagnosticar antes de apresentar**.

## Por que isso pesa tanto em SST

Em Saúde e Segurança do Trabalho o cliente raramente **sente** a dor. Ela é invisível até o dia em que chega um fiscal, um processo trabalhista ou um afastamento. Até lá, SST parece um custo obrigatório, e custo obrigatório se compra pelo menor preço.

O trabalho do vendedor consultivo é tornar esse risco **concreto e visível** antes de falar de solução. Quando o próprio cliente diz em voz alta quanto o problema custa, a conversa muda de "quanto custa o exame" para "quanto custa não resolver".

## Quem fala na reunião

Numa reunião consultiva **o cliente fala mais que o vendedor**. A referência que usamos: o vendedor fala no máximo **30%** do tempo na conversa e até **40%** medidos na transcrição inteira. Cada minuto que você fala é um minuto em que você não está aprendendo nada sobre o cliente.

## As técnicas e o papel de cada uma

Nenhuma técnica sozinha cobre a reunião inteira. Cada uma resolve um momento:

- **Contrato de abertura (Sandler)**: abre a reunião combinando tempo, pauta e o que acontece no final.
- **SPIN Selling (Rackham)**: conduz o diagnóstico com quatro tipos de pergunta.
- **GPCT + BA/C&I (HubSpot)**: qualifica, para saber se a oportunidade merece proposta.
- **Insight Challenger (Dixon e Adamson)**: traz algo que o cliente não sabia e posiciona o vendedor como especialista.
- **LAER (Carew International)**: trata objeções sem brigar com o cliente.
- **Escuta ativa e fechamento**: amarram tudo e transformam a conversa em próximo passo.

As próximas aulas explicam cada uma em profundidade. A trilha de **Método · Roteiro de vendas Controller** mostra como aplicamos todas elas, com as nossas falas e perguntas.
""",
            "quiz": [
                {
                    "enunciado": "Qual é a regra central da venda consultiva?",
                    "alternativas": [
                        ("Apresentar a empresa logo no início para gerar confiança", False),
                        ("Diagnosticar antes de apresentar", True),
                        ("Dar o preço antes de qualquer pergunta", False),
                        ("Mostrar o portfólio completo em toda reunião", False),
                    ],
                },
                {
                    "enunciado": "Por que o diagnóstico pesa tanto na venda de SST?",
                    "alternativas": [
                        ("Porque SST é barato", False),
                        ("Porque o cliente raramente sente a dor até ser autuado, processado ou ter um afastamento", True),
                        ("Porque o cliente sempre sabe exatamente o que precisa", False),
                        ("Porque a norma obriga o vendedor a perguntar", False),
                    ],
                },
                {
                    "enunciado": "Qual técnica é usada para tratar objeções?",
                    "alternativas": [
                        ("SPIN", False),
                        ("GPCT", False),
                        ("LAER", True),
                        ("Contrato de abertura", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, o que acontece quando o vendedor apresenta antes de entender o problema do cliente?",
                    "alternativas": [
                        ("O cliente passa a comparar preço, como diante de um catálogo", True),
                        ("O cliente ganha confiança e decide mais rápido", False),
                        ("A reunião fica mais curta e mais produtiva", False),
                        ("O cliente revela sozinho todas as suas dores", False),
                    ],
                },
                {
                    "enunciado": "Quando o próprio cliente diz em voz alta quanto o problema custa, a conversa muda de quê para quê?",
                    "alternativas": [
                        ("De \"quanto custa não resolver\" para \"quanto custa o exame\"", False),
                        ("De \"quem decide\" para \"quando vamos começar\"", False),
                        ("De \"qual é o prazo\" para \"qual é o desconto\"", False),
                        ("De \"quanto custa o exame\" para \"quanto custa não resolver\"", True),
                    ],
                },
                {
                    "enunciado": "Qual é a referência de tempo de fala do vendedor numa reunião consultiva, segundo a aula?",
                    "alternativas": [
                        ("No mínimo 50% na conversa e até 60% na transcrição inteira", False),
                        ("No máximo 30% na conversa e até 40% na transcrição inteira", True),
                        ("No máximo 40% na conversa e até 30% na transcrição inteira", False),
                        ("Metade do tempo para cada lado, em qualquer medição", False),
                    ],
                },
                {
                    "enunciado": "O vendedor precisa decidir se uma oportunidade merece proposta. Qual técnica, segundo a aula, cumpre esse papel?",
                    "alternativas": [
                        ("Insight Challenger (Dixon e Adamson)", False),
                        ("GPCT + BA/C&I (HubSpot)", True),
                        ("Contrato de abertura (Sandler)", False),
                        ("SPIN Selling (Rackham)", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0412"),
            "titulo": "Contrato de abertura (Sandler)",
            "resumo": "O combinado do início da reunião: tempo, pauta, papéis e o que se decide no final.",
            "duracao_min": 8,
            "conteudo_md": """\
## De onde vem

O **contrato de abertura** (em inglês, *up-front contract*) é uma das bases do **Sandler Selling System**, o método criado por David Sandler nos anos 1960. A ideia é simples: muitas reuniões fracassam não pelo que é dito, mas pelo que **não foi combinado**. O vendedor acha que vai sair com uma decisão; o cliente acha que só veio ouvir. A reunião acaba em "vou pensar".

O contrato de abertura resolve isso **no primeiro minuto**, combinando as regras do jogo antes de jogar.

## Os quatro elementos

Um contrato de abertura completo combina:

1. **Tempo**: quanto dura a conversa. "Combinamos 45 minutos, ainda está bom?" Confirmar o tempo mostra respeito e evita que o cliente saia no meio.
2. **Propósito e pauta**: o que vai acontecer. Primeiro o vendedor entende a realidade do cliente; depois, se fizer sentido, mostra como pode ajudar.
3. **Papéis**: o que se espera de cada um. O cliente vai responder perguntas; o vendedor vai ouvir e, se tiver solução, apresentar.
4. **Desfecho**: o que acontece no final. Este é o elemento mais importante e o mais esquecido: **no final, decidimos juntos se há um próximo passo ou não**.

## Por que o "não" é uma resposta boa

Sandler insistia que o vendedor deve dar ao cliente permissão explícita para dizer **não**. Parece contraintuitivo, mas tem efeito duplo:

- **Tira a pressão**: o cliente relaxa porque sabe que não vai ser empurrado, e por isso responde as perguntas com mais franqueza.
- **Acaba com o "vou pensar"**: se ficou combinado que haveria uma decisão, "vou pensar" deixa de ser uma saída aceita. Um "não" claro libera o vendedor para a próxima oportunidade; um "talvez" eterno ocupa o funil e a agenda.

## Sinais de que o contrato funcionou

- O cliente concorda com a pauta e com o tempo ("pode ser").
- O cliente aceita responder perguntas antes de ver a apresentação.
- No final, quando você retoma "combinamos que decidiríamos o próximo passo", o cliente reconhece o combinado.

## Erros comuns

- Pular o desfecho e combinar só tempo e pauta.
- Fazer o contrato de forma burocrática, como um termo a ser assinado. Ele é uma conversa, dita com naturalidade.
- Esquecer de retomar o contrato no fechamento. O contrato do início só vale se for lembrado no final.
""",
            "quiz": [
                {
                    "enunciado": "Qual elemento do contrato de abertura é o mais esquecido e o mais importante?",
                    "alternativas": [
                        ("O tempo da reunião", False),
                        ("O desfecho: decidir juntos no final se há próximo passo", True),
                        ("A apresentação da empresa", False),
                        ("O preço", False),
                    ],
                },
                {
                    "enunciado": "Por que dar ao cliente permissão explícita para dizer \"não\"?",
                    "alternativas": [
                        ("Para encerrar a reunião mais cedo", False),
                        ("Porque tira a pressão, deixa o cliente mais franco e acaba com o \"vou pensar\"", True),
                        ("Porque é exigência da LGPD", False),
                        ("Para parecer desinteressado", False),
                    ],
                },
                {
                    "enunciado": "Quando o contrato de abertura deve ser retomado?",
                    "alternativas": [
                        ("Nunca, basta fazê-lo no início", False),
                        ("No fechamento, ao propor o próximo passo", True),
                        ("Só se o cliente pedir desconto", False),
                        ("No e-mail de proposta", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, por que muitas reuniões terminam em \"vou pensar\"?",
                    "alternativas": [
                        ("Porque o vendedor fez perguntas demais antes de apresentar a solução", False),
                        ("Pelo que não foi combinado: vendedor e cliente esperavam desfechos diferentes", True),
                        ("Porque a apresentação institucional foi curta demais para convencer", False),
                        ("Porque o cliente não recebeu a proposta por e-mail antes da reunião", False),
                    ],
                },
                {
                    "enunciado": "No contrato de abertura, o que define o elemento \"Papéis\"?",
                    "alternativas": [
                        ("O cliente responde perguntas; o vendedor ouve e, se tiver solução, apresenta", True),
                        ("O vendedor apresenta a empresa; o cliente diz se gostou ou não", False),
                        ("O cliente define a pauta; o vendedor controla o tempo da reunião", False),
                        ("O vendedor pergunta o orçamento; o cliente indica quem decide", False),
                    ],
                },
                {
                    "enunciado": "Qual destes é um sinal de que o contrato de abertura funcionou?",
                    "alternativas": [
                        ("O cliente pede para ver a apresentação logo no início", False),
                        ("O cliente diz no final que ainda vai pensar no assunto", False),
                        ("O cliente pede o preço antes de começar o diagnóstico", False),
                        ("O cliente aceita responder perguntas antes de ver a apresentação", True),
                    ],
                },
                {
                    "enunciado": "Qual destes é um erro comum ao fazer o contrato de abertura, segundo a aula?",
                    "alternativas": [
                        ("Dizê-lo com naturalidade, como parte da conversa", False),
                        ("Confirmar com o cliente o tempo combinado da reunião", False),
                        ("Fazê-lo de forma burocrática, como um termo a ser assinado", True),
                        ("Combinar que no final se decide o próximo passo", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0413"),
            "titulo": "SPIN Selling: a pesquisa e os quatro tipos de pergunta",
            "resumo": "O que Neil Rackham descobriu estudando milhares de visitas de venda, e o papel de Situação, Problema, Implicação e Necessidade.",
            "duracao_min": 15,
            "conteudo_md": """\
## De onde vem

**SPIN Selling** é o resultado de uma pesquisa conduzida por **Neil Rackham** e pela Huthwaite, publicada no livro *SPIN Selling* (1988). A equipe observou cerca de **35 mil visitas de venda** ao longo de vários anos para descobrir o que os vendedores de melhor resultado faziam de diferente em **vendas complexas**: as de ticket alto, ciclo longo e mais de um decisor. É o caso de um contrato de SST.

A descoberta principal: nas vendas complexas, quem mais vende **não é quem apresenta melhor, é quem pergunta melhor**, e na ordem certa.

## Necessidade implícita × necessidade explícita

Rackham separa dois tipos de necessidade:

- **Implícita**: uma insatisfação vaga. "O admissional às vezes demora." O cliente reconhece o incômodo, mas não quer gastar para resolvê-lo.
- **Explícita**: um desejo claro de mudança. "Preciso que o admissional saia em 24 horas, porque cada dia de atraso me custa uma loja desfalcada." Aqui o cliente já quer comprar.

Em vendas pequenas, uma necessidade implícita às vezes basta. Em vendas complexas, **só a explícita fecha negócio**. O papel das perguntas SPIN é transformar uma em outra.

## S · Situação

Perguntas sobre **fatos** da realidade do cliente: quantos funcionários, quem cuida de SST hoje, quando foi a última revisão do PGR.

- São necessárias, mas **não vendem**. A pesquisa mostrou que vendedores de pior resultado fazem perguntas de Situação demais, e o cliente se cansa delas.
- Regra: pergunte só o que a pesquisa prévia **não respondeu**. Tudo o que está no cartão CNPJ, no site ou no LinkedIn não se pergunta.

## P · Problema

Perguntas que exploram **dificuldades, insatisfações e incômodos**: "O que te incomoda no modelo atual?", "Já aconteceu de…?".

- Revelam as **necessidades implícitas**.
- Vendedores experientes fazem mais perguntas de Problema que os iniciantes.

## I · Implicação

Perguntas sobre as **consequências e os efeitos** do problema: "Quanto custa um dia de funcionário parado?", "Se o fiscal chegasse amanhã, o que encontraria?".

- É o tipo de pergunta **mais ligado ao sucesso** nas vendas complexas, e o mais difícil de fazer bem.
- Pegam um problema que parece pequeno e mostram o tamanho real dele. Um admissional atrasado vira dias de loja desfalcada, venda perdida, hora extra de outro funcionário.
- Em SST, é aqui que o risco invisível fica concreto: autuação, ação trabalhista, aposentadoria especial errada, horas do RH conferindo eSocial.

## N · Necessidade de solução (*need-payoff*)

Perguntas sobre o **valor e a utilidade** de resolver: "Se você tivesse todos os vencimentos num lugar só, o que mudaria na sua rotina?".

- O ponto genial do SPIN: quem diz o benefício **é o cliente**, não o vendedor. Um benefício dito pelo cliente convence muito mais do que o mesmo benefício dito pelo vendedor.
- Transformam a necessidade implícita em **explícita**.
- Preparam a apresentação: depois delas, você só mostra o que o cliente já disse que quer.

## A sequência não é rígida

S → P → I → N é a lógica natural, mas a conversa vai e volta. O que não pode acontecer é **pular a Implicação**: sem ela, o cliente tem um problema pequeno e uma solução cara.

## Erros comuns

- Interrogatório: disparar as perguntas da lista uma atrás da outra, sem ouvir.
- Apresentar a solução assim que aparece o primeiro problema. Rackham mostrou que oferecer solução cedo demais, quando a necessidade ainda é implícita, gera objeção.
- Fazer Situação demais e Implicação de menos.
""",
            "quiz": [
                {
                    "enunciado": "Qual tipo de pergunta SPIN a pesquisa de Rackham mais associou ao sucesso em vendas complexas?",
                    "alternativas": [
                        ("Situação", False),
                        ("Problema", False),
                        ("Implicação", True),
                        ("Nenhuma, o que importa é a apresentação", False),
                    ],
                },
                {
                    "enunciado": "O que é uma necessidade explícita?",
                    "alternativas": [
                        ("Uma insatisfação vaga com a situação atual", False),
                        ("Um desejo claro de mudança, que o cliente quer resolver", True),
                        ("Uma necessidade que só o vendedor enxerga", False),
                        ("Uma exigência da norma", False),
                    ],
                },
                {
                    "enunciado": "Qual é a grande vantagem das perguntas de Necessidade de solução (need-payoff)?",
                    "alternativas": [
                        ("Elas dispensam a apresentação", False),
                        ("O próprio cliente verbaliza o benefício de resolver", True),
                        ("Elas descobrem o orçamento", False),
                        ("Elas encurtam a reunião", False),
                    ],
                },
                {
                    "enunciado": "Qual é o erro típico com perguntas de Situação?",
                    "alternativas": [
                        ("Fazer poucas", False),
                        ("Fazer demais, inclusive sobre o que a pesquisa já respondia", True),
                        ("Fazer no início da reunião", False),
                        ("Anotar as respostas", False),
                    ],
                },
                {
                    "enunciado": "O cliente comenta: \"O admissional às vezes demora.\" Segundo a aula, isso é:",
                    "alternativas": [
                        ("Uma necessidade implícita, uma insatisfação vaga", True),
                        ("Uma necessidade explícita, pronta para fechar negócio", False),
                        ("Uma pergunta de Implicação feita pelo próprio cliente", False),
                        ("Uma objeção de preço que precisa ser tratada com LAER", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, o que acontece quando o vendedor pula as perguntas de Implicação?",
                    "alternativas": [
                        ("O cliente decide mais rápido, porque a reunião encurta", False),
                        ("A apresentação fica mais convincente e mais objetiva", False),
                        ("O cliente fica com um problema pequeno e uma solução cara", True),
                        ("As perguntas de Situação passam a fazer o papel delas", False),
                    ],
                },
                {
                    "enunciado": "O que Rackham mostrou sobre oferecer a solução assim que aparece o primeiro problema?",
                    "alternativas": [
                        ("Gera objeção, porque a necessidade ainda é implícita", True),
                        ("Acelera o fechamento, porque o cliente vê a solução cedo", False),
                        ("Funciona bem quando o ticket é alto e o ciclo é longo", False),
                        ("Transforma automaticamente a necessidade em explícita", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0414"),
            "titulo": "Qualificação GPCT + BA/C&I (HubSpot)",
            "resumo": "Os oito critérios que dizem se uma oportunidade merece proposta: metas, planos, desafios, prazo, orçamento, autoridade, consequências e implicações.",
            "duracao_min": 12,
            "conteudo_md": """\
## De onde vem

**GPCT + BA/C&I** é um modelo de qualificação de oportunidades popularizado pela **HubSpot** como evolução do antigo **BANT** (*Budget, Authority, Need, Timeline*). O BANT perguntava primeiro sobre dinheiro e poder de decisão; o GPCT começa pelo que o cliente **quer alcançar**, que é por onde uma venda consultiva deve começar.

Qualificar não é burocracia: é decidir **onde investir o seu tempo**. Uma proposta feita para quem não tem prazo, verba ou poder de decisão ocupa horas e quase nunca fecha.

## GPCT: o lado do cliente

- **G · Goals (Metas)**: o que o cliente quer alcançar. Uma meta concreta ("regularizar antes da fiscalização", "padronizar as unidades") é sinal de compra; "só quero cotar" não é.
- **P · Plans (Planos)**: o que ele já tentou ou planeja fazer. Quem tentou e não conseguiu tem dor real; quem nunca pensou no assunto ainda não está pronto.
- **C · Challenges (Desafios)**: o que impediu de resolver até agora. O obstáculo importa: se é algo que a sua solução remove, ótimo; se é interno e sem solução, a venda trava.
- **T · Timeline (Prazo)**: quando precisa estar resolvido. Uma data ou um gatilho (vencimento de contrato, nova unidade, fiscalização) mostra urgência; "sem pressa" mostra que não é prioridade.

## BA: o lado da compra

- **B · Budget (Orçamento)**: quanto investe hoje e se aceita discutir **valor**, não só preço. Quem decide exclusivamente pelo menor preço por exame raramente valoriza um serviço consultivo.
- **A · Authority (Autoridade)**: quem decide e como a empresa aprova um fornecedor. Falar só com quem não decide é o motivo mais comum de oportunidade parada.

## C&I: o que está em jogo

- **C · Negative Consequences (Consequências)**: o que acontece se nada mudar. Se o cliente nomeia um risco real, há motivo para agir; se a resposta é "nada", não há.
- **I · Positive Implications (Implicações)**: o que muda, para ele e para a empresa, se der certo. Inclui o ganho **pessoal** do interlocutor: menos retrabalho, reconhecimento, tranquilidade.

## A ordem importa

Pergunte **orçamento depois das consequências e implicações**. Com o custo do problema já dito pelo cliente, o investimento é comparado ao **risco**, e não ao preço do concorrente.

## Ligação com o SPIN

O GPCT não é um segundo interrogatório. Boa parte dele já aparece no diagnóstico SPIN: as Implicações do SPIN alimentam as Consequências do GPCT; as perguntas de Necessidade de solução alimentam as Implicações positivas. A etapa de qualificação só completa o que faltou: principalmente **prazo, autoridade e orçamento**.
""",
            "quiz": [
                {
                    "enunciado": "O GPCT + BA/C&I é uma evolução de qual modelo de qualificação?",
                    "alternativas": [
                        ("SPIN", False),
                        ("BANT", True),
                        ("LAER", False),
                        ("AIDA", False),
                    ],
                },
                {
                    "enunciado": "Por que perguntar orçamento depois das consequências e implicações?",
                    "alternativas": [
                        ("Para o cliente esquecer o preço", False),
                        ("Para que o investimento seja comparado ao risco que o cliente já verbalizou, e não ao preço do concorrente", True),
                        ("Porque orçamento não importa", False),
                        ("Porque o HubSpot exige essa ordem", False),
                    ],
                },
                {
                    "enunciado": "O que o critério A (Authority) investiga?",
                    "alternativas": [
                        ("Quem decide e como a empresa aprova um fornecedor", True),
                        ("Se o cliente tem certificação ISO", False),
                        ("Qual é o grau de risco da empresa", False),
                        ("Quem é o médico do PCMSO", False),
                    ],
                },
                {
                    "enunciado": "Perguntado sobre prazo, o cliente responde \"sem pressa\". Segundo a aula, isso indica:",
                    "alternativas": [
                        ("Que ele tem urgência, mas prefere não demonstrar", False),
                        ("Que o orçamento para o serviço já está aprovado", False),
                        ("Que resolver isso não é prioridade para ele agora", True),
                        ("Que o decisor da compra está presente na reunião", False),
                    ],
                },
                {
                    "enunciado": "No critério P (Plans), por que importa saber o que o cliente já tentou fazer?",
                    "alternativas": [
                        ("Porque quem tentou e não conseguiu tem uma dor real", True),
                        ("Para descobrir quanto ele pagava ao fornecedor antigo", False),
                        ("Para identificar quem aprova um fornecedor novo", False),
                        ("Para definir a data de início do novo contrato", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, qual é o motivo mais comum de oportunidade parada?",
                    "alternativas": [
                        ("Perguntar o orçamento cedo demais", False),
                        ("Fazer perguntas de Implicação demais", False),
                        ("Falar só com quem não decide", True),
                        ("Apresentar a proposta pessoalmente", False),
                    ],
                },
                {
                    "enunciado": "Como o GPCT se relaciona com o diagnóstico SPIN, segundo a aula?",
                    "alternativas": [
                        ("O GPCT refaz todas as perguntas do SPIN para confirmar as respostas", False),
                        ("Boa parte do GPCT já aparece no SPIN; a qualificação só completa o que faltou", True),
                        ("O GPCT substitui o SPIN sempre que a venda é complexa e de ticket alto", False),
                        ("Não se relacionam: o GPCT ignora o que surgiu no diagnóstico", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0415"),
            "titulo": "O insight Challenger",
            "resumo": "Ensinar algo novo ao cliente, adaptar a mensagem e conduzir a conversa: por que o especialista vence o vendedor simpático.",
            "duracao_min": 10,
            "conteudo_md": """\
## De onde vem

*The Challenger Sale* (2011), de **Matthew Dixon e Brent Adamson**, saiu de uma pesquisa do **CEB** (hoje parte do Gartner) com milhares de vendedores B2B. Eles agruparam os vendedores em perfis e compararam o desempenho de cada um. O perfil **Challenger** foi o que mais se destacou entre os de alto desempenho, principalmente em vendas complexas; o perfil que só constrói relacionamento (*Relationship Builder*) foi o que menos apareceu entre os melhores.

A conclusão incomodou muita gente: ser simpático e disponível **não basta**. O cliente B2B quer um vendedor que o faça pensar diferente sobre o próprio negócio.

## Os três movimentos do Challenger

1. **Ensinar (*Teach*)**: trazer um **insight**, algo que o cliente não sabia sobre o próprio risco ou oportunidade, e que muda a forma como ele vê o problema.
2. **Adaptar (*Tailor*)**: ajustar a mensagem a quem está na sala. O RH, o financeiro, o dono e o técnico de segurança têm dores diferentes.
3. **Conduzir (*Take control*)**: conduzir a conversa com firmeza, inclusive sobre preço e próximos passos, sem ser agressivo.

## O que é um bom insight

Um insight comercial não é uma informação qualquer. Ele precisa:

- ser **novo** para o cliente;
- ser **relevante** para o negócio dele;
- levar naturalmente a algo que **você resolve melhor**.

Exemplo em SST: "Desde 26/05/2026 a nova redação da NR-01 exige que o PGR trate os fatores de risco psicossociais, e ela mesma manda revisar o PGR quando a lei muda. Muitas empresas ainda não revisaram." O cliente não sabia, é relevante (risco de autuação) e leva a um serviço da Controller.

## Toque, não palestra

Na Controller usamos um **toque** Challenger, não o método inteiro. O insight entra no diagnóstico como uma pergunta ou um comentário curto, e o cliente é quem tira a conclusão. Um insight dito em tom de sermão gera defesa; dito como pergunta, gera reflexão.

## O que muda na posição do vendedor

O insight posiciona a Controller como **consultoria** e não como "clínica de exame". Clínica de exame se compara por preço por exame; consultoria se compara pelo risco que evita.
""",
            "quiz": [
                {
                    "enunciado": "Quais são os três movimentos do vendedor Challenger?",
                    "alternativas": [
                        ("Ouvir, acolher e responder", False),
                        ("Ensinar, adaptar e conduzir", True),
                        ("Situação, problema e implicação", False),
                        ("Prospectar, apresentar e fechar", False),
                    ],
                },
                {
                    "enunciado": "Qual destas características NÃO é exigida de um bom insight comercial?",
                    "alternativas": [
                        ("Ser novo para o cliente", False),
                        ("Ser relevante para o negócio dele", False),
                        ("Levar a algo que você resolve melhor", False),
                        ("Ser dito em tom de sermão, para impor autoridade", True),
                    ],
                },
                {
                    "enunciado": "Qual perfil a pesquisa do Challenger encontrou menos entre os vendedores de alto desempenho?",
                    "alternativas": [
                        ("Challenger", False),
                        ("O que só constrói relacionamento (Relationship Builder)", True),
                        ("Todos apareceram igualmente", False),
                        ("O vendedor técnico", False),
                    ],
                },
                {
                    "enunciado": "Qual é a diferença entre ser visto como \"clínica de exame\" e como \"consultoria\"?",
                    "alternativas": [
                        ("Clínica se compara pelo risco que evita; consultoria, por preço por exame", False),
                        ("Clínica atende só empresas pequenas; consultoria atende só indústrias", False),
                        ("Nenhuma: as duas são comparadas pelo preço por exame", False),
                        ("Clínica se compara por preço por exame; consultoria, pelo risco que evita", True),
                    ],
                },
                {
                    "enunciado": "Como a Controller usa o método Challenger nas reuniões?",
                    "alternativas": [
                        ("Como método completo, com uma palestra sobre a NR-01 na abertura", False),
                        ("Como um sermão curto, para deixar clara a autoridade técnica", False),
                        ("Como um toque: o insight vira pergunta curta e o cliente tira a conclusão", True),
                        ("Só depois da proposta, como argumento no e-mail de follow-up", False),
                    ],
                },
                {
                    "enunciado": "Na sala estão o dono e o técnico de segurança, com dores diferentes, e o vendedor ajusta a mensagem para cada um. Qual movimento Challenger é esse?",
                    "alternativas": [
                        ("Ensinar (Teach)", False),
                        ("Conduzir (Take control)", False),
                        ("Acolher (Acknowledge)", False),
                        ("Adaptar (Tailor)", True),
                    ],
                },
                {
                    "enunciado": "Por que o comentário sobre a NR-01 exigir riscos psicossociais no PGR é um bom insight comercial?",
                    "alternativas": [
                        ("É uma regra antiga que todo cliente já conhece e por isso gera confiança imediata", False),
                        ("Dispensa o diagnóstico, porque vale do mesmo jeito para qualquer empresa", False),
                        ("É novo para o cliente, relevante pelo risco de autuação e leva a um serviço da Controller", True),
                        ("Permite apresentar o preço logo no início, antes de qualquer pergunta", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0416"),
            "titulo": "LAER: tratamento de objeções",
            "resumo": "Listen, Acknowledge, Explore, Respond: por que nunca responder uma objeção antes de explorá-la.",
            "duracao_min": 10,
            "conteudo_md": """\
## De onde vem

**LAER** é um modelo de tratamento de objeções associado à **Carew International**. O nome vem das quatro etapas em inglês: ***Listen, Acknowledge, Explore, Respond***. Em português: **Ouvir, Acolher, Explorar e Responder**.

A premissa: a objeção que o cliente **diz** quase nunca é a objeção **real**. "Está caro" pode significar "não entendi o valor", "não tenho verba este mês" ou "o outro fornecedor me deu um desconto e quero o mesmo". Responder à frase errada é perder a venda com um argumento certo.

## L · Ouvir (*Listen*)

Ouça a objeção **até o fim, sem interromper**. Interromper passa a mensagem de que você já sabe o que ele vai dizer e está pronto para rebater, o que coloca o cliente na defensiva.

## A · Acolher (*Acknowledge*)

Mostre que entendeu e que a preocupação é legítima: "Faz sentido você pensar nisso." Acolher **não é concordar**: é reconhecer que o cliente tem direito à dúvida. Isso baixa a tensão e abre espaço para a próxima etapa.

## E · Explorar (*Explore*)

É a etapa que diferencia o método, e a mais pulada. Faça **uma pergunta** para descobrir a objeção real e o que está por trás dela:

- "Caro comparado a quê?"
- "O que exatamente você quer avaliar melhor: preço, escopo ou o momento?"
- "O que te preocupa mais na troca?"

Explorar costuma revelar que a objeção é outra, menor ou mais fácil de resolver do que parecia. Às vezes o próprio cliente resolve a objeção ao respondê-la.

## R · Responder (*Respond*)

Só agora responda, e responda à **objeção real**, com um **fato ligado ao diagnóstico**. A melhor resposta usa as palavras que o cliente disse antes: "Você me contou que o RH gasta horas conferindo eSocial…".

Depois de responder, **confirme**: "Isso responde à sua preocupação?" Se não, volte a explorar.

## A regra de ouro

**Nunca responda antes de explorar.** A resposta pronta, por melhor que seja, soa como discurso decorado e gera uma nova objeção.

## Objeção é bom sinal

Cliente sem objeção nenhuma geralmente não está considerando comprar de verdade. A objeção mostra que ele está imaginando como seria fechar, e o que o impede. O pior cenário não é a objeção dita; é a objeção **escondida**, que só aparece depois, como silêncio.
""",
            "quiz": [
                {
                    "enunciado": "O que significam as letras do LAER?",
                    "alternativas": [
                        ("Listar, Argumentar, Explicar, Repetir", False),
                        ("Ouvir, Acolher, Explorar, Responder", True),
                        ("Ligar, Agendar, Enviar, Retornar", False),
                        ("Levantar, Analisar, Executar, Revisar", False),
                    ],
                },
                {
                    "enunciado": "Qual é a regra de ouro do LAER?",
                    "alternativas": [
                        ("Sempre dar desconto na primeira objeção", False),
                        ("Nunca responder antes de explorar", True),
                        ("Responder rápido para não perder o ritmo", False),
                        ("Ignorar objeções de preço", False),
                    ],
                },
                {
                    "enunciado": "Acolher a objeção significa:",
                    "alternativas": [
                        ("Concordar com o cliente", False),
                        ("Reconhecer que a dúvida é legítima, sem necessariamente concordar", True),
                        ("Mudar de assunto", False),
                        ("Pedir para o cliente repetir", False),
                    ],
                },
                {
                    "enunciado": "O cliente diz: \"Está caro.\" Segundo o LAER, qual é uma boa pergunta para a etapa Explorar?",
                    "alternativas": [
                        ("\"Caro comparado a quê?\"", True),
                        ("\"Se eu der 10% de desconto, fechamos hoje?\"", False),
                        ("\"Mas você viu que o serviço é completo, né?\"", False),
                        ("\"Quer que eu refaça a proposta mais barata?\"", False),
                    ],
                },
                {
                    "enunciado": "Qual é a premissa do LAER sobre as objeções?",
                    "alternativas": [
                        ("Toda objeção de preço se resolve com um desconto bem dado", False),
                        ("A objeção que o cliente diz é sempre exatamente a real", False),
                        ("As objeções devem ser respondidas antes de o cliente terminar", False),
                        ("A objeção que o cliente diz quase nunca é a objeção real", True),
                    ],
                },
                {
                    "enunciado": "Depois de responder à objeção, o que a aula manda fazer?",
                    "alternativas": [
                        ("Confirmar se respondeu à preocupação e, se não, voltar a explorar", True),
                        ("Seguir direto para o fechamento sem perguntar mais nada", False),
                        ("Repetir a mesma resposta com outras palavras para reforçar", False),
                        ("Oferecer um desconto para garantir que a objeção acabou", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, qual é o pior cenário em relação a objeções?",
                    "alternativas": [
                        ("O cliente levantar várias objeções durante a reunião", False),
                        ("O cliente fazer uma objeção de preço logo na abertura", False),
                        ("A objeção escondida, que só aparece depois como silêncio", True),
                        ("O cliente pedir um tempo para avaliar a proposta", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0417"),
            "titulo": "Escuta ativa, benefício e fechamento",
            "resumo": "Como ouvir de verdade, transformar recurso em benefício e conduzir a conversa até um próximo passo com data.",
            "duracao_min": 10,
            "conteudo_md": """\
## Escuta ativa

Ouvir é a habilidade que faz as outras técnicas funcionarem. Três práticas simples:

- **Anote as palavras exatas do cliente.** Não o que você entendeu, mas o que ele disse. Elas vão voltar no resumo, na apresentação e na proposta, e o cliente se reconhece nelas.
- **Peça profundidade.** Depois de uma resposta, "como assim?" ou "me dá um exemplo". A primeira resposta costuma ser genérica; a segunda traz o problema real.
- **Use o silêncio.** Espere cerca de **3 segundos** antes de seguir. O silêncio incomoda, e o cliente tende a completar a resposta com o que tinha de mais importante.

## O resumo de confirmação

Antes de apresentar qualquer solução, devolva ao cliente o que ouviu, nas palavras dele, e peça confirmação: "Deixa eu ver se entendi…". O resumo:

- prova que você ouviu;
- corrige mal-entendidos antes que virem uma proposta errada;
- faz o cliente ouvir o próprio problema de uma vez só, o que aumenta a percepção de urgência.

## Recurso × benefício

Um **recurso** é o que o produto tem; um **benefício** é o que muda na vida do cliente.

- Recurso: "Temos o SOC."
- Benefício: "Você vê todos os vencimentos em tempo real e para de ser pego de surpresa."

Cliente compra benefício. E o benefício mais forte é o que ele mesmo disse que queria no diagnóstico.

## Pequenos fechamentos

Fechar não é um momento único no fim da reunião. A cada bloco da apresentação, uma pergunta de confirmação ("Isso resolveria o que você comentou sobre…?") produz um pequeno "sim". Uma sequência de pequenos "sim" torna o "sim" final natural.

## Tipos de fechamento

- **Direto**: com decisor presente e qualificação forte, pede-se a decisão. "Podemos começar no dia X?"
- **Alternativa**: oferecem-se duas opções de próximo passo, ambas positivas. "Quinta às 10h ou sexta às 15h?"
- **Reunião com o decisor**: quando quem decide não está, o próximo passo é levá-lo à mesa.
- **Passo de baixo risco**: para o cliente inseguro, um compromisso menor (como um diagnóstico) que prova valor.
- **Fechamento futuro**: quando há contrato vigente com outro fornecedor, agenda-se agora a conversa para antes do vencimento.

## O que não é próximo passo

"Vou pensar" e "me manda por e-mail" **não são** próximos passos. Um próximo passo tem **data e hora**, aceitas pelo cliente e marcadas na agenda dele.

## A pergunta final

"Tem alguma coisa que possa impedir a gente de avançar que eu ainda não sei?" Ela revela objeções escondidas enquanto ainda dá para tratá-las.
""",
            "quiz": [
                {
                    "enunciado": "Qual destas é uma forma de benefício, e não de recurso?",
                    "alternativas": [
                        ("Temos o sistema SOC", False),
                        ("Você vê todos os vencimentos em tempo real e para de ser pego de surpresa", True),
                        ("Temos 30 anos de mercado", False),
                        ("Temos médicos do trabalho", False),
                    ],
                },
                {
                    "enunciado": "Qual destas respostas é um próximo passo válido?",
                    "alternativas": [
                        ("\"Vou pensar e te retorno\"", False),
                        ("\"Me manda a proposta por e-mail\"", False),
                        ("\"Quinta às 10h apresentamos a proposta ao diretor\"", True),
                        ("\"Fica à vontade para me ligar\"", False),
                    ],
                },
                {
                    "enunciado": "Para que serve o silêncio de cerca de 3 segundos depois de uma resposta?",
                    "alternativas": [
                        ("Para anotar com calma", False),
                        ("Para o cliente completar a resposta, muitas vezes com o que tinha de mais importante", True),
                        ("Para mostrar autoridade", False),
                        ("Para encerrar o assunto", False),
                    ],
                },
                {
                    "enunciado": "O cliente dá uma resposta genérica. O que a escuta ativa recomenda fazer em seguida?",
                    "alternativas": [
                        ("Pedir profundidade: \"como assim?\" ou \"me dá um exemplo\"", True),
                        ("Passar logo para a próxima pergunta da lista", False),
                        ("Resumir e apresentar a solução em seguida", False),
                        ("Repetir a mesma pergunta com outras palavras", False),
                    ],
                },
                {
                    "enunciado": "Qual destes é um benefício do resumo de confirmação, segundo a aula?",
                    "alternativas": [
                        ("Dispensa a necessidade de anotar as palavras do cliente", False),
                        ("Substitui a pergunta final sobre o que impede de avançar", False),
                        ("Corrige mal-entendidos antes que virem uma proposta errada", True),
                        ("Permite falar do preço antes de apresentar a solução", False),
                    ],
                },
                {
                    "enunciado": "O cliente está inseguro sobre trocar de fornecedor. Qual tipo de fechamento a aula indica?",
                    "alternativas": [
                        ("Fechamento direto, pedindo a decisão ainda na reunião", False),
                        ("Passo de baixo risco, como um diagnóstico que prova valor", True),
                        ("Fechamento futuro, marcado para antes do vencimento", False),
                        ("Reunião com o decisor, mesmo com ele já presente", False),
                    ],
                },
                {
                    "enunciado": "Como funcionam os pequenos fechamentos descritos na aula?",
                    "alternativas": [
                        ("A cada objeção, um pequeno desconto é oferecido ao cliente", False),
                        ("A cada bloco, uma pergunta de confirmação gera um pequeno \"sim\"", True),
                        ("Em cada etapa, o vendedor pede uma assinatura parcial", False),
                        ("Em cada reunião, fecha-se apenas um item do escopo", False),
                    ],
                },
            ],
        },
    ],
}



# ═════════════════════════════════════════════════════════════════════
# MÉTODO 01 — Roteiro de vendas Controller (pilar Método)
# ═════════════════════════════════════════════════════════════════════
# Fonte: "Roteiro de Vendas — Controller Med Seg" (30/09/2026, anexado à
# aula 1). Aqui as técnicas da trilha 04 viram as nossas falas, perguntas,
# regras e métricas. Reforça a medida "roteiro" (elo com o PDI).

METODO_01 = {
    "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0100"),
    "titulo": "Método 01 · Roteiro de vendas Controller",
    "pilar": "metodo",
    "reforca": "roteiro",
    "descricao": (
        "Como a Controller conduz uma reunião comercial do começo ao fim: "
        "preparação, abertura, diagnóstico SPIN, qualificação GPCT, "
        "apresentação reordenada, objeções com LAER, fechamento, follow-up e "
        "o scorecard que mede tudo isso."
    ),
    "prazo_dias": 45,
    "obrigatorios": ("SDR", "EV", "EC"),
    "opcionais": ("EP", "ADM", "Franqueado"),
    "aulas": [
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0111"),
            "titulo": "A reunião Controller em 45 minutos",
            "resumo": "As seis etapas, o tempo de cada uma, o método por trás e a mudança principal: a apresentação não abre mais a reunião.",
            "duracao_min": 8,
            "pdf": "roteiro",
            "conteudo_md": """\
## A regra única

Toda reunião comercial da Controller segue a mesma regra: **diagnosticar antes de apresentar**. O vendedor fala no máximo **30%** do tempo, e a apresentação só entra depois que o cliente disse, **com as próprias palavras**, qual é o problema e quanto ele custa.

As técnicas estão explicadas em profundidade na trilha **04 · Técnicas de venda consultiva**. Esta trilha mostra como elas viram a nossa reunião.

## As seis etapas

1. **Abertura · 5 min.** Rapport e contrato de abertura (Sandler).
2. **Diagnóstico · 15 min.** O cliente verbaliza o problema e o custo (SPIN).
3. **Qualificação · 5 min.** Confirmar prazo, orçamento e decisor (GPCT + BA/C&I).
4. **Solução · 12 min.** Mostrar só o que resolve o que foi dito (apresentação reordenada).
5. **Objeções · 5 min.** Tratar as dúvidas reais (LAER).
6. **Fechamento · 3 min.** Próximo passo com data (compromisso).

Repare na proporção: **20 minutos** de abertura e diagnóstico antes de qualquer slide. Se o diagnóstico render, a apresentação encolhe; nunca o contrário.

## A mudança principal

Antes, a reunião abria com a apresentação institucional: 30 anos, 100 mil vidas, 500 clientes. Agora, **a apresentação deixa de abrir a reunião**. Os slides de credenciais viram **prova**, usados **depois** do diagnóstico, para confirmar que a Controller resolve o que o cliente acabou de dizer.

## O toque Challenger da Controller

O insight do momento: **desde 26/05/2026 está em vigor a redação da NR-01 que exige os fatores de risco psicossociais no PGR**, e a própria norma manda revisar o PGR quando a lei muda. Toda empresa deveria ter revisado; muitas não revisaram. Use como pergunta no diagnóstico, não como sermão.

## O roteiro completo

O documento **Roteiro de Vendas · Controller Med Seg** está em **Material de apoio**. Ele é a referência oficial; estas aulas o explicam etapa por etapa.
""",
            "quiz": [
                {
                    "enunciado": "Quanto tempo da reunião de 45 minutos vem ANTES de qualquer slide?",
                    "alternativas": [
                        ("5 minutos", False),
                        ("20 minutos (abertura e diagnóstico)", True),
                        ("Nenhum: a apresentação abre a reunião", False),
                        ("40 minutos", False),
                    ],
                },
                {
                    "enunciado": "Qual é o papel dos slides de credenciais (30 anos, 100 mil vidas, 500 clientes) no novo roteiro?",
                    "alternativas": [
                        ("Abrir a reunião", False),
                        ("Servir de prova, depois do diagnóstico", True),
                        ("Substituir o diagnóstico", False),
                        ("Não são mais usados", False),
                    ],
                },
                {
                    "enunciado": "No máximo quanto do tempo o vendedor deve falar na reunião?",
                    "alternativas": [
                        ("30%", True),
                        ("50%", False),
                        ("70%", False),
                        ("Não há limite", False),
                    ],
                },
                {
                    "enunciado": "Quanto tempo a etapa de Diagnóstico ocupa na reunião Controller de 45 minutos?",
                    "alternativas": [
                        ("5 minutos", False),
                        ("12 minutos", False),
                        ("15 minutos", True),
                        ("3 minutos", False),
                    ],
                },
                {
                    "enunciado": "Se o diagnóstico render mais que o previsto, o que a aula diz que acontece?",
                    "alternativas": [
                        ("A apresentação encolhe", True),
                        ("A reunião é estendida", False),
                        ("O diagnóstico é interrompido", False),
                        ("As objeções são puladas", False),
                    ],
                },
                {
                    "enunciado": "Qual técnica orienta a etapa de Qualificação no roteiro Controller?",
                    "alternativas": [
                        ("GPCT + BA/C&I", True),
                        ("SPIN", False),
                        ("LAER", False),
                        ("Contrato de abertura (Sandler)", False),
                    ],
                },
                {
                    "enunciado": "Como o roteiro manda usar o insight sobre a NR-01 exigir riscos psicossociais no PGR?",
                    "alternativas": [
                        ("Como abertura da apresentação, antes do rapport", False),
                        ("Como pergunta no diagnóstico, não como sermão", True),
                        ("Como argumento final, só na hora do fechamento", False),
                        ("Como sermão curto, para mostrar autoridade", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0112"),
            "titulo": "Antes da reunião: pesquisa e hipóteses de dor",
            "resumo": "Os 15 minutos de preparação obrigatória, as três hipóteses de dor por perfil e o checklist pré-reunião.",
            "duracao_min": 10,
            "conteudo_md": """\
## A regra

**Nenhuma reunião começa sem 15 minutos de preparação e três hipóteses de dor escritas.** O vendedor chega sabendo mais sobre o risco da empresa do que o próprio interlocutor. É o que permite fazer poucas perguntas de Situação e ir direto ao que importa.

## A pesquisa obrigatória

- **CNAE principal e grau de risco (NR-04).** Onde: cartão CNPJ, e a conta no HIPO já mostra o grau de risco. Por quê: define exigências, exames complementares e preço.
- **Número de funcionários e de unidades.** Onde: LinkedIn, site, cadastro. Por quê: dimensiona as vidas; várias unidades puxam o argumento do atendimento nacional.
- **Segmento e atividades de risco.** Onde: site, Google Maps, vagas abertas. Por quê: altura, ruído, químico, turno noturno, alimentação mudam tudo.
- **Contratações recentes.** Onde: vagas no LinkedIn e no Indeed. Por quê: volume de admissionais; turnover alto é dor de agilidade.
- **Fornecedor atual de SST.** Onde: pergunta do SDR na qualificação. Por quê: prepara a comparação sem falar mal do concorrente.
- **Quem vai estar na reunião.** Onde: agendamento. Por quê: RH, DP, financeiro, dono ou técnico de segurança, cada um tem uma dor.

## As três hipóteses de dor

Escreva três hipóteses antes de entrar. Exemplos por perfil:

- **Rede de alimentação ou varejo com várias lojas**: turnover alto, admissional demorado atrasando o início do funcionário, cada loja com um fornecedor diferente.
- **Indústria ou construção**: PGR e LTCAT desatualizados, exames complementares por risco (audiometria, espirometria), NR-35 (altura) e NR-10 (eletricidade).
- **Escritório ou serviços**: acha que "não tem risco"; não incluiu os riscos psicossociais no PGR; eventos S-2220 e S-2240 do eSocial enviados com erro pelo contador.

As hipóteses não são para afirmar ao cliente: são para escolher **quais perguntas** fazer no diagnóstico.

## Checklist pré-reunião

- CNAE, grau de risco e porte levantados.
- Três hipóteses de dor escritas.
- Participantes e cargo de cada um confirmados.
- Lembrete enviado 24h antes, com a pauta.
- Apresentação aberta no slide 1, mas **não compartilhada** na abertura.
- Registro da oportunidade atualizado no HIPO.

## O papel do SDR

Boa parte da pesquisa nasce na qualificação do SDR: fornecedor atual, número de unidades, quem participa da decisão. O que o SDR descobre e não registra no HIPO, o vendedor vai perguntar de novo, e o cliente percebe.
""",
            "quiz": [
                {
                    "enunciado": "Quanto tempo de preparação é obrigatório antes de toda reunião?",
                    "alternativas": [
                        ("Nenhum, a reunião é para descobrir tudo", False),
                        ("15 minutos, com três hipóteses de dor escritas", True),
                        ("Um dia inteiro", False),
                        ("5 minutos para abrir a apresentação", False),
                    ],
                },
                {
                    "enunciado": "Para um escritório que \"acha que não tem risco\", qual é uma boa hipótese de dor?",
                    "alternativas": [
                        ("NR-35 e trabalho em altura", False),
                        ("PGR sem riscos psicossociais e eventos de SST do eSocial com erro", True),
                        ("Falta de EPI", False),
                        ("Audiometria vencida", False),
                    ],
                },
                {
                    "enunciado": "Na abertura da reunião, a apresentação deve estar:",
                    "alternativas": [
                        ("Compartilhada na tela desde o início", False),
                        ("Aberta no slide 1, mas não compartilhada", True),
                        ("Enviada por e-mail antes da reunião", False),
                        ("Fechada: não é usada", False),
                    ],
                },
                {
                    "enunciado": "A reunião é com uma rede de varejo com várias lojas. Qual hipótese de dor a aula sugere para esse perfil?",
                    "alternativas": [
                        ("LTCAT desatualizado e exames por risco, como audiometria e espirometria", False),
                        ("Acha que não tem risco e o PGR não inclui riscos psicossociais", False),
                        ("Trabalho em altura (NR-35) e eletricidade (NR-10) sem controle", False),
                        ("Turnover alto e admissional demorado atrasando o início do funcionário", True),
                    ],
                },
                {
                    "enunciado": "Para que servem as três hipóteses de dor escritas antes da reunião?",
                    "alternativas": [
                        ("Para afirmar ao cliente qual é o problema dele", False),
                        ("Para montar a proposta antes mesmo da reunião", False),
                        ("Para escolher quais perguntas fazer no diagnóstico", True),
                        ("Para dispensar as perguntas de Problema", False),
                    ],
                },
                {
                    "enunciado": "Segundo a aula, onde pesquisar contratações recentes da empresa e por que isso importa?",
                    "alternativas": [
                        ("Vagas no LinkedIn e no Indeed; mostram volume de admissionais e turnover", True),
                        ("No cartão CNPJ; mostra o grau de risco e os exames complementares", False),
                        ("No Google Maps; mostra as atividades de risco de cada unidade", False),
                        ("No agendamento; mostra quem vai estar presente na reunião", False),
                    ],
                },
                {
                    "enunciado": "Por que o SDR precisa registrar no HIPO o que descobre na qualificação?",
                    "alternativas": [
                        ("Senão o vendedor pergunta de novo, e o cliente percebe", True),
                        ("Para o SDR receber a comissão integral da venda", False),
                        ("Porque o cliente exige ver o registro da conversa", False),
                        ("Para liberar o envio da proposta por e-mail", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0113"),
            "titulo": "Abertura: rapport e contrato de abertura",
            "resumo": "Os 5 primeiros minutos: rapport ligado à pesquisa, a fala padrão do contrato, a credencial em uma frase e a transição.",
            "duracao_min": 8,
            "conteudo_md": """\
## O objetivo

Sair da abertura com **permissão para fazer perguntas** e com o combinado de que **haverá uma decisão sobre o próximo passo no final**.

## Rapport (1 minuto)

Curto e específico, ligado à pesquisa, **nunca ao clima**:

> "Vi que vocês abriram a unidade de Campinas este ano. Como está sendo essa expansão?"

Um rapport que usa a pesquisa mostra preparo e já abre um tema de negócio.

## Contrato de abertura (2 minutos)

A fala padrão:

> "Obrigado pelo tempo, [nome]. Combinamos 45 minutos, ainda está bom para você? A ideia é eu entender primeiro como vocês cuidam hoje da saúde e segurança dos colaboradores. Depois, se fizer sentido, mostro como a Controller pode ajudar. No final, a gente decide junto se vale um próximo passo ou se não é o momento: as duas respostas são boas para mim. Pode ser?"

Repare nos quatro elementos de Sandler: **tempo** (45 minutos), **pauta** (entender primeiro, mostrar depois), **papéis** (eu pergunto, você conta) e **desfecho** (decidimos juntos, e "não" é uma resposta aceita).

## Credencial em uma frase (1 minuto)

Sem slide, só para dar contexto:

> "Rapidamente sobre nós: a Controller nasceu em Guarulhos em 1991, com o Dr. Paulo Dick. Hoje atendemos mais de 500 empresas e mais de 100 mil vidas no Brasil todo, de redes como Bob's e Subway até indústrias. Mas quero entender a realidade de vocês primeiro."

## Transição para o diagnóstico

> "Para eu não te mostrar coisa que não serve, posso te fazer algumas perguntas?"

## Erros a evitar

- Abrir compartilhando a tela.
- Falar da empresa por mais de 1 minuto.
- Pular o combinado sobre o final da reunião.

No scorecard, o item **Contrato de abertura** só ganha nota máxima com tempo, pauta **e** o combinado de decidir o próximo passo no final.
""",
            "quiz": [
                {
                    "enunciado": "Qual destes é um bom rapport, segundo o roteiro?",
                    "alternativas": [
                        ("\"Que calor hoje, né?\"", False),
                        ("\"Vi que vocês abriram a unidade de Campinas este ano. Como está sendo essa expansão?\"", True),
                        ("\"Deixa eu te mostrar nossa apresentação\"", False),
                        ("\"Quanto vocês pagam hoje por exame?\"", False),
                    ],
                },
                {
                    "enunciado": "Quanto tempo, no máximo, o vendedor fala da Controller na abertura?",
                    "alternativas": [
                        ("1 minuto, sem slide", True),
                        ("5 minutos, com a apresentação", False),
                        ("O tempo que for preciso", False),
                        ("Não fala da Controller", False),
                    ],
                },
                {
                    "enunciado": "Para o item Contrato de abertura ganhar nota máxima no scorecard, o vendedor precisa:",
                    "alternativas": [
                        ("Só confirmar o tempo", False),
                        ("Combinar tempo, pauta e que no final se decide o próximo passo", True),
                        ("Apresentar a empresa", False),
                        ("Pedir o orçamento", False),
                    ],
                },
                {
                    "enunciado": "Qual é o objetivo da abertura da reunião, segundo a aula?",
                    "alternativas": [
                        ("Sair com a apresentação institucional já mostrada e entendida pelo cliente", False),
                        ("Sair com o orçamento e o prazo do cliente confirmados logo de início", False),
                        ("Sair com permissão para perguntar e o combinado de decidir o próximo passo no final", True),
                        ("Sair com o cliente convencido de que precisa trocar de fornecedor", False),
                    ],
                },
                {
                    "enunciado": "Qual é a fala de transição da abertura para o diagnóstico?",
                    "alternativas": [
                        ("\"Para eu não te mostrar coisa que não serve, posso te fazer algumas perguntas?\"", True),
                        ("\"Agora deixa eu te mostrar rapidamente quem é a Controller e o que fazemos.\"", False),
                        ("\"Antes de tudo, qual é o orçamento que vocês têm hoje para SST?\"", False),
                        ("\"Vou compartilhar a tela para a gente seguir pela nossa apresentação.\"", False),
                    ],
                },
                {
                    "enunciado": "Na fala padrão do contrato, para que serve o trecho \"as duas respostas são boas para mim\"?",
                    "alternativas": [
                        ("Mostra que o vendedor não tem interesse real na venda", False),
                        ("Deixa claro que um \"não\" é uma resposta aceita no desfecho", True),
                        ("Encerra o rapport com um toque de bom humor", False),
                        ("Define quanto tempo a reunião vai durar", False),
                    ],
                },
                {
                    "enunciado": "Qual destes é um erro a evitar na abertura?",
                    "alternativas": [
                        ("Confirmar se os 45 minutos ainda estão bons", False),
                        ("Fazer um rapport ligado à pesquisa da empresa", False),
                        ("Abrir a reunião compartilhando a tela", True),
                        ("Pedir permissão para fazer algumas perguntas", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0114"),
            "titulo": "Diagnóstico SPIN na Controller",
            "resumo": "As perguntas de Situação, Problema, Implicação e Necessidade para SST, o resumo de confirmação e as técnicas de escuta.",
            "duracao_min": 15,
            "conteudo_md": """\
## Quando o diagnóstico termina

O diagnóstico termina quando o cliente disse, **em voz alta, um problema e o custo dele**. Escolha 2 ou 3 perguntas de cada bloco conforme as suas hipóteses. **Não use o roteiro como interrogatório.**

## S · Situação (no máximo 4, só o que a pesquisa não respondeu)

- Quantos colaboradores vocês têm hoje, e em quantas unidades?
- Quem cuida de medicina e segurança do trabalho hoje: fornecedor externo, equipe interna ou o contador?
- Como funciona hoje quando entra um funcionário novo? Quanto tempo leva do pedido ao ASO na mão?
- Quando foi a última revisão do PGR e do PCMSO?
- Quem envia os eventos de SST do eSocial (S-2210, S-2220, S-2240)?

No scorecard: **até 4 perguntas de Situação antes da primeira de Problema vale 2**; 5 ou 6 vale 1; mais de 6 vale 0.

## P · Problema

- O que te incomoda no modelo atual? Se pudesse mudar uma coisa, o que seria?
- Já aconteceu de um funcionário atrasar o início por causa do exame admissional?
- Você consegue saber hoje, em 5 minutos, quais exames periódicos vencem no próximo mês?
- As unidades fora de Guarulhos/SP são atendidas pelo mesmo padrão? Como você controla isso?
- O PGR de vocês já inclui os riscos psicossociais que a NR-01 passou a exigir?
- Já receberam alguma notificação de divergência no eSocial ou visita de fiscalização?

## I · Implicação (o bloco que mais converte: não pule)

- Quando um admissional atrasa, quanto custa um dia de funcionário parado ou de loja desfalcada?
- Se um fiscal chegasse amanhã e pedisse PGR, PCMSO e ASOs, o que ele encontraria?
- Se houver um acidente ou afastamento e o PGR estiver desatualizado, como isso fica numa ação trabalhista?
- Um laudo (LTCAT) errado afeta a aposentadoria especial e o recolhimento ao INSS. Alguém já conferiu isso?
- Quantas horas por mês o RH gasta cobrando fornecedor, conferindo ASO e corrigindo eSocial? O que essa pessoa poderia fazer nesse tempo?
- Quem responde internamente se der problema: você, o dono, o contador?

## N · Necessidade de solução (o cliente vende para si mesmo)

- Se você tivesse todos os exames, vencimentos e documentos num lugar só, em tempo real, o que mudaria na sua rotina?
- Quanto valeria ter um único parceiro para todas as unidades, com o mesmo padrão?
- Se o eSocial de SST saísse sem você ter que conferir, isso ajudaria?
- O que precisaria acontecer para você dormir tranquilo com relação à fiscalização?

## Resumo de confirmação (obrigatório antes de apresentar)

> "Deixa eu ver se entendi: hoje vocês têm [situação], o que mais pesa é [problema 1] e [problema 2], e isso está custando [implicação nas palavras do cliente]. O ideal seria [necessidade]. É isso? Faltou alguma coisa?"

Só vale nota máxima no scorecard com o **"sim" do cliente**.

## Técnicas de escuta

- Anote as **palavras exatas** do cliente: elas vão para a proposta.
- Depois de uma resposta, pergunte "como assim?" ou "me dá um exemplo".
- **Silêncio de 3 segundos** antes de seguir.

## Onde registrar

As dores, **nas palavras do cliente**, vão para a oportunidade no HIPO no mesmo dia. É delas que nascem o e-mail de resumo e a primeira página da proposta.
""",
            "quiz": [
                {
                    "enunciado": "Quando termina o diagnóstico?",
                    "alternativas": [
                        ("Quando acabam as perguntas da lista", False),
                        ("Quando o cliente disse em voz alta um problema e o custo dele", True),
                        ("Depois de exatamente 15 minutos, aconteça o que acontecer", False),
                        ("Quando o cliente pede o preço", False),
                    ],
                },
                {
                    "enunciado": "\"Se um fiscal chegasse amanhã e pedisse PGR, PCMSO e ASOs, o que ele encontraria?\" é uma pergunta de:",
                    "alternativas": [
                        ("Situação", False),
                        ("Problema", False),
                        ("Implicação", True),
                        ("Necessidade de solução", False),
                    ],
                },
                {
                    "enunciado": "Quantas perguntas de Situação antes da primeira de Problema valem nota 2 no scorecard?",
                    "alternativas": [
                        ("Até 4", True),
                        ("5 a 6", False),
                        ("Mais de 6", False),
                        ("Nenhuma", False),
                    ],
                },
                {
                    "enunciado": "\"Se você tivesse todos os exames, vencimentos e documentos num lugar só, o que mudaria na sua rotina?\" é uma pergunta de:",
                    "alternativas": [
                        ("Necessidade de solução", True),
                        ("Situação", False),
                        ("Problema", False),
                        ("Implicação", False),
                    ],
                },
                {
                    "enunciado": "\"Você consegue saber hoje, em 5 minutos, quais exames periódicos vencem no próximo mês?\" é uma pergunta de:",
                    "alternativas": [
                        ("Situação", False),
                        ("Problema", True),
                        ("Implicação", False),
                        ("Necessidade de solução", False),
                    ],
                },
                {
                    "enunciado": "Quando o resumo de confirmação vale nota máxima no scorecard?",
                    "alternativas": [
                        ("Quando o vendedor o faz depois da apresentação", False),
                        ("Quando o resumo usa os termos técnicos do vendedor", False),
                        ("Quando o cliente confirma o resumo com um \"sim\"", True),
                        ("Quando o resumo é enviado por e-mail após a reunião", False),
                    ],
                },
                {
                    "enunciado": "Onde e quando as dores do cliente devem ser registradas?",
                    "alternativas": [
                        ("Na proposta, só depois que o cliente aprovar o escopo", False),
                        ("No e-mail de resumo, reescritas com as palavras do vendedor", False),
                        ("Na oportunidade no HIPO, no mesmo dia, nas palavras do cliente", True),
                        ("No HIPO, no fim da semana, traduzidas em termos técnicos", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0115"),
            "titulo": "Qualificação GPCT na Controller",
            "resumo": "As perguntas modelo, os sinais verde e vermelho de cada critério e a regra de avanço que decide se há proposta.",
            "duracao_min": 10,
            "conteudo_md": """\
## A regra

**Uma oportunidade só recebe proposta se tiver Prazo, Autoridade e Consequência respondidos.** Sem isso, ela vira **nutrição**, não proposta.

## As perguntas modelo e os sinais

- **G · Metas.** "O que vocês querem alcançar em SST nos próximos 6 meses?" Verde: meta concreta (regularizar, padronizar unidades, reduzir custo). Vermelho: "só cotar".
- **P · Planos.** "O que já tentaram para resolver isso?" Verde: tentou e não funcionou. Vermelho: nunca pensou no assunto.
- **C · Desafios.** "O que impediu de resolver até agora?" Verde: obstáculo que a Controller remove. Vermelho: obstáculo interno sem solução.
- **T · Prazo.** "Quando isso precisa estar resolvido? O contrato atual vence quando?" Verde: data definida ou gatilho (fiscalização, vencimento, nova unidade). Vermelho: "sem pressa".
- **B · Orçamento.** "Quanto vocês investem hoje por mês em SST, somando exames e programas?" Verde: sabe o valor e aceita discutir valor, não só preço. Vermelho: decide só pelo menor preço por exame.
- **A · Autoridade.** "Além de você, quem participa dessa decisão? Como vocês costumam aprovar um fornecedor novo?" Verde: decisor presente ou próxima reunião com ele. Vermelho: decisor inacessível.
- **C · Consequências.** "O que acontece se nada mudar nos próximos 6 meses?" Verde: o cliente nomeia um risco real. Vermelho: "nada".
- **I · Implicações.** "E se der certo, o que isso muda para você e para a empresa?" Verde: benefício pessoal e para o negócio. Vermelho: sem ganho percebido.

## A regra de avanço

- **6 ou mais verdes**: apresentar e propor.
- **4 ou 5 verdes**: apresentar e agendar reunião com o decisor.
- **3 ou menos**: enviar material, marcar retorno e registrar como **nutrição**.

## A dica da ordem

Pergunte **orçamento depois das implicações**. Com o custo do problema na mesa, o investimento é comparado ao **risco**, não ao preço do concorrente.

## No scorecard e no HIPO

O item 7 do scorecard verifica se o cliente respondeu **quando** (prazo), **quem decide** (autoridade) e **o que acontece se nada mudar** (consequência): os três valem 2. O GPCT preenchido vai para a oportunidade no HIPO junto com o decisor.
""",
            "quiz": [
                {
                    "enunciado": "Quais três critérios precisam estar respondidos para uma oportunidade receber proposta?",
                    "alternativas": [
                        ("Metas, Planos e Desafios", False),
                        ("Prazo, Autoridade e Consequência", True),
                        ("Orçamento, Metas e Implicações", False),
                        ("Nenhum, toda reunião gera proposta", False),
                    ],
                },
                {
                    "enunciado": "Uma oportunidade com 4 sinais verdes deve:",
                    "alternativas": [
                        ("Receber proposta imediatamente", False),
                        ("Apresentar e agendar reunião com o decisor", True),
                        ("Ir para nutrição", False),
                        ("Ser descartada", False),
                    ],
                },
                {
                    "enunciado": "\"Só quero cotar\" é sinal de que cor no critério Metas?",
                    "alternativas": [
                        ("Verde", False),
                        ("Vermelho", True),
                        ("Não influencia", False),
                        ("Amarelo", False),
                    ],
                },
                {
                    "enunciado": "Uma oportunidade terminou a qualificação com 3 sinais verdes. O que fazer, segundo a regra de avanço?",
                    "alternativas": [
                        ("Apresentar e propor na mesma reunião", False),
                        ("Apresentar e agendar reunião com o decisor", False),
                        ("Enviar material, marcar retorno e registrar como nutrição", True),
                        ("Enviar a proposta por e-mail no mesmo dia", False),
                    ],
                },
                {
                    "enunciado": "Perguntado \"O que acontece se nada mudar nos próximos 6 meses?\", o cliente responde \"nada\". Como isso se classifica?",
                    "alternativas": [
                        ("Verde no critério Consequências", False),
                        ("Vermelho no critério Prazo", False),
                        ("Vermelho no critério Consequências", True),
                        ("Verde no critério Implicações", False),
                    ],
                },
                {
                    "enunciado": "O cliente diz que escolhe fornecedor só pelo menor preço por exame. Em qual critério isso é sinal vermelho?",
                    "alternativas": [
                        ("Autoridade", False),
                        ("Orçamento", True),
                        ("Metas", False),
                        ("Desafios", False),
                    ],
                },
                {
                    "enunciado": "Qual destes é um sinal verde no critério Prazo?",
                    "alternativas": [
                        ("O cliente diz que está sem pressa para resolver", False),
                        ("O cliente diz que, por enquanto, só quer cotar", False),
                        ("O decisor da compra está inacessível no momento", False),
                        ("O contrato atual vence numa data já definida", True),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0116"),
            "titulo": "Apresentação reordenada: dor, solução e prova",
            "resumo": "A ordem dos slides na reunião, a fala-ponte de cada um e as regras de apresentação.",
            "duracao_min": 10,
            "conteudo_md": """\
## A mudança de ordem

A apresentação institucional (11 slides) segue a ordem "quem somos → o que fazemos → por que nós". Na reunião, a ordem muda para **dor → solução → prova**, e cada slide só aparece se conecta a algo que o cliente disse.

## A ordem na reunião

1. **Slide 10 · O custo de não ter uma gestão especializada.** Abrir por aqui. Apontar na coluna laranja os itens que o cliente citou. Fala-ponte: "Você me falou de [documentos vencidos / retrabalho]. É exatamente o que a gente mais encontra."
2. **Slide 6 · Serviços: Medicina e Segurança.** Mostrar só os itens ligados à dor e citar o resto em uma frase. Fala-ponte: "Para o seu caso, o que resolve é [PGR com psicossociais + periódicos]. Além disso fazemos o ciclo completo."
3. **Slide 7 · Gestão, compliance e bem-estar.** eSocial e indicadores para quem citou retrabalho; campanhas para quem citou afastamentos. Fala-ponte: "Você disse que o RH gasta [X horas] conferindo eSocial. Aqui isso sai da sua mão."
4. **Slides 8 e 9 · Por que escolhem a Controller.** Cada diferencial ligado a uma dor: nacional → várias unidades; SOC e tempo real → falta de controle; consultivo → insegurança jurídica. Fala-ponte: "Lembra que você não consegue ver os vencimentos em 5 minutos? Com o SOC…"
5. **Slides 2, 3 e 5 · +30 anos, +100 mil vidas, +500 clientes.** Prova social. Citar um logo do mesmo segmento do cliente. Fala-ponte: "Atendemos redes como a [marca do mesmo setor], com o mesmo desafio de várias unidades."
6. **Slide 4 · Nossa história.** Opcional: só se o cliente valoriza tradição ou empresa local de Guarulhos.
7. **Slide 11 · Conte conosco.** Deixar na tela durante o fechamento.

## As regras

- **Benefício, não recurso.** Não "temos o SOC"; sim "você vê todos os vencimentos em tempo real e para de ser pego de surpresa".
- **Use as palavras do cliente.** Repita os termos anotados no diagnóstico.
- **Pergunta de confirmação a cada bloco**: "Isso resolveria o que você comentou sobre [X]?" Cada "sim" é um pequeno fechamento.
- **Uma história de cliente** do mesmo porte ou setor: situação antes, o que fizemos, resultado.

## No scorecard

O item 8 (**Apresentação ligada às dores**) vale 2 quando **toda** solução mostrada é ligada a uma dor dita pelo cliente; mostrar o deck inteiro sem ligação vale 0.
""",
            "quiz": [
                {
                    "enunciado": "Por qual slide a apresentação começa na reunião?",
                    "alternativas": [
                        ("Slide 1, a capa", False),
                        ("Slide 10, o custo de não ter uma gestão especializada", True),
                        ("Slide 4, nossa história", False),
                        ("Slide 2, os 30 anos", False),
                    ],
                },
                {
                    "enunciado": "Quando o slide de história (slide 4) deve ser usado?",
                    "alternativas": [
                        ("Sempre, para abrir", False),
                        ("Só se o cliente valoriza tradição ou empresa local de Guarulhos", True),
                        ("Nunca", False),
                        ("Só no fechamento", False),
                    ],
                },
                {
                    "enunciado": "Para cada bloco apresentado, o que o vendedor deve fazer?",
                    "alternativas": [
                        ("Passar rápido para o próximo slide", False),
                        ("Perguntar se aquilo resolve o que o cliente comentou", True),
                        ("Mostrar o preço daquele item", False),
                        ("Pedir para o cliente ler o slide", False),
                    ],
                },
                {
                    "enunciado": "A apresentação institucional segue \"quem somos → o que fazemos → por que nós\". Qual ordem a reunião usa?",
                    "alternativas": [
                        ("Prova → dor → solução", False),
                        ("Solução → prova → dor", False),
                        ("Dor → solução → prova", True),
                        ("Quem somos → dor → preço", False),
                    ],
                },
                {
                    "enunciado": "Como usar o slide 6 (Serviços: Medicina e Segurança) na reunião?",
                    "alternativas": [
                        ("Mostrar todos os serviços em detalhe, um por um, sem pular", False),
                        ("Pular o slide, porque a lista de serviços não interessa", False),
                        ("Deixá-lo na tela durante todo o fechamento da reunião", False),
                        ("Mostrar só os itens ligados à dor e citar o resto em uma frase", True),
                    ],
                },
                {
                    "enunciado": "O cliente tem várias unidades. Qual diferencial dos slides 8 e 9 deve ser ligado a essa dor?",
                    "alternativas": [
                        ("Atendimento nacional", True),
                        ("Consultoria sobre insegurança jurídica", False),
                        ("Campanhas de bem-estar", False),
                        ("História local em Guarulhos", False),
                    ],
                },
                {
                    "enunciado": "Quando o item 8 do scorecard (Apresentação ligada às dores) vale 0?",
                    "alternativas": [
                        ("Quando o deck inteiro é mostrado sem ligação com as dores", True),
                        ("Quando a apresentação começa pelo slide 10", False),
                        ("Quando o slide 4 de história não é usado", False),
                        ("Quando há pergunta de confirmação a cada bloco", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0117"),
            "titulo": "Objeções da Controller com LAER",
            "resumo": "As nove objeções mais comuns, a pergunta para explorar cada uma, a resposta-base e o que fazer com a objeção de preço.",
            "duracao_min": 12,
            "conteudo_md": """\
## O método

Ouvir até o fim → Acolher ("faz sentido você pensar isso") → **Explorar** com uma pergunta → Responder com fato ligado ao diagnóstico. **Nunca responda antes de explorar.**

## As objeções

### "Está caro" / "O outro cobra menos por exame"

- **Explorar:** "Caro comparado a quê? Nessa comparação estão inclusos PGR, eSocial e gestão dos vencimentos?"
- **Responder:** comparar **custo total**, não preço de exame. Retomar a implicação: "Uma autuação ou uma ação trabalhista sem PGR válido custa mais que um ano de contrato."

### "Já temos fornecedor"

- **Explorar:** "E como está sendo? Se pudesse melhorar uma coisa nele, o que seria?"
- **Responder:** **não falar mal do concorrente**. Oferecer auditoria ou diagnóstico da documentação atual como próximo passo de baixo risco.

### "Nosso contador cuida disso"

- **Explorar:** "Ele cuida dos exames e do PGR ou só do envio do eSocial?"
- **Responder:** o contador envia o evento; quem responde pelo **conteúdo técnico** (PGR, PCMSO, LTCAT) é SST. Propor trabalhar **junto** com o contador.

### "Somos pequenos / escritório, não temos risco"

- **Explorar:** "Vocês têm PGR e PCMSO hoje? E o PGR já inclui riscos psicossociais?"
- **Responder:** a NR-01 vale para todas as empresas com empregados CLT; risco psicossocial (estresse, sobrecarga) existe em qualquer escritório. As dispensas para pequenas empresas são estreitas (trilha 03).

### "Preciso pensar"

- **Explorar:** "Claro. O que exatamente você quer avaliar melhor: preço, escopo ou o momento?"
- **Responder:** tratar a objeção real que aparecer. Fechar com data: "Posso te ligar quinta às 10h para a gente decidir?"

### "Manda uma proposta por e-mail"

- **Explorar:** "Mando sim. Para ela vir certa, posso confirmar três pontos?"
- **Responder:** **nunca enviar proposta sem reunião de apresentação marcada.** "Prefiro te apresentar em 20 minutos, para não ficar dúvida."

### "Trocar dá muito trabalho"

- **Explorar:** "O que te preocupa mais na troca?"
- **Responder:** explicar a implantação: a Controller migra histórico e documentos, e o RH não precisa refazer nada.

### "Tenho unidades em outros estados"

- **Explorar:** "Quantas e onde? Como é feito hoje?"
- **Responder:** transformar em vantagem: atendimento nacional com um único parceiro e padrão único (slide 8).

### "O dono/diretor precisa aprovar"

- **Explorar:** "O que ele vai querer ver para aprovar? Como a gente te ajuda a levar isso?"
- **Responder:** propor reunião de 20 minutos com o decisor, com você presente. Preparar um resumo de uma página com dor, custo e solução.

## A objeção de preço que persiste

Antes de dar desconto, **reduza o escopo**: "Se o foco agora é regularizar, podemos começar por PGR e PCMSO." Desconto, quando houver, **sempre em troca de algo**: prazo de contrato maior, pagamento antecipado ou indicação.

## No scorecard

O item 9 (**Objeções com LAER**) vale 2 quando há pergunta de exploração **antes** da resposta; rebater direto vale 0.
""",
            "quiz": [
                {
                    "enunciado": "O cliente diz \"Nosso contador cuida disso\". Qual é a pergunta para explorar?",
                    "alternativas": [
                        ("\"Quanto ele cobra?\"", False),
                        ("\"Ele cuida dos exames e do PGR ou só do envio do eSocial?\"", True),
                        ("\"Posso falar com ele?\"", False),
                        ("\"Por que vocês não trocam de contador?\"", False),
                    ],
                },
                {
                    "enunciado": "Diante de uma objeção de preço que persiste, o que fazer antes de dar desconto?",
                    "alternativas": [
                        ("Encerrar a reunião", False),
                        ("Reduzir o escopo, começando pelo essencial (por exemplo, PGR e PCMSO)", True),
                        ("Dar o desconto máximo de uma vez", False),
                        ("Falar mal do concorrente", False),
                    ],
                },
                {
                    "enunciado": "O cliente pede \"manda a proposta por e-mail\". Qual é a regra?",
                    "alternativas": [
                        ("Enviar na hora para não perder o cliente", False),
                        ("Nunca enviar proposta sem reunião de apresentação marcada", True),
                        ("Enviar só a tabela de preços", False),
                        ("Pedir para ele pedir de novo depois", False),
                    ],
                },
                {
                    "enunciado": "O cliente diz: \"Já temos fornecedor.\" Depois de explorar, qual resposta a aula indica?",
                    "alternativas": [
                        ("Sem falar mal do concorrente, oferecer uma auditoria da documentação atual", True),
                        ("Mostrar os erros que o concorrente costuma cometer com outros clientes", False),
                        ("Oferecer um desconto que cubra a eventual multa de troca de fornecedor", False),
                        ("Encerrar a conversa e marcar um novo contato só para daqui a um ano", False),
                    ],
                },
                {
                    "enunciado": "Se for preciso dar desconto, como ele deve ser concedido?",
                    "alternativas": [
                        ("Logo na primeira objeção de preço, para mostrar boa vontade", False),
                        ("Sempre em troca de algo: prazo maior, pagamento antecipado ou indicação", True),
                        ("Sem contrapartida, desde que o cliente feche no mesmo dia", False),
                        ("Apenas por e-mail, depois que a proposta já tiver sido enviada", False),
                    ],
                },
                {
                    "enunciado": "O cliente diz: \"Trocar dá muito trabalho.\" Qual resposta a aula indica?",
                    "alternativas": [
                        ("Dizer que o trabalho da troca é pequeno e seguir para o próximo assunto", False),
                        ("Explicar que a Controller migra histórico e documentos e o RH não refaz nada", True),
                        ("Oferecer um desconto para compensar o trabalho que a troca vai dar", False),
                        ("Sugerir que ele espere o contrato atual vencer para pensar no assunto", False),
                    ],
                },
                {
                    "enunciado": "O cliente diz: \"O diretor precisa aprovar.\" Qual é a resposta indicada?",
                    "alternativas": [
                        ("Mandar a proposta por e-mail para o cliente repassar ao diretor quando puder", False),
                        ("Propor 20 minutos com o decisor, com você presente, e levar um resumo de uma página", True),
                        ("Pedir o telefone do diretor e ligar para ele sem a participação do cliente", False),
                        ("Oferecer um desconto para facilitar a aprovação do diretor na mesma semana", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0118"),
            "titulo": "Fechamento: próximo passo com data",
            "resumo": "O resumo de valor, o tipo de fechamento para cada situação, o convite na hora e a pergunta final.",
            "duracao_min": 8,
            "conteudo_md": """\
## A regra

**Nenhuma reunião termina sem próximo passo com data e hora na agenda do cliente.** "Vou pensar" e "me manda por e-mail" não são próximos passos.

## 1. Resumo de valor (retomando o contrato de abertura)

> "Você me contou que [dor 1] e [dor 2] estão custando [implicação]. Vimos que com [solução] isso se resolve. Combinamos no início que decidiríamos juntos o próximo passo. Faz sentido seguirmos?"

## 2. O fechamento conforme a qualificação

- **Decisor presente, 6 ou mais verdes → fechamento direto.** "Podemos começar a implantação no dia [X]? Preciso só dos dados para o contrato."
- **Decisor presente, mas quer ver números → alternativa.** "Te apresento a proposta na quinta às 10h ou na sexta às 15h?"
- **Decisor ausente → reunião com o decisor.** "Vamos marcar 20 minutos com o [diretor] esta semana? Eu levo a proposta pronta."
- **Cliente inseguro sobre trocar → passo de baixo risco.** "Que tal começarmos com um diagnóstico da documentação atual? Em [X] dias você sabe exatamente onde está exposto."
- **Contrato atual vigente → fechamento futuro.** "Seu contrato vence em [mês]. Vamos marcar agora a revisão para 60 dias antes?"

## 3. Confirmação

Mande o **convite de calendário ainda na reunião**, com pauta e participantes. Confirme quem mais precisa estar.

## 4. A pergunta final

> "Tem alguma coisa que possa impedir a gente de avançar que eu ainda não sei?"

Ela revela objeções ocultas enquanto ainda dá para tratá-las.

## No HIPO

O próximo passo combinado vira a **próxima tarefa** da oportunidade, com a data e a hora que o cliente aceitou. É a regra da casa: oportunidade viva nunca fica sem próximo passo aberto.

## No scorecard

O item 10 (**Próximo passo com data**) vale 2 com **dia e hora** falados e aceitos pelo cliente; próximo passo sem data vale 1.
""",
            "quiz": [
                {
                    "enunciado": "O cliente tem contrato vigente com outro fornecedor até março. Qual fechamento usar?",
                    "alternativas": [
                        ("Fechamento direto", False),
                        ("Fechamento futuro: marcar agora a revisão para 60 dias antes do vencimento", True),
                        ("Desistir da oportunidade", False),
                        ("Enviar a proposta por e-mail", False),
                    ],
                },
                {
                    "enunciado": "Quando o convite de calendário do próximo passo deve ser enviado?",
                    "alternativas": [
                        ("Ainda na reunião", True),
                        ("No dia seguinte", False),
                        ("Só depois da proposta aceita", False),
                        ("Quando o cliente pedir", False),
                    ],
                },
                {
                    "enunciado": "Qual é o objetivo da pergunta final \"Tem alguma coisa que possa impedir a gente de avançar que eu ainda não sei?\"",
                    "alternativas": [
                        ("Encerrar a reunião com educação", False),
                        ("Revelar objeções ocultas enquanto ainda dá para tratá-las", True),
                        ("Pedir desconto", False),
                        ("Confirmar o e-mail do cliente", False),
                    ],
                },
                {
                    "enunciado": "O decisor está presente, mas quer ver números antes de decidir. Qual fechamento usar?",
                    "alternativas": [
                        ("Direto: \"Podemos começar a implantação no dia X?\"", False),
                        ("Alternativa: \"Te apresento a proposta na quinta às 10h ou na sexta às 15h?\"", True),
                        ("Baixo risco: \"Que tal começarmos com um diagnóstico da documentação?\"", False),
                        ("Futuro: \"Vamos marcar a revisão para 60 dias antes do vencimento?\"", False),
                    ],
                },
                {
                    "enunciado": "O que o resumo de valor, no início do fechamento, retoma do começo da reunião?",
                    "alternativas": [
                        ("A história da Controller desde 1991, para reforçar a credibilidade", False),
                        ("O contrato de abertura: o combinado de decidir juntos o próximo passo", True),
                        ("A lista completa de serviços do slide 6, para não esquecer nada", False),
                        ("As perguntas de Situação, para confirmar os dados da empresa", False),
                    ],
                },
                {
                    "enunciado": "No HIPO, o que acontece com o próximo passo combinado na reunião?",
                    "alternativas": [
                        ("Vira a próxima tarefa da oportunidade, com a data e a hora aceitas", True),
                        ("Fica anotado só no e-mail de resumo enviado ao cliente", False),
                        ("É registrado como observação, sem data definida", False),
                        ("Só é lançado depois que a proposta for assinada", False),
                    ],
                },
                {
                    "enunciado": "Qual nota o item 10 do scorecard dá a um próximo passo combinado, mas sem data?",
                    "alternativas": [
                        ("0", False),
                        ("2", False),
                        ("Não é avaliado", False),
                        ("1", True),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0119"),
            "titulo": "Pós-reunião, proposta e follow-up",
            "resumo": "O que fazer nas 2 horas seguintes, a estrutura da proposta em 48h e a cadência quando o cliente some.",
            "duracao_min": 8,
            "conteudo_md": """\
## A regra

O registro e o resumo saem **no mesmo dia**; a proposta sai em **até 48h** e é sempre **apresentada**, nunca só enviada.

## Em até 2 horas

- **Registrar no HIPO**: o desfecho da reunião, as dores **nas palavras do cliente**, o GPCT preenchido, o decisor e o próximo passo com data (como próxima tarefa).
- **Enviar o e-mail de resumo ao cliente**:

> "[Nome], obrigado pela conversa. Resumindo o que entendi: hoje [situação]; os pontos críticos são [dor 1] e [dor 2]; o impacto é [implicação]. Combinamos [próximo passo] em [data/hora]. Se algo ficou diferente do que você pensou, me avise."

## A proposta (até 48h)

A **primeira página repete o diagnóstico do cliente**, antes de qualquer preço. A estrutura:

1. O que ouvimos.
2. O que propomos, item por item ligado à dor.
3. Implantação em etapas.
4. Investimento.
5. Próximos passos.

## Quando o cliente some: a cadência

- **D+2 · WhatsApp**: confirmar recebimento da proposta e o horário combinado.
- **D+5 · Ligação**: tirar dúvidas; perguntar se surgiu algo novo.
- **D+9 · E-mail**: conteúdo útil, como um checklist da NR-01 psicossocial ou dos vencimentos do eSocial.
- **D+14 · Ligação**: retomar a implicação do diagnóstico.
- **D+21 · WhatsApp**: mensagem de encerramento: "Entendo que não é prioridade agora. Posso retomar em [mês]?"

A mensagem de encerramento costuma gerar resposta. Sem retorno, a oportunidade vai para **nutrição com data de retomada**, e nunca fica aberta indefinidamente.

## No HIPO

Cada toque da cadência é uma tarefa, e cada tarefa concluída pede a próxima. Assim a cadência anda sozinha, e o gestor enxerga no funil quem está em follow-up e há quanto tempo.
""",
            "quiz": [
                {
                    "enunciado": "Em quanto tempo o registro no HIPO e o e-mail de resumo devem sair?",
                    "alternativas": [
                        ("Em até 2 horas", True),
                        ("Em até 1 semana", False),
                        ("Só quando a proposta for enviada", False),
                        ("No fim do mês", False),
                    ],
                },
                {
                    "enunciado": "O que vem na primeira página da proposta?",
                    "alternativas": [
                        ("A tabela de preços", False),
                        ("O diagnóstico do cliente: o que ouvimos", True),
                        ("A história da Controller", False),
                        ("O contrato para assinatura", False),
                    ],
                },
                {
                    "enunciado": "O que acontece com a oportunidade se o cliente não responder nem à mensagem de encerramento do D+21?",
                    "alternativas": [
                        ("Fica aberta até ele responder", False),
                        ("Vai para nutrição com data de retomada", True),
                        ("É apagada do HIPO", False),
                        ("O vendedor recomeça a cadência do zero", False),
                    ],
                },
                {
                    "enunciado": "Em quanto tempo a proposta deve sair, e como ela chega ao cliente?",
                    "alternativas": [
                        ("Em até 2 horas, enviada por e-mail", False),
                        ("Em até uma semana, por WhatsApp", False),
                        ("Em até 48 horas, sempre apresentada", True),
                        ("No mesmo dia, só enviada por e-mail", False),
                    ],
                },
                {
                    "enunciado": "Na cadência de follow-up, o que acontece no D+9?",
                    "alternativas": [
                        ("WhatsApp para confirmar o recebimento da proposta e o horário", False),
                        ("E-mail com conteúdo útil, como um checklist da NR-01 psicossocial", True),
                        ("Ligação para retomar a implicação levantada no diagnóstico", False),
                        ("Mensagem de encerramento perguntando quando pode retomar", False),
                    ],
                },
                {
                    "enunciado": "Na estrutura da proposta, em que ponto entra o Investimento?",
                    "alternativas": [
                        ("Na primeira página, antes do diagnóstico do cliente", False),
                        ("Depois do que ouvimos, do que propomos e da implantação", True),
                        ("Logo depois do que ouvimos, antes do que propomos", False),
                        ("No final, depois dos próximos passos combinados", False),
                    ],
                },
                {
                    "enunciado": "Como o HIPO faz a cadência de follow-up andar sozinha?",
                    "alternativas": [
                        ("Cada toque é uma tarefa, e cada tarefa concluída pede a próxima", True),
                        ("Envia as mensagens ao cliente automaticamente, sem o vendedor", False),
                        ("Encerra a oportunidade no D+21 sem nenhum registro de motivo", False),
                        ("Agenda todos os toques de uma vez no calendário do cliente", False),
                    ],
                },
            ],
        },
        {
            "id": UUID("7c1d0f4e-5a01-4c0e-9b11-0000000b0120"),
            "titulo": "Scorecard, métricas e rotina de melhoria",
            "resumo": "Como cada reunião é avaliada pela transcrição, os 10 itens do scorecard, as métricas de funil e a rotina de implantação do roteiro.",
            "duracao_min": 10,
            "conteudo_md": """\
## O roteiro só vira padrão se for medido

Toda reunião é avaliada pela sua **transcrição**, com o scorecard abaixo (0 a 2 por item, máximo de 20 pontos).

## Como funciona

1. A reunião acontece pelo **link do Meet do evento**, com o vendedor logado na conta **@controllermedseg.com**. Sem isso não há transcrição.
2. Com a transcrição pronta, o HIPO a envia à IA, que preenche o scorecard item a item com a nota e o **trecho literal** que a justifica. O **gestor revisa** e pode ajustar qualquer nota; a avaliação é sugestão até ele validar.
3. O vendedor recebe a nota com dois trechos da transcrição: **um que funcionou e um para melhorar**.
4. Reunião presencial sem transcrição é avaliada pelo registro no HIPO e marcada como "sem transcrição", para não distorcer a média.

## O scorecard (0 / 1 / 2)

1. **Preparação**: cita dado da empresa que pesquisou. Nenhum / 1 dado / rapport e perguntas usam a pesquisa.
2. **Contrato de abertura**: tempo, pauta e o combinado do final. Não fez / sem o combinado / completo.
3. **Perguntas de Situação** antes da primeira de Problema: mais de 6 / 5 a 6 / até 4.
4. **Perguntas de Problema**: nenhuma / 1 / 2 ou mais.
5. **Perguntas de Implicação**: nenhuma / 1 / 2 ou mais.
6. **Resumo de confirmação**: não fez / sem validação / cliente confirmou.
7. **GPCT: prazo, decisor e consequência**: nenhum / 1 ou 2 / os 3.
8. **Apresentação ligada às dores**: deck inteiro sem ligação / parcial / toda solução ligada a uma dor.
9. **Objeções com LAER**: rebateu direto / explorou pouco / explorou antes de responder.
10. **Próximo passo com data**: nenhum / sem data / data e hora combinadas.

Fora da nota, como indicador: **tempo de fala do vendedor**, com meta de **até 40%** da transcrição.

## A meta

**Média de 15 ou mais por vendedor em 60 dias.** Com todas as reuniões avaliadas, dá para comparar o scorecard das reuniões que avançaram com o das que morreram e descobrir quais itens mais pesam na conversão. Os itens mais fracos do mês viram o tema do treinamento semanal.

## As métricas de funil (no HIPO, por vendedor e por mês)

- Reuniões realizadas ÷ agendadas (comparecimento).
- Reuniões com próximo passo marcado ÷ realizadas.
- Propostas apresentadas ÷ reuniões.
- Fechamentos ÷ propostas apresentadas.
- Ciclo médio de venda (dias do 1º contato ao fechamento).
- Ticket médio e número de vidas por contrato.
- Motivos de perda (preço, timing, concorrente, sem decisor).

## A rotina de implantação

1. **Semana 1**: leitura do roteiro e role-play da abertura e do SPIN.
2. **Semana 2**: role-play de objeções e fechamento, com o gestor como cliente.
3. **Semana 3 em diante**: scorecard em toda reunião e, uma vez por semana, leitura em grupo de trechos de transcrições (os melhores e os que perderam a venda).
4. **A cada 90 dias**: revisão do roteiro com as perguntas e respostas a objeções que mais aparecem nas reuniões que fecharam.

## O elo com a Universidade

A nota de roteiro validada é um dos componentes do pilar **Método** na avaliação mensal. Quando ela fica baixa, o PDI aponta de volta para esta trilha.
""",
            "quiz": [
                {
                    "enunciado": "Sem o que não há transcrição da reunião?",
                    "alternativas": [
                        ("Sem o vendedor logado na conta @controllermedseg.com, usando o link do Meet do evento", True),
                        ("Sem a apresentação compartilhada", False),
                        ("Sem o cliente autorizar por escrito", False),
                        ("Sem o gestor presente", False),
                    ],
                },
                {
                    "enunciado": "Qual é a meta de nota média no scorecard por vendedor?",
                    "alternativas": [
                        ("10 ou mais em 30 dias", False),
                        ("15 ou mais em 60 dias", True),
                        ("20 em todas as reuniões", False),
                        ("Não há meta", False),
                    ],
                },
                {
                    "enunciado": "Qual é a meta de tempo de fala do vendedor medida na transcrição?",
                    "alternativas": [
                        ("Até 40%", True),
                        ("Pelo menos 60%", False),
                        ("Exatamente 50%", False),
                        ("Não é medido", False),
                    ],
                },
                {
                    "enunciado": "Como é tratada uma reunião presencial que não tem transcrição?",
                    "alternativas": [
                        ("Recebe nota zero em todos os itens do scorecard", False),
                        ("É avaliada pelo registro no HIPO e marcada como \"sem transcrição\"", True),
                        ("Não é registrada e fica fora do HIPO", False),
                        ("Recebe automaticamente a nota média do vendedor", False),
                    ],
                },
                {
                    "enunciado": "Qual é o papel do gestor na avaliação feita pela IA?",
                    "alternativas": [
                        ("Nenhum: a nota da IA é final e vai direto para o vendedor", False),
                        ("Só lê a avaliação quando o vendedor contesta alguma nota", False),
                        ("Preenche o scorecard do zero, sem usar a sugestão da IA", False),
                        ("Revisa e pode ajustar as notas; a avaliação é sugestão até ele validar", True),
                    ],
                },
                {
                    "enunciado": "Além da nota, o que o vendedor recebe da avaliação de cada reunião?",
                    "alternativas": [
                        ("A transcrição inteira, sem nenhum destaque do gestor", False),
                        ("Uma lista com todas as falas que ele deveria ter evitado", False),
                        ("Dois trechos da transcrição: um que funcionou e um para melhorar", True),
                        ("A comparação com as notas de todos os outros vendedores", False),
                    ],
                },
                {
                    "enunciado": "O que acontece com os itens mais fracos do scorecard no mês?",
                    "alternativas": [
                        ("São retirados do scorecard", False),
                        ("Viram o tema do treinamento semanal", True),
                        ("Reduzem a comissão do vendedor", False),
                        ("Ficam para a revisão de 90 dias", False),
                    ],
                },
            ],
        },
    ],
}


# Trilhas de uso do HIPO por função (entrega 035), com tour guiado.
from scripts.uc_conteudo_hipo import TRILHAS_HIPO  # noqa: E402
# Roteiros do SDR e do EC (Método 02 e 03, entrega 036).
from scripts.uc_conteudo_roteiros import TRILHAS_ROTEIROS  # noqa: E402
# Primeira trilha do pilar Energia (entrega 037).
from scripts.uc_conteudo_energia import TRILHAS_ENERGIA  # noqa: E402
# Técnicas do SDR na prática (Método 04, entrega 042).
from scripts.uc_conteudo_tecnicas_sdr import TRILHAS_TECNICAS_SDR  # noqa: E402

TRILHAS: list[dict] = [
    TRILHA_01, TRILHA_02, TRILHA_03, TRILHA_04, METODO_01,
    *TRILHAS_HIPO, *TRILHAS_ROTEIROS, *TRILHAS_ENERGIA, *TRILHAS_TECNICAS_SDR,
]
