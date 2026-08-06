"""
HIPO — Testes da lista de seed de usuários.

Testes puros (sem banco): garantem que a lista da equipe nunca entre em
produção com e-mail duplicado ou cargo que o sistema não reconhece — o que
criaria um usuário capaz de logar mas sem módulo nenhum.
"""
import pytest

from routers.permissions import CARGOS_VALIDOS, modulos_do_cargo
from scripts.seed_usuarios import SENHA_PADRAO, USUARIOS, validar_lista


class TestListaDeUsuarios:
    def test_lista_nao_esta_vazia(self):
        """Lista vazia + RESET deixaria o banco sem nenhum login."""
        assert len(USUARIOS) > 0

    def test_validar_lista_passa(self):
        validar_lista()

    def test_todos_os_cargos_sao_validos(self):
        for nome, email, cargo in USUARIOS:
            assert cargo in CARGOS_VALIDOS, f"{email} tem cargo invalido: {cargo}"

    def test_todo_usuario_recebe_ao_menos_um_modulo(self):
        for nome, email, cargo in USUARIOS:
            assert modulos_do_cargo(cargo), f"{email} ({cargo}) nao receberia modulo nenhum"

    def test_emails_sao_unicos(self):
        emails = [email.lower() for _, email, _ in USUARIOS]
        assert len(emails) == len(set(emails))

    def test_emails_tem_formato_minimo(self):
        for nome, email, cargo in USUARIOS:
            assert "@" in email and "." in email.split("@")[-1], f"email suspeito: {email}"

    def test_nomes_preenchidos(self):
        for nome, email, cargo in USUARIOS:
            assert nome and nome.strip(), f"{email} esta sem nome"

    def test_existe_ao_menos_um_franqueado(self):
        """Sem um cargo de gestao ninguem administra usuarios."""
        cargos = {cargo for _, _, cargo in USUARIOS}
        assert cargos & {"Franqueado", "ADM"}

    def test_senha_padrao_atende_o_minimo_da_api(self):
        """PUT /auth/senha exige min_length=6; a padrao nao pode ser menor."""
        assert len(SENHA_PADRAO) >= 6


class TestValidacaoFalha:
    def test_cargo_invalido_e_rejeitado(self, monkeypatch):
        import scripts.seed_usuarios as seed

        monkeypatch.setattr(seed, "USUARIOS", [("Fulano", "f@x.com", "Gerente")])
        with pytest.raises(ValueError, match="invalido"):
            seed.validar_lista()

    def test_email_duplicado_e_rejeitado(self, monkeypatch):
        import scripts.seed_usuarios as seed

        monkeypatch.setattr(seed, "USUARIOS", [
            ("Fulano", "f@x.com", "EV"),
            ("Ciclano", "F@X.com", "SDR"),
        ])
        with pytest.raises(ValueError, match="[Dd]uplicado"):
            seed.validar_lista()

    def test_lista_vazia_e_rejeitada(self, monkeypatch):
        import scripts.seed_usuarios as seed

        monkeypatch.setattr(seed, "USUARIOS", [])
        with pytest.raises(ValueError, match="vazia"):
            seed.validar_lista()
