"""
HIPO - Testes puros da classificacao de atividade (services/atividade.py).

Sem banco e sem rede. O teste de cobertura do catalogo importa `main` para
ler as rotas, mas nao abre conexao.
"""
from __future__ import annotations

import pytest

from services import atividade as a


def _linha(uid="u1", nome="Kethlleen Gomes", cargo="SDR", metodo="POST",
           rota="/crm/tarefas", status=201, hora=10, qtd=1):
    return {"usuario_id": uid, "nome": nome, "cargo": cargo, "metodo": metodo,
            "rota": rota, "status": status, "hora": hora, "qtd": qtd}


class TestContaComoAtividade:
    def test_escrita_com_sucesso_conta(self):
        assert a.conta_como_atividade("POST", "/crm/tarefas/{tarefa_id}/concluir", 200)
        assert a.conta_como_atividade("patch", "/crm/tarefas/{tarefa_id}", 200)
        assert a.conta_como_atividade("DELETE", "/crm/anexos/{anexo_id}", 204)

    @pytest.mark.parametrize("metodo", ["GET", "HEAD", "OPTIONS"])
    def test_leitura_nao_conta(self, metodo):
        assert not a.conta_como_atividade(metodo, "/crm/tarefas", 200)

    @pytest.mark.parametrize("status", [400, 401, 403, 409, 422, 500])
    def test_escrita_com_erro_nao_conta(self, status):
        """O 409 de vincular contato que ja estava vinculado nao produziu nada."""
        assert not a.conta_como_atividade("POST", "/crm/contatos/{contato_id}/vinculos", status)

    @pytest.mark.parametrize("metodo,rota", sorted(a.IGNORADAS))
    def test_ignoradas_nao_contam(self, metodo, rota):
        assert not a.conta_como_atividade(metodo, rota, 200)


class TestClassificar:
    def test_rotas_do_dia_15_09(self):
        """As escritas reais do fechamento de 15/09 saem com nome de gente."""
        casos = {
            ("POST", "/crm/tarefas/{tarefa_id}/concluir"): "Tarefa concluída",
            ("POST", "/crm/tarefas"): "Tarefa criada",
            ("POST", "/crm/oportunidades/{oportunidade_id}/desfecho"):
                "Oportunidade finalizada (ganho/perda)",
            ("PATCH", "/crm/oportunidades/{oportunidade_id}/fase"): "Fase alterada",
            ("POST", "/crm/contatos/{contato_id}/vinculos"): "Contato vinculado a conta",
            ("POST", "/crm/agenda/reunioes"): "Reunião agendada",
            ("POST", "/crm/oportunidades/{oportunidade_id}/propostas"): "Proposta gerada",
        }
        for (m, r), rotulo in casos.items():
            assert a.classificar(m, r).rotulo == rotulo

    def test_vinculo_de_contato_nao_vira_contato_criado(self):
        """O erro que uma traducao por heuristica cometeria."""
        t = a.classificar("POST", "/crm/contatos/{contato_id}/vinculos")
        assert t.rotulo != a.classificar("POST", "/crm/contatos").rotulo

    def test_rota_desconhecida_nao_some(self):
        t = a.classificar("POST", "/crm/algo-novo")
        assert t.grupo == "Outras alterações"
        assert "/crm/algo-novo" in t.rotulo

    def test_todo_grupo_do_catalogo_tem_ordem(self):
        assert {t.grupo for t in a.CATALOGO.values()} <= set(a.GRUPOS)


class TestCatalogoCobreAApi:
    def test_toda_rota_de_escrita_tem_nome_ou_esta_ignorada(self):
        """
        Rota de escrita nova sem entrada aqui cairia em "outras alteracoes"
        com a rota crua no e-mail do dono da operacao. Este teste obriga a
        dar nome a ela -- ou a decidir, por escrito, que nao e atividade.
        """
        from main import app

        faltando = []
        for rota in app.routes:
            metodos = getattr(rota, "methods", None) or set()
            for m in metodos - a.METODOS_DE_LEITURA:
                chave = (m, rota.path)
                if chave not in a.CATALOGO and chave not in a.IGNORADAS:
                    faltando.append(f"{m} {rota.path}")
        assert not faltando, (
            "rotas de escrita sem rotulo em services/atividade.py: "
            + ", ".join(sorted(faltando))
        )

    def test_catalogo_nao_tem_rota_morta(self):
        """Entrada para rota que nao existe mais e rotulo que nunca aparece."""
        from main import app

        existentes = {
            (m, r.path)
            for r in app.routes
            for m in (getattr(r, "methods", None) or set())
        }
        mortas = [f"{m} {p}" for (m, p) in a.CATALOGO if (m, p) not in existentes]
        assert not mortas, f"rotas do catalogo que nao existem na API: {mortas}"


