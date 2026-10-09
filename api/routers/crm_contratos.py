"""
HIPO — CRM: contrato com assinatura eletrônica pela Autentique (entrega 053).

O contrato nasce de uma VERSÃO APROVADA da proposta. O EV abre "Enviar para
assinatura" na versão, confere os quatro signatários (contratante,
testemunha da contratante, contratada, testemunha da contratada), vê a
prévia do PDF e envia. Daí em diante o estado anda sozinho: o webhook da
Autentique (routers/webhooks.py) e o timer de sincronização
(scripts/sincronizar_contratos.py) leem o documento pela API e atualizam a
situação de cada um.

Regras puras em services/contrato.py; modelo e PDF em
services/contrato_render.py; API da Autentique em services/autentique.py.
Aqui só há orquestração.

DECISÕES

  * Só registra e avisa. Contrato assinado por todos guarda o PDF assinado
    e abre uma TAREFA para o executivo da proposta finalizar a oportunidade
    — o desfecho continua sendo dele (decisão do Tulio, 08/10/2026).
    Recusa também abre tarefa. O envio vira tarefa concluída, como o e-mail.

  * Quem assina pela contratada vem do .env (CONTRATO_CONTRATADA_*), não da
    tela: é sempre o CEO, e um campo editável seria um jeito de mandar o
    contrato para a pessoa errada sem ninguém notar.

  * Um contrato em andamento por oportunidade (índice único parcial). Para
    mandar outra versão, cancela-se a anterior — que fica bloqueada na
    Autentique, para ninguém assinar o contrato velho.

  * Nada é gravado se a Autentique recusar o envio. Se o banco falhar depois
    de a Autentique aceitar, o documento é cancelado lá (melhor esforço):
    contrato que existe na Autentique e não existe no HIPO é contrato que
    ninguém acompanha.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status as http
from pydantic import BaseModel, Field

from config import settings
from database import get_conn
from routers.auth import usuario_atual
from routers.crm_propostas import _buscar as buscar_proposta
from routers.crm_tarefas import (
    TarefaDeFinalizacao,
    inserir_tarefa,
    inserir_tarefa_concluida,
    registrar_no_comite,
)
from routers.permissions import CARGOS_GESTAO
from services import anexo as s3
from services import autentique
from services import cnpj as cnpj_svc
from services import contrato as regras
from services import contrato_render as render
from services import email_comercial
from services import gmail
from services.instancia import empresa_sigla
from services.oportunidade import STATUS_ABERTOS

log = logging.getLogger("hipo.contratos")
router = APIRouter()

FUSO = ZoneInfo("America/Sao_Paulo")


# ── Schemas ──────────────────────────────────────────────────────────

class SignatarioIn(BaseModel):
    papel: str = Field(..., pattern="^(contratante|testemunha_contratante|testemunha_contratada)$")
    nome: str = Field(..., max_length=150)
    email: str = Field(..., max_length=150)
    # De onde veio, quando veio do cadastro. Só para a trilha: o que vale é
    # nome e e-mail, que a pessoa pode ter corrigido na tela.
    contato_id: UUID | None = None
    usuario_id: UUID | None = None


class PreviaIn(BaseModel):
    # 055: qual grupo de CNPJ (raiz) vira este contrato. Em branco, o grupo
    # do CNPJ principal da oportunidade.
    raiz_cnpj: str | None = Field(default=None, pattern=r"^\d{8}$")
    data_contrato: date | None = None
    inicio_vigencia: date | None = None
    dia_vencimento: int = Field(default=regras.DIA_VENCIMENTO_PADRAO, ge=1,
                                le=regras.DIA_VENCIMENTO_MAX)
    # 055: serviços além do básico (Cláusula 2, itens 2.7 em diante).
    servicos: list[str] = Field(default_factory=list, max_length=len(regras.SERVICOS_EXTRAS))
    servicos_livres: list[str] = Field(default_factory=list,
                                       max_length=regras.MAX_SERVICOS_LIVRES)


class ContratoIn(PreviaIn):
    # A contratada NÃO vem da tela: é o CEO, do .env (ver cabeçalho).
    signatarios: list[SignatarioIn] = Field(..., min_length=3, max_length=3)


class CancelarIn(BaseModel):
    motivo: str = Field(..., min_length=3, max_length=regras.MAX_MOTIVO)


class SignatarioOut(BaseModel):
    id: UUID
    ordem: int
    papel: str
    papel_rotulo: str
    nome: str
    email: str
    acao: str
    situacao: str
    visualizado_em: datetime | None
    assinado_em: datetime | None
    recusado_em: datetime | None
    motivo_recusa: str | None
    reenviado_em: datetime | None
    da_vez: bool


class EventoOut(BaseModel):
    id: UUID
    tipo: str
    origem: str
    descricao: str | None
    usuario_nome: str | None
    criado_em: datetime


class CnpjContratoOut(BaseModel):
    cnpj: str
    cnpj_formatado: str
    razao_social: str
    vidas: int
    mensalidade: Decimal


class ContratoRefOut(BaseModel):
    id: UUID
    versao: int
    data_contrato: date
    oportunidade_numero: str | None = None


class ContratoOut(BaseModel):
    id: UUID
    oportunidade_id: UUID
    proposta_id: UUID
    proposta_versao: int
    versao: int
    status: str
    sandbox: bool
    nome_documento: str
    data_contrato: date
    inicio_vigencia: date
    dia_vencimento: int
    hash_original: str
    tem_assinado: bool
    assinado_em: datetime | None
    recusado_em: datetime | None
    cancelado_em: datetime | None
    cancelado_por_nome: str | None
    motivo_cancelamento: str | None
    sincronizado_em: datetime | None
    sincronizacao_erro: str | None
    criado_por_nome: str | None
    criado_em: datetime
    signatarios: list[SignatarioOut]
    eventos: list[EventoOut]
    assinados: int
    total_signatarios: int
    proximo_nome: str | None
    pode_cancelar: bool
    # 054: aviso ao faturamento, contratos e ADM.
    aviso_enviado_em: datetime | None = None
    aviso_para: list[str] | None = None
    aviso_remetente: str | None = None
    aviso_erro: str | None = None
    pode_reenviar_aviso: bool = False
    # 055: grupo de CNPJ, serviços e substituição.
    raiz_cnpj: str | None = None
    contratante_razao_social: str | None = None
    cnpjs: list[CnpjContratoOut] = []
    servicos: list[str] = []
    servicos_livres: list[str] = []
    substitui: list[ContratoRefOut] = []
    substituido_por_versao: int | None = None
    substituido_em: datetime | None = None


class SituacaoOut(BaseModel):
    configurado: bool
    problemas: list[str]
    sandbox: bool
    previa_disponivel: bool
    # 054: para quem vai o aviso de contrato assinado. Vazio = desligado.
    aviso_destinatarios: list[str] = []


class PessoaOut(BaseModel):
    id: UUID
    nome: str
    email: str | None
    detalhe: str | None


class ServicoOut(BaseModel):
    chave: str
    texto: str


class GrupoOut(BaseModel):
    """Um contrato possível: os CNPJs de uma raiz (matriz + filiais)."""
    raiz: str
    principal: bool
    contratante_razao_social: str
    contratante_cnpj: str
    conta_id: UUID | None
    endereco: str
    pendencias_endereco: list[str]
    cnpjs: list[CnpjContratoOut]
    linhas_preco: list[str]
    contrato_em_aberto_id: UUID | None
    substitui: list[ContratoRefOut]


class PadraoOut(BaseModel):
    proposta_id: UUID
    proposta_versao: int
    aprovada: bool
    oportunidade_aberta: bool
    cliente_razao_social: str
    cliente_cnpj: str
    endereco: str
    pendencias_endereco: list[str]
    conta_id: UUID
    contratada_nome: str
    contratada_email: str
    data_contrato: date
    inicio_vigencia: date
    dia_vencimento: int
    contatos: list[PessoaOut]
    usuarios: list[PessoaOut]
    sugestao_contratante_id: UUID | None
    sugestao_testemunha_contratada_id: UUID | None
    contrato_em_aberto_id: UUID | None
    linhas_preco: list[str]
    # 055
    grupos: list[GrupoOut]
    servicos_catalogo: list[ServicoOut]
    servicos_sugeridos: list[str]


# ── Helpers ──────────────────────────────────────────────────────────

def _hoje() -> date:
    return datetime.now(FUSO).date()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _eh_gestao(user: dict) -> bool:
    return user.get("cargo") in CARGOS_GESTAO


async def _contexto(conn, proposta_id: UUID) -> tuple[dict, dict, dict]:
    """(proposta, oportunidade, conta principal)."""
    proposta = await buscar_proposta(conn, proposta_id)
    opp = await conn.fetchrow(
        "SELECT id, numero, status, conta_id FROM oportunidades WHERE id = $1",
        proposta["oportunidade_id"],
    )
    conta = await conn.fetchrow(
        """
        SELECT id, razao_social, cnpj, cep, logradouro, numero, complemento,
               bairro, cidade, uf
          FROM contas WHERE id = $1
        """,
        opp["conta_id"],
    )
    return proposta, dict(opp), dict(conta)


def _exigir_enviavel(proposta: dict, opp: dict) -> None:
    if not proposta.get("aprovada_em"):
        raise HTTPException(
            422, "Aprove esta versão da proposta antes de mandar o contrato: "
                 "o contrato sai com os números dela.",
        )
    if opp["status"] not in STATUS_ABERTOS:
        raise HTTPException(
            422, "Esta oportunidade já foi finalizada; não dá para mandar contrato.",
        )


def _datas(payload, hoje: date | None = None) -> tuple[date, date, int]:
    data_contrato = payload.data_contrato or (hoje or _hoje())
    inicio = payload.inicio_vigencia or regras.inicio_vigencia_padrao(data_contrato)
    try:
        regras.validar_datas(data_contrato, inicio, payload.dia_vencimento)
    except regras.ContratoInvalido as e:
        raise HTTPException(422, str(e))
    return data_contrato, inicio, payload.dia_vencimento


_COLUNAS_CONTA = """id, razao_social, cnpj, cep, logradouro, numero, complemento,
                   bairro, cidade, uf"""


async def _grupo(conn, proposta: dict, opp: dict, raiz: str | None) -> dict:
    """
    O grupo de CNPJs (uma raiz) que vira este contrato, com a conta da
    contratante (para o endereço) e os endereços das demais (Anexo 1).
    """
    itens = proposta.get("itens") or []
    grupos = regras.agrupar_itens(itens)
    if not grupos:
        raise HTTPException(422, "Esta proposta não tem CNPJ.")
    principal = await conn.fetchval("SELECT cnpj FROM contas WHERE id = $1", opp["conta_id"])
    raiz_principal = regras.raiz(principal)
    if raiz is None:
        grupo = next((g for g in grupos if g["raiz"] == raiz_principal), grupos[0])
    else:
        try:
            grupo = regras.grupo_da_raiz(itens, raiz)
        except regras.ContratoInvalido as e:
            raise HTTPException(422, str(e))

    contas_ids = [i["conta_id"] for i in grupo["itens"] if i.get("conta_id")]
    rows = await conn.fetch(
        f"SELECT {_COLUNAS_CONTA} FROM contas WHERE id = ANY($1::uuid[])", contas_ids,
    )
    por_id = {r["id"]: dict(r) for r in rows}
    contratante = grupo["contratante"]
    conta = por_id.get(contratante.get("conta_id")) or {
        "id": None, "razao_social": contratante["razao_social"], "cnpj": contratante["cnpj"],
    }
    # Snapshot da proposta vence o cadastro na razão social: o contrato sai
    # com o nome que foi negociado.
    conta = {**conta, "razao_social": contratante["razao_social"],
             "cnpj": cnpj_svc.normalizar(contratante["cnpj"])}
    enderecos = {}
    for i in grupo["itens"][1:]:
        c = por_id.get(i.get("conta_id"))
        if c and not regras.pendencias_endereco(c):
            enderecos[cnpj_svc.normalizar(i["cnpj"])] = regras.endereco_formatado(c)
    return {
        **grupo,
        "conta": conta,
        "enderecos": enderecos,
        "principal": grupo["raiz"] == raiz_principal,
    }


async def _substituiveis(conn, raiz: str, excluir: UUID | None = None) -> list[dict]:
    """Os contratos ASSINADOS desta raiz (de qualquer oportunidade)."""
    rows = await conn.fetch(
        """
        SELECT k.id, k.versao, k.data_contrato, o.numero AS oportunidade_numero
          FROM contratos k
          JOIN oportunidades o ON o.id = k.oportunidade_id
         WHERE k.raiz_cnpj = $1 AND k.status = 'assinado'
           AND ($2::uuid IS NULL OR k.id <> $2)
         ORDER BY k.data_contrato, k.versao
        """,
        raiz, excluir,
    )
    return [dict(r) for r in rows]


def _campos(proposta: dict, grupo: dict, data_contrato: date, inicio: date, dia: int,
            servicos: list[str], livres: list[str],
            substituidos: list[dict]) -> tuple[dict, dict]:
    conta = grupo["conta"]
    faltam = regras.pendencias_endereco(conta)
    if faltam:
        raise HTTPException(
            422, f"Complete o endereço de {conta['razao_social']} antes do contrato "
                 "(falta: " + ", ".join(faltam) + "). A contratante é qualificada com ele.",
        )
    try:
        return regras.campos(
            proposta=proposta, conta=conta, itens_grupo=grupo["itens"],
            data_contrato=data_contrato, inicio_vigencia=inicio, dia_vencimento=dia,
            com_extras=grupo["principal"], servicos=servicos, servicos_livres=livres,
            enderecos=grupo["enderecos"], substituidos=substituidos,
        )
    except regras.ContratoInvalido as e:
        raise HTTPException(422, str(e))


def _cnpj_out(item: dict) -> dict:
    return {
        "cnpj": cnpj_svc.normalizar(item["cnpj"]),
        "cnpj_formatado": cnpj_svc.formatar(item["cnpj"]),
        "razao_social": item["razao_social"],
        "vidas": item["vidas"],
        "mensalidade": item["mensalidade"],
    }


async def _pdf(simples: dict, listas: dict) -> bytes:
    try:
        return await asyncio.to_thread(render.montar_pdf, simples, listas)
    except (render.ModeloContratoIndisponivel, render.ModeloInvalido,
            render.ContratoPdfIndisponivel) as e:
        raise HTTPException(503, str(e))


async def _contatos_disponiveis(conn, oportunidade_id: UUID) -> list[dict]:
    """
    O universo do seletor: contatos da empresa (CNPJ principal ou
    adicional) e do comitê da oportunidade — o mesmo do e-mail (050). Papel
    no comitê vem junto, para sugerir o decisor.
    """
    rows = await conn.fetch(
        """
        WITH contas_opp AS (
            SELECT o.conta_id FROM oportunidades o WHERE o.id = $1
            UNION
            SELECT oc.conta_id FROM oportunidade_contas oc
             WHERE oc.oportunidade_id = $1 AND oc.removido_em IS NULL
        )
        SELECT ct.id, ct.nome, ct.email, x.papel,
               (SELECT cc.cargo FROM conta_contatos cc
                 WHERE cc.contato_id = ct.id AND cc.ativo
                   AND cc.conta_id IN (SELECT conta_id FROM contas_opp)
                 ORDER BY cc.principal DESC LIMIT 1) AS cargo
          FROM contatos ct
          LEFT JOIN oportunidade_contatos x
                 ON x.oportunidade_id = $1 AND x.contato_id = ct.id
         WHERE ct.ativo
           AND (
                EXISTS (SELECT 1 FROM conta_contatos cc
                         WHERE cc.contato_id = ct.id AND cc.ativo
                           AND cc.conta_id IN (SELECT conta_id FROM contas_opp))
             OR x.contato_id IS NOT NULL
           )
         ORDER BY (x.papel = 'decisor') DESC NULLS LAST, ct.nome
        """,
        oportunidade_id,
    )
    return [dict(r) for r in rows]


async def _usuarios_ativos(conn) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, nome, email, cargo FROM usuarios WHERE ativo ORDER BY nome"
    )
    return [dict(r) for r in rows]


def _contratada() -> dict:
    return {
        "papel": "contratada",
        "nome": settings.CONTRATO_CONTRATADA_NOME,
        "email": settings.CONTRATO_CONTRATADA_EMAIL,
    }


async def _validar_origens(conn, oportunidade_id: UUID, payload: ContratoIn) -> None:
    """contato_id precisa ser do universo da oportunidade; usuario_id, ativo."""
    contatos = {c["id"] for c in await _contatos_disponiveis(conn, oportunidade_id)}
    for s in payload.signatarios:
        if s.contato_id is not None and s.contato_id not in contatos:
            raise HTTPException(
                422, "Um dos contatos escolhidos não é da empresa nem do comitê "
                     "desta oportunidade.",
            )
        if s.usuario_id is not None:
            ativo = await conn.fetchval(
                "SELECT ativo FROM usuarios WHERE id = $1", s.usuario_id,
            )
            if not ativo:
                raise HTTPException(422, "Um dos usuários escolhidos não está ativo.")


async def _em_aberto(conn, oportunidade_id: UUID, raiz: str) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT id, versao FROM contratos
         WHERE oportunidade_id = $1 AND raiz_cnpj = $2 AND status = 'enviado'
        """,
        oportunidade_id, raiz,
    )
    return dict(row) if row else None


