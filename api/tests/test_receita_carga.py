"""
HIPO — Carga da base de Dados Abertos do CNPJ (022).

Duas metades:

  * PARSER (services/receita_carga.py): sem banco. Prende as posições do
    layout da Receita com linhas de exemplo — se a Receita mudar o layout, é
    aqui que quebra primeiro, e não na tela do SDR.

  * CARGA (scripts/carregar_base_receita.py): ZIPs fictícios, no formato
    real (Latin-1, `;`, aspas, sem cabeçalho), carregados no banco de teste.
    Prova o filtro (ativa, UF, sem MEI), o JOIN com Empresas e Simples, a
    troca da tabela e — o que mais importa — que os índices da tabela
    trocada têm os MESMOS nomes da migration 022. Se divergirem, a próxima
    migration que mexer neles quebra em produção.
"""
import re
import zipfile
from argparse import Namespace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import carregar_base_receita as carga
from services import receita_carga as rc

UFS = frozenset({"SP"})


def _estab(basico="11222333", ordem="0001", dv="81", situacao="02", uf="SP",
           cnae="2511000", sec="2512800,3321000", fantasia="ACME",
           municipio="6477", email="CONTATO@ACME.COM.BR", matriz="1"):
    campos = [""] * 30
    campos[rc.E_BASICO] = basico
    campos[rc.E_ORDEM] = ordem
    campos[rc.E_DV] = dv
    campos[rc.E_MATRIZ_FILIAL] = matriz
    campos[rc.E_FANTASIA] = fantasia
    campos[rc.E_SITUACAO] = situacao
    campos[rc.E_INICIO_ATIVIDADE] = "20150312"
    campos[rc.E_CNAE_PRINCIPAL] = cnae
    campos[rc.E_CNAES_SECUNDARIOS] = sec
    campos[rc.E_TIPO_LOGRADOURO] = "RUA"
    campos[rc.E_LOGRADOURO] = "DAS   FLORES"
    campos[rc.E_NUMERO] = "100"
    campos[rc.E_BAIRRO] = "CENTRO"
    campos[rc.E_CEP] = "07010000"
    campos[rc.E_UF] = uf
    campos[rc.E_MUNICIPIO] = municipio
    campos[rc.E_DDD_1] = "11"
    campos[rc.E_TELEFONE_1] = "23456789"
    campos[rc.E_EMAIL] = email
    return campos


# ── Parser ───────────────────────────────────────────────────────────────────

class TestEstabelecimento:
    def test_linha_completa(self):
        e = rc.linha_estabelecimento(_estab(), UFS)
        assert e.cnpj == "11222333000181"
        assert e.matriz is True
        assert e.data_abertura == date(2015, 3, 12)
        assert e.cnaes_secundarios == ("2512800", "3321000")
        assert e.logradouro == "RUA DAS FLORES"
        assert e.telefone == "1123456789"
        assert e.email == "contato@acme.com.br"
        assert e.municipio_codigo == "6477"

    def test_inativa_fica_de_fora(self):
        assert rc.linha_estabelecimento(_estab(situacao="08"), UFS) is None

    def test_situacao_sem_zero_a_esquerda(self):
        assert rc.linha_estabelecimento(_estab(situacao="2"), UFS) is not None

    def test_outra_uf_fica_de_fora(self):
        assert rc.linha_estabelecimento(_estab(uf="RJ"), UFS) is None

    def test_cnae_sem_zero_a_esquerda(self):
        e = rc.linha_estabelecimento(_estab(cnae="111301", sec="111302"), UFS)
        assert e.cnae_principal == "0111301"
        assert e.cnaes_secundarios == ("0111302",)

    def test_secundario_igual_ao_principal_e_repetido_somem(self):
        e = rc.linha_estabelecimento(_estab(sec="2511000,3321000,3321000"), UFS)
        assert e.cnaes_secundarios == ("3321000",)

    def test_cnae_ilegivel_descarta_a_linha(self):
        assert rc.linha_estabelecimento(_estab(cnae=""), UFS) is None

    def test_linha_curta_descarta(self):
        assert rc.linha_estabelecimento(["1", "2"], UFS) is None

    def test_email_sem_arroba_vira_vazio(self):
        assert rc.linha_estabelecimento(_estab(email="nao tem"), UFS).email is None

    def test_filial(self):
        assert rc.linha_estabelecimento(_estab(matriz="2"), UFS).matriz is False


