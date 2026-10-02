"""
HIPO — UC: carga da trilha de Técnica "Normas Regulamentadoras: NR-01 e NR-04".

Primeiro conteúdo da Universidade Corporativa. Textos escritos a partir das
normas entregues pelo Tulio em 01/10/2026:

  * NR-01 — Disposições Gerais e Gerenciamento de Riscos Ocupacionais,
    com a redação da Portaria MTE nº 1.419/2024 (item 1.5 e Anexo I), em
    vigor desde 26/05/2026 pela Portaria MTE nº 765/2025;
  * NR-04 — SESMT, redação da Portaria MTP nº 2.318/2022 (alterada pela
    nº 4.219/2022).

As aulas RESUMEM a norma para quem vende serviço de medicina e segurança
do trabalho. O texto legal é o PDF anexado às aulas 1 e 6, e é ele que
vale quando a dúvida for de detalhe.

O QUIZ de cada aula já está escrito aqui, mas só é carregado na UC-2
(quando as tabelas de quiz existirem). Ficam juntos para não haver duas
fontes do mesmo conteúdo.

IDEMPOTENTE. Ids fixos: rodar de novo não duplica nada. Sem `--atualizar`,
trilha que já existe não é tocada (a gestão pode ter editado pelo estúdio).
Com `--atualizar`, reescreve título, resumo, texto e duração das aulas, sem
subir versão — correção de redação não reabre a aula para quem concluiu.

USO (na EC2, como hipo, de dentro de /home/hipo/app/api):
  python -m scripts.semear_uc_nr --simular
  python -m scripts.semear_uc_nr --pdf-nr01 /tmp/nr-01.pdf --pdf-nr04 /tmp/nr-04.pdf

Sem os PDFs, a trilha entra sem material de apoio; dá para anexar depois
pelo estúdio. DATABASE_URL não tem o safeguard do conftest: o script mostra
o host mascarado e pede confirmação antes de gravar.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from uuid import UUID

TRILHA_ID = UUID("7c1d0f4e-5a01-4c0e-9b11-0000000a0101")

TRILHA = {
    "id": TRILHA_ID,
    "titulo": "Normas Regulamentadoras: NR-01 e NR-04",
    "pilar": "tecnica",
    "descricao": (
        "A base legal do que a MedSeg vende: o gerenciamento de riscos (GRO/PGR), "
        "os riscos psicossociais, os treinamentos, o tratamento das pequenas "
        "empresas e o SESMT. Quem conversa com cliente precisa dominar."
    ),
    # Manual da função: todo cargo que fala com cliente ou atende cliente.
    "cargos": [
        {"cargo": c, "obrigatoria": True, "prazo_dias": 30}
        for c in ("SDR", "EV", "EC", "EP", "ADM")
    ],
}

AULAS: list[dict] = [
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

PDFS = {
    "nr01": "NR-01 (texto oficial, atualizado 2025).pdf",
    "nr04": "NR-04 (texto oficial, atualizado 2023).pdf",
}


# ── Conferência (também usada pelos testes) ──────────────────────────

def conferir() -> list[str]:
    """Problemas de forma no conteúdo. Lista vazia = pronto para carregar."""
    erros: list[str] = []
    ids = [a["id"] for a in AULAS]
    if len(ids) != len(set(ids)):
        erros.append("id de aula repetido")
    for i, a in enumerate(AULAS, start=1):
        rot = f"aula {i}"
        if not a["titulo"].strip() or len(a["titulo"]) > 160:
            erros.append(f"{rot}: título vazio ou acima de 160")
        if not (1 <= a["duracao_min"] <= 600):
            erros.append(f"{rot}: duração fora de 1..600")
        if not a["conteudo_md"].lstrip().startswith("## "):
            erros.append(f"{rot}: o texto deve abrir com um título de seção")
        if re.search(r"(?m)^# ", a["conteudo_md"]):
            erros.append(f"{rot}: '# ' de nível 1 é o título da aula, não do texto")
        if a.get("pdf") and a["pdf"] not in PDFS:
            erros.append(f"{rot}: pdf desconhecido")
        for j, q in enumerate(a.get("quiz", []), start=1):
            certas = sum(1 for _, c in q["alternativas"] if c)
            if certas != 1:
                erros.append(f"{rot}, pergunta {j}: precisa de exatamente 1 correta")
            if len(q["alternativas"]) < 3:
                erros.append(f"{rot}, pergunta {j}: menos de 3 alternativas")
    return erros


# ── Carga ────────────────────────────────────────────────────────────

def _mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url)


async def _carregar(conn, pdfs: dict[str, Path], atualizar: bool, simular: bool) -> None:
    from services import uc_material

    existe = await conn.fetchval("SELECT 1 FROM uc_trilhas WHERE id = $1", TRILHA_ID)
    if existe and not atualizar:
        print("Trilha já existe. Nada a fazer (use --atualizar para reescrever os textos).")
    elif simular:
        print(("Atualizaria" if existe else "Criaria") + f" a trilha e {len(AULAS)} aulas.")
    else:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO uc_trilhas (id, titulo, descricao, pilar, status)
                VALUES ($1, $2, $3, $4, 'rascunho')
                ON CONFLICT (id) DO UPDATE
                   SET titulo = EXCLUDED.titulo, descricao = EXCLUDED.descricao,
                       atualizado_em = NOW()
                """,
                TRILHA_ID, TRILHA["titulo"], TRILHA["descricao"], TRILHA["pilar"],
            )
            for ordem, a in enumerate(AULAS, start=1):
                await conn.execute(
                    """
                    INSERT INTO uc_aulas (id, trilha_id, ordem, titulo, resumo,
                                          conteudo_md, duracao_min, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'publicada')
                    ON CONFLICT (id) DO UPDATE
                       SET titulo = EXCLUDED.titulo, resumo = EXCLUDED.resumo,
                           conteudo_md = EXCLUDED.conteudo_md,
                           duracao_min = EXCLUDED.duracao_min, atualizado_em = NOW()
                    """,
                    a["id"], TRILHA_ID, ordem, a["titulo"], a["resumo"],
                    a["conteudo_md"], a["duracao_min"],
                )
            if not existe:
                for c in TRILHA["cargos"]:
                    await conn.execute(
                        """
                        INSERT INTO uc_trilha_cargos (trilha_id, cargo, obrigatoria, prazo_dias)
                        VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
                        """,
                        TRILHA_ID, c["cargo"], c["obrigatoria"], c["prazo_dias"],
                    )
                await conn.execute(
                    "UPDATE uc_trilhas SET status = 'publicada' WHERE id = $1", TRILHA_ID,
                )
        print(("Trilha atualizada" if existe else "Trilha criada e publicada") + f": {len(AULAS)} aulas.")

    for a in AULAS:
        chave_pdf = a.get("pdf")
        if not chave_pdf or chave_pdf not in pdfs:
            continue
        nome = uc_material.nome_seguro(PDFS[chave_pdf], ".pdf")
        ja = await conn.fetchval(
            "SELECT 1 FROM uc_materiais WHERE aula_id = $1 AND nome_original = $2",
            a["id"], nome,
        )
        if ja:
            print(f"  material já anexado: {nome}")
            continue
        if simular:
            print(f"  anexaria {pdfs[chave_pdf]} em '{a['titulo']}'")
            continue
        problemas = uc_material.problemas()
        if problemas:
            print("  S3 indisponível, PDF não anexado: " + "; ".join(problemas))
            continue
        conteudo = pdfs[chave_pdf].read_bytes()
        uc_material.validar_tamanho(len(conteudo))
        material_id = await conn.fetchval("SELECT gen_random_uuid()")
        chave = uc_material.chave_do_objeto(a["id"], material_id, ".pdf")
        uc_material.subir(chave, conteudo, "application/pdf")
        await conn.execute(
            """
            INSERT INTO uc_materiais (id, aula_id, chave_s3, nome_original, tipo_mime, bytes)
            VALUES ($1, $2, $3, $4, 'application/pdf', $5)
            """,
            material_id, a["id"], chave, nome, len(conteudo),
        )
        print(f"  anexado: {nome} ({len(conteudo) // 1024} KB)")


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--pdf-nr01", type=Path)
    ap.add_argument("--pdf-nr04", type=Path)
    ap.add_argument("--atualizar", action="store_true")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--sim", action="store_true", help="não pergunta (para scripts)")
    args = ap.parse_args(argv)

    erros = conferir()
    if erros:
        print("Conteúdo com problema:\n  " + "\n  ".join(erros))
        return 1

    pdfs: dict[str, Path] = {}
    for chave, caminho in (("nr01", args.pdf_nr01), ("nr04", args.pdf_nr04)):
        if caminho is None:
            continue
        if not caminho.is_file():
            print(f"PDF não encontrado: {caminho}")
            return 1
        pdfs[chave] = caminho

    import asyncpg
    from config import settings

    print(f"Banco: {_mascarar(settings.DATABASE_URL)}")
    if not args.simular and not args.sim:
        if input("Gravar nesse banco? [s/N] ").strip().lower() != "s":
            print("Cancelado.")
            return 0

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        await _carregar(conn, pdfs, args.atualizar, args.simular)
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
