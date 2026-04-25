"""
Testes do parser do CROmie.
Testa parsing das 4 abas e auditoria de schema.
"""
import pytest
import pandas as pd
from parsers.cromie_parser import parse_cromie_arquivo, _auditar_schema, SCHEMA_CLIENTE_FINAL


class TestAuditoriaSchema:
    def test_schema_sem_alteracao(self):
        df = pd.DataFrame(columns=["op id", "empresa", "cnpj", "fase", "temperatura"])
        result = _auditar_schema(df, ["op_id", "empresa", "cnpj", "fase", "temperatura"], "teste")
        assert result["alterado"] is False

    def test_detecta_coluna_nova(self):
        df = pd.DataFrame(columns=["empresa", "cnpj", "nova_coluna_misteriosa"])
        result = _auditar_schema(df, ["empresa", "cnpj"], "teste")
        assert result["alterado"] is True
        assert any("nova_coluna_misteriosa" in c for c in result["novas"])

    def test_detecta_coluna_removida(self):
        df = pd.DataFrame(columns=["empresa"])
        result = _auditar_schema(df, ["empresa", "cnpj", "fase"], "teste")
        assert result["alterado"] is True
        assert "cnpj" in result["removidas"] or "fase" in result["removidas"]


class TestParseCromie:
    def _criar_cromie_xlsx(self, tmp_path, abas: dict) -> str:
        caminho = str(tmp_path / "BD_CROMIE_test.xlsx")
        with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
            for nome_aba, dados in abas.items():
                pd.DataFrame(dados).to_excel(writer, sheet_name=nome_aba, index=False)
        return caminho

    def test_parse_cliente_final(self, tmp_path):
        caminho = self._criar_cromie_xlsx(tmp_path, {
            "Cliente Final": [
                {
                    "Op Id": "OP001",
                    "Empresa": "Construtora Horizonte",
                    "CNPJ": "12.345.678/0001-90",
                    "Fase": "Qualificação",
                    "Temperatura": "Quente",
                    "Tarefa Futura": "Sim",
                    "Temperatura Preenchida": "Sim",
                    "Previsão Preenchida": "Sim",
                    "Ticket Preenchido": "Não",
                    "Usuário": "ec.joao@omie.com.vc",
                    "Origem": "Inbound",
                }
            ]
        })
        resultado = parse_cromie_arquivo(caminho)
        assert "cliente_final" in resultado["abas"]
        linhas = resultado["abas"]["cliente_final"]["linhas"]
        assert len(linhas) == 1
        assert linhas[0]["empresa"] == "Construtora Horizonte"
        assert linhas[0]["tarefa_futura"] is True
        assert linhas[0]["ticket_preenchido"] is False
        assert linhas[0]["usuario_responsavel"] == "ec.joao@omie.com.vc"

    def test_parse_todas_abas(self, tmp_path):
        caminho = self._criar_cromie_xlsx(tmp_path, {
            "Cliente Final": [{"Empresa": "Empresa A", "Fase": "Qualificação"}],
            "Tarefa Cliente": [{"Empresa": "Empresa A", "Tipo": "Reunião", "Resultado": "Sucesso", "Data": "2026-04-01"}],
            "Contador": [{"Razão Social": "Contabilidade Silva", "CNPJ": "11.222.333/0001-44", "SOW": "Sim"}],
            "Tarefa Contador": [{"Contador": "Contabilidade Silva", "Tipo": "Reunião", "Resultado": "Realizado", "Data": "2026-04-15"}],
        })
        resultado = parse_cromie_arquivo(caminho)
        assert len(resultado["abas"]) == 4
        assert resultado["abas"]["cliente_final"]["total"] == 1
        assert resultado["abas"]["tarefa_cliente"]["total"] == 1
        assert resultado["abas"]["contador"]["total"] == 1
        assert resultado["abas"]["tarefa_contador"]["total"] == 1

    def test_schema_alterado_detectado(self, tmp_path):
        caminho = self._criar_cromie_xlsx(tmp_path, {
            "Cliente Final": [
                {
                    "Empresa": "Empresa X",
                    "Fase": "Qualificação",
                    "Nova Coluna Omie 2027": "valor_novo",  # coluna nova inesperada
                }
            ]
        })
        resultado = parse_cromie_arquivo(caminho)
        assert resultado["schema_alterado"] is True
        auditoria = resultado["abas"]["cliente_final"]["auditoria"]
        assert auditoria["alterado"] is True
        assert len(auditoria["novas"]) > 0

    def test_arquivo_corrompido_retorna_erro(self, tmp_path):
        caminho = str(tmp_path / "BD_CROMIE_corrompido.xlsx")
        with open(caminho, "w") as f:
            f.write("isso não é um xlsx válido")
        resultado = parse_cromie_arquivo(caminho)
        assert len(resultado["erros"]) > 0

    def test_aba_desconhecida_ignorada(self, tmp_path):
        caminho = self._criar_cromie_xlsx(tmp_path, {
            "Cliente Final": [{"Empresa": "X", "Fase": "Qualificação"}],
            "Aba Aleatória": [{"dados": "irrelevantes"}],  # deve ser ignorada
        })
        resultado = parse_cromie_arquivo(caminho)
        assert "aba_aleatória" not in resultado["abas"]
        assert "cliente_final" in resultado["abas"]
