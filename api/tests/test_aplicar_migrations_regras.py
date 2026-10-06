"""
Regras puras do scripts/aplicar_migrations.py -- sem banco.

O caminho com banco (do zero ate a ultima, e a segunda passada sem nada a
aplicar) e testado pelo proprio CI, no passo que sobe o schema de teste.
"""
from pathlib import Path

import pytest

from scripts import aplicar_migrations as am


def _pasta(tmp_path: Path, arquivos: dict) -> Path:
    for nome, texto in arquivos.items():
        (tmp_path / nome).write_bytes(texto if isinstance(texto, bytes) else texto.encode("utf-8"))
    return tmp_path


def _hash(texto: str) -> str:
    return am.sha256_de(texto)


# ---------------------------------------------------------------------------
# Nomes e ordem
# ---------------------------------------------------------------------------

def test_lista_em_ordem_numerica(tmp_path):
    p = _pasta(tmp_path, {"010_b.sql": "", "002_a.sql": "", "100_c.sql": ""})
    assert [n for n, _, _ in am.listar_migrations(p)] == [2, 10, 100]


def test_numero_repetido_trava(tmp_path):
    p = _pasta(tmp_path, {"029_a.sql": "", "029_b.sql": ""})
    with pytest.raises(am.Trava, match="029 repetido"):
        am.listar_migrations(p)


@pytest.mark.parametrize("nome", ["29_a.sql", "030-a.sql", "030_A.sql", "030_a b.sql"])
def test_nome_fora_do_padrao_trava(tmp_path, nome):
    p = _pasta(tmp_path, {nome: ""})
    with pytest.raises(am.Trava, match="fora do padrao"):
        am.listar_migrations(p)


def test_pasta_inexistente_trava(tmp_path):
    with pytest.raises(am.Trava, match="nao existe"):
        am.listar_migrations(tmp_path / "nao-tem")


def test_repositorio_real_passa_nas_travas():
    # O que esta commitado tem que ser aplicavel do zero: nomes, numeros
    # unicos e regras novas da LIMITE_LEGADO+1 em diante.
    arquivos = am.listar_migrations(am.PASTA_PADRAO)
    assert arquivos[0][1] == "000_base_pre_crm.sql"
    pendentes, _ = am.planejar(arquivos, {})
    assert len(pendentes) == len(arquivos)


# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------

def test_hash_ignora_bom_e_crlf(tmp_path):
    lf = _pasta(tmp_path, {"001_a.sql": b"SELECT 1;\nSELECT 2;\n"})
    crlf = tmp_path / "crlf"
    crlf.mkdir()
    _pasta(crlf, {"001_a.sql": b"\xef\xbb\xbfSELECT 1;\r\nSELECT 2;\r\n"})
    assert am.texto_normalizado(lf / "001_a.sql") == am.texto_normalizado(crlf / "001_a.sql")


def test_aplicada_com_mesmo_hash_nao_e_pendente(tmp_path):
    p = _pasta(tmp_path, {"030_a.sql": "SELECT 1;\n", "031_b.sql": "SELECT 2;\n"})
    pendentes, _ = am.planejar(am.listar_migrations(p), {"030_a.sql": _hash("SELECT 1;\n")})
    assert pendentes == [(31, "031_b.sql")]


def test_aplicada_editada_trava(tmp_path):
    p = _pasta(tmp_path, {"030_a.sql": "SELECT 1; -- editado\n"})
    with pytest.raises(am.Trava, match="mudou"):
        am.planejar(am.listar_migrations(p), {"030_a.sql": _hash("SELECT 1;\n")})


def test_aplicada_sumida_trava(tmp_path):
    p = _pasta(tmp_path, {"031_b.sql": "SELECT 2;\n"})
    with pytest.raises(am.Trava, match="ausentes do repositorio: 030_a.sql"):
        am.planejar(am.listar_migrations(p), {"030_a.sql": "x"})


def test_pendente_atras_da_ultima_aplicada_trava(tmp_path):
    p = _pasta(tmp_path, {"030_a.sql": "SELECT 1;\n", "031_b.sql": "SELECT 2;\n"})
    with pytest.raises(am.Trava, match="031 ja foi aplicada"):
        am.planejar(am.listar_migrations(p), {"031_b.sql": _hash("SELECT 2;\n")})


