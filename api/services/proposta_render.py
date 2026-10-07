"""
HIPO — Preenchimento do modelo .pptx da proposta e conversão para PDF.

Separado de services/proposta.py de propósito: aqui há I/O (abre arquivo,
chama subprocesso) e dependência externa (python-pptx, LibreOffice). As
regras e a formatação ficam lá, testáveis sem nada disso.

## Como o modelo funciona

`api/templates/proposta_modelo.pptx` é o material da Controller MedSeg com
os campos variáveis trocados por marcadores `{{ASSIM}}`. Os slides 1 a 4
são institucionais e não têm marcador nenhum — o código nem os visita.

Desde a 042 o modelo tem os slides das DUAS modalidades (5: escopo com
quadro de investimento, por vida; 6: escopo com uma linha por CNPJ e a
mensalidade total, tabela). Cada um leva a etiqueta `hipo-modalidade:<x>`
no nome de um shape, e `montar_pptx` apaga os da modalidade que não foi
escolhida antes de preencher.

A 051 tirou o slide da tabela de preços: a tabela é base do vendedor e não
vai para o cliente. O cliente vê a faixa de cada CNPJ na própria linha.

Cada marcador vive num run ÚNICO dentro do parágrafo. Isso não é detalhe:
o PowerPoint quebra texto em runs por corretor ortográfico e formatação, e
um `{{VALOR_VIDA}}` digitado à mão costuma virar três runs ('{{VALOR', '_',
'VIDA}}'), que nenhum replace de string encontra. O modelo foi gerado por
script justamente para garantir um run por marcador.

Se você trocar o modelo, mantenha os marcadores intactos e prefira colar
cada um de uma vez, sem editar letra por letra dentro dele.

## O escopo

`{{ESCOPO_ITEM}}` é o parágrafo-molde da lista. O código o clona uma vez
por item da proposta, preservando bullet, fonte e recuo, e remove o molde
no fim. Escrever os itens com '\\n' num run só perderia a marcação de lista.
"""
from __future__ import annotations

import copy
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

# python-pptx é importado DENTRO das funções, não aqui.
#
# Este módulo é alcançado pela cadeia main -> routers -> services, então um
# import no topo faz a API INTEIRA morrer se a biblioteca faltar: o serviço
# não sobe, e o HIPO fica fora do ar por causa de uma feature. Já aconteceu
# na primeira tentativa de deploy da 009 -- a suíte inteira de testes
# abortou no conftest, sem nenhum teste ter rodado.
#
# O deploy do CI faz rsync e reinicia; NÃO roda pip install. Com o import
# tardio, faltar a lib derruba só a proposta, com 503 e mensagem dizendo o
# que instalar.

# api/services/proposta_render.py -> api/templates/proposta_modelo.pptx
CAMINHO_MODELO = Path(__file__).resolve().parent.parent / "templates" / "proposta_modelo.pptx"

MARCADOR_ESCOPO = "{{ESCOPO_ITEM}}"

# A caixa "Mensalidade total para os 5 CNPJs - R$ 4.500,00" (slide da
# modalidade tabela). O texto muda de tamanho com o número de CNPJs e com o
# valor; acima de CARACTERES_MENSALIDADE a fonte encolhe para a frase caber
# numa linha, até ESCALA_MINIMA_MENSALIDADE.
SHAPE_MENSALIDADE = "hipo-mensalidade"
CARACTERES_MENSALIDADE = 34
ESCALA_MINIMA_MENSALIDADE = 0.6

# Os slides que só valem para uma modalidade levam esta etiqueta no nome de
# um shape (ver scripts/gerar_modelo_proposta_tabela.py). Slide sem
# etiqueta vale para todas.
ETIQUETA_MODALIDADE = "hipo-modalidade:"

# Nomes do binário no PATH, conforme a distribuição.
BINARIOS_LIBREOFFICE = ("soffice", "libreoffice")

