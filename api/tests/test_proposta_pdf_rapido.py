"""
HIPO — PDF da proposta mais rápido (entrega 052). Sem banco, sem LibreOffice.

O LibreOffice é simulado por um conversor falso que devolve um PDF de
verdade com uma página por slide — a largura da página codifica o texto do
slide. Assim dá para provar, sem converter nada, que:

  1. os slides fixos são os institucionais (sem marcador, sem etiqueta);
  2. o PDF montado em partes (fixos do cache + variáveis) tem as mesmas
     páginas, na mesma ordem, que o PDF convertido inteiro;
  3. os fixos são convertidos uma vez só;
  4. sem pypdf, ou com PDF ilegível, cai no caminho inteiro;
  5. o cache por proposta guarda, devolve e limpa os mais antigos.
"""
import hashlib
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest

# No CI o pypdf vem do requirements; no Windows de quem roda o deploy pode
# faltar -- aí o arquivo é pulado em vez de derrubar o passo de testes.
pypdf = pytest.importorskip("pypdf")
Presentation = pytest.importorskip("pptx").Presentation
PdfReader, PdfWriter = pypdf.PdfReader, pypdf.PdfWriter

from services import proposta as regras
from services import proposta_render as render


def _largura(slide) -> int:
    texto = "".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)
    texto += str(len(list(slide.shapes)))
    return 100 + int(hashlib.sha1(texto.encode()).hexdigest(), 16) % 900


class ConversorFalso:
    """Faz o papel do LibreOffice: uma página por slide, largura = assinatura."""

    def __init__(self):
        self.chamadas = []

    def __call__(self, pptx: bytes) -> bytes:
        prs = Presentation(BytesIO(pptx))
        self.chamadas.append(len(prs.slides))
        w = PdfWriter()
        for slide in prs.slides:
            w.add_blank_page(width=_largura(slide), height=100)
        b = BytesIO()
        w.write(b)
        return b.getvalue()


def _larguras(pdf: bytes) -> list[int]:
    return [round(float(p.mediabox.width)) for p in PdfReader(BytesIO(pdf)).pages]


def _entrada(modalidade="tabela"):
    faixas = regras.normalizar_tabela(regras.TABELA_PADRAO)
    itens = regras.calcular_itens(
        modalidade=modalidade,
        itens=[{"cnpj": "11222333000181", "razao_social": "ALFA LTDA", "vidas": 18}],
        valor_por_vida=Decimal("20") if modalidade == "por_vida" else None,
        faixas=faixas,
    )
    linhas = regras.linhas_da_lista(modalidade=modalidade, escopo=["PGR"], itens=itens,
                                    faixas=faixas)
    subs = regras.substituicoes(
        cliente="ALFA LTDA", vidas=18,
        valor_por_vida=Decimal("20") if modalidade == "por_vida" else None,
        treinamentos=Decimal(0), laudos=Decimal(0), executivo_nome="Bruno",
        executivo_email="b@x", executivo_telefone="1",
        data_proposta=date(2026, 10, 7), validade=date(2026, 10, 17),
        mensal=regras.total_itens(itens), qtd_cnpjs=1, valor_excedente=Decimal("15"),
    )
    return subs, linhas


@pytest.fixture
def falso(monkeypatch, tmp_path):
    monkeypatch.setenv("HIPO_CACHE_PROPOSTAS", str(tmp_path))
    conv = ConversorFalso()
    monkeypatch.setattr(render, "para_pdf", conv)
    return conv


class TestSlidesFixos:
    def test_sao_os_institucionais(self):
        prs = Presentation(str(render.CAMINHO_MODELO))
        fixos = [i for i, s in enumerate(prs.slides) if render._slide_fixo(s)]
        assert fixos == [0, 1, 2, 3]

    def test_slide_de_modalidade_nunca_e_fixo(self):
        prs = Presentation(str(render.CAMINHO_MODELO))
        for s in prs.slides:
            if render._modalidade_do_slide(s) is not None:
                assert not render._slide_fixo(s)


