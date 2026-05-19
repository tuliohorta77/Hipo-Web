"""
Testes do parser da planilha Carteira.

Valida:
  - Filtro Tipo Cnae = 'CNAE Contábil'
  - Agrupamento de colaboradores únicos
  - Tratamento de colunas obrigatórias ausentes
"""
import os
import tempfile

import pandas as pd
import pytest

from parsers.carteira import parse_carteira_arquivo


# ── Helper ───────────────────────────────────────────────────────

def _build_xlsx(rows: list[dict], colunas: list[str] | None = None) -> str:
    """Cria um XLSX no formato Carteira (header na linha 1) e devolve o caminho."""
    if colunas is None:
        colunas = [
            "ID Grupo de Empresas", "Grupo", "CNPJ Contador", "Contabilidade",
            "Bairro", "Cidade/UF", "Parceria", "Data Parceria", "Tipo Cnae",
            "Colaborador", "Função", "Porte Faturamento", "Score RFM",
            "Apps Ativos", "MRR Ativo", "Leads no Mês", "Status RF",
        ]
    df = pd.DataFrame([{c: r.get(c) for c in colunas} for r in rows])
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    df.to_excel(path, index=False, engine="openpyxl")
    return path


# ── Filtro CNAE Contábil ─────────────────────────────────────────

class TestFiltroCnaeContabil:
    def test_aceita_somente_cnae_contabil(self):
        path = _build_xlsx([
            {"ID Grupo de Empresas": "G1", "Tipo Cnae": "CNAE Contábil", "Colaborador": "Ana"},
            {"ID Grupo de Empresas": "G2", "Tipo Cnae": "CNAE Consultor", "Colaborador": "Bob"},
            {"ID Grupo de Empresas": "G3", "Tipo Cnae": "CNAE Outros",   "Colaborador": "Cad"},
        ])
        try:
            r = parse_carteira_arquivo(path)
        finally:
            os.unlink(path)

        assert r["total_linhas"] == 3
        assert r["total_validos"] == 1
        assert r["linhas"][0]["id_grupo"] == "G1"
        assert r["linhas"][0]["colaborador_nome"] == "Ana"

    def test_normaliza_acentos_no_filtro(self):
        path = _build_xlsx([
            {"ID Grupo de Empresas": "G1", "Tipo Cnae": "CNAE CONTÁBIL", "Colaborador": "Ana"},
            {"ID Grupo de Empresas": "G2", "Tipo Cnae": "cnae contabil",  "Colaborador": "Bob"},
        ])
        try:
            r = parse_carteira_arquivo(path)
        finally:
            os.unlink(path)

        assert r["total_validos"] == 2


# ── Colaboradores ────────────────────────────────────────────────

class TestColaboradores:
    def test_extrai_lista_unica_ordenada(self):
        path = _build_xlsx([
            {"ID Grupo de Empresas": "G1", "Tipo Cnae": "CNAE Contábil",
             "Colaborador": "Beatriz", "Função": "Executivo de Contas - FR"},
            {"ID Grupo de Empresas": "G2", "Tipo Cnae": "CNAE Contábil",
             "Colaborador": "ana",     "Função": "Executivo de Contas I - FR"},
            {"ID Grupo de Empresas": "G3", "Tipo Cnae": "CNAE Contábil",
             "Colaborador": "Beatriz", "Função": "Executivo de Contas - FR"},
            {"ID Grupo de Empresas": "G4", "Tipo Cnae": "CNAE Contábil",
             "Colaborador": None,      "Função": None},
        ])
        try:
            r = parse_carteira_arquivo(path)
        finally:
            os.unlink(path)

        nomes = [c["nome"] for c in r["colaboradores"]]
        # Únicos + ordenados case-insensitive
        assert nomes == ["ana", "Beatriz"]
        assert r["colaboradores"][0]["funcao_origem"] == "Executivo de Contas I - FR"


# ── Schema ───────────────────────────────────────────────────────

class TestSchemaObrigatorio:
    def test_falha_quando_id_grupo_ausente(self):
        path = _build_xlsx(
            [{"Tipo Cnae": "CNAE Contábil", "Colaborador": "Ana"}],
            colunas=["Tipo Cnae", "Colaborador"],
        )
        try:
            r = parse_carteira_arquivo(path)
        finally:
            os.unlink(path)

        assert r["erros"]
        assert "id_grupo" in r["erros"][0]
        assert r["total_validos"] == 0

    def test_falha_quando_tipo_cnae_ausente(self):
        path = _build_xlsx(
            [{"ID Grupo de Empresas": "G1", "Colaborador": "Ana"}],
            colunas=["ID Grupo de Empresas", "Colaborador"],
        )
        try:
            r = parse_carteira_arquivo(path)
        finally:
            os.unlink(path)

        assert r["erros"]
        assert "tipo_cnae" in r["erros"][0]

    def test_arquivo_invalido(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"this is not an xlsx")
            path = f.name
        try:
            r = parse_carteira_arquivo(path)
        finally:
            os.unlink(path)
        assert r["erros"]
        assert r["total_validos"] == 0


# ── Coerção de tipos ─────────────────────────────────────────────

class TestCoercao:
    def test_leads_apps_e_mrr_sao_numericos(self):
        path = _build_xlsx([
            {"ID Grupo de Empresas": "G1", "Tipo Cnae": "CNAE Contábil",
             "Colaborador": "Ana", "Leads no Mês": "5", "Apps Ativos": 12,
             "MRR Ativo": "1.234,56"},
        ])
        try:
            r = parse_carteira_arquivo(path)
        finally:
            os.unlink(path)

        ln = r["linhas"][0]
        assert ln["leads_no_mes"] == 5
        assert ln["apps_ativos"] == 12
        assert ln["mrr_ativo"] == 1234.56

    def test_linha_sem_id_grupo_eh_descartada(self):
        # Construímos manualmente: a coluna existe, mas o valor é None
        df = pd.DataFrame([
            {"ID Grupo de Empresas": None, "Tipo Cnae": "CNAE Contábil", "Colaborador": "Ana"},
            {"ID Grupo de Empresas": "G2", "Tipo Cnae": "CNAE Contábil", "Colaborador": "Bob"},
        ])
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            df.to_excel(path, index=False, engine="openpyxl")
            r = parse_carteira_arquivo(path)
        finally:
            os.unlink(path)

        assert r["total_validos"] == 1
        assert r["linhas"][0]["id_grupo"] == "G2"
        assert any("sem ID Grupo" in e for e in r["erros"])