_SELECT_CONTRATO = """
    SELECT c.*, p.versao AS proposta_versao, p.executivo_id,
           u.nome AS criado_por_nome, uc.nome AS cancelado_por_nome,
           ct.razao_social AS conta_razao_social, ct.cnpj AS conta_cnpj,
           o.numero AS oportunidade_numero,
           -- 055: a contratante DESTE contrato (o 1o CNPJ do grupo), que nem
           -- sempre e o CNPJ principal da oportunidade.
           (SELECT x.razao_social FROM contrato_cnpjs x
             WHERE x.contrato_id = c.id ORDER BY x.ordem LIMIT 1) AS contratante_razao_social,
           (SELECT x.cnpj FROM contrato_cnpjs x
             WHERE x.contrato_id = c.id ORDER BY x.ordem LIMIT 1) AS contratante_cnpj,
           sp.versao AS substituido_por_versao
      FROM contratos c
      JOIN propostas p      ON p.id = c.proposta_id
      JOIN oportunidades o  ON o.id = c.oportunidade_id
      JOIN contas ct        ON ct.id = o.conta_id
      LEFT JOIN usuarios u  ON u.id = c.criado_por
      LEFT JOIN usuarios uc ON uc.id = c.cancelado_por
      LEFT JOIN contratos sp ON sp.id = c.substituido_por
"""


