"""
HIPO — Scorecard da reunião: regras puras e a chamada à IA (sem banco).

Roda no pytest local do Windows. A IA NÃO é chamada: o `httpx.AsyncClient`
do módulo é trocado por um cliente de teste que devolve a resposta que o
teste quiser — inclusive as tortas.
"""
import pytest

from services import avaliacao_roteiro as aval
from services import roteiro_scorecard as sc

TRANSCRICAO = (
    "[10:00] Bruno Gonçalo: Bom dia! Vi que vocês abriram a unidade de Guarulhos.\n"
    "[10:01] Bruno Gonçalo: A gente tem 30 minutos, eu entendo primeiro e "
    "apresento depois, e no final a gente decide junto se vale um próximo passo.\n"
    "[10:03] Cliente: Hoje temos 120 vidas e o fornecedor atual atrasa o ASO.\n"
    "[10:05] Bruno Gonçalo: E o que te incomoda hoje no fornecedor atual?\n"
    "[10:06] Cliente: O atraso trava a admissão.\n"
)


def itens_validos(**trocas):
    itens = {
        n: {"item": n, "nota": 0, "evidencia": "", "justificativa": "j", "sugestao": "s"}
        for n in range(1, 11)
    }
    for n, campos in trocas.items():
        itens[int(n[1:])].update(campos)
    return list(itens.values())


def entrada(itens=None, **extra):
    corpo = {
        "itens": itens if itens is not None else itens_validos(),
        "pontos_fortes": [],
        "pontos_melhorar": [],
        "foco_proxima": "Perguntar o custo do atraso.",
        "resumo": "Reunião curta.",
    }
    corpo.update(extra)
    return corpo


# ── O roteiro ────────────────────────────────────────────────────────


class TestRoteiro:
    def test_dez_itens_numerados_de_1_a_10(self):
        assert [i.numero for i in sc.ITENS] == list(range(1, 11))
        assert sc.QTD_ITENS == 10
        assert sc.NOTA_MAXIMA == 20
        assert set(sc.POR_NUMERO) == set(range(1, 11))

    def test_todo_item_tem_os_tres_criterios(self):
        for i in sc.ITENS:
            assert i.nome and i.etapa and i.o_que_procurar
            assert i.criterio_0 and i.criterio_1 and i.criterio_2

    def test_versao_e_meta(self):
        assert sc.VERSAO == "2026-09-30"
        assert sc.META_PADRAO == 15.0

    def test_faixas(self):
        assert sc.faixa(20) == "boa"
        assert sc.faixa(15) == "boa"
        assert sc.faixa(14) == "media"
        assert sc.faixa(10) == "media"
        assert sc.faixa(9) == "baixa"
        assert sc.faixa(0) == "baixa"
        assert sc.faixa(None) is None

    def test_prompt_leva_o_roteiro_e_os_itens(self):
        texto = aval.instrucao()
        assert "SCORECARD" in texto
        for i in sc.ITENS:
            assert f"{i.numero}. {i.nome}" in texto
        assert "registrar_avaliacao" in texto


# ── Elegibilidade e texto ────────────────────────────────────────────


class TestElegibilidade:
    @pytest.mark.parametrize("alvo,status,desfecho,cancelada,esperado", [
        ("oportunidade", "pronta", "realizada", False, True),
        ("oportunidade", "pronta", None, False, True),
        ("parceiro", "pronta", "realizada", False, False),
        ("oportunidade", "aguardando", None, False, False),
        ("oportunidade", "indisponivel", None, False, False),
        ("oportunidade", "pronta", "no_show", False, False),
        ("oportunidade", "pronta", "cancelada", False, False),
        ("oportunidade", "pronta", None, True, False),
    ])
    def test_regra(self, alvo, status, desfecho, cancelada, esperado):
        assert aval.elegivel(alvo, status, desfecho, cancelada) is esperado


