"""
Acrescenta ao modelo da proposta os dois slides da modalidade "tabela de
preço por faixa" (entrega 042).

    python -m scripts.gerar_modelo_proposta_tabela "PROPOSTA ... VARIOS CNPJs.pptx"

## O que sai

`api/templates/proposta_modelo.pptx` passa a ter 8 slides:

    1-4  institucionais (não mudam)
    5    escopo + quadro de investimento   -> modalidade por_vida
    6    tabela de preços                  -> modalidade tabela
    7    escopo + mensalidade              -> modalidade tabela
    8    fechamento

O render (services/proposta_render.py) apaga os slides da modalidade que
não foi escolhida. Cada slide variável leva uma etiqueta no NOME de um
shape (`hipo-modalidade:por_vida` / `hipo-modalidade:tabela`) — é assim que
o render sabe o que apagar sem depender de posição.

## Por que copiar do material, e não desenhar

Os slides 6 e 7 vêm do material "VARIOS CNPJs" da Controller MedSeg: mesma
moldura, mesmas faixas verdes. O fundo deles usa exatamente as mesmas
imagens do slide 5 do modelo (conferido por hash), então a cópia não
acrescenta mídia nenhuma — o arquivo não engorda.

A imagem da tabela de preços do material NÃO é copiada: vira lista de
texto com o marcador {{FAIXA_ITEM}}, montada a partir da tabela que a
gestão edita no HIPO. Imagem fixa mentiria no dia do primeiro reajuste.

## Um run por marcador

Mesma regra do gerar_modelo_proposta.py: cada marcador vive num run único,
senão nenhum replace de string o encontra.
"""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

from pptx import Presentation
from pptx.oxml.ns import qn

RAIZ = Path(__file__).resolve().parent.parent
MODELO = RAIZ / "templates" / "proposta_modelo.pptx"

ETIQUETA = "hipo-modalidade:"

# Índices no MODELO atual (0-based).
SLIDE_POR_VIDA = 4
# Índices no material "VARIOS CNPJs".
ORIGEM_TABELA = 4
ORIGEM_ESCOPO = 5

RODAPE = "{{TABELA_RODAPE}}"


def _shape(slide, nome):
    for sh in slide.shapes:
        if sh.name == nome:
            return sh
    raise KeyError(f"shape '{nome}' não existe no slide")


def _hash(part) -> str:
    return hashlib.sha1(part.blob).hexdigest()


def _run_unico(paragrafo, texto: str) -> None:
    runs = paragrafo.runs
    if not runs:
        raise ValueError("parágrafo sem runs — nada de onde herdar formatação")
    runs[0].text = texto
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def _texto_unico(shape, texto: str) -> None:
    """Um parágrafo, um run, com a formatação do primeiro run original."""
    tf = shape.text_frame
    _run_unico(tf.paragraphs[0], texto)
    for p in list(tf.paragraphs[1:]):
        p._p.getparent().remove(p._p)


def _copiar_slide(destino, origem_slide, layout, por_hash: dict):
    """
    Cria no destino um slide com a árvore de shapes da origem.

    Cada imagem referenciada é religada à parte EQUIVALENTE do destino
    (mesmo conteúdo, por hash). Imagem sem equivalente aborta: copiar
    mídia nova não é o objetivo, e ela engordaria o modelo em silêncio.
    """
    novo = destino.slides.add_slide(layout)
    arvore = novo.shapes._spTree
    for filho in list(arvore):
        if filho.tag not in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
            arvore.remove(filho)

    origem_arvore = copy.deepcopy(origem_slide.shapes._spTree)

    # A imagem da tabela (Imagem 9) não vem.
    for pic in origem_arvore.findall(qn("p:pic")):
        origem_arvore.remove(pic)

    rels_origem = origem_slide.part.rels
    for el in origem_arvore.iter():
        for atributo in (qn("r:embed"), qn("r:id"), qn("r:link")):
            rid = el.get(atributo)
            if not rid:
                continue
            rel = rels_origem[rid]
            if rel.is_external:
                novo_rid = novo.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
            else:
                alvo = por_hash.get(_hash(rel.target_part))
                if alvo is None:
                    raise RuntimeError(
                        f"imagem {rel.target_part.partname} do material não existe "
                        "no modelo — o fundo mudou? Confira antes de seguir."
                    )
                novo_rid = novo.part.relate_to(alvo, rel.reltype)
            el.set(atributo, novo_rid)

    for filho in origem_arvore:
        if filho.tag in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
            continue
        arvore.append(filho)

    # O fundo verde é um gradiente do PRÓPRIO slide (p:bg), fora da árvore
    # de shapes. Sem ele o slide sai branco e o rodapé, que é texto branco,
    # some.
    fundo = origem_slide._element.cSld.find(qn("p:bg"))
    if fundo is not None:
        csld = novo._element.cSld
        antigo = csld.find(qn("p:bg"))
        if antigo is not None:
            csld.remove(antigo)
        csld.insert(0, copy.deepcopy(fundo))
    return novo