# A Amazon Linux 2023 NÃO tem LibreOffice nos repositórios (o
# libreoffice-impress do AL2 sumiu). Quando ele é instalado pelo tarball
# oficial da Document Foundation, o binário fica fora do PATH, em
# /opt/libreoffice<versão>/program/soffice — daí a busca por padrão de
# caminho além do `which`.
PADROES_LIBREOFFICE = (
    "/opt/libreoffice*/program/soffice",
    "/usr/lib64/libreoffice/program/soffice",
    "/opt/libreoffice*/program/soffice.bin",
)

# Conversão de 6 slides com imagens pesadas leva ~5s numa t3.medium fria.
# 120s é folga para o primeiro uso, quando o LibreOffice ainda monta o
# perfil do usuário.
TIMEOUT_PDF_S = 120


class BibliotecaIndisponivel(RuntimeError):
    """python-pptx não instalado no ambiente que está servindo."""


class ModeloIndisponivel(RuntimeError):
    """O .pptx do modelo não está onde deveria."""


class PdfIndisponivel(RuntimeError):
    """LibreOffice ausente ou falhou. A mensagem diz o que fazer no servidor."""


# ── PPTX ─────────────────────────────────────────────────────────────

def _presentation():
    """Importa python-pptx na hora do uso. Ver a nota no topo do módulo."""
    try:
        from pptx import Presentation
    except ImportError as erro:
        raise BibliotecaIndisponivel(
            "python-pptx não está instalado no servidor, então a proposta não "
            "pode ser gerada. Instale com: "
            "sudo -iu hipo python3 -m pip install --user python-pptx==1.0.2"
        ) from erro
    return Presentation


def pptx_disponivel() -> bool:
    """Usado pela tela para avisar antes de o usuário preencher o formulário."""
    try:
        import pptx  # noqa: F401
    except ImportError:
        return False
    return True


def _substituir_no_texto(shape, mapa: dict[str, str]) -> None:
    """
    Troca marcadores run a run, preservando a formatação de cada um.

    Percorre runs em vez do texto do shape inteiro porque atribuir
    `text_frame.text` apaga toda a formatação do quadro — o slide sairia
    com a fonte padrão do tema no lugar da tipografia da marca.
    """
    if not shape.has_text_frame:
        return
    for par in shape.text_frame.paragraphs:
        for run in par.runs:
            texto = run.text
            if "{{" not in texto:
                continue
            for marcador, valor in mapa.items():
                if marcador in texto:
                    texto = texto.replace(marcador, valor)
            run.text = texto


# Tamanho da fonte da lista quando o run não diz (herdado do mestre) e a
# entrelinha do material — base da redução quando a lista não cabe.
FONTE_LISTA_CENTESIMOS = 1800
ENTRELINHA_LISTA_CENTESIMOS = 3639


def _aplicar_escala(p_xml, escala) -> None:
    """
    Encolhe fonte e entrelinha do parágrafo pelo mesmo fator.

    As duas juntas: só a fonte menor deixaria o mesmo vão entre linhas e a
    lista continuaria transbordando; só a entrelinha menor encavalaria as
    letras.
    """
    from pptx.oxml.ns import qn
    fator = float(escala)
    ppr = p_xml.find(qn("a:pPr"))
    if ppr is not None:
        spc = ppr.find(f"{qn('a:lnSpc')}/{qn('a:spcPts')}")
        if spc is not None:
            spc.set("val", str(round(int(spc.get("val", ENTRELINHA_LISTA_CENTESIMOS)) * fator)))
    for rpr in p_xml.iter(qn("a:rPr")):
        base = int(rpr.get("sz") or FONTE_LISTA_CENTESIMOS)
        rpr.set("sz", str(round(base * fator)))


