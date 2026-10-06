"""
HIPO — scripts/clonar_config (entrega 046): copia a configuração da base da
Controller MedSeg para a base nova da MOS.

Cobertura:
  - funções puras: leitura do .env, mesmo banco, plano de colunas, chave S3
  - travas: mesmo banco, destino com operação, mesmo bucket sem prefixo
  - clone de verdade entre dois bancos: tabelas de configuração chegam,
    autoria vira NULL, sequência continua de onde parou, operação NÃO vem,
    plano (sem --executar) não grava, materiais da UC ganham chave própria
    e o objeto é copiado no S3 (cliente falso)

O teste de clone cria um segundo banco no mesmo servidor de teste (o usuário
do CI é superusuário do postgres do service) e o apaga no fim.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest

from scripts.clonar_config import (
    TABELA_MATERIAIS,
    TABELAS_CONFIG,
    CloneRecusado,
    Coluna,
    Opcoes,
    clonar,
    identidade_do_banco,
    ler_env,
    mascarar,
    nova_chave_s3,
    plano_de_colunas,
    tabelas_do_clone,
    validar_origem_destino,
)

_DB_URL = os.environ["DATABASE_URL"]
_SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


# ── Puras ─────────────────────────────────────────────────────────────────

class TestLerEnv:
    def test_formato_do_systemd(self):
        texto = (
            "# comentario\n"
            "DATABASE_URL=postgresql://u:p@h:5432/hipo\n"
            "\n"
            "S3_BUCKET_ANEXOS='hipo-anexos'\n"
            'EMPRESA_NOME="MOS Medicina"\n'
            "export AWS_REGION=eu-central-1\n"
            "SEM_IGUAL\n"
            "VAZIA=\n"
        )
        assert ler_env(texto) == {
            "DATABASE_URL": "postgresql://u:p@h:5432/hipo",
            "S3_BUCKET_ANEXOS": "hipo-anexos",
            "EMPRESA_NOME": "MOS Medicina",
            "AWS_REGION": "eu-central-1",
            "VAZIA": "",
        }

    def test_senha_com_igual_nao_e_cortada(self):
        assert ler_env("DATABASE_URL=postgresql://u:a=b@h/x")["DATABASE_URL"] == (
            "postgresql://u:a=b@h/x"
        )


class TestMesmoBanco:
    def test_identidade(self):
        assert identidade_do_banco("postgresql://u:p@HOST/hipo") == ("host", 5432, "hipo")

    def test_recusa_mesmo_banco_com_usuario_diferente(self):
        with pytest.raises(CloneRecusado):
            validar_origem_destino(
                "postgresql://hipo:x@rds.amazonaws.com:5432/hipo",
                "postgresql://hipo_mos:y@rds.amazonaws.com/hipo",
            )

    def test_aceita_outro_banco_no_mesmo_servidor(self):
        validar_origem_destino(
            "postgresql://hipo:x@rds.amazonaws.com:5432/hipo",
            "postgresql://hipo_mos:y@rds.amazonaws.com:5432/hipo_mos",
        )

    def test_recusa_url_vazia(self):
        with pytest.raises(CloneRecusado):
            validar_origem_destino("", "postgresql://h/x")

    def test_mascara_senha(self):
        assert mascarar("postgresql://u:segredo@h/x") == "postgresql://u:****@h/x"


class TestPlanoDeColunas:
    def test_fk_de_usuario_vira_null_tipado_e_gerada_fica_de_fora(self):
        origem = [Coluna("id", "integer"), Coluna("nome", "text"),
                  Coluna("criado_por", "uuid", fk_usuarios=True), Coluna("so_na_origem", "text")]
        destino = [Coluna("id", "integer"), Coluna("nome", "text"),
                   Coluna("criado_por", "uuid", fk_usuarios=True),
                   Coluna("busca", "tsvector", gerada=True), Coluna("so_no_destino", "text")]
        cols, exprs = plano_de_colunas(origem, destino)
        assert cols == ["id", "nome", "criado_por"]
        assert exprs == ['"id"', '"nome"', "NULL::uuid"]


class TestChaveS3:
    @pytest.mark.parametrize("prefixo,chave,esperada", [
        ("mos/", "uc/aulas/a/b.pdf", "mos/uc/aulas/a/b.pdf"),
        ("mos", "uc/aulas/a/b.pdf", "mos/uc/aulas/a/b.pdf"),
        ("/mos/", "uc/aulas/a/b.pdf", "mos/uc/aulas/a/b.pdf"),
        ("mos/", "mos/uc/aulas/a/b.pdf", "mos/uc/aulas/a/b.pdf"),  # idempotente
        ("", "uc/aulas/a/b.pdf", "uc/aulas/a/b.pdf"),
    ])
    def test_nova_chave(self, prefixo, chave, esperada):
        assert nova_chave_s3(prefixo, chave) == esperada


class TestTabelasDoClone:
    def test_sem_bucket_no_destino_materiais_ficam_de_fora(self):
        assert TABELA_MATERIAIS not in tabelas_do_clone(Opcoes(bucket_destino=""))

    def test_receita_so_quando_pedida(self):
        assert "receita_estabelecimentos" not in tabelas_do_clone(Opcoes(bucket_destino="b"))
        assert "receita_estabelecimentos" in tabelas_do_clone(
            Opcoes(bucket_destino="b", com_receita=True)
        )


# ── Clone entre dois bancos ───────────────────────────────────────────────

def _url_com_banco(url: str, banco: str) -> str:
    u = urlparse(url)
    return urlunparse(u._replace(path=f"/{banco}"))


@pytest.fixture
async def destino():
    """Banco novo com o schema.sql aplicado, apagado no fim."""
    nome = f"hipo_clone_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_DB_URL)
    await admin.execute(f'CREATE DATABASE "{nome}"')
    conn = await asyncpg.connect(_url_com_banco(_DB_URL, nome))
    try:
        await conn.execute(_SCHEMA.read_text(encoding="utf-8"))
        yield conn
    finally:
        await conn.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{nome}"')
        await admin.close()


class S3Falso:
    def __init__(self):
        self.copias: list[tuple[str, str, str, str]] = []

    def copy_object(self, *, Bucket, Key, CopySource):
        self.copias.append((CopySource["Bucket"], CopySource["Key"], Bucket, Key))


async def _semear_origem(conn) -> dict:
    """Configuração + um pouco de operação na 'base MedSeg'."""
    autor = await conn.fetchval(
        "INSERT INTO usuarios (nome, email, senha_hash, cargo) "
        "VALUES ('Autor', 'autor@teste.com', 'x', 'Franqueado') RETURNING id"
    )
    await conn.execute(
        "INSERT INTO dia_nao_util (data, motivo, criado_por_usuario_id) "
        "VALUES ('2026-11-20', 'Consciencia Negra', $1)", autor,
    )
    await conn.execute(
        "INSERT INTO verticais (nome, slug, criado_por) VALUES "
        "('Industria', 'industria', $1), ('Servicos', 'servicos', $1)", autor,
    )
    await conn.execute(
        "INSERT INTO tipos_reuniao (sigla, nome, slug, criado_por) "
        "VALUES ('AP', 'Apresentação', 'apresentacao', $1)", autor,
    )
    trilha = await conn.fetchval(
        "INSERT INTO uc_trilhas (titulo, pilar, status, criado_por) "
        "VALUES ('Manual do SDR', 'metodo', 'publicada', $1) RETURNING id", autor,
    )
    await conn.execute(
        "INSERT INTO uc_trilha_cargos (trilha_id, cargo, prazo_dias) VALUES ($1, 'SDR', 30)", trilha,
    )
    aula = await conn.fetchval(
        "INSERT INTO uc_aulas (trilha_id, ordem, titulo, conteudo_md) "
        "VALUES ($1, 1, 'Abertura', '# oi') RETURNING id", trilha,
    )
    chave = f"uc/aulas/{aula}/{uuid.uuid4()}.pdf"
    await conn.execute(
        "INSERT INTO uc_materiais (aula_id, chave_s3, nome_original, tipo_mime, bytes, enviado_por) "
        "VALUES ($1, $2, 'roteiro.pdf', 'application/pdf', 10, $3)", aula, chave, autor,
    )
    # Operação: NÃO pode ir para o destino.
    await conn.execute("INSERT INTO contatos (nome) VALUES ('Fulano')")
    return {"chave": chave, "trilha": trilha}


class TestClone:
    async def test_copia_config_e_nao_copia_operacao(self, db_conn, destino):
        semente = await _semear_origem(db_conn)
        s3 = S3Falso()
        op = Opcoes(prefixo_s3="mos/", bucket_origem="hipo-anexos", bucket_destino="hipo-anexos")

        resultado = await clonar(db_conn, destino, op, executar=True, s3=s3, log=lambda *_: None)

        assert set(resultado) == set(TABELAS_CONFIG)
        assert resultado["verticais"] == 2
        assert resultado["uc_aulas"] == 1
        # Seeds do schema (tipos_reuniao) foram substituídos pelos da origem.
        assert await destino.fetchval("SELECT count(*) FROM tipos_reuniao") == 1
        # Autoria: os usuários da origem não existem aqui.
        assert await destino.fetchval("SELECT count(*) FROM usuarios") == 0
        assert await destino.fetchval(
            "SELECT criado_por FROM uc_trilhas WHERE id = $1", semente["trilha"]
        ) is None
        # Operação ficou na origem.
        assert await destino.fetchval("SELECT count(*) FROM contatos") == 0
        # Sequência continua depois do maior id copiado.
        maior = await destino.fetchval("SELECT max(id) FROM verticais")
        novo = await destino.fetchval(
            "INSERT INTO verticais (nome, slug) VALUES ('Nova', 'nova') RETURNING id"
        )
        assert novo == maior + 1
        # Material: objeto copiado no S3 e a linha aponta para a cópia.
        assert s3.copias == [
            ("hipo-anexos", semente["chave"], "hipo-anexos", "mos/" + semente["chave"])
        ]
        assert await destino.fetchval("SELECT chave_s3 FROM uc_materiais") == (
            "mos/" + semente["chave"]
        )
        # A origem não foi tocada.
        assert await db_conn.fetchval("SELECT chave_s3 FROM uc_materiais") == semente["chave"]

    async def test_plano_nao_grava(self, db_conn, destino):
        await _semear_origem(db_conn)
        antes = await destino.fetchval("SELECT count(*) FROM tipos_reuniao")
        op = Opcoes(prefixo_s3="mos/", bucket_origem="b", bucket_destino="b")
        assert await clonar(db_conn, destino, op, executar=False, s3=S3Falso(),
                            log=lambda *_: None) == {}
        assert await destino.fetchval("SELECT count(*) FROM tipos_reuniao") == antes
        assert await destino.fetchval("SELECT count(*) FROM verticais") == 0

    async def test_sem_bucket_no_destino_aula_vem_sem_material(self, db_conn, destino):
        await _semear_origem(db_conn)
        s3 = S3Falso()
        await clonar(db_conn, destino, Opcoes(bucket_origem="b", bucket_destino=""),
                     executar=True, s3=s3, log=lambda *_: None)
        assert await destino.fetchval("SELECT count(*) FROM uc_aulas") == 1
        assert await destino.fetchval("SELECT count(*) FROM uc_materiais") == 0
        assert s3.copias == []

    async def test_recusa_destino_com_operacao(self, db_conn, destino):
        await _semear_origem(db_conn)
        await destino.execute(
            "INSERT INTO contas (cnpj, razao_social) VALUES ('11222333000181', 'Ja Existe LTDA')"
        )
        with pytest.raises(CloneRecusado, match="já tem operação"):
            await clonar(db_conn, destino, Opcoes(), executar=True, log=lambda *_: None)

    async def test_recusa_mesmo_bucket_sem_prefixo(self, db_conn, destino):
        await _semear_origem(db_conn)
        with pytest.raises(CloneRecusado, match="prefixo"):
            await clonar(db_conn, destino, Opcoes(bucket_origem="b", bucket_destino="b"),
                         executar=True, s3=S3Falso(), log=lambda *_: None)