class TestMontarPdf:
    @pytest.mark.parametrize("modalidade", ["tabela", "por_vida"])
    def test_mesmas_paginas_e_ordem_que_o_inteiro(self, falso, modalidade):
        subs, linhas = _entrada(modalidade)
        inteiro = falso(render.montar_pptx(subs, linhas, modalidade=modalidade))
        partes = render.montar_pdf(subs, linhas, modalidade=modalidade)
        assert _larguras(partes) == _larguras(inteiro)
        assert len(_larguras(partes)) == 6

    def test_fixos_convertidos_uma_vez(self, falso):
        subs, linhas = _entrada()
        render.montar_pdf(subs, linhas, modalidade="tabela")
        render.montar_pdf(subs, linhas, modalidade="tabela")
        render.montar_pdf(subs, linhas, modalidade="por_vida")
        # 1ª: fixos (4 slides) + variáveis (2). Depois, só os variáveis.
        assert falso.chamadas == [4, 2, 2, 2]

    def test_sem_pypdf_converte_inteiro(self, falso, monkeypatch):
        monkeypatch.setattr(render, "_pypdf", lambda: None)
        subs, linhas = _entrada()
        render.montar_pdf(subs, linhas, modalidade="tabela")
        assert falso.chamadas == [6]

    def test_pdf_ilegivel_cai_no_inteiro_e_nao_vai_para_o_cache(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HIPO_CACHE_PROPOSTAS", str(tmp_path))
        monkeypatch.setattr(render, "para_pdf", lambda pptx: b"%PDF-falso")
        subs, linhas = _entrada()
        assert render.montar_pdf(subs, linhas, modalidade="tabela") == b"%PDF-falso"
        assert not list(tmp_path.glob("fixos-*.pdf"))

    def test_aquecer_prepara_os_fixos(self, falso, monkeypatch):
        monkeypatch.setattr(render, "libreoffice_disponivel", lambda: "/usr/bin/soffice")
        assert render.aquecer_cache() is True
        subs, linhas = _entrada()
        render.montar_pdf(subs, linhas, modalidade="tabela")
        assert falso.chamadas == [4, 2]

    def test_aquecer_sem_libreoffice_nao_faz_nada(self, falso, monkeypatch):
        monkeypatch.setattr(render, "libreoffice_disponivel", lambda: None)
        assert render.aquecer_cache() is False
        assert falso.chamadas == []


class TestCacheDaProposta:
    def test_guarda_e_devolve(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HIPO_CACHE_PROPOSTAS", str(tmp_path))
        chave = render.chave_pdf("p1", None)
        assert render.pdf_do_cache(chave) is None
        render.guardar_pdf(chave, b"%PDF-1")
        assert render.pdf_do_cache(chave) == b"%PDF-1"

    def test_chave_separa_proposta_cnpj_e_versao_do_render(self, monkeypatch):
        a = render.chave_pdf("p1", None)
        assert a != render.chave_pdf("p1", "i1")
        assert a != render.chave_pdf("p2", None)
        monkeypatch.setattr(render, "VERSAO_RENDER", "999")
        assert a != render.chave_pdf("p1", None)

    def test_limpa_os_mais_antigos(self, monkeypatch, tmp_path):
        import os
        import time
        monkeypatch.setenv("HIPO_CACHE_PROPOSTAS", str(tmp_path))
        agora = time.time()
        for i in range(4):
            render.guardar_pdf(f"k{i}", b"x")
            os.utime(tmp_path / f"proposta-k{i}.pdf", (agora - 100 + i, agora - 100 + i))
        monkeypatch.setattr(render, "MAX_PDFS_EM_CACHE", 2)
        render.guardar_pdf("k9", b"x")
        restantes = sorted(p.name for p in tmp_path.glob("proposta-*.pdf"))
        assert len(restantes) == 2
        assert restantes == ["proposta-k3.pdf", "proposta-k9.pdf"]


class TestFiltro:
    def test_pdf_com_imagens_a_200_dpi(self):
        assert '"ReduceImageResolution":{"type":"boolean","value":"true"}' in render.FILTRO_PDF
        assert '"MaxImageResolution":{"type":"long","value":"200"}' in render.FILTRO_PDF
