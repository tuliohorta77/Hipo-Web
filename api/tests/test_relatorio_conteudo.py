"""
HIPO — Regras de destaque do conteúdo do CRM no fechamento diário.

Puros: sem Postgres. O que está sob teste é a decisão de O QUE vira destaque
e em que ordem — a leitura do banco é exercitada no CI pelos testes de rota.

O QUE ESTES TESTES TRAVAM

O e-mail existe para produzir ação. Se o filtro deixar passar tudo, ele vira
inventário e ninguém lê; se apertar demais, o negócio que precisava de gente
some. Cada teste aqui é uma dessas duas bordas.
"""
from __future__ import annotations

from datetime import date

from services.relatorio_conteudo import (
    Destaque, classificar, cortar, dias_ate, ordenar,
    sinais_de_acao, sinais_de_fechamento,
)

HOJE = date(2026, 8, 31)


def motivos(achados):
    return [m for _, m in achados]


class TestDiasAte:
    def test_futuro_passado_e_ausente(self):
        assert dias_ate(date(2026, 9, 4), HOJE) == 4
        assert dias_ate(date(2026, 8, 24), HOJE) == -7
        assert dias_ate(None, HOJE) is None


class TestSinaisDeAcao:
    def base(self, **kw):
        args = dict(fase="negociacao", previsao=None, dias_parada=0,
                    tem_proxima_tarefa=True, hoje=HOJE)
        args.update(kw)
        return sinais_de_acao(**args)

    def test_nada_errado_nao_gera_sinal(self):
        assert self.base() == []

    def test_previsao_vencida(self):
        assert motivos(self.base(previsao=date(2026, 8, 24))) == [
            "previsão venceu há 7 dias"
        ]

    def test_previsao_de_hoje_ainda_nao_venceu(self):
        """Hoje é o dia da promessa, não o dia seguinte a ela."""
        assert self.base(previsao=HOJE) == []

    def test_singular_no_texto(self):
        assert motivos(self.base(previsao=date(2026, 8, 30))) == [
            "previsão venceu há 1 dia"
        ]

    def test_sem_proxima_tarefa(self):
        assert motivos(self.base(tem_proxima_tarefa=False)) == [
            "sem próxima tarefa marcada"
        ]

    def test_parada_em_fase_avancada(self):
        assert motivos(self.base(dias_parada=20)) == ["parada há 20 dias"]

    def test_parada_no_limite_nao_dispara_antes(self):
        assert self.base(dias_parada=13) == []
        assert motivos(self.base(dias_parada=14)) == ["parada há 14 dias"]

    def test_suspect_parado_nao_e_problema(self):
        """
        A boca do funil está parada por definição — ninguém tocou ainda. Se
        entrasse, a lista encheria de suspect e enterraria a negociação que
        de fato precisa de gente.
        """
        assert self.base(fase="suspect", dias_parada=200) == []
        assert self.base(fase="lead", dias_parada=200) == []

    def test_sinais_acumulam(self):
        achados = self.base(previsao=date(2026, 8, 21), tem_proxima_tarefa=False,
                            dias_parada=30)
        assert len(achados) == 3
        # Vencida pesa mais que sem-tarefa, que pesa mais que parada.
        assert [p for p, _ in achados] == [120, 80, 50]


class TestSinaisDeFechamento:
    def test_temperatura_alta(self):
        assert motivos(sinais_de_fechamento(
            temperatura=70, previsao=None, hoje=HOJE)) == ["temperatura 70"]

    def test_temperatura_media_nao_conta(self):
        assert sinais_de_fechamento(
            temperatura=60, previsao=None, hoje=HOJE) == []

    def test_sem_temperatura_nao_quebra(self):
        """Oportunidade suspensa pode ter temperatura nula."""
        assert sinais_de_fechamento(
            temperatura=None, previsao=None, hoje=HOJE) == []

    def test_previsao_proxima(self):
        assert motivos(sinais_de_fechamento(
            temperatura=None, previsao=date(2026, 9, 3), hoje=HOJE)) == [
            "previsão em 3 dias"]

    def test_previsao_hoje_tem_texto_proprio(self):
        assert motivos(sinais_de_fechamento(
            temperatura=None, previsao=HOJE, hoje=HOJE)) == ["previsão é hoje"]

    def test_previsao_distante_nao_conta(self):
        assert sinais_de_fechamento(
            temperatura=None, previsao=date(2026, 9, 30), hoje=HOJE) == []

    def test_previsao_vencida_nao_e_fechamento(self):
        """Vencida é cobrança, e quem trata dela é sinais_de_acao."""
        assert sinais_de_fechamento(
            temperatura=None, previsao=date(2026, 8, 1), hoje=HOJE) == []


class TestClassificar:
    def base(self, **kw):
        args = dict(numero="OPP-2026-00001", conta="Empresa X", fase="negociacao",
                    status="ativa", temperatura=50, valor=1000.0, previsao=None,
                    dias_parada=0, tem_proxima_tarefa=True, hoje=HOJE)
        args.update(kw)
        return classificar(**args)

    def test_sem_sinal_fica_de_fora(self):
        """O e-mail mostra o que precisa de gente, não o inventário."""
        assert self.base() == (None, None)

    def test_acao_ganha_de_celebracao(self):
        """
        Quente E sem próxima tarefa é a coisa mais urgente do CRM. Mostrar na
        lista das boas notícias esconderia exatamente o que precisa de ação.
        """
        categoria, d = self.base(temperatura=90, tem_proxima_tarefa=False)
        assert categoria == "acao"
        assert d.motivos == ("sem próxima tarefa marcada",)

    def test_temperatura_sobrevive_na_lista_de_acao(self):
        """A informação não se perde por cair na outra lista."""
        _, d = self.base(temperatura=90, tem_proxima_tarefa=False)
        assert d.temperatura == 90

    def test_fechar_quando_nao_ha_furo(self):
        categoria, d = self.base(temperatura=80)
        assert categoria == "fechar"
        assert d.motivos == ("temperatura 80",)


