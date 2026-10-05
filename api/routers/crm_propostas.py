"""
HIPO — CRM: propostas comerciais.

Uma proposta é uma VERSÃO congelada dos números de uma oportunidade, que
vira um .pptx (e, onde o servidor permite, um .pdf) a partir do modelo da
Controller MedSeg.

Decisões que este módulo materializa:

  * As regras vivem em services/proposta.py, como funções puras; o
    preenchimento do arquivo, em services/proposta_render.py. Aqui só há
    orquestração — ler o estado, validar, gravar, montar o arquivo.

  * O ARQUIVO NÃO É GUARDADO. A tabela guarda os dados; o download remonta
    a partir do modelo. Um .pptx de 16 MB por versão encheria o RDS por
    algo que se reproduz em segundos.

  * nome/e-mail/telefone do executivo e a razão social do cliente são
    COPIADOS no momento da geração. Proposta enviada não muda de conteúdo
    porque alguém trocou de telefone depois.

  * A versão é calculada no próprio INSERT, com SELECT ... FOR UPDATE na
    oportunidade. Ler o MAX antes e inserir depois abriria janela para
    duas gerações simultâneas pegarem a mesma versão — o mesmo cuidado da
    numeração das oportunidades.

042 — vários CNPJs e tabela de preço:

  * A oportunidade tem um CNPJ PRINCIPAL (oportunidades.conta_id) e pode
    ter CNPJs ADICIONAIS (oportunidade_contas). As rotas /cnpjs desta
    oportunidade vinculam e desvinculam; é o vínculo que faz a conta de
    cada CNPJ mostrar que está nesta negociação.

  * A proposta tem um item por CNPJ (proposta_itens) e uma modalidade:
    'por_vida' (vidas x valor por vida, como sempre) ou 'tabela' (faixa de
    vidas, valor sugerido e negociável). A mensalidade é a soma dos itens.

  * O download sai consolidado (todos os CNPJs, no estilo do material
    "VARIOS CNPJs") ou recortado para UM CNPJ (`?item=<id>`).

  * A tabela de preço vive no banco e é editada pela gestão
    (/tabela-precos). A proposta guarda uma cópia da tabela usada.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status as http
from pydantic import BaseModel, Field, field_validator

from database import get_conn
from routers.auth import usuario_atual
from routers.crm_oportunidades import (
    _validar_prospeccao,
    erro_conta_vinculada,
    vinculo_adicional_aberto,
)
from routers.permissions import CARGOS_GESTAO
from services import cnpj as cnpj_svc
from services import proposta as regras
from services import proposta_render as render

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class ItemIn(BaseModel):
    """Um CNPJ da proposta. A conta precisa ser da oportunidade."""
    conta_id: UUID
    vidas: int = Field(..., ge=1, le=regras.MAX_VIDAS)
    # Só vale na modalidade tabela, e é opcional: em branco, entra o valor
    # da tabela. Na modalidade por vida é ignorado (o valor é derivado).
    mensalidade: Decimal | None = Field(default=None, ge=0)


class PropostaIn(BaseModel):
    modalidade: str = Field(default="por_vida", pattern="^(por_vida|tabela)$")
    # Compatibilidade com o formulário de um CNPJ só (antes da 042): sem
    # `itens`, a proposta tem um item — o CNPJ principal com estas vidas.
    vidas: int | None = Field(default=None, ge=1, le=regras.MAX_VIDAS)
    valor_por_vida: Decimal | None = Field(default=None, gt=0)
    itens: list[ItemIn] | None = Field(default=None, max_length=regras.MAX_CNPJS)
    treinamentos: Decimal = Field(default=Decimal(0), ge=0)
    laudos: Decimal = Field(default=Decimal(0), ge=0)
    escopo: list[str] = Field(..., min_length=1)
    data_proposta: date
    validade: date
    cidade: str = Field(default=regras.CIDADE_PADRAO, min_length=1, max_length=80)
    # Quem assina. Em branco, é quem está gerando — o caso normal. O campo
    # existe porque o ADM às vezes monta a proposta para o executivo que
    # está em visita, e o slide precisa trazer o contato de quem vai
    # atender a ligação do cliente.
    executivo_id: UUID | None = None

    @field_validator("escopo")
    @classmethod
    def _escopo(cls, v: list[str]) -> list[str]:
        limpos = regras.limpar_escopo(v)
        if not limpos:
            raise ValueError("A proposta precisa de ao menos um item de escopo.")
        return limpos


class ItemOut(BaseModel):
    id: UUID | None = None
    ordem: int
    conta_id: UUID | None
    cnpj: str
    cnpj_formatado: str
    razao_social: str
    vidas: int
    mensalidade: Decimal
    valor_tabela: Decimal | None
    desconto_percentual: Decimal | None


class FaixaPreco(BaseModel):
    vidas_ate: int | None = Field(default=None, ge=1)
    tipo: str = Field(..., pattern="^(fixo|por_vida)$")
    valor: Decimal = Field(..., gt=0)


class PropostaOut(BaseModel):
    id: UUID
    oportunidade_id: UUID
    versao: int
    modalidade: str
    vidas: int
    valor_por_vida: Decimal | None
    treinamentos: Decimal
    laudos: Decimal
    # Derivados, calculados na leitura: ver a nota do schema.
    mensalidade: Decimal
    investimento: Decimal
    itens: list[ItemOut]
    tabela_preco: list[FaixaPreco] | None
    escopo: list[str]
    cidade: str
    data_proposta: date
    validade: date
    cliente_razao_social: str
    executivo_id: UUID | None
    executivo_nome: str
    executivo_email: str
    executivo_telefone: str | None
    criado_por_nome: str | None
    criado_em: object


class CnpjDaOportunidade(BaseModel):
    conta_id: UUID
    cnpj: str
    cnpj_formatado: str
    razao_social: str
    nome_fantasia: str | None
    principal: bool
    num_funcionarios: int | None
    num_funcionarios_origem: str | None
    vinculado_em: datetime | None
    vinculado_por_nome: str | None


class VincularIn(BaseModel):
    conta_id: UUID


class TabelaOut(BaseModel):
    faixas: list[FaixaPreco]
    linhas: list[str]
    rodape: str
    # True quando o banco está vazio e vale a tabela padrão do código.
    padrao: bool
    atualizado_em: datetime | None
    atualizado_por_nome: str | None
    pode_editar: bool


class TabelaIn(BaseModel):
    faixas: list[FaixaPreco] = Field(..., min_length=1, max_length=regras.MAX_FAIXAS)


class PadraoProposta(BaseModel):
    """
    O que a tela precisa para abrir o formulário já preenchido.

    Existe para o front não ter que saber as regras: escopo padrão, prazo
    de validade e dados do executivo logado vêm prontos do servidor, e o
    vendedor só ajusta o que for diferente.
    """
    escopo_padrao: list[str]
    cidade: str
    dias_validade: int
    modalidade: str
    vidas: int | None
    valor_por_vida: Decimal | None
    # Itens da última proposta (conta_id -> vidas/mensalidade): o "ajustar
    # o desconto" de uma proposta com cinco CNPJs não pode obrigar a
    # redigitar as cinco linhas.
    ultimos_itens: list[ItemOut]
    cnpjs: list[CnpjDaOportunidade]
    tabela: TabelaOut
    executivo_id: UUID
    executivo_nome: str
    executivo_email: str
    executivo_telefone: str | None
    cliente_razao_social: str
    # Duas capacidades do SERVIDOR, não do usuário: a tela avisa antes de
    # alguém preencher o formulário inteiro para descobrir no clique que
    # falta biblioteca. Ver a nota de import tardio em proposta_render.
    geracao_disponivel: bool
    pdf_disponivel: bool


# ── Helpers ──────────────────────────────────────────────────────────

def _eh_gestao(user: dict) -> bool:
    return user.get("cargo") in CARGOS_GESTAO


def _item_out(d: dict) -> dict:
    d = dict(d)
    d["cnpj_formatado"] = cnpj_svc.formatar(d["cnpj"])
    d["desconto_percentual"] = regras.desconto_percentual(
        d.get("mensalidade"), d.get("valor_tabela")
    )
    return d


def _linha(row, itens: list[dict] | None = None) -> dict:
    d = dict(row)
    escopo = d.get("escopo")
    d["escopo"] = json.loads(escopo) if isinstance(escopo, str) else (escopo or [])
    tabela = d.get("tabela_preco")
    if isinstance(tabela, str):
        tabela = json.loads(tabela)
    d["tabela_preco"] = regras.tabela_de_json(tabela) if tabela else None
    d.setdefault("modalidade", "por_vida")

    itens = list(itens or [])
    if not itens and d.get("valor_por_vida"):
        # Proposta anterior à 026 que a migration não alcançou (não
        # deveria existir): lida como um item só, sem CNPJ conhecido.
        itens = [{
            "id": None, "ordem": 1, "conta_id": None, "cnpj": "",
            "razao_social": d["cliente_razao_social"], "vidas": d["vidas"],
            "mensalidade": regras.mensalidade(d["vidas"], d["valor_por_vida"]),
            "valor_tabela": None,
        }]
    d["itens"] = [_item_out(i) for i in itens]
    mensal = regras.total_itens(itens) if itens else Decimal("0.00")
    d["mensalidade"] = mensal
    d["investimento"] = regras.investimento(mensal, d["treinamentos"], d["laudos"])
    return d


async def _itens(conn, proposta_ids: list[UUID]) -> dict[UUID, list[dict]]:
    if not proposta_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT id, proposta_id, ordem, conta_id, cnpj, razao_social, vidas,
               mensalidade, valor_tabela
          FROM proposta_itens
         WHERE proposta_id = ANY($1::uuid[])
         ORDER BY proposta_id, ordem
        """,
        proposta_ids,
    )
    por: dict[UUID, list[dict]] = {}
    for r in rows:
        d = dict(r)
        por.setdefault(d.pop("proposta_id"), []).append(d)
    return por