def _preencher_lista(slide, marcador: str, itens: list[str], escala=None) -> bool:
    """
    Clona o parágrafo-molde uma vez por item. Devolve True se achou o molde.

    `escala` (< 1) encolhe fonte e entrelinha de todos os itens — é o que
    faz uma proposta com muitos CNPJs caber na caixa do material.
    """
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        molde = None
        for par in shape.text_frame.paragraphs:
            if marcador in par.text:
                molde = par
                break
        if molde is None:
            continue

        pai = molde._p.getparent()
        for item in itens:
            novo = copy.deepcopy(molde._p)
            pai.insert(list(pai).index(molde._p), novo)
            # Reencontra o parágrafo recém-inserido pela árvore XML: o
            # objeto Paragraph do python-pptx é um wrapper, e o índice na
            # lista de paragraphs muda a cada inserção.
            from pptx.text.text import _Paragraph  # import local: detalhe interno
            _Paragraph(novo, shape.text_frame).runs[0].text = item
            if escala is not None and escala < 1:
                _aplicar_escala(novo, escala)

        pai.remove(molde._p)
        return True
    return False


def _preencher_escopo(slide, itens: list[str], escala=None) -> bool:
    return _preencher_lista(slide, MARCADOR_ESCOPO, itens, escala)


def _propriedades(prs, substituicoes: dict[str, str]) -> None:
    """
    Título e autor do ARQUIVO (não dos slides): é o que o leitor de PDF
    mostra na barra e o que o Windows mostra em Propriedades.

    O modelo veio do material de outra proposta, e o título dele era
    "(modelo) Proposta Comercial - SOLAR DOS PAMPAS ..." — todo PDF gerado
    levava o nome de outro cliente na barra do visualizador. Visto no
    visualizador da 051.
    """
    cliente = substituicoes.get("{{CLIENTE}}", "").strip()
    executivo = substituicoes.get("{{EXECUTIVO_NOME}}", "").strip()
    props = prs.core_properties
    props.title = f"Proposta Comercial - {cliente}" if cliente else "Proposta Comercial"
    props.subject = ""
    props.keywords = ""
    props.comments = ""
    props.author = executivo
    props.last_modified_by = executivo


def _caber_numa_linha(shape) -> None:
    """
    Encolhe a fonte da caixa da mensalidade quando a frase passa de
    CARACTERES_MENSALIDADE. Proporcional ao comprimento: "Mensalidade
    R$ 300,00" fica do tamanho do material; "Mensalidade total para os 12
    CNPJs - R$ 14.500,00" encolhe o bastante para não quebrar a linha.
    """
    from pptx.oxml.ns import qn
    texto = shape.text_frame.text.strip()
    if len(texto) <= CARACTERES_MENSALIDADE:
        return
    fator = max(ESCALA_MINIMA_MENSALIDADE, CARACTERES_MENSALIDADE / len(texto))
    for rpr in shape._element.iter(qn("a:rPr")):
        base = rpr.get("sz")
        if base:
            rpr.set("sz", str(round(int(base) * fator)))


def _modalidade_do_slide(slide) -> str | None:
    """A etiqueta `hipo-modalidade:<x>` no nome de um shape, se houver."""
    for shape in slide.shapes:
        if shape.name.startswith(ETIQUETA_MODALIDADE):
            return shape.name[len(ETIQUETA_MODALIDADE):]
    return None


def _remover_slide(prs, slide) -> None:
    """
    Tira o slide da apresentação. Some da lista E perde a relação: sem
    relação, o python-pptx não grava a parte, e o arquivo não leva o slide
    escondido junto (cliente que abre o painel de seleção acharia).
    """
    lista = prs.slides._sldIdLst
    for sld in list(lista):
        if prs.part.related_part(sld.rId) is slide.part:
            lista.remove(sld)
            prs.part.drop_rel(sld.rId)
            return


