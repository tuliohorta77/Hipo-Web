"""
HIPO — Contrato: preenche o modelo .docx, converte em PDF e acha as linhas
de assinatura (entrega 053).

SEM DEPENDÊNCIA NOVA. O .docx é um zip de XML; o preenchimento abre o zip e
mexe no XML com lxml, que já vem com o python-pptx da proposta. O
python-docx ficou só no gerador do modelo (scripts/gerar_modelo_contrato.py)
— lição da 009: o deploy faz rsync e não roda pip install, e lib nova na API
vira 500 em produção até alguém instalar à mão.

CAMPO QUEBRADO PELO WORD. Quem edita o modelo no Word pode deixar
`{{DIA_VENCIMENTO}}` repartido em três runs (`{{DIA_`, `VENCI`, `MENTO}}`) —
basta corrigir uma letra no meio. O preenchimento junta o texto do
parágrafo, acha o campo e reescreve só os runs que ele ocupa: o primeiro
recebe o valor (com a formatação dele), os do meio ficam vazios. Negrito
vizinho ("CONTRATANTE") não é tocado.

CAMPO DESCONHECIDO É ERRO. Modelo com `{{QUALQUER}}` que o código não sabe
preencher iria para o cliente com o marcador impresso. `preencher` recusa
com ModeloInvalido, e a suíte confere o modelo versionado.

O PDF sai pelo mesmo LibreOffice da proposta (proposta_render), com o
filtro do Writer.
"""
from __future__ import annotations

import copy
import io
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from config import settings
from services import contrato as regras
from services.proposta_render import libreoffice_disponivel

CAMINHO_MODELO = Path(__file__).resolve().parent.parent / "templates" / "contrato_modelo.docx"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_CAMPO = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

# Partes do pacote que podem ter campo: corpo, cabeçalhos e rodapés.
_PARTES = re.compile(r"^word/(document|header\d*|footer\d*)\.xml$")

TIMEOUT_PDF_S = 120
FILTRO_PDF = "pdf:writer_pdf_Export"

# Rótulos do bloco de assinaturas, na ordem do modelo (ver
# scripts/gerar_modelo_contrato.py). O PDF é varrido atrás destas linhas.
ROTULOS = {
    "contratante": ("Contratante", 1),
    "contratada": ("Contratada", 1),
    "testemunha_contratante": ("Testemunha", 1),   # 1ª "Testemunha" do bloco
    "testemunha_contratada": ("Testemunha", 2),    # 2ª
}

# O carimbo da Autentique vai ACIMA da linha, no espaço em branco que o
# modelo deixa. y da Autentique é % da altura a partir do topo; o rótulo
# fica uma linha abaixo do traço. Valores conferidos no sandbox; se a arte
# do bloco mudar, é aqui que se ajusta.
SUBIR_CARIMBO_PT = 52
X_MINIMO_PCT = 2.0


class ModeloContratoIndisponivel(RuntimeError):
    pass


class ModeloInvalido(RuntimeError):
    pass


class ContratoPdfIndisponivel(RuntimeError):
    pass


def _lxml():
    try:
        from lxml import etree
    except ImportError as exc:  # pragma: no cover - vem com o python-pptx
        raise ModeloContratoIndisponivel(
            "lxml não está instalado no servidor (pip install lxml)."
        ) from exc
    return etree


# ── Modelo ───────────────────────────────────────────────────────────

def caminho_do_modelo() -> Path:
    """CONTRATO_MODELO_ARQUIVO no .env troca o modelo (instância MOS)."""
    personalizado = (settings.CONTRATO_MODELO_ARQUIVO or "").strip()
    return Path(personalizado) if personalizado else CAMINHO_MODELO


def ler_modelo(caminho: Path | None = None) -> bytes:
    caminho = caminho or caminho_do_modelo()
    try:
        return caminho.read_bytes()
    except OSError as exc:
        raise ModeloContratoIndisponivel(
            f"O modelo do contrato não foi encontrado em {caminho}."
        ) from exc


def _paragrafos(raiz):
    return list(raiz.iter(f"{W}p"))


def _textos(p) -> list:
    """Os w:t do parágrafo, sem descer em parágrafos aninhados (caixa de texto)."""
    nos = []
    for t in p.iter(f"{W}t"):
        dono = t.getparent()
        while dono is not None and dono.tag != f"{W}p":
            dono = dono.getparent()
        if dono is p:
            nos.append(t)
    return nos


def _texto(p) -> str:
    return "".join(t.text or "" for t in _textos(p))