async def _oportunidade(conn, oportunidade_id: UUID) -> dict:
    row = await conn.fetchrow(
        """
        SELECT o.id, o.numero, o.conta_id, c.razao_social, c.cnpj
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
         WHERE o.id = $1
        """,
        oportunidade_id,
    )
    if not row:
        raise HTTPException(404, "Oportunidade não encontrada.")
    return dict(row)


async def _cnpjs(conn, oportunidade_id: UUID) -> list[dict]:
    """O principal primeiro, depois os adicionais na ordem em que entraram."""
    rows = await conn.fetch(
        """
        SELECT c.id AS conta_id, c.cnpj, c.razao_social, c.nome_fantasia,
               TRUE AS principal, c.num_funcionarios, c.num_funcionarios_origem,
               NULL::timestamptz AS vinculado_em, NULL::text AS vinculado_por_nome,
               0 AS ordem, NULL::timestamptz AS ordem_tempo
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
         WHERE o.id = $1
        UNION ALL
        SELECT c.id, c.cnpj, c.razao_social, c.nome_fantasia,
               FALSE, c.num_funcionarios, c.num_funcionarios_origem,
               oc.criado_em, u.nome, 1, oc.criado_em
          FROM oportunidade_contas oc
          JOIN contas c        ON c.id = oc.conta_id
          LEFT JOIN usuarios u ON u.id = oc.criado_por
         WHERE oc.oportunidade_id = $1 AND oc.removido_em IS NULL
         ORDER BY ordem, ordem_tempo
        """,
        oportunidade_id,
    )
    return [
        {**{k: v for k, v in dict(r).items() if k not in ("ordem", "ordem_tempo")},
         "cnpj_formatado": cnpj_svc.formatar(r["cnpj"])}
        for r in rows
    ]