class TestEvidencia:
    def test_ignora_caixa_acento_e_pontuacao(self):
        assert aval.evidencia_confere("o que te INCOMODA hoje no fornecedor", TRANSCRICAO)
        assert aval.evidencia_confere("vi que voces abriram a unidade", TRANSCRICAO)

    def test_reticencias_exigem_a_ordem(self):
        assert aval.evidencia_confere("Hoje temos 120 vidas ... atrasa o ASO", TRANSCRICAO)
        assert not aval.evidencia_confere("atrasa o ASO ... Hoje temos 120 vidas", TRANSCRICAO)

    def test_trecho_inventado_nao_confere(self):
        assert not aval.evidencia_confere("quanto custa um dia de admissão parada", TRANSCRICAO)

    def test_trecho_atravessa_a_troca_de_quem_fala(self):
        """
        Pergunta do vendedor + resposta do cliente: entre as duas a
        transcricao tem "[hh:mm] Nome:". Antes desta correcao o trecho nunca
        conferia, e os itens 7 e 10 eram descartados em massa (02/10).
        """
        t = ("[10:05] Bruno Gonçalo: Fechamos terça às 10 para ver a proposta?\n"
             "[10:05] Cliente Alfa: Pode ser, terça às 10 está ótimo.")
        assert aval.evidencia_confere(
            "Fechamos terça às 10 para ver a proposta? Pode ser, terça às 10", t)
        # A IA as vezes poe o nome de quem fala: tambem confere.
        assert aval.evidencia_confere(
            "Bruno Gonçalo: Fechamos terça às 10? ... Cliente Alfa: Pode ser, terça às 10", t)
        # Mas nao inventa: frase que ninguem disse continua sem conferir.
        assert not aval.evidencia_confere("Fechamos quarta às 15", t)

    def test_so_falas_tira_o_prefixo_e_guarda_os_nomes(self):
        falas, nomes = aval.so_falas("[09:00] Ana: oi\n[09:01] Cliente X: ola")
        assert falas == "oi\nola"
        assert nomes == ["Ana", "Cliente X"]

    def test_trecho_curto_demais_nao_prova(self):
        assert not aval.evidencia_confere("o", TRANSCRICAO)
        assert not aval.evidencia_confere("...", TRANSCRICAO)
        assert not aval.evidencia_confere(None, TRANSCRICAO)


class TestFala:
    def test_conta_palavras_do_vendedor(self):
        entradas = [
            {"participante": "BRUNO GONÇALO", "texto": "um dois tres quatro"},
            {"participante": "Cliente Fulano", "texto": "cinco"},
            {"participante": "Bruno Gonçalo", "texto": "seis seis seis seis seis"},
        ]
        assert aval.fala_vendedor_pct(entradas, "Bruno Gonçalo") == 90.0

    def test_homonimo_de_sobrenome_diferente_nao_conta(self):
        entradas = [
            {"participante": "Bruno Lima", "texto": "um dois"},
            {"participante": "Cliente", "texto": "tres"},
        ]
        assert aval.fala_vendedor_pct(entradas, "Bruno Gonçalo") is None

    def test_total_com_item_sem_nota_conta_zero(self):
        assert aval.total([2, 2, None, 1]) == 5
        assert aval.total([]) == 0


# ── Leitura da resposta ──────────────────────────────────────────────


