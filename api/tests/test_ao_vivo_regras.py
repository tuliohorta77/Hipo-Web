"""
HIPO — Transcrição ao vivo: regras puras (services/ao_vivo.py).

Sem banco: rodam no pytest local do Windows.
"""
from datetime import datetime, timedelta, timezone

from services import ao_vivo as r

T = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)


def motivo(agora=T, cancelada=False, modalidade="online", duracao=30):
    return r.motivo_para_nao_abrir(
        inicio=T, duracao_min=duracao, agora=agora,
        cancelada=cancelada, modalidade=modalidade,
    )


class TestJanela:
    def test_na_hora_abre(self):
        assert motivo() is None

    def test_uma_hora_antes_abre(self):
        assert motivo(agora=T - timedelta(hours=1)) is None

    def test_mais_cedo_recusa(self):
        assert "cedo" in motivo(agora=T - timedelta(hours=1, minutes=1))

    def test_tres_horas_depois_do_fim_ainda_abre(self):
        assert motivo(agora=T + timedelta(minutes=30, hours=3)) is None

    def test_depois_disso_recusa(self):
        assert "terminou" in motivo(agora=T + timedelta(minutes=31, hours=3))

    def test_a_duracao_empurra_o_fim(self):
        assert motivo(agora=T + timedelta(hours=4, minutes=30), duracao=90) is None

    def test_cancelada_recusa_mesmo_na_hora(self):
        assert "cancelada" in motivo(cancelada=True)

    def test_presencial_recusa(self):
        assert "presencial" in motivo(modalidade="presencial")

    def test_cancelada_vem_antes_da_modalidade(self):
        assert "cancelada" in motivo(cancelada=True, modalidade="presencial")


class TestQuemCaptura:
    def test_anfitriao(self):
        assert r.pode_capturar(usuario_id="a", eh_gestao=False,
                               anfitriao_id="a", participantes=[])

    def test_participante(self):
        assert r.pode_capturar(usuario_id="p", eh_gestao=False,
                               anfitriao_id="a", participantes=["x", "p"])

    def test_gestao(self):
        assert r.pode_capturar(usuario_id="g", eh_gestao=True,
                               anfitriao_id="a", participantes=[])

    def test_quem_so_marcou_nao(self):
        assert not r.pode_capturar(usuario_id="sdr", eh_gestao=False,
                                   anfitriao_id="a", participantes=["p"])

    def test_compara_uuid_com_texto(self):
        from uuid import UUID
        u = UUID("00000000-0000-0000-0000-000000000001")
        assert r.pode_capturar(usuario_id=str(u), eh_gestao=False,
                               anfitriao_id=u, participantes=[])


class TestPalavras:
    def test_minusculas_sem_acento(self):
        assert r.palavras("Você TEM exame admissional?") == [
            "voce", "tem", "exame", "admissional",
        ]

    def test_vazio(self):
        assert r.palavras(None) == []
        assert r.palavras("   ") == []

    def test_numeros_contam(self):
        assert r.contar_palavras("temos 120 vidas") == 3

    def test_pontuacao_nao_conta(self):
        assert r.contar_palavras("sim, sim... não!") == 3


class TestMetricas:
    def test_proporcao_por_palavra(self):
        m = r.metricas([
            {"canal": "vendedor", "texto": "um dois tres"},
            {"canal": "cliente", "texto": "quatro"},
        ])
        assert m == {
            "falas": 2, "palavras_vendedor": 3, "palavras_cliente": 1,
            "palavras_total": 4, "proporcao_vendedor_pct": 75,
        }

    def test_sem_palavras_proporcao_e_none_nao_zero(self):
        m = r.metricas([])
        assert m["proporcao_vendedor_pct"] is None
        assert m["palavras_total"] == 0

    def test_canal_desconhecido_e_ignorado(self):
        m = r.metricas([{"canal": "outro", "texto": "abc"}])
        assert m["falas"] == 0 and m["palavras_total"] == 0


class TestCobertura:
    def test_sem_referencia_nao_tem_nota(self):
        assert r.cobertura(["oi"], []) is None
        assert r.cobertura(["oi"], ["", None or ""]) is None

    def test_tudo_coberto(self):
        c = r.cobertura(["Bom dia, tudo bem"], ["bom dia", "tudo bem?"])
        assert c == {"palavras_meet": 4, "palavras_ao_vivo": 4, "cobertura_pct": 100}

    def test_multiconjunto(self):
        c = r.cobertura(["sim"], ["sim sim sim"])
        assert c["cobertura_pct"] == 33

    def test_acento_nao_e_erro(self):
        c = r.cobertura(["voce nao"], ["você não"])
        assert c["cobertura_pct"] == 100

    def test_ordem_nao_importa(self):
        c = r.cobertura(["mande a proposta"], ["a proposta mande"])
        assert c["cobertura_pct"] == 100

    def test_palavra_a_mais_no_ao_vivo_nao_passa_de_100(self):
        c = r.cobertura(["ok ok ok ok"], ["ok"])
        assert c["cobertura_pct"] == 100
        assert c["palavras_ao_vivo"] == 4


class TestUtilidades:
    def test_limpar_texto(self):
        assert r.limpar_texto("  bom   dia \n tudo ") == "bom dia tudo"
        assert r.limpar_texto(None) == ""

    def test_juntar_erros_guarda_os_mais_recentes(self):
        atuais = [{"erro": str(i)} for i in range(r.MAX_ERROS_GUARDADOS)]
        juntos = r.juntar_erros(atuais, [{"erro": "novo"}])
        assert len(juntos) == r.MAX_ERROS_GUARDADOS
        assert juntos[-1] == {"erro": "novo"}
        assert juntos[0] == {"erro": "1"}

    def test_juntar_erros_sem_atuais(self):
        assert r.juntar_erros(None, [{"erro": "x"}]) == [{"erro": "x"}]
