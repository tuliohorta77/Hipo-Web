"""
Gera api/templates/contrato_modelo.docx (entrega 053).

    python -m scripts.gerar_modelo_contrato            # grava o modelo
    python -m scripts.gerar_modelo_contrato --saida x.docx

O texto e o da minuta que a Controller MedSeg ja usa (contrato da Porto
Pisos Elevados, assinado pela Autentique em 08/10/2026), com os trechos que
mudam de cliente para cliente trocados por CAMPOS ({{NOME}}).

DEPOIS DE GERADO, O MODELO E DO TULIO. Ajuste de clausula se faz abrindo o
.docx no Word e salvando: o preenchimento (services/contrato_render.py)
aguenta campo quebrado em pedacos pelo Word, e a suite falha se o modelo
passar a ter um campo que o codigo nao conhece. Este script so existe para
recriar o arquivo do zero (arte nova, perda do arquivo).

Precisa de python-docx, que NAO esta no requirements.txt de proposito: e
ferramenta de quem edita o modelo, nao dependencia da API. O preenchimento
em producao abre o .docx como zip e mexe no XML com lxml (que ja vem com o
python-pptx).

    pip install python-docx==1.1.2

CAMPOS
  Simples (trocados no lugar, mantendo a formatacao do trecho):
    {{CONTRATANTE_RAZAO_SOCIAL}}  {{CONTRATANTE_ENDERECO}}  {{CONTRATANTE_CNPJ}}
    {{CONTRATANTE_DEMAIS}} (", e demais CNPJs ... ANEXO 1", ou vazio)
    {{DIA_VENCIMENTO}}  {{INICIO_VIGENCIA}}  {{CIDADE}}  {{DATA_EXTENSO}}
  De lista (o paragrafo inteiro e repetido, um por item; lista vazia apaga
  o paragrafo). O campo precisa estar SOZINHO no paragrafo:
    {{SERVICO_EXTRA}}  itens 2.7, 2.8... da Clausula 2 (055)
    {{PRECO_LINHA}}    Clausula 5
    {{SUBSTITUICAO}}   "Este contrato substitui ..." (055)
    {{ANEXO_TITULO}}   titulo do Anexo 1, em pagina nova (055)
    {{ANEXO_LINHA}}    um CNPJ do grupo por paragrafo (055)

Os dados da CONTRATADA (razao social, CNPJ, endereco) e o medico
coordenador ficam escritos no texto: mudam uma vez por ano, se mudarem, e o
lugar de muda-los e o Word.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
SAIDA_PADRAO = TEMPLATES / "contrato_modelo.docx"
LOGO = TEMPLATES / "contrato_logo.jpg"

RODAPE = ("R. Francisco Antônio Miranda, 65 - Centro - Guarulhos - S.P. - "
          "Cep.: 07090-140 - Tel: 11 2442-8128 - www.controllermedseg.com.br")

# Rotulos do bloco de assinaturas. O render procura estas linhas no PDF para
# posicionar a assinatura de cada um (services/contrato_render.ROTULOS);
# mudar aqui exige mudar la.
ROTULO_CONTRATANTE = "Contratante"
ROTULO_CONTRATADA = "Contratada"
ROTULO_TESTEMUNHA = "Testemunha"


def _docx():
    try:
        import docx  # noqa: F401
    except ImportError:
        sys.exit("python-docx nao instalado: pip install python-docx==1.1.2")
    import docx
    return docx


def _campo_pagina(paragrafo) -> None:
    """Número da página (campo PAGE do Word), como na minuta."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    campo = OxmlElement("w:fldSimple")
    campo.set(qn("w:instr"), "PAGE")
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    tamanho = OxmlElement("w:sz")
    tamanho.set(qn("w:val"), str(int(Pt(8).pt * 2)))
    props.append(tamanho)
    run.append(props)
    texto = OxmlElement("w:t")
    texto.text = "1"
    run.append(texto)
    campo.append(run)
    paragrafo._p.append(campo)