class TestLeitura:
    def test_nota_com_evidencia_que_confere_fica(self):
        itens = itens_validos(i4={"nota": 2, "evidencia": "o que te incomoda hoje no fornecedor atual"})
        a = aval.ler_entrada(entrada(itens), TRANSCRICAO)
        assert a.itens[3].nota == 2
        assert a.descartados == ()

    def test_nota_com_evidencia_inventada_e_descartada(self):
        itens = itens_validos(i5={"nota": 2, "evidencia": "quanto custa cada dia de atraso"})
        a = aval.ler_entrada(entrada(itens), TRANSCRICAO)
        assert a.itens[4].nota is None
        assert "não foi encontrado" in a.itens[4].descartado
        assert a.descartados == (5,)

    def test_nota_sem_evidencia_e_descartada(self):
        itens = itens_validos(i2={"nota": 1, "evidencia": ""})
        a = aval.ler_entrada(entrada(itens), TRANSCRICAO)
        assert a.itens[1].nota is None
        assert a.descartados == (2,)

    def test_nota_zero_com_trecho_inventado_perde_so_o_trecho(self):
        itens = itens_validos(i3={"nota": 0, "evidencia": "frase que ninguem disse aqui"})
        a = aval.ler_entrada(entrada(itens), TRANSCRICAO)
        assert a.itens[2].nota == 0
        assert a.itens[2].evidencia is None
        assert a.descartados == ()

    def test_item_faltando_e_invalido(self):
        with pytest.raises(aval.RespostaInvalida, match="itens 10"):
            aval.ler_entrada(entrada(itens_validos()[:9]), TRANSCRICAO)

    def test_item_repetido_e_invalido(self):
        itens = itens_validos()
        itens[9] = dict(itens[0])
        with pytest.raises(aval.RespostaInvalida, match="repetido"):
            aval.ler_entrada(entrada(itens), TRANSCRICAO)

    @pytest.mark.parametrize("nota", [3, -1, "2", True, None])
    def test_nota_fora_de_0_a_2_e_invalida(self, nota):
        itens = itens_validos(i1={"nota": nota})
        with pytest.raises(aval.RespostaInvalida):
            aval.ler_entrada(entrada(itens), TRANSCRICAO)

    def test_sem_lista_e_invalido(self):
        with pytest.raises(aval.RespostaInvalida):
            aval.ler_entrada(None, TRANSCRICAO)
        with pytest.raises(aval.RespostaInvalida):
            aval.ler_entrada({"itens": "x"}, TRANSCRICAO)

    def test_pontos_do_coach(self):
        a = aval.ler_entrada(entrada(
            pontos_fortes=[
                {"texto": "Usou a pesquisa", "evidencia": "abriram a unidade de Guarulhos"},
                {"texto": "Contrato", "evidencia": "frase inventada pela IA aqui"},
                {"texto": "Terceiro some", "evidencia": ""},
            ],
            pontos_melhorar=[{
                "texto": "Faltou implicação", "evidencia": "O atraso trava a admissão",
                "como_fazer": "Pergunte quanto custa um dia sem admitir.",
            }],
        ), TRANSCRICAO)
        assert len(a.pontos_fortes) == 2
        assert a.pontos_fortes[0].evidencia == "abriram a unidade de Guarulhos"
        # Trecho que não confere some; o comentário fica.
        assert a.pontos_fortes[1].texto == "Contrato"
        assert a.pontos_fortes[1].evidencia is None
        assert a.pontos_melhorar[0].como_fazer.startswith("Pergunte")
        assert a.foco_proxima == "Perguntar o custo do atraso."


class TestPayload:
    def test_saida_estruturada_forcada(self):
        p = aval.payload(TRANSCRICAO, {"empresa": "Alfa"})
        assert p["tool_choice"] == {"type": "tool", "name": aval.NOME_FERRAMENTA}
        assert p["tools"][0]["name"] == aval.NOME_FERRAMENTA
        schema = p["tools"][0]["input_schema"]
        assert schema["properties"]["itens"]["minItems"] == 10
        assert "Alfa" in p["messages"][0]["content"]
        assert "incomoda" in p["messages"][0]["content"]

    def test_entrada_da_ferramenta(self):
        corpo = {"content": [
            {"type": "text", "text": "ok"},
            {"type": "tool_use", "name": aval.NOME_FERRAMENTA, "input": {"itens": []}},
        ]}
        assert aval.entrada_da_ferramenta(corpo) == {"itens": []}
        assert aval.entrada_da_ferramenta({"content": []}) is None

    def test_modelo_proprio_com_volta_para_o_padrao(self, monkeypatch):
        from types import SimpleNamespace

        # O campo pode nem existir em config.py (e o Settings recusa campo
        # desconhecido): troca o settings inteiro do modulo.
        monkeypatch.setattr(aval, "settings", SimpleNamespace(ANTHROPIC_MODEL_AVALIACAO="modelo-x"))
        assert aval.modelo() == "modelo-x"
        monkeypatch.setattr(aval, "settings", SimpleNamespace())
        assert aval.modelo() == aval.MODELO_PADRAO == "claude-sonnet-4-5"


# ── A chamada ────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, status, corpo):
        self.status_code = status
        self._corpo = corpo
        self.text = str(corpo)

    def json(self):
        return self._corpo


def cliente_falso(monkeypatch, resposta=None, erro=None):
    chamadas = []

    class Cliente:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            chamadas.append(json)
            if erro:
                raise erro
            return resposta

    monkeypatch.setattr(aval.httpx, "AsyncClient", Cliente)
    monkeypatch.setattr(aval.settings, "ANTHROPIC_API_KEY", "sk-teste")
    return chamadas