class TestEmpresaESimples:
    def test_empresa(self):
        r = rc.linha_empresa(["11222333", "ACME   LTDA", "2062", "49", "150000,00", "05", ""])
        assert r == ("11222333", "ACME LTDA", "2062", Decimal("150000.00"), "05")

    def test_empresa_sem_razao_descarta(self):
        assert rc.linha_empresa(["11222333", "", "2062", "49", "1,00", "05", ""]) is None

    def test_capital_absurdo_vira_vazio(self):
        r = rc.linha_empresa(["11222333", "X", "2062", "49", "99999999999999999,00", "05", ""])
        assert r[3] is None

    def test_simples(self):
        assert rc.linha_simples(["11222333", "S", "20100101", "0", "N", "0", "0"]) == (
            "11222333", True, False,
        )
        assert rc.linha_simples(["11222333", "N", "0", "0", "S", "0", "0"])[2] is True

    def test_ufs(self):
        assert rc.ufs_validas("sp, rj") == {"SP", "RJ"}
        with pytest.raises(ValueError):
            rc.ufs_validas("")
        with pytest.raises(ValueError):
            rc.ufs_validas("SPX")


def test_indices_do_script_batem_com_a_migration():
    sql = (Path(__file__).resolve().parent.parent / "migrations" / "022_base_receita.sql").read_text(
        encoding="utf-8"
    )
    na_migration = set(re.findall(
        r"CREATE INDEX IF NOT EXISTS (\w+)\s+ON receita_estabelecimentos", sql
    ))
    assert na_migration == {nome for nome, _ in carga.INDICES}


# ── Carga de ponta a ponta ───────────────────────────────────────────────────

def _zip(pasta: Path, nome: str, linhas: list[list[str]], encoding: str = "latin-1") -> None:
    corpo = "\n".join(";".join(f'"{c}"' for c in linha) for linha in linhas) + "\n"
    with zipfile.ZipFile(pasta / nome, "w") as zf:
        # "utf-16" no Python grava o BOM sozinho -- o formato visto na
        # Receita depois de fev/2026.
        zf.writestr("K3241.K03200Y0.D60913.ARQUIVO", corpo.encode(encoding))


@pytest.fixture
def zips(tmp_path):
    _zip(tmp_path, "Estabelecimentos0.zip", [
        _estab(),                                                     # entra
        _estab(basico="34028316", dv="03", fantasia="JOÃO MEI"),     # MEI: sai
        _estab(basico="11444777", dv="35", situacao="08"),           # baixada: sai
    ])
    _zip(tmp_path, "Estabelecimentos1.zip", encoding="utf-16", linhas=[
        _estab(basico="19131243", dv="45", uf="RJ"),                 # outra UF: sai
        _estab(basico="45997418", dv="71", cnae="4120400", sec="",
               fantasia="", municipio="7107"),                       # entra
    ])
    _zip(tmp_path, "Empresas0.zip", [
        ["11222333", "METALÚRGICA ACME LTDA", "2062", "49", "150000,00", "05", ""],
        ["34028316", "JOAO DA SILVA", "2135", "50", "1000,00", "01", ""],
        ["45997418", "CONSTRUTORA BETA SA", "2054", "10", "5000000,00", "05", ""],
        ["99999999", "FORA DA FATIA", "2062", "49", "1,00", "01", ""],
    ])
    _zip(tmp_path, "Simples.zip", [
        ["11222333", "S", "20100101", "0", "N", "0", "0"],
        ["34028316", "S", "20100101", "0", "S", "20100101", "0"],
    ])
    _zip(tmp_path, "Municipios.zip", [["6477", "GUARULHOS"], ["7107", "SAO PAULO"], ["6001", "RIO DE JANEIRO"]])
    _zip(tmp_path, "Cnaes.zip", [["2511000", "Fabricação de estruturas metálicas"],
                                 ["4120400", "Construção de edifícios"]])
    return tmp_path


def _args(pasta, **kw):
    base = dict(ufs="SP", referencia="2026-09", pasta=str(pasta), baixar=None,
                apagar_depois=False, manter_mei=False, simular=False, limite=0)
    base.update(kw)
    return Namespace(**base)


class TestEncoding:
    def test_bom(self):
        assert carga.encoding_pelo_bom(b"\xff\xfe1\x00") == "utf-16"
        assert carga.encoding_pelo_bom(b"\xef\xbb\xbf") == "utf-8-sig"
        assert carga.encoding_pelo_bom(b'"112') == "latin-1"

    @pytest.mark.parametrize("encoding", ["latin-1", "utf-16", "utf-8-sig"])
    def test_le_o_mesmo_conteudo_em_qualquer_encoding(self, tmp_path, encoding):
        _zip(tmp_path, "Empresas0.zip",
             [["11222333", "METALÚRGICA AÇO LTDA", "2062", "49", "1,00", "05", ""]],
             encoding)
        linhas = list(carga.ler_zip(tmp_path / "Empresas0.zip"))
        assert linhas == [["11222333", "METALÚRGICA AÇO LTDA", "2062", "49", "1,00", "05", ""]]