def gerar(saida: Path) -> Path:
    docx = _docx()
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    doc = docx.Document()

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.5)
    sec.top_margin = Cm(3.2)
    sec.bottom_margin = Cm(2.2)
    sec.header_distance = Cm(0.8)
    sec.footer_distance = Cm(0.8)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10.5)
    pf = normal.paragraph_format
    pf.space_after = Pt(6)
    pf.line_spacing = 1.15

    # Cabecalho: o logo.
    cab = sec.header.paragraphs[0]
    cab.alignment = WD_ALIGN_PARAGRAPH.LEFT
    cab.add_run().add_picture(str(LOGO), width=Cm(5.2))

    # Rodape: endereco + numero da pagina.
    rod = sec.footer.paragraphs[0]
    rod.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = rod.add_run(RODAPE)
    r.font.size = Pt(7.5)
    r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    num = sec.footer.add_paragraph()
    num.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _campo_pagina(num)

    def par(*trechos, alinhar="justify", depois=6, antes=0):
        """trechos: str ou (str, 'b'). Cada trecho vira UM run."""
        p = doc.add_paragraph()
        p.alignment = {
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "left": WD_ALIGN_PARAGRAPH.LEFT,
        }[alinhar]
        p.paragraph_format.space_after = Pt(depois)
        p.paragraph_format.space_before = Pt(antes)
        for t in trechos:
            if isinstance(t, tuple):
                run = p.add_run(t[0])
                run.bold = "b" in t[1]
                run.underline = "u" in t[1]
            else:
                p.add_run(t)
        return p

    def clausula(n):
        par((f"CLÁUSULA {n}", "bu"), alinhar="left", antes=8)

    def item(texto, recuo=0.6):
        p = par(texto)
        p.paragraph_format.left_indent = Cm(recuo)
        return p

    def marcador(texto):
        p = par(f"-  {texto}", depois=1)
        p.paragraph_format.left_indent = Cm(1.6)
        return p

    par(("CONTRATO DE PRESTAÇÃO DE SERVIÇOS MÉDICOS OCUPACIONAIS E "
         "SEGURANÇA DO TRABALHO", "bu"), alinhar="center", depois=14)

    par("{{CONTRATANTE_RAZAO_SOCIAL}}", ", com sede à ", "{{CONTRATANTE_ENDERECO}}",
        ", inscrita no C.N.P.J. do M.F. sob o nº ", "{{CONTRATANTE_CNPJ}}",
        "{{CONTRATANTE_DEMAIS}}",
        ", daqui por diante denominada apenas ", ("CONTRATANTE", "b"),
        " e Controller Medicina e Segurança do Trabalho Ltda., com sede à Rua "
        "Francisco Antonio de Miranda, nº 65, Guarulhos, SP, inscrita no C.N.P.J. "
        "do M.F. sob o nº 43.351.883/0001-97, daqui por diante denominada apenas ",
        ("CONTRATADA", "b"),
        ", têm firmado o presente acordo de atendimento mediante cláusulas abaixo:")

    clausula(1)
    par("A ", ("CONTRATADA", "b"), " prestará à ", ("CONTRATANTE", "b"),
        ", Serviços Médicos Ocupacionais, de acordo com a N.R. 7 publicada no "
        "DOU em 30/12/94, assim relacionados:")
    item("1.1) Elaboração do PCMSO (Programa de Controle Médico de Saúde Ocupacional);")
    item("1.2) Emissão de ASO (Atestado de Saúde Ocupacional): (exames clínicos e "
         "avaliações clínicas já inclusos no valor do contrato)")
    for m in ("exame clínico admissional;", "exame clínico periódico;",
              "exame clínico de retorno ao trabalho;",
              "exame clínico de mudança de função;", "exame clínico demissional."):
        marcador(m)
    item("1.3) Emissão de Relatório Analítico ao final do exercício contratual.")
    par(("Parágrafo Único:", "b"), antes=4)
    par("Os exames poderão ser realizados tanto na sede da ", ("CONTRATANTE", "b"),
        " como na sede da ", ("CONTRATADA", "b"),
        ", sendo o critério puramente técnico e de acordo com a necessidade "
        "clínica e ocupacional estabelecida pela ", ("CONTRATADA", "b"),
        ", através do Médico Coordenador Responsável pelo PCMSO.")

    clausula(2)
    item("2.1) A Contratada prestará serviços à Contratante na área de Segurança "
         "do Trabalho, constituindo seu objeto:")
    item("2.2) Assessoria permanente na área de Segurança do Trabalho para "
         "realização dos levantamentos de informações necessárias, auditorias e "
         "resoluções de eventuais problemas pertinentes à área;")
    item("2.3) Elaboração de Laudos Ambientais dos Agentes físicos e químicos "
         "(químicos quando necessários e com prévia aprovação de custos à parte "
         "pela empresa).")
    par(("Parágrafo Único: ", "b"),
        "Será de responsabilidade da Contratada as avaliações, medições, coletas "
        "de materiais para análises químicas e emissão dos Laudos, sendo "
        "repassado apenas à Contratante as despesas com análises laboratoriais, "
        "locação de equipamentos específicos a determinadas avaliações e "
        "mostradores para coleta, quando necessários. Essas despesas, quando e "
        "se necessárias, dependerão de aprovação por parte da contratante que "
        "deverá fazê-lo em até 5 (cinco) dias úteis. Passado esse prazo deverá "
        "ser solicitado um novo orçamento.")
    item("2.4) Elaboração de Laudo Técnico das Condições do Ambiente de Trabalho – LTCAT;")
    item("2.5) Implantação do PGR (Programa de Gerenciamento de Riscos), em "
         "conformidade com a NR-9 da Portaria 3214 do MTE;")
    item("2.6) Implantação de Fatores de Riscos Psicossociais (NR-01);")
    # 055: serviços além do básico, marcados no envio (2.7, 2.8, ...).
    item("{{SERVICO_EXTRA}}")
    par("A ", ("CONTRATADA", "b"), " nomeia os seguintes Médicos do Trabalho para a "
        "elaboração e coordenação do PCMSO (Programa de Controle Médico de Saúde "
        "Ocupacional) da ", ("CONTRATANTE", "b"), ":")
    par(("Dr. Eduardo Antiori – CRM 73388 - SP", "b"))

    clausula(3)
    par(("e-Social", "b"))
    item("3.1) Envio através de Mensageria do sistema do SOC os layouts S-2220 - "
         "Monitoramento da Saúde do Trabalhador (ASO) e S-2240 - Condições "
         "Ambientais do Trabalho. Para tanto se faz necessária uma outorga "
         "digital feita pela empresa contratante.")
    item("3.2) Eventos descritos na cláusula 3.1 serão enviados até o dia 15 do "
         "mês subsequente aos eventos realizados conforme legislação vigente.")

    clausula(4)
    par("A ", ("CONTRATADA", "b"), " realizará o faturamento mensal de acordo com a "
        "quantidade de funcionários registrados em nosso sistema SOC, podendo "
        "utilizar o FGTS digital da ", ("CONTRATANTE", "b"),
        " para validar esta informação quando necessário.")

    clausula(5)
    par("A ", ("CONTRATANTE", "b"), " pagará mensalmente à ", ("CONTRATADA", "b"),
        ", pelos serviços constantes nas Cláusulas 1, 2 e 3, o valor "
        "correspondente conforme segue, com vencimento todo dia ",
        "{{DIA_VENCIMENTO}}", " de cada mês:")
    p = par("{{PRECO_LINHA}}", depois=2)
    p.paragraph_format.left_indent = Cm(0.6)
    par("Os exames laboratoriais serão pagos de acordo com tabela vigente no "
        "período, enviada à ", ("CONTRATANTE", "b"), ".", antes=6)
    par("Exames Periódicos na sede da ", ("CONTRATANTE", "b"),
        " serão cobrados à parte com negociação de valores através de tabela "
        "vigente no período.")
    par(("Parágrafo Primeiro:", "b"), antes=4)
    par("Deixando a ", ("CONTRATANTE", "b"), " de pagar qualquer parcela nos prazos "
        "aqui estabelecidos, poderá a ", ("CONTRATADA", "b"), " considerar "
        "rescindido o presente Contrato, mediante simples comunicação, cessando "
        "de imediato a prestação de serviços médico-ocupacionais, sem prejuízo "
        "das cobranças que se fizerem necessárias e legais.")
    par(("Parágrafo Segundo:", "b"), antes=4)
    par("A ", ("CONTRATADA", "b"), " compromete-se a não descontar junto a "
        "terceiros, sejam eles bancos, empresas de prestação de serviços, "
        "factoring, ou de outra natureza, quaisquer duplicatas sacadas contra a ",
        ("CONTRATANTE", "b"), ", sob pena de indenizá-la pelos prejuízos a ela "
        "causados, inclusive relacionados a danos morais e lucros cessantes.")

    clausula(6)
    par("As taxas mensais estabelecidas na Cláusula 5 serão reajustadas a cada "
        "aniversário deste Contrato (anual), tendo por base a variação do IPCA "
        "Saúde (Índice de Preços ao Consumidor Amplo divulgado pelo IBGE). Na "
        "hipótese de extinção ou indisponibilidade desse índice, aplicar-se-á o "
        "IPCA/IBGE ou IGPM (o que sofrer a maior variação no período).")

    clausula(7)
    par("O presente Contrato vigorará a partir de ", "{{INICIO_VIGENCIA}}",
        ", com duração de 01 (um) ano e com renovação automática por igual "
        "período e assim sucessivamente nos demais períodos. No caso de "
        "cancelamento, se não houver denúncia por escrito no prazo de 30 "
        "(trinta) dias antes de seu termo final do primeiro ano de vigência "
        "deste contrato, acarretará uma multa equivalente a 03 (três) faturas "
        "mensais. Nos demais anos se faz necessário apenas o cumprimento de 30 "
        "dias de aviso prévio, sem incidência de multa contratual.")
    par(("Parágrafo Primeiro:", "b"), antes=4)
    par("O não pagamento na data estipulada na Cláusula 5 implicará em multa de "
        "2% sobre o valor cobrado, mais juros moratórios de 1% ao mês (ou "
        "atualização pela SELIC/juros legais previstos no art. 406 c/c 389 do CC).")
    par(("Parágrafo Segundo:", "b"), antes=4)
    par("O pedido de falência automaticamente rescinde o presente Contrato, "
        "independentemente de aviso ou notificação judicial ou extrajudicial, sem "
        "prejuízo das cobranças que se fizerem necessárias e legais;")
    par(("Parágrafo Terceiro:", "b"), antes=4)
    par("O pedido de concordata permitirá à ", ("CONTRATADA", "b"), ", opção de "
        "continuar ou não mantendo as cláusulas contratuais do presente "
        "instrumento, na prestação dos serviços médico-ocupacionais à ",
        ("CONTRATANTE", "b"), ";")
    par(("Parágrafo Quarto:", "b"), antes=4)
    par("O pedido de concordata não autoriza a ", ("CONTRATANTE", "b"),
        " a romper o presente Contrato, a não ser na data prevista no mesmo, ou "
        "mediante o pagamento da multa equivalente à quitação de seus débitos "
        "existentes.")
    par(("Parágrafo Quinto:", "b"), antes=4)
    par("A Contratada obriga-se a respeitar as disposições estabelecidas na Lei "
        "Federal n.º 13.709/2018, com a redação dada pela Lei n. 13.853/2019 "
        "(Lei Geral de Proteção de Dados – LGPD), limitando-se a utilizar as "
        "informações e dados pessoais prestados pela Contratante e/ou pelos "
        "candidatos envolvidos na presente contratação, apenas durante o prazo "
        "de vigência do contrato e para o fim exclusivo de executar o objeto "
        "contratual, sendo que:")
    item("I - A Contratada só poderá utilizar as informações e dados pessoais "
         "prestados pela Contratante para propósitos legítimos, específicos, "
         "explícitos e informados à Contratante, sem possibilidade de utilização "
         "posterior de forma incompatível com essas finalidades. A utilização "
         "dessas informações e dados pessoais deverá se limitar ao período "
         "necessário para a execução do objeto contratual, jamais podendo "
         "ultrapassar o prazo de vigência do contrato;")
    item("II - Fica vedada a transferência para terceiros das informações e "
         "dados pessoais prestados pela Contratante e/ou pelos funcionários e "
         "colaboradores desta, salvo mediante prévio e expresso consentimento por "
         "escrito da Contratante e para o fim específico de possibilitar a "
         "execução do objeto contratual; e")
    item("III - A Contratada atesta que conhece a Política de Privacidade da "
         "Contratante, obrigando-se a respeitá-la, bem como a adotar regras de "
         "boas práticas e governança com o objetivo de tratar as informações e "
         "dados pessoais prestados pela Contratante.")

    # 055: contrato que substitui o anterior da mesma raiz de CNPJ.
    par("{{SUBSTITUICAO}}", antes=8)
    par("As partes elegem o FORO DA COMARCA DE GUARULHOS para dirimir quaisquer "
        "dúvidas oriundas deste Contrato.", antes=8)
    par("E por estarem assim justos e contratados, firmam o presente em 02 (duas) "
        "vias de igual teor e forma, na presença de duas testemunhas abaixo "
        "identificadas.")
    par("{{CIDADE}}", ", ", "{{DATA_EXTENSO}}", ".", alinhar="left", antes=10, depois=10)

    # Bloco de assinaturas. Cada um: espaco para o carimbo da Autentique,
    # a linha, o rotulo (que o render procura no PDF) e a empresa. O bloco
    # inteiro fica numa pagina so (keep_with_next), para o carimbo nao cair
    # numa pagina e o rotulo na outra.
    blocos = [
        (ROTULO_CONTRATANTE, "{{CONTRATANTE_RAZAO_SOCIAL}}"),
        (ROTULO_CONTRATADA, "Controller Medicina e Segurança do Trabalho Ltda."),
        (ROTULO_TESTEMUNHA, "{{CONTRATANTE_RAZAO_SOCIAL}}"),
        (ROTULO_TESTEMUNHA, "Controller Medicina e Segurança do Trabalho Ltda."),
    ]
    for i, (rotulo, empresa) in enumerate(blocos):
        espaco = par("", alinhar="left", antes=0, depois=0)
        espaco.paragraph_format.space_before = Pt(30)
        espaco.paragraph_format.keep_with_next = True
        linha = par("______________________________________", alinhar="left", depois=0)
        linha.paragraph_format.keep_with_next = True
        rot = par((rotulo, "b"), alinhar="left", depois=0)
        rot.paragraph_format.keep_with_next = True
        emp = par(empresa, alinhar="left", depois=4)
        emp.paragraph_format.keep_with_next = i < len(blocos) - 1

    # 055: Anexo 1 -- matriz e filiais do mesmo contrato. O titulo abre
    # pagina nova; sem filiais, titulo e linhas somem.
    tit = par(("{{ANEXO_TITULO}}", "b"), alinhar="left", depois=10)
    tit.paragraph_format.page_break_before = True
    lin = par("{{ANEXO_LINHA}}", alinhar="left", depois=4)
    lin.paragraph_format.left_indent = Cm(0.6)

    saida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(saida))
    return saida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = ap.parse_args()
    caminho = gerar(args.saida)
    print(f"modelo gravado em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
