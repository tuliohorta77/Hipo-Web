"""
HIPO — UC: trilhas de uso do HIPO por função e o tour guiado.

Puro, sem banco. O tour aponta para âncoras `data-tour` do front; se uma
tela muda e a âncora some, o balão cai no centro da tela sem destacar
nada. Estes testes leem o código do front e travam isso no CI, além de
garantir que o tour só CLICA no que abre (nunca no que grava) e que cada
trilha só passa por telas que o cargo dela enxerga.
"""
import re
from pathlib import Path

import pytest

from routers.permissions import CARGOS_COM_PARCEIROS, CARGOS_PROSPECCAO
from scripts import semear_uc
from scripts import uc_conteudo as c
from scripts import uc_conteudo_hipo as h
from services import uc as regras

WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def _ancoras_do_front() -> set[str]:
    estaticas: set[str] = set()
    chaves_de_aba: set[str] = set()
    for arq in WEB.rglob("*.jsx"):
        if "tests" in arq.parts:
            continue
        texto = arq.read_text(encoding="utf-8")
        estaticas |= set(re.findall(r'data-tour="([a-z0-9-]+)"', texto))
        # Itens da nav: { to: ..., tour: 'nav-x', ... }
        estaticas |= set(re.findall(r"tour: '([a-z0-9-]+)'", texto))
        # Abas: Tabs gera data-tour={`aba-${key}`} para cada { key: 'x' }.
        chaves_de_aba |= set(re.findall(r"\{ key: '([a-z0-9-]+)'", texto))
    return estaticas | {f"aba-{k}" for k in chaves_de_aba}


def _passos():
    """Todo passo de tour de todas as trilhas (as de uso e as que só citam o HIPO)."""
    for t in c.TRILHAS:
        for a in t["aulas"]:
            for i, p in enumerate(a.get("tour") or [], start=1):
                yield t, a, i, p


needs_web = pytest.mark.skipif(not WEB.is_dir(), reason="sem o código do front ao lado")


def test_tres_trilhas_no_metodo_uma_por_funcao():
    assert [t["titulo"] for t in h.TRILHAS_HIPO] == ["01 · HIPO - SDR", "01 · HIPO - EV", "01 · HIPO - EC"]
    assert [t["obrigatorios"] for t in h.TRILHAS_HIPO] == [("SDR",), ("EV",), ("EC",)]
    for t in h.TRILHAS_HIPO:
        assert t["pilar"] == "metodo"
        assert set(t["opcionais"]) == {"ADM", "Franqueado"}
        assert t in c.TRILHAS


def test_hipo_vem_logo_depois_das_boas_vindas():
    """Aprender a ferramenta cedo: prazo entre a 01 (10) e a 02 (20)."""
    for t in h.TRILHAS_HIPO:
        assert c.TRILHA_01["prazo_dias"] < t["prazo_dias"] < c.TRILHA_02["prazo_dias"]


def test_toda_aula_de_uso_tem_tour_valido():
    for t in h.TRILHAS_HIPO:
        for a in t["aulas"]:
            assert a.get("tour"), a["titulo"]
            assert regras.validar_tour(a["tour"]) is not None
    assert semear_uc.conferir() == []


def test_tour_so_clica_no_que_abre():
    for t, a, i, p in _passos():
        for clique in p.get("clicar", []):
            assert clique in h.ABRIDORES, f"{a['titulo']}, passo {i}: clique em {clique}"


def test_tour_so_passa_por_tela_que_o_cargo_enxerga():
    restritas = {"/crm/prospeccao": CARGOS_PROSPECCAO, "/crm/parceiros": CARGOS_COM_PARCEIROS}
    for t, a, i, p in _passos():
        if p["rota"] in restritas:
            for cargo in t.get("obrigatorios", c.CARGOS_OBRIGATORIOS):
                assert cargo in restritas[p["rota"]], f"{t['titulo']} / {a['titulo']}, passo {i}"


@needs_web
def test_toda_ancora_do_tour_existe_no_front():
    ancoras = _ancoras_do_front()
    faltando = []
    for t, a, i, p in _passos():
        for id_ in ([p["alvo"]] if p["alvo"] else []) + p.get("clicar", []):
            if id_ not in ancoras:
                faltando.append(f"{t['titulo']} / {a['titulo']}, passo {i}: {id_}")
    assert faltando == []


@needs_web
def test_todo_abridor_existe_no_front():
    assert h.ABRIDORES <= _ancoras_do_front()


def test_textos_curtos_para_o_balao():
    for t, a, i, p in _passos():
        assert len(p["titulo"]) <= 80 and len(p["texto"]) <= 600


def test_ids_das_aulas_nao_colidem_com_o_resto():
    ids = [x["id"] for x in c.TRILHAS] + [a["id"] for x in c.TRILHAS for a in x["aulas"]]
    assert len(ids) == len(set(ids))


def test_passos_de_outras_trilhas_entram_na_conferencia():
    """Os roteiros (Método 02 e 03) também têm tour: o teste das âncoras os cobre."""
    from scripts import uc_conteudo_roteiros as r
    com_tour = {t["titulo"] for t, _a, _i, _p in _passos()}
    assert {r.METODO_02["titulo"], r.METODO_03["titulo"]} <= com_tour


def test_toda_trilha_hipo_termina_no_desempenho_da_carreira():
    """Entrega 038: a Universidade virou aba da Carreira; cada função aprende a ler o Desempenho."""
    assert {"/carreira", "/carreira/desempenho"} <= set(regras.ROTAS_TOUR)
    for t in h.TRILHAS_HIPO:
        ultima = t["aulas"][-1]
        assert ultima["titulo"] == "Carreira: o seu Desempenho", t["titulo"]
        rotas = {p["rota"] for p in ultima["tour"]}
        assert "/carreira/desempenho" in rotas
        assert "Monitor › RPeR › Metas" in ultima["conteudo_md"]
        # A primeira aula apresenta o item novo do menu.
        assert any(p["alvo"] == "nav-carreira" for p in t["aulas"][0]["tour"]), t["titulo"]


def test_nenhum_texto_manda_procurar_a_universidade_no_menu():
    for t in h.TRILHAS_HIPO:
        for a in t["aulas"]:
            assert "**Relatórios**, **Universidade**" not in a["conteudo_md"], a["titulo"]
            for p in a["tour"]:
                assert p["rota"] != "/uc", f"{t['titulo']} / {a['titulo']}"
