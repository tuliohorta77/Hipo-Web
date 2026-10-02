"""
HIPO — Prospecção: as regras da fatia e do "puxar para o HIPO".

Funções puras, sem banco e sem rede — rodam no pytest local do Windows. O
router (`routers/crm_prospeccao.py`) só orquestra.

A FATIA

O SDR recorta a base da Receita (022) por UF, CNAE e, opcionalmente, cidade,
porte, regime e idade da empresa. `montar_where` traduz esse recorte em SQL
parametrizado. Duas regras de entrada, ambas para proteger o banco de
produção de uma consulta que varre o estado inteiro:

  * UF é obrigatória. A base é recortada por UF na carga e os dois índices
    começam por ela.
  * CNAE é obrigatório, a partir da DIVISÃO (2 dígitos). Fatiar "tudo de SP"
    não é prospecção, é exportar a Receita.

A SITUAÇÃO DE CADA CNPJ NA FATIA

O mesmo CNPJ pode já existir no CRM, e o que o SDR pode fazer depende do
que ele é lá. A ordem das regras é a ordem de prioridade — a primeira que
casar decide:

    bloqueada          conta marcada "não prospectar" (010)
    inativa            conta desativada (delete lógico)
    cliente            já tem oportunidade CONQUISTADA
    em_negociacao      já tem oportunidade ativa ou suspensa
    conta_sem_negocio  conta existe, sem nada aberto nem ganho
    nova               não existe no CRM

Só as duas últimas são PUXÁVEIS. "Cliente" fica de fora de propósito:
cliente de carteira é trabalho do EC, e uma oportunidade de prospecção
aberta em cima dele por um SDR seria o pior jeito de descobrir isso.

A mesma regra existe em SQL (`SITUACAO_SQL`) para a lista e os KPIs, e aqui
em Python para a decisão do puxar. O teste de API prende as duas juntas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from services import cnpj as cnpj_svc
from services.receita_carga import CAPITAL_MAXIMO_CONTA, PORTES

LIMITE_LOTE = 50

# A oportunidade nasce numa conta que ninguém conversou ainda. Temperatura
# baixa de propósito: o padrão do formulário (50) é para quem já sabe algo
# do cliente, e 50 lotes puxados com 50 inflariam qualquer leitura do funil
# ponderada por temperatura. Editável depois, como em qualquer oportunidade.
TEMPERATURA_PADRAO = 10

ORIGEM_SLUG = "base-receita"
ORIGEM_NOME = "Base da Receita"

TIPO_TAREFA = "ligacao"

SITUACOES = (
    "nova", "conta_sem_negocio", "em_negociacao", "cliente", "inativa",
    "bloqueada",
)
PUXAVEIS = frozenset({"nova", "conta_sem_negocio"})

MOTIVOS_PULO = {
    "bloqueada": "Conta marcada como não prospectar.",
    "inativa": "Conta desativada no CRM.",
    "cliente": "Já é cliente (oportunidade conquistada).",
    "em_negociacao": "Já tem oportunidade aberta.",
    "fora_da_base": "CNPJ fora da base da Receita carregada.",
    "cnpj_invalido": "CNPJ inválido.",
    "repetido": "CNPJ repetido no lote.",
}

PORTES_VALIDOS = frozenset({"00", *PORTES})
REGIMES = frozenset({"simples", "nao_simples"})

ORDENACOES = {
    "capital": "r.capital_social DESC NULLS LAST, r.razao_social",
    "abertura": "r.data_abertura ASC NULLS LAST, r.razao_social",
    "razao": "r.razao_social",
}

# Espelho SQL de `situacao()`. Espera os aliases `c` (contas, LEFT JOIN) e
# `o` (agregado das oportunidades da conta: `aberta`, `conquistada`).
SITUACAO_SQL = """
    CASE
        WHEN c.id IS NULL THEN 'nova'
        WHEN c.nao_prospectar THEN 'bloqueada'
        WHEN NOT c.ativo THEN 'inativa'
        WHEN COALESCE(o.conquistada, FALSE) THEN 'cliente'
        WHEN COALESCE(o.aberta, FALSE) THEN 'em_negociacao'
        ELSE 'conta_sem_negocio'
    END
