"""
HIPO - Escopo de visao por cargo (recorte de dados, nao de modulo).

Funcao pura, sem banco: roda no pytest local do Windows.

O guard de modulo (routers/permissions.requer_modulo) responde "esta pessoa
pode abrir esta tela?". Esta funcao responde a pergunta seguinte: "dentro
da tela, de QUEM sao os registros que ela enxerga?".

A regra e a da especificacao do filtro por envolvimento (docs do projeto,
filtro-por-envolvimento.md):

    Gestao (Franqueado, ADM)          -> tudo           (devolve None)
    Operacional (EC, SDR, EV, EP)     -> so o que e seu (devolve o id)
    Cargo extinto ou nulo             -> nunca chega aqui: o guard de
                                         modulo ja barrou.

None significa "sem recorte", NAO "sem acesso". Por isso cargo desconhecido
devolve o proprio id (recorte maximo) e nao None: se um dia um cargo novo
ganhar o modulo 'crm' antes de alguem decidir o escopo dele, o erro fica do
lado seguro -- ele ve pouco, em vez de ver tudo.

O recorte nasce do JWT, no servidor. Nunca de parametro que o cliente
escolhe mandar.
"""
from __future__ import annotations

from uuid import UUID

from routers.permissions import CARGOS_GESTAO


def eh_gestao(cargo: str | None) -> bool:
    return cargo in CARGOS_GESTAO


def escopo_de_visao(cargo: str | None, usuario_id) -> UUID | None:
    """
    Devolve o usuario_id que recorta a visao, ou None para visao total.

    >>> escopo_de_visao("ADM", "u1") is None
    True
    >>> escopo_de_visao("EV", "u1")
    'u1'
    """
    if eh_gestao(cargo):
        return None
    return usuario_id
