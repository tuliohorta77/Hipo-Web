"""
HIPO — Testes do modelo de enriquecimento (funções puras).

Sem banco e sem rede: rodam no pytest local do Windows, como os de
`services/cnpj.py` e `services/texto.py`.

O que está coberto aqui é o que mais provavelmente quebra em silêncio: a
leitura de payload de terceiro. Fonte que renomeia campo, devolve faixa em
vez de número, manda data em outro formato ou solta um CPF inteiro no QSA —
cada um desses tem um teste, porque nenhum deles daria erro visível.
"""
import pytest

from services.enriquecimento import modelo as m

# Resposta da BrasilAPI, recortada nos campos que o normalizador lê. Os
# nomes vêm do layout dos Dados Abertos da Receita.
PAYLOAD_BRASILAPI = {
    "cnpj": "11222333000181",
    "razao_social": "  METALURGICA   ALFA LTDA ",
    "nome_fantasia": "Alfa Metais",
    "cnae_fiscal": 2511000,
    "cnae_fiscal_descricao": "Fabricação de estruturas metálicas",
    "cnaes_secundarios": [
        {"codigo": 4399103, "descricao": "Obras de alvenaria"},
        {"codigo": 0, "descricao": "lixo que não vira CNAE"},
    ],
    "descricao_porte": "DEMAIS",
    "porte": "05",
    "descricao_situacao_cadastral": "ATIVA",
    "data_inicio_atividade": "2009-03-17",
    "capital_social": 250000.0,
    "natureza_juridica": "206-2 - Sociedade Empresária Limitada",
    "opcao_pelo_simples": False,
    "cep": "07190-000",
    "logradouro": "AVENIDA DAS INDUSTRIAS",
    "numero": "1500",
    "complemento": "GALPAO 2",
    "bairro": "CUMBICA",
    "municipio": "GUARULHOS",
    "uf": "sp",
    "ddd_telefone_1": "1123456789",
    "email": "CONTATO@ALFA.COM.BR",
    "qsa": [
        {
            "nome_socio": "JOSE DA SILVA",
            "cnpj_cpf_do_socio": "***123456**",
            "qualificacao_socio": "49-Sócio-Administrador",
            "faixa_etaria": "Entre 41 a 50 anos",
            "data_entrada_sociedade": "2009-03-17",
        },
        {
            "nome_socio": "ALFA PARTICIPACOES LTDA",
            "cnpj_cpf_do_socio": "34028316000103",
            "qualificacao_socio": "22-Sócio",
            "data_entrada_sociedade": "2015-06-01",
        },
    ],
}


class TestMascararDocumento:
    def test_cpf_inteiro_nunca_passa_inteiro(self):
        """
        A regra de privacidade do módulo. Fonte paga pode devolver o CPF
        completo; o banco não guarda CPF completo em hipótese nenhuma.
        """
        saida = m.mascarar_documento("12345678901")
        assert saida == "***456789**"
        assert "12345678901" not in saida

    def test_ja_mascarado_passa_intacto(self):
        assert m.mascarar_documento("***123456**") == "***123456**"

    def test_cnpj_de_socio_pj_passa_inteiro(self):
        # CNPJ é dado de empresa, público por definição.
        assert m.mascarar_documento("34.028.316/0001-03") == "34028316000103"

    def test_cpf_embutido_em_texto_tambem_e_mascarado(self):
        # Fonte que devolve "CPF 12345678901" num campo de texto livre não
        # pode furar a regra por causa do invólucro.
        saida = m.mascarar_documento("CPF 12345678901 do socio")
        assert saida == "***456789**"
        assert "12345678901" not in saida

    def test_texto_com_digitos_demais_e_recusado(self):
        # Não é CPF nem CNPJ, mas carrega 11 dígitos seguidos — o CHECK do
        # banco recusaria. Recusar aqui evita o 500.
        assert m.mascarar_documento("ABC12345678901234567") is None

    def test_vazio_vira_none(self):
        assert m.mascarar_documento("   ") is None
        assert m.mascarar_documento(None) is None