class TestOrdenar:
    def d(self, numero, peso, valor=None):
        return Destaque(numero=numero, conta="X", fase="negociacao", status="ativa",
                        temperatura=None, valor=valor, previsao=None,
                        motivos=(), peso=peso)

    def test_peso_manda(self):
        saida = ordenar([self.d("B", 50), self.d("A", 120)])
        assert [x.numero for x in saida] == ["A", "B"]

    def test_valor_so_desempata(self):
        """
        Contrato grande e saudável NÃO passa na frente de um pequeno com a
        previsão vencida. A lista responde "o que precisa de mim", não "o que
        vale mais" — essa o funil já responde.
        """
        saida = ordenar([self.d("GRANDE", 50, 90000.0), self.d("VENCIDA", 120, 100.0)])
        assert [x.numero for x in saida] == ["VENCIDA", "GRANDE"]

    def test_empate_de_peso_usa_valor(self):
        saida = ordenar([self.d("MENOR", 80, 100.0), self.d("MAIOR", 80, 9000.0)])
        assert [x.numero for x in saida] == ["MAIOR", "MENOR"]

    def test_ordem_estavel_entre_iguais(self):
        """
        Sem critério final, dois itens idênticos trocariam de lugar entre um
        e-mail e outro sem nada ter mudado — e quem lê todo dia perceberia.
        """
        a = ordenar([self.d("OPP-2", 80), self.d("OPP-1", 80)])
        b = ordenar([self.d("OPP-1", 80), self.d("OPP-2", 80)])
        assert [x.numero for x in a] == [x.numero for x in b] == ["OPP-1", "OPP-2"]


class TestCortar:
    def d(self, numero, peso):
        return Destaque(numero=numero, conta="X", fase="negociacao", status="ativa",
                        temperatura=None, valor=None, previsao=None,
                        motivos=(), peso=peso)

    def test_vazio(self):
        assert cortar([]) == ([], 0)

    def test_corta_e_conta_o_resto(self):
        itens = [self.d(f"OPP-{i}", 100 - i) for i in range(8)]
        lista, sobrou = cortar(itens, limite=5)
        assert len(lista) == 5 and sobrou == 3
        assert lista[0]["numero"] == "OPP-0"

    def test_abaixo_do_limite_nao_sobra(self):
        lista, sobrou = cortar([self.d("A", 10)], limite=5)
        assert len(lista) == 1 and sobrou == 0


class TestNarrativaSoFalaDoQueOLeitorVe:
    """
    O e-mail deixou de mostrar rota; a narrativa também não pode citar.

    O fechamento de 31/08 saiu com "consultou 117 vezes dados de contas
    específicas" — número correto, e conferível por ninguém, porque a tabela
    de rotas tinha saído. Número sem onde conferir é pior que número
    inventado: parece verificável.
    """

    def base(self):
        return {
            "adocao": {
                "acoes": 698, "pessoas_ativas": 1,
                "rotas_mais_usadas": [
                    {"metodo": "GET", "rota": "/crm/contas/{id}",
                     "acoes": 117, "media_ms": 30},
                ],
                "erros_por_rota": [
                    {"metodo": "POST", "rota": "/crm/contatos/vinculo",
                     "status": 409, "ocorrencias": 33},
                ],
            },
            "operacao": {"contas_criadas": 2},
        }

    def test_tira_o_detalhe_de_rota(self):
        from services.ia import metricas_para_narrar
        saida = metricas_para_narrar(self.base())
        assert "rotas_mais_usadas" not in saida["adocao"]
        assert "erros_por_rota" not in saida["adocao"]
        assert saida["adocao"]["acoes"] == 698, "o resto continua"
        assert saida["operacao"]["contas_criadas"] == 2

    def test_nao_muta_a_original(self):
        """
        O mesmo dicionário vai para o relatorio_render depois, e a API serve
        as rotas para quem consultar. Esvaziar aqui apagaria dado alheio.
        """
        from services.ia import metricas_para_narrar
        m = self.base()
        metricas_para_narrar(m)
        assert m["adocao"]["rotas_mais_usadas"], "a original foi mutilada"

    def test_numero_de_rota_deixa_de_ser_permitido(self):
        """
        A guarda passa a validar contra a mesma cópia que o modelo recebeu —
        então citar 117 ou 409 agora DESCARTA a narrativa, que é o certo.
        """
        from services.ia import metricas_para_narrar
        from services.validacao_numerica import numeros_invalidos, numeros_permitidos

        permitidos = numeros_permitidos(metricas_para_narrar(self.base()))
        assert numeros_invalidos("foram 698 ações", permitidos) == []
        assert numeros_invalidos("consultou 117 vezes", permitidos) == ["117"]

    def test_sem_bloco_adocao_nao_quebra(self):
        from services.ia import metricas_para_narrar
        assert metricas_para_narrar({"operacao": {}}) == {"operacao": {}}
