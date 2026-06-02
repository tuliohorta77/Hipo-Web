"""
HIPO -- Permissões por cargo (controle de acesso aos módulos).

Cargos e seus módulos:
  ADM, Franqueado:  tudo (+ agendamento)
  Gerente:          carteira + clientes + agendamento
  EP:               carteira + clientes
  EV:               clientes              (Vendas + Clientes, SEM Contadores)
  Hunter, Farmer:   só carteira (Contadores)
  SDR:              só agendamento        (módulo Agendamento — v1.3.1)
  EC:               só carteira (compat)

Notas:
  - O módulo é chamado 'carteira' no backend mas o frontend o chama
    de "Contadores" (renomeação visual, não estrutural).
  - 'clientes' é o módulo de oportunidades/leads + tarefas, e a página
    Vendas também é protegida por ele (decisão de produto:
    "quem vê Clientes vê Vendas").
  - EV (Executivo de Vendas) tem 'clientes' mas NÃO tem 'carteira':
    vê Clientes + Vendas e não vê Contadores.
  - SDR (v1.3.1): cargo dedicado ao módulo 'agendamento'. A v1 do
    Agendamento replica a régua de conformidade do CROmie. O SDR NÃO
    vê Contadores nem Clientes — só Agendamento. EC permanece em
    'carteira' por compat com o schema antigo.
  - v1.3.2: ADM, Franqueado e Gerente também passam a ver o módulo
    'agendamento' (acompanhamento). EP NÃO recebe (decisão de produto).
  - Rotas que servem ao drilldown da carteira (ex: /clientes/contador-leads)
    devem usar requer_qualquer_modulo(["clientes", "carteira"]) para
    permitir que Hunter/Farmer (que só têm 'carteira') também acessem.
"""
from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException

from routers.auth import usuario_atual


# Cargos que veem TUDO.
CARGOS_ADMIN = {"ADM", "Franqueado"}

# Cargos com acesso a Contadores + Clientes (mas não admin).
CARGOS_GESTAO = {"Gerente", "EP"}

# Cargos de Vendas: Clientes + Vendas, SEM Contadores.
CARGOS_VENDAS = {"EV"}

# Cargos que veem só Contadores (acesso a leads é via drilldown).
# EC permanece aqui por compat com o schema antigo.
CARGOS_OPERACIONAL = {
    "Hunter", "Farmer",
    "EC",
}

# Cargo de pré-vendas (agendamento). v1.3.1: módulo Agendamento, que
# replica a régua de conformidade do CROmie. Separado de CARGOS_OPERACIONAL
# de propósito — SDR não vê Contadores.
CARGOS_AGENDAMENTO = {"SDR"}

# Cargos de gestão/admin que ACOMPANHAM o Agendamento (v1.3.2).
# Recebem o módulo 'agendamento' ADICIONALMENTE aos seus módulos.
# EP fica de fora por decisão de produto.
CARGOS_VE_AGENDAMENTO = {"ADM", "Franqueado", "Gerente"}


def modulos_do_cargo(cargo: str | None) -> set[str]:
    """
    Devolve o conjunto de módulos visíveis para o cargo informado.

    Módulos:
      - 'pex'          : PEX, Compliance Gaps
      - 'po'           : POs, reconciliação
      - 'bd'           : BD Ativados
      - 'metas'        : Configuração de metas
      - 'carteira'     : Contadores (Hunter/Farmer/Outros + upload)
      - 'clientes'     : Oportunidades + Tarefas de clientes (cobre Vendas)
      - 'agendamento'  : Agendamento (régua de conformidade — SDR + gestão)
      - 'usuarios'     : Gestão de usuários (futuro)
    """
    if not cargo:
        return set()

    if cargo in CARGOS_ADMIN:
        mods = {"pex", "po", "bd", "metas", "carteira", "clientes", "usuarios"}
    elif cargo in CARGOS_GESTAO:
        mods = {"carteira", "clientes", "painel"}
    elif cargo in CARGOS_VENDAS:
        # Vendas e Clientes, sem Contadores.
        mods = {"clientes", "painel"}
    elif cargo in CARGOS_AGENDAMENTO:
        # Só Agendamento — não vê Contadores nem Clientes.
        mods = {"agendamento", "painel"}
    elif cargo in CARGOS_OPERACIONAL:
        mods = {"carteira", "painel"}
    else:
        return set()

    # v1.3.2: ADM/Franqueado/Gerente também acompanham o Agendamento.
    if cargo in CARGOS_VE_AGENDAMENTO:
        mods = mods | {"agendamento", "painel"}

    return mods