async def _linha_contrato(conn, contrato_id: UUID) -> dict:
    row = await conn.fetchrow(_SELECT_CONTRATO + " WHERE c.id = $1", contrato_id)
    if not row:
        raise HTTPException(404, "Contrato não encontrado.")
    return dict(row)


async def _signatarios(conn, contrato_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        "SELECT * FROM contrato_signatarios WHERE contrato_id = $1 ORDER BY ordem",
        contrato_id,
    )
    return [dict(r) for r in rows]


def _pode_cancelar(contrato: dict, user: dict) -> bool:
    if contrato["status"] != regras.STATUS_ENVIADO:
        return False
    return (_eh_gestao(user)
            or str(contrato.get("criado_por")) == str(user["id"])
            or str(contrato.get("executivo_id")) == str(user["id"]))


async def _saida(conn, contrato: dict, user: dict) -> dict:
    sigs = await _signatarios(conn, contrato["id"])
    eventos = await conn.fetch(
        """
        SELECT e.id, e.tipo, e.origem, e.descricao, e.criado_em, u.nome AS usuario_nome
          FROM contrato_eventos e
          LEFT JOIN usuarios u ON u.id = e.usuario_id
         WHERE e.contrato_id = $1 AND e.tipo <> 'webhook'
         ORDER BY e.criado_em DESC, e.id
         LIMIT 50
        """,
        contrato["id"],
    )
    proximo = (regras.proximo_a_assinar(sigs)
               if contrato["status"] == regras.STATUS_ENVIADO else None)
    return {
        **contrato,
        "tem_assinado": bool(contrato.get("s3_chave_assinado"))
        or contrato["status"] == regras.STATUS_ASSINADO,
        "signatarios": [
            {**s, "papel_rotulo": regras.PAPEL_POR_CHAVE[s["papel"]].rotulo,
             "da_vez": proximo is not None and s["id"] == proximo["id"]}
            for s in sigs
        ],
        "eventos": [dict(e) for e in eventos],
        "assinados": sum(1 for s in sigs if s["situacao"] == regras.SIG_ASSINADO),
        "total_signatarios": len(sigs),
        "proximo_nome": proximo["nome"] if proximo else None,
        "pode_cancelar": _pode_cancelar(contrato, user),
        "aviso_para": list(contrato.get("aviso_para") or []) or None,
        "pode_reenviar_aviso": (contrato["status"] == regras.STATUS_ASSINADO
                                and _pode_cancelar({**contrato, "status": regras.STATUS_ENVIADO},
                                                   user)),
        "cnpjs": [_cnpj_out(c) for c in await _cnpjs_do_contrato(conn, contrato["id"])],
        "servicos": list(contrato.get("servicos") or []),
        "servicos_livres": list(contrato.get("servicos_livres") or []),
        "substitui": await _refs(conn, list(contrato.get("substitui_ids") or [])),
    }


