"""
HIPO — Scorecard da reunião contra o Roteiro de Vendas (entrega 030).

Pela TAREFA, como a transcrição (crm_agenda, 016): é a tarefa que as telas
têm na mão. Montado em main.py com o mesmo prefixo e o mesmo módulo da
agenda — é a mesma reunião, vista depois da call.

  GET    /tarefas/{id}/avaliacao                 o scorecard (qualquer um do CRM)
  POST   /tarefas/{id}/avaliacao/gerar           avalia (ou reavalia) agora
  PATCH  /tarefas/{id}/avaliacao/itens/{item}    gestão: nota de um item
  POST   /tarefas/{id}/avaliacao/validar         gestão: põe o selo
  DELETE /tarefas/{id}/avaliacao/validar         gestão: tira o selo
  GET    /roteiro/guia                           o guia rápido do roteiro (07/10/2026)

A nota da IA vale assim que sai (decisão do Tulio, 02/10). O ajuste e o
selo são da gestão — Franqueado e ADM —, e o vendedor vê os dois.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from routers.permissions import CARGOS_GESTAO
from services import coleta_avaliacao
from services import coleta_transcricao
from services import roteiro_scorecard

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────


class PontoOut(BaseModel):
    texto: str
    evidencia: str | None = None
    como_fazer: str | None = None


class ItemAvaliacaoOut(BaseModel):
    item: int
    nome: str
    etapa: str | None
    o_que_procurar: str | None
    # O critério de 0, 1 e 2 pontos, nessa ordem.
    criterios: list[str]
    # A nota que vale: a da gestão, se houver, senão a da IA.
    nota: int | None
    nota_ia: int | None
    nota_gestor: int | None
    evidencia: str | None
    justificativa: str | None
    sugestao: str | None
    # Preenchido quando a IA deu nota sem trecho que conferisse: a nota
    # foi descartada e o item conta zero até a gestão avaliar.
    descartado: str | None
    ajustada_por_nome: str | None
    ajustada_em: datetime | None


class AvaliacaoOut(BaseModel):
    reuniao_id: UUID
    tarefa_id: UUID
    # nao_elegivel | na_fila | aguardando | pronta | erro
    status: str
    motivo: str | None
    versao_roteiro: str
    nota_total: int | None
    nota_maxima: int
    # boa | media | baixa (a cor da nota na tela)
    faixa: str | None
    meta: float
    vendedor_nome: str | None
    fala_vendedor_pct: float | None
    meta_fala_pct: float
    resumo: str | None
    foco_proxima: str | None
    pontos_fortes: list[PontoOut]
    pontos_melhorar: list[PontoOut]
    modelo: str | None
    erro: str | None
    tentativas: int
    gerada_em: datetime | None
    validada: bool
    validada_por_nome: str | None
    validada_em: datetime | None
    ajustada: bool
    itens: list[ItemAvaliacaoOut]
    ia_configurada: bool
    pode_gerar: bool
    # Calculado aqui, por quem pede: a tela mostra o seletor de nota e o
    # botão Validar só para a gestão.
    pode_ajustar: bool = False


class GuiaItemOut(BaseModel):
    item: int
    nome: str
    # O critério de 2 pontos: o que o vendedor precisa fazer para gabaritar.
    vale_2: str
    fazer: str
    exemplos: list[str]
    evitar: str


class GuiaEtapaOut(BaseModel):
    nome: str
    minutos: int | None
    itens: list[GuiaItemOut]


class GuiaCertezaOut(BaseModel):
    nome: str
    sinal_baixo: str
    como_subir: str


class GuiaTresDezOut(BaseModel):
    certezas: list[GuiaCertezaOut]
    pergunta_calibracao: str
    pergunta_o_que_falta: str
    looping_maximo: int


class GuiaFechamentoOut(BaseModel):
    situacao: str
    tecnica: str
    frase: str


class GuiaRoteiroOut(BaseModel):
    versao_roteiro: str
    duracao_min: int
    meta_fala_pct: float
    nota_maxima: int
    etapas: list[GuiaEtapaOut]
    tres_dez: GuiaTresDezOut
    fechamentos: list[GuiaFechamentoOut]
    pergunta_final: str


class AjusteIn(BaseModel):
    # None desfaz o ajuste: volta a valer a nota da IA.
    nota: int | None = Field(None, ge=0, le=2)


# ── Apoio ────────────────────────────────────────────────────────────


async def _reuniao_ou_404(conn, tarefa_id: UUID) -> UUID:
    reuniao_id = await coleta_transcricao.reuniao_da_tarefa(conn, tarefa_id)
    if reuniao_id is None:
        raise HTTPException(404, "Esta tarefa não é uma reunião da agenda.")
    return reuniao_id


def _gestao(user) -> bool:
    return user.get("cargo") in CARGOS_GESTAO


def _exigir_gestao(user) -> None:
    if not _gestao(user):
        raise HTTPException(
            403, "Só a gestão (Franqueado ou ADM) ajusta e valida o scorecard.",
        )


def _saida(estado: dict, user) -> dict:
    estado["pode_ajustar"] = _gestao(user) and estado["status"] == "pronta"
    return estado


# ── Rotas ────────────────────────────────────────────────────────────


@router.get("/roteiro/guia", response_model=GuiaRoteiroOut)
async def guia_do_roteiro(user=Depends(usuario_atual)):
    """
    O script resumido do scorecard, para o vendedor ter ao lado durante a
    call: as etapas com tempo, os 10 itens com exemplo de fala, os três 10
    e as técnicas de fechamento. Igual para todo mundo do CRM; sem banco.
    """
    return roteiro_scorecard.guia_rapido()


@router.get("/tarefas/{tarefa_id}/avaliacao", response_model=AvaliacaoOut)
async def obter_avaliacao(
    tarefa_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """O scorecard da reunião: nota, itens com trecho e o resumo do coach."""
    reuniao_id = await _reuniao_ou_404(conn, tarefa_id)
    return _saida(await coleta_avaliacao.obter(conn, reuniao_id), user)


@router.post("/tarefas/{tarefa_id}/avaliacao/gerar", response_model=AvaliacaoOut)
async def gerar_avaliacao(
    tarefa_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Avalia agora, sem esperar o timer — ou de novo, depois de uma falha.

    Falha da IA NÃO é erro HTTP: volta 200 com `erro`, e a nota anterior
    (se havia) continua valendo. 409 para o que a pessoa não resolve
    clicando de novo: reunião não elegível, avaliação validada, ou outra
    avaliação da mesma reunião rodando.
    """
    reuniao_id = await _reuniao_ou_404(conn, tarefa_id)
    try:
        estado = await coleta_avaliacao.avaliar(conn, reuniao_id, user["id"])
    except coleta_avaliacao.AvaliacaoIndisponivel as e:
        raise HTTPException(409, str(e))
    except coleta_avaliacao.EmAndamento as e:
        raise HTTPException(409, str(e))
    return _saida(estado, user)