def deve_filtrar_por_usuario(cargo: str | None) -> bool:
    """
    Decide se a visão de Carteira deve ser restrita ao colaborador
    vinculado ao usuário logado (v1.3.0 — visibilidade por colaborador).

    Regra:
      - Cargos ADMIN (ADM, Franqueado), GESTÃO (Gerente, EP) e VENDAS
        (EV) veem o conjunto inteiro -> retorna False (sem filtro).
      - Cargos OPERACIONAIS (Hunter, Farmer, EC) veem apenas a própria
        fatia -> retorna True (filtra por usuario_id).
      - SDR não tem 'carteira', então na prática essa função nem é
        consultada para ele nos endpoints de Carteira. Por segurança,
        cai no ramo final e retorna True (filtra).
      - Cargo desconhecido ou ausente: por segurança, retorna True
        (filtra). Um cargo não mapeado não deve ver tudo por acidente.

    Nota: EV não tem o módulo 'carteira', então na prática essa função
    nem é consultada para EV nos endpoints de Carteira. Mas se um dia
    EV ganhar acesso parcial à carteira (ex: ver os próprios contadores),
    esta função precisará ser revista.

    Usada pelos endpoints de dashboard/resumo do router de carteira.
    """
    if not cargo:
        return True
    if cargo in CARGOS_ADMIN or cargo in CARGOS_GESTAO or cargo in CARGOS_VENDAS:
        return False
    # Operacionais, SDR e quaisquer cargos não mapeados: filtra.
    return True


def requer_modulo(modulo: str):
    """Dependency factory. 403 se o cargo não tem o módulo."""
    async def _dep(user=Depends(usuario_atual)):
        cargo = user.get("cargo")
        permitidos = modulos_do_cargo(cargo)
        if modulo not in permitidos:
            raise HTTPException(
                403,
                f"Cargo '{cargo or 'sem cargo'}' não tem acesso ao módulo '{modulo}'.",
            )
        return user
    return _dep


def requer_qualquer_modulo(modulos: Iterable[str]):
    """
    Dependency factory: libera se o usuário tem QUALQUER UM dos módulos da lista.

    Uso típico: rotas que conceitualmente pertencem a um módulo (ex: /clientes/...)
    mas que servem ao drilldown de outro (ex: aba Leads dentro de Contadores).
    Aplicada como dependency da rota — sobrescreve o guard global do router.

    Exemplo:
        @router.get("/contador-leads",
                    dependencies=[Depends(requer_qualquer_modulo(["clientes","carteira"]))])
        async def leads_do_contador(...): ...

    Raises:
        HTTPException 403 se o cargo não tem nenhum dos módulos.
    """
    modulos_set = set(modulos)
    if not modulos_set:
        raise ValueError("requer_qualquer_modulo: lista de módulos não pode ser vazia.")

    async def _dep(user=Depends(usuario_atual)):
        cargo = user.get("cargo")
        permitidos = modulos_do_cargo(cargo)
        if not (permitidos & modulos_set):
            raise HTTPException(
                403,
                f"Cargo '{cargo or 'sem cargo'}' não tem acesso a nenhum dos "
                f"módulos exigidos: {sorted(modulos_set)}.",
            )
        return user
    return _dep