def montar_pptx(
    substituicoes: dict[str, str],
    escopo: list[str],
    caminho_modelo: Path | str | None = None,
    *,
    modalidade: str = "por_vida",
    escala_escopo=None,
) -> bytes:
    """
    Devolve o .pptx preenchido, em memória.

    Não grava em disco: o arquivo é servido direto na resposta HTTP, e
    escrever num diretório temporário só criaria lixo para limpar (e uma
    corrida entre dois vendedores gerando ao mesmo tempo).
    """
    from services.instancia import modelo_proposta

    # CAMINHO_MODELO segue sendo o versionado; o .env pode apontar outro
    # (PROPOSTA_MODELO_ARQUIVO, 046) para a instancia de outra empresa.
    modelo = Path(caminho_modelo or modelo_proposta())
    if not modelo.is_file():
        raise ModeloIndisponivel(
            f"Modelo da proposta não encontrado em {modelo}. "
            "Ele é versionado em api/templates/ — confira se o deploy copiou a pasta."
        )

    Presentation = _presentation()
    prs = Presentation(str(modelo))

    # Primeiro sai o que não é desta modalidade; depois se preenche o resto.
    for slide in list(prs.slides):
        etiqueta = _modalidade_do_slide(slide)
        if etiqueta is not None and etiqueta != modalidade:
            _remover_slide(prs, slide)

    for slide in prs.slides:
        _preencher_escopo(slide, escopo, escala_escopo)
        for shape in slide.shapes:
            _substituir_no_texto(shape, substituicoes)
            if shape.name == SHAPE_MENSALIDADE:
                _caber_numa_linha(shape)

    _propriedades(prs, substituicoes)

    buffer = BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


# ── PDF ──────────────────────────────────────────────────────────────

def libreoffice_disponivel() -> str | None:
    """Caminho do binário, ou None. Usado pela tela para esconder o botão."""
    for nome in BINARIOS_LIBREOFFICE:
        caminho = shutil.which(nome)
        if caminho:
            return caminho

    # Instalação por tarball não põe nada no PATH.
    import glob
    for padrao in PADROES_LIBREOFFICE:
        for achado in sorted(glob.glob(padrao), reverse=True):
            if os.access(achado, os.X_OK):
                return achado
    return None


def para_pdf(pptx: bytes) -> bytes:
    """
    Converte via LibreOffice headless.

    Roda num diretório temporário próprio, com HOME apontando para ele: sem
    isso o soffice tenta escrever o perfil em /home/hipo e, se dois pedidos
    chegam juntos, o segundo morre disputando o mesmo lock — falha
    intermitente que só aparece quando dois vendedores geram ao mesmo tempo.
    """
    binario = libreoffice_disponivel()
    if not binario:
        raise PdfIndisponivel(
            "LibreOffice não está instalado no servidor, então o PDF não pode "
            "ser gerado. O PPTX continua funcionando normalmente — baixe e "
            "exporte pelo PowerPoint. Para habilitar o PDF, rode o "
            "deploy-009 com -InstalarLibreOffice (a Amazon Linux 2023 não "
            "tem o pacote nos repositórios; a instalação é pelo tarball "
            "oficial)."
        )

    with tempfile.TemporaryDirectory(prefix="hipo-proposta-") as tmp:
        entrada = os.path.join(tmp, "proposta.pptx")
        with open(entrada, "wb") as f:
            f.write(pptx)

        ambiente = dict(os.environ, HOME=tmp)
        try:
            resultado = subprocess.run(
                [binario, "--headless", "--norestore", "--invisible",
                 "--convert-to", "pdf", "--outdir", tmp, entrada],
                capture_output=True, timeout=TIMEOUT_PDF_S, env=ambiente,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfIndisponivel(
                f"A conversão para PDF passou de {TIMEOUT_PDF_S}s e foi "
                "interrompida. Baixe o PPTX e converta no PowerPoint."
            ) from exc

        saida = os.path.join(tmp, "proposta.pdf")
        if not os.path.exists(saida):
            erro = (resultado.stderr or b"").decode("utf-8", "replace")[:300]
            raise PdfIndisponivel(
                "O LibreOffice não produziu o PDF. Baixe o PPTX e converta no "
                f"PowerPoint. Detalhe do servidor: {erro or 'sem mensagem'}"
            )
        with open(saida, "rb") as f:
            return f.read()
