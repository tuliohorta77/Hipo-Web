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
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status as http
from pydantic import BaseModel, Field, field_validator

from database import get_conn
from routers.auth import usuario_atual
from services import proposta as regras
from services import proposta_render as render

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class PropostaIn(BaseModel):
    vidas: int = Field(..., ge=1, le=regras.MAX_VIDAS)
    valor_por_vida: Decimal = Field(..., gt=0)
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


class PropostaOut(BaseModel):
    id: UUID
    oportunidade_id: UUID
    versao: int
    vidas: int
    valor_por_vida: Decimal
    treinamentos: Decimal
    laudos: Decimal
    # Derivados, calculados na leitura: ver a nota do schema.
    mensalidade: Decimal
    investimento: Decimal
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
    vidas: int | None
    valor_por_vida: Decimal | None
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

def _linha(row) -> dict:
    d = dict(row)
    escopo = d.get("escopo")
    d["escopo"] = json.loads(escopo) if isinstance(escopo, str) else (escopo or [])
    mensal = regras.mensalidade(d["vidas"], d["valor_por_vida"])
    d["mensalidade"] = mensal
    d["investimento"] = regras.investimento(mensal, d["treinamentos"], d["laudos"])
    return d


async def _oportunidade(conn, oportunidade_id: UUID) -> dict:
    row = await conn.fetchrow(
        """
        SELECT o.id, o.numero, o.conta_id, c.razao_social
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
         WHERE o.id = $1
        """,
        oportunidade_id,
    )
    if not row:
        raise HTTPException(404, "Oportunidade não encontrada.")
    return dict(row)


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
    return _linha(row)


def _montar_pptx(proposta: dict) -> bytes:
    subs = regras.substituicoes(
        cliente=proposta["cliente_razao_social"],
        vidas=proposta["vidas"],
        valor_por_vida=proposta["valor_por_vida"],
        treinamentos=proposta["treinamentos"],
        laudos=proposta["laudos"],
        executivo_nome=proposta["executivo_nome"],
        executivo_email=proposta["executivo_email"],
        executivo_telefone=proposta["executivo_telefone"],
        data_proposta=proposta["data_proposta"],
        validade=proposta["validade"],
        cidade=proposta["cidade"],
    )
    return render.montar_pptx(subs, proposta["escopo"])


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
    cliente da oportunidade e a última proposta como ponto de partida.

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
        SELECT vidas, valor_por_vida FROM propostas
         WHERE oportunidade_id = $1
         ORDER BY versao DESC LIMIT 1
        """,
        oportunidade_id,
    )

    return {
        "escopo_padrao": regras.ESCOPO_PADRAO,
        "cidade": regras.CIDADE_PADRAO,
        "dias_validade": regras.DIAS_VALIDADE_PADRAO,
        "vidas": ultima["vidas"] if ultima else None,
        "valor_por_vida": ultima["valor_por_vida"] if ultima else None,
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
    return [_linha(r) for r in rows]


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

    A mensalidade calculada aqui também atualiza `valor_mensalidade` da
    oportunidade: o funil soma ticket, e uma proposta enviada por R$ 1.200
    com o funil marcando R$ 900 faz a previsão do mês mentir. Só sobe o
    valor da proposta mais nova — versões antigas não reescrevem o funil.
    """
    opp = await _oportunidade(conn, oportunidade_id)
    executivo = await _executivo(conn, payload.executivo_id, user)

    try:
        regras.validar(
            vidas=payload.vidas,
            valor_por_vida=payload.valor_por_vida,
            treinamentos=payload.treinamentos,
            laudos=payload.laudos,
            escopo=payload.escopo,
            data_proposta=payload.data_proposta,
            validade=payload.validade,
        )
    except regras.PropostaInvalida as erro:
        raise HTTPException(422, str(erro))

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
                executivo_email, executivo_telefone, criado_por
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16)
            RETURNING *
            """,
            oportunidade_id, proxima, payload.vidas, payload.valor_por_vida,
            payload.treinamentos, payload.laudos, json.dumps(payload.escopo),
            payload.cidade.strip(), payload.data_proposta, payload.validade,
            opp["razao_social"], executivo["id"], executivo["nome"],
            executivo["email"], executivo.get("telefone"), user["id"],
        )

        await conn.execute(
            """
            UPDATE oportunidades
               SET valor_mensalidade = $2, atualizado_em = NOW()
             WHERE id = $1
            """,
            oportunidade_id,
            regras.mensalidade(payload.vidas, payload.valor_por_vida),
        )

    d = _linha(row)
    d["criado_por_nome"] = user["nome"]
    return d


# ── Download ─────────────────────────────────────────────────────────

@router.get("/propostas/{proposta_id}/arquivo")
async def baixar(
    proposta_id: UUID,
    formato: str = Query("pptx", pattern="^(pptx|pdf)$"),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Remonta o arquivo a partir do modelo e devolve para download.

    Erro de modelo ou de conversão vira 503 com a mensagem pronta para a
    tela — é falha de ambiente do servidor, não pedido inválido, e o
    vendedor precisa saber que o PPTX continua funcionando.
    """
    proposta = await _buscar(conn, proposta_id)

    numero = await conn.fetchval(
        "SELECT numero FROM oportunidades WHERE id = $1",
        proposta["oportunidade_id"],
    )

    try:
        pptx = _montar_pptx(proposta)
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
        numero or "PROPOSTA", proposta["cliente_razao_social"],
        proposta["versao"], formato,
    )
    return Response(
        content=corpo,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