@router.patch(
    "/tarefas/{tarefa_id}/avaliacao/itens/{item}", response_model=AvaliacaoOut,
)
async def ajustar_item(
    tarefa_id: UUID,
    item: int,
    payload: AjusteIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """A gestão dá a nota de um item (0, 1 ou 2), ou desfaz com `null`."""
    _exigir_gestao(user)
    reuniao_id = await _reuniao_ou_404(conn, tarefa_id)
    try:
        estado = await coleta_avaliacao.ajustar_item(
            conn, reuniao_id, item, payload.nota, user["id"],
        )
    except coleta_avaliacao.AvaliacaoIndisponivel as e:
        raise HTTPException(409, str(e))
    return _saida(estado, user)


@router.post("/tarefas/{tarefa_id}/avaliacao/validar", response_model=AvaliacaoOut)
async def validar_avaliacao(
    tarefa_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """O selo da gestão: "li e concordo com esta avaliação"."""
    _exigir_gestao(user)
    reuniao_id = await _reuniao_ou_404(conn, tarefa_id)
    try:
        estado = await coleta_avaliacao.validar(conn, reuniao_id, user["id"], True)
    except coleta_avaliacao.AvaliacaoIndisponivel as e:
        raise HTTPException(409, str(e))
    return _saida(estado, user)


@router.delete("/tarefas/{tarefa_id}/avaliacao/validar", response_model=AvaliacaoOut)
async def desfazer_validacao(
    tarefa_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Tira o selo — o caminho para reavaliar uma reunião já validada."""
    _exigir_gestao(user)
    reuniao_id = await _reuniao_ou_404(conn, tarefa_id)
    try:
        estado = await coleta_avaliacao.validar(conn, reuniao_id, None, False)
    except coleta_avaliacao.AvaliacaoIndisponivel as e:
        raise HTTPException(409, str(e))
    return _saida(estado, user)
