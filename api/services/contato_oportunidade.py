"""
HIPO — Regras do comitê da oportunidade (ABM / multithreading). Entrega 045.

Funções puras: sem banco, sem I/O. Mesmo padrão de services/tarefa.py.

Duas ideias do método SDR viram dado aqui:

  * ACCOUNT BASED: a venda é para a CONTA, não para uma pessoa. Numa
    empresa média quem compra medicina ocupacional envolve RH, DP, Compras,
    SESMT, médico do trabalho e a diretoria. O papel de cada um na decisão
    é vocabulário FECHADO — é a cobertura do comitê que a tela mede, e papel
    inventado não entra na conta.

  * MULTITHREADING: vários relacionamentos simultâneos dentro da conta. Uma
    oportunidade forte tem idealmente de 2 a 4 contatos envolvidos; com um
    só, o negócio depende de uma pessoa que pode sair de férias, ser
    demitida ou simplesmente parar de responder.
"""
from __future__ import annotations

from dataclasses import dataclass

PAPEIS = (
    "decisor", "campeao", "influenciador", "operacional", "compras", "tecnico",
)

ROTULOS_PAPEL = {
    "decisor": "Decisor",
    "campeao": "Campeão",
    "influenciador": "Influenciador",
    "operacional": "Operacional (RH/DP)",
    "compras": "Compras/Financeiro",
    "tecnico": "Técnico (SESMT/Médico)",
}

# A faixa ideal do método. Fica aqui, e não espalhada pelo front, porque é
# o mesmo número que a aula da Universidade ensina.
MINIMO_IDEAL = 2
MAXIMO_IDEAL = 4


class ContatoOportunidadeInvalido(ValueError):
    """Operação recusada pelas regras do comitê."""


def validar_papel(papel: str | None) -> str | None:
    if papel is None:
        return None
    limpo = papel.strip().lower()
    if not limpo:
        return None
    if limpo not in PAPEIS:
        raise ContatoOportunidadeInvalido(
            f"Papel inválido: '{papel}'. Use: {', '.join(PAPEIS)}."
        )
    return limpo


@dataclass(frozen=True)
class Farol:
    nivel: str          # 'sem_contato' | 'um_so' | 'ideal' | 'amplo'
    tom: str            # 'danger' | 'warning' | 'success'
    rotulo: str
    dica: str
    tem_decisor: bool


def farol_multithreading(qtd: int, papeis: list[str | None] | tuple = ()) -> Farol:
    """
    O farol do comitê, a partir de QUANTOS contatos e QUAIS papéis.

        0     -> sem contato  (vermelho)  a conta ainda não tem rosto
        1     -> um só        (amarelo)   single-thread: depende de uma pessoa
        2..4  -> ideal        (verde)
        5+    -> amplo        (verde)     comitê grande; continua bom

    Um contato só é AMARELO e não vermelho de propósito: é o estado normal
    logo depois do primeiro contato, e pintar de vermelho toda oportunidade
    recém-qualificada ensinaria a ignorar a cor. O vermelho fica para o
    que é buraco de verdade — conversa sem ninguém do outro lado.

    O decisor não muda a cor; muda a DICA. Faltar o decisor com três
    contatos ainda é melhor do que um contato só, e misturar os dois
    critérios numa cor só esconderia qual dos dois está faltando.
    """
    qtd = max(int(qtd or 0), 0)
    tem_decisor = "decisor" in (papeis or ())

    if qtd == 0:
        return Farol(
            "sem_contato", "danger", "Sem contato",
            "Mapeie quem decide e quem usa o serviço nesta empresa.",
            tem_decisor,
        )
    if qtd < MINIMO_IDEAL:
        return Farol(
            "um_so", "warning", "1 contato",
            "Depende de uma pessoa só. Abra mais uma frente: RH, DP, "
            "Compras ou SESMT.",
            tem_decisor,
        )
    nivel = "ideal" if qtd <= MAXIMO_IDEAL else "amplo"
    dica = (
        "Comitê coberto." if tem_decisor
        else "Falta mapear o decisor."
    )
    return Farol(nivel, "success", f"{qtd} contatos", dica, tem_decisor)