def campos_do_modelo(docx: bytes) -> set[str]:
    """Os campos que o modelo usa (com o campo reconstruído entre runs)."""
    etree = _lxml()
    achados: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        for nome in z.namelist():
            if _PARTES.match(nome):
                raiz = etree.fromstring(z.read(nome))
                for p in _paragrafos(raiz):
                    achados.update(m.group(1) for m in _CAMPO.finditer(_texto(p)))
    return achados


def _gravar(nos, textos) -> None:
    for t, novo in zip(nos, textos):
        if (t.text or "") != novo:
            t.text = novo
            t.set(XML_SPACE, "preserve")


def _trocar_simples(p, valores: dict[str, str], desconhecidos: set[str]) -> None:
    nos = _textos(p)
    if not nos:
        return
    textos = [t.text or "" for t in nos]
    pos = 0
    while True:
        completo = "".join(textos)
        m = _CAMPO.search(completo, pos)
        if not m:
            break
        nome = m.group(1)
        if nome not in valores:
            desconhecidos.add(nome)
            pos = m.end()
            continue
        valor = valores[nome]
        # Localiza o run de início e o de fim do campo.
        ini, fim = m.start(), m.end()
        acum = 0
        i_ini = i_fim = None
        off_ini = off_fim = 0
        for i, txt in enumerate(textos):
            prox = acum + len(txt)
            if i_ini is None and ini < prox:
                i_ini, off_ini = i, ini - acum
            if fim <= prox:
                i_fim, off_fim = i, fim - acum
                break
            acum = prox
        if i_ini == i_fim:
            textos[i_ini] = textos[i_ini][:off_ini] + valor + textos[i_ini][off_fim:]
        else:
            textos[i_ini] = textos[i_ini][:off_ini] + valor
            for k in range(i_ini + 1, i_fim):
                textos[k] = ""
            textos[i_fim] = textos[i_fim][off_fim:]
        pos = ini + len(valor)
    _gravar(nos, textos)


def _expandir_lista(p, valores: list[str]) -> None:
    """Repete o parágrafo, um por valor; lista vazia remove o parágrafo."""
    pai = p.getparent()
    for valor in valores:
        novo = copy.deepcopy(p)
        nos = _textos(novo)
        _gravar(nos, [valor] + [""] * (len(nos) - 1))
        p.addprevious(novo)
    pai.remove(p)


def preencher(docx: bytes, simples: dict[str, str], listas: dict[str, list[str]]) -> bytes:
    """
    O .docx com os campos preenchidos.

    Campo de lista precisa estar sozinho no parágrafo — é o parágrafo que se
    repete. Fora disso, ou com campo desconhecido, ModeloInvalido.
    """
    etree = _lxml()
    desconhecidos: set[str] = set()
    lista_misturada: set[str] = set()
    saida = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx)) as entrada, \
            zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for info in entrada.infolist():
            dados = entrada.read(info.filename)
            if _PARTES.match(info.filename):
                raiz = etree.fromstring(dados)
                for p in _paragrafos(raiz):
                    texto = _texto(p)
                    if "{{" not in texto:
                        continue
                    sozinho = _CAMPO.fullmatch(texto.strip())
                    if sozinho and sozinho.group(1) in listas:
                        _expandir_lista(p, listas[sozinho.group(1)])
                        continue
                    for m in _CAMPO.finditer(texto):
                        if m.group(1) in listas:
                            lista_misturada.add(m.group(1))
                    _trocar_simples(p, simples, desconhecidos)
                dados = etree.tostring(raiz, xml_declaration=True,
                                       encoding="UTF-8", standalone=True)
            destino.writestr(info, dados)

    if lista_misturada:
        raise ModeloInvalido(
            "No modelo do contrato, o campo " + ", ".join(
                f"{{{{{n}}}}}" for n in sorted(lista_misturada))
            + " precisa ficar sozinho no parágrafo (o parágrafo é repetido "
            "uma vez por item)."
        )
    if desconhecidos:
        raise ModeloInvalido(
            "O modelo do contrato tem campo que o HIPO não sabe preencher: "
            + ", ".join(f"{{{{{n}}}}}" for n in sorted(desconhecidos))
            + ". Corrija o modelo no Word ou fale com o desenvolvimento."
        )
    return saida.getvalue()


def conferir_modelo(docx: bytes) -> list[str]:
    """Problemas do modelo, para a suíte e para o deploy. Vazio = ok."""
    usados = campos_do_modelo(docx)
    conhecidos = set(regras.CAMPOS_SIMPLES) | set(regras.CAMPOS_LISTA)
    problemas = [f"campo desconhecido: {{{{{n}}}}}" for n in sorted(usados - conhecidos)]
    for n in ("CONTRATANTE_RAZAO_SOCIAL", "CONTRATANTE_CNPJ", "PRECO_LINHA"):
        if n not in usados:
            problemas.append(f"campo obrigatório ausente: {{{{{n}}}}}")
    return problemas


