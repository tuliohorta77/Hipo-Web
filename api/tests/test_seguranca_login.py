"""
HIPO -- limite de tentativas de login (032).

O que esta suite protege:

  1. Cinco falhas no mesmo e-mail barram a sexta -- inclusive com a senha
     CERTA, que e o ponto de existir um limite.
  2. Barrado, a senha nem e conferida, e a tentativa barrada nao conta (o
     bloqueio nao se renova sozinho).
  3. Acertar a senha zera a contagem do e-mail, nao a do IP.
  4. A janela vence: falha velha nao conta.
  5. Toda tentativa vira linha em login_tentativas, com motivo.
  6. O limite nunca derruba o login: se a checagem falhar, o login segue.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import settings
from services import login_limite
from tests.conftest import criar_usuario


async def tentar(client, email, senha, ip=None):
    headers = {"X-Real-IP": ip} if ip else {}
    return await client.post(
        "/auth/login", data={"username": email, "password": senha}, headers=headers,
    )


# ── Regras puras ──────────────────────────────────────────────────────

class TestRegras:
    def test_avaliar(self):
        assert login_limite.avaliar(4, 19, max_email=5, max_ip=20) is None
        assert login_limite.avaliar(5, 0, max_email=5, max_ip=20) == "email"
        assert login_limite.avaliar(0, 20, max_email=5, max_ip=20) == "ip"
        # Os dois estouram: o do e-mail tem a mensagem mais util.
        assert login_limite.avaliar(9, 99, max_email=5, max_ip=20) == "email"

    def test_limite_zero_desliga_aquela_contagem(self):
        assert login_limite.avaliar(100, 0, max_email=0, max_ip=20) is None
        assert login_limite.avaliar(0, 100, max_email=5, max_ip=0) is None

    def test_segundos_para_liberar(self):
        agora = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
        janela = timedelta(minutes=15)
        libera = agora - timedelta(minutes=10)
        assert login_limite.segundos_para_liberar(libera, agora, janela) == 300
        # Ja vencida (corrida entre a contagem e o calculo): nunca 0.
        assert login_limite.segundos_para_liberar(agora - janela * 2, agora, janela) == 1
        assert login_limite.segundos_para_liberar(None, agora, janela) == 900

    def test_mensagem_em_minutos_arredondando_para_cima(self):
        assert "1 minuto." in login_limite.Decisao(True, "email", 30).mensagem()
        assert "5 minutos." in login_limite.Decisao(True, "email", 241).mensagem()

    def test_normalizar_email(self):
        assert login_limite.normalizar_email("  Fulano@Empresa.COM ") == "fulano@empresa.com"
        assert login_limite.normalizar_email(None) == ""

    def test_ip_atras_do_nginx_usa_x_real_ip(self):
        req = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"x-real-ip": "200.1.2.3"},
        )
        assert login_limite.ip_do_cliente(req) == "200.1.2.3"

    def test_x_real_ip_de_fora_e_ignorado(self):
        """Peer que nao e o nginx nao consegue escolher o proprio IP."""
        req = SimpleNamespace(
            client=SimpleNamespace(host="200.9.9.9"),
            headers={"x-real-ip": "1.1.1.1"},
        )
        assert login_limite.ip_do_cliente(req) == "200.9.9.9"


# ── Endpoint ──────────────────────────────────────────────────────────

class TestLimitePorEmail:
    async def test_sexta_tentativa_barrada_mesmo_com_senha_certa(
        self, db_conn, client, usuario_adm
    ):
        for _ in range(settings.LOGIN_MAX_FALHAS_EMAIL):
            r = await tentar(client, usuario_adm["email"], "errada")
            assert r.status_code == 401

        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"])
        assert r.status_code == 429
        assert "Muitas tentativas" in r.json()["detail"]
        retry = int(r.headers["retry-after"])
        assert 0 < retry <= settings.LOGIN_JANELA_MIN * 60

    async def test_barrado_nao_confere_senha(
        self, db_conn, client, usuario_adm, monkeypatch
    ):
        for _ in range(settings.LOGIN_MAX_FALHAS_EMAIL):
            await tentar(client, usuario_adm["email"], "errada")

        from routers import auth

        def explode(*a, **k):
            raise AssertionError("bcrypt rodou com o login bloqueado")

        monkeypatch.setattr(auth, "_verificar_senha", explode)
        r = await tentar(client, usuario_adm["email"], "qualquer")
        assert r.status_code == 429

    async def test_tentativa_barrada_nao_renova_o_bloqueio(
        self, db_conn, client, usuario_adm
    ):
        for _ in range(settings.LOGIN_MAX_FALHAS_EMAIL):
            await tentar(client, usuario_adm["email"], "errada")
        for _ in range(3):
            assert (await tentar(client, usuario_adm["email"], "x")).status_code == 429

        contadas = await db_conn.fetchval(
            "SELECT count(*) FROM login_tentativas"
            " WHERE email = $1 AND motivo <> 'bloqueado' AND NOT sucesso",
            usuario_adm["email"],
        )
        bloqueadas = await db_conn.fetchval(
            "SELECT count(*) FROM login_tentativas WHERE motivo = 'bloqueado'"
        )
        assert contadas == settings.LOGIN_MAX_FALHAS_EMAIL
        assert bloqueadas == 3

    async def test_sucesso_zera_a_contagem_do_email(
        self, db_conn, client, usuario_adm
    ):
        limite = settings.LOGIN_MAX_FALHAS_EMAIL
        for _ in range(limite - 1):
            await tentar(client, usuario_adm["email"], "errada")
        assert (await tentar(client, usuario_adm["email"], usuario_adm["senha"])).status_code == 200
        for _ in range(limite - 1):
            assert (await tentar(client, usuario_adm["email"], "errada")).status_code == 401
        # 2*(limite-1) falhas no total, mas so limite-1 depois do acerto.
        assert (await tentar(client, usuario_adm["email"], usuario_adm["senha"])).status_code == 200

    async def test_falha_fora_da_janela_nao_conta(
        self, db_conn, client, usuario_adm
    ):
        velho = datetime.now(timezone.utc) - timedelta(minutes=settings.LOGIN_JANELA_MIN + 1)
        for _ in range(settings.LOGIN_MAX_FALHAS_EMAIL * 2):
            await db_conn.execute(
                "INSERT INTO login_tentativas (email, ip, sucesso, motivo, criado_em)"
                " VALUES ($1, '127.0.0.1', FALSE, 'senha', $2)",
                usuario_adm["email"], velho,
            )
        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"])
        assert r.status_code == 200

    async def test_maiuscula_no_email_e_o_mesmo_alvo(
        self, db_conn, client, usuario_adm
    ):
        for _ in range(settings.LOGIN_MAX_FALHAS_EMAIL):
            await tentar(client, usuario_adm["email"].upper(), "errada")
        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"])
        assert r.status_code == 429

    async def test_login_aceita_email_com_maiuscula(self, db_conn, client, usuario_adm):
        r = await tentar(client, "  " + usuario_adm["email"].upper(), usuario_adm["senha"])
        assert r.status_code == 200, r.text

    async def test_limite_desligado_por_env(
        self, db_conn, client, usuario_adm, monkeypatch
    ):
        monkeypatch.setattr(settings, "LOGIN_LIMITE_ATIVO", False)
        for _ in range(settings.LOGIN_MAX_FALHAS_EMAIL + 2):
            await tentar(client, usuario_adm["email"], "errada")
        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"])
        assert r.status_code == 200


class TestLimitePorIp:
    async def test_varredura_de_emails_do_mesmo_ip_e_barrada(
        self, db_conn, client, usuario_adm, monkeypatch
    ):
        monkeypatch.setattr(settings, "LOGIN_MAX_FALHAS_IP", 3)
        for i in range(3):
            await tentar(client, f"alvo{i}@teste.com", "x", ip="200.1.2.3")

        # E-mail novo, nunca tentado -- barrado pelo IP.
        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"], ip="200.1.2.3")
        assert r.status_code == 429

        # Outro IP segue livre.
        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"], ip="200.9.9.9")
        assert r.status_code == 200

    async def test_sucesso_nao_zera_a_contagem_do_ip(
        self, db_conn, client, usuario_adm, monkeypatch
    ):
        monkeypatch.setattr(settings, "LOGIN_MAX_FALHAS_IP", 3)
        for i in range(2):
            await tentar(client, f"alvo{i}@teste.com", "x", ip="200.1.2.3")
        ok = await tentar(client, usuario_adm["email"], usuario_adm["senha"], ip="200.1.2.3")
        assert ok.status_code == 200
        await tentar(client, "alvo9@teste.com", "x", ip="200.1.2.3")
        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"], ip="200.1.2.3")
        assert r.status_code == 429


class TestRegistro:
    async def test_cada_tentativa_vira_linha_com_motivo(
        self, db_conn, client, usuario_adm
    ):
        await db_conn.execute("TRUNCATE login_tentativas")
        await tentar(client, usuario_adm["email"], "errada", ip="200.1.2.3")
        await tentar(client, "ninguem@teste.com", "x", ip="200.1.2.3")
        await tentar(client, usuario_adm["email"], usuario_adm["senha"], ip="200.1.2.3")

        linhas = await db_conn.fetch(
            "SELECT email, ip, sucesso, motivo, user_agent"
            " FROM login_tentativas ORDER BY id"
        )
        assert [(r["email"], r["sucesso"], r["motivo"]) for r in linhas] == [
            (usuario_adm["email"], False, "senha"),
            ("ninguem@teste.com", False, "inativo_ou_inexistente"),
            (usuario_adm["email"], True, None),
        ]
        assert all(r["ip"] == "200.1.2.3" for r in linhas)

    async def test_resposta_igual_para_email_inexistente_e_senha_errada(
        self, db_conn, client, usuario_adm
    ):
        a = await tentar(client, usuario_adm["email"], "errada")
        b = await tentar(client, "ninguem@teste.com", "errada")
        assert a.status_code == b.status_code == 401
        assert a.json() == b.json()

    async def test_usuario_inativo_conta_como_falha(self, db_conn, client, usuario_adm):
        await db_conn.execute(
            "UPDATE usuarios SET ativo = FALSE WHERE email = $1", usuario_adm["email"]
        )
        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"])
        assert r.status_code == 401
        motivo = await db_conn.fetchval(
            "SELECT motivo FROM login_tentativas ORDER BY id DESC LIMIT 1"
        )
        assert motivo == "inativo_ou_inexistente"


class TestNuncaDerrubaOLogin:
    async def test_checagem_quebrada_libera_o_login(
        self, db_conn, client, usuario_adm, monkeypatch
    ):
        async def quebrada(*a, **k):
            raise RuntimeError("relation login_tentativas does not exist")

        monkeypatch.setattr(login_limite, "verificar", quebrada)
        r = await tentar(client, usuario_adm["email"], usuario_adm["senha"])
        assert r.status_code == 200

    async def test_gravacao_quebrada_nao_derruba(self, db_conn, client, usuario_adm):
        class ConnQuebrada:
            async def execute(self, *a, **k):
                raise RuntimeError("banco fora")

        # Nao levanta: so loga.
        await login_limite.registrar(
            ConnQuebrada(), "x@y.com", None, sucesso=False, motivo="senha",
        )


class TestRetencao:
    async def test_apaga_so_o_que_passou_do_prazo(self, db_conn):
        await db_conn.execute(
            "INSERT INTO login_tentativas (email, sucesso, motivo, criado_em) VALUES"
            " ('velho@x.com', FALSE, 'senha', NOW() - INTERVAL '200 days'),"
            " ('novo@x.com',  FALSE, 'senha', NOW() - INTERVAL '10 days')"
        )
        apagados = await login_limite.aplicar_retencao(db_conn, 180)
        assert apagados == 1
        restou = await db_conn.fetchval("SELECT email FROM login_tentativas")
        assert restou == "novo@x.com"

    async def test_zero_nao_apaga(self, db_conn):
        await db_conn.execute(
            "INSERT INTO login_tentativas (email, sucesso, motivo, criado_em)"
            " VALUES ('velho@x.com', FALSE, 'senha', NOW() - INTERVAL '900 days')"
        )
        assert await login_limite.aplicar_retencao(db_conn, 0) == 0


class TestHistoricoDeLogin:
    async def test_gestao_le_o_historico(self, db_conn, client, usuario_adm):
        await tentar(client, "ninguem@teste.com", "x")
        r = await client.get(
            "/telemetria/logins", params={"so_falhas": True},
            headers=usuario_adm["headers"],
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["total"] >= 1
        assert corpo["itens"][0]["email"] == "ninguem@teste.com"
        assert corpo["falhas_24h"].get("inativo_ou_inexistente") == 1

    async def test_filtro_por_email(self, db_conn, client, usuario_adm):
        await tentar(client, "alguem@teste.com", "x")
        r = await client.get(
            "/telemetria/logins", params={"email": "ALGUEM@teste.com"},
            headers=usuario_adm["headers"],
        )
        assert [i["email"] for i in r.json()["itens"]] == ["alguem@teste.com"]

    @pytest.mark.parametrize("cargo", ["SDR", "EV", "EC", "EP"])
    async def test_operacional_nao_ve(self, db_conn, client, cargo):
        u = await criar_usuario(db_conn, client, cargo)
        r = await client.get("/telemetria/logins", headers=u["headers"])
        assert r.status_code == 403
