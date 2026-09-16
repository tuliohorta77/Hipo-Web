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
    "atividades": {
        "total": 31,
        "oportunidades_trabalhadas": 17,
        "oportunidades_primeira_vez": 6,
        "horas": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
        "total_por_hora": [0, 0, 26, 0, 0, 0, 5, 0, 0, 0, 0],
        "por_pessoa": [
            {"nome": "Aline Martins", "cargo": "EC", "entrada": "08:20", "saida": "17:54",
             "total": 31, "oportunidades_trabalhadas": 17, "oportunidades_primeira_vez": 6,
             "por_hora": [0, 0, 26, 0, 0, 0, 5, 0, 0, 0, 0],
             "por_tipo": [
                 {"grupo": "Tarefas", "tipo": "Tarefa concluída", "qtd": 24},
                 {"grupo": "Tarefas", "tipo": "Tarefa criada", "qtd": 5},
                 {"grupo": "Anexos", "tipo": "Anexo enviado", "qtd": 2},
             ]},
            {"nome": "Jakeline Santana", "cargo": "EV", "entrada": "08:43", "saida": "17:32",
             "total": 0, "por_hora": [0] * 11, "por_tipo": []},
        ],
    },
    "reunioes": {
        "total": 3, "realizadas": 1, "canceladas": 0, "no_show": 1, "pendentes": 1,
        "taxa_realizacao_pct": 50.0,
        "por_anfitriao": [
            {"nome": "Bruno Gonçalo", "cargo": "EV", "total": 3, "realizadas": 1,
             "canceladas": 0, "no_show": 1, "pendentes": 1},
        ],
        "itens": [
            {"hora": "09:00", "anfitriao": "Bruno Gonçalo", "empresa": "Frigorifico Sao Jorge",
             "tipo": "DG · Diagnóstico", "modalidade": "Online",
             "agendado_por": "Kethlleen Gomes", "situacao": "realizada",
             "situacao_rotulo": "Realizada"},
            {"hora": "14:00", "anfitriao": "Bruno Gonçalo", "empresa": "Padaria Estrela",
             "tipo": "AP · Apresentação", "modalidade": "Online",
             "agendado_por": "Gabriel Lira", "situacao": "no_show",
             "situacao_rotulo": "No-show"},
            {"hora": "16:30", "anfitriao": "Bruno Gonçalo", "empresa": "Auto Pecas Lima",
             "tipo": "FC · Fechamento", "modalidade": "Presencial",
             "agendado_por": "Kethlleen Gomes", "situacao": "pendente",
             "situacao_rotulo": "Sem desfecho"},
        ],
        "agendamentos_total": 4,
        "agendamentos_por_pessoa": [
            {"nome": "Kethlleen Gomes", "cargo": "SDR", "qtd": 3},
            {"nome": "Gabriel Lira", "cargo": "SDR", "qtd": 1},
        ],
    },
    "comparativo": {
        "disponivel": True, "dia": "2026-08-14", "acoes": 90, "pessoas_ativas": 4,
        "oportunidades_criadas": 3, "tarefas_concluidas": 4, "atividades": 20,
        "oportunidades_trabalhadas": 12,
    },
    "conteudo": {
        "precisa_de_acao": [
            {"numero": "OPP-2026-00001", "conta": "Metalurgica Andrade",
             "fase": "negociacao", "status": "ativa", "temperatura": 80,
             "valor": 4200.0, "previsao": "2026-08-10",
             "motivos": ["previsão venceu há 7 dias", "sem próxima tarefa marcada"]},
        ],
        "precisa_de_acao_mais": 2,
        "perto_de_fechar": [
            {"numero": "OPP-2026-00003", "conta": "Frigorifico Sao Jorge",
             "fase": "negociacao", "status": "ativa", "temperatura": 90,
             "valor": 9500.0, "previsao": "2026-08-20",
             "motivos": ["temperatura 90"]},
        ],
        "perto_de_fechar_mais": 0,
        "parceiros_para_acionar": [
            {"conta": "Escritorio Aurora", "situacao": "dormente",
             "indicacoes": 4, "conquistadas": 2, "em_aberto": 0,
             "dias_sem_indicar": 238},
        ],
        "parceiros_para_acionar_mais": 0,
        "tarefas_atrasadas": [
            {"titulo": "Visita tecnica", "responsavel": "Aline Martins",
             "dias_atraso": 13, "alvo": "OPP-2026-00001"},
        ],
        "tarefas_atrasadas_total": 2,
        "totais": {"oportunidades_abertas": 5, "com_acao_pendente": 3,
                   "perto_de_fechar": 1},
    },
}