# ── PDF ──────────────────────────────────────────────────────────────

def para_pdf(docx: bytes) -> bytes:
    """
    Converte pelo LibreOffice headless, com HOME num diretório temporário
    próprio (mesma razão de proposta_render.para_pdf: dois pedidos juntos
    disputariam o perfil do usuário).
    """
    binario = libreoffice_disponivel()
    if not binario:
        raise ContratoPdfIndisponivel(
            "O LibreOffice não está instalado no servidor, então o contrato não "
            "pode ser gerado em PDF."
        )
    with tempfile.TemporaryDirectory(prefix="hipo-contrato-") as tmp:
        entrada = os.path.join(tmp, "contrato.docx")
        with open(entrada, "wb") as f:
            f.write(docx)
        try:
            resultado = subprocess.run(
                [binario, "--headless", "--norestore", "--invisible",
                 "--convert-to", FILTRO_PDF, "--outdir", tmp, entrada],
                capture_output=True, timeout=TIMEOUT_PDF_S,
                env=dict(os.environ, HOME=tmp),
            )
        except subprocess.TimeoutExpired as exc:
            raise ContratoPdfIndisponivel(
                f"A conversão do contrato para PDF passou de {TIMEOUT_PDF_S}s."
            ) from exc
        saida = os.path.join(tmp, "contrato.pdf")
        if not os.path.exists(saida):
            erro = (resultado.stderr or b"").decode("utf-8", "replace")[:300]
            raise ContratoPdfIndisponivel(
                "O LibreOffice não produziu o PDF do contrato. "
                f"Detalhe do servidor: {erro or 'sem mensagem'}"
            )
        with open(saida, "rb") as f:
            return f.read()


def montar_pdf(simples: dict[str, str], listas: dict[str, list[str]],
               caminho_modelo: Path | None = None) -> bytes:
    """Modelo -> campos -> PDF. Síncrono e lento (segundos): chamar em thread."""
    docx = preencher(ler_modelo(caminho_modelo), simples, listas)
    return para_pdf(docx)


# ── Onde cada um assina ──────────────────────────────────────────────

def localizar_assinaturas(pdf: bytes) -> dict[str, dict]:
    """
    {papel: {'x': '12.3', 'y': '45.6', 'z': 6}} — a posição do carimbo de
    cada signatário, para a Autentique desenhar a assinatura em cima da
    linha certa, como no contrato da Porto Pisos.

    Procura no PDF as linhas cujo texto é exatamente o rótulo ("Contratante",
    "Contratada", "Testemunha"); vale a ÚLTIMA ocorrência de cada uma (o
    bloco de assinaturas fecha o contrato). Papel não encontrado fica de
    fora: a Autentique ainda colhe a assinatura, só não a desenha no corpo —
    o contrato vale do mesmo jeito, pela página de auditoria.
    """
    try:
        import pypdf
    except ImportError:
        return {}
    try:
        leitor = pypdf.PdfReader(io.BytesIO(pdf))
    except Exception:
        return {}

    achados: dict[str, list[tuple[int, float, float, float, float]]] = {}
    for indice, pagina in enumerate(leitor.pages):
        caixa = pagina.mediabox
        largura, altura = float(caixa.width), float(caixa.height)

        def visitante(texto, cm, tm, _fonte, _tamanho, _i=indice, _l=largura, _a=altura):
            limpo = (texto or "").strip()
            if limpo not in ("Contratante", "Contratada", "Testemunha"):
                return
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            achados.setdefault(limpo, []).append((_i, x, y, _l, _a))

        try:
            pagina.extract_text(visitor_text=visitante)
        except Exception:
            continue

    posicoes: dict[str, dict] = {}
    ultimas = {rot: lista for rot, lista in achados.items()}
    testemunhas = ultimas.get("Testemunha", [])[-2:]
    for papel, (rotulo, n) in ROTULOS.items():
        if rotulo == "Testemunha":
            if len(testemunhas) < n:
                continue
            ponto = testemunhas[n - 1]
        else:
            lista = ultimas.get(rotulo)
            if not lista:
                continue
            ponto = lista[-1]
        pagina, x, y, largura, altura = ponto
        topo = (altura - y) - SUBIR_CARIMBO_PT
        posicoes[papel] = {
            "x": f"{max(X_MINIMO_PCT, x / largura * 100):.1f}",
            "y": f"{max(0.0, min(95.0, topo / altura * 100)):.1f}",
            "z": pagina + 1,
        }
    return posicoes
