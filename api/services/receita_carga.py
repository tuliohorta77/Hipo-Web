"""
HIPO — Leitura dos arquivos de Dados Abertos do CNPJ da Receita.

Funções puras: recebem a linha já quebrada em campos e devolvem a tupla que
vai para o banco, ou None quando a linha fica de fora. Sem banco e sem rede —
rodam no pytest local do Windows. Quem orquestra download, COPY e a troca da
tabela é `scripts/carregar_base_receita.py`.

O LAYOUT

Os arquivos não têm cabeçalho. Separador `;`, aspas duplas, encoding
Latin-1. A posição de cada campo vem do "Metadados CNPJ" da Receita, e é
a única coisa que muda quando a Receita muda o layout — por isso as posições
moram aqui, em constantes nomeadas, e o teste prende cada uma com uma linha
real de exemplo.

Datas chegam como AAAAMMDD, com "0" ou "00000000" para vazio. Capital
social chega com vírgula decimal ("1000,00"). Código de CNAE pode chegar sem
o zero da esquerda ("111301" para 0111301).

O QUE FICA DE FORA, E POR QUÊ

  * Situação diferente de 02 (ativa). Empresa baixada, inapta ou suspensa
    não compra exame — e são mais da metade dos registros.
  * UF fora da lista pedida. A base nacional não cabe na conta do RDS, e o
    SDR só trabalha onde a operação atende.
  * CNAE principal ilegível. Sem ele a empresa não aparece em fatia nenhuma
    e só ocuparia espaço.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

# ── Posições no arquivo de ESTABELECIMENTOS ──────────────────────────────────
E_BASICO = 0
E_ORDEM = 1
E_DV = 2
E_MATRIZ_FILIAL = 3
E_FANTASIA = 4
E_SITUACAO = 5
E_INICIO_ATIVIDADE = 10
E_CNAE_PRINCIPAL = 11
E_CNAES_SECUNDARIOS = 12
E_TIPO_LOGRADOURO = 13
E_LOGRADOURO = 14
E_NUMERO = 15
E_COMPLEMENTO = 16
E_BAIRRO = 17
E_CEP = 18
E_UF = 19
E_MUNICIPIO = 20
E_DDD_1 = 21
E_TELEFONE_1 = 22
E_DDD_2 = 23
E_TELEFONE_2 = 24
E_EMAIL = 27
E_TOTAL_CAMPOS = 30

# ── Posições no arquivo de EMPRESAS ──────────────────────────────────────────
M_BASICO = 0
M_RAZAO = 1
M_NATUREZA = 2
M_CAPITAL = 4
M_PORTE = 5
M_TOTAL_CAMPOS = 7

# ── Posições no arquivo do SIMPLES ───────────────────────────────────────────
S_BASICO = 0
S_OPCAO_SIMPLES = 1
S_OPCAO_MEI = 4
S_TOTAL_CAMPOS = 7

SITUACAO_ATIVA = "02"

# Rótulos do porte como a BrasilAPI os escreve — é o que já está em
# `contas.porte` das contas enriquecidas. Escrever igual evita que a mesma
# conta apareça com dois textos para a mesma faixa.
PORTES = {
    "01": "MICRO EMPRESA",
    "03": "EMPRESA DE PEQUENO PORTE",
    "05": "DEMAIS",
}

# Maior valor que cabe em contas.capital_social NUMERIC(15,2). A base traz
# capitais maiores que isso (holdings, estatais), e eles ficariam como erro
# na hora de puxar a empresa para o CRM.
CAPITAL_MAXIMO_CONTA = Decimal("9999999999999.99")
CAPITAL_MAXIMO_BASE = Decimal("1000000000000000")


@dataclass(frozen=True)
class Estabelecimento:
    cnpj: str
    cnpj_basico: str
    matriz: bool
    nome_fantasia: str | None
    data_abertura: date | None
    cnae_principal: str
    cnaes_secundarios: tuple[str, ...]
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    cep: str | None
    uf: str
    municipio_codigo: str
    telefone: str | None
    telefone_2: str | None
    email: str | None

    def como_registro(self) -> tuple:
        """Na ordem das colunas de STAGING_ESTAB (ver o script de carga)."""
        return (
            self.cnpj, self.cnpj_basico, self.matriz, self.nome_fantasia,
            self.data_abertura, self.cnae_principal, list(self.cnaes_secundarios),
            self.logradouro, self.numero, self.complemento, self.bairro,
            self.cep, self.uf, self.municipio_codigo, self.telefone,
            self.telefone_2, self.email,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def so_digitos(valor: str | None) -> str:
    """
    >>> so_digitos(' 11.222-333 ')
    '11222333'
    """
    return "".join(c for c in (valor or "") if c.isdigit())


def texto(valor: str | None, limite: int) -> str | None:
    """
    Colapsa espaços, corta no limite da coluna e transforma vazio em None.

    >>> texto('  RUA   DAS   FLORES ', 200)
    'RUA DAS FLORES'
    >>> texto('   ', 10) is None
    True
    """
    if valor is None:
        return None
    limpo = " ".join(valor.split())
    if not limpo:
        return None
    return limpo[:limite]


def data_receita(valor: str | None) -> date | None:
    """
    AAAAMMDD -> date. "0", "00000000" e data impossível viram None.

    >>> data_receita('20150312')
    datetime.date(2015, 3, 12)
    >>> data_receita('00000000') is None
    True
    >>> data_receita('20151345') is None
    True
    """
    d = so_digitos(valor)
    if len(d) != 8 or d == "00000000":
        return None
    try:
        return date(int(d[:4]), int(d[4:6]), int(d[6:]))
    except ValueError:
        return None


def capital(valor: str | None) -> Decimal | None:
    """
    "1000,00" -> Decimal('1000.00'). Ilegível vira None.

    >>> capital('1500000,50')
    Decimal('1500000.50')
    >>> capital('') is None
    True
    """
    bruto = (valor or "").strip().replace(".", "").replace(",", ".")
    if not bruto:
        return None
    try:
        numero = Decimal(bruto)
    except InvalidOperation:
        return None
    # NUMERIC(17,2) na base: 15 digitos inteiros. Acima disso e erro de
    # digitacao na origem, e o COPY inteiro do arquivo cairia por uma linha.
    if numero < 0 or numero >= CAPITAL_MAXIMO_BASE:
        return None
    return numero.quantize(Decimal("0.01"))


def codigo_cnae(valor: str | None) -> str | None:
    """
    Sete dígitos, com o zero da esquerda que a Receita às vezes come.

    >>> codigo_cnae('111301')
    '0111301'
    >>> codigo_cnae('4120400')
    '4120400'
    >>> codigo_cnae('abc') is None
    True
    """
    d = so_digitos(valor)
    if not d or len(d) > 7:
        return None
    d = d.zfill(7)
    return None if d == "0000000" else d


def telefone(ddd: str | None, numero: str | None) -> str | None:
    """
    DDD grudado no número, só dígitos — o mesmo formato da BrasilAPI
    (`ddd_telefone_1`), para a mesma conta não ter dois telefones iguais
    escritos de jeitos diferentes.

    >>> telefone('11', '2345-6789')
    '1123456789'
    >>> telefone('', '') is None
    True
    """
    n = so_digitos(numero)
    if not n:
        return None
    return (so_digitos(ddd) + n)[:20]


def email(valor: str | None) -> str | None:
    """
    >>> email(' Contato@Empresa.COM.BR ')
    'contato@empresa.com.br'
    >>> email('sem-arroba') is None
    True
    """
    limpo = (valor or "").strip().lower()
    if "@" not in limpo or len(limpo) > 150 or " " in limpo:
        return None
    return limpo


def _campo(campos: list[str], pos: int) -> str:
    return campos[pos] if pos < len(campos) else ""


# ── Linhas ───────────────────────────────────────────────────────────────────

def linha_estabelecimento(campos: list[str], ufs: frozenset[str]) -> Estabelecimento | None:
    """
    Uma linha do arquivo de estabelecimentos, ou None se ela fica de fora.

    A checagem de UF e de situação vem ANTES de qualquer outra conversão:
    são elas que descartam a maior parte do arquivo, e o script passa por
    dezenas de milhões de linhas.
    """
    if len(campos) < E_TOTAL_CAMPOS - 2:
        return None
    uf = _campo(campos, E_UF).strip().upper()
    if uf not in ufs:
        return None
    if so_digitos(_campo(campos, E_SITUACAO)).zfill(2) != SITUACAO_ATIVA:
        return None

    basico = so_digitos(_campo(campos, E_BASICO)).zfill(8)
    ordem = so_digitos(_campo(campos, E_ORDEM)).zfill(4)
    dv = so_digitos(_campo(campos, E_DV)).zfill(2)
    cnpj = basico + ordem + dv
    if len(cnpj) != 14:
        return None

    cnae = codigo_cnae(_campo(campos, E_CNAE_PRINCIPAL))
    if cnae is None:
        return None

    municipio = so_digitos(_campo(campos, E_MUNICIPIO))
    if not municipio or len(municipio) > 4:
        return None

    secundarios: list[str] = []
    for bruto in _campo(campos, E_CNAES_SECUNDARIOS).split(","):
        codigo = codigo_cnae(bruto)
        if codigo and codigo != cnae and codigo not in secundarios:
            secundarios.append(codigo)

    tipo = texto(_campo(campos, E_TIPO_LOGRADOURO), 40)
    logr = texto(_campo(campos, E_LOGRADOURO), 200)
    logradouro = texto(f"{tipo or ''} {logr or ''}", 200) if logr else None

    cep = so_digitos(_campo(campos, E_CEP))

    return Estabelecimento(
        cnpj=cnpj,
        cnpj_basico=basico,
        matriz=_campo(campos, E_MATRIZ_FILIAL).strip() == "1",
        nome_fantasia=texto(_campo(campos, E_FANTASIA), 200),
        data_abertura=data_receita(_campo(campos, E_INICIO_ATIVIDADE)),
        cnae_principal=cnae,
        cnaes_secundarios=tuple(secundarios),
        logradouro=logradouro,
        numero=texto(_campo(campos, E_NUMERO), 20),
        complemento=texto(_campo(campos, E_COMPLEMENTO), 100),
        bairro=texto(_campo(campos, E_BAIRRO), 100),
        cep=cep if len(cep) == 8 else None,
        uf=uf,
        municipio_codigo=municipio.zfill(4),
        telefone=telefone(_campo(campos, E_DDD_1), _campo(campos, E_TELEFONE_1)),
        telefone_2=telefone(_campo(campos, E_DDD_2), _campo(campos, E_TELEFONE_2)),
        email=email(_campo(campos, E_EMAIL)),
    )


def linha_empresa(campos: list[str]) -> tuple | None:
    """
    (cnpj_basico, razao_social, natureza_juridica, capital_social, porte).

    O filtro por cnpj_basico (só as empresas cujos estabelecimentos
    entraram) é do script, que tem o conjunto na mão.
    """
    if len(campos) < M_TOTAL_CAMPOS - 1:
        return None
    basico = so_digitos(_campo(campos, M_BASICO)).zfill(8)
    razao = texto(_campo(campos, M_RAZAO), 200)
    if len(basico) != 8 or not razao:
        return None
    natureza = so_digitos(_campo(campos, M_NATUREZA))
    porte = so_digitos(_campo(campos, M_PORTE))
    return (
        basico,
        razao,
        natureza.zfill(4) if natureza and len(natureza) <= 4 else None,
        capital(_campo(campos, M_CAPITAL)),
        porte.zfill(2) if porte and len(porte) <= 2 else None,
    )


def linha_simples(campos: list[str]) -> tuple | None:
    """(cnpj_basico, optante_simples, mei). 'S' é sim; o resto, não."""
    if len(campos) < S_TOTAL_CAMPOS - 2:
        return None
    basico = so_digitos(_campo(campos, S_BASICO)).zfill(8)
    if len(basico) != 8:
        return None
    return (
        basico,
        _campo(campos, S_OPCAO_SIMPLES).strip().upper() == "S",
        _campo(campos, S_OPCAO_MEI).strip().upper() == "S",
    )


def linha_codigo_descricao(campos: list[str], digitos: int) -> tuple | None:
    """
    Tabelas auxiliares (Municipios, Cnaes): código;descrição.

    >>> linha_codigo_descricao(['7107', 'SAO PAULO'], 4)
    ('7107', 'SAO PAULO')
    >>> linha_codigo_descricao(['111301', 'Cultivo de arroz'], 7)
    ('0111301', 'Cultivo de arroz')
    """
    if len(campos) < 2:
        return None
    codigo = so_digitos(campos[0])
    if not codigo or len(codigo) > digitos:
        return None
    descricao = texto(campos[1], 300)
    if not descricao:
        return None
    return codigo.zfill(digitos), descricao


def ufs_validas(bruto: str) -> frozenset[str]:
    """
    "sp, RJ" -> {'SP', 'RJ'}. Levanta ValueError com a UF ruim no texto.

    >>> sorted(ufs_validas('sp, RJ'))
    ['RJ', 'SP']
    """
    ufs = {u.strip().upper() for u in (bruto or "").split(",") if u.strip()}
    if not ufs:
        raise ValueError("Informe ao menos uma UF (ex.: --ufs SP).")
    for uf in ufs:
        if len(uf) != 2 or not uf.isalpha():
            raise ValueError(f"UF inválida: {uf!r}.")
    return frozenset(ufs)