class TestCodigoCnae:
    def test_inteiro_da_receita_vira_sete_digitos(self):
        assert m.codigo_cnae(2511000) == "2511000"

    def test_cnae_que_comeca_com_zero_ganha_o_zero_de_volta(self):
        """
        `0111301` chega da Receita como 111301, com 6 dígitos. Sem o zfill,
        o CHECK do banco recusa e o enriquecimento inteiro falha por causa
        de um CNAE agrícola.
        """
        assert m.codigo_cnae(111301) == "0111301"

    def test_mascarado_e_aceito(self):
        assert m.codigo_cnae("25.11-0-00") == "2511000"

    def test_lixo_vira_none(self):
        assert m.codigo_cnae("") is None
        assert m.codigo_cnae(0) is None
        assert m.codigo_cnae("123") is None
        assert m.codigo_cnae("123456789") is None


class TestParaInteiro:
    def test_faixa_vira_o_piso_e_nao_a_media(self):
        """
        Piso é a única leitura honesta de uma faixa. Média inventa precisão
        que o dado não tem.
        """
        assert m.para_inteiro("11 a 50 funcionários") == 11

    def test_numero_puro(self):
        assert m.para_inteiro(30) == 30
        assert m.para_inteiro("30") == 30

    def test_sem_numero_vira_none(self):
        assert m.para_inteiro("sem informação") is None
        assert m.para_inteiro(None) is None


class TestParaData:
    @pytest.mark.parametrize("entrada", [
        "2019-04-16", "16/04/2019", "20190416",
        "2019-04-16T00:00:00Z", "2019-04-16T00:00:00-03:00",
    ])
    def test_formatos_aceitos(self, entrada):
        assert m.para_data(entrada).isoformat() == "2019-04-16"

    def test_data_ilegivel_e_ausencia_de_data_nao_erro(self):
        assert m.para_data("qualquer coisa") is None
        assert m.para_data("00000000") is None


class TestParaDecimal:
    def test_formato_brasileiro(self):
        assert m.para_decimal("1.000.000,00") == 1000000.0

    def test_formato_americano(self):
        assert m.para_decimal("50000.00") == 50000.0


class TestNormalizarBrasilapi:
    @pytest.fixture
    def dados(self):
        return m.normalizar_brasilapi(PAYLOAD_BRASILAPI)

    def test_campos_de_cadastro(self, dados):
        assert dados.razao_social == "METALURGICA ALFA LTDA"
        assert dados.nome_fantasia == "Alfa Metais"
        assert dados.cnae_codigo == "2511000"
        assert dados.cidade == "GUARULHOS"
        assert dados.uf == "SP"
        assert dados.cep == "07190000"
        assert dados.telefone == "1123456789"
        assert dados.capital_social == 250000.0
        assert dados.data_abertura.isoformat() == "2009-03-17"

    def test_porte_usa_a_descricao_e_nao_o_codigo(self, dados):
        assert dados.porte == "DEMAIS"

    def test_numero_de_funcionarios_nao_vem_da_receita(self, dados):
        """
        A Receita não publica quadro de pessoal. `porte` é faixa de
        FATURAMENTO — converter um no outro seria inventar.
        """
        assert dados.num_funcionarios is None
        assert dados.num_funcionarios_origem is None

    def test_cnae_secundario_invalido_e_descartado(self, dados):
        assert dados.cnaes_secundarios == (("4399103", "Obras de alvenaria"),)

    def test_socios(self, dados):
        assert len(dados.socios) == 2
        pessoa, empresa = dados.socios
        assert pessoa.nome == "JOSE DA SILVA"
        assert pessoa.documento_mascarado == "***123456**"
        assert pessoa.eh_pj is False
        assert empresa.eh_pj is True

    def test_nome_normalizado_do_socio_perde_acento_e_sobe_a_caixa(self):
        dados = m.normalizar_brasilapi({
            **PAYLOAD_BRASILAPI,
            "qsa": [{"nome_socio": "José da Silva Júnior"}],
        })
        assert dados.socios[0].nome_normalizado == "JOSE DA SILVA JUNIOR"

    def test_situacao_ativa_significa_operando(self, dados):
        assert dados.operando is True

    def test_baixada_nao_esta_operando(self):
        dados = m.normalizar_brasilapi({
            **PAYLOAD_BRASILAPI, "descricao_situacao_cadastral": "BAIXADA",
        })
        assert dados.operando is False

    def test_payload_vazio_nao_explode(self):
        dados = m.normalizar_brasilapi({})
        assert dados.razao_social is None
        assert dados.socios == ()


