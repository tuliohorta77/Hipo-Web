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
  - 'clientes' é o novo módulo de oportunidades/leads + tarefas.
"""
from __future__ import annotations

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