# ---------------------------------------------------------------------------
# Regras das migrations novas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "BEGIN;\nSELECT 1;\nCOMMIT;\n",
    "SELECT 1;\n  commit;\n",
    "START TRANSACTION;\nSELECT 1;\n",
    "SELECT 1;\nROLLBACK;\n",
])
def test_controle_de_transacao_trava_na_nova(sql):
    with pytest.raises(am.Trava, match="BEGIN/COMMIT"):
        am.conferir_regras_novas(am.LIMITE_LEGADO + 1, "030_a.sql", sql)


def test_controle_de_transacao_tolerado_no_legado():
    am.conferir_regras_novas(am.LIMITE_LEGADO, "029_a.sql", "BEGIN;\nSELECT 1;\nCOMMIT;\n")


def test_begin_de_bloco_do_nao_e_controle_de_transacao():
    sql = "DO $$\nBEGIN\n  RAISE NOTICE 'x';\nEND $$;\n"
    am.conferir_regras_novas(am.LIMITE_LEGADO + 1, "030_a.sql", sql)


def test_palavra_em_comentario_nao_conta():
    sql = "-- COMMIT;\n/* DROP TABLE contas; */\nSELECT 1;\n"
    am.conferir_regras_novas(am.LIMITE_LEGADO + 1, "030_a.sql", sql)


@pytest.mark.parametrize("sql", [
    "DROP TABLE contas;",
    "ALTER TABLE contas DROP COLUMN nome;",
    "TRUNCATE tarefas;",
    "DELETE FROM tarefas WHERE true;",
    "DROP SCHEMA x CASCADE;",
])
def test_destrutiva_sem_marcador_trava(sql):
    with pytest.raises(am.Trava, match="destrutiva"):
        am.conferir_regras_novas(am.LIMITE_LEGADO + 1, "030_a.sql", sql)


def test_destrutiva_com_marcador_passa():
    sql = "-- hipo:destrutiva-com-export hipo-backup-030-20261006.zip\nDROP TABLE contas;\n"
    am.conferir_regras_novas(am.LIMITE_LEGADO + 1, "030_a.sql", sql)


def test_marcador_sem_zip_nao_vale():
    sql = "-- hipo:destrutiva-com-export depois\nDROP TABLE contas;\n"
    with pytest.raises(am.Trava, match="destrutiva"):
        am.conferir_regras_novas(am.LIMITE_LEGADO + 1, "030_a.sql", sql)


def test_drop_index_e_constraint_nao_sao_destrutivas():
    sql = "DROP INDEX IF EXISTS idx_x;\nALTER TABLE t DROP CONSTRAINT ck_x;\nDROP VIEW IF EXISTS vw;\n"
    am.conferir_regras_novas(am.LIMITE_LEGADO + 1, "030_a.sql", sql)


# ---------------------------------------------------------------------------
# .env e mascara
# ---------------------------------------------------------------------------

def test_url_do_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text('JWT_SECRET=x\nDATABASE_URL="postgresql://u:s&?*@h:5432/db"\n', encoding="utf-8")
    assert am.url_do_env_file(str(env)) == "postgresql://u:s&?*@h:5432/db"


def test_env_file_sem_url_sai(tmp_path):
    env = tmp_path / ".env"
    env.write_text("JWT_SECRET=x\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        am.url_do_env_file(str(env))


def test_mascara_esconde_senha():
    assert am.mascarar("postgresql://hipo:segredo@hipo-db:5432/hipo") == "postgresql://hipo:****@hipo-db:5432/hipo"


def test_sem_database_url_sai_com_1(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert am.main([]) == 1


def test_corpo_de_funcao_com_begin_end_nao_e_controle_de_transacao():
    sql = (
        "CREATE OR REPLACE FUNCTION f() RETURNS trigger AS $fn$\n"
        "BEGIN\n  NEW.x := 1;\n  RETURN NEW;\nEND;\n$fn$ LANGUAGE plpgsql;\n"
    )
    am.conferir_regras_novas(am.LIMITE_LEGADO + 1, "030_a.sql", sql)
