"""
HIPO — Enriquecimento: modelo canônico e normalizadores.

Funções PURAS: nada de rede, nada de banco. Rodam no pytest local do Windows
sem Postgres, igual a `services/cnpj.py`.

O QUE ESTE MÓDULO RESOLVE

Cada fonte devolve o mesmo fato com nome diferente: a Receita chama de
`cnae_fiscal`, uma fonte paga chama de `atividade_principal.codigo`. Se o
router falasse com as fontes direto, cada tela precisaria saber de qual
provedor veio o dado. Aqui tudo vira `DadosEmpresa` — um formato só, com os
nomes das colunas de `contas` — e o resto do sistema nunca mais vê o JSON cru.

A REGRA DE PRIVACIDADE MORA AQUI

`mascarar_documento()` é chamada por TODO normalizador, sem exceção. O QSA
público já vem mascarado da Receita (`***123456**`), mas fonte paga pode
devolver o CPF inteiro, e CPF inteiro não entra no banco do HIPO. A coluna
`conta_socios.documento_mascarado` tem CHECK contra 11 dígitos seguidos —
esta função é a primeira barreira, o CHECK é a segunda.

O TOLERANTE NÃO É PREGUIÇA

`_primeiro()` procura o mesmo campo sob vários nomes. Isso existe porque a
documentação da LeadCNPJ não é pública (exige login), e um adaptador que
quebra inteiro porque o provedor renomeou um campo é pior que um que
preenche o que conseguiu. Campo que não casa vira None, e None significa
"a tela pede para o usuário" — nunca "zero" ou "vazio".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime

_SO_DIGITOS = re.compile(r"\D")
_ESPACOS = re.compile(r"\s+")
_ONZE_DIGITOS = re.compile(r"\d{11}")

# Situações cadastrais em que a empresa NÃO opera. Prospectar uma delas é
# queimar ligação — a tela avisa em vermelho antes de o SDR gastar o telefonema.
SITUACOES_MORTAS = {"BAIXADA", "NULA", "INAPTA", "SUSPENSA"}

# Procedência do nº de funcionários. Ver o cabeçalho da migration 014: esta
# distinção é o que impede estimativa de um ano atrás sobrescrever a vida
# declarada pelo cliente.
DECLARADO = "declarado"
ESTIMADO = "estimado"


# ── Helpers puros ────────────────────────────────────────────────────────────

# NOMES sob os quais um objeto {codigo, descricao} guarda cada metade.
# A LeadCNPJ devolve porte, situacao cadastral, CNAE, qualificacao de
# socio e faixa etaria assim -- todos como objeto, nunca como texto.
_ROTULOS = ("descricao", "description", "nome", "name", "texto", "text",
            "label", "valor", "value")
_CODIGOS = ("codigo", "code", "id", "valor", "value", "numero", "number")


def desembrulhar(valor, prefere: str = "rotulo"):
    """
    Tira o texto (ou o código) de um objeto `{codigo, descricao}`.

    POR QUE ISTO EXISTE

    A BrasilAPI devolve `descricao_situacao_cadastral: "ATIVA"`. A LeadCNPJ
    devolve `situacao_cadastral: {"codigo": "02", "descricao": "Ativa"}`. O
    mesmo vale para porte, CNAE, qualificação de sócio e faixa etária.

    Sem desembrulhar, o `str()` do dicionário inteiro ia para o banco e
    aparecia na tela como `{'codigo': '02', 'descricao': 'Ativa', '` —
    cortado no limite da coluna. Pior: a regra que avisa "empresa fora de
    operação" compara com "ATIVA", não casava, e toda empresa ativa saía
    marcada como baixada.

    `prefere="rotulo"` devolve o texto legível; `prefere="codigo"`, o
    código. Quem chama sabe qual quer: `limpar_texto` quer o rótulo,
    `codigo_cnae` quer o código.

    Valor que não é dicionário volta intacto — a função é transparente
    para todo o resto.

    >>> desembrulhar({"codigo": "02", "descricao": "Ativa"})
    'Ativa'
    >>> desembrulhar({"codigo": "4713002", "descricao": "Lojas"}, "codigo")
    '4713002'
    >>> desembrulhar("ATIVA")
    'ATIVA'
    >>> desembrulhar(42)
    42
    >>> desembrulhar({"foo": "bar"})
    {'foo': 'bar'}
    """
    if not isinstance(valor, dict):
        return valor
    ordem = _CODIGOS + _ROTULOS if prefere == "codigo" else _ROTULOS + _CODIGOS
    for chave in ordem:
        interno = valor.get(chave)
        if interno not in (None, "", [], {}) and not isinstance(interno, (dict, list)):
            return interno
    # Objeto que não é um par {codigo, descricao}: devolver intacto é mais
    # honesto que devolver a primeira chave qualquer. O chamador decide.
    return valor


def so_digitos(valor) -> str:
    """
    >>> so_digitos("12.345.678/0001-95")
    '12345678000195'
    >>> so_digitos(None)
    ''
    >>> so_digitos({"codigo": "4713002", "descricao": "Lojas"})
    '4713002'
    """
    valor = desembrulhar(valor, "codigo")
    if valor is None:
        return ""
    return _SO_DIGITOS.sub("", str(valor))


def normalizar_nome(texto: str | None) -> str:
    """
    Chave de casamento de pessoa: sem acento, maiúsculo, espaço colapsado.

    Vai para `conta_socios.nome_normalizado`, que é o que a busca reversa
    consulta. Coluna materializada, e não função no WHERE, para o índice
    poder ser usado.

    >>> normalizar_nome("  José   da Silva Júnior ")
    'JOSE DA SILVA JUNIOR'
    >>> normalizar_nome(None)
    ''
    """
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return _ESPACOS.sub(" ", sem_acento).strip().upper()


def mascarar_documento(valor) -> str | None:
    """
    Devolve o documento em formato seguro para guardar, ou None.

    Já mascarado (formato da Receita) passa intacto. CPF inteiro vira o
    mesmo formato que a Receita usa: três asteriscos, os seis dígitos do
    meio, dois asteriscos. CNPJ de sócio PJ passa inteiro — é dado de
    empresa, público por definição.

    >>> mascarar_documento("***123456**")
    '***123456**'
    >>> mascarar_documento("12345678901")
    '***456789**'
    >>> mascarar_documento("12.345.678/0001-95")
    '12345678000195'
    >>> mascarar_documento("  ")
    >>> mascarar_documento(None)
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None

    digitos = so_digitos(texto)

    # Sócio pessoa jurídica: 14 dígitos são CNPJ, que é público.
    if len(digitos) == 14:
        return digitos

    # CPF inteiro: nunca guardado por inteiro. Mesmo recorte da Receita.
    if len(digitos) == 11:
        return f"***{digitos[3:9]}**"

    # Já mascarado ou formato desconhecido: guarda como veio, desde que não
    # carregue 11 dígitos seguidos (o CHECK do banco recusaria).
    if _ONZE_DIGITOS.search(texto):
        return None
    return texto[:20]