class TestNormalizarLeadcnpj:
    def test_le_o_layout_da_receita(self):
        dados = m.normalizar_leadcnpj(PAYLOAD_BRASILAPI)
        assert dados.razao_social == "METALURGICA ALFA LTDA"
        assert dados.cnae_codigo == "2511000"
        assert dados.fonte == "leadcnpj"

    def test_le_o_layout_aportuguesado_alternativo(self):
        """
        A documentação da LeadCNPJ exige login, então o adaptador procura
        cada campo sob vários nomes. Este teste fixa esse contrato: se o
        provedor usar os nomes alternativos, continua funcionando.
        """
        dados = m.normalizar_leadcnpj({
            "cnpj": "11222333000181",
            "razaoSocial": "Beta Servicos LTDA",
            "nomeFantasia": "Beta",
            "atividade_principal": {"codigo": "8610-1/01", "descricao": "Hospital"},
            "quantidade_funcionarios": 180,
            "endereco": {"cidade": "Guarulhos", "uf": "SP", "cep": "07190000"},
            "socios": [{"nome": "Maria Souza", "cpf": "98765432100",
                        "cargo": "Administradora"}],
        })
        assert dados.razao_social == "Beta Servicos LTDA"
        assert dados.cnae_codigo == "8610101"
        assert dados.cidade == "Guarulhos"
        assert dados.num_funcionarios == 180
        assert dados.socios[0].nome == "Maria Souza"

    def test_cpf_inteiro_do_socio_e_mascarado_antes_de_sair_daqui(self):
        dados = m.normalizar_leadcnpj({
            "cnpj": "11222333000181",
            "socios": [{"nome": "Maria Souza", "cpf": "98765432100"}],
        })
        assert dados.socios[0].documento_mascarado == "***654321**"

    def test_numero_de_funcionarios_daqui_e_sempre_estimado(self):
        dados = m.normalizar_leadcnpj({"cnpj": "1", "employees": 42})
        assert dados.num_funcionarios == 42
        assert dados.num_funcionarios_origem == m.ESTIMADO

    def test_sem_funcionarios_nao_inventa_procedencia(self):
        dados = m.normalizar_leadcnpj({"cnpj": "1"})
        assert dados.num_funcionarios is None
        assert dados.num_funcionarios_origem is None

    def test_telefone_em_lista(self):
        dados = m.normalizar_leadcnpj({"cnpj": "1", "telefones": ["1133334444"]})
        assert dados.telefone == "1133334444"


class TestMesclar:
    def test_primeira_fonte_vence_campo_a_campo(self):
        paga = m.DadosEmpresa(
            cnpj="1", fonte="leadcnpj", num_funcionarios=30,
            num_funcionarios_origem=m.ESTIMADO, razao_social="NOME DA PAGA",
        )
        publica = m.DadosEmpresa(
            cnpj="1", fonte="brasilapi", razao_social="NOME DA RECEITA",
            cnae_codigo="2511000",
        )
        junto = m.mesclar(paga, publica)
        assert junto.razao_social == "NOME DA PAGA"
        assert junto.cnae_codigo == "2511000"
        assert junto.num_funcionarios == 30

    def test_fonte_registra_quem_contribuiu(self):
        a = m.DadosEmpresa(cnpj="1", fonte="leadcnpj")
        b = m.DadosEmpresa(cnpj="1", fonte="brasilapi")
        assert m.mesclar(a, b).fonte == "leadcnpj+brasilapi"

    def test_uma_fonte_fora_do_ar_nao_derruba_a_outra(self):
        b = m.DadosEmpresa(cnpj="1", fonte="brasilapi", razao_social="ACME")
        junto = m.mesclar(None, b)
        assert junto.razao_social == "ACME"
        assert junto.fonte == "brasilapi"

    def test_nenhuma_fonte_devolve_none(self):
        assert m.mesclar(None, None) is None


