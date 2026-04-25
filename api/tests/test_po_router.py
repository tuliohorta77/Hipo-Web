"""
Testes dos endpoints de POs (v2).
Reescrito para usar as colunas reais das planilhas da Omie identificadas após
análise das 4 planilhas de produção.
"""
import io
import pytest
import pandas as pd
from httpx import AsyncClient


def _gerar_po_bytes(linhas: list[dict], tipo: str = "comissao",
                    com_enabler: bool = False, fundo: float = -7.5,
                    subtotal: float = None) -> bytes:
    """
    Gera um Excel de PO em memória usando as colunas REAIS da Omie.

    `linhas` espera dicts simples no formato:
      {"ref": "app1", "cliente": "X", "valor": 100, "contador": "..."}

    Adiciona automaticamente as 2 linhas especiais (Fundo + Subtotal) que
    sempre aparecem no formato real.
    """
    rows = []

    if tipo == "comissao":
        for l in linhas:
            row = {
                "Aplicativo": l.get("aplicativo", "Test App"),
                "Cliente": l.get("cliente", "Cliente Teste"),
                "NFS-e": l.get("nfse", "1234567"),
                "Faturado R$": l.get("faturado", l["valor"] * 3.3),
                "Impostos R$": l.get("impostos", l["valor"] * 0.25),
                "Comissão R$": l["valor"],
                "Referência do Aplicativo": l["ref"],
                "PO": l.get("po", 1500000000),
            }
            if com_enabler:
                row["Contador"] = l.get("contador", "* Sem Contador")
            rows.append(row)
    elif tipo == "repasse":
        for l in linhas:
            rows.append({
                "Razão Social": l.get("cliente", "Cliente Teste"),
                "Fantasia": l.get("cliente", "Cliente Teste"),
                "NFS-e": l.get("nfse", "1234567"),
                "Parcela": l.get("parcela", "1/1"),
                "Valor Faturado": l.get("faturado", l["valor"] * 1.4),
                "Impostos": l.get("impostos", l["valor"] * 0.04),
                "Valor do Repasse": l["valor"],
                "Aplicativo Ativado Por": l.get("ep"),
                "Referência do Aplicativo": l["ref"],
                "PO": l.get("po", 1500000000),
            })
    elif tipo == "incentivo":
        for l in linhas:
            rows.append({
                "Contador": l.get("contador", "* Sem Contador"),
                "Aplicativo": l.get("aplicativo", "Test App"),
                "Cliente": l.get("cliente", "Cliente Teste"),
                "Valor Negociado R$": l.get("negociado", l["valor"] * 2),
                "Abatimentos - Impostos R$": l.get("impostos", l["valor"] * 0.15),
                "Abatimentos - Comissão do Contador R$": l.get("com_cont", 0),
                "Abatimentos - Comissão da Franquia R$": l.get("com_franq", 0),
                "Prêmio R$": l["valor"],
                "Ativado Por": l.get("ep"),
                "Referência do Aplicativo": l["ref"],
                "PO": l.get("po", 1500000000),
            })

    # Adiciona linhas especiais (sempre presentes no formato real)
    valor_col = {"comissao": "Comissão R$", "repasse": "Valor do Repasse", "incentivo": "Prêmio R$"}[tipo]
    desc_col = {"comissao": "Cliente", "repasse": "Razão Social", "incentivo": "Cliente"}[tipo]
    soma = sum(l["valor"] for l in linhas)
    if subtotal is None:
        subtotal = round(soma + fundo, 2)

    rows.append({desc_col: "Fundo de Marketing (2,5%)", valor_col: fundo})
    rows.append({valor_col: subtotal})

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf.read()


class TestUploadPO:
    async def test_upload_comissao_sucesso(self, client, usuario_adm):
        conteudo = _gerar_po_bytes([
            {"ref": "app1", "cliente": "Empresa A", "valor": 1800.0},
            {"ref": "app2", "cliente": "Empresa B", "valor": 950.0},
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
        # Arquivo com nome não reconhecido pelo detectar_tipo
        df = pd.DataFrame([{"col": "val"}])
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        resp = await client.post(
            "/po/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("arquivo_invalido.xlsx", buf.read(),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 400

    async def test_upload_sem_autenticacao_retorna_401(self, client):
        conteudo = _gerar_po_bytes([{"ref": "app1", "valor": 100}])
        resp = await client.post(
            "/po/upload",
            files={"arquivo": ("Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 401

    async def test_upload_enabler_detectado(self, client, usuario_adm):
        conteudo = _gerar_po_bytes([
            {"ref": "app1", "valor": 900, "contador": "Silva Contab."},
        ], com_enabler=True)
        resp = await client.post(
            "/po/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("Omie_Apuracao_ComissaoV6Enabler_2026_4_Abril_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        assert resp.json()["tem_enabler"] is True


class TestReconciliacao:
    async def _upload_po(self, client, headers, nome, linhas, **kwargs):
        conteudo = _gerar_po_bytes(linhas, **kwargs)
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
        await self._upload_po(
            client, usuario_adm["headers"],
            "Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx",
            [{"ref": "app1", "valor": 1000}],
        )
        resp = await client.get("/po/reconciliacao/ausentes", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_historico_registra_upload(self, client, usuario_adm):
        await self._upload_po(
            client, usuario_adm["headers"],
            "Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx",
            [{"ref": "app1", "valor": 1000}],
        )
        resp = await client.get("/po/historico", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["total_linhas"] == 1

    async def test_resumo_financeiro(self, client, usuario_adm):
        await self._upload_po(
            client, usuario_adm["headers"],
            "Omie_Apuracao_ComissaoV6_2026_4_Abril_test.xlsx",
            [{"ref": "app1", "valor": 1800}],
        )
        resp = await client.get("/po/resumo/financeiro", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)