def para_data(valor) -> date | None:
    """
    Aceita os formatos que as fontes usam e devolve `date` ou None.

    Nunca levanta: data ilegível é ausência de data, não erro de consulta —
    o resto do enriquecimento continua valendo.

    >>> para_data("2019-04-16")
    datetime.date(2019, 4, 16)
    >>> para_data("16/04/2019")
    datetime.date(2019, 4, 16)
    >>> para_data("20190416")
    datetime.date(2019, 4, 16)
    >>> para_data("data ruim")
    >>> para_data(0)
    >>> para_data({"valor": "2019-04-16"})
    datetime.date(2019, 4, 16)
    """
    valor = desembrulhar(valor, "codigo")
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    if not texto or texto in {"0", "00000000"}:
        return None

    # ISO com fuso primeiro ("2019-04-16T00:00:00Z", "...-03:00"): é o formato
    # que mais aparece em API e o único que `strptime` com máscara fixa não
    # cobre sem enumerar variações.
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).date()
    except ValueError:
        pass

    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue

    # Último recurso: sobra um horário grudado numa data ISO sem fuso.
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def para_inteiro(valor) -> int | None:
    """
    Número de funcionários chega como int, como "12", como "12 funcionários"
    e como faixa ("11 a 50"). Faixa vira o PISO dela, nunca a média: dizer
    "11" quando pode ser 50 subestima; dizer "30" inventa precisão que o
    dado não tem. O piso é a única leitura honesta — e a tela mostra que é
    estimativa.

    >>> para_inteiro(12)
    12
    >>> para_inteiro("12")
    12
    >>> para_inteiro("11 a 50 funcionários")
    11
    >>> para_inteiro("")
    >>> para_inteiro("sem informação")
    >>> para_inteiro({"codigo": 5, "descricao": "41-50 anos"})
    5
    """
    # Aqui o CÓDIGO é o que vale: numa faixa `{"codigo": 5, "descricao":
    # "41-50 anos"}` a descrição viraria 41, que é outra coisa.
    valor = desembrulhar(valor, "codigo")
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor >= 0 else None
    if isinstance(valor, float):
        return int(valor) if valor >= 0 else None

    numeros = re.findall(r"\d+", str(valor))
    if not numeros:
        return None
    return int(numeros[0])


