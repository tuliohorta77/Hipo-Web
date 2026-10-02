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
  'telemetria' — uso do sistema e fechamento diário (Franqueado, ADM)
  'monitor'    — SÓ o painel de parede; exclusivo do cargo Monitor (conta de
                 TV). Os demais cargos chegam ao Monitor pelo 'crm' — o router
                 aceita qualquer um dos dois (requer_qualquer_modulo).
  'uc'         — SÓ a Universidade Corporativa; exclusivo do cargo UC (quem
                 estuda o conteúdo sem operar o CRM). Os demais cargos chegam
                 à UC pelo 'crm', do mesmo jeito que no Monitor.

Por que 'parceiros' NÃO é de todo mundo: cultivar a relação com o escritório
de contabilidade que indica é trabalho do EC, e a diretriz é uma tela por
função. SDR, EV e EP não trabalham carteira de parceiro — a tela na barra
deles seria ruído permanente. Gestão enxerga porque é quem remaneja carteira
quando alguém sai.

Por que 'telemetria' é só de gestão: não é sigilo, é ruído. Mostrar para o
SDR quantas ações o colega fez transforma a ferramenta em painel de vigilância
entre pares — o jeito mais rápido de a equipe parar de lançar no sistema.

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

# Conta de tela: login que existe só para deixar o Monitor aberto numa TV.
# NÃO entra em CARGOS_VALIDOS de propósito: CARGOS_VALIDOS é "gente que opera"
# (recebe a base, aparece no seletor de envolvidos, pode ser dona de
# oportunidade). A TV não é ninguém — vê o painel e mais nada.
CARGO_MONITOR = "Monitor"

# Conta de leitura da Universidade Corporativa: alguém de fora da operação
# (sócio, parceiro, candidato) que assiste às trilhas e nada mais. Mesmo
# arranjo do Monitor: fora de CARGOS_VALIDOS, porque não opera — não recebe a
# base, não é envolvido, não entra na visão do time da UC. Vê todas as
# trilhas publicadas, nenhuma como obrigatória (routers/uc.py).
CARGO_UC = "UC"

# Contas que existem para UMA tela e não são gente da operação. Ficam fora
# do seletor de envolvidos e da lista de ausentes da telemetria.
CARGOS_DE_TELA = (CARGO_MONITOR, CARGO_UC)

# Módulos que todo cargo válido enxerga.
MODULOS_BASE = {"perfil", "crm"}

# Cargos que trabalham carteira de parceiro. O EC é quem cultiva a relação;
# gestão entra porque é quem remaneja carteira quando alguém sai. Esta é
# também a lista de quem pode ser `contas.ec_responsavel_id` — validada em
# routers/crm_parceiros.py, porque CHECK de banco não enxerga cargo.
CARGOS_COM_PARCEIROS = CARGOS_GESTAO | {"EC"}


# Cargos que fatiam a base da Receita e puxam empresa para o CRM (022). E a
# tela do SDR; gestao entra porque acompanha e distribui. Restricao por
# CARGO dentro do modulo 'crm', e nao modulo novo: modulo novo so reflete
# depois de todo mundo relogar, e mexer em modulos_do_cargo quebraria os
# asserts de igualdade da suite. Mesmo arranjo do de-para de CNAEs.
CARGOS_PROSPECCAO = CARGOS_GESTAO | {"SDR"}

def modulos_do_cargo(cargo: str | None) -> set[str]:
    """Devolve o conjunto de módulos visíveis para o cargo informado."""
    if not cargo:
        return set()

    # Conta de TV: só o painel. Nem 'perfil' nem 'crm' — sem o 'crm' a API
    # barra contas, oportunidades, tarefas e relatórios no guard do router.
    if cargo == CARGO_MONITOR:
        return {"monitor"}

    # Conta da UC: só as trilhas. A tela /perfil (troca de senha) não depende
    # de módulo — vive em /auth, que é de todo usuário autenticado.
    if cargo == CARGO_UC:
        return {"uc"}

    if cargo not in CARGOS_VALIDOS:
        return set()

    modulos = set(MODULOS_BASE)

    if cargo in CARGOS_GESTAO:
        modulos.add("usuarios")
        modulos.add("telemetria")

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


async def requer_gestao(user=Depends(usuario_atual)):
    """
    Dependency: 403 para quem nao e gestao (Franqueado ou ADM).

    Existe para as escritas que NAO sao de um modulo e sim da operacao
    inteira — as metas e os feriados do Monitor. O painel e de todo mundo
    (fica numa TV); definir a meta que a equipe vai ser medida por nao e.

    Nao virou modulo novo de proposito: modulo novo so reflete depois de
    relogin, e um modulo cujo unico conteudo e "pode editar meta" seria
    cargo escrito com outro nome.
    """
    cargo = user.get("cargo")
    if cargo not in CARGOS_GESTAO:
        raise HTTPException(
            403,
            f"Cargo '{cargo or 'sem cargo'}' nao pode alterar metas e feriados. "
            f"Fale com a gestao.",
        )
    return user


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


async def requer_prospeccao(user=Depends(usuario_atual)):
    """
    Dependency: 403 para quem nao trabalha a base de prospeccao.

    Aplicada no include_router de /crm/prospeccao, ao lado do guard do
    modulo 'crm'. Ver CARGOS_PROSPECCAO.
    """
    cargo = user.get("cargo")
    if cargo not in CARGOS_PROSPECCAO:
        raise HTTPException(
            403,
            f"Cargo '{cargo or 'sem cargo'}' nao trabalha a base de prospeccao.",
        )
    return user