class TestCarga:
    async def test_carrega_filtra_e_troca(self, db_conn, zips):
        assert await carga.principal(_args(zips)) == 0

        rows = await db_conn.fetch(
            "SELECT * FROM receita_estabelecimentos ORDER BY cnpj"
        )
        assert [r["cnpj"] for r in rows] == ["11222333000181", "45997418000171"]
        acme, beta = rows
        assert acme["razao_social"] == "METALÚRGICA ACME LTDA"   # Latin-1 lido certo
        assert acme["simples"] is True and acme["mei"] is False
        assert acme["capital_social"] == Decimal("150000.00")
        assert acme["cnaes_secundarios"] == ["2512800", "3321000"]
        # Sem linha no Simples: não é MEI, e não é optante.
        assert beta["simples"] is None and beta["mei"] is None
        assert beta["nome_fantasia"] is None

        municipios = await db_conn.fetch("SELECT * FROM receita_municipios ORDER BY codigo")
        # Só os das UFs carregadas, com a UF tirada dos estabelecimentos.
        assert [(m["codigo"], m["uf"]) for m in municipios] == [("6477", "SP"), ("7107", "SP")]
        assert await db_conn.fetchval("SELECT count(*) FROM receita_cnaes") == 2

        carga_row = await db_conn.fetchrow("SELECT * FROM receita_cargas")
        assert carga_row["status"] == "concluida"
        assert carga_row["estabelecimentos"] == 2
        assert carga_row["ufs"] == "SP"

    async def test_indices_e_pk_com_os_nomes_da_migration(self, db_conn, zips):
        assert await carga.principal(_args(zips)) == 0
        nomes = {r["indexname"] for r in await db_conn.fetch(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'receita_estabelecimentos'"
        )}
        assert nomes == {"receita_estabelecimentos_pkey"} | {n for n, _ in carga.INDICES}
        sobras = await db_conn.fetchval(
            "SELECT count(*) FROM pg_tables WHERE tablename LIKE 'receita_stg_%' "
            "OR tablename = 'receita_estabelecimentos_carga'"
        )
        assert sobras == 0

    async def test_segunda_carga_substitui_a_primeira(self, db_conn, zips):
        assert await carga.principal(_args(zips)) == 0
        assert await carga.principal(_args(zips, referencia="2026-10", manter_mei=True)) == 0
        assert await db_conn.fetchval("SELECT count(*) FROM receita_estabelecimentos") == 3
        refs = await db_conn.fetch(
            "SELECT referencia FROM receita_cargas WHERE status = 'concluida' ORDER BY id"
        )
        assert [r["referencia"] for r in refs] == ["2026-09", "2026-10"]

    async def test_arquivo_faltando_nao_toca_na_base(self, db_conn, zips):
        assert await carga.principal(_args(zips)) == 0
        (zips / "Cnaes.zip").unlink()
        assert await carga.principal(_args(zips, referencia="2026-10")) == 2
        assert await db_conn.fetchval("SELECT count(*) FROM receita_estabelecimentos") == 2

    async def test_simular_nao_grava_nem_apaga(self, db_conn, zips):
        assert await carga.principal(_args(zips, simular=True, apagar_depois=True)) == 0
        assert await db_conn.fetchval("SELECT count(*) FROM receita_estabelecimentos") == 0
        assert await db_conn.fetchval("SELECT count(*) FROM receita_cargas") == 0
        assert (zips / "Estabelecimentos0.zip").exists()

    async def test_falha_no_meio_marca_erro_e_preserva_a_base(self, db_conn, zips, monkeypatch):
        assert await carga.principal(_args(zips)) == 0

        async def explode(*a, **kw):
            raise RuntimeError("disco cheio")

        monkeypatch.setattr(carga, "montar_tabela_nova", explode)
        assert await carga.principal(_args(zips, referencia="2026-10")) == 1
        assert await db_conn.fetchval("SELECT count(*) FROM receita_estabelecimentos") == 2
        st = await db_conn.fetchrow(
            "SELECT status, observacao FROM receita_cargas WHERE referencia = '2026-10'"
        )
        assert st["status"] == "erro" and "disco cheio" in st["observacao"]
