"""
Enxuga as imagens do modelo da proposta (entrega 052).

    python -m scripts.otimizar_modelo_proposta            # o modelo versionado
    python -m scripts.otimizar_modelo_proposta arquivo.pptx

## Por que

O modelo tinha 17 MB, quase tudo imagem. Toda proposta abre e salva o
arquivo inteiro (python-pptx) e o LibreOffice processa cada imagem ao
gerar o PDF — era a maior parte dos ~20 s que o visualizador levava.

A pior delas era a textura de linho do slide de fechamento: PNG RGBA de
2000x2000 e 8 MB, aplicada a 35% de opacidade. Ela é cinza pura (R=G=B),
então vira PNG cinza+alfa (metade dos canais, sem perda) e cabe em 1000 px
— na tela não há diferença (conferido em imagem lado a lado).

## Regras (iguais para qualquer arte nova)

  * PNG em que R, G e B são iguais em todo pixel: vira cinza (+ alfa) —
    sem perda de informação.
  * Textura grande (lado > LADO_TEXTURA e cinza): reduzida a LADO_TEXTURA.
  * Qualquer imagem com lado maior que LADO_MAXIMO: reduzida a ele. Em 200
    dpi, que é a resolução do PDF, 2000 px cobrem 10 polegadas — mais que
    a largura de qualquer imagem do material.
  * Só troca a imagem se o resultado for MENOR que o original.

Os nomes e caminhos das imagens não mudam (o XML dos slides aponta para
eles); só o conteúdo é regravado.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELO = RAIZ / "templates" / "proposta_modelo.pptx"

LADO_MAXIMO = 2000
LADO_TEXTURA = 1000
QUALIDADE_JPEG = 90


def _cinza(im) -> bool:
    from PIL import ImageChops
    if im.mode not in ("RGB", "RGBA"):
        return False
    r, g, b = im.convert("RGB").split()
    return (ImageChops.difference(r, g).getbbox() is None
            and ImageChops.difference(g, b).getbbox() is None)


def otimizar_imagem(nome: str, dados: bytes) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(dados))
    formato = im.format
    im.load()

    if formato == "PNG" and _cinza(im):
        im = im.convert("LA" if "A" in im.getbands() else "L")
        if max(im.size) > LADO_TEXTURA:
            r = LADO_TEXTURA / max(im.size)
            im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    elif max(im.size) > LADO_MAXIMO:
        r = LADO_MAXIMO / max(im.size)
        im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)

    saida = io.BytesIO()
    if formato == "JPEG":
        im.convert("RGB").save(saida, "JPEG", quality=QUALIDADE_JPEG, optimize=True)
    else:
        im.save(saida, "PNG", optimize=True)
    novo = saida.getvalue()
    return novo if len(novo) < len(dados) else dados


def otimizar(origem: Path = MODELO, destino: Path | None = None) -> tuple[int, int]:
    destino = destino or origem
    with zipfile.ZipFile(origem) as zin:
        itens = [(info, zin.read(info.filename)) for info in zin.infolist()]

    antes = depois = 0
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, dados in itens:
            nome = info.filename.lower()
            if nome.startswith("ppt/media/") and nome.endswith((".png", ".jpg", ".jpeg")):
                novo = otimizar_imagem(nome, dados)
                antes += len(dados)
                depois += len(novo)
                dados = novo
            zout.writestr(info, dados)
    Path(destino).write_bytes(buffer.getvalue())
    return antes, depois


if __name__ == "__main__":
    alvo = Path(sys.argv[1]) if len(sys.argv) > 1 else MODELO
    a, d = otimizar(alvo)
    print(f"imagens: {a // 1024} KB -> {d // 1024} KB ({alvo})")