class TestChamada:
    async def test_sem_chave_nao_chama(self, monkeypatch):
        monkeypatch.setattr(aval.settings, "ANTHROPIC_API_KEY", "")
        a = await aval.avaliar(TRANSCRICAO, {})
        assert "ANTHROPIC_API_KEY" in a.erro
        assert a.itens == ()

    async def test_transcricao_vazia(self, monkeypatch):
        cliente_falso(monkeypatch)
        a = await aval.avaliar("   ", {})
        assert "vazia" in a.erro

    async def test_resposta_boa(self, monkeypatch):
        itens = itens_validos(i4={"nota": 2, "evidencia": "o que te incomoda hoje"})
        chamadas = cliente_falso(monkeypatch, _Resp(200, {"content": [
            {"type": "tool_use", "name": aval.NOME_FERRAMENTA, "input": entrada(itens)},
        ]}))
        a = await aval.avaliar(TRANSCRICAO, {"empresa": "Alfa"})
        assert a.erro is None
        assert aval.total([i.nota for i in a.itens]) == 2
        assert a.modelo == aval.modelo()
        assert len(chamadas) == 1

    async def test_http_de_erro_vira_mensagem(self, monkeypatch):
        cliente_falso(monkeypatch, _Resp(529, {"error": "overloaded"}))
        a = await aval.avaliar(TRANSCRICAO, {})
        assert a.erro == "A IA respondeu HTTP 529."

    async def test_excecao_de_rede_vira_mensagem(self, monkeypatch):
        cliente_falso(monkeypatch, erro=TimeoutError("lento"))
        a = await aval.avaliar(TRANSCRICAO, {})
        assert "TimeoutError" in a.erro

    async def test_resposta_fora_do_schema_vira_mensagem(self, monkeypatch):
        cliente_falso(monkeypatch, _Resp(200, {"content": [{"type": "text", "text": "oi"}]}))
        a = await aval.avaliar(TRANSCRICAO, {})
        assert "formato esperado" in a.erro


# ── Guia rápido do roteiro (botão na reunião, 07/10/2026) ─────────────

class TestGuiaRapido:
    def test_um_guia_por_item_do_scorecard(self):
        assert sorted(sc.GUIA_POR_ITEM) == [i.numero for i in sc.ITENS]
        for g in sc.GUIA:
            assert g.fazer.strip() and g.evitar.strip()
            assert 1 <= len(g.exemplos) <= 3, g.item

    def test_todo_item_cai_numa_etapa_e_o_tempo_fecha_45(self):
        guia = sc.guia_rapido()
        numeros = [i["item"] for e in guia["etapas"] for i in e["itens"]]
        assert numeros == list(range(1, sc.QTD_ITENS + 1))
        assert sum(e.minutos or 0 for e in sc.ETAPAS) == sc.DURACAO_REUNIAO_MIN == 45

    def test_vale_2_e_o_criterio_da_avaliacao(self):
        """O guia mostra o MESMO critério de 2 pontos que a IA aplica."""
        guia = sc.guia_rapido()
        for e in guia["etapas"]:
            for i in e["itens"]:
                assert i["vale_2"] == sc.POR_NUMERO[i["item"]].criterio_2

    def test_tres_dez_e_fechamento_batem_com_a_trilha_da_uc(self):
        from scripts import uc_conteudo_fechamento as f
        texto = " ".join(a["conteudo_md"] for a in f.TECNICA_06_FECHAMENTO["aulas"])
        assert [c.nome for c in sc.TRES_DEZ] == ["Produto", "Você", "Controller"]
        assert "O que faltaria para ser 10?" in texto
        assert "Até duas voltas" in texto and sc.LOOPING_MAXIMO == 2
        assert sc.PERGUNTA_FINAL in texto
        for fe in sc.FECHAMENTOS:
            assert fe.tecnica.lower() in texto.lower(), fe.tecnica

    def test_guia_nao_muda_a_versao_da_avaliacao(self):
        """O guia é apoio: não vai no prompt, então não pode mexer na versão."""
        assert sc.VERSAO == "2026-09-30"
        assert "Linha Reta" not in sc.ROTEIRO and "três 10" not in sc.texto_dos_itens()