async def _tabela_vigente(conn) -> tuple[list[dict], dict]:
    """
    (faixas normalizadas, metadados). Banco vazio = tabela padrão do código:
    a modalidade tabela nunca fica sem preço para sugerir.
    """
    rows = await conn.fetch(
        """
        SELECT f.vidas_ate, f.tipo, f.valor, f.atualizado_em, u.nome AS atualizado_por_nome
          FROM tabela_preco_faixas f
          LEFT JOIN usuarios u ON u.id = f.atualizado_por
        """
    )
    if not rows:
        return regras.normalizar_tabela(regras.TABELA_PADRAO), {
            "padrao": True, "atualizado_em": None, "atualizado_por_nome": None,
        }
    faixas = regras.normalizar_tabela([dict(r) for r in rows])
    mais_nova = max(rows, key=lambda r: r["atualizado_em"])
    return faixas, {
        "padrao": False,
        "atualizado_em": mais_nova["atualizado_em"],
        "atualizado_por_nome": mais_nova["atualizado_por_nome"],
    }


def _tabela_out(faixas: list[dict], meta: dict, user: dict) -> dict:
    return {
        "faixas": faixas,
        "linhas": regras.linhas_tabela(faixas),
        "rodape": regras.rodape_tabela(faixas),
        "pode_editar": _eh_gestao(user),
        **meta,
    }