"""


class FiltroInvalido(ValueError):
    """Recorte que a tela não deveria ter conseguido montar."""


# ── Situação ─────────────────────────────────────────────────────────────────

def situacao(
    existe: bool,
    ativa: bool = True,
    nao_prospectar: bool = False,
    tem_conquistada: bool = False,
    tem_aberta: bool = False,
) -> str:
    """
    >>> situacao(existe=False)
    'nova'
    >>> situacao(existe=True, nao_prospectar=True, tem_aberta=True)
    'bloqueada'
    >>> situacao(existe=True, tem_conquistada=True, tem_aberta=True)
    'cliente'
    >>> situacao(existe=True)
    'conta_sem_negocio'
    """
    if not existe:
        return "nova"
    if nao_prospectar:
        return "bloqueada"
    if not ativa:
        return "inativa"
    if tem_conquistada:
        return "cliente"
    if tem_aberta:
        return "em_negociacao"
    return "conta_sem_negocio"


# ── Filtros ──────────────────────────────────────────────────────────────────

def faixa_cnae(prefixo: str) -> tuple[str, str]:
    """
    Divisão, grupo, classe ou subclasse -> faixa de subclasses.

    >>> faixa_cnae('41')
    ('4100000', '4199999')
    >>> faixa_cnae('4120400')
    ('4120400', '4120400')
    >>> faixa_cnae('01')
    ('0100000', '0199999')
    """
    p = "".join(c for c in (prefixo or "") if c.isdigit())
    if len(p) < 2 or len(p) > 7:
        raise FiltroInvalido(
            f"CNAE {prefixo!r}: use de 2 (divisão) a 7 dígitos (subclasse)."
        )
    return p.ljust(7, "0"), p.ljust(7, "9")


def anos_atras(hoje: date, anos: int) -> date:
    """
    >>> anos_atras(date(2026, 10, 2), 3)
    datetime.date(2023, 10, 2)
    >>> anos_atras(date(2028, 2, 29), 1)
    datetime.date(2027, 2, 28)
    """
    try:
        return hoje.replace(year=hoje.year - anos)
    except ValueError:  # 29/02 num ano que não é bissexto
        return hoje.replace(year=hoje.year - anos, day=28)


@dataclass(frozen=True)
class FiltrosFatia:
    ufs: tuple[str, ...]
    cnaes: tuple[str, ...]
    secundarios: bool = False
    municipios: tuple[str, ...] = ()
    portes: tuple[str, ...] = ()
    regime: str | None = None
    idade_min: int | None = None
    capital_min: Decimal | None = None
    com_telefone: bool = False
    com_email: bool = False
    so_matriz: bool = False
    q: str | None = None
    so_puxaveis: bool = True

    def validar(self) -> "FiltrosFatia":
        if not self.ufs:
            raise FiltroInvalido("Escolha ao menos uma UF.")
        for uf in self.ufs:
            if len(uf) != 2 or not uf.isalpha() or not uf.isupper():
                raise FiltroInvalido(f"UF inválida: {uf!r}.")
        if not self.cnaes:
            raise FiltroInvalido(
                "Escolha ao menos um CNAE. Fatiar o estado inteiro não é "
                "prospecção."
            )
        if len(self.cnaes) > 30:
            raise FiltroInvalido("No máximo 30 CNAEs por fatia.")
        for c in self.cnaes:
            faixa_cnae(c)
        for m in self.municipios:
            if not m.isdigit() or len(m) != 4:
                raise FiltroInvalido(f"Município inválido: {m!r}.")
        for p in self.portes:
            if p not in PORTES_VALIDOS:
                raise FiltroInvalido(f"Porte inválido: {p!r}.")
        if self.regime is not None and self.regime not in REGIMES:
            raise FiltroInvalido(f"Regime inválido: {self.regime!r}.")
        if self.idade_min is not None and not 0 <= self.idade_min <= 100:
            raise FiltroInvalido("Idade mínima entre 0 e 100 anos.")
        if self.capital_min is not None and self.capital_min < 0:
            raise FiltroInvalido("Capital mínimo não pode ser negativo.")
        return self


@dataclass
class _Sql:
    """Acumula cláusulas e parâmetros com a numeração $n do asyncpg."""
    clausulas: list[str] = field(default_factory=list)
    params: list = field(default_factory=list)

    def p(self, valor) -> str:
        self.params.append(valor)
        return f"${len(self.params)}"


def montar_where(f: FiltrosFatia, hoje: date) -> tuple[str, list]:
    """
    WHERE parametrizado sobre `receita_estabelecimentos r`.

    Não inclui o filtro de situação: ele depende do JOIN com contas e é o
    router que o acrescenta (ver `SITUACAO_SQL`).
    """
    s = _Sql()
    s.clausulas.append(f"r.uf = ANY({s.p(list(f.ufs))}::char(2)[])")

    faixas = [faixa_cnae(c) for c in f.cnaes]
    principal = " OR ".join(
        f"r.cnae_principal BETWEEN {s.p(lo)} AND {s.p(hi)}" for lo, hi in faixas
    )
    if f.secundarios:
        # O índice GIN serve ao `&&` com uma lista de códigos, não a uma
        # faixa. A lista sai da própria tabela de CNAEs da Receita: são ~1.300
        # linhas, e o subselect roda uma vez só (initplan).
        dentro = " OR ".join(
            f"rc.codigo BETWEEN {s.p(lo)} AND {s.p(hi)}" for lo, hi in faixas
        )
        s.clausulas.append(
            f"(({principal}) OR r.cnaes_secundarios && "
            f"ARRAY(SELECT rc.codigo FROM receita_cnaes rc WHERE {dentro})::char(7)[])"
        )
    else:
        s.clausulas.append(f"({principal})")

    if f.municipios:
        s.clausulas.append(
            f"r.municipio_codigo = ANY({s.p(list(f.municipios))}::char(4)[])"
        )
    if f.portes:
        s.clausulas.append(f"r.porte = ANY({s.p(list(f.portes))}::char(2)[])")
    if f.regime == "simples":
        s.clausulas.append("r.simples IS TRUE")
    elif f.regime == "nao_simples":
        s.clausulas.append("r.simples IS NOT TRUE")
    if f.idade_min:
        s.clausulas.append(f"r.data_abertura <= {s.p(anos_atras(hoje, f.idade_min))}")
    if f.capital_min is not None:
        s.clausulas.append(f"r.capital_social >= {s.p(f.capital_min)}")
    if f.com_telefone:
        s.clausulas.append("r.telefone IS NOT NULL")
    if f.com_email:
        s.clausulas.append("r.email IS NOT NULL")
    if f.so_matriz:
        s.clausulas.append("r.matriz")
    termo = (f.q or "").strip()
    if termo:
        sem_pontuacao = "".join(c for c in termo if c not in "./- ")
        if len(sem_pontuacao) >= 8 and sem_pontuacao.isdigit():
            # Busca por CNPJ (ou pela raiz de 8 dígitos, que acha matriz e
            # filiais juntas).
            s.clausulas.append(f"r.cnpj LIKE {s.p(sem_pontuacao + '%')}")
        else:
            padrao = f"%{termo}%"
            ph = s.p(padrao)
            s.clausulas.append(f"(r.razao_social ILIKE {ph} OR r.nome_fantasia ILIKE {ph})")

    return " AND ".join(s.clausulas), s.params


# ── Do registro da Receita para a conta ─────────────────────────────────────

def conta_da_base(base: dict, municipio_nome: str | None) -> dict:
    """
    Colunas de `contas` preenchidas a partir da linha da Receita.

    `situacao_cadastral` é 'ATIVA' porque a carga só guarda ativas — e com
    o mesmo texto que a BrasilAPI devolve, para o enriquecimento que vem
    logo depois não acusar divergência onde não há nenhuma.

    Capital acima do que `contas.capital_social` comporta fica vazio em vez
    de estourar o INSERT: é dado de holding e estatal, e não decide
    prospecção de ninguém.
    """
    capital = base.get("capital_social")
    if capital is not None and Decimal(capital) > CAPITAL_MAXIMO_CONTA:
        capital = None
    cidade = (municipio_nome or "").strip()[:100] or None
    return {
        "cnpj": base["cnpj"],
        "razao_social": base["razao_social"],
        "nome_fantasia": base.get("nome_fantasia"),
        "cnae_codigo": base["cnae_principal"],
        "porte": PORTES.get(base.get("porte") or ""),
        "situacao_cadastral": "ATIVA",
        "data_abertura": base.get("data_abertura"),
        "capital_social": capital,
        "cep": base.get("cep"),
        "logradouro": base.get("logradouro"),
        "numero": base.get("numero"),
        "complemento": base.get("complemento"),
        "bairro": base.get("bairro"),
        "cidade": cidade,
        "uf": base.get("uf"),
        "telefone": base.get("telefone"),
        "telefone_2": base.get("telefone_2"),
        "email": base.get("email"),
    }


def titulo_primeiro_contato(razao_social: str, nome_fantasia: str | None) -> str:
    """
    >>> titulo_primeiro_contato('ACME INDUSTRIA LTDA', 'ACME')
    'Primeiro contato - ACME'
    >>> titulo_primeiro_contato('ACME INDUSTRIA LTDA', None)
    'Primeiro contato - ACME INDUSTRIA LTDA'
    """
    nome = (nome_fantasia or "").strip() or razao_social.strip()
    return f"Primeiro contato - {nome}"[:200]


def preparar_lote(cnpjs: list[str]) -> tuple[list[str], list[dict]]:
    """
    Normaliza o lote: devolve (válidos na ordem recebida, pulados).

    Repetido no mesmo lote é pulado na segunda aparição — dois cliques no
    mesmo CNPJ não podem virar duas oportunidades.

    >>> validos, pulados = preparar_lote(['11.222.333/0001-81', '11222333000181', '123'])
    >>> validos
    ['11222333000181']
    >>> [p['motivo'] for p in pulados]
    ['repetido', 'cnpj_invalido']
    """
    validos: list[str] = []
    pulados: list[dict] = []
    for bruto in cnpjs:
        num = cnpj_svc.normalizar(bruto)
        if not cnpj_svc.valido(num):
            pulados.append({"cnpj": num or str(bruto), "motivo": "cnpj_invalido"})
            continue
        if num in validos:
            pulados.append({"cnpj": num, "motivo": "repetido"})
            continue
        validos.append(num)
    return validos, pulados
