"""
HIPO — Ensaio do contrato no servidor (entrega 053). NÃO manda nada.

Preenche o modelo com dados de exemplo, converte em PDF pelo LibreOffice e
mostra onde cada assinatura seria desenhada. É a conferência do deploy:
prova que o modelo está no lugar, que o LibreOffice da EC2 tem o Writer
(o da proposta só precisou do Impress) e que a configuração da Autentique
está completa.

    cd /home/hipo/app/api
    python3 -m scripts.ensaiar_contrato                 # só confere
    python3 -m scripts.ensaiar_contrato --pdf /tmp/c.pdf  # e grava o PDF

Saída 0 = pronto para enviar; 1 = algo falta (a mensagem diz o quê).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from decimal import Decimal

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])  # permite rodar de api/

from services import autentique  # noqa: E402
from services import contrato as regras  # noqa: E402
from services import contrato_render as render  # noqa: E402
from services import proposta as pr  # noqa: E402

PROPOSTA = {
    "modalidade": "tabela",
    "tabela_preco": pr.normalizar_tabela(pr.TABELA_PADRAO),
    "valor_vida_excedente": Decimal("15.00"),
    "valor_por_vida": None,
    "itens": [{"cnpj": "11222333000181", "razao_social": "Empresa de Ensaio Ltda.",
               "vidas": 8, "mensalidade": Decimal("220.00"), "valor_tabela": Decimal("220.00")}],
    "treinamentos": Decimal("0"), "laudos": Decimal("0"), "cidade": "Guarulhos",
}
CONTA = {
    "razao_social": "Empresa de Ensaio Ltda.", "cnpj": "11222333000181",
    "logradouro": "Rua do Ensaio", "numero": "100", "bairro": "Centro",
    "cidade": "Guarulhos", "uf": "SP", "cep": "07000000",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Ensaio do contrato (não envia)")
    ap.add_argument("--pdf", help="grava o PDF de ensaio neste caminho")
    args = ap.parse_args()

    problemas = autentique.problemas()
    print(f"sandbox: {autentique.em_sandbox()}")
    print(f"modelo:  {render.caminho_do_modelo()}")

    try:
        modelo = render.ler_modelo()
    except render.ModeloContratoIndisponivel as e:
        print(f"ERRO: {e}")
        return 1
    conferencia = render.conferir_modelo(modelo)
    if conferencia:
        print("ERRO no modelo: " + "; ".join(conferencia))
        return 1

    hoje = date.today()
    simples, listas = regras.campos(proposta=PROPOSTA, conta=CONTA, data_contrato=hoje,
                                    inicio_vigencia=regras.inicio_vigencia_padrao(hoje),
                                    dia_vencimento=10)
    inicio = time.monotonic()
    try:
        pdf = render.montar_pdf(simples, listas)
    except (render.ModeloInvalido, render.ContratoPdfIndisponivel) as e:
        print(f"ERRO no PDF: {e}")
        return 1
    print(f"PDF:     {len(pdf) // 1024} KB em {time.monotonic() - inicio:.1f}s")

    posicoes = render.localizar_assinaturas(pdf)
    for p in regras.PAPEIS:
        pos = posicoes.get(p.chave)
        print(f"  {p.rotulo:28} " + (f"página {pos['z']}, x={pos['x']}%, y={pos['y']}%"
                                     if pos else "NÃO ENCONTRADO (assina só na página de auditoria)"))
    if args.pdf:
        with open(args.pdf, "wb") as f:
            f.write(pdf)
        print(f"gravado em {args.pdf}")

    if problemas:
        print("FALTA para enviar: " + "; ".join(problemas))
        return 1
    print("OK: pronto para enviar contrato.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
