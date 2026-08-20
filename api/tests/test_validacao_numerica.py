"""
Testes da guarda contra numero inventado.

Logica pura: sem `db_conn`, sem AWS, sem chamada a Anthropic. Roda no Windows
sem Postgres.
"""

from __future__ import annotations

from datetime import date

import pytest

from services.validacao_numerica import (
    canonizar,
    numeros_invalidos,
    numeros_permitidos,
)

METRICAS = {
    "dia": date(2026, 8, 19),
    "requisicoes": 412,
    "erros_5xx": 3,
    "usuarios_ativos": 2,
    "por_usuario": [
        {"nome": "Aline Martins", "acoes": 37},
        {"nome": "Tulio Horta", "acoes": 5},
    ],
    "tarefas_atrasadas": 12,
}


def test_numeros_das_metricas_sao_permitidos():
    p = numeros_permitidos(METRICAS)
    assert {"412", "3", "2", "37", "5", "12"} <= p


def test_data_libera_dia_mes_e_ano():
    p = numeros_permitidos(METRICAS)
    assert {"19", "8", "08", "2026"} <= p


def test_numero_dentro_da_chave_conta():
    # A IA cita rotulos como 'erros_5xx'. O 5 vem do nome da metrica, nao do ar.
    assert "5" in numeros_permitidos({"erros_5xx": 0})


def test_narrativa_fiel_passa():
    texto = (
        "Foram 412 requisicoes e 3 erros. Aline Martins concentrou 37 acoes; "
        "as 12 tarefas atrasadas seguem sem dono."
    )
    assert numeros_invalidos(texto, numeros_permitidos(METRICAS)) == []


def test_percentual_calculado_pela_ia_e_barrado():
    # O caso que motiva o modulo: numero plausivel, impossivel de rastrear.
    texto = "As 412 requisicoes representam queda de 30% contra ontem."
    assert numeros_invalidos(texto, numeros_permitidos(METRICAS)) == ["30"]


def test_soma_inventada_e_barrada():
    texto = "Aline e Tulio somaram 42 acoes."
    assert numeros_invalidos(texto, numeros_permitidos(METRICAS)) == ["42"]


def test_token_invalido_nao_repete_no_relato():
    texto = "30% hoje, 30% ontem e 55% na semana."
    assert numeros_invalidos(texto, numeros_permitidos(METRICAS)) == ["30", "55"]


def test_texto_sem_numero_passa():
    texto = "Dia parado: quase ninguem entrou no sistema."
    assert numeros_invalidos(texto, numeros_permitidos(METRICAS)) == []


@pytest.mark.parametrize("escrito, canonico", [
    ("1.234", "1234"),
    ("1.234,50", "1234.5"),
    ("0", "0"),
    ("412", "412"),
])
def test_canonizacao_entende_notacao_brasileira(escrito, canonico):
    assert canonizar(escrito) == canonico


def test_separador_de_milhar_nao_vira_falso_positivo():
    # A metrica guarda 1234; a IA escreve 'R$ 1.234'. E o mesmo numero.
    p = numeros_permitidos({"faturamento": 1234})
    assert numeros_invalidos("Somaram R$ 1.234 no dia.", p) == []


def test_metricas_vazias_barram_qualquer_numero():
    # Dia sem dado nenhum: a IA nao tem de onde tirar numero.
    assert numeros_invalidos("Houve 7 acessos.", numeros_permitidos({})) == ["7"]