class TestCamposDeConta:
    def test_so_devolve_o_que_tem_valor(self):
        dados = m.DadosEmpresa(cnpj="1", fonte="x", razao_social="ACME")
        campos = dados.campos_de_conta()
        assert campos == {"razao_social": "ACME"}

    def test_socios_nao_entram_em_campos_de_conta(self):
        dados = m.normalizar_brasilapi(PAYLOAD_BRASILAPI)
        assert "socios" not in dados.campos_de_conta()
        assert "cnaes_secundarios" not in dados.campos_de_conta()


class TestEstruturaCnae:
    """
    A derivação da vertical não é chute: a CNAE é uma hierarquia oficial do
    IBGE, e a seção de um código é um fato da classificação.
    """

    def test_secao_pela_divisao(self):
        from services.enriquecimento import cnae_estrutura as ce

        assert ce.secao_de("6204000")[0] == "J"   # tecnologia
        assert ce.secao_de("8610101")[0] == "Q"   # saúde
        assert ce.secao_de("4663000")[0] == "G"   # comércio
        assert ce.secao_de("2511000")[0] == "C"   # indústria
        assert ce.secao_de("4120400")[0] == "F"   # construção
        assert ce.secao_de("0111301")[0] == "A"   # agro

    def test_toda_divisao_existente_tem_secao(self):
        """
        Se uma faixa ficar de fora, um pedaço inteiro da economia deixa de
        ser classificado em silêncio.
        """
        from services.enriquecimento import cnae_estrutura as ce

        # Buracos reais na numeração da CNAE 2.0.
        inexistentes = {4, 34, 40, 44, 48, 54, 57, 67, 76, 83, 89, 98}
        for div in range(1, 100):
            codigo = f"{div:02d}00000"
            tem = ce.secao_de(codigo) is not None
            if div in inexistentes:
                assert not tem, f"divisão {div} não existe mas foi classificada"
            else:
                assert tem, f"divisão {div} ficou sem seção"

    def test_sao_21_secoes(self):
        from services.enriquecimento import cnae_estrutura as ce

        assert len(ce.verticais_derivadas()) == 21
        slugs = [s for s, _ in ce.verticais_derivadas()]
        assert len(set(slugs)) == 21, "slug repetido criaria vertical duplicada"

    def test_codigo_invalido_nao_vira_vertical(self):
        from services.enriquecimento import cnae_estrutura as ce

        assert ce.secao_de("0000000") is None
        assert ce.secao_de("123") is None
        assert ce.secao_de(None) is None


