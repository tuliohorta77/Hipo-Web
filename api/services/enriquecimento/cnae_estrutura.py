"""
HIPO — Estrutura oficial da CNAE 2.0, usada para classificar sozinho.

O PROBLEMA QUE ISTO RESOLVE

A primeira versão do de-para nascia vazia: cada CNAE esperava alguém dizer
a que vertical pertencia. Com centenas de códigos distintos na base, isso é
trabalho que não termina — e vertical vazia não classifica nada.

A SAÍDA QUE NÃO É CHUTE

A CNAE não é uma lista solta: é uma hierarquia oficial do IBGE. Todo código
de 7 dígitos pertence a uma DIVISÃO (os 2 primeiros dígitos), e toda divisão
pertence a uma das 21 SEÇÕES (A a U), que são nomeadas pelo próprio IBGE.
"6204000 é seção J, informação e comunicação" não é opinião minha — é a
estrutura da classificação.

Então a vertical nasce derivada da seção, e a operação só precisa mexer onde
discordar. É a diferença entre uma base classificada que se ajusta e uma
base vazia que ninguém preenche.

O QUE ISTO **NÃO** FAZ

Não define grau de risco. O grau vem do Anexo I da NR-4, que é norma e tem
valor por SUBCLASSE, não por seção — dentro da mesma divisão há códigos de
grau 1 e de grau 4. Derivar grau de risco por faixa seria inventar um número
que decide dimensionamento de SESMT. Fica nulo até a tabela oficial ser
carregada (ver `scripts/carregar_grau_risco_nr4.py`).

PARA AJUSTAR

Trocar o nome de uma vertical aqui NÃO renomeia a vertical no banco — o
casamento é por slug. Renomear é trabalho da tela de domínio; aqui só se
mexe em qual seção aponta para qual slug.
"""
from __future__ import annotations

# As 21 seções da CNAE 2.0, com a faixa de divisões de cada uma e o nome da
# vertical que o HIPO usa. Fonte: estrutura da CNAE 2.0 (IBGE/Concla).
#
# O nome da vertical é COMERCIAL, não o título acadêmico da seção: quem lê
# é o vendedor. "Transporte e logística" diz mais que "Transporte,
# armazenagem e correio", e continua sendo a mesma seção H.
SECOES = (
    # (secao, divisao_inicial, divisao_final, slug_vertical, nome_vertical)
    ("A", 1, 3, "agro", "Agro"),
    ("B", 5, 9, "industria-extrativa", "Indústria extrativa"),
    ("C", 10, 33, "industria", "Indústria"),
    ("D", 35, 35, "energia", "Energia"),
    ("E", 36, 39, "saneamento-e-residuos", "Saneamento e resíduos"),
    ("F", 41, 43, "construcao", "Construção"),
    ("G", 45, 47, "comercio", "Comércio"),
    ("H", 49, 53, "transporte-e-logistica", "Transporte e logística"),
    ("I", 55, 56, "alimentacao-e-hospedagem", "Alimentação e hospedagem"),
    ("J", 58, 63, "tecnologia-e-comunicacao", "Tecnologia e comunicação"),
    ("K", 64, 66, "financeiro", "Financeiro"),
    ("L", 68, 68, "imobiliario", "Imobiliário"),
    ("M", 69, 75, "servicos-tecnicos", "Serviços técnicos"),
    ("N", 77, 82, "servicos-administrativos", "Serviços administrativos"),
    ("O", 84, 84, "setor-publico", "Setor público"),
    ("P", 85, 85, "educacao", "Educação"),
    ("Q", 86, 88, "saude", "Saúde"),
    ("R", 90, 93, "cultura-e-lazer", "Cultura e lazer"),
    ("S", 94, 96, "outros-servicos", "Outros serviços"),
    ("T", 97, 97, "servicos-domesticos", "Serviços domésticos"),
    ("U", 99, 99, "organismos-internacionais", "Organismos internacionais"),
)


def divisao(codigo: str | None) -> int | None:
    """
    Os dois primeiros dígitos do CNAE — a divisão.

    >>> divisao("6204000")
    62
    >>> divisao("0111301")
    1
    >>> divisao("")
    >>> divisao("123")
    """
    if not codigo:
        return None
    digitos = "".join(ch for ch in str(codigo) if ch.isdigit())
    if len(digitos) != 7:
        return None
    return int(digitos[:2])


def secao_de(codigo: str | None) -> tuple[str, str, str] | None:
    """
    Devolve (secao, slug_vertical, nome_vertical) para um CNAE, ou None.

    >>> secao_de("6204000")
    ('J', 'tecnologia-e-comunicacao', 'Tecnologia e comunicação')
    >>> secao_de("8610101")
    ('Q', 'saude', 'Saúde')
    >>> secao_de("4663000")
    ('G', 'comercio', 'Comércio')
    >>> secao_de("9609208")
    ('S', 'outros-servicos', 'Outros serviços')
    >>> secao_de("2511000")
    ('C', 'industria', 'Indústria')
    >>> secao_de("4120400")
    ('F', 'construcao', 'Construção')
    >>> secao_de("0000000")
    >>> secao_de(None)
    """
    div = divisao(codigo)
    if div is None:
        return None
    for secao, inicio, fim, slug, nome in SECOES:
        if inicio <= div <= fim:
            return (secao, slug, nome)
    # A numeração da CNAE 2.0 tem buracos: 04, 34, 40, 44, 48, 54, 57, 67,
    # 76, 83, 89 e 98 não existem. Código com uma dessas divisões é lixo, e
    # lixo não recebe vertical — devolve None e a tela pede classificação.
    return None


def verticais_derivadas() -> list[tuple[str, str]]:
    """
    (slug, nome) de todas as verticais que a derivação pode usar.

    O seed cria estas; quem já existir com o mesmo slug é reaproveitada, e
    nada é renomeado.

    >>> len(verticais_derivadas())
    21
    """
    return [(slug, nome) for _, _, _, slug, nome in SECOES]
