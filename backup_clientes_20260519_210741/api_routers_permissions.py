"""
HIPO — Permissões por cargo (controle de acesso aos módulos).

Filosofia:
  - Cargos são strings livres em `usuarios.cargo` (VARCHAR(80), não enum).
  - Cada cargo tem um conjunto de módulos visíveis. O ADM e o Franqueado
    veem tudo; Hunter/Farmer/EP/Gerente/SDR/EV/CARTEIRA só veem 'carteira'.
  - Módulos cobrem famílias inteiras de endpoints (pex, po, bd, metas,
    carteira, usuarios).

Como aplicar nos routers:
  from routers.permissions import requer_modulo
  @router.get("/algo", dependencies=[Depends(requer_modulo("pex"))])
  async def algo(...): ...

Ou injetando junto do user:
  user=Depends(requer_modulo("pex"))

Auth e perfil próprio (/auth/*) ficam livres — todos os cargos precisam
poder fazer login, ver o próprio /me e trocar a própria senha.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from routers.auth import usuario_atual


# Cargos que veem TUDO. Permissão de admin de fato.
CARGOS_ADMIN = {"ADM", "Franqueado"}

# Cargos que veem apenas o módulo Carteira (além do perfil próprio).
# Inclui os cargos antigos do schema (SDR, EV) por compat.
CARGOS_VIEWER_CARTEIRA = {
    "Hunter", "Farmer", "EP", "Gerente",
    "SDR", "EV", "EC",
}


def modulos_do_cargo(cargo: str | None) -> set[str]:
    """
    Devolve o conjunto de módulos visíveis para o cargo informado.

    Módulos:
      - 'pex'        : PEX, Compliance Gaps
      - 'po'         : POs, reconciliação, projeção
      - 'bd'         : BD Ativados
      - 'metas'      : Configuração de metas
      - 'carteira'   : Carteira (Hunter/Farmer/Outros + upload)
      - 'usuarios'   : Gestão de usuários (futuro)
    """
    if not cargo:
        return set()
    if cargo in CARGOS_ADMIN:
        return {"pex", "po", "bd", "metas", "carteira", "usuarios"}
    if cargo in CARGOS_VIEWER_CARTEIRA:
        return {"carteira"}
    # Cargo desconhecido: nada por segurança
    return set()


def requer_modulo(modulo: str):
    """
    Dependency factory. Bloqueia o acesso se o cargo do usuário não
    inclui o módulo. Retorna o user (dict) quando autorizado.

    Uso:
      @router.get("/x")
      async def x(user=Depends(requer_modulo("pex"))):
          ...
    """
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
