"""
HIPO — UC: conteúdo das três primeiras trilhas da Universidade Corporativa.

  01 · Boas-vindas à Controller    (prazo 10 dias)
  02 · Conceitos gerais de SST     (prazo 20 dias)
  03 · Produto e normas            (prazo 30 dias)

Todas no pilar Técnica, obrigatórias para SDR, EV, EC, EP e ADM e abertas
(sem obrigação) ao Franqueado, para a gestão conseguir fazer e revisar.

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

As trilhas obrigatórias do seu cargo formam o **Manual da função**, com prazo. A tela da Universidade sempre mostra a sua **próxima aula**.

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


TRILHAS: list[dict] = [TRILHA_01, TRILHA_02, TRILHA_03]
