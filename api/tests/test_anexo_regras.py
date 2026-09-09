"""
Regras de anexo de tarefa — testes puros, sem banco e sem AWS.

Rodam no pytest local do Windows (que não tem Postgres) e no CI. O que
depende de bucket não é testado aqui de propósito: dublar o boto3 para
provar que `put_object` foi chamado testaria o boto3, não a regra.
"""
from uuid import UUID

import pytest

from services import anexo as regras
from services.anexo import AnexoInvalido


# ── Tipos aceitos ────────────────────────────────────────────────────

class TestValidarTipo:
    @pytest.mark.parametrize("mime,ext", [
        ("image/png", ".png"),
        ("image/jpeg", ".jpg"),
        ("image/webp", ".webp"),
        ("image/gif", ".gif"),
        ("application/pdf", ".pdf"),
    ])
    def test_aceita_os_tipos_do_catalogo(self, mime, ext):
        assert regras.validar_tipo(mime) == ext

    def test_ignora_parametros_do_content_type(self):
        """
        'image/png; charset=binary' chega assim de alguns clientes. Sem
        cortar no ';' o tipo nunca casaria com a tabela, e o upload seria
        recusado com "tipo não aceito" para um PNG legítimo.
        """
        assert regras.validar_tipo("image/png; charset=binary") == ".png"

    def test_ignora_caixa(self):
        assert regras.validar_tipo("IMAGE/PNG") == ".png"

    def test_heic_recusa_explicando_o_caminho(self):
        """
        Aceitar HEIC produziria um anexo que sobe, ocupa storage e aparece
        como quadrado quebrado — o usuário só descobriria depois. A recusa
        precisa dizer o que fazer, não só que não deu.
        """
        with pytest.raises(AnexoInvalido) as e:
            regras.validar_tipo("image/heic")
        assert "iPhone" in str(e.value)

    @pytest.mark.parametrize("mime", [
        "application/zip", "text/html", "application/x-msdownload", "", None,
    ])
    def test_recusa_o_resto(self, mime):
        with pytest.raises(AnexoInvalido):
            regras.validar_tipo(mime)

    def test_mensagem_de_recusa_lista_os_aceitos(self):
        with pytest.raises(AnexoInvalido) as e:
            regras.validar_tipo("application/zip")
        assert "PNG" in str(e.value)


# ── Tamanho e quantidade ─────────────────────────────────────────────

class TestLimites:
    def test_aceita_tamanho_normal(self):
        regras.validar_tamanho(2 * 1024 * 1024)   # print de celular

    def test_recusa_vazio(self):
        with pytest.raises(AnexoInvalido):
            regras.validar_tamanho(0)

    def test_recusa_acima_do_limite(self):
        with pytest.raises(AnexoInvalido) as e:
            regras.validar_tamanho(regras.LIMITE_BYTES + 1)
        assert str(regras.LIMITE_MB) in str(e.value)

    def test_o_limite_exato_passa(self):
        """Fronteira: 10 MB cravados é aceito, 10 MB + 1 byte não."""
        regras.validar_tamanho(regras.LIMITE_BYTES)

    def test_quantidade_por_tarefa(self):
        regras.validar_quantidade(regras.MAX_POR_TAREFA - 1)
        with pytest.raises(AnexoInvalido):
            regras.validar_quantidade(regras.MAX_POR_TAREFA)


# ── Nome seguro ──────────────────────────────────────────────────────

class TestNomeSeguro:
    def test_mantem_um_nome_comum(self):
        assert regras.nome_seguro("print da conversa.png", ".png") == "print-da-conversa.png"

    def test_descarta_caminho(self):
        """
        Travessia de caminho: o nome volta num header e um dia alguém vai
        usá-lo para montar caminho. Só o último segmento sobrevive.
        """
        assert regras.nome_seguro(r"..\..\etc\senha.png", ".png") == "senha.png"
        assert regras.nome_seguro("/var/www/foto.jpg", ".jpg") == "foto.jpg"

    def test_tira_acento(self):
        assert regras.nome_seguro("proposta assinada.pdf", ".pdf") == "proposta-assinada.pdf"
        assert regras.nome_seguro("negociação.png", ".png") == "negociacao.png"

    def test_vazio_vira_anexo(self):
        """Imagem colada do clipboard chega sem nome nenhum."""
        assert regras.nome_seguro(None, ".png") == "anexo.png"
        assert regras.nome_seguro("   ", ".png") == "anexo.png"

    def test_so_pontuacao_vira_anexo(self):
        assert regras.nome_seguro("...", ".png") == "anexo.png"

    def test_extensao_vem_do_tipo_e_nao_do_nome(self):
        """
        ".png" no nome não prova que o conteúdo é png. Quem decide é o
        content-type validado, e o nome recebe a extensão canônica.
        """
        assert regras.nome_seguro("foto.exe", ".png") == "foto.png"

    def test_nao_estoura_o_limite_da_coluna(self):
        nome = regras.nome_seguro("a" * 500, ".png")
        assert len(nome) <= 255

    def test_sem_caractere_que_quebra_header(self):
        sujo = 'rela"tório\r\nX-Falso: 1.png'
        limpo = regras.nome_seguro(sujo, ".png")
        assert '"' not in limpo and "\r" not in limpo and "\n" not in limpo