class TestFormatacao:
    def test_data_por_extenso(self):
        assert r.data_por_extenso(date(2026, 8, 17)) == "segunda-feira, 17 de agosto de 2026"

    def test_hora_curta(self):
        assert r.hora_curta("2026-08-17T14:32:05-03:00") == "14:32"

    def test_hora_curta_converte_utc_para_brasilia(self):
        """
        O e-mail de 15/09 mostrou a equipe entrando as 11h e saindo as 21h.
        Era o timestamptz em UTC formatado sem conversao.
        """
        assert r.hora_curta("2026-09-15T11:46:00+00:00") == "08:46"
        assert r.hora_curta("2026-09-15T23:54:00+00:00") == "20:54"
        assert r.hora_curta(None) == "—"
        assert r.hora_curta("nao-e-data") == "—"

    def test_variacao(self):
        assert r.variacao(120, 90) == "+30 vs. dia anterior"
        assert r.variacao(80, 90) == "-10 vs. dia anterior"
        assert r.variacao(90, 90) == "igual ao dia anterior"
        assert r.variacao(10, None) == ""

    def test_assunto_resume_o_dia(self):
        assert r.assunto(METRICAS) == (
            "HIPO 17/08 — 3 pessoas, 31 atividades, 1/3 reuniões realizadas"
        )

    def test_assunto_sem_reuniao_nao_fala_de_reuniao(self):
        m = {"dia": "2026-08-17", "adocao": {"pessoas_ativas": 1},
             "atividades": {"total": 1}, "reunioes": {"total": 0}}
        assert r.assunto(m) == "HIPO 17/08 — 1 pessoa, 1 atividade"

    def test_assunto_de_payload_antigo(self):
        """Fechamento gravado antes de 16/09 nao tem `atividades`."""
        m = {"dia": "2026-08-17", "adocao": {"pessoas_ativas": 1},
             "operacao": {"oportunidades_criadas": 1}}
        assert r.assunto(m) == "HIPO 17/08 — 1 pessoa, 1 oportunidade"


