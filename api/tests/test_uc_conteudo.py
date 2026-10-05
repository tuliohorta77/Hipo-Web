"""
HIPO — UC: forma do conteúdo das trilhas iniciais (scripts/uc_conteudo.py).

Puro: confere o texto antes de ele chegar ao banco. O que se trava aqui é
o que quebraria a tela, a carga ou a ordem das trilhas.
"""
from scripts import semear_uc
from scripts import uc_conteudo as c


def test_conteudo_sem_problema_de_forma():
    assert semear_uc.conferir() == []


def test_trilhas_na_ordem_com_prazos_crescentes():
    """O prazo é o que ordena a próxima aula entre obrigatórias em dia."""
    base = c.TRILHAS[:5]
    assert [t["titulo"][:2] for t in base] == ["01", "02", "03", "04", "02"]
    assert [t["pilar"] for t in base] == ["tecnica"] * 4 + ["metodo"]
    prazos = [t["prazo_dias"] for t in base]
    assert prazos == sorted(prazos) and len(set(prazos)) == len(prazos)


def test_cada_cargo_tem_prazos_distintos_no_manual():
    """Duas obrigatórias com o mesmo prazo empatariam na próxima aula."""
    for cargo in ("SDR", "EV", "EC", "EP", "ADM"):
        prazos = [t["prazo_dias"] for t in c.TRILHAS
                  if cargo in t.get("obrigatorios", c.CARGOS_OBRIGATORIOS)]
        assert len(set(prazos)) == len(prazos), cargo


def test_tecnica_ensina_e_metodo_aplica():
    """Pedido do Tulio: teoria em profundidade na Técnica, aplicação no Método."""
    assert c.TRILHA_04["pilar"] == "tecnica"
    assert c.METODO_01["pilar"] == "metodo" and c.METODO_01["reforca"] == "roteiro"
    teoria = " ".join(a["conteudo_md"] for a in c.TRILHA_04["aulas"])
    for tecnica in ("SPIN", "GPCT", "LAER", "Sandler", "Challenger"):
        assert tecnica in teoria
    pratica = " ".join(a["conteudo_md"] for a in c.METODO_01["aulas"])
    for regra in ("45 minutos", "scorecard", "D+21", "6 ou mais verdes", "Deixa eu ver se entendi"):
        assert regra in pratica


def test_scorecard_do_metodo_bate_com_o_do_hipo():
    """Os 10 itens ensinados são os mesmos que a avaliação de roteiro usa."""
    aula = c.METODO_01["aulas"][-1]["conteudo_md"]
    for item in ("Preparação", "Contrato de abertura", "Perguntas de Situação",
                 "Perguntas de Problema", "Perguntas de Implicação",
                 "Resumo de confirmação", "GPCT: prazo, decisor e consequência",
                 "Apresentação ligada às dores", "Objeções com LAER",
                 "Próximo passo com data"):
        assert item in aula


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


def test_todos_os_pdfs_estao_em_alguma_aula():
    usados = {a.get("pdf") for t in c.TRILHAS for a in t["aulas"]}
    assert usados >= set(c.PDFS)


def test_toda_aula_tem_quiz_de_sete_perguntas():
    """Decisão de 05/10/2026: 7 perguntas, 85% (6 de 7) para aprovar."""
    assert all(len(a["quiz"]) == 7 for t in c.TRILHAS for a in t["aulas"])


def test_vigencia_dos_psicossociais_esta_no_texto():
    texto = next(a for a in c.TRILHA_03["aulas"] if "psicossociais" in a["titulo"])["conteudo_md"]
    assert "26 de maio de 2026" in texto


def test_conferir_pega_quiz_com_duas_corretas(monkeypatch):
    aula = dict(c.TRILHA_01["aulas"][0])
    aula["quiz"] = [dict(q) for q in aula["quiz"]]
    aula["quiz"][2] = {"enunciado": "x", "alternativas": [("a", True), ("b", True), ("c", False)]}
    trilha = {**c.TRILHA_01, "aulas": [aula]}
    monkeypatch.setattr(semear_uc, "TRILHAS", [trilha])
    assert any("exatamente uma alternativa correta" in e for e in semear_uc.conferir())


def test_conferir_pega_quiz_com_menos_de_sete(monkeypatch):
    aula = dict(c.TRILHA_01["aulas"][0])
    aula["quiz"] = aula["quiz"][:3]
    trilha = {**c.TRILHA_01, "aulas": [aula]}
    monkeypatch.setattr(semear_uc, "TRILHAS", [trilha])
    assert any("precisa de exatamente 7" in e for e in semear_uc.conferir())


def test_senha_do_banco_sai_mascarada():
    assert semear_uc._mascarar("postgresql://u:segredo@host:5432/db") == "postgresql://u:****@host:5432/db"


