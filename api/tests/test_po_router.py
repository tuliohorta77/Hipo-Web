"""
Testes dos endpoints de POs.
Testa upload, reconciliação e consultas.
"""
import io
import pytest
import pandas as pd
from httpx import AsyncClient


def _gerar_po_bytes(dados: list[dict], nome_coluna_ref="Referência Aplicativo") -> bytes:
    """Gera um Excel de PO em memória."""
    df = pd.DataFrame(dados)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf.read()


class TestUploadPO:
    async def test_upload_comissao_sucesso(self, client, usuario_adm):
        conteudo = _gerar_po_bytes([
            {"Referência Aplicativo": "APP001", "Razão Social": "Empresa A", "Valor Líquido": 1800.0},
            {"Referência Aplicativo": "APP002", "Razão Social": "Empresa B", "Valor Líquido": 950.0},
        ])
        resp = await client.post(
            "/po/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tipo"] == "COMISSAO"
        assert data["tem_enabler"] is False
        assert data["total_linhas"] == 2

    async def test_upload_arquivo_desconhecido_retorna_400(self, client, usuario_adm):
        conteudo = _gerar_po_bytes([{"col": "val"}])
        resp = await client.post(
            "/po/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("arquivo_invalido.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 400

    async def test_upload_sem_autenticacao_retorna_401(self, client):
        conteudo = _gerar_po_bytes([{"Referência Aplicativo": "APP001", "Valor Líquido": 100}])
        resp = await client.post(
            "/po/upload",
            files={"arquivo": ("Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 401

    async def test_upload_enabler_detectado(self, client, usuario_adm):
        conteudo = _gerar_po_bytes([
            {"Referência Aplicativo": "APP001", "Valor Líquido": 900, "Contador": "Silva Contab."},
        ])
        resp = await client.post(
            "/po/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("Omie_Apuracao_ComissaoV6Enabler_2026_4_Abril_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        assert resp.json()["tem_enabler"] is True


class TestReconciliacao:
    async def _upload_po(self, client, headers, nome, dados):
        conteudo = _gerar_po_bytes(dados)
        return await client.post(
            "/po/upload",
            headers=headers,
            files={"arquivo": (nome, conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    async def test_reconciliacao_retorna_lista_vazia_sem_uploads(self, client, usuario_adm):
        resp = await client.get("/po/reconciliacao/ultima", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_ausentes_retorna_lista_vazia_sem_projecao(self, client, usuario_adm):
        # Faz upload mas sem projeção cadastrada
        await self._upload_po(
            client, usuario_adm["headers"],
            "Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx",
            [{"Referência Aplicativo": "APP001", "Valor Líquido": 1000}],
        )
        resp = await client.get("/po/reconciliacao/ausentes", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        # Sem projeção cadastrada, não há ausentes
        assert isinstance(resp.json(), list)

    async def test_historico_registra_upload(self, client, usuario_adm):
        await self._upload_po(
            client, usuario_adm["headers"],
            "Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx",
            [{"Referência Aplicativo": "APP001", "Valor Líquido": 1000}],
        )
        resp = await client.get("/po/historico", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["total_linhas"] == 1

    async def test_resumo_financeiro(self, client, usuario_adm):
        await self._upload_po(
            client, usuario_adm["headers"],
            "Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx",
            [{"Referência Aplicativo": "APP001", "Valor Líquido": 1800}],
        )
        resp = await client.get("/po/resumo/financeiro", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