class TestHtml:
    def test_contem_os_numeros_e_os_nomes(self):
        html = r.montar_html(METRICAS)
        for esperado in ["31", "Aline Martins", "55", "Bruno Gonçalo"]:
            assert esperado in html, f"faltou {esperado!r} no e-mail"

    def test_nao_mostra_rota_de_api(self):
        """
        As tabelas "Telas mais usadas" e "Erros do dia" saíram em 31/08.

        Quem lê este e-mail é o dono da operação, e `/crm/parceiros/{id}` não
        sugere ação nenhuma para ele — é diagnóstico de desenvolvedor. Os
        dados continuam em `adocao.rotas_mais_usadas` para quem consultar a
        API; o que saiu foi a exibição.

        Este teste existe para a decisão não voltar por descuido: as métricas
        ainda trazem as rotas no payload, então é fácil alguém religar a
        tabela sem perceber que ela tinha sido tirada de propósito.
        """
        html = r.montar_html(METRICAS)
        assert "/crm/contas" not in html
        assert "Telas mais usadas" not in html
        assert "Erros do dia" not in html

    def test_desenha_o_conteudo_do_crm(self):
        """O motivo de o e-mail existir depois de 31/08."""
        html = r.montar_html(METRICAS)
        for esperado in [
            "Precisa de ação", "OPP-2026-00001", "Metalurgica Andrade",
            "previsão venceu há 7 dias",
            "Perto de fechar", "OPP-2026-00003", "temperatura 90",
            "Parceiros para acionar", "Escritorio Aurora",
            "Tarefas atrasadas", "Visita tecnica",
        ]:
            assert esperado in html, f"faltou {esperado!r} no e-mail"

    def test_motivo_acompanha_cada_item(self):
        """
        Item sem motivo obrigaria o leitor a adivinhar por que aquela
        oportunidade está na lista — e lista que precisa ser decifrada não é
        lida. É também o material que a IA usa para narrar sem inventar.
        """
        html = r.montar_html(METRICAS)
        assert "sem próxima tarefa marcada" in html

    def test_conta_quantos_ficaram_de_fora(self):
        """As listas são cortadas em cinco; o resto não pode sumir calado."""
        assert "e mais 2 com pendência" in r.montar_html(METRICAS)

    def test_sem_conteudo_nao_desenha_bloco_vazio(self):
        """Payload antigo, sem a chave `conteudo`, não pode quebrar o render."""
        m = {k: v for k, v in METRICAS.items() if k != "conteudo"}
        html = r.montar_html(m)
        assert "Precisa de ação" not in html
        assert "Atividade da equipe" in html, "o resto do e-mail continua desenhado"

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
        m["atividades"] = dict(METRICAS["atividades"])
        m["atividades"]["por_pessoa"] = [{
            "nome": "<script>alerta()</script>", "cargo": "EC", "entrada": None,
            "saida": None, "total": 1, "por_hora": [1] + [0] * 10,
            "por_tipo": [{"grupo": "Tarefas", "tipo": "Tarefa criada", "qtd": 1}],
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
        assert "Nada no período." in html, "payload antigo cai na tabela antiga"
        assert "<!DOCTYPE html>" in html

    def test_tabela_usuario_por_hora(self):
        html = r.montar_html(METRICAS)
        assert "Atividade da equipe" in html
        for h in ("8h", "12h", "18h"):
            assert f">{h}</th>" in html
        assert "08:20–17:54" in html, "expediente no horário de Brasília"
        assert ">Equipe</td>" in html

    def test_nao_mostra_mais_acoes_brutas(self):
        """
        "Ações" era toda request, e 89% eram leitura. Saiu em 16/09 junto com
        latência e erros: quem lê é o dono da operação.
        """
        html = r.montar_html(METRICAS)
        assert "Uso do sistema" not in html
        assert "Latência" not in html
        assert ">Ações<" not in html
        assert ">120<" not in html

    def test_detalhe_por_colaborador_por_tipo(self):
        html = r.montar_html(METRICAS)
        assert "O que cada um lançou" in html
        assert "Tarefa concluída" in html
        assert "Anexo enviado" in html
        assert "e não lançou nada" in html, "quem entrou e não lançou aparece"

    def test_reunioes_com_desfecho(self):
        html = r.montar_html(METRICAS)
        assert "Reuniões do dia" in html
        for esperado in ["Frigorifico Sao Jorge", "Realizada", "No-show",
                         "Sem desfecho", "DG · Diagnóstico",
                         "Agendamentos marcados no dia (4)",
                         "50,0% das que tiveram desfecho"]:
            assert esperado in html, f"faltou {esperado!r}"

    def test_dia_sem_reuniao_diz_isso(self):
        m = dict(METRICAS, reunioes={"total": 0, "realizadas": 0, "canceladas": 0,
                                     "no_show": 0, "pendentes": 0,
                                     "taxa_realizacao_pct": None, "por_anfitriao": [],
                                     "itens": [], "agendamentos_total": 0,
                                     "agendamentos_por_pessoa": []})
        assert "Nenhuma reunião marcada para o dia." in r.montar_html(m)

    def test_oportunidades_trabalhadas_e_primeira_vez(self):
        html = r.montar_html(METRICAS)
        assert "Oportunidades trabalhadas" in html
        assert "Trabalhadas pela 1ª vez" in html
        assert ">17<" in html and ">6<" in html
        assert "+5 vs. dia anterior" in html
        assert ">Opp.</th>" in html and ">1ª vez</th>" in html
        txt = r.montar_texto(METRICAS)
        assert "Oportunidades trabalhadas: 17 (pela 1ª vez: 6)" in txt

    def test_variacao_de_atividades_contra_o_dia_anterior(self):
        assert "+11 vs. dia anterior" in r.montar_html(METRICAS)

    def test_payload_antigo_mostra_hora_convertida(self):
        m = {k: v for k, v in METRICAS.items() if k not in ("atividades", "reunioes")}
        m["adocao"] = dict(METRICAS["adocao"], por_pessoa=[{
            "nome": "Kethlleen Gomes", "cargo": "SDR", "acoes": 980, "telas": 33,
            "primeira": "2026-09-15T11:46:00+00:00",
            "ultima": "2026-09-15T20:52:00+00:00", "erros": 6,
        }])
        html = r.montar_html(m)
        assert "08:46" in html and "17:52" in html
        assert "11:46" not in html

    def test_html_fecha_o_documento(self):
        assert r.montar_html(METRICAS).rstrip().endswith("</html>")


class TestTexto:
    def test_versao_texto_tem_o_essencial(self):
        txt = r.montar_texto(METRICAS, "Resumo do dia.")
        assert "HIPO — FECHAMENTO DO DIA" in txt
        assert "Resumo do dia." in txt
        assert "Aline Martins" in txt
        assert "NÃO ACESSARAM" in txt
        assert "ATIVIDADE DA EQUIPE" in txt
        assert "REUNIÕES DO DIA" in txt
        assert "Tarefa concluída" in txt
        assert "SEM DESFECHO" in txt
        assert "<" not in txt, "a versão texto não pode conter marcação"

    def test_dia_sem_ninguem(self):
        m = dict(METRICAS)
        m["atividades"] = dict(METRICAS["atividades"], por_pessoa=[], total=0)
        assert "ninguém entrou no sistema" in r.montar_texto(m)

    def test_dia_sem_ninguem_payload_antigo(self):
        m = {k: v for k, v in METRICAS.items() if k not in ("atividades", "reunioes")}
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

    def test_narrativa_nao_recebe_acoes_brutas(self):
        """A narrativa só fala do que o leitor vê -- e ele não vê mais ações."""
        copia = ia.metricas_para_narrar(METRICAS)
        assert "acoes" not in copia["adocao"]
        assert "latencia_p95_ms" not in copia["adocao"]
        assert "acoes" not in copia["comparativo"]
        assert copia["atividades"]["total"] == 31
        assert METRICAS["adocao"]["acoes"] == 120, "a original não pode ser mutada"

    def test_prompt_proibe_prazo_e_regra_inventados(self):
        """
        15/09: "Se a oportunidade nao se recuperar em 48 horas, qualifique-a
        como perda". A guarda pegou o 48; a frase sem numero passaria. A
        proibicao precisa estar escrita na instrucao.
        """
        assert "NÃO CRIE PRAZO, META, LIMITE OU REGRA DE NEGÓCIO" in ia.INSTRUCAO
        assert "NÃO SOME, SUBTRAIA NEM CALCULE PERCENTUAL" in ia.INSTRUCAO

    def test_guarda_descarta_o_prazo_inventado_de_15_09(self):
        from services.validacao_numerica import numeros_invalidos, numeros_permitidos
        texto = ("Se a oportunidade não se recuperar em 48 horas, qualifique-a "
                 "como perda.")
        permitidos = numeros_permitidos(ia.metricas_para_narrar(METRICAS))
        assert numeros_invalidos(texto, permitidos) == ["48"]

    def test_prompt_proibe_inventar_numero(self):
        """
        O contrato com o modelo está no texto da instrução. Se alguém suavizar
        essa linha, o relatório passa a poder mentir — e este teste cai.
        """
        assert "NÃO invente" in ia.INSTRUCAO
