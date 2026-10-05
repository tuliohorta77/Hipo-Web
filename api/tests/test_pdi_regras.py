"""
HIPO — Carreira · PDI: regras puras (services/pdi.py).
"""
from datetime import date

import pytest

from services import pdi as r

HOJE = date(2026, 10, 15)


def _linha(chave, ating, principal=False, rotulo=None):
    return {"chave": chave, "rotulo": rotulo or chave.upper(), "atingimento": ating,
            "principal": principal, "realizado_txt": "1", "meta_hoje_txt": "2", "meta_mes_txt": "4"}


def test_desempenho_sugere_os_tres_piores_abaixo_de_70():
    linhas = [_linha("a", 0.9), _linha("b", 0.2), _linha("c", 0.5), _linha("d", 0.69),
              _linha("e", 0.1), _linha("f", None)]
    s = r.sugestoes_do_desempenho("SDR", linhas, 2026, 10, True, HOJE)
    assert [x.chave for x in s] == ["desempenho:2026-10:e", "desempenho:2026-10:b", "desempenho:2026-10:c"]
    assert all(x.origem == "desempenho" and x.prazo == date(2026, 10, 31) for x in s)


def test_desempenho_principal_desempata():
    s = r.sugestoes_do_desempenho("EV", [_linha("x", 0.3), _linha("nmrr", 0.3, principal=True)], 2026, 10, True, HOJE)
    assert s[0].chave.endswith(":nmrr")


def test_desempenho_diz_onde_agir():
    s = r.sugestoes_do_desempenho("SDR", [_linha("agendamentos", 0.4, rotulo="AGENDAMENTOS")], 2026, 10, True, HOJE)
    assert "40%" in s[0].objetivo and "Agenda" in s[0].o_que_fazer and "meta de hoje" in s[0].o_que_fazer


def _trilha(cod, dias, quiz=None):
    return {"id": "t1", "titulo": "02 · Roteiro do SDR", "situacao": {"codigo": cod, "dias_restantes": dias},
            "aulas_concluidas": 3, "aulas_total": 7, "quiz": quiz}


def test_uc_sugere_trilha_atrasada_ou_vencendo():
    assert r.sugestoes_da_uc([_trilha("em_dia", 20)], [], HOJE) == []
    s = r.sugestoes_da_uc([_trilha("atrasada", -4)], [], HOJE)
    assert s[0].chave == "uc:trilha:t1" and s[0].trilha_id == "t1"
    assert "atrasada há 4 dia(s)" in s[0].o_que_fazer and s[0].prazo == date(2026, 10, 22)
    s = r.sugestoes_da_uc([_trilha("vence_logo", 2, {"liberado": True, "aprovado": False})], [], HOJE)
    assert "vence em 2 dia(s)" in s[0].o_que_fazer and "falta o quiz final" in s[0].o_que_fazer


def test_uc_sugere_quiz_reprovado():
    s = r.sugestoes_da_uc([], [{"trilha_id": "t9", "titulo": "01 · HIPO - SDR", "tentativas": 3,
                                "aulas_rever": ["Aula 2. Tarefas"]}], HOJE)
    assert s[0].chave == "uc:quiz:t9" and "3 tentativas" in s[0].o_que_fazer and "Aula 2. Tarefas" in s[0].o_que_fazer


def test_filtra_o_que_ja_virou_acao():
    s = r.sugestoes_da_uc([_trilha("atrasada", -1)], [], HOJE)
    assert r.filtrar_sugestoes(s, {"uc:trilha:t1"}) == []


def test_origem_pela_chave():
    assert r.origem_da_chave(None) == "gestao"
    assert r.origem_da_chave("uc:trilha:x") == "uc"
    assert r.origem_da_chave("desempenho:2026-10:nmrr") == "desempenho"
    with pytest.raises(r.AcaoInvalida):
        r.origem_da_chave("outra:coisa")


def test_validacoes():
    assert r.validar_texto("  Subir   o NMRR ", "objetivo", 200) == "Subir o NMRR"
    with pytest.raises(r.AcaoInvalida, match="objetivo"):
        r.validar_texto("", "objetivo", 200)
    with pytest.raises(r.AcaoInvalida, match="passado"):
        r.validar_prazo(date(2026, 10, 1), HOJE, novo=True)
    assert r.validar_prazo(date(2026, 10, 1), HOJE, novo=False) == date(2026, 10, 1)
    with pytest.raises(r.AcaoInvalida, match="um ano"):
        r.validar_prazo(date(2028, 1, 1), HOJE, novo=True)


def test_situacao_e_proxima():
    assert r.situacao("aberta", date(2026, 10, 10), HOJE)["codigo"] == "atrasada"
    assert r.situacao("aberta", date(2026, 10, 17), HOJE)["codigo"] == "vence_logo"
    assert r.situacao("aberta", date(2026, 11, 1), HOJE)["codigo"] == "em_dia"
    assert r.situacao("concluida", date(2026, 10, 1), HOJE)["rotulo"] == "Feita"
    acoes = [
        {"status": "concluida", "prazo": date(2026, 10, 1), "criado_em": 1},
        {"status": "aberta", "prazo": date(2026, 10, 20), "criado_em": 2},
        {"status": "aberta", "prazo": date(2026, 10, 18), "criado_em": 3},
    ]
    assert r.proxima_acao(acoes)["criado_em"] == 3
    assert r.proxima_acao([]) is None


def test_fim_do_mes():
    assert r.fim_do_mes(date(2026, 2, 10)) == date(2026, 2, 28)
    assert r.fim_do_mes(date(2026, 12, 31)) == date(2026, 12, 31)
