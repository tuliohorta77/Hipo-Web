"""
HIPO — CRM: e-mail comercial pela Gmail API (entrega 050).

O vendedor manda, de dentro da oportunidade, os dois e-mails que já mandava
à mão — primeiro contato e envio de proposta — e o e-mail sai da caixa
DELE, com a assinatura DELE. O HIPO grava o que saiu e acompanha se o
cliente respondeu.

Rotas (prefixo /crm, módulo `crm`):

  GET  /email/modelos                         modelos, variáveis e se o Gmail está ligado
  PUT  /email/modelos/{slug}                  gestão edita um modelo
  GET  /oportunidades/{id}/emails             o que já saiu desta oportunidade
  POST /oportunidades/{id}/emails/rascunho    modelo preenchido para um contato
  POST /oportunidades/{id}/emails             envia (e grava)
  POST /oportunidades/{id}/emails/verificar   olha agora se o cliente respondeu

Decisões que este módulo materializa:

  * RASCUNHO E ENVIO SÃO DUAS CHAMADAS. O rascunho preenche o modelo; o
    vendedor lê, edita e manda. O envio manda o texto que veio da tela —
    não remonta o modelo —, porque o que o vendedor aprovou é o que o
    cliente tem que receber.

  * O REMETENTE É QUEM ESTÁ LOGADO. Não há "enviar como" outra pessoa: o
    cliente responde para quem mandou, e é essa pessoa que precisa ver a
    resposta.

  * SÓ O QUE SAIU É GRAVADO. Falha do Gmail volta como 502 com a frase em
    português, e nada fica no banco. Diferente da agenda, que grava a
    reunião e mostra "sem convite": lá a reunião existe mesmo sem o
    Google; aqui, e-mail que não saiu não existe.

  * O PDF É REMONTADO NO ENVIO, pela mesma rota do download
    (crm_propostas._montar_pptx + render.para_pdf). A proposta continua sem
    arquivo guardado; o que o cliente recebe é o mesmo que o vendedor
    baixaria naquele momento.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status as http
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from routers.crm_propostas import _buscar as buscar_proposta
from routers.crm_propostas import _eh_gestao, _montar_pptx
from services import cnpj as cnpj_svc
from services import email_comercial as regras
from services import gmail
from services import proposta as regras_proposta
from services import proposta_render as render
from services.instancia import empresa_nome

router = APIRouter()

# Quanto tempo depois do envio a verificação automática segue olhando o
# fio. Depois disso, quem não respondeu em um mês não vai responder a este
# e-mail — é assunto do próximo Touch, não deste.
JANELA_VERIFICACAO_DIAS = 30


# ── Schemas ──────────────────────────────────────────────────────────

class VariavelOut(BaseModel):
    nome: str
    rotulo: str
    exemplo: str


class ModeloOut(BaseModel):
    slug: str
    nome: str
    assunto: str
    corpo: str
    anexa_proposta: bool
    ordem: int
    atualizado_em: datetime | None = None
    atualizado_por_nome: str | None = None


class SituacaoOut(BaseModel):
    ligado: bool
    problemas: list[str]
    remetente: str


class ModelosOut(BaseModel):
    modelos: list[ModeloOut]
    variaveis: list[VariavelOut]
    gmail: SituacaoOut
    pode_editar: bool
    pdf_disponivel: bool


class ModeloIn(BaseModel):
    nome: str = Field(..., max_length=80)
    assunto: str = Field(..., max_length=250)
    corpo: str = Field(..., max_length=regras.MAX_CORPO)


class RascunhoIn(BaseModel):
    modelo: str | None = Field(None, description="slug do modelo; vazio = em branco")
    contato_id: UUID
    proposta_id: UUID | None = None
    proposta_item_id: UUID | None = None


class RascunhoOut(BaseModel):
    modelo: str | None
    para: list[str]
    assunto: str
    corpo: str
    anexo_nome: str | None
    assinatura: bool
    avisos: list[str]


class EnvioIn(BaseModel):
    contato_id: UUID
    para: list[str] = Field(..., min_length=1)
    cc: list[str] = Field(default_factory=list)
    assunto: str = Field(..., max_length=regras.MAX_ASSUNTO)
    corpo: str = Field(..., max_length=regras.MAX_CORPO)
    modelo: str | None = None
    proposta_id: UUID | None = None
    proposta_item_id: UUID | None = None


class EmailOut(BaseModel):
    id: UUID
    oportunidade_id: UUID
    contato_id: UUID | None
    contato_nome: str | None
    modelo_slug: str | None
    modelo_nome: str | None
    proposta_id: UUID | None
    proposta_versao: int | None
    anexo_nome: str | None
    remetente_id: UUID
    remetente_nome: str | None
    remetente_email: str
    para: list[str]
    cc: list[str]
    assunto: str
    corpo: str
    com_assinatura: bool
    gmail_thread_id: str | None
    enviado_em: datetime
    respondido_em: datetime | None
    resposta_de: str | None
    verificado_em: datetime | None
    verificacao_erro: str | None


class VerificacaoOut(BaseModel):
    verificados: int
    respondidos: int
    erros: list[str]


# ── Helpers ──────────────────────────────────────────────────────────

def _situacao(user: dict) -> dict:
    ligado = gmail.configurado()
    return {
        "ligado": ligado,
        "problemas": gmail.problemas() if ligado else [
            "Integração com o Google desligada neste servidor (GOOGLE_SA_ARQUIVO vazio)."
        ],
        "remetente": user["email"],
    }


async def _modelos(conn) -> list[dict]:
    """Os do banco; os do código para o que faltar (base nova, teste)."""
    rows = await conn.fetch(
        """
        SELECT m.slug, m.nome, m.assunto, m.corpo, m.anexa_proposta, m.ordem,
               m.atualizado_em, u.nome AS atualizado_por_nome
          FROM email_modelos m
          LEFT JOIN usuarios u ON u.id = m.atualizado_por
        """
    )
    por_slug = {r["slug"]: dict(r) for r in rows}
    for slug, padrao in regras.MODELOS_PADRAO.items():
        por_slug.setdefault(slug, {**padrao, "atualizado_em": None,
                                   "atualizado_por_nome": None})
    return sorted(por_slug.values(), key=lambda m: (m["ordem"], m["slug"]))


async def _modelo(conn, slug: str) -> dict:
    m = next((m for m in await _modelos(conn) if m["slug"] == slug), None)
    if m is None:
        raise HTTPException(404, "Modelo de e-mail não encontrado.")
    return m


async def _oportunidade(conn, oportunidade_id: UUID) -> dict:
    row = await conn.fetchrow(
        """
        SELECT o.id, o.numero, o.status, o.conta_id,
               c.razao_social, c.nome_fantasia, c.cnpj
          FROM oportunidades o
          JOIN contas c ON c.id = o.conta_id
         WHERE o.id = $1
        """,
        oportunidade_id,
    )
    if not row:
        raise HTTPException(404, "Oportunidade não encontrada.")
    return dict(row)


async def _contato(conn, oportunidade_id: UUID, contato_id: UUID) -> dict:
    """
    O contato precisa ser da empresa (CNPJ principal ou adicional) ou do
    comitê da oportunidade — o mesmo universo do seletor de contato da
    tarefa (GET /crm/contatos/por-alvo).
    """
    row = await conn.fetchrow(
        """
        WITH contas_opp AS (
            SELECT o.conta_id FROM oportunidades o WHERE o.id = $1
            UNION
            SELECT oc.conta_id FROM oportunidade_contas oc
             WHERE oc.oportunidade_id = $1 AND oc.removido_em IS NULL
        )
        SELECT ct.id, ct.nome, ct.email
          FROM contatos ct
         WHERE ct.id = $2 AND ct.ativo
           AND (
                EXISTS (SELECT 1 FROM conta_contatos cc
                         WHERE cc.contato_id = ct.id AND cc.ativo
                           AND cc.conta_id IN (SELECT conta_id FROM contas_opp))
             OR EXISTS (SELECT 1 FROM oportunidade_contatos x
                         WHERE x.oportunidade_id = $1 AND x.contato_id = ct.id)
           )
        """,
        oportunidade_id, contato_id,
    )
    if not row:
        raise HTTPException(
            422, "Este contato não é da empresa nem do comitê desta oportunidade.",
        )
    return dict(row)


async def _proposta_escolhida(
    conn, oportunidade_id: UUID, proposta_id: UUID | None, item_id: UUID | None,
) -> tuple[dict | None, dict | None]:
    if proposta_id is None:
        if item_id is not None:
            raise HTTPException(422, "Escolha a proposta antes do CNPJ.")
        return None, None
    proposta = await buscar_proposta(conn, proposta_id)
    if proposta["oportunidade_id"] != oportunidade_id:
        raise HTTPException(422, "Esta proposta é de outra oportunidade.")
    item = None
    if item_id is not None:
        item = next((i for i in proposta["itens"] if i["id"] == item_id), None)
        if item is None:
            raise HTTPException(422, "Este CNPJ não faz parte desta proposta.")
    return proposta, item


def _nome_anexo(numero: str, proposta: dict, item: dict | None) -> str:
    return regras_proposta.nome_do_arquivo(
        numero or "PROPOSTA",
        item["razao_social"] if item else proposta["cliente_razao_social"],
        proposta["versao"], "pdf",
        cnpj=item["cnpj"] if item else None,
    )


def _valores(opp: dict, contato: dict, user: dict, proposta, item,
             agora: datetime) -> dict:
    alvo_proposta = None
    if proposta is not None:
        alvo_proposta = {
            "mensalidade": item["mensalidade"] if item else proposta["mensalidade"],
            "vidas": item["vidas"] if item else proposta["vidas"],
            "validade": proposta["validade"],
        }
    return regras.valores(
        agora=agora,
        contato_nome=contato["nome"],
        razao_social=(item or {}).get("razao_social") or opp["razao_social"],
        nome_fantasia=None if item else opp["nome_fantasia"],
        cnpj_formatado=cnpj_svc.formatar((item or {}).get("cnpj") or opp["cnpj"]),
        remetente_nome=user.get("nome"),
        remetente_telefone=user.get("telefone"),
        nossa_empresa=empresa_nome(),
        proposta=alvo_proposta,
    )


_SELECT_EMAIL = """
    SELECT e.*, ct.nome AS contato_nome, u.nome AS remetente_nome,
           m.nome AS modelo_nome, p.versao AS proposta_versao
      FROM emails_enviados e
      LEFT JOIN contatos ct    ON ct.id = e.contato_id
      LEFT JOIN usuarios u     ON u.id = e.remetente_id
      LEFT JOIN email_modelos m ON m.slug = e.modelo_slug
      LEFT JOIN propostas p    ON p.id = e.proposta_id
