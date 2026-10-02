"""
HIPO — UC: forma do conteúdo da trilha de NR-01 e NR-04 (scripts/semear_uc_nr.py).

Puro: confere o texto antes de ele chegar ao banco. O conteúdo em si foi
escrito a partir das normas; o que se trava aqui é o que quebraria a tela
ou a carga.
"""
from scripts import semear_uc_nr as nr


def test_conteudo_sem_problema_de_forma():
    assert nr.conferir() == []


def test_seis_aulas_na_ordem_da_trilha():
    titulos = [a["titulo"] for a in nr.AULAS]
    assert len(titulos) == 6
    assert titulos[0].startswith("NR-01")
    assert titulos[-1].startswith("NR-04")


def test_os_dois_pdfs_estao_anexados_a_alguma_aula():
    assert {a.get("pdf") for a in nr.AULAS} >= {"nr01", "nr04"}


def test_manual_da_funcao_cobre_quem_fala_com_cliente():
    cargos = {c["cargo"] for c in nr.TRILHA["cargos"]}
    assert cargos == {"SDR", "EV", "EC", "EP", "ADM"}
    assert all(c["obrigatoria"] and c["prazo_dias"] == 30 for c in nr.TRILHA["cargos"])


def test_toda_aula_tem_quiz_para_a_uc2():
    assert all(len(a["quiz"]) >= 3 for a in nr.AULAS)


def test_vigencia_dos_psicossociais_esta_no_texto():
    """A data que o vendedor vai repetir para o cliente precisa estar certa."""
    texto = next(a for a in nr.AULAS if "psicossociais" in a["titulo"])["conteudo_md"]
    assert "26 de maio de 2026" in texto


def test_conferir_pega_quiz_com_duas_corretas(monkeypatch):
    aula = dict(nr.AULAS[0])
    aula["quiz"] = [{"enunciado": "x", "alternativas": [("a", True), ("b", True), ("c", False)]}]
    monkeypatch.setattr(nr, "AULAS", [aula] + nr.AULAS[1:])
    assert any("exatamente 1 correta" in e for e in nr.conferir())


def test_senha_do_banco_sai_mascarada():
    assert nr._mascarar("postgresql://u:segredo@host:5432/db") == "postgresql://u:****@host:5432/db"