def para_decimal(valor) -> float | None:
    """
    Capital social chega como número, como "1000000.00" e como
    "1.000.000,00". A vírgula decimal brasileira é o caso que quebra
    `float()` direto.

    >>> para_decimal(1000)
    1000.0
    >>> para_decimal("1.000.000,00")
    1000000.0
    >>> para_decimal("50000.00")
    50000.0
    >>> para_decimal("nada")
    """
    valor = desembrulhar(valor, "codigo")
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    if not texto:
        return None
    # "1.000.000,00" -> "1000000.00" ; "50000.00" fica como está.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def limpar_texto(valor, limite: int = 200) -> str | None:
    """
    Colapsa espaços, corta no limite da coluna e devolve None para vazio.

    >>> limpar_texto("  ACME   LTDA ")
    'ACME LTDA'
    >>> limpar_texto("   ")
    >>> limpar_texto({"codigo": "02", "descricao": "Ativa"})
    'Ativa'
    """
    valor = desembrulhar(valor)
    if valor is None:
        return None
    texto = _ESPACOS.sub(" ", str(valor)).strip()
    return texto[:limite] if texto else None


def _primeiro(dados: dict, *caminhos: str):
    """
    Primeiro caminho presente e não vazio. O caminho desce por ponto, tanto
    em dicionário ("atividade_principal.codigo") quanto em lista por índice
    ("telefones.0") — fonte que devolve contatos em array é comum.

    >>> _primeiro({"a": None, "b": 2}, "a", "b")
    2
    >>> _primeiro({"x": {"y": "z"}}, "x.y")
    'z'
    >>> _primeiro({"tel": ["1133334444"]}, "tel.0")
    '1133334444'
    >>> _primeiro({"tel": []}, "tel.0", "outro")
    >>> _primeiro({"a": ""}, "a", "inexistente")
    """
    for caminho in caminhos:
        atual = dados
        for parte in caminho.split("."):
            if isinstance(atual, dict):
                atual = atual.get(parte)
            elif isinstance(atual, list) and parte.isdigit():
                indice = int(parte)
                atual = atual[indice] if indice < len(atual) else None
            else:
                atual = None
            if atual is None:
                break
        if atual not in (None, "", [], {}):
            return atual
    return None


def _lista(dados: dict, *caminhos: str) -> list:
    """Primeiro caminho que contenha uma lista não vazia. [] se nenhum."""
    valor = _primeiro(dados, *caminhos)
    if isinstance(valor, list):
        return valor
    if isinstance(valor, dict):
        return [valor]
    return []


