"""
Extrai as fontes embutidas no modelo .pptx para arquivos .ttf/.otf.

    python -m scripts.extrair_fontes_modelo [destino]

## Para que serve

O PPTX carrega as fontes da marca embutidas (Codec Pro, Poppins), então
ele abre certo em qualquer PowerPoint. O LibreOffice, que é quem converte
para PDF no servidor, NÃO usa fonte embutida de pptx: ele substitui pela
mais parecida que estiver instalada — e o slide sai com o texto
transbordando das caixas, "INVESTIMENTO" partido ao meio e o quadro de
valores desalinhado.

Instalando estas fontes no servidor, o PDF sai igual ao PPTX.

## O que sai e o que não sai

As .fntdata do PPTX estão em formato EOT. As não comprimidas trazem o TTF/
OTF inteiro no fim do arquivo, e são essas que este script recupera — na
prática, as que os slides 5 e 6 usam. As comprimidas (MTX) precisariam de
um descompressor próprio e são ignoradas: se faltar alguma, o LibreOffice
substitui só aquela.

## Licença

As fontes vêm do material que a Controller MedSeg produziu e são usadas
aqui para renderizar esse mesmo material. Não redistribua os arquivos
extraídos para fora do servidor da aplicação.
"""
from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELO = RAIZ / "templates" / "proposta_modelo.pptx"

# Flag TTEMBED_TTCOMPRESSED no cabeçalho do EOT.
COMPRIMIDO = 0x00000004

ASSINATURAS = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")


def _corpo_da_fonte(dados: bytes) -> bytes | None:
    """Devolve o TTF/OTF de dentro do EOT, ou None se não der para extrair."""
    if len(dados) < 16:
        return None
    _eot_size, font_size, _versao, flags = struct.unpack_from("<IIII", dados, 0)
    if flags & COMPRIMIDO:
        return None
    if font_size <= 0 or font_size > len(dados):
        return None
    corpo = dados[len(dados) - font_size:]
    return corpo if corpo[:4] in ASSINATURAS else None


def extrair(modelo: Path, destino: Path) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []

    with zipfile.ZipFile(modelo) as z:
        nomes = [n for n in z.namelist() if n.startswith("ppt/fonts/")]
        for nome in sorted(nomes):
            corpo = _corpo_da_fonte(z.read(nome))
            if corpo is None:
                continue
            extensao = "otf" if corpo[:4] == b"OTTO" else "ttf"
            saida = destino / f"{Path(nome).stem}.{extensao}"
            saida.write_bytes(corpo)
            escritos.append(saida)
    return escritos


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fontes-proposta")
    if not MODELO.is_file():
        print(f"ERRO: modelo não encontrado em {MODELO}")
        return 1

    escritos = extrair(MODELO, destino)
    if not escritos:
        print("Nenhuma fonte pôde ser extraída (todas comprimidas).")
        return 1

    for caminho in escritos:
        print(f"  {caminho}  ({caminho.stat().st_size // 1024} KB)")
    print(f"\n{len(escritos)} fonte(s) em {destino}")
    print("No servidor: copie para /usr/share/fonts/hipo/ e rode 'fc-cache -f'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
