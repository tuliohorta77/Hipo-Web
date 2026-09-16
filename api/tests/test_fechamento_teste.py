"""
HIPO - Modo --teste do fechamento diario (puro, sem banco e sem SES).
"""
from __future__ import annotations

from datetime import datetime

from scripts import fechamento_diario as f


class TestAssuntoDeTeste:
    def test_prefixo_com_hora(self):
        assert f.assunto_de_teste("HIPO 15/09 — 5 pessoas", datetime(2026, 9, 16, 19, 41, 7)) \
            == "[TESTE 19:41:07] HIPO 15/09 — 5 pessoas"

    def test_dois_envios_no_mesmo_minuto_tem_assuntos_diferentes(self):
        """Assunto igual volta a empilhar na mesma conversa do Gmail."""
        a = f.assunto_de_teste("X", datetime(2026, 9, 16, 19, 41, 7))
        b = f.assunto_de_teste("X", datetime(2026, 9, 16, 19, 41, 40))
        assert a != b


class TestArgumentos:
    def test_para_sem_teste_e_recusado(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["x", "--dia", "2026-09-15", "--para", "a@b.com"])
        chamado = []
        monkeypatch.setattr(f, "executar", lambda *a, **k: chamado.append(1))
        assert f.main() == 1
        assert not chamado

    def test_teste_repassa_destinatarios(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["x", "--dia", "2026-09-15", "--teste",
                                         "--para", "a@b.com, c@d.com"])
        recebido = {}

        async def falso(dia, **kw):
            recebido.update(kw, dia=dia)
            return 0

        monkeypatch.setattr(f, "executar", falso)
        assert f.main() == 0
        assert recebido["teste"] is True
        assert recebido["para_override"] == ["a@b.com", "c@d.com"]