def codigo_cnae(valor) -> str | None:
    """
    CNAE canônico: 7 dígitos, sem máscara, com zero à esquerda quando a
    fonte devolve como inteiro.

    A Receita entrega `cnae_fiscal` como número — e `8610101` tem 7 dígitos,
    mas `1113502` vindo de um CNAE que começa com zero (`0111301`) chega
    como 111301, com 6. Sem o zfill, o CHECK do banco recusa e o
    enriquecimento inteiro falha por causa de um CNAE agrícola.

    >>> codigo_cnae(8610101)
    '8610101'
    >>> codigo_cnae("86.10-1-01")
    '8610101'
    >>> codigo_cnae(111301)
    '0111301'
    >>> codigo_cnae("")
    >>> codigo_cnae("123")
    """
    digitos = so_digitos(valor)
    if not digitos:
        return None
    if len(digitos) > 7:
        return None
    preenchido = digitos.zfill(7)
    # Menos de 6 dígitos não é CNAE truncado, é lixo. Recusa em silêncio.
    return preenchido if len(digitos) >= 6 else None


# ── Modelo canônico ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Socio:
    """Uma linha do quadro societário, já no formato do banco."""
    nome: str
    nome_normalizado: str
    documento_mascarado: str | None = None
    qualificacao: str | None = None
    faixa_etaria: str | None = None
    entrada_em: date | None = None
    eh_pj: bool = False

    @classmethod
    def de(
        cls,
        nome,
        documento=None,
        qualificacao=None,
        faixa_etaria=None,
        entrada_em=None,
    ) -> "Socio | None":
        """Construtor que normaliza tudo. None se não houver nome."""
        limpo = limpar_texto(nome, 200)
        if not limpo:
            return None
        doc = mascarar_documento(documento)
        return cls(
            nome=limpo,
            nome_normalizado=normalizar_nome(limpo),
            documento_mascarado=doc,
            qualificacao=limpar_texto(qualificacao, 150),
            faixa_etaria=limpar_texto(faixa_etaria, 40),
            entrada_em=para_data(entrada_em),
            # Sócio PJ: documento com 14 dígitos é CNPJ.
            eh_pj=bool(doc and len(so_digitos(doc)) == 14),
        )


@dataclass(frozen=True)
class DadosEmpresa:
    """
    O formato único. Os nomes dos campos são os das colunas de `contas` de
    propósito: o router monta o UPDATE a partir daqui sem tradução no meio.
    """
    cnpj: str
    fonte: str

    razao_social: str | None = None
    nome_fantasia: str | None = None
    cnae_codigo: str | None = None
    cnae_descricao: str | None = None
    cnaes_secundarios: tuple[tuple[str, str], ...] = ()
    porte: str | None = None
    situacao_cadastral: str | None = None
    data_abertura: date | None = None
    capital_social: float | None = None
    natureza_juridica: str | None = None
    simples: bool | None = None

    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None

    telefone: str | None = None
    telefone_2: str | None = None
    email: str | None = None

    num_funcionarios: int | None = None
    num_funcionarios_origem: str | None = None

    socios: tuple[Socio, ...] = field(default_factory=tuple)

    @property
    def operando(self) -> bool:
        """
        False quando a situação cadastral é uma das mortas. None (fonte que
        não informa) conta como operando — não dá para afirmar o contrário.

        >>> DadosEmpresa(cnpj="1", fonte="x", situacao_cadastral="ATIVA").operando
        True
        >>> DadosEmpresa(cnpj="1", fonte="x", situacao_cadastral="Baixada").operando
        False
        >>> DadosEmpresa(cnpj="1", fonte="x").operando
        True
        """
        if not self.situacao_cadastral:
            return True
        return normalizar_nome(self.situacao_cadastral) not in SITUACOES_MORTAS

    def campos_de_conta(self) -> dict:
        """
        Só o que vai para colunas de `contas`, sem os None.

        Sócios e CNAEs secundários ficam de fora: moram em tabelas próprias.
        """
        bruto = {
            "razao_social": self.razao_social,
            "nome_fantasia": self.nome_fantasia,
            "cnae_codigo": self.cnae_codigo,
            "porte": self.porte,
            "situacao_cadastral": self.situacao_cadastral,
            "data_abertura": self.data_abertura,
            "capital_social": self.capital_social,
            "cep": self.cep,
            "logradouro": self.logradouro,
            "numero": self.numero,
            "complemento": self.complemento,
            "bairro": self.bairro,
            "cidade": self.cidade,
            "uf": self.uf,
            "telefone": self.telefone,
            "telefone_2": self.telefone_2,
            "email": self.email,
            "num_funcionarios": self.num_funcionarios,
        }
        return {k: v for k, v in bruto.items() if v is not None}


