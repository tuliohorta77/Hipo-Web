"""
HIPO — Modelo do contrato: preenchimento do .docx e posição das assinaturas
(entrega 053). Sem banco e sem LibreOffice: roda no Windows e no CI.

O teste do modelo versionado (TestModeloVersionado) é o que impede o
contrato de sair com `{{CAMPO}}` impresso depois que alguém editar o .docx
no Word.
"""
import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest

# lxml vem com o python-pptx (CI e EC2 têm). No venv do Windows pode faltar:
# aí este arquivo é pulado em vez de derrubar o pré-voo do deploy -- o CI
# roda de qualquer jeito.
etree = pytest.importorskip("lxml.etree", reason="lxml não instalado (vem com o python-pptx)")

from services import contrato as regras
from services import contrato_render as render
from services import proposta as pr

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_com(paragrafos: list[list[tuple[str, bool]]]) -> bytes:
    """Um .docx mínimo: cada parágrafo é uma lista de runs (texto, negrito)."""
    corpo = []
    for runs in paragrafos:
        rs = []
        for texto, negrito in runs:
            rpr = "<w:rPr><w:b/></w:rPr>" if negrito else ""
            rs.append(f'<w:r>{rpr}<w:t xml:space="preserve">{texto}</w:t></w:r>')
        corpo.append(f"<w:p>{''.join(rs)}</w:p>")
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 f'<w:document xmlns:w="{W_NS}"><w:body>{"".join(corpo)}</w:body></w:document>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", documento)
    return saida.getvalue()


def paragrafos(docx: bytes) -> list[list[tuple[str, bool]]]:
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        raiz = etree.fromstring(z.read("word/document.xml"))
    w = f"{{{W_NS}}}"
    saida = []
    for p in raiz.iter(f"{w}p"):
        runs = []
        for r in p.iter(f"{w}r"):
            t = r.find(f"{w}t")
            negrito = r.find(f"{w}rPr/{w}b") is not None
            runs.append((t.text or "" if t is not None else "", negrito))
        saida.append(runs)
    return saida


def texto(docx: bytes) -> list[str]:
    return ["".join(t for t, _ in p) for p in paragrafos(docx)]


class TestPreencher:
    def test_campo_simples(self):
        out = render.preencher(docx_com([[("Sede: {{CIDADE}}.", False)]]),
                               {"CIDADE": "Guarulhos"}, {})
        assert texto(out) == ["Sede: Guarulhos."]

    def test_campo_quebrado_pelo_word(self):
        """O Word reparte o campo em runs ao corrigir uma letra no meio."""
        doc = docx_com([[("Vence todo dia {{DIA_", False), ("VENCI", False),
                         ("MENTO}} de cada mês", False)]])
        out = render.preencher(doc, {"DIA_VENCIMENTO": "10"}, {})
        assert texto(out) == ["Vence todo dia 10 de cada mês"]

    def test_negrito_vizinho_fica(self):
        doc = docx_com([[("{{CONTRATANTE_RAZAO_SOCIAL}}", False),
                         (", denominada ", False), ("CONTRATANTE", True)]])
        out = render.preencher(doc, {"CONTRATANTE_RAZAO_SOCIAL": "Alfa & Cia <Ltda>"}, {})
        [runs] = paragrafos(out)
        assert runs[0] == ("Alfa & Cia <Ltda>", False)
        assert runs[2] == ("CONTRATANTE", True)

    def test_dois_campos_no_mesmo_paragrafo(self):
        doc = docx_com([[("{{CIDADE}}, {{DATA_EXTENSO}}.", False)]])
        out = render.preencher(doc, {"CIDADE": "Guarulhos",
                                     "DATA_EXTENSO": "08 de outubro de 2026"}, {})
        assert texto(out) == ["Guarulhos, 08 de outubro de 2026."]

    def test_campo_com_espacos_dentro(self):
        out = render.preencher(docx_com([[("{{ CIDADE }}", False)]]), {"CIDADE": "X"}, {})
        assert texto(out) == ["X"]

    def test_lista_repete_o_paragrafo(self):
        doc = docx_com([[("antes", False)], [("{{PRECO_LINHA}}", False)], [("depois", False)]])
        out = render.preencher(doc, {}, {"PRECO_LINHA": ["a;", "b."]})
        assert texto(out) == ["antes", "a;", "b.", "depois"]

    def test_lista_vazia_apaga_o_paragrafo(self):
        doc = docx_com([[("antes", False)], [("{{CNPJ_", False), ("ADICIONAL}}", False)],
                        [("depois", False)]])
        out = render.preencher(doc, {}, {"CNPJ_ADICIONAL": []})
        assert texto(out) == ["antes", "depois"]

    def test_campo_desconhecido_e_recusado(self):
        with pytest.raises(render.ModeloInvalido, match="QUALQUER"):
            render.preencher(docx_com([[("{{QUALQUER}}", False)]]), {}, {})

    def test_lista_no_meio_do_texto_e_recusada(self):
        with pytest.raises(render.ModeloInvalido, match="sozinho"):
            render.preencher(docx_com([[("Preço: {{PRECO_LINHA}}", False)]]), {},
                             {"PRECO_LINHA": ["x"]})