# ── Roteiros do SDR e do EC (Método 02 e 03) ─────────────────────────

def test_roteiros_sdr_e_ec_um_por_cargo():
    from scripts import uc_conteudo_roteiros as r
    assert r.METODO_02["obrigatorios"] == ("SDR",)
    assert r.METODO_03["obrigatorios"] == ("EC",)
    for t in r.TRILHAS_ROTEIROS:
        assert t["pilar"] == "metodo" and t in c.TRILHAS
        assert set(t["opcionais"]) == {"ADM", "Franqueado"}


def test_roteiro_do_sdr_segue_as_decisoes_do_tulio():
    """Decisor + interesse marca a reunião; canais: ligação, WhatsApp e e-mail; SDR não fala preço."""
    from scripts import uc_conteudo_roteiros as r
    texto = " ".join(a["conteudo_md"] for a in r.METODO_02["aulas"])
    for regra in ("Decisor", "Interesse", "Ligação", "WhatsApp", "E-mail",
                  "Falar preço", "Agendado por", "Lead"):
        assert regra in texto, regra


def test_roteiro_do_ec_fala_de_comissao_recorrente_sem_numero():
    """O percentual é da gestão: nenhum número de comissão pode virar promessa no texto."""
    import re
    from scripts import uc_conteudo_roteiros as r
    texto = " ".join(a["conteudo_md"] for a in r.METODO_03["aulas"])
    assert "omissão recorrente" in texto and "tabela vigente" in texto
    assert not re.search(r"\d+\s*%", texto)
    for termo in ("6920-6/01", "Finder", "S-2220", "S-2240", "devolutiva"):
        assert termo in texto, termo


# ── Energia 01 ───────────────────────────────────────────────────────

def test_energia_01_no_pilar_certo_e_com_os_temas_pedidos():
    from scripts import uc_conteudo_energia as e
    t = e.ENERGIA_01
    assert t["pilar"] == "energia" and t in c.TRILHAS
    assert t["obrigatorios"] == ("SDR", "EV", "EC")
    texto = " ".join(a["conteudo_md"] for a in t["aulas"])
    for tema in ("conta reversa", "mínimo diário", "lotes", "pausa", "resiliência",
                 "Monitor", "diária", "sem ranking"):
        assert tema.lower() in texto.lower(), tema


def test_energia_01_marca_os_numeros_como_exemplo():
    """Os números da conta reversa são ilustrativos: o texto precisa dizer isso."""
    from scripts import uc_conteudo_energia as e
    aula = e.ENERGIA_01["aulas"][1]["conteudo_md"]
    assert "exemplo ilustrativo" in aula and "Não são meta nem taxa oficial" in aula



# ── Técnicas do SDR na prática (Método 04) ───────────────────────────

def test_tecnicas_do_sdr_treinam_cada_tecnica_com_pratica():
    """Pedido de 05/10/2026: cada técnica do roteiro, com exercício e role-play."""
    from scripts import uc_conteudo_tecnicas_sdr as t
    m = t.METODO_04
    assert m in c.TRILHAS and m["pilar"] == "tecnica"
    assert m["titulo"] == "04 · Técnicas do SDR na prática"
    assert m["obrigatorios"] == ("SDR",) and set(m["opcionais"]) == {"ADM", "Franqueado"}
    assert len(m["aulas"]) == 9
    for a in m["aulas"]:
        md = a["conteudo_md"]
        for secao in ("## O que é", "## Por que funciona", "## Exercício", "## Role-play"):
            assert secao in md, (a["titulo"], secao)
        assert "Critérios" in md, a["titulo"]


def test_tecnicas_do_sdr_depois_do_roteiro_e_antes_da_energia():
    from scripts import uc_conteudo_roteiros as r
    from scripts import uc_conteudo_energia as e
    from scripts import uc_conteudo_tecnicas_sdr as t
    assert r.METODO_02["prazo_dias"] < t.METODO_04["prazo_dias"] < e.ENERGIA_01["prazo_dias"]


def test_tecnicas_do_sdr_usam_os_fatos_do_roteiro():
    from scripts import uc_conteudo_tecnicas_sdr as t
    texto = " ".join(a["conteudo_md"] for a in t.METODO_04["aulas"])
    for fato in ("26/05/2026", "mais de 500 empresas", "D12", "decisor", "Terça às 10h ou quarta às 15h"):
        assert fato in texto, fato


def test_titulos_sem_o_nome_do_pilar():
    """Tulio, 05/10/2026: o número é a ordem no pilar; o pilar não vai no título."""
    for t in c.TRILHAS:
        assert not t["titulo"].startswith(("Método", "Energia", "Técnica", "HIPO")), t["titulo"]
        assert t["titulo"][:2].isdigit() and t["titulo"][2:5] == " · ", t["titulo"]