async def _executivo(conn, executivo_id: UUID | None, user: dict) -> dict:
    """
    Dados de contato de quem assina a proposta.

    Sem executivo_id, é o usuário logado — e aí nem consulta o banco, já
    que `usuario_atual` traz a linha inteira.
    """
    if executivo_id is None or str(executivo_id) == str(user["id"]):
        return {
            "id": user["id"],
            "nome": user["nome"],
            "email": user["email"],
            "telefone": user.get("telefone"),
        }
    row = await conn.fetchrow(
        "SELECT id, nome, email, telefone FROM usuarios WHERE id = $1 AND ativo",
        executivo_id,
    )
    if not row:
        raise HTTPException(422, "Executivo não encontrado ou inativo.")
    return dict(row)


async def _buscar(conn, proposta_id: UUID) -> dict:
    row = await conn.fetchrow(
        """
        SELECT p.*, u.nome AS criado_por_nome, o.numero AS oportunidade_numero
          FROM propostas p
          LEFT JOIN usuarios u     ON u.id = p.criado_por
          JOIN oportunidades o     ON o.id = p.oportunidade_id
         WHERE p.id = $1
        """,
        proposta_id,
    )
    if not row:
        raise HTTPException(404, "Proposta não encontrada.")
    itens = (await _itens(conn, [proposta_id])).get(proposta_id, [])
    return _linha(row, itens)


def _montar_pptx(proposta: dict, item: dict | None = None) -> bytes:
    """
    Consolidada (item=None): todos os CNPJs, uma linha por CNPJ na lista.
    Por CNPJ: cliente, vidas e mensalidade daquele CNPJ, sem a lista de
    CNPJs e sem treinamentos/laudos (que são do negócio inteiro).
    """
    modalidade = proposta["modalidade"]
    faixas = proposta["tabela_preco"] or regras.TABELA_PADRAO
    itens = proposta["itens"]
    if item is None:
        cliente = proposta["cliente_razao_social"]
        vidas = proposta["vidas"]
        mensal = proposta["mensalidade"]
        consolidada = True
    else:
        cliente = item["razao_social"]
        vidas = item["vidas"]
        mensal = Decimal(str(item["mensalidade"]))
        consolidada = False

    linhas = regras.linhas_da_lista(
        modalidade=modalidade, escopo=proposta["escopo"], itens=itens,
        treinamentos=proposta["treinamentos"], laudos=proposta["laudos"],
        consolidada=consolidada,
    )
    # Proposta gravada passou na validação, então cabe; o "or" mínimo é só
    # para nunca recusar o download de uma versão já enviada.
    escala = (regras.escala_da_lista(linhas, regras.CAPACIDADE_LINHAS[modalidade])
              or regras.ESCALA_MINIMA)
    faixas_linhas = regras.linhas_tabela(faixas)
    escala_faixas = (regras.escala_da_lista(faixas_linhas, regras.CAPACIDADE_LINHAS["faixas"])
                     or regras.ESCALA_MINIMA)

    subs = regras.substituicoes(
        cliente=cliente,
        vidas=vidas,
        valor_por_vida=proposta["valor_por_vida"],
        treinamentos=proposta["treinamentos"],
        laudos=proposta["laudos"],
        executivo_nome=proposta["executivo_nome"],
        executivo_email=proposta["executivo_email"],
        executivo_telefone=proposta["executivo_telefone"],
        data_proposta=proposta["data_proposta"],
        validade=proposta["validade"],
        cidade=proposta["cidade"],
        mensal=mensal,
        sem_extras=not consolidada,
        faixas=faixas,
    )
    return render.montar_pptx(
        subs, linhas, modalidade=modalidade, faixas=faixas_linhas,
        escala_escopo=escala, escala_faixas=escala_faixas,
    )


