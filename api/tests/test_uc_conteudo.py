"""
HIPO — UC: forma do conteúdo das trilhas iniciais (scripts/uc_conteudo.py).

Puro: confere o texto antes de ele chegar ao banco. O que se trava aqui é
o que quebraria a tela, a carga ou a ordem das trilhas.
"""
from scripts import semear_uc
from scripts import uc_conteudo as c


def test_conteudo_sem_problema_de_forma():
    assert semear_uc.conferir() == []


def test_tres_trilhas_na_ordem_com_prazos_crescentes():
    assert [t["titulo"][:2] for t in c.TRILHAS] == ["01", "02", "03"]
    prazos = [t["prazo_dias"] for t in c.TRILHAS]
    assert prazos == sorted(prazos)
    assert all(t["pilar"] == "tecnica" for t in c.TRILHAS)


def test_boas_vindas_traz_a_historia_da_apresentacao():
    texto = c.TRILHA_01["aulas"][0]["conteudo_md"]
    for fato in ("1991", "Dr. Paulo Dick", "Guarulhos", "100 mil vidas", "500 clientes"):
        assert fato in texto
    assert c.TRILHA_01["aulas"][0]["pdf"] == "apresentacao"


def test_trilha_03_reaproveita_a_trilha_de_nr_da_029():
    """Mudar o id criaria uma trilha nova e deixaria a antiga órfã em produção."""
    assert str(c.TRILHA_03["id"]) == "7c1d0f4e-5a01-4c0e-9b11-0000000a0101"
    nr = [a for a in c.TRILHA_03["aulas"] if a.get("pdf") in ("nr01", "nr04")]
    assert [str(a["id"])[-4:] for a in nr] == ["0201", "0206"]


def test_os_tres_pdfs_estao_em_alguma_aula():
    usados = {a.get("pdf") for t in c.TRILHAS for a in t["aulas"]}
    assert usados >= set(c.PDFS)


def test_toda_aula_tem_quiz_para_a_uc2():
    assert all(len(a["quiz"]) >= 3 for t in c.TRILHAS for a in t["aulas"])


def test_vigencia_dos_psicossociais_esta_no_texto():
    texto = next(a for a in c.TRILHA_03["aulas"] if "psicossociais" in a["titulo"])["conteudo_md"]
    assert "26 de maio de 2026" in texto


def test_conferir_pega_quiz_com_duas_corretas(monkeypatch):
    aula = dict(c.TRILHA_01["aulas"][0])
    aula["quiz"] = [{"enunciado": "x", "alternativas": [("a", True), ("b", True), ("c", False)]}]
    trilha = {**c.TRILHA_01, "aulas": [aula]}
    monkeypatch.setattr(semear_uc, "TRILHAS", [trilha])
    assert any("exatamente 1 correta" in e for e in semear_uc.conferir())


def test_senha_do_banco_sai_mascarada():
    assert semear_uc._mascarar("postgresql://u:segredo@host:5432/db") == "postgresql://u:****@host:5432/db"
