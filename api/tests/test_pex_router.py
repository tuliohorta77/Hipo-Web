"""
Testes dos endpoints de PEX.
Testa upload do CROmie, cálculo de indicadores e compliance.
"""
import io
import pytest
import pandas as pd
from httpx import AsyncClient


def _gerar_cromie_bytes(abas: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for nome, dados in abas.items():
            pd.DataFrame(dados).to_excel(writer, sheet_name=nome, index=False)
    buf.seek(0)
    return buf.read()


class TestUploadCROmie:
    async def test_upload_cromie_sucesso(self, client, usuario_adm, meta_abril):
        conteudo = _gerar_cromie_bytes({
            "Cliente Final": [
                {
                    "Empresa": "Empresa A", "Fase": "Qualificação",
                    "Tarefa Futura": "Sim", "Temperatura Preenchida": "Sim",
                    "Previsão Preenchida": "Sim", "Ticket Preenchido": "Não",
                    "Usuário": "ec.joao@omie.com.vc", "Origem": "Outbound",
                    "Data Criação": "2026-04-01",
                }
            ],
            "Tarefa Cliente": [
                {"Empresa": "Empresa A", "Tipo": "Registro", "Finalidade": "Apresentação",
                 "Resultado": "Realizado", "Usuário": "ec.joao@omie.com.vc", "Data": "2026-04-10"}
            ],
            "Contador": [
                {"Razão Social": "Contabilidade Alpha", "CNPJ": "11.222.333/0001-44",
                 "SOW": "Sim", "Possui Tarefa": "Sim", "Usuário": "ec.joao@omie.com.vc"}
            ],
            "Tarefa Contador": [
                {"Contador": "Contabilidade Alpha", "Tipo": "Reunião",
                 "Finalidade": "Online", "Resultado": "Sucesso",
                 "Usuário": "ec.joao@omie.com.vc", "Data": "2026-04-05"}
            ],
        })
        resp = await client.post(
            "/pex/cromie/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("BD_CROMIE_2026_04.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pex"]["total_geral_pts"] is not None
        assert data["pex"]["risco"] in ["VERDE", "AMARELO", "LARANJA", "VERMELHO"]

    async def test_upload_cromie_detecta_schema_alterado(self, client, usuario_adm, meta_abril):
        conteudo = _gerar_cromie_bytes({
            "Cliente Final": [
                {"Empresa": "Empresa X", "Fase": "Qualificação",
                 "Coluna Nova Omie 2027": "valor_inesperado"}
            ]
        })
        resp = await client.post(
            "/pex/cromie/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("BD_CROMIE_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_alterado"] is True
        assert len(data["colunas_novas"]) > 0

    async def test_painel_sem_dados_retorna_404(self, client, usuario_adm):
        resp = await client.get("/pex/painel", headers=usuario_adm["headers"])
        assert resp.status_code == 404

    async def test_painel_apos_upload(self, client, usuario_adm, meta_abril):
        conteudo = _gerar_cromie_bytes({
            "Cliente Final": [{"Empresa": "X", "Fase": "Qualificação", "Tarefa Futura": "Sim"}],
            "Tarefa Contador": [{"Contador": "Y", "Tipo": "Reunião", "Resultado": "Sucesso", "Data": "2026-04-01"}],
        })
        await client.post(
            "/pex/cromie/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("BD_CROMIE_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        resp = await client.get("/pex/painel", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert "total_geral_pts" in data
        assert "risco_classificacao" in data

    async def test_compliance_apos_upload(self, client, usuario_adm, meta_abril):
        conteudo = _gerar_cromie_bytes({
            "Cliente Final": [
                {"Empresa": "A", "Fase": "Qualificação", "Tarefa Futura": "Não",  # gap!
                 "Usuário": "vendedor@omie.com.vc"},
                {"Empresa": "B", "Fase": "Qualificação", "Tarefa Futura": "Sim",
                 "Usuário": "vendedor@omie.com.vc"},
            ]
        })
        await client.post(
            "/pex/cromie/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("BD_CROMIE_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        resp = await client.get("/pex/compliance", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        dados = resp.json()
        assert len(dados) > 0
        vendedor = next((d for d in dados if d["usuario_responsavel"] == "vendedor@omie.com.vc"), None)
        assert vendedor is not None
        assert vendedor["leads_sem_tarefa_futura"] == 1

    async def test_configurar_metas(self, client, usuario_adm):
        resp = await client.post(
            "/pex/metas",
            headers=usuario_adm["headers"],
            json={
                "mes_ref": "2026-05",
                "nmrr_meta": 50000,
                "demos_outbound_meta": 120,
                "dias_uteis": 21,
                "ecs_ativos_m3": 3,
                "evs_ativos": 2,
                "carteira_total_contadores": 150,
            },
        )
        assert resp.status_code == 200

    async def test_auditoria_schema_registra_historico(self, client, usuario_adm, meta_abril):
        conteudo = _gerar_cromie_bytes({
            "Cliente Final": [{"Empresa": "X", "Fase": "Q"}]
        })
        await client.post(
            "/pex/cromie/upload",
            headers=usuario_adm["headers"],
            files={"arquivo": ("BD_CROMIE_test.xlsx", conteudo,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        resp = await client.get("/pex/cromie/auditoria", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestAuth:
    async def test_login_valido(self, client, usuario_adm):
        resp = await client.post(
            "/auth/login",
            data={"username": usuario_adm["email"], "password": "senha123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_login_senha_errada(self, client, usuario_adm):
        resp = await client.post(
            "/auth/login",
            data={"username": usuario_adm["email"], "password": "senha_errada"},
        )
        assert resp.status_code == 401

    async def test_me_retorna_usuario(self, client, usuario_adm):
        resp = await client.get("/auth/me", headers=usuario_adm["headers"])
        assert resp.status_code == 200
        assert resp.json()["email"] == usuario_adm["email"]
