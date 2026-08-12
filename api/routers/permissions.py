"""
HIPO — Permissões por cargo (controle de acesso aos módulos).

Cargos canônicos:
  Franqueado  — gestão / master. (renomear é backlog)
  ADM         — administração da operação
  EC          — Executivo de Contas (fusão de Hunter + Farmer)
  SDR         — pré-vendas
  EV          — Executivo de Vendas
  EP          — Especialista de Produto

Cargos extintos na Sprint 0: Gerente (removido), Hunter e Farmer (fundidos
em EC). Um usuário que ainda tenha um desses cargos loga mas não recebe
módulo nenhum — proposital, para não herdar acesso por acidente.

Módulos:
  'perfil'     — dados do próprio usuário e troca de senha (todo cargo válido)
  'crm'        — contas, contatos e oportunidades (todo cargo válido)
  'parceiros'  — carteira de parceiros indicadores (EC + gestão)
  'usuarios'   — gestão de usuários (Franqueado, ADM)

Por que 'parceiros' NÃO é de todo mundo: cultivar a relação com o escritório
de contabilidade que indica é trabalho do EC, e a diretriz é uma tela por
função. SDR, EV e EP não trabalham carteira de parceiro — a tela na barra
deles seria ruído permanente. Gestão enxerga porque é quem remaneja carteira
quando alguém sai.

Por que 'crm' é de todo mundo: contas e contatos são base compartilhada.
Se cada um enxergasse só a própria fatia, um usuário bateria no erro de CNPJ
duplicado sem conseguir ver o registro que causou o conflito — e cadastraria
a mesma empresa de novo com outro documento. O recorte por dono existe, mas
dentro de oportunidades (via oportunidade_envolvidos), aplicado no
repositório, não no guard de módulo.
"""
from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException

from routers.auth import usuario_atual


# Cargos com visão de gestão: também administram usuários.
CARGOS_GESTAO = {"Franqueado", "ADM"}

# Cargos operacionais: uma tela por função.
CARGOS_OPERACIONAIS = {"EC", "SDR", "EV", "EP"}

# Todos os cargos válidos do sistema.
CARGOS_VALIDOS = CARGOS_GESTAO | CARGOS_OPERACIONAIS

# Módulos que todo cargo válido enxerga.
MODULOS_BASE = {"perfil", "crm"}

# Cargos que trabalham carteira de parceiro. O EC é quem cultiva a relação;
# gestão entra porque é quem remaneja carteira quando alguém sai. Esta é
# também a lista de quem pode ser `contas.ec_responsavel_id` — validada em
# routers/crm_parceiros.py, porque CHECK de banco não enxerga cargo.
CARGOS_COM_PARCEIROS = CARGOS_GESTAO | {"EC"}


def modulos_do_cargo(cargo: str | None) -> set[str]:
    """Devolve o conjunto de módulos visíveis para o cargo informado."""
    if not cargo:
        return set()

    if cargo not in CARGOS_VALIDOS:
        return set()

    modulos = set(MODULOS_BASE)

    if cargo in CARGOS_GESTAO:
        modulos.add("usuarios")

    if cargo in CARGOS_COM_PARCEIROS:
        modulos.add("parceiros")

    return modulos


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
