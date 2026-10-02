"""
HIPO — UC: regras puras (services/uc.py e services/uc_material.py).

Sem banco e sem rede: rodam no pytest local do Windows.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from services import uc as r
from services import uc_material as m
from services.anexo import AnexoInvalido
from services.uc import ConteudoInvalido

UTC = timezone.utc


# ── Vídeo ────────────────────────────────────────────────────────────

class TestNormalizarVideo:
    @pytest.mark.parametrize("url,esperado", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", ("youtube", "dQw4w9WgXcQ")),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s", ("youtube", "dQw4w9WgXcQ")),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", ("youtube", "dQw4w9WgXcQ")),
        ("https://youtu.be/dQw4w9WgXcQ?si=abc", ("youtube", "dQw4w9WgXcQ")),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", ("youtube", "dQw4w9WgXcQ")),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", ("youtube", "dQw4w9WgXcQ")),
        ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", ("youtube", "dQw4w9WgXcQ")),
        ("https://vimeo.com/76979871", ("vimeo", "76979871")),
        ("https://player.vimeo.com/video/76979871", ("vimeo", "76979871")),
        ("https://www.loom.com/share/0281766fa2d04bb788eaf19e65135184",
         ("loom", "0281766fa2d04bb788eaf19e65135184")),
        ("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing",
         ("drive", "1AbCdEfGhIjKlMnOpQrStUvWxYz012345")),
        ("https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345",
         ("drive", "1AbCdEfGhIjKlMnOpQrStUvWxYz012345")),
        ("  https://youtu.be/dQw4w9WgXcQ  ", ("youtube", "dQw4w9WgXcQ")),
    ])
    def test_formatos_conhecidos(self, url, esperado):
        assert r.normalizar_video(url) == esperado

    @pytest.mark.parametrize("vazio", [None, "", "   "])
    def test_vazio_e_aula_sem_video(self, vazio):
        assert r.normalizar_video(vazio) is None

    @pytest.mark.parametrize("url", [
        "javascript:alert(1)",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "data:text/html,<script>",
    ])
    def test_esquema_que_nao_e_http_e_recusado(self, url):
        with pytest.raises(ConteudoInvalido, match="https"):
            r.normalizar_video(url)

    @pytest.mark.parametrize("url", [
        "https://exemplo.com/video.mp4",
        "https://youtube.com.golpe.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/channel/UC123",
        "https://drive.google.com/drive/folders/abc",
    ])
    def test_host_ou_caminho_fora_da_lista(self, url):
        with pytest.raises(ConteudoInvalido, match="Aceitos"):
            r.normalizar_video(url)

    def test_id_truncado_diz_para_copiar_de_novo(self):
        with pytest.raises(ConteudoInvalido, match="Copie o link de novo"):
            r.normalizar_video("https://youtu.be/dQw4w9")

    def test_id_com_caractere_estranho_nao_passa(self):
        with pytest.raises(ConteudoInvalido):
            r.normalizar_video('https://youtu.be/dQw4w9"><x>')

    def test_url_publica_e_montada_do_par(self):
        assert r.url_do_video("youtube", "dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert r.url_do_video("drive", "abc") == "https://drive.google.com/file/d/abc/view"
        assert r.url_do_video(None, None) is None


# ── Vocabulário ──────────────────────────────────────────────────────

class TestVocabulario:
    def test_tres_pilares_na_ordem_da_spec(self):
        assert list(r.PILARES) == ["tecnica", "metodo", "energia"]

    def test_pilar_aceita_caixa_e_espaco(self):
        assert r.validar_pilar(" Tecnica ") == "tecnica"

    def test_pilar_invalido_lista_os_validos(self):
        with pytest.raises(ConteudoInvalido, match="Técnica, Método, Energia"):
            r.validar_pilar("comercial")

    def test_reforco_vazio_vira_none(self):
        assert r.validar_reforca("") is None
        assert r.validar_reforca(None) is None
        assert r.validar_reforca("roteiro") == "roteiro"
        with pytest.raises(ConteudoInvalido):
            r.validar_reforca("simpatia")

    def test_conta_de_tv_nao_recebe_trilha(self):
        with pytest.raises(ConteudoInvalido):
            r.validar_cargo("Monitor")
        assert r.validar_cargo("EV") == "EV"

    def test_cargos_extintos_nao_recebem_trilha(self):
        for cargo in ("Hunter", "Farmer", "Gerente"):
            with pytest.raises(ConteudoInvalido):
                r.validar_cargo(cargo)


# ── Trava de tempo ───────────────────────────────────────────────────

class TestTravaDeTempo:
    AGORA = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)

    def test_metade_da_duracao_arredondada_para_cima(self):
        assert r.minutos_minimos(10) == 5
        assert r.minutos_minimos(7) == 4
        assert r.minutos_minimos(1) == 1

    @pytest.mark.parametrize("duracao", [None, 0])
    def test_sem_duracao_libera_na_hora(self, duracao):
        assert r.minutos_minimos(duracao) == 0
        assert r.segundos_para_liberar(self.AGORA, duracao, self.AGORA) == 0

    def test_conta_a_partir_da_abertura(self):
        aberta = self.AGORA - timedelta(minutes=3)
        assert r.segundos_para_liberar(aberta, 10, self.AGORA) == 120

    def test_passado_o_tempo_libera(self):
        aberta = self.AGORA - timedelta(minutes=6)
        assert r.segundos_para_liberar(aberta, 10, self.AGORA) == 0

    def test_nunca_aberta_conta_como_aberta_agora(self):
        assert r.segundos_para_liberar(None, 10, self.AGORA) == 300


# ── Prazo e situação ─────────────────────────────────────────────────

class TestPrazo:
    def test_conta_da_data_mais_recente(self):
        entrada = datetime(2025, 1, 10, tzinfo=UTC)
        desde = datetime(2026, 10, 1, tzinfo=UTC)
        assert r.prazo_da_obrigatoria(entrada, desde, 30) == date(2026, 10, 31)

    def test_quem_entra_depois_da_trilha_conta_da_propria_entrada(self):
        desde = datetime(2026, 1, 1, tzinfo=UTC)
        entrada = datetime(2026, 9, 1, tzinfo=UTC)
        assert r.prazo_da_obrigatoria(entrada, desde, 10) == date(2026, 9, 11)

    def test_sem_prazo_dias_nao_tem_prazo(self):
        assert r.prazo_da_obrigatoria(datetime.now(UTC), datetime.now(UTC), None) is None

    def test_sem_datas_nao_tem_prazo(self):
        assert r.prazo_da_obrigatoria(None, None, 30) is None


class TestSituacao:
    HOJE = date(2026, 10, 15)

    def test_concluida_vence_qualquer_prazo(self):
        s = r.situacao_trilha(3, 3, date(2026, 10, 1), self.HOJE)
        assert s.codigo == "concluida"

    def test_atrasada(self):
        s = r.situacao_trilha(3, 1, date(2026, 10, 14), self.HOJE)
        assert (s.codigo, s.dias_restantes) == ("atrasada", -1)

    def test_vence_logo_inclui_o_dia_do_prazo(self):
        assert r.situacao_trilha(3, 1, self.HOJE, self.HOJE).codigo == "vence_logo"
        assert r.situacao_trilha(3, 1, self.HOJE + timedelta(days=7), self.HOJE).codigo == "vence_logo"

    def test_em_dia(self):
        assert r.situacao_trilha(3, 0, self.HOJE + timedelta(days=8), self.HOJE).codigo == "em_dia"

    def test_sem_prazo(self):
        assert r.situacao_trilha(3, 0, None, self.HOJE).codigo == "sem_prazo"

    def test_trilha_vazia_nao_e_concluida(self):
        assert r.situacao_trilha(0, 0, None, self.HOJE).codigo == "sem_prazo"

    def test_percentual_de_trilha_vazia_e_indefinido(self):
        assert r.percentual(0, 0) is None
        assert r.percentual(1, 3) == 33


# ── Próxima aula ─────────────────────────────────────────────────────

def _p(aula, trilha, ordem=1, *, obrig=False, sit="sem_prazo", prazo=None,
       iniciada=False, anterior=False, titulo=None):
    return r.AulaPendente(
        aula_id=aula, aula_titulo=aula, aula_ordem=ordem,
        trilha_id=trilha, trilha_titulo=titulo or trilha, pilar="tecnica",
        obrigatoria=obrig, situacao_trilha=sit, prazo=prazo,
        trilha_iniciada=iniciada, concluiu_versao_anterior=anterior,
    )


class TestProximaAula:
    def test_sem_pendencia_nao_ha_proxima(self):
        assert r.proxima_aula([]) is None

    def test_atrasada_passa_na_frente_de_tudo(self):
        p, motivo = r.proxima_aula([
            _p("a1", "nova"),
            _p("b1", "andamento", iniciada=True),
            _p("c1", "obrig", obrig=True, sit="atrasada", prazo=date(2026, 9, 1)),
        ])
        assert (p.aula_id, motivo) == ("c1", "atrasada")

    def test_vence_logo_antes_de_continuar(self):
        p, motivo = r.proxima_aula([
            _p("b1", "andamento", iniciada=True),
            _p("c1", "obrig", obrig=True, sit="vence_logo", prazo=date(2026, 10, 20)),
        ])
        assert motivo == "vence_logo"

    def test_aula_atualizada_antes_de_trilha_em_andamento(self):
        p, motivo = r.proxima_aula([
            _p("b1", "andamento", iniciada=True),
            _p("x2", "ja-feita", 2, anterior=True, iniciada=True),
        ])
        assert (p.aula_id, motivo) == ("x2", "atualizada")

    def test_dentro_da_trilha_vale_a_primeira_pendente(self):
        p, _ = r.proxima_aula([
            _p("a3", "t", 3), _p("a2", "t", 2), _p("a4", "t", 4),
        ])
        assert p.aula_id == "a2"

    def test_entre_atrasadas_o_prazo_mais_antigo(self):
        p, _ = r.proxima_aula([
            _p("x", "x", obrig=True, sit="atrasada", prazo=date(2026, 9, 20)),
            _p("y", "y", obrig=True, sit="atrasada", prazo=date(2026, 9, 1)),
        ])
        assert p.aula_id == "y"

    def test_obrigatoria_em_dia_antes_de_trilha_livre(self):
        p, motivo = r.proxima_aula([
            _p("livre", "livre", titulo="A livre"),
            _p("obrig", "obrig", obrig=True, sit="em_dia", prazo=date(2026, 12, 1), titulo="Z obrig"),
        ])
        assert (p.aula_id, motivo) == ("obrig", "obrigatoria")

    def test_todo_motivo_tem_texto(self):
        assert set(r.PRIORIDADE) == set(r.MOTIVOS)


# ── Material ─────────────────────────────────────────────────────────

class TestMaterial:
    def test_pdf_e_office_aceitos(self):
        assert m.validar_tipo("application/pdf") == ".pdf"
        assert m.validar_tipo(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ) == ".pptx"

    def test_video_como_arquivo_manda_usar_link(self):
        with pytest.raises(AnexoInvalido, match="cole o link"):
            m.validar_tipo("video/mp4")

    def test_tipo_desconhecido(self):
        with pytest.raises(AnexoInvalido, match="Aceitos"):
            m.validar_tipo("application/x-msdownload")

    def test_limites(self):
        m.validar_tamanho(m.LIMITE_BYTES)
        with pytest.raises(AnexoInvalido):
            m.validar_tamanho(m.LIMITE_BYTES + 1)
        with pytest.raises(AnexoInvalido):
            m.validar_tamanho(0)
        m.validar_quantidade(m.MAX_POR_AULA - 1)
        with pytest.raises(AnexoInvalido):
            m.validar_quantidade(m.MAX_POR_AULA)

    def test_chave_so_de_ids_no_prefixo_da_uc(self):
        assert m.chave_do_objeto("a", "b", ".pdf") == "uc/aulas/a/b.pdf"

    def test_nome_de_norma_sai_limpo(self):
        assert m.nome_seguro("NR-01 atualizada 2025.pdf", ".pdf") == "NR-01-atualizada-2025.pdf"
