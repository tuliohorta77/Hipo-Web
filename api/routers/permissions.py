"""
HIPO -- Permissões por cargo (controle de acesso aos módulos).

Cargos e seus módulos:
  ADM, Franqueado:  tudo
  Gerente, EP:      pex + po + bd + metas + carteira + clientes + usuarios
  Hunter, Farmer:   só carteira (contadores)
  SDR, EV, EC:      só carteira (compat)

Notas:
  - O módulo é chamado 'carteira' no backend mas o frontend o chama
    de "Contadores" (renomeação visual, não estrutural).
  - 'clientes' é o módulo de oportunidades/leads + tarefas.
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

# Cargos que veem só Contadores (acesso a leads é via drilldown).
CARGOS_OPERACIONAL = {
    "Hunter", "Farmer",
    "SDR", "EV", "EC",  # cargos antigos do schema, mantidos por compat
}


def modulos_do_cargo(cargo: str | None) -> set[str]:
    """
    Devolve o conjunto de módulos visíveis para o cargo informado.

    Módulos:
      - 'pex'        : PEX, Compliance Gaps
      - 'po'         : POs, reconciliação
      - 'bd'         : BD Ativados
      - 'metas'      : Configuração de metas
      - 'carteira'   : Contadores (Hunter/Farmer/Outros + upload)
      - 'clientes'   : Oportunidades + Tarefas de clientes
      - 'usuarios'   : Gestão de usuários (futuro)
    """
    if not cargo:
        return set()
    if cargo in CARGOS_ADMIN:
        return {"pex", "po", "bd", "metas", "carteira", "clientes", "usuarios"}
    if cargo in CARGOS_GESTAO:
        # Gerente e EP veem apenas Contadores e Clientes
        return {"carteira", "clientes"}
    if cargo in CARGOS_OPERACIONAL:
        return {"carteira"}
    return set()


def deve_filtrar_por_usuario(cargo: str | None) -> bool:
    """
    Decide se a visão de Carteira deve ser restrita ao colaborador
    vinculado ao usuário logado (v1.3.0 — visibilidade por colaborador).

    Regra:
      - Cargos ADMIN (ADM, Franqueado) e GESTÃO (Gerente, EP) veem a
        carteira inteira  -> retorna False (sem filtro).
      - Cargos OPERACIONAIS (Hunter, Farmer, SDR, EV, EC) veem apenas
        a própria fatia    -> retorna True (filtra por usuario_id).
      - Cargo desconhecido ou ausente: por segurança, retorna True
        (filtra). Um cargo não mapeado não deve ver tudo por acidente.

    Usada pelos endpoints de dashboard/resumo do router de carteira.
    """
    if not cargo:
        return True
    if cargo in CARGOS_ADMIN or cargo in CARGOS_GESTAO:
        return False
    # Operacionais e quaisquer cargos não mapeados: filtra.
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