class TestModeloVersionado:
    def test_modelo_sem_problemas(self):
        assert render.conferir_modelo(render.ler_modelo()) == []

    def test_usa_todos_os_campos(self):
        usados = render.campos_do_modelo(render.ler_modelo())
        assert usados == set(regras.CAMPOS_SIMPLES) | set(regras.CAMPOS_LISTA)

    def test_preenchido_nao_sobra_campo(self):
        proposta = {
            "modalidade": "tabela", "tabela_preco": pr.normalizar_tabela(pr.TABELA_PADRAO),
            "valor_vida_excedente": Decimal("15"), "valor_por_vida": None,
            "itens": [{"cnpj": "08363161000151", "razao_social": "Porto Pisos Elevados Ltda.",
                       "vidas": 8, "mensalidade": Decimal("220"), "valor_tabela": Decimal("220")}],
            "treinamentos": Decimal("0"), "laudos": Decimal("0"), "cidade": "Guarulhos",
        }
        conta = {"razao_social": "Porto Pisos Elevados Ltda.", "cnpj": "08363161000151",
                 "logradouro": "Rua A", "numero": "1", "bairro": "B", "cidade": "Guarulhos",
                 "uf": "SP", "cep": "07111000"}
        simples, listas = regras.campos(proposta=proposta, conta=conta,
                                        data_contrato=date(2026, 10, 8),
                                        inicio_vigencia=date(2026, 10, 9), dia_vencimento=10)
        out = render.preencher(render.ler_modelo(), simples, listas)
        assert render.campos_do_modelo(out) == set()
        tudo = "\n".join(texto(out))
        assert "08.363.161/0001-51" in tudo
        assert "vigorará a partir de 09 de outubro de 2026" in tudo
        assert "Guarulhos, 08 de outubro de 2026." in tudo

    def test_conferir_acusa_campo_obrigatorio_faltando(self):
        assert "campo obrigatório ausente: {{PRECO_LINHA}}" in render.conferir_modelo(
            docx_com([[("{{CONTRATANTE_RAZAO_SOCIAL}} {{CONTRATANTE_CNPJ}}", False)]])
        )


class TestPdf:
    def test_sem_libreoffice(self, monkeypatch):
        monkeypatch.setattr(render, "libreoffice_disponivel", lambda: None)
        with pytest.raises(render.ContratoPdfIndisponivel, match="LibreOffice"):
            render.para_pdf(b"x")

    def test_modelo_ausente(self, tmp_path):
        with pytest.raises(render.ModeloContratoIndisponivel):
            render.ler_modelo(tmp_path / "nao-existe.docx")


def pdf_com_textos(paginas: list[list[tuple[float, float, str]]]) -> bytes:
    """PDF mínimo (A4), escrito à mão: cada página com textos em (x, y)."""
    objetos: list[bytes] = []
    n_pag = len(paginas)
    # 1 catálogo, 2 páginas, 3 fonte, depois (página, conteúdo) por página.
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pag))
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pag} >>".encode())
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, textos in enumerate(paginas):
        fluxo = "".join(f"BT /F1 11 Tf {x} {y} Td ({t}) Tj ET\n" for x, y, t in textos).encode()
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objetos.append(b"<< /Length %d >>\nstream\n" % len(fluxo) + fluxo + b"endstream")
    saida = io.BytesIO()
    saida.write(b"%PDF-1.4\n")
    offsets = []
    for n, corpo in enumerate(objetos, start=1):
        offsets.append(saida.tell())
        saida.write(f"{n} 0 obj\n".encode() + corpo + b"\nendobj\n")
    xref = saida.tell()
    saida.write(f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode())
    for o in offsets:
        saida.write(f"{o:010d} 00000 n \n".encode())
    saida.write(f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n".encode())
    return saida.getvalue()


class TestLocalizarAssinaturas:
    def test_quatro_rotulos_na_ultima_pagina(self):
        pdf = pdf_com_textos([
            [(72, 700, "A CONTRATANTE pagara a Contratada")],
            [(72, 500, "Contratante"), (72, 400, "Contratada"),
             (72, 300, "Testemunha"), (72, 200, "Testemunha")],
        ])
        pos = render.localizar_assinaturas(pdf)
        assert set(pos) == set(regras.CHAVES_PAPEIS)
        assert all(p["z"] == 2 for p in pos.values())
        assert float(pos["contratante"]["x"]) == pytest.approx(72 / 595 * 100, abs=0.1)
        # De cima para baixo, na ordem do bloco; acima do rótulo.
        ys = [float(pos[k]["y"]) for k in ("contratante", "contratada",
                                           "testemunha_contratante", "testemunha_contratada")]
        assert ys == sorted(ys)
        assert ys[0] == pytest.approx((842 - 500 - render.SUBIR_CARIMBO_PT) / 842 * 100, abs=0.1)

    def test_rotulo_que_falta_fica_de_fora(self):
        pdf = pdf_com_textos([[(72, 500, "Contratante")]])
        assert set(render.localizar_assinaturas(pdf)) == {"contratante"}

    def test_pdf_invalido(self):
        assert render.localizar_assinaturas(b"nao e pdf") == {}
