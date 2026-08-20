"""
HIPO — Testes puros do fechamento: render do e-mail e fallback da IA.

Sem banco e sem rede: rodam no pytest local do Windows.
"""
from __future__ import annotations

from datetime import date

import pytest

from services import ia, relatorio_render as r

pytestmark = pytest.mark.anyio


METRICAS = {
    "dia": "2026-08-17",
    "fuso": "America/Sao_Paulo",
    "adocao": {
        "acoes": 120, "pessoas_ativas": 3, "erros": 2, "taxa_erro_pct": 1.7,
        "requests_anonimas": 0, "latencia_media_ms": 40, "latencia_p95_ms": 180,
        "por_pessoa": [
            {"nome": "Aline Martins", "cargo": "EC", "acoes": 80, "telas": 6,
             "primeira": "2026-08-17T09:12:00-03:00",
             "ultima": "2026-08-17T18:03:00-03:00", "erros": 1},
        ],
        "por_modulo": [{"modulo": "crm", "acoes": 100}],
        "rotas_mais_usadas": [
            {"metodo": "GET", "rota": "/crm/contas", "acoes": 50, "media_ms": 30},
        ],
        "erros_por_rota": [
            {"metodo": "POST", "rota": "/crm/contas", "status": 422, "ocorrencias": 2},
        ],
        "sem_acesso_hoje": [{"nome": "Bruno Gonçalo", "cargo": "EV"}],
    },
    "operacao": {
        "contas_criadas": 4, "contatos_criados": 3, "oportunidades_criadas": 2,
        "mudancas_de_fase": 5, "reaberturas": 0, "conquistadas": 1, "perdidas": 0,
        "tarefas_criadas": 6, "tarefas_concluidas": 4, "tarefas_em_atraso": 2,
        "parceiros_marcados": 0, "parceiros_transferidos": 0, "parceiros_atribuidos": 0,
        "carteira_parceiros": 55, "parceiros_sem_ec": 0,
    },
    "comparativo": {
        "disponivel": True, "dia": "2026-08-14", "acoes": 90, "pessoas_ativas": 4,
        "oportunidades_criadas": 3, "tarefas_concluidas": 4,
    },
}


class TestFormatacao:
    def test_data_por_extenso(self):
        assert r.data_por_extenso(date(2026, 8, 17)) == "segunda-feira, 17 de agosto de 2026"

    def test_hora_curta(self):
        assert r.hora_curta("2026-08-17T14:32:05-03:00") == "14:32"
        assert r.hora_curta(None) == "—"
        assert r.hora_curta("nao-e-data") == "—"

    def test_variacao(self):
        assert r.variacao(120, 90) == "+30 vs. dia anterior"
        assert r.variacao(80, 90) == "-10 vs. dia anterior"
        assert r.variacao(90, 90) == "igual ao dia anterior"
        assert r.variacao(10, None) == ""

    def test_assunto_resume_o_dia(self):
        assert r.assunto(METRICAS) == "HIPO 17/08 — 3 pessoas, 2 oportunidades"

    def test_assunto_no_singular(self):
        m = {"dia": "2026-08-17", "adocao": {"pessoas_ativas": 1},
             "operacao": {"oportunidades_criadas": 1}}
        assert r.assunto(m) == "HIPO 17/08 — 1 pessoa, 1 oportunidade"