# ── Tabela de preço ──────────────────────────────────────────────────

@router.get("/tabela-precos", response_model=TabelaOut)
async def tabela_precos(conn=Depends(get_conn), user=Depends(usuario_atual)):
    """A tabela vigente, já com as linhas como saem no slide."""
    faixas, meta = await _tabela_vigente(conn)
    return _tabela_out(faixas, meta, user)


@router.put("/tabela-precos", response_model=TabelaOut)
async def salvar_tabela_precos(
    payload: TabelaIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Substitui a tabela inteira. Só gestão: preço é decisão comercial, e a
    tabela vale para toda proposta nova de todo vendedor.

    Propostas já geradas não mudam — cada uma guardou a cópia da tabela
    que usou.
    """
    if not _eh_gestao(user):
        raise HTTPException(403, "Só a gestão altera a tabela de preços.")
    try:
        faixas = regras.normalizar_tabela([f.model_dump() for f in payload.faixas])
    except regras.PropostaInvalida as erro:
        raise HTTPException(422, str(erro))

    async with conn.transaction():
        await conn.execute("DELETE FROM tabela_preco_faixas")
        for f in faixas:
            await conn.execute(
                """
                INSERT INTO tabela_preco_faixas (vidas_ate, tipo, valor, atualizado_por)
                VALUES ($1, $2, $3, $4)
                """,
                f["vidas_ate"], f["tipo"], f["valor"], user["id"],
            )
    faixas, meta = await _tabela_vigente(conn)
    return _tabela_out(faixas, meta, user)


# ── CNPJs da oportunidade ────────────────────────────────────────────

@router.get("/oportunidades/{oportunidade_id}/cnpjs",
            response_model=list[CnpjDaOportunidade])
async def listar_cnpjs(
    oportunidade_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    await _oportunidade(conn, oportunidade_id)
    return await _cnpjs(conn, oportunidade_id)


@router.post("/oportunidades/{oportunidade_id}/cnpjs",
             response_model=list[CnpjDaOportunidade],
             status_code=http.HTTP_201_CREATED)
async def vincular_cnpj(
    oportunidade_id: UUID,
    payload: VincularIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Põe mais um CNPJ nesta negociação.

    Recusa (com o motivo) quando a conta:
      * já é a principal desta oportunidade, ou já está na lista;
      * está desativada, ou bloqueada para prospecção;
      * já está em OUTRA oportunidade aberta — como principal ou como
        adicional. Duas negociações do mesmo CNPJ dividiriam o ticket.
    """
    opp = await _oportunidade(conn, oportunidade_id)
    conta = await conn.fetchrow(
        "SELECT id, razao_social, ativo FROM contas WHERE id = $1", payload.conta_id
    )
    if not conta:
        raise HTTPException(422, "Conta não encontrada.")
    if not conta["ativo"]:
        raise HTTPException(422, f"{conta['razao_social']} está desativada.")
    if payload.conta_id == opp["conta_id"]:
        raise HTTPException(422, "Este é o CNPJ principal da oportunidade.")
    await _validar_prospeccao(conn, payload.conta_id)

    vinculo = await vinculo_adicional_aberto(conn, payload.conta_id)
    if vinculo is not None:
        if vinculo["id"] == oportunidade_id:
            raise HTTPException(422, "Este CNPJ já está nesta oportunidade.")
        raise erro_conta_vinculada(vinculo)

    propria = await conn.fetchrow(
        """
        SELECT id, numero FROM oportunidades
         WHERE conta_id = $1 AND status IN ('ativa', 'suspensa') AND id <> $2
         ORDER BY criado_em LIMIT 1
        """,
        payload.conta_id, oportunidade_id,
    )
    if propria is not None:
        raise HTTPException(
            409,
            detail={
                "erro": "conta_com_oportunidade_propria",
                "mensagem": (
                    f"{conta['razao_social']} tem a oportunidade "
                    f"{propria['numero']} aberta. Finalize ou cancele aquela "
                    "antes de trazer o CNPJ para esta negociação."
                ),
                "oportunidade_id": str(propria["id"]),
                "numero": propria["numero"],
            },
        )

    async with conn.transaction():
        await conn.execute(
            "SELECT id FROM oportunidades WHERE id = $1 FOR UPDATE", oportunidade_id
        )
        await conn.execute(
            """
            INSERT INTO oportunidade_contas (oportunidade_id, conta_id, criado_por)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            oportunidade_id, payload.conta_id, user["id"],
        )
        await conn.execute(
            "UPDATE oportunidades SET atualizado_em = NOW() WHERE id = $1",
            oportunidade_id,
        )
    return await _cnpjs(conn, oportunidade_id)


@router.delete("/oportunidades/{oportunidade_id}/cnpjs/{conta_id}",
               response_model=list[CnpjDaOportunidade])
async def desvincular_cnpj(
    oportunidade_id: UUID,
    conta_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Tira o CNPJ da negociação. Lógico: a conta guarda no histórico que
    esteve aqui. Propostas já geradas não mudam (cada uma tem a sua cópia).
    """
    opp = await _oportunidade(conn, oportunidade_id)
    if conta_id == opp["conta_id"]:
        raise HTTPException(422, "O CNPJ principal não sai da oportunidade.")
    feito = await conn.fetchval(
        """
        UPDATE oportunidade_contas
           SET removido_em = NOW(), removido_por = $3
         WHERE oportunidade_id = $1 AND conta_id = $2 AND removido_em IS NULL
        RETURNING id
        """,
        oportunidade_id, conta_id, user["id"],
    )
    if not feito:
        raise HTTPException(404, "Este CNPJ não está nesta oportunidade.")
    await conn.execute(
        "UPDATE oportunidades SET atualizado_em = NOW() WHERE id = $1", oportunidade_id
    )
    return await _cnpjs(conn, oportunidade_id)


# ── Padrões do formulário ────────────────────────────────────────────

@router.get("/oportunidades/{oportunidade_id}/proposta-padrao",
            response_model=PadraoProposta)
async def padrao(
    oportunidade_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Formulário pré-preenchido: escopo padrão, contato do usuário logado,
    cliente da oportunidade, CNPJs, tabela vigente e a última proposta como
    ponto de partida.

    `geracao_disponivel` e `pdf_disponivel` são lidos do servidor, não
    assumidos: a tela avisa (e desliga o botão) onde falta python-pptx ou
    LibreOffice, em vez de oferecer um download que só falharia depois do
    clique — com o formulário todo preenchido.
    """
    opp = await _oportunidade(conn, oportunidade_id)

    # Repetir a última proposta é o caso comum de "ajustar o desconto":
    # muda um valor, o resto continua igual.
    ultima = await conn.fetchrow(
        """
        SELECT id, modalidade, vidas, valor_por_vida FROM propostas
         WHERE oportunidade_id = $1
         ORDER BY versao DESC LIMIT 1
        """,
        oportunidade_id,
    )
    ultimos = []
    if ultima:
        ultimos = [_item_out(i) for i in
                   (await _itens(conn, [ultima["id"]])).get(ultima["id"], [])]

    faixas, meta = await _tabela_vigente(conn)
    return {
        "escopo_padrao": regras.ESCOPO_PADRAO,
        "cidade": regras.CIDADE_PADRAO,
        "dias_validade": regras.DIAS_VALIDADE_PADRAO,
        "modalidade": ultima["modalidade"] if ultima else regras.MODALIDADE_PADRAO,
        "vidas": ultima["vidas"] if ultima else None,
        "valor_por_vida": ultima["valor_por_vida"] if ultima else None,
        "ultimos_itens": ultimos,
        "cnpjs": await _cnpjs(conn, oportunidade_id),
        "tabela": _tabela_out(faixas, meta, user),
        "executivo_id": user["id"],
        "executivo_nome": user["nome"],
        "executivo_email": user["email"],
        "executivo_telefone": user.get("telefone"),
        "cliente_razao_social": opp["razao_social"],
        "geracao_disponivel": render.pptx_disponivel(),
        "pdf_disponivel": render.libreoffice_disponivel() is not None,
    }


# ── Leitura ──────────────────────────────────────────────────────────

@router.get("/oportunidades/{oportunidade_id}/propostas",
            response_model=list[PropostaOut])
async def listar(
    oportunidade_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Versões da oportunidade, da mais nova para a mais antiga."""
    rows = await conn.fetch(
        """
        SELECT p.*, u.nome AS criado_por_nome
          FROM propostas p
          LEFT JOIN usuarios u ON u.id = p.criado_por
         WHERE p.oportunidade_id = $1
         ORDER BY p.versao DESC
        """,
        oportunidade_id,
    )
    itens = await _itens(conn, [r["id"] for r in rows])
    return [_linha(r, itens.get(r["id"], [])) for r in rows]


# ── Criação ──────────────────────────────────────────────────────────

@router.post("/oportunidades/{oportunidade_id}/propostas",
             response_model=PropostaOut, status_code=http.HTTP_201_CREATED)
async def criar(
    oportunidade_id: UUID,
    payload: PropostaIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Cria a próxima versão da proposta.

    A mensalidade calculada aqui (soma dos CNPJs) também atualiza
    `valor_mensalidade` da oportunidade: o funil soma ticket, e uma
    proposta enviada por R$ 1.200 com o funil marcando R$ 900 faz a
    previsão do mês mentir. Só sobe o valor da proposta mais nova —
    versões antigas não reescrevem o funil.
    """
    opp = await _oportunidade(conn, oportunidade_id)
    executivo = await _executivo(conn, payload.executivo_id, user)
    modalidade = payload.modalidade

    # Os CNPJs que podem entrar: o principal e os adicionais vigentes.
    disponiveis = {c["conta_id"]: c for c in await _cnpjs(conn, oportunidade_id)}

    if payload.itens is None:
        if payload.vidas is None:
            raise HTTPException(422, "Informe as vidas ou os CNPJs da proposta.")
        entrada = [ItemIn(conta_id=opp["conta_id"], vidas=payload.vidas)]
    else:
        entrada = payload.itens
    if not entrada:
        raise HTTPException(422, "A proposta precisa de pelo menos um CNPJ.")

    itens = []
    for i, it in enumerate(entrada, start=1):
        conta = disponiveis.get(it.conta_id)
        if conta is None:
            raise HTTPException(
                422,
                "Um dos CNPJs não está vinculado a esta oportunidade. "
                "Adicione-o na lista de CNPJs antes de gerar.",
            )
        itens.append({
            "ordem": i, "conta_id": it.conta_id, "cnpj": conta["cnpj"],
            "razao_social": conta["razao_social"], "vidas": it.vidas,
            "mensalidade": it.mensalidade,
        })

    faixas = None
    if modalidade == "tabela":
        faixas, _ = await _tabela_vigente(conn)
    valor_por_vida = payload.valor_por_vida if modalidade == "por_vida" else None

    try:
        itens = regras.calcular_itens(
            modalidade=modalidade, itens=itens,
            valor_por_vida=valor_por_vida, faixas=faixas,
        )
        regras.validar(
            vidas=regras.vidas_itens(itens),
            # validar() é da modalidade por vida; na tabela o valor por
            # vida não existe e a regra correspondente já passou acima.
            valor_por_vida=valor_por_vida or Decimal(1),
            treinamentos=payload.treinamentos,
            laudos=payload.laudos,
            escopo=payload.escopo,
            data_proposta=payload.data_proposta,
            validade=payload.validade,
        )
        regras.validar_itens(
            modalidade=modalidade, itens=itens, valor_por_vida=valor_por_vida,
            escopo=payload.escopo, treinamentos=payload.treinamentos,
            laudos=payload.laudos,
        )
    except regras.PropostaInvalida as erro:
        raise HTTPException(422, str(erro))

    vidas_total = regras.vidas_itens(itens)
    mensal_total = regras.total_itens(itens)

    async with conn.transaction():
        # Trava a oportunidade: duas gerações simultâneas na mesma
        # oportunidade viriam a disputar o mesmo número de versão, e o
        # UNIQUE derrubaria a segunda com erro de banco em vez de
        # simplesmente numerar 2.
        await conn.execute(
            "SELECT id FROM oportunidades WHERE id = $1 FOR UPDATE",
            oportunidade_id,
        )
        proxima = await conn.fetchval(
            "SELECT COALESCE(MAX(versao), 0) + 1 FROM propostas WHERE oportunidade_id = $1",
            oportunidade_id,
        )
        row = await conn.fetchrow(
            """
            INSERT INTO propostas (
                oportunidade_id, versao, vidas, valor_por_vida, treinamentos,
                laudos, escopo, cidade, data_proposta, validade,
                cliente_razao_social, executivo_id, executivo_nome,
                executivo_email, executivo_telefone, criado_por,
                modalidade, tabela_preco
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18::jsonb)
            RETURNING *
            """,
            oportunidade_id, proxima, vidas_total, valor_por_vida,
            payload.treinamentos, payload.laudos, json.dumps(payload.escopo),
            payload.cidade.strip(), payload.data_proposta, payload.validade,
            opp["razao_social"], executivo["id"], executivo["nome"],
            executivo["email"], executivo.get("telefone"), user["id"],
            modalidade,
            json.dumps(regras.tabela_para_json(faixas)) if faixas else None,
        )

        gravados = []
        for it in itens:
            gravado = await conn.fetchrow(
                """
                INSERT INTO proposta_itens (
                    proposta_id, ordem, conta_id, cnpj, razao_social, vidas,
                    mensalidade, valor_tabela
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, ordem, conta_id, cnpj, razao_social, vidas,
                          mensalidade, valor_tabela
                """,
                row["id"], it["ordem"], it["conta_id"], it["cnpj"],
                it["razao_social"], it["vidas"], it["mensalidade"],
                it["valor_tabela"],
            )
            gravados.append(dict(gravado))

        await conn.execute(
            """
            UPDATE oportunidades
               SET valor_mensalidade = $2, atualizado_em = NOW()
             WHERE id = $1
            """,
            oportunidade_id,
            mensal_total,
        )

    d = _linha(row, gravados)
    d["criado_por_nome"] = user["nome"]
    return d


# ── Download ─────────────────────────────────────────────────────────

@router.get("/propostas/{proposta_id}/arquivo")
async def baixar(
    proposta_id: UUID,
    formato: str = Query("pptx", pattern="^(pptx|pdf)$"),
    item: UUID | None = Query(None, description="Item (CNPJ) para a proposta de um CNPJ só"),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Remonta o arquivo a partir do modelo e devolve para download.

    Sem `item`: a proposta consolidada, com todos os CNPJs. Com `item`: a
    proposta só daquele CNPJ — cliente, vidas e mensalidade dele.

    Erro de modelo ou de conversão vira 503 com a mensagem pronta para a
    tela — é falha de ambiente do servidor, não pedido inválido, e o
    vendedor precisa saber que o PPTX continua funcionando.
    """
    proposta = await _buscar(conn, proposta_id)

    escolhido = None
    if item is not None:
        escolhido = next((i for i in proposta["itens"] if i["id"] == item), None)
        if escolhido is None:
            raise HTTPException(404, "Este CNPJ não faz parte desta proposta.")

    numero = await conn.fetchval(
        "SELECT numero FROM oportunidades WHERE id = $1",
        proposta["oportunidade_id"],
    )

    try:
        pptx = _montar_pptx(proposta, escolhido)
    except (render.ModeloIndisponivel, render.BibliotecaIndisponivel) as erro:
        raise HTTPException(503, str(erro))

    if formato == "pptx":
        corpo = pptx
        tipo = ("application/vnd.openxmlformats-officedocument."
                "presentationml.presentation")
    else:
        try:
            corpo = render.para_pdf(pptx)
        except render.PdfIndisponivel as erro:
            raise HTTPException(503, str(erro))
        tipo = "application/pdf"

    nome = regras.nome_do_arquivo(
        numero or "PROPOSTA",
        escolhido["razao_social"] if escolhido else proposta["cliente_razao_social"],
        proposta["versao"], formato,
        cnpj=escolhido["cnpj"] if escolhido else None,
    )
    return Response(
        content=corpo,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