# ── Chave do objeto ──────────────────────────────────────────────────

class TestChaveDoObjeto:
    def test_deriva_so_de_ids(self):
        t = UUID("11111111-1111-1111-1111-111111111111")
        a = UUID("22222222-2222-2222-2222-222222222222")
        assert regras.chave_do_objeto(t, a, ".png") == f"tarefas/{t}/{a}.png"

    def test_nao_carrega_nada_do_nome_do_usuario(self):
        """
        A chave é o caminho real dentro do bucket. Nome de usuário nela
        seria travessia de caminho com efeito de verdade — por isso ela
        não recebe o nome, nem sanitizado.
        """
        t = UUID("11111111-1111-1111-1111-111111111111")
        a = UUID("22222222-2222-2222-2222-222222222222")
        chave = regras.chave_do_objeto(t, a, ".png")
        assert ".." not in chave
        assert chave.count("/") == 2


# ── Imutabilidade do histórico ───────────────────────────────────────

class TestPodeAlterar:
    def test_tarefa_aberta_aceita(self):
        assert regras.pode_alterar(None, None) is True

    def test_concluida_congela(self):
        assert regras.pode_alterar("2026-09-09T12:00:00Z", None) is False

    def test_cancelada_congela(self):
        assert regras.pode_alterar(None, "2026-09-09T12:00:00Z") is False


# ── Disponibilidade do serviço ───────────────────────────────────────

class TestDisponibilidade:
    def test_sem_bucket_configurado_diz_o_que_falta(self, monkeypatch):
        """
        503 com mensagem acionável, não 500 genérico. A 009 subiu verde e
        a tela dizia só "erro ao gerar" — o usuário não tinha como saber
        que faltava uma biblioteca no servidor.
        """
        from config import settings
        monkeypatch.setattr(settings, "S3_BUCKET_ANEXOS", "")
        problemas = regras.problemas()
        assert any("S3_BUCKET_ANEXOS" in p for p in problemas)
        assert not regras.disponivel()

    def test_com_bucket_configurado_o_problema_do_bucket_some(self, monkeypatch):
        """
        A regra testável aqui é só a do bucket. Se o boto3 está instalado
        ou não é outra pergunta — e é uma pergunta sobre o AMBIENTE, não
        sobre a regra.

        A primeira versão deste teste exigia `disponivel()` inteiro e
        quebrava no Windows, onde o venv local não tem o boto3 do
        requirements. Um teste que se anuncia como puro e depende de
        biblioteca de runtime instalada mente sobre o próprio escopo, e o
        preço é um deploy abortado por algo que o CI passaria.
        """
        from config import settings
        monkeypatch.setattr(settings, "S3_BUCKET_ANEXOS", "hipo-anexos-teste")
        assert not any("S3_BUCKET_ANEXOS" in p for p in regras.problemas())

    def test_com_boto3_e_bucket_o_servico_fica_disponivel(self, monkeypatch):
        """
        O caso completo, e só onde o boto3 existe: no CI, que instala o
        requirements. Local sem boto3, o teste é pulado em vez de
        vermelho — a ausência da lib não é regressão do código.
        """
        pytest.importorskip(
            "boto3",
            reason="boto3 é dependência de runtime; o venv local nem sempre tem",
        )
        from config import settings
        monkeypatch.setattr(settings, "S3_BUCKET_ANEXOS", "hipo-anexos-teste")
        assert regras.disponivel(), regras.problemas()