class TestHtml:
    def test_contem_os_numeros_e_os_nomes(self):
        html = r.montar_html(METRICAS)
        for esperado in ["120", "Aline Martins", "/crm/contas", "55", "Bruno Gonçalo"]:
            assert esperado in html, f"faltou {esperado!r} no e-mail"

    def test_sem_narrativa_nao_desenha_a_secao(self):
        assert "Leitura gerada por IA" not in r.montar_html(METRICAS)

    def test_com_narrativa_desenha(self):
        html = r.montar_html(METRICAS, "Primeiro parágrafo.\nSegundo parágrafo.")
        assert "Primeiro parágrafo." in html
        assert "Segundo parágrafo." in html
        assert "Leitura gerada por IA" in html

    def test_escapa_html_de_nome(self):
        """
        Nome com < ou & viraria tag no cliente de e-mail. O dado vem de campo
        livre digitado por usuário — tratar como HTML confiável é injeção.
        """
        m = dict(METRICAS)
        m["adocao"] = dict(METRICAS["adocao"])
        m["adocao"]["por_pessoa"] = [{
            "nome": "<script>alerta()</script>", "cargo": "EC", "acoes": 1,
            "telas": 1, "primeira": None, "ultima": None, "erros": 0,
        }]
        html = r.montar_html(m)
        assert "<script>alerta()" not in html
        assert "&lt;script&gt;" in html

    def test_dia_vazio_nao_quebra(self):
        vazio = {"dia": "2026-08-16", "fuso": "America/Sao_Paulo",
                 "adocao": {"acoes": 0, "pessoas_ativas": 0, "erros": 0,
                            "taxa_erro_pct": None, "latencia_media_ms": 0,
                            "latencia_p95_ms": 0, "por_pessoa": [], "por_modulo": [],
                            "rotas_mais_usadas": [], "erros_por_rota": [],
                            "sem_acesso_hoje": []},
                 "operacao": {}, "comparativo": {"disponivel": False}}
        html = r.montar_html(vazio)
        assert "Nada no período." in html
        assert "<!DOCTYPE html>" in html

    def test_html_fecha_o_documento(self):
        assert r.montar_html(METRICAS).rstrip().endswith("</html>")


class TestTexto:
    def test_versao_texto_tem_o_essencial(self):
        txt = r.montar_texto(METRICAS, "Resumo do dia.")
        assert "HIPO — FECHAMENTO DO DIA" in txt
        assert "Resumo do dia." in txt
        assert "Aline Martins" in txt
        assert "NÃO ACESSARAM HOJE" in txt
        assert "<" not in txt, "a versão texto não pode conter marcação"

    def test_dia_sem_ninguem(self):
        m = dict(METRICAS)
        m["adocao"] = dict(METRICAS["adocao"], por_pessoa=[], sem_acesso_hoje=[])
        assert "ninguém usou o sistema hoje" in r.montar_texto(m)


class TestIaFallback:
    async def test_sem_chave_devolve_none_sem_chamar_rede(self, monkeypatch):
        """
        A regra central da IA aqui: ausência de chave não é erro, é modo
        degradado. O fechamento tem que seguir e o e-mail tem que sair.
        """
        monkeypatch.setattr(ia.settings, "ANTHROPIC_API_KEY", "")
        assert await ia.narrar(METRICAS) == (None, None)

    async def test_erro_de_rede_nao_levanta(self, monkeypatch):
        monkeypatch.setattr(ia.settings, "ANTHROPIC_API_KEY", "chave-de-teste")

        class ClienteQuebrado:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                raise ConnectionError("sem rede")

        monkeypatch.setattr(ia.httpx, "AsyncClient", lambda **kw: ClienteQuebrado())
        assert await ia.narrar(METRICAS) == (None, None)

    async def test_resposta_ok_extrai_o_texto(self, monkeypatch):
        monkeypatch.setattr(ia.settings, "ANTHROPIC_API_KEY", "chave-de-teste")
        monkeypatch.setattr(ia.settings, "ANTHROPIC_MODEL", "modelo-x")

        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"content": [{"type": "text", "text": "O dia rendeu."}]}

        class Cliente:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                return Resp()

        monkeypatch.setattr(ia.httpx, "AsyncClient", lambda **kw: Cliente())
        assert await ia.narrar(METRICAS) == ("O dia rendeu.", "modelo-x")

    async def test_http_de_erro_devolve_none(self, monkeypatch):
        monkeypatch.setattr(ia.settings, "ANTHROPIC_API_KEY", "chave-de-teste")

        class Resp:
            status_code = 401
            text = '{"error":"invalid api key"}'

        class Cliente:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                return Resp()

        monkeypatch.setattr(ia.httpx, "AsyncClient", lambda **kw: Cliente())
        assert await ia.narrar(METRICAS) == (None, None)

    def test_prompt_proibe_inventar_numero(self):
        """
        O contrato com o modelo está no texto da instrução. Se alguém suavizar
        essa linha, o relatório passa a poder mentir — e este teste cai.
        """
        assert "NÃO invente" in ia.INSTRUCAO