"""


def _email_out(row) -> dict:
    d = dict(row)
    if d.get("modelo_nome") is None and d.get("modelo_slug") in regras.MODELOS_PADRAO:
        d["modelo_nome"] = regras.MODELOS_PADRAO[d["modelo_slug"]]["nome"]
    d["para"] = list(d.get("para") or [])
    d["cc"] = list(d.get("cc") or [])
    return d


async def verificar_um(conn, email: dict, *, agora: datetime | None = None) -> str:
    """
    Olha o fio de UM e-mail e grava o resultado. Devolve 'respondido',
    'sem_resposta' ou 'erro'. Compartilhado com
    scripts/verificar_respostas_email.
    """
    agora = agora or datetime.now(timezone.utc)
    r = await gmail.fio(email["remetente_email"], email["gmail_thread_id"])
    if r.erro:
        await conn.execute(
            "UPDATE emails_enviados SET verificado_em = $2, verificacao_erro = $3 WHERE id = $1",
            email["id"], agora, r.erro[:500],
        )
        return "erro"
    resposta = regras.detectar_resposta(
        r.thread or {}, email["gmail_message_id"], email["remetente_email"],
    )
    await conn.execute(
        """
        UPDATE emails_enviados
           SET verificado_em = $2, verificacao_erro = NULL,
               respondido_em = COALESCE(respondido_em, $3),
               resposta_de   = COALESCE(resposta_de, $4)
         WHERE id = $1
        """,
        email["id"], agora,
        resposta.em if resposta else None,
        resposta.de if resposta else None,
    )
    return "respondido" if resposta else "sem_resposta"


async def pendentes_de_verificacao(
    conn, *, oportunidade_id: UUID | None = None, agora: datetime | None = None,
) -> list[dict]:
    agora = agora or datetime.now(timezone.utc)
    rows = await conn.fetch(
        """
        SELECT id, remetente_email, gmail_message_id, gmail_thread_id
          FROM emails_enviados
         WHERE respondido_em IS NULL
           AND gmail_thread_id IS NOT NULL
           AND enviado_em >= $1
           AND ($2::uuid IS NULL OR oportunidade_id = $2)
         ORDER BY verificado_em NULLS FIRST, enviado_em
        """,
        agora - timedelta(days=JANELA_VERIFICACAO_DIAS), oportunidade_id,
    )
    return [dict(r) for r in rows]


# ── Modelos ──────────────────────────────────────────────────────────

@router.get("/email/modelos", response_model=ModelosOut)
async def listar_modelos(conn=Depends(get_conn), user=Depends(usuario_atual)):
    return {
        "modelos": await _modelos(conn),
        "variaveis": [v.__dict__ for v in regras.VARIAVEIS],
        "gmail": _situacao(user),
        "pode_editar": _eh_gestao(user),
        "pdf_disponivel": render.libreoffice_disponivel() is not None,
    }


@router.put("/email/modelos/{slug}", response_model=ModeloOut)
async def salvar_modelo(
    slug: str, payload: ModeloIn, conn=Depends(get_conn), user=Depends(usuario_atual),
):
    if not _eh_gestao(user):
        raise HTTPException(403, "Só a gestão edita os modelos de e-mail.")
    atual = await _modelo(conn, slug)
    try:
        nome, assunto, corpo = regras.validar_modelo(
            payload.nome, payload.assunto, payload.corpo,
        )
    except regras.EmailInvalido as e:
        raise HTTPException(422, str(e))
    await conn.execute(
        """
        INSERT INTO email_modelos (slug, nome, assunto, corpo, anexa_proposta,
                                   ordem, atualizado_por, atualizado_em)
        VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
        ON CONFLICT (slug) DO UPDATE
           SET nome = EXCLUDED.nome, assunto = EXCLUDED.assunto,
               corpo = EXCLUDED.corpo, atualizado_por = EXCLUDED.atualizado_por,
               atualizado_em = NOW()
        """,
        slug, nome, assunto, corpo, atual["anexa_proposta"], atual["ordem"],
        user["id"],
    )
    return await _modelo(conn, slug)


# ── E-mails da oportunidade ──────────────────────────────────────────

@router.get("/oportunidades/{oportunidade_id}/emails", response_model=list[EmailOut])
async def listar(
    oportunidade_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual),
):
    await _oportunidade(conn, oportunidade_id)
    rows = await conn.fetch(
        _SELECT_EMAIL + " WHERE e.oportunidade_id = $1 ORDER BY e.enviado_em DESC",
        oportunidade_id,
    )
    return [_email_out(r) for r in rows]


@router.post("/oportunidades/{oportunidade_id}/emails/rascunho",
             response_model=RascunhoOut)
async def rascunho(
    oportunidade_id: UUID, payload: RascunhoIn,
    conn=Depends(get_conn), user=Depends(usuario_atual),
):
    opp = await _oportunidade(conn, oportunidade_id)
    contato = await _contato(conn, oportunidade_id, payload.contato_id)
    proposta, item = await _proposta_escolhida(
        conn, oportunidade_id, payload.proposta_id, payload.proposta_item_id,
    )

    avisos: list[str] = []
    if payload.modelo:
        modelo = await _modelo(conn, payload.modelo)
        if modelo["anexa_proposta"] and proposta is None:
            avisos.append("Este modelo é para enviar a proposta: escolha a versão a anexar.")
        vals = _valores(opp, contato, user, proposta, item, datetime.now(timezone.utc))
        assunto = regras.preencher(modelo["assunto"], vals)
        corpo = regras.preencher(modelo["corpo"], vals)
        avisos += regras.avisos_de_ausencia(assunto.ausentes + corpo.ausentes)
        assunto_txt, corpo_txt = " ".join(assunto.texto.split()), corpo.texto
    else:
        assunto_txt, corpo_txt = "", ""

    para = [contato["email"]] if contato.get("email") else []
    if not para:
        avisos.append(
            f"{contato['nome']} não tem e-mail no cadastro. Digite o endereço "
            "abaixo (e vale atualizar o contato)."
        )

    anexo_nome = None
    if proposta is not None:
        anexo_nome = _nome_anexo(opp["numero"], proposta, item)
        if render.libreoffice_disponivel() is None:
            avisos.append(
                "O servidor não gera PDF (LibreOffice ausente), então a proposta "
                "não pode ser anexada agora."
            )

    tem_assinatura = False
    if gmail.configurado():
        a = await gmail.assinatura(user["email"])
        if a.erro:
            avisos.append(f"A sua assinatura do Gmail não pôde ser lida: {a.erro} "
                          "O e-mail sai sem ela.")
        elif a.html:
            tem_assinatura = True
        else:
            avisos.append("Você não tem assinatura configurada no Gmail — o e-mail sai sem ela.")
    else:
        avisos.append("O envio pelo Gmail está desligado neste servidor.")

    return {
        "modelo": payload.modelo, "para": para, "assunto": assunto_txt,
        "corpo": corpo_txt, "anexo_nome": anexo_nome,
        "assinatura": tem_assinatura, "avisos": avisos,
    }


@router.post("/oportunidades/{oportunidade_id}/emails",
             response_model=EmailOut, status_code=http.HTTP_201_CREATED)
async def enviar(
    oportunidade_id: UUID, payload: EnvioIn,
    conn=Depends(get_conn), user=Depends(usuario_atual),
):
    opp = await _oportunidade(conn, oportunidade_id)
    contato = await _contato(conn, oportunidade_id, payload.contato_id)
    if payload.modelo:
        await _modelo(conn, payload.modelo)
    proposta, item = await _proposta_escolhida(
        conn, oportunidade_id, payload.proposta_id, payload.proposta_item_id,
    )

    try:
        envio = regras.validar_envio(
            para=payload.para, cc=payload.cc, assunto=payload.assunto,
            corpo=payload.corpo, remetente_email=user["email"],
        )
    except regras.EmailInvalido as e:
        raise HTTPException(422, str(e))

    if not gmail.configurado():
        raise HTTPException(503, "O envio pelo Gmail está desligado neste servidor.")

    anexo = None
    if proposta is not None:
        try:
            pptx = _montar_pptx(proposta, item)
            # LibreOffice e subprocesso de segundos: fora do event loop.
            pdf = await asyncio.to_thread(render.para_pdf, pptx)
        except (render.ModeloIndisponivel, render.BibliotecaIndisponivel,
                render.PdfIndisponivel) as e:
            raise HTTPException(503, f"A proposta não pôde ser anexada: {e}")
        anexo = regras.Anexo(_nome_anexo(opp["numero"], proposta, item), pdf)

    a = await gmail.assinatura(user["email"])
    try:
        mensagem = regras.montar_mensagem(
            remetente_nome=user.get("nome") or "",
            remetente_email=user["email"],
            envio=envio, assinatura_html=a.html, anexo=anexo,
        )
    except regras.EmailInvalido as e:
        raise HTTPException(422, str(e))

    resultado = await gmail.enviar(user["email"], mensagem)
    if not resultado.ok:
        raise HTTPException(502, resultado.erro or "O Gmail recusou o envio.")

    novo_id = await conn.fetchval(
        """
        INSERT INTO emails_enviados (
            oportunidade_id, contato_id, modelo_slug, proposta_id,
            proposta_item_id, anexo_nome, remetente_id, remetente_email,
            para, cc, assunto, corpo, com_assinatura,
            gmail_message_id, gmail_thread_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        RETURNING id
        """,
        oportunidade_id, contato["id"], payload.modelo,
        proposta["id"] if proposta else None, item["id"] if item else None,
        anexo.nome if anexo else None, user["id"], user["email"],
        envio.para, envio.cc, envio.assunto, envio.corpo, bool(a.html),
        resultado.message_id, resultado.thread_id,
    )
    row = await conn.fetchrow(_SELECT_EMAIL + " WHERE e.id = $1", novo_id)
    return _email_out(row)


@router.post("/oportunidades/{oportunidade_id}/emails/verificar",
             response_model=VerificacaoOut)
async def verificar(
    oportunidade_id: UUID, conn=Depends(get_conn), user=Depends(usuario_atual),
):
    """O botão "ver se respondeu": a mesma passada do timer, só desta oportunidade."""
    await _oportunidade(conn, oportunidade_id)
    if not gmail.configurado():
        raise HTTPException(503, "A integração com o Google está desligada neste servidor.")
    pendentes = await pendentes_de_verificacao(conn, oportunidade_id=oportunidade_id)
    respondidos, erros = 0, []
    for e in pendentes:
        estado = await verificar_um(conn, e)
        if estado == "respondido":
            respondidos += 1
        elif estado == "erro":
            msg = await conn.fetchval(
                "SELECT verificacao_erro FROM emails_enviados WHERE id = $1", e["id"],
            )
            if msg and msg not in erros:
                erros.append(msg)
    return {"verificados": len(pendentes), "respondidos": respondidos, "erros": erros}
