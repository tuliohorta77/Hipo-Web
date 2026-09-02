"""
Confere que o modelo .pptx da proposta ainda serve.

    python -m scripts.conferir_modelo_proposta

Sai com 0 se estiver tudo certo, 1 e uma mensagem do que houve se não.

## Por que existe

O modelo é um binário de 16 MB versionado no repositório. Trocá-lo é o
caminho normal quando o marketing entrega arte nova — e é também o jeito
mais fácil de quebrar a feature em silêncio: basta um marcador perdido no
caminho para a proposta sair com campo em branco, e ninguém percebe até o
cliente receber.

Este script é chamado pelo deploy ANTES do push. Ele faz duas perguntas:

  1. os 14 marcadores estão no arquivo?
  2. preenchendo com números conhecidos, sai o que deveria sair?

A segunda pega o que a primeira não pega: marcador presente mas em runs
partidos, molde de escopo que sumiu, texto substituído no lugar errado.

## Por que não ficou embutido no .ps1

Estava. Uma linha de Python dentro de aspas duplas do PowerShell, com
'R$ 4.000,00' no meio — e o '$' precisou de escape para o PowerShell não
interpolar, o que fez o Python receber 'R\\$' e o assert falhar num deploy
que estava perfeito. Verificação frágil dá alarme falso, e alarme falso
ensina a ignorar o alarme.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from decimal import Decimal
from io import BytesIO

from services import proposta as regras
from services import proposta_render as render

MARCADORES = {
    "{{ESCOPO_ITEM}}", "{{VIDAS}}", "{{VALOR_VIDA}}", "{{MENSALIDADE}}",
    "{{TREINAMENTOS}}", "{{LAUDOS}}", "{{INVESTIMENTO}}", "{{CLIENTE}}",
    "{{EXECUTIVO_NOME}}", "{{EXECUTIVO_EMAIL}}", "{{EXECUTIVO_TELEFONE}}",
    "{{CIDADE}}", "{{DATA_EXTENSO}}", "{{VALIDADE}}",
}

# Os números do material original. Se a conta mudar, é para doer aqui.
CLIENTE = "CLIENTE DE TESTE LTDA"
VIDAS = 50
VALOR_VIDA = Decimal("20")
TREINAMENTOS = Decimal("2000")
LAUDOS = Decimal("1000")


def _texto(prs) -> str:
    return "\n".join(
        shape.text_frame.text
        for slide in prs.slides for shape in slide.shapes
        if shape.has_text_frame
    )


def conferir() -> list[str]:
    """Devolve a lista de problemas. Vazia = tudo certo."""
    problemas: list[str] = []

    try:
        Presentation = render._presentation()
    except render.BibliotecaIndisponivel as erro:
        return [str(erro)]

    if not render.CAMINHO_MODELO.is_file():
        return [f"modelo não encontrado em {render.CAMINHO_MODELO}"]

    # 1. Os marcadores estão lá?
    achados = set(re.findall(r"\{\{\w+\}\}", _texto(Presentation(str(render.CAMINHO_MODELO)))))
    faltando = MARCADORES - achados
    if faltando:
        problemas.append(f"marcadores ausentes no modelo: {sorted(faltando)}")
        return problemas

    # 2. Preenchido, sai o que deveria?
    subs = regras.substituicoes(
        cliente=CLIENTE, vidas=VIDAS, valor_por_vida=VALOR_VIDA,
        treinamentos=TREINAMENTOS, laudos=LAUDOS,
        executivo_nome="Fulano de Tal", executivo_email="fulano@exemplo.com",
        executivo_telefone="11 90000-0000",
        data_proposta=date(2026, 8, 26), validade=date(2026, 9, 5),
    )
    escopo = regras.ESCOPO_PADRAO + ["Item extra de conferência"]
    texto = _texto(Presentation(BytesIO(render.montar_pptx(subs, escopo))))

    sobrou = sorted(set(re.findall(r"\{\{\w+\}\}", texto)))
    if sobrou:
        problemas.append(f"marcador não substituído no arquivo gerado: {sobrou}")

    esperado = {
        "cliente": CLIENTE,
        "quantidade de vidas": f"QTDE. VIDAS: {VIDAS}",
        "valor por vida": regras.moeda(VALOR_VIDA),
        "mensalidade": regras.moeda(regras.mensalidade(VIDAS, VALOR_VIDA)),
        "investimento": regras.moeda(
            regras.investimento(regras.mensalidade(VIDAS, VALOR_VIDA),
                                TREINAMENTOS, LAUDOS)
        ),
        "data por extenso": "26 de agosto de 2026",
        "validade": "05/09/2026",
        "primeiro item do escopo": regras.ESCOPO_PADRAO[0],
        "item extra do escopo": "Item extra de conferência",
        "telefone do executivo": "11 90000-0000",
    }
    for rotulo, trecho in esperado.items():
        if trecho not in texto:
            problemas.append(f"{rotulo}: esperava encontrar {trecho!r} no arquivo")

    return problemas


def main() -> int:
    problemas = conferir()
    if problemas:
        print("MODELO COM PROBLEMA:")
        for p in problemas:
            print(f"  - {p}")
        print("\nSe você trocou a arte, rode: python -m scripts.gerar_modelo_proposta <arquivo novo>")
        return 1

    print(f"modelo OK: {len(MARCADORES)} marcadores, proposta de teste "
          f"conferida (investimento "
          f"{regras.moeda(regras.investimento(regras.mensalidade(VIDAS, VALOR_VIDA), TREINAMENTOS, LAUDOS))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