async def _cnpjs_do_contrato(conn, contrato_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT conta_id, cnpj, razao_social, vidas, mensalidade
          FROM contrato_cnpjs WHERE contrato_id = $1 ORDER BY ordem
        """,
        contrato_id,
    )
    return [dict(r) for r in rows]


async def _refs(conn, ids: list) -> list[dict]:
    if not ids:
        return []
    rows = await conn.fetch(
        """
        SELECT k.id, k.versao, k.data_contrato, o.numero AS oportunidade_numero
          FROM contratos k JOIN oportunidades o ON o.id = k.oportunidade_id
         WHERE k.id = ANY($1::uuid[])
         ORDER BY k.data_contrato, k.versao
        """,
        ids,
    )
    return [dict(r) for r in rows]


# ── Sincronização (usada pela rota, pelo webhook e pelo timer) ───────

_DESCRICAO = {
    regras.SIG_VISUALIZADO: "{nome} abriu o contrato",
    regras.SIG_ASSINADO: "{nome} assinou",
    regras.SIG_RECUSADO: "{nome} recusou",
    regras.SIG_FALHA: "O e-mail para {nome} não foi entregue",
}


async def aplicar_documento(
    conn, contrato: dict, documento: dict, *, origem: str,
    evento_externo_id: str | None = None, evento_tipo: str | None = None,
) -> dict:
    """
    Reescreve o estado do contrato a partir do documento lido na Autentique.
    Idempotente: aplicar duas vezes o mesmo documento não cria evento nem
    tarefa repetidos. Roda numa transação; devolve o contrato atualizado.

    Não baixa o PDF assinado (é lento e é rede): quem chama faz isso depois,
    fora da transação — `guardar_assinado`.
    """
    sigs = await _signatarios(conn, contrato["id"])
    casados = regras.casar_assinaturas(sigs, documento.get("signatures") or [])
    agora = _agora()

    async with conn.transaction():
        atual = await conn.fetchrow(
            "SELECT * FROM contratos WHERE id = $1 FOR UPDATE", contrato["id"],
        )
        if evento_externo_id:
            inserido = await conn.fetchval(
                """
                INSERT INTO contrato_eventos (contrato_id, tipo, origem, descricao,
                                              evento_externo_id)
                VALUES ($1, 'webhook', 'webhook', $2, $3)
                ON CONFLICT (evento_externo_id) WHERE evento_externo_id IS NOT NULL
                DO NOTHING
                RETURNING id
                """,
                contrato["id"], evento_tipo, evento_externo_id,
            )
            if inserido is None:
                return dict(atual)  # entrega repetida: já processada

        situacoes = []
        for s in sigs:
            assinatura = casados.get(s["id"])
            if assinatura is None:
                situacoes.append(s["situacao"])
                continue
            novo = regras.situacao_signatario(assinatura)
            situacoes.append(novo["situacao"])
            mudou = (novo["situacao"] != s["situacao"]
                     or novo["assinado_em"] != s["assinado_em"]
                     or novo["visualizado_em"] != s["visualizado_em"]
                     or (assinatura.get("public_id") and not s["autentique_public_id"]))
            if not mudou:
                continue
            await conn.execute(
                """
                UPDATE contrato_signatarios
                   SET situacao = $2, visualizado_em = $3, assinado_em = $4,
                       recusado_em = $5, motivo_recusa = $6,
                       autentique_public_id = COALESCE(autentique_public_id, $7),
                       atualizado_em = NOW()
                 WHERE id = $1
                """,
                s["id"], novo["situacao"], novo["visualizado_em"], novo["assinado_em"],
                novo["recusado_em"], novo["motivo_recusa"], assinatura.get("public_id"),
            )
            if novo["situacao"] != s["situacao"] and novo["situacao"] in _DESCRICAO:
                descricao = _DESCRICAO[novo["situacao"]].format(nome=s["nome"])
                if novo["situacao"] == regras.SIG_RECUSADO and novo["motivo_recusa"]:
                    descricao += f": {novo['motivo_recusa']}"
                await conn.execute(
                    """
                    INSERT INTO contrato_eventos (contrato_id, tipo, origem, descricao,
                                                  signatario_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    contrato["id"], novo["situacao"], origem, descricao, s["id"],
                )

        status_novo = regras.status_do_contrato(situacoes, atual["status"])
        if status_novo != atual["status"] and atual["status"] == regras.STATUS_ENVIADO:
            await _virar(conn, dict(atual), status_novo, sigs, casados, origem)

        await conn.execute(
            "UPDATE contratos SET sincronizado_em = $2, sincronizacao_erro = NULL, "
            "atualizado_em = NOW() WHERE id = $1",
            contrato["id"], agora,
        )
    return await _linha_contrato(conn, contrato["id"])


async def _responsavel_aviso(conn, contrato: dict) -> UUID | None:
    """O executivo da proposta, se ativo; senão quem mandou o contrato."""
    row = await conn.fetchrow(
        """
        SELECT CASE WHEN ue.ativo THEN p.executivo_id END AS executivo,
               CASE WHEN uc.ativo THEN c.criado_por END AS criador
          FROM contratos c
          JOIN propostas p     ON p.id = c.proposta_id
          LEFT JOIN usuarios ue ON ue.id = p.executivo_id
          LEFT JOIN usuarios uc ON uc.id = c.criado_por
         WHERE c.id = $1
        """,
        contrato["id"],
    )
    return (row["executivo"] or row["criador"]) if row else None


async def _virar(conn, contrato: dict, status_novo: str, sigs: list[dict],
                 casados: dict, origem: str) -> None:
    """Contrato concluído (todos assinaram) ou recusado: grava e avisa."""
    # A contratante deste contrato (055: pode não ser o CNPJ principal).
    razao = await conn.fetchval(
        "SELECT razao_social FROM contrato_cnpjs WHERE contrato_id = $1 ORDER BY ordem LIMIT 1",
        contrato["id"],
    ) or await conn.fetchval(
        "SELECT ct.razao_social FROM oportunidades o JOIN contas ct ON ct.id = o.conta_id "
        "WHERE o.id = $1", contrato["oportunidade_id"],
    )
    responsavel = await _responsavel_aviso(conn, contrato)

    if status_novo == regras.STATUS_ASSINADO:
        datas = [regras.situacao_signatario(casados[s["id"]])["assinado_em"]
                 for s in sigs if s["id"] in casados]
        quando = max((d for d in datas if d), default=_agora())
        await conn.execute(
            "UPDATE contratos SET status = 'assinado', assinado_em = $2 WHERE id = $1",
            contrato["id"], quando,
        )
        await conn.execute(
            "INSERT INTO contrato_eventos (contrato_id, tipo, origem, descricao) "
            "VALUES ($1, 'concluido', $2, 'Todos assinaram. Contrato concluído.')",
            contrato["id"], origem,
        )
        # 055: o contrato novo da raiz substitui os anteriores que ainda
        # estavam valendo. Só na assinatura: enquanto o novo não é assinado,
        # o antigo segue sendo o contrato da empresa.
        substituidos = await conn.fetch(
            """
            UPDATE contratos
               SET status = 'substituido', substituido_em = $2, substituido_por = $3,
                   atualizado_em = NOW()
             WHERE id = ANY($1::uuid[]) AND status = 'assinado'
            RETURNING id
            """,
            list(contrato.get("substitui_ids") or []), quando, contrato["id"],
        )
        for r in substituidos:
            await conn.execute(
                "INSERT INTO contrato_eventos (contrato_id, tipo, origem, descricao) "
                "VALUES ($1, 'substituido', $2, $3)",
                r["id"], origem,
                f"Substituído pelo contrato v{contrato['versao']}, assinado por todos.",
            )
        titulo = regras.titulo_tarefa_assinado(razao)
        descricao = ("O contrato foi assinado por todos na Autentique. O PDF "
                     "assinado está na aba Contrato da oportunidade. Faça o "
                     "desfecho da oportunidade.")
    else:
        recusou = next((s for s in sigs if s["id"] in casados and
                        regras.situacao_signatario(casados[s["id"]])["situacao"]
                        == regras.SIG_RECUSADO), None)
        nome = recusou["nome"] if recusou else "um signatário"
        motivo = (regras.situacao_signatario(casados[recusou["id"]])["motivo_recusa"]
                  if recusou else None)
        await conn.execute(
            "UPDATE contratos SET status = 'recusado', recusado_em = NOW() WHERE id = $1",
            contrato["id"],
        )
        titulo = regras.titulo_tarefa_recusado(nome)
        descricao = (f"{nome} recusou o contrato na Autentique."
                     + (f" Motivo informado: {motivo}" if motivo else "")
                     + " Fale com o cliente; para mandar de novo, gere outra "
                       "versão do contrato.")

    if responsavel is None:
        log.warning("contrato %s: sem responsavel ativo para a tarefa de aviso",
                    contrato["id"])
        return
    contratante = next((s for s in sigs if s["papel"] == "contratante"), None)
    tarefa_id = await inserir_tarefa(
        conn,
        SimpleNamespace(
            tipo="outro", titulo=titulo, descricao=descricao,
            responsavel_id=responsavel, prazo=_agora(),
            contato_id=contratante.get("contato_id") if contratante else None,
        ),
        contrato["oportunidade_id"], None, None, None,
    )
    await conn.execute(
        "UPDATE contratos SET tarefa_aviso_id = $2 WHERE id = $1",
        contrato["id"], tarefa_id,
    )


def _chave_s3(contrato: dict, tipo: str) -> str:
    return f"contratos/{contrato['oportunidade_id']}/{contrato['id']}/{tipo}.pdf"


async def guardar_assinado(conn, contrato: dict, documento: dict | None = None) -> bool:
    """
    Baixa o PDF assinado da Autentique e guarda no S3. Melhor esforço: sem
    bucket, ou com a Autentique fora, o download continua funcionando direto
    da Autentique, e o timer tenta de novo na próxima passada.
    """
    if contrato["status"] != regras.STATUS_ASSINADO or contrato.get("s3_chave_assinado"):
        return False
    if not s3.disponivel():
        return False
    try:
        documento = documento or await autentique.consultar(contrato["autentique_id"])
        url = (documento.get("files") or {}).get("signed")
        if not url:
            return False
        pdf = await autentique.baixar(url)
        chave = _chave_s3(contrato, "assinado")
        await asyncio.to_thread(s3.subir, chave, pdf, "application/pdf")
    except Exception as exc:  # noqa: BLE001 - nada aqui pode derrubar o fluxo
        log.warning("contrato %s: PDF assinado nao guardado: %s", contrato["id"], exc)
        return False
    await conn.execute(
        "UPDATE contratos SET s3_chave_assinado = $2 WHERE id = $1", contrato["id"], chave,
    )
    return True


async def sincronizar_um(conn, contrato: dict, *, origem: str = "sincronizacao") -> dict:
    """Lê a Autentique e aplica. Erro de API fica gravado no contrato."""
    try:
        documento = await autentique.consultar(contrato["autentique_id"])
    except autentique.AutentiqueErro as e:
        await conn.execute(
            "UPDATE contratos SET sincronizacao_erro = $2, sincronizado_em = NOW() "
            "WHERE id = $1",
            contrato["id"], str(e)[:500],
        )
        raise
    atualizado = await aplicar_documento(conn, contrato, documento, origem=origem)
    await guardar_assinado(conn, atualizado, documento)
    await avisar_assinado(conn, await _linha_contrato(conn, contrato["id"]), documento)
    return await _linha_contrato(conn, contrato["id"])


async def pendentes_de_sincronizacao(conn) -> list[dict]:
    """
    O que o timer olha: contratos aguardando assinatura (o que foi
    sincronizado há mais tempo primeiro) e assinados sem o PDF no S3.
    """
    # Sem bucket, assinado sem PDF guardado é o estado normal, e não algo a
    # tentar de novo a cada passada.
    rows = await conn.fetch(
        _SELECT_CONTRATO
        + """
         WHERE c.status = 'enviado'
            OR ($1 AND c.status = 'assinado' AND c.s3_chave_assinado IS NULL)
            OR ($2 AND c.status = 'assinado' AND c.aviso_enviado_em IS NULL
                AND NOT c.sandbox AND c.aviso_tentativas < $3)
         ORDER BY c.sincronizado_em NULLS FIRST
        """,
        s3.disponivel(), aviso_ligado(), regras.MAX_TENTATIVAS_AVISO,
    )
    return [dict(r) for r in rows]


# ── Aviso de contrato assinado (054) ─────────────────────────────────

def aviso_ligado() -> bool:
    return bool(regras.destinatarios_aviso(settings.CONTRATO_AVISO_DESTINATARIOS))


async def _remetente_aviso(conn, contrato: dict) -> dict | None:
    """
    O executivo da proposta, se ativo; senão quem mandou o contrato. O e-mail
    sai da caixa dele pelo Gmail (delegação no domínio, a mesma do 050).
    """
    row = await conn.fetchrow(
        """
        SELECT ue.nome AS ex_nome, ue.email AS ex_email, ue.ativo AS ex_ativo,
               uc.nome AS cr_nome, uc.email AS cr_email, uc.ativo AS cr_ativo
          FROM contratos c
          JOIN propostas p      ON p.id = c.proposta_id
          LEFT JOIN usuarios ue ON ue.id = p.executivo_id
          LEFT JOIN usuarios uc ON uc.id = c.criado_por
         WHERE c.id = $1
        """,
        contrato["id"],
    )
    if row is None:
        return None
    if row["ex_ativo"] and row["ex_email"]:
        return {"nome": row["ex_nome"], "email": row["ex_email"]}
    if row["cr_ativo"] and row["cr_email"]:
        return {"nome": row["cr_nome"], "email": row["cr_email"]}
    return None


async def _pdf_assinado(contrato: dict, documento: dict | None) -> bytes:
    """Do S3 quando já está lá; senão da Autentique."""
    chave = contrato.get("s3_chave_assinado")
    if chave and s3.disponivel():
        try:
            return await asyncio.to_thread(_ler_s3, chave)
        except Exception as exc:  # noqa: BLE001 - cai para a Autentique
            log.warning("contrato %s: S3 falhou no aviso: %s", contrato["id"], exc)
    documento = documento or await autentique.consultar(contrato["autentique_id"])
    url = (documento.get("files") or {}).get("signed")
    if not url:
        raise autentique.AutentiqueErro("A Autentique ainda não tem o PDF assinado.")
    return await autentique.baixar(url)


async def _falha_aviso(conn, contrato_id, mensagem: str) -> None:
    await conn.execute(
        """
        UPDATE contratos
           SET aviso_erro = $2, aviso_tentativas = aviso_tentativas + 1
         WHERE id = $1
        """,
        contrato_id, mensagem[:500],
    )


def _razao_contratante(contrato: dict) -> str:
    return contrato.get("contratante_razao_social") or contrato["conta_razao_social"]


def _com_extras(contrato: dict) -> bool:
    """Treinamentos e laudos vão só no contrato do grupo do CNPJ principal."""
    return regras.raiz(contrato.get("conta_cnpj")) == contrato.get("raiz_cnpj")


async def avisar_assinado(
    conn, contrato: dict, documento: dict | None = None, *,
    forcar: bool = False, usuario_id=None,
) -> bool:
    """
    Manda o aviso de contrato assinado. Devolve True se saiu.

    NUNCA levanta: é chamada do webhook e do timer, e um Gmail fora do ar
    não pode fazer a Autentique achar que o webhook falhou (ela tentaria de
    novo e o contrato já está gravado). A falha fica em aviso_erro, e o timer
    tenta de novo até MAX_TENTATIVAS_AVISO.

    Idempotente: aviso já enviado não sai de novo, a não ser com `forcar`
    (o botão "Reenviar aviso" da tela).
    """
    if contrato["status"] != regras.STATUS_ASSINADO:
        return False
    if contrato.get("aviso_enviado_em") and not forcar:
        return False
    # Contrato de teste (sandbox) não avisa o faturamento sozinho: cobrança
    # cadastrada por engano a partir de um teste é pior que aviso nenhum.
    # Pelo botão da tela sai, com "[TESTE]" no assunto.
    if contrato.get("sandbox") and not forcar:
        return False

    try:
        remetente = await _remetente_aviso(conn, contrato)
        destinos = regras.destinatarios_aviso(
            settings.CONTRATO_AVISO_DESTINATARIOS,
            remetente["email"] if remetente else None,
        )
        if not destinos:
            if forcar:
                await _falha_aviso(conn, contrato["id"],
                                   "Nenhum destinatário configurado "
                                   "(CONTRATO_AVISO_DESTINATARIOS no .env).")
            return False
        if remetente is None:
            await _falha_aviso(conn, contrato["id"],
                               "Nem o executivo da proposta nem quem mandou o contrato "
                               "estão ativos; não há caixa de onde enviar.")
            return False
        if not gmail.configurado():
            await _falha_aviso(conn, contrato["id"],
                               "O envio pelo Gmail está desligado neste servidor.")
            return False

        pdf = await _pdf_assinado(contrato, documento)
        proposta = await buscar_proposta(conn, contrato["proposta_id"])
        sigs = await _signatarios(conn, contrato["id"])
        cnpjs = await _cnpjs_do_contrato(conn, contrato["id"])
        razao = _razao_contratante(contrato)
        corpo = regras.corpo_aviso(
            razao_social=razao,
            cnpj=contrato.get("contratante_cnpj") or contrato.get("conta_cnpj") or "",
            numero_oportunidade=contrato.get("oportunidade_numero"),
            executivo_nome=proposta.get("executivo_nome"),
            proposta=proposta, contrato=contrato, signatarios=sigs,
            link=regras.url_oportunidade(settings.HIPO_URL_PUBLICA, empresa_sigla(),
                                         contrato["oportunidade_id"]),
            itens=cnpjs or None,
            com_extras=_com_extras(contrato),
        )
        assunto = regras.assunto_aviso(razao, contrato.get("oportunidade_numero"))
        if contrato.get("sandbox"):
            assunto = "[TESTE] " + assunto
        assinatura = await gmail.assinatura(remetente["email"])
        mensagem = email_comercial.montar_mensagem(
            remetente_nome=remetente["nome"] or "",
            remetente_email=remetente["email"],
            envio=email_comercial.Envio(destinos, [], assunto, corpo),
            assinatura_html=assinatura.html,
            anexo=email_comercial.Anexo(
                regras.nome_arquivo(contrato.get("oportunidade_numero"), razao,
                                    contrato["versao"], assinado=True),
                pdf,
            ),
        )
        resultado = await gmail.enviar(remetente["email"], mensagem)
    except Exception as exc:  # noqa: BLE001 - nunca derruba quem chamou
        log.warning("contrato %s: aviso falhou: %s", contrato["id"], exc)
        await _falha_aviso(conn, contrato["id"], f"Falha ao montar o aviso: {exc}")
        return False

    if not resultado.ok:
        await _falha_aviso(conn, contrato["id"], resultado.erro or "O Gmail recusou o envio.")
        return False

    async with conn.transaction():
        await conn.execute(
            """
            UPDATE contratos
               SET aviso_enviado_em = NOW(), aviso_para = $2, aviso_remetente = $3,
                   aviso_erro = NULL, aviso_tentativas = aviso_tentativas + 1
             WHERE id = $1
            """,
            contrato["id"], destinos, remetente["email"],
        )
        await conn.execute(
            """
            INSERT INTO contrato_eventos (contrato_id, tipo, origem, descricao, usuario_id)
            VALUES ($1, 'aviso_enviado', 'hipo', $2, $3)
            """,
            contrato["id"],
            f"Aviso de contrato assinado enviado por {remetente['email']} para "
            + ", ".join(destinos),
            usuario_id,
        )
    return True


# ── Situação e padrão ────────────────────────────────────────────────

@router.get("/contratos/situacao", response_model=SituacaoOut)
async def situacao():
    """O que falta para o envio funcionar. A tela esconde o botão se faltar."""
    from services.proposta_render import libreoffice_disponivel

    problemas = autentique.problemas()
    return {
        "configurado": not problemas,
        "problemas": problemas,
        "sandbox": autentique.em_sandbox(),
        "previa_disponivel": libreoffice_disponivel() is not None,
        "aviso_destinatarios": regras.destinatarios_aviso(settings.CONTRATO_AVISO_DESTINATARIOS),
    }


@router.get("/propostas/{proposta_id}/contrato-padrao", response_model=PadraoOut)
async def padrao(proposta_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    Tudo o que o formulário de envio precisa, já sugerido.

    055: `grupos` traz um contrato possível por raiz de CNPJ. Os campos de
    cliente no topo (razão, CNPJ, endereço, preço) são os do primeiro grupo,
    o do CNPJ principal — compatibilidade com a tela de um grupo só.
    """
    proposta, opp, _conta = await _contexto(conn, proposta_id)
    hoje = _hoje()
    contatos = await _contatos_disponiveis(conn, opp["id"])
    usuarios = await _usuarios_ativos(conn)
    decisor = next((c for c in contatos if c["papel"] == "decisor" and c["email"]), None)
    com_email = next((c for c in contatos if c["email"]), None)
    executivo = proposta.get("executivo_id")
    testemunha = executivo if any(u["id"] == executivo for u in usuarios) else user["id"]

    grupos = []
    for g in regras.agrupar_itens(proposta.get("itens") or []):
        grupo = await _grupo(conn, proposta, opp, g["raiz"])
        aberto = await _em_aberto(conn, opp["id"], grupo["raiz"])
        grupos.append({
            "raiz": grupo["raiz"],
            "principal": grupo["principal"],
            "contratante_razao_social": grupo["conta"]["razao_social"],
            "contratante_cnpj": cnpj_svc.formatar(grupo["conta"]["cnpj"]),
            "conta_id": grupo["conta"].get("id"),
            "endereco": regras.endereco_formatado(grupo["conta"]),
            "pendencias_endereco": regras.pendencias_endereco(grupo["conta"]),
            "cnpjs": [_cnpj_out(i) for i in grupo["itens"]],
            "linhas_preco": regras.linhas_preco(proposta, grupo["itens"], grupo["principal"]),
            "contrato_em_aberto_id": aberto["id"] if aberto else None,
            "substitui": await _substituiveis(conn, grupo["raiz"]),
        })
    grupos.sort(key=lambda g: not g["principal"])
    if not grupos:
        raise HTTPException(422, "Esta proposta não tem CNPJ.")
    primeiro = grupos[0]
    return {
        "proposta_id": proposta["id"],
        "proposta_versao": proposta["versao"],
        "aprovada": bool(proposta.get("aprovada_em")),
        "oportunidade_aberta": opp["status"] in STATUS_ABERTOS,
        "cliente_razao_social": primeiro["contratante_razao_social"],
        "cliente_cnpj": primeiro["contratante_cnpj"],
        "endereco": primeiro["endereco"],
        "pendencias_endereco": primeiro["pendencias_endereco"],
        "conta_id": primeiro["conta_id"] or opp["conta_id"],
        "contratada_nome": settings.CONTRATO_CONTRATADA_NOME,
        "contratada_email": settings.CONTRATO_CONTRATADA_EMAIL,
        "data_contrato": hoje,
        "inicio_vigencia": regras.inicio_vigencia_padrao(hoje),
        "dia_vencimento": regras.DIA_VENCIMENTO_PADRAO,
        "contatos": [
            {"id": c["id"], "nome": c["nome"], "email": c["email"],
             "detalhe": " · ".join(x for x in (c.get("cargo"), c.get("papel")) if x) or None}
            for c in contatos
        ],
        "usuarios": [
            {"id": u["id"], "nome": u["nome"], "email": u["email"], "detalhe": u["cargo"]}
            for u in usuarios
        ],
        "sugestao_contratante_id": (decisor or com_email or {}).get("id"),
        "sugestao_testemunha_contratada_id": testemunha,
        "contrato_em_aberto_id": primeiro["contrato_em_aberto_id"],
        "linhas_preco": primeiro["linhas_preco"],
        "grupos": grupos,
        "servicos_catalogo": [{"chave": x.chave, "texto": x.texto}
                              for x in regras.SERVICOS_EXTRAS],
        "servicos_sugeridos": regras.servicos_sugeridos(proposta.get("escopo")),
    }


async def _montar(conn, proposta: dict, opp: dict, payload: PreviaIn):
    """(grupo, substituíveis, data, início, dia, simples, listas) do contrato."""
    grupo = await _grupo(conn, proposta, opp, payload.raiz_cnpj)
    substituiveis = await _substituiveis(conn, grupo["raiz"])
    data_contrato, inicio, dia = _datas(payload)
    simples, listas = _campos(proposta, grupo, data_contrato, inicio, dia,
                              payload.servicos, payload.servicos_livres, substituiveis)
    return grupo, substituiveis, data_contrato, inicio, dia, simples, listas


@router.post("/propostas/{proposta_id}/contrato/previa")
async def previa(
    proposta_id: UUID, payload: PreviaIn,
    conn=Depends(get_conn), user=Depends(usuario_atual),
):
    """O PDF exatamente como vai para a Autentique, sem mandar nada."""
    proposta, opp, _conta = await _contexto(conn, proposta_id)
    grupo, _subs, _d, _i, _v, simples, listas = await _montar(conn, proposta, opp, payload)
    pdf = await _pdf(simples, listas)
    nome = regras.nome_arquivo(opp["numero"], grupo["conta"]["razao_social"], 1,
                               assinado=False)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="previa-{nome}"'},
    )


# ── Envio ────────────────────────────────────────────────────────────

@router.post("/propostas/{proposta_id}/contratos", response_model=ContratoOut,
             status_code=http.HTTP_201_CREATED)
async def enviar(
    proposta_id: UUID, payload: ContratoIn,
    conn=Depends(get_conn), user=Depends(usuario_atual),
):
    problemas = autentique.problemas()
    if problemas:
        raise HTTPException(503, "O envio de contrato está desligado neste servidor: "
                                 + "; ".join(problemas) + ".")

    proposta, opp, _conta = await _contexto(conn, proposta_id)
    _exigir_enviavel(proposta, opp)
    try:
        signatarios = regras.validar_signatarios(
            [s.model_dump() for s in payload.signatarios] + [_contratada()]
        )
    except regras.ContratoInvalido as e:
        raise HTTPException(422, str(e))
    await _validar_origens(conn, opp["id"], payload)
    origem = {s.papel: s for s in payload.signatarios}

    (grupo, substituiveis, data_contrato, inicio, dia,
     simples, listas) = await _montar(conn, proposta, opp, payload)
    aberto = await _em_aberto(conn, opp["id"], grupo["raiz"])
    if aberto:
        raise HTTPException(
            409, f"Já há um contrato (v{aberto['versao']}) de "
                 f"{grupo['conta']['razao_social']} aguardando assinatura. "
                 "Cancele-o antes de mandar outro.",
        )
    razao = grupo["conta"]["razao_social"]

    pdf = await _pdf(simples, listas)
    posicoes = render.localizar_assinaturas(pdf)
    modelo_hash = regras.sha256(render.ler_modelo())

    versao = (await conn.fetchval(
        "SELECT COALESCE(MAX(versao), 0) FROM contratos WHERE oportunidade_id = $1",
        opp["id"],
    )) + 1
    nome_doc = regras.nome_documento(opp["numero"], razao, versao)
    nome_pdf = regras.nome_arquivo(opp["numero"], razao, versao, assinado=False)

    try:
        criado = await autentique.criar_documento(
            nome=nome_doc,
            mensagem=regras.mensagem_para_signatarios(razao),
            pdf=pdf, nome_arquivo=nome_pdf,
            signatarios=signatarios, posicoes=posicoes,
        )
    except autentique.AutentiqueErro as e:
        raise HTTPException(502, str(e))

    por_email = {(a.email or "").lower(): a for a in criado.assinaturas}
    hash_original = regras.sha256(pdf)
    try:
        async with conn.transaction():
            tarefa_id = await inserir_tarefa_concluida(
                conn,
                TarefaDeFinalizacao(
                    tipo="outro", titulo=regras.titulo_tarefa_envio(versao),
                    descricao=nome_doc, responsavel_id=user["id"],
                    contato_id=origem["contratante"].contato_id,
                ),
                oportunidade_id=opp["id"], criado_por=user["id"],
                resultado=regras.resultado_tarefa_envio(signatarios),
            )
            await registrar_no_comite(conn, opp["id"], origem["contratante"].contato_id,
                                      user["id"])
            contrato_id = await conn.fetchval(
                """
                INSERT INTO contratos (
                    oportunidade_id, proposta_id, versao, autentique_id, sandbox,
                    nome_documento, data_contrato, inicio_vigencia, dia_vencimento,
                    campos, hash_original, modelo_hash, tarefa_envio_id, criado_por,
                    raiz_cnpj, servicos, servicos_livres, substitui_ids
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $14,
                        $15, $16, $17, $18)
                RETURNING id
                """,
                opp["id"], proposta["id"], versao, criado.id, autentique.em_sandbox(),
                nome_doc, data_contrato, inicio, dia,
                json.dumps({"simples": simples, "listas": listas}, ensure_ascii=False),
                hash_original, modelo_hash, tarefa_id, user["id"],
                grupo["raiz"], list(dict.fromkeys(payload.servicos)),
                [x for x in (" ".join(l.split()) for l in payload.servicos_livres) if x],
                [x["id"] for x in substituiveis],
            )
            for ordem, item in enumerate(grupo["itens"], start=1):
                await conn.execute(
                    """
                    INSERT INTO contrato_cnpjs (contrato_id, ordem, conta_id, cnpj,
                                                razao_social, vidas, mensalidade)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    contrato_id, ordem, item.get("conta_id"),
                    cnpj_svc.normalizar(item["cnpj"]), item["razao_social"],
                    item["vidas"], item["mensalidade"],
                )
            for s in signatarios:
                vindo = origem.get(s["papel"])
                a = por_email.get(s["email"])
                await conn.execute(
                    """
                    INSERT INTO contrato_signatarios (
                        contrato_id, ordem, papel, nome, email, acao, contato_id,
                        usuario_id, autentique_public_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    contrato_id, s["ordem"], s["papel"], s["nome"], s["email"], s["acao"],
                    vindo.contato_id if vindo else None,
                    vindo.usuario_id if vindo else None,
                    a.public_id if a else None,
                )
            descricao = (f"Contrato v{versao} de {razao} enviado pela Autentique "
                         f"(proposta v{proposta['versao']}")
            if len(grupo["itens"]) > 1:
                descricao += f", {len(grupo['itens'])} CNPJs"
            descricao += ")"
            if substituiveis:
                descricao += (" — substitui " + ", ".join(f"v{x['versao']}" for x in substituiveis)
                              + " quando for assinado")
            if autentique.em_sandbox():
                descricao += " — documento de TESTE (sandbox)"
            await conn.execute(
                """
                INSERT INTO contrato_eventos (contrato_id, tipo, origem, descricao, usuario_id)
                VALUES ($1, 'enviado', 'hipo', $2, $3)
                """,
                contrato_id, descricao, user["id"],
            )
    except Exception:
        log.exception("contrato: falha ao gravar; cancelando %s na Autentique", criado.id)
        try:
            await autentique.cancelar(criado.id)
        except Exception:  # noqa: BLE001
            log.exception("contrato: o cancelamento de %s tambem falhou", criado.id)
        raise

    # O original no S3, fora da transação: sem bucket, o download vai à
    # Autentique — o contrato já está registrado de qualquer jeito.
    if s3.disponivel():
        chave = _chave_s3({"oportunidade_id": opp["id"], "id": contrato_id}, "original")
        try:
            await asyncio.to_thread(s3.subir, chave, pdf, "application/pdf")
            await conn.execute(
                "UPDATE contratos SET s3_chave_original = $2 WHERE id = $1", contrato_id, chave,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("contrato %s: original nao foi para o S3: %s", contrato_id, exc)

    return await _saida(conn, await _linha_contrato(conn, contrato_id), user)


# ── Leitura e ações ──────────────────────────────────────────────────

@router.get("/oportunidades/{oportunidade_id}/contratos", response_model=list[ContratoOut])
async def listar(oportunidade_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    existe = await conn.fetchval("SELECT 1 FROM oportunidades WHERE id = $1", oportunidade_id)
    if not existe:
        raise HTTPException(404, "Oportunidade não encontrada.")
    rows = await conn.fetch(
        _SELECT_CONTRATO + " WHERE c.oportunidade_id = $1 ORDER BY c.versao DESC",
        oportunidade_id,
    )
    return [await _saida(conn, dict(r), user) for r in rows]


@router.get("/contratos/{contrato_id}", response_model=ContratoOut)
async def obter(contrato_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    return await _saida(conn, await _linha_contrato(conn, contrato_id), user)


@router.post("/contratos/{contrato_id}/sincronizar", response_model=ContratoOut)
async def sincronizar(contrato_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """O botão "Atualizar": lê a Autentique agora, sem esperar webhook."""
    contrato = await _linha_contrato(conn, contrato_id)
    if contrato["status"] == regras.STATUS_CANCELADO:
        return await _saida(conn, contrato, user)
    if not settings.AUTENTIQUE_API_TOKEN:
        raise HTTPException(503, "A integração com a Autentique está desligada neste servidor.")
    try:
        contrato = await sincronizar_um(conn, contrato, origem="sincronizacao")
    except autentique.AutentiqueErro as e:
        raise HTTPException(502, str(e))
    return await _saida(conn, contrato, user)


@router.post("/contratos/{contrato_id}/reenviar", response_model=ContratoOut)
async def reenviar(contrato_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    Reenvia o e-mail para quem é a vez (assinatura sequencial: os seguintes
    ainda não receberam). A Autentique tem um intervalo mínimo entre
    reenvios; dentro dele, a mensagem dela volta traduzida.
    """
    contrato = await _linha_contrato(conn, contrato_id)
    if contrato["status"] != regras.STATUS_ENVIADO:
        raise HTTPException(409, "Este contrato não está aguardando assinatura.")
    sigs = await _signatarios(conn, contrato_id)
    vez = regras.proximo_a_assinar(sigs)
    if vez is None or not vez["autentique_public_id"]:
        raise HTTPException(409, "Não há para quem reenviar agora. Use Atualizar.")
    try:
        await autentique.reenviar([vez["autentique_public_id"]])
    except autentique.AutentiqueErro as e:
        raise HTTPException(502, str(e))
    async with conn.transaction():
        await conn.execute(
            "UPDATE contrato_signatarios SET reenviado_em = NOW() WHERE id = $1", vez["id"],
        )
        await conn.execute(
            """
            INSERT INTO contrato_eventos (contrato_id, tipo, origem, descricao,
                                          signatario_id, usuario_id)
            VALUES ($1, 'reenviado', 'hipo', $2, $3, $4)
            """,
            contrato_id, f"E-mail de assinatura reenviado para {vez['nome']}",
            vez["id"], user["id"],
        )
    return await _saida(conn, await _linha_contrato(conn, contrato_id), user)


@router.post("/contratos/{contrato_id}/cancelar", response_model=ContratoOut)
async def cancelar(
    contrato_id: UUID, payload: CancelarIn,
    conn=Depends(get_conn), user=Depends(usuario_atual),
):
    """
    Bloqueia o documento na Autentique e marca cancelado. Quem pode: quem
    mandou, o executivo da proposta e a gestão.
    """
    contrato = await _linha_contrato(conn, contrato_id)
    if contrato["status"] != regras.STATUS_ENVIADO:
        raise HTTPException(409, "Só contrato aguardando assinatura pode ser cancelado.")
    if not _pode_cancelar(contrato, user):
        raise HTTPException(
            403, "Só quem mandou o contrato, o executivo da proposta ou a gestão "
                 "podem cancelar.",
        )
    try:
        await autentique.cancelar(contrato["autentique_id"])
    except autentique.AutentiqueErro as e:
        raise HTTPException(502, str(e))
    motivo = " ".join(payload.motivo.split())
    async with conn.transaction():
        await conn.execute(
            """
            UPDATE contratos
               SET status = 'cancelado', cancelado_em = NOW(), cancelado_por = $2,
                   motivo_cancelamento = $3, atualizado_em = NOW()
             WHERE id = $1
            """,
            contrato_id, user["id"], motivo,
        )
        await conn.execute(
            """
            INSERT INTO contrato_eventos (contrato_id, tipo, origem, descricao, usuario_id)
            VALUES ($1, 'cancelado', 'hipo', $2, $3)
            """,
            contrato_id, f"Cancelado: {motivo}", user["id"],
        )
    return await _saida(conn, await _linha_contrato(conn, contrato_id), user)


@router.post("/contratos/{contrato_id}/aviso", response_model=ContratoOut)
async def reenviar_aviso(contrato_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    "Reenviar aviso": manda de novo para faturamento, contratos e ADM — ou
    pela primeira vez, se as tentativas automáticas falharam. Mesmas pessoas
    que podem cancelar um contrato em andamento.
    """
    contrato = await _linha_contrato(conn, contrato_id)
    if contrato["status"] != regras.STATUS_ASSINADO:
        raise HTTPException(409, "O aviso só sai depois que todos assinam.")
    if not _pode_cancelar({**contrato, "status": regras.STATUS_ENVIADO}, user):
        raise HTTPException(
            403, "Só quem mandou o contrato, o executivo da proposta ou a gestão "
                 "podem reenviar o aviso.",
        )
    if not aviso_ligado():
        raise HTTPException(503, "Nenhum destinatário configurado para o aviso "
                                 "(CONTRATO_AVISO_DESTINATARIOS no .env).")
    ok = await avisar_assinado(conn, contrato, forcar=True, usuario_id=user["id"])
    atualizado = await _linha_contrato(conn, contrato_id)
    if not ok:
        raise HTTPException(502, atualizado.get("aviso_erro") or "O aviso não pôde ser enviado.")
    return await _saida(conn, atualizado, user)


@router.get("/contratos/{contrato_id}/arquivo")
async def arquivo(
    contrato_id: UUID,
    tipo: str = Query("original", pattern="^(original|assinado)$"),
    conn=Depends(get_conn), user=Depends(usuario_atual),
):
    """
    O PDF original (o que foi para assinatura) ou o assinado (com carimbos e
    página de auditoria). Do S3 quando está lá; senão, da Autentique.
    """
    contrato = await _linha_contrato(conn, contrato_id)
    if tipo == "assinado" and contrato["status"] != regras.STATUS_ASSINADO:
        raise HTTPException(409, "O contrato ainda não foi assinado por todos.")

    chave = contrato["s3_chave_assinado" if tipo == "assinado" else "s3_chave_original"]
    corpo = None
    if chave and s3.disponivel():
        try:
            corpo = await asyncio.to_thread(_ler_s3, chave)
        except Exception as exc:  # noqa: BLE001
            log.warning("contrato %s: leitura do S3 falhou: %s", contrato_id, exc)
    if corpo is None:
        if not settings.AUTENTIQUE_API_TOKEN:
            raise HTTPException(503, "O arquivo não está guardado no HIPO e a "
                                     "integração com a Autentique está desligada.")
        try:
            documento = await autentique.consultar(contrato["autentique_id"])
            url = (documento.get("files") or {}).get("signed" if tipo == "assinado" else "original")
            if not url:
                raise HTTPException(404, "A Autentique ainda não tem este arquivo.")
            corpo = await autentique.baixar(url)
        except autentique.AutentiqueErro as e:
            raise HTTPException(502, str(e))
        if tipo == "assinado":
            await guardar_assinado(conn, contrato, documento)

    nome = regras.nome_arquivo(contrato["oportunidade_numero"], _razao_contratante(contrato),
                               contrato["versao"], assinado=tipo == "assinado")
    return Response(
        content=corpo, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def _ler_s3(chave: str) -> bytes:
    resp = s3._cliente().get_object(Bucket=settings.S3_BUCKET_ANEXOS, Key=chave)
    return resp["Body"].read()