def mesclar(*fontes: DadosEmpresa | None) -> DadosEmpresa | None:
    """
    Combina o resultado de várias fontes, campo a campo, na ordem recebida:
    o primeiro valor não nulo vence.

    É o que permite `ENRIQUECIMENTO_FONTES=leadcnpj,brasilapi` — a paga
    entrega o nº de funcionários, e a gratuita completa o que ela não trouxe,
    sem gastar crédito à toa nem depender de uma só estar no ar.

    `fonte` do resultado lista quem contribuiu, para a trilha não mentir.

    >>> a = DadosEmpresa(cnpj="1", fonte="leadcnpj", num_funcionarios=30)
    >>> b = DadosEmpresa(cnpj="1", fonte="brasilapi", razao_social="ACME")
    >>> m = mesclar(a, b)
    >>> m.num_funcionarios, m.razao_social, m.fonte
    (30, 'ACME', 'leadcnpj+brasilapi')
    >>> mesclar(None, b).fonte
    'brasilapi'
    >>> mesclar(None) is None
    True
    """
    presentes = [f for f in fontes if f is not None]
    if not presentes:
        return None
    if len(presentes) == 1:
        return presentes[0]

    base = presentes[0]
    mudancas: dict = {}
    for outra in presentes[1:]:
        for campo in base.__dataclass_fields__:
            if campo in ("cnpj", "fonte"):
                continue
            atual = mudancas.get(campo, getattr(base, campo))
            if atual in (None, (), []):
                novo = getattr(outra, campo)
                if novo not in (None, (), []):
                    mudancas[campo] = novo

    mudancas["fonte"] = "+".join(f.fonte for f in presentes)
    return replace(base, **mudancas)


# ── Normalizadores por fonte ─────────────────────────────────────────────────

def normalizar_brasilapi(payload: dict) -> DadosEmpresa:
    """
    Converte a resposta de `GET brasilapi.com.br/api/cnpj/v1/{cnpj}`.

    Os nomes vêm do layout dos Dados Abertos da Receita, que a BrasilAPI
    espelha: `cnae_fiscal`, `qsa[].nome_socio`, `ddd_telefone_1`.

    O telefone chega com DDD grudado ("1133334444") e vai assim para a
    coluna — a máscara é da tela. `VARCHAR(20)` comporta.
    """
    cnpj = so_digitos(_primeiro(payload, "cnpj", "estabelecimento.cnpj"))

    secundarios: list[tuple[str, str]] = []
    for item in _lista(payload, "cnaes_secundarios"):
        if not isinstance(item, dict):
            continue
        codigo = codigo_cnae(item.get("codigo"))
        descricao = limpar_texto(item.get("descricao"), 300)
        if codigo and descricao:
            secundarios.append((codigo, descricao))

    socios: list[Socio] = []
    for item in _lista(payload, "qsa"):
        if not isinstance(item, dict):
            continue
        socio = Socio.de(
            nome=item.get("nome_socio"),
            documento=item.get("cnpj_cpf_do_socio"),
            qualificacao=item.get("qualificacao_socio"),
            faixa_etaria=item.get("faixa_etaria"),
            entrada_em=item.get("data_entrada_sociedade"),
        )
        if socio:
            socios.append(socio)

    simples_bruto = _primeiro(payload, "opcao_pelo_simples")
    if isinstance(simples_bruto, bool):
        simples = simples_bruto
    elif isinstance(simples_bruto, str):
        simples = simples_bruto.strip().upper() in {"S", "SIM", "TRUE"}
    else:
        simples = None

    return DadosEmpresa(
        cnpj=cnpj,
        fonte="brasilapi",
        razao_social=limpar_texto(payload.get("razao_social"), 200),
        nome_fantasia=limpar_texto(payload.get("nome_fantasia"), 200),
        cnae_codigo=codigo_cnae(payload.get("cnae_fiscal")),
        cnae_descricao=limpar_texto(payload.get("cnae_fiscal_descricao"), 300),
        cnaes_secundarios=tuple(secundarios),
        porte=limpar_texto(
            _primeiro(payload, "descricao_porte", "porte"), 40
        ),
        situacao_cadastral=limpar_texto(
            payload.get("descricao_situacao_cadastral"), 40
        ),
        data_abertura=para_data(payload.get("data_inicio_atividade")),
        capital_social=para_decimal(payload.get("capital_social")),
        natureza_juridica=limpar_texto(payload.get("natureza_juridica"), 200),
        simples=simples,
        cep=(so_digitos(payload.get("cep")) or None),
        logradouro=limpar_texto(payload.get("logradouro"), 200),
        numero=limpar_texto(payload.get("numero"), 20),
        complemento=limpar_texto(payload.get("complemento"), 100),
        bairro=limpar_texto(payload.get("bairro"), 100),
        cidade=limpar_texto(payload.get("municipio"), 100),
        uf=(limpar_texto(payload.get("uf"), 2) or "").upper() or None,
        telefone=(so_digitos(payload.get("ddd_telefone_1"))[:20] or None),
        telefone_2=(so_digitos(payload.get("ddd_telefone_2"))[:20] or None),
        email=limpar_texto(payload.get("email"), 150),
        # A Receita NÃO publica quantidade de funcionários. `porte` é faixa
        # de faturamento, não de gente, e converter um no outro seria
        # inventar. Fica None e a tela pede.
        num_funcionarios=None,
        num_funcionarios_origem=None,
        socios=tuple(socios),
    )