class TestMesmoValor:
    """
    A comparação que decide se a tela pede uma decisão ao usuário.

    Cada caso aqui apareceu numa conta real. Divergência falsa custa mais
    que divergência escondida: o usuário aprende a clicar em "usar os dados
    da fonte" sem ler, e no dia em que a divergência for de verdade ele
    clica igual.
    """

    def _f(self, campo="razao_social"):
        """O campo entra na comparação: telefone e CEP têm regra própria."""
        from services.enriquecimento.persistencia import _mesmo_valor
        return lambda a, b: _mesmo_valor(campo, a, b)

    def test_decimal_do_banco_contra_float_da_fonte(self):
        """
        O caso que apareceu em TODA conta consultada.

        `capital_social` é NUMERIC; o asyncpg devolve Decimal('200000.00') e
        a Receita manda 200000.0. Com `str()` puro, dois textos diferentes
        para o mesmo número — e a tela pedindo ao usuário que escolhesse
        entre R$ 200.000,00 e R$ 200.000,00.
        """
        from decimal import Decimal
        f = self._f("capital_social")
        assert f(Decimal("200000.00"), 200000.0)
        assert f(Decimal("0.00"), 0)
        assert f(Decimal("1000.5"), 1000.50)

    def test_numero_diferente_continua_divergencia(self):
        from decimal import Decimal
        assert not self._f("capital_social")(Decimal("200000.00"), 250000.0)

    def test_acento_e_caixa_nao_sao_divergencia(self):
        """
        `ARUJÁ` no cadastro contra `ARUJA` na Receita. Oferecer a troca
        pioraria o dado: a grafia com acento é a correta.
        """
        assert self._f("cidade")("ARUJÁ", "ARUJA")
        assert self._f("cidade")("São Paulo", "SAO PAULO")
        assert self._f()("  METALURGICA   ALFA ", "Metalurgica Alfa")

    def test_espaco_interno_continua_divergencia(self):
        """
        `A COSTA IMOVEIS` contra `ACOSTA IMOVEIS` são duas grafias da razão
        social, e qual vale é decisão de quem está olhando — não do código.
        Por isso o normalizador colapsa repetição de espaço, mas nunca
        remove o espaço.
        """
        assert not self._f()("A COSTA IMOVEIS LTDA", "ACOSTA IMOVEIS LTDA")

    def test_nulo_nao_casa_com_valor(self):
        assert self._f()(None, None)
        assert not self._f()(None, "algo")
        assert not self._f()("algo", None)

    def test_bool_nao_e_tratado_como_numero(self):
        """True == 1 em Python. Aqui não: campo booleano compara como texto."""
        assert not self._f()(True, 1)

    def test_telefone_compara_so_os_digitos(self):
        """
        `(11) 6860-7201` no cadastro contra `1168607201` na fonte: mesmo
        telefone. A máscara é escolha de quem digitou, e aceitar a troca
        só tiraria a formatação sem ganhar informação.
        """
        f = self._f("telefone")
        assert f("(11) 6860-7201", "1168607201")
        assert f("11 6860-7201", "1168607201")
        assert not f("(11) 6860-7201", "1199998888")

    def test_cep_tambem(self):
        assert self._f("cep")("07400-000", "07400000")

    def test_a_regra_dos_digitos_nao_vaza_para_outros_campos(self):
        """
        Razão social não pode comparar por dígito: `LOJA 2 LTDA` e
        `LOJA 2 SA` virariam o mesmo `2` e a divergência sumiria.
        """
        assert not self._f("razao_social")("LOJA 2 LTDA", "LOJA 2 SA")


class TestEnderecoDaLeadcnpj:
    """
    A URL que a fonte paga recebe.

    Isto não é teste de integração: é uma trava sobre um valor que já
    esteve errado por palpite e custou toda consulta paga com HTTP 400.
    O endereço correto está na página pública leadcnpj.com.br/api-empresas:

        curl -H "Authorization: Bearer leadcnpj_live_..." \\
             "https://leadcnpj.com.br/api/v1/empresa/{cnpj}?enriquecer=true"
    """

    def test_caminho_e_o_documentado(self):
        from config import settings

        molde = settings.LEADCNPJ_CAMINHO_CNPJ
        assert molde.startswith("v1/empresa/"), (
            "o caminho é /v1/empresa/{cnpj} — singular e com o /v1. "
            "O plural sem versão respondia 400 em toda consulta."
        )
        montado = molde.format(cnpj="11222333000181")
        assert montado.startswith("v1/empresa/11222333000181")
        # Sem `enriquecer=true` a resposta é só o espelho da Receita, que a
        # BrasilAPI já dá de graça — e some o nº de funcionários, que é o
        # único motivo de a fonte paga existir aqui.
        assert "enriquecer=true" in montado

    def test_url_montada_bate_com_o_curl_da_documentacao(self):
        from config import settings
        from services.enriquecimento import fontes

        base = fontes._url_base(settings.LEADCNPJ_URL, "")
        caminho = settings.LEADCNPJ_CAMINHO_CNPJ.format(cnpj="12345678000190")
        assert f"{base}/{caminho}" == (
            "https://leadcnpj.com.br/api/v1/empresa/12345678000190"
            "?enriquecer=true"
        )

    def test_credencial_vai_como_bearer(self, monkeypatch):
        from config import settings
        from services.enriquecimento import fontes

        monkeypatch.setattr(settings, "LEADCNPJ_API_KEY", "leadcnpj_live_xyz")
        cabecalhos = fontes._cabecalhos_leadcnpj()
        assert cabecalhos["Authorization"] == "Bearer leadcnpj_live_xyz"