def _mover(prs, slide, para_indice: int) -> None:
    lista = prs.slides._sldIdLst
    alvo = None
    for sld in lista:
        if prs.part.related_part(sld.get(qn("r:id"))) is slide.part:
            alvo = sld
            break
    lista.remove(alvo)
    lista.insert(para_indice, alvo)


def gerar(material: str, modelo: Path = MODELO) -> Path:
    prs = Presentation(str(modelo))
    for slide in prs.slides:
        for sh in slide.shapes:
            if sh.name.startswith(ETIQUETA):
                raise SystemExit("o modelo já tem os slides da tabela — nada a fazer.")

    origem = Presentation(material)
    s5 = prs.slides[SLIDE_POR_VIDA]
    layout = s5.slide_layout

    # Toda imagem que o modelo já tem, por conteúdo.
    por_hash = {}
    for slide in prs.slides:
        for rel in slide.part.rels.values():
            if not rel.is_external and rel.reltype.endswith("/image"):
                por_hash[_hash(rel.target_part)] = rel.target_part

    molde_escopo = _shape(s5, "TextBox 8").text_frame._txBody

    # ── Slide da tabela de preços ──
    tabela = _copiar_slide(prs, origem.slides[ORIGEM_TABELA], layout, por_hash)
    lista = _shape(tabela, "TextBox 8")
    novo_corpo = copy.deepcopy(molde_escopo)
    lista._element.replace(lista._element.txBody, novo_corpo)
    _texto_unico(lista, "{{FAIXA_ITEM}}")
    # Ocupa o lugar da imagem que saiu.
    lista.left, lista.top = 3657600, 2550000
    lista.width, lista.height = 11071516, 2700000
    _texto_unico(_shape(tabela, "TextBox 15"), RODAPE)
    lista.name = f"{ETIQUETA}tabela"

    # ── Slide do escopo com mensalidade ──
    escopo = _copiar_slide(prs, origem.slides[ORIGEM_ESCOPO], layout, por_hash)
    caixa = _shape(escopo, "TextBox 8")
    caixa._element.replace(caixa._element.txBody, copy.deepcopy(molde_escopo))
    _texto_unico(_shape(escopo, "TextBox 16"), "QTDE. VIDAS: {{VIDAS}}")
    _texto_unico(_shape(escopo, "TextBox 24"), "{{MENSALIDADE}}")
    _texto_unico(_shape(escopo, "TextBox 25"), "Mensalidade")
    for vazio in ("TextBox 18", "TextBox 19"):
        sh = _shape(escopo, vazio)
        sh._element.getparent().remove(sh._element)
    caixa.name = f"{ETIQUETA}tabela"

    # Etiqueta do slide por vida.
    _shape(s5, "TextBox 8").name = f"{ETIQUETA}por_vida"

    # Ordem: 1-4, 5 por vida, 6 tabela, 7 escopo tabela, 8 fechamento.
    _mover(prs, tabela, SLIDE_POR_VIDA + 1)
    _mover(prs, escopo, SLIDE_POR_VIDA + 2)

    prs.save(str(modelo))
    return modelo


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    print(f"Modelo atualizado: {gerar(sys.argv[1])}")