class TestJanelaDeHoras:
    def test_padrao_8_as_18(self):
        assert a.janela_de_horas([]) == list(range(8, 19))

    def test_estende_para_quem_trabalha_fora(self):
        assert a.janela_de_horas([7, 20]) == list(range(7, 21))

    def test_nao_encolhe(self):
        assert a.janela_de_horas([10, 11]) == list(range(8, 19))


class TestAgregar:
    def test_soma_por_hora_e_por_tipo(self):
        r = a.agregar([
            _linha(rota="/crm/tarefas/{tarefa_id}/concluir", status=200, hora=10, qtd=20),
            _linha(rota="/crm/tarefas/{tarefa_id}/concluir", status=200, hora=17, qtd=4),
            _linha(rota="/crm/tarefas", hora=10, qtd=4),
        ], [])
        p = r["por_pessoa"][0]
        assert p["total"] == 28
        assert r["total"] == 28
        assert p["por_hora"][r["horas"].index(10)] == 24
        assert p["por_hora"][r["horas"].index(17)] == 4
        assert {t["tipo"]: t["qtd"] for t in p["por_tipo"]} == {
            "Tarefa criada": 4, "Tarefa concluída": 24,
        }

    def test_tipos_saem_na_ordem_do_catalogo(self):
        r = a.agregar([
            _linha(rota="/crm/contatos", qtd=5),
            _linha(rota="/crm/tarefas/{tarefa_id}/concluir", status=200, qtd=1),
            _linha(rota="/crm/oportunidades", qtd=2),
        ], [])
        grupos = [t["grupo"] for t in r["por_pessoa"][0]["por_tipo"]]
        assert grupos == ["Tarefas", "Oportunidades", "Contas e contatos"]

    def test_leitura_erro_e_login_ficam_de_fora(self):
        r = a.agregar([
            _linha(metodo="GET", rota="/crm/tarefas", status=200, qtd=900),
            _linha(rota="/crm/contatos/{contato_id}/vinculos", status=409, qtd=5),
            _linha(rota="/auth/login", status=200, qtd=1),
        ], [])
        assert r["total"] == 0

    def test_quem_entrou_e_nao_lancou_aparece_com_zero(self):
        r = a.agregar(
            [_linha(uid="u1", qtd=3)],
            [
                {"usuario_id": "u1", "nome": "Kethlleen Gomes", "cargo": "SDR",
                 "entrada": "08:46", "saida": "17:52"},
                {"usuario_id": "u2", "nome": "Jakeline Santana", "cargo": "EV",
                 "entrada": "08:43", "saida": "17:32"},
            ],
        )
        nomes = [p["nome"] for p in r["por_pessoa"]]
        assert nomes == ["Kethlleen Gomes", "Jakeline Santana"]
        jake = r["por_pessoa"][1]
        assert jake["total"] == 0
        assert jake["por_tipo"] == []
        assert jake["entrada"] == "08:43"
        assert len(jake["por_hora"]) == len(r["horas"])

    def test_total_por_hora_bate_com_as_linhas(self):
        r = a.agregar([
            _linha(uid="u1", hora=9, qtd=2),
            _linha(uid="u2", nome="Gabriel Lira", hora=9, qtd=3),
            _linha(uid="u2", nome="Gabriel Lira", hora=15, qtd=1),
        ], [])
        assert sum(r["total_por_hora"]) == r["total"] == 6
        assert r["total_por_hora"][r["horas"].index(9)] == 5

    def test_ordena_por_quem_mais_lancou(self):
        r = a.agregar([
            _linha(uid="u1", nome="Aline Martins", qtd=2),
            _linha(uid="u2", nome="Gabriel Lira", qtd=7),
        ], [])
        assert [p["nome"] for p in r["por_pessoa"]] == ["Gabriel Lira", "Aline Martins"]


class TestAgregarOportunidades:
    def test_total_vem_do_banco_e_nao_da_soma(self):
        r = a.agregar(
            [],
            [],
            [{"usuario_id": "u1", "nome": "A", "cargo": "SDR", "trabalhadas": 3, "primeira_vez": 1},
             {"usuario_id": "u2", "nome": "B", "cargo": "EV", "trabalhadas": 2, "primeira_vez": 1}],
            {"trabalhadas": 4, "primeira_vez": 1},
        )
        assert r["oportunidades_trabalhadas"] == 4
        assert r["oportunidades_primeira_vez"] == 1
        assert [p["oportunidades_trabalhadas"] for p in r["por_pessoa"]] == [3, 2]

    def test_sem_oportunidades_fica_zero(self):
        r = a.agregar([_linha()], [])
        assert r["oportunidades_trabalhadas"] == 0
        assert r["por_pessoa"][0]["oportunidades_primeira_vez"] == 0