class TestLeadcnpjObjetoCodigoDescricao:
    """
    O formato REAL da LeadCNPJ, conferido contra uma resposta de produção
    em 21/09/2026.

    Onde a BrasilAPI manda texto (`descricao_situacao_cadastral: "ATIVA"`),
    a LeadCNPJ manda objeto (`situacao_cadastral: {"codigo": "02",
    "descricao": "Ativa"}`). Sem desembrulhar, o `str()` do dicionário
    inteiro ia para o banco e a tela mostrava
    `{'codigo': '02', 'descricao': 'Ativa', '` — cortado no limite da
    coluna. E a regra de "empresa fora de operação" comparava com "ATIVA",
    não casava, e marcava TODA empresa ativa como baixada.
    """

    PAYLOAD = {
        "cnpj": "11222333000181",
        "razao_social": "LOJA DE VARIEDADES LTDA",
        "cnae_fiscal": {
            "codigo": "4713002",
            "descricao": "Lojas de variedades, exceto lojas de departamentos",
        },
        "porte": {"codigo": "03", "descricao": "Empresa de Pequeno Porte"},
        "situacao_cadastral": {
            "codigo": "02", "descricao": "Ativa", "data": "2025-05-26",
        },
        "data_inicio_atividade": "2025-05-26",
        "capital_social": 1000000,
        "municipio": {"codigo": "3550308", "descricao": "SAO PAULO"},
        "uf": "SP",
        "ddd_telefone_1": "1168607201",
        "qsa": [{
            "nome": "Hussein Deeb Tiba",
            "cpf": "***778168**",
            "qualificacao": {"codigo": "49", "descricao": "Sócio-Administrador"},
            "faixa_etaria": {"codigo": 5, "descricao": "41-50 anos"},
            "data_entrada_sociedade": "2025-05-26",
        }],
    }

    def _d(self):
        return m.normalizar_leadcnpj(self.PAYLOAD)

    def test_situacao_vira_o_texto_e_nao_o_dicionario(self):
        assert self._d().situacao_cadastral == "Ativa"

    def test_porte_vira_o_texto(self):
        assert self._d().porte == "Empresa de Pequeno Porte"

    def test_cnae_pega_o_codigo_e_a_descricao_de_lugares_diferentes(self):
        """
        O mesmo objeto serve os dois campos: o código vem de `codigo`, a
        atividade vem de `descricao`. É por isso que desembrulhar precisa
        saber qual metade quem chama quer.
        """
        dados = self._d()
        assert dados.cnae_codigo == "4713002"
        assert dados.cnae_descricao.startswith("Lojas de variedades")

    def test_cidade_vira_o_nome(self):
        assert self._d().cidade == "SAO PAULO"

    def test_socio_tambem_desembrulha(self):
        socio = self._d().socios[0]
        assert socio.qualificacao == "Sócio-Administrador"
        assert socio.faixa_etaria == "41-50 anos"
        assert "{" not in (socio.qualificacao or "")

    def test_nenhum_campo_carrega_chave_de_dicionario(self):
        """
        A trava larga: se QUALQUER campo de texto voltar com `{'codigo'`
        dentro, algum lugar deixou de desembrulhar. Vale mais que um teste
        por campo, porque pega o campo que ninguém lembrou de cobrir.
        """
        import dataclasses
        for campo, valor in dataclasses.asdict(self._d()).items():
            if isinstance(valor, str):
                assert "'codigo'" not in valor and "{" not in valor, campo
