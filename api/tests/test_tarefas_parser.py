"""
Testes do parser de Tarefas.

Valida:
  - Mapeamento de 'Situação da Tarefa' → enum interno.
  - Regra data_efetiva = Data Agendamento ?: Data Criação.
  - Schema obrigatório.
"""
import os
import tempfile
from datetime import datetime

import pandas as pd

from parsers.tarefas import parse_tarefas_arquivo, _mapear_situacao


def _build_xlsx(rows: list[dict], colunas: list[str] | None = None) -> str:
    if colunas is None:
        colunas = [
            "Tarefa_ID", "Data Criação", "Data Agendamento", "CNPJ Contador",
            "Contabilidade", "Situação da Tarefa", "Status da Tarefa",
            "Tarefa Canal", "Tipo da Tarefa", "Resultado", "Executivo de Contas",
        ]
    df = pd.DataFrame([{c: r.get(c) for c in colunas} for r in rows])
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    df.to_excel(path, index=False, engine="openpyxl")
    return path


class TestMapeamentoSituacao:
    def test_em_dia(self):
        assert _mapear_situacao("Tarefa em dia") == "EM_DIA"

    def test_futura(self):
        assert _mapear_situacao("Tarefa futura") == "FUTURA"

    def test_atrasada(self):
        assert _mapear_situacao("Tarefa atrasada") == "ATRASADA"

    def test_acentuacao_e_case(self):
        assert _mapear_situacao("TAREFA ATRASADA") == "ATRASADA"
        assert _mapear_situacao("Situação Desconhecida") == "DESCONHECIDA"

    def test_none(self):
        assert _mapear_situacao(None) == "DESCONHECIDA"


class TestDataEfetiva:
    def test_usa_agendamento_quando_existe(self):
        path = _build_xlsx([{
            "Tarefa_ID": "T1",
            "Data Criação": datetime(2026, 5, 1, 10, 0),
            "Data Agendamento": datetime(2026, 5, 10, 14, 0),
            "Executivo de Contas": "Ana",
            "Situação da Tarefa": "Tarefa em dia",
        }])
        try:
            r = parse_tarefas_arquivo(path)
        finally:
            os.unlink(path)

        assert r["total_validos"] == 1
        assert r["linhas"][0]["data_efetiva"].date() == datetime(2026, 5, 10).date()

    def test_fallback_para_criacao_quando_sem_agendamento(self):
        path = _build_xlsx([{
            "Tarefa_ID": "T1",
            "Data Criação": datetime(2026, 5, 1, 10, 0),
            "Data Agendamento": None,
            "Executivo de Contas": "Ana",
            "Situação da Tarefa": "Tarefa em dia",
        }])
        try:
            r = parse_tarefas_arquivo(path)
        finally:
            os.unlink(path)

        assert r["linhas"][0]["data_efetiva"].date() == datetime(2026, 5, 1).date()

    def test_sem_nenhuma_data(self):
        path = _build_xlsx([{
            "Tarefa_ID": "T1",
            "Executivo de Contas": "Ana",
            "Situação da Tarefa": "Tarefa em dia",
        }])
        try:
            r = parse_tarefas_arquivo(path)
        finally:
            os.unlink(path)

        assert r["linhas"][0]["data_efetiva"] is None


class TestSchema:
    def test_falha_sem_executivo(self):
        path = _build_xlsx(
            [{"Tarefa_ID": "T1", "Situação da Tarefa": "Tarefa em dia"}],
            colunas=["Tarefa_ID", "Situação da Tarefa"],
        )
        try:
            r = parse_tarefas_arquivo(path)
        finally:
            os.unlink(path)
        assert r["erros"]
        assert "executivo_nome" in r["erros"][0]

    def test_linha_vazia_eh_descartada(self):
        path = _build_xlsx([
            {"Tarefa_ID": "T1", "Executivo de Contas": "Ana", "Situação da Tarefa": "Tarefa em dia"},
            {"Tarefa_ID": None, "Executivo de Contas": None, "Situação da Tarefa": None,
             "CNPJ Contador": None},
        ])
        try:
            r = parse_tarefas_arquivo(path)
        finally:
            os.unlink(path)
        assert r["total_validos"] == 1


class TestCanalReuniao:
    def test_canal_preservado_no_parser(self):
        """O parser não filtra Reunião — apenas preserva o canal para o agregador."""
        path = _build_xlsx([
            {"Tarefa_ID": "T1", "Executivo de Contas": "Ana",
             "Situação da Tarefa": "Tarefa em dia", "Tarefa Canal": "Reunião"},
            {"Tarefa_ID": "T2", "Executivo de Contas": "Ana",
             "Situação da Tarefa": "Tarefa em dia", "Tarefa Canal": "WhatsApp"},
        ])
        try:
            r = parse_tarefas_arquivo(path)
        finally:
            os.unlink(path)

        canais = {l["tarefa_canal"] for l in r["linhas"]}
        assert canais == {"Reunião", "WhatsApp"}
