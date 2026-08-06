"""
HIPO — Permissões por cargo (controle de acesso aos módulos).

Sprint 0: o legado saiu e o CRM ainda não entrou, então o único módulo
funcional é 'perfil' (troca de senha, dados do próprio usuário). Cargos
de gestão recebem também 'usuarios'.

Cargos canônicos:
  Franqueado  — gestão / master. Vê tudo. (renomear é backlog)
  ADM         — administração da operação
  EC          — Executivo de Contas (fusão de Hunter + Farmer)
  SDR         — pré-vendas
  EV          — Executivo de Vendas
  EP          — Especialista de Produto

Removidos na Sprint 0:
  Gerente     — cargo extinto; usuários com esse cargo foram desativados
  Hunter      — fundido em EC
  Farmer      — fundido em EC

Módulos:
  'perfil'    — dados do próprio usuário e troca de senha (todo cargo válido)
  'usuarios'  — gestão de usuários (Franqueado, ADM)
  'crm'       — contas, contatos e oportunidades (entra na Sprint 1)

Um cargo desconhecido ou ausente recebe conjunto vazio — nunca herda
acesso por acidente.
"""
from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException

from routers.auth import usuario_atual


# Cargos com visão de gestão: também administram usuários.
CARGOS_GESTAO = {"Franqueado", "ADM"}

# Cargos operacionais: uma tela por função (Sprint 1 em diante).
CARGOS_OPERACIONAIS = {"EC", "SDR", "EV", "EP"}

# Todos os cargos válidos do sistema.
CARGOS_VALIDOS = CARGOS_GESTAO | CARGOS_OPERACIONAIS


def modulos_do_cargo(cargo: str | None) -> set[str]:
    """Devolve o conjunto de módulos visíveis para o cargo informado."""
    if not cargo:
        return set()

    if cargo in CARGOS_GESTAO:
        return {"perfil", "usuarios"}

    if cargo in CARGOS_OPERACIONAIS:
        return {"perfil"}

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


def requer_qualquer_modulo(modulos: Iterable[str]):
    """
    Dependency factory: libera se o usuário tem QUALQUER UM dos módulos.

    Uso típico: rotas de drilldown que pertencem a um módulo mas servem à
    tela de outro. Aplicada como dependency da rota individual, sobrescreve
    o guard global do router.

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