def normalizar_leadcnpj(payload: dict) -> DadosEmpresa:
    """
    Converte a resposta da LeadCNPJ.

    TOLERANTE POR NECESSIDADE. A documentação da API deles exige login, então
    cada campo é procurado sob os nomes plausíveis: o do layout da Receita
    (que quase toda fonte brasileira espelha), o aportuguesado e o inglês.
    Campo que não casar vira None — o enriquecimento entrega o que achou em
    vez de falhar inteiro.

    AO CONFERIR CONTRA A RESPOSTA REAL: os únicos pontos a ajustar são as
    listas de nomes em cada `_primeiro(...)`. Nenhuma outra parte do sistema
    conhece o formato da LeadCNPJ.

    O nº de funcionários daqui é SEMPRE `estimado` — vem de base tipo
    RAIS/CAGED, com defasagem. Ver o cabeçalho da migration 014.
    """
    cnpj = so_digitos(
        _primeiro(payload, "cnpj", "empresa.cnpj", "dados.cnpj", "document")
    )

    secundarios: list[tuple[str, str]] = []
    for item in _lista(
        payload, "cnaes_secundarios", "atividades_secundarias",
        "cnae_secundarios", "secondary_activities",
    ):
        if isinstance(item, dict):
            codigo = codigo_cnae(
                _primeiro(item, "codigo", "code", "cnae", "id")
            )
            descricao = limpar_texto(
                _primeiro(item, "descricao", "description", "texto", "text"), 300
            )
        else:
            codigo, descricao = codigo_cnae(item), None
        if codigo:
            secundarios.append((codigo, descricao or "CNAE sem descrição"))

    socios: list[Socio] = []
    for item in _lista(payload, "qsa", "socios", "quadro_societario", "partners"):
        if not isinstance(item, dict):
            continue
        socio = Socio.de(
            nome=_primeiro(item, "nome_socio", "nome", "name", "socio"),
            documento=_primeiro(
                item, "cnpj_cpf_do_socio", "cpf_cnpj", "documento",
                "cpf", "document",
            ),
            qualificacao=_primeiro(
                item, "qualificacao_socio", "qualificacao", "cargo", "role"
            ),
            faixa_etaria=_primeiro(item, "faixa_etaria", "idade", "age_range"),
            entrada_em=_primeiro(
                item, "data_entrada_sociedade", "data_entrada", "entrada",
                "since",
            ),
        )
        if socio:
            socios.append(socio)

    funcionarios = para_inteiro(_primeiro(
        payload,
        "quantidade_funcionarios", "qtd_funcionarios", "numero_funcionarios",
        "num_funcionarios", "funcionarios", "faixa_funcionarios",
        "employees", "employee_count", "employee_range",
        "empresa.quantidade_funcionarios", "dados.quantidade_funcionarios",
    ))

    return DadosEmpresa(
        cnpj=cnpj,
        fonte="leadcnpj",
        razao_social=limpar_texto(
            _primeiro(payload, "razao_social", "razaoSocial", "nome",
                      "company_name", "empresa.razao_social"), 200
        ),
        nome_fantasia=limpar_texto(
            _primeiro(payload, "nome_fantasia", "nomeFantasia", "fantasia",
                      "trade_name"), 200
        ),
        cnae_codigo=codigo_cnae(_primeiro(
            payload, "cnae_fiscal", "cnae_principal", "cnae",
            "atividade_principal.codigo", "cnae_principal.codigo",
            "primary_activity.code",
        )),
        cnae_descricao=limpar_texto(_primeiro(
            payload, "cnae_fiscal_descricao", "cnae_descricao",
            # A LeadCNPJ põe código e descrição no MESMO objeto
            # `cnae_fiscal`. O código sai dele por `desembrulhar`, mas a
            # descrição precisa do caminho explícito — senão `limpar_texto`
            # recebe o objeto e devolve a descrição... do objeto certo por
            # acaso. Ser explícito aqui é o que torna o comportamento
            # previsível quando a fonte mudar.
            "cnae_fiscal.descricao", "cnae_principal.descricao",
            "cnae.descricao", "atividade_principal.descricao",
            "primary_activity.description",
        ), 300),
        cnaes_secundarios=tuple(secundarios),
        porte=limpar_texto(
            _primeiro(payload, "descricao_porte", "porte", "porte_empresa",
                      "company_size"), 40
        ),
        situacao_cadastral=limpar_texto(
            _primeiro(payload, "descricao_situacao_cadastral",
                      "situacao_cadastral", "situacao", "status"), 40
        ),
        data_abertura=para_data(_primeiro(
            payload, "data_inicio_atividade", "data_abertura", "abertura",
            "founded_at",
        )),
        capital_social=para_decimal(_primeiro(
            payload, "capital_social", "capital", "share_capital"
        )),
        natureza_juridica=limpar_texto(_primeiro(
            payload, "natureza_juridica", "descricao_natureza_juridica",
            "legal_nature",
        ), 200),
        simples=_primeiro(payload, "simples_nacional", "opcao_pelo_simples",
                          "simples") in (True, "S", "SIM", "Sim", "true"),
        cep=(so_digitos(_primeiro(
            payload, "cep", "endereco.cep", "address.zip"
        )) or None),
        logradouro=limpar_texto(_primeiro(
            payload, "logradouro", "endereco.logradouro", "address.street"
        ), 200),
        numero=limpar_texto(_primeiro(
            payload, "numero", "endereco.numero", "address.number"
        ), 20),
        complemento=limpar_texto(_primeiro(
            payload, "complemento", "endereco.complemento"
        ), 100),
        bairro=limpar_texto(_primeiro(
            payload, "bairro", "endereco.bairro", "address.district"
        ), 100),
        cidade=limpar_texto(_primeiro(
            payload, "municipio", "cidade", "endereco.municipio",
            "endereco.cidade", "address.city",
        ), 100),
        uf=((limpar_texto(_primeiro(
            payload, "uf", "estado", "endereco.uf", "address.state"
        ), 2) or "").upper() or None),
        telefone=(so_digitos(_primeiro(
            payload, "ddd_telefone_1", "telefone", "telefone_1", "phone",
            "telefones.0",
        ))[:20] or None),
        telefone_2=(so_digitos(_primeiro(
            payload, "ddd_telefone_2", "telefone_2", "phone_2"
        ))[:20] or None),
        email=limpar_texto(
            _primeiro(payload, "email", "e_mail", "emails.0"), 150
        ),
        num_funcionarios=funcionarios,
        num_funcionarios_origem=ESTIMADO if funcionarios is not None else None,
        socios=tuple(socios),
    )
