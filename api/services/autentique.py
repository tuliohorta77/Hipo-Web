"""
HIPO — Cliente da API da Autentique (entrega 053).

API GraphQL única (https://api.autentique.com.br/v2/graphql), token Bearer.
Documentação: https://docs.autentique.com.br/api

O que usamos:
  * createDocument (multipart: operations + map + file) com os signatários,
    `sortable` (assinatura na ordem) e `stop_on_rejected`;
  * document(id) para ler o estado — é a fonte de verdade do contrato,
    tanto no webhook quanto no timer de sincronização;
  * resendSignatures(public_ids) para o "Reenviar" da tela;
  * updateDocument(deadline_at=agora) + deleteDocument no cancelamento.
    Só o delete não basta: com alguém já assinado, a Autentique apenas move
    o documento para a lixeira de quem pediu, e os demais ainda conseguem
    assinar. O prazo vencido é o que bloqueia.

FUNÇÕES PEQUENAS E DUBLÁVEIS. Os testes trocam `_post` (ou as funções
públicas) por dublês: a suíte nunca fala com a Autentique.

SANDBOX. Fora de produção todo documento sai como sandbox (não gasta
crédito, some em alguns dias). Um pytest ou um `uvicorn` local com o token
de produção no .env não pode mandar contrato de verdade para cliente.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from config import settings
from services.instancia import empresa_sigla

log = logging.getLogger("hipo.autentique")

TIMEOUT_S = 30.0
# O PDF do contrato tem ~100 KB; o teto do plano profissional é 20 MB.
TIMEOUT_UPLOAD_S = 60.0


class AutentiqueErro(RuntimeError):
    """Falha da API, com mensagem pronta para a tela."""


@dataclass
class Assinatura:
    public_id: str | None
    email: str | None
    nome: str | None
    acao: str | None
    link: str | None


@dataclass
class DocumentoCriado:
    id: str
    assinaturas: list[Assinatura]


# ── Configuração ─────────────────────────────────────────────────────

def em_sandbox() -> bool:
    if settings.ENVIRONMENT != "production":
        return True
    return bool(settings.AUTENTIQUE_SANDBOX)


def problemas() -> list[str]:
    """
    O que impede o envio, em linguagem de quem vai resolver. Vazio = pronto.
    A tela pergunta antes de mostrar o botão (GET /crm/contratos/situacao).
    """
    from services import contrato_render as render
    from services.proposta_render import libreoffice_disponivel

    achados = []
    if not settings.AUTENTIQUE_API_TOKEN:
        achados.append("AUTENTIQUE_API_TOKEN não configurado no .env")
    if not settings.CONTRATO_CONTRATADA_NOME or not settings.CONTRATO_CONTRATADA_EMAIL:
        achados.append(
            "CONTRATO_CONTRATADA_NOME e CONTRATO_CONTRATADA_EMAIL (quem assina pela "
            "contratada) não configurados no .env"
        )
    if empresa_sigla() and not (settings.CONTRATO_MODELO_ARQUIVO or "").strip():
        achados.append(
            "esta instância precisa do próprio modelo de contrato "
            "(CONTRATO_MODELO_ARQUIVO no .env); o padrão é o da Controller MedSeg"
        )
    elif not render.caminho_do_modelo().is_file():
        achados.append(f"modelo do contrato não encontrado em {render.caminho_do_modelo()}")
    if libreoffice_disponivel() is None:
        achados.append("LibreOffice não instalado no servidor (o PDF do contrato sai por ele)")
    return achados


def configurado() -> bool:
    return not problemas()


# ── Transporte ───────────────────────────────────────────────────────

def _cabecalhos() -> dict:
    return {"Authorization": f"Bearer {settings.AUTENTIQUE_API_TOKEN}"}


def _erro_legivel(corpo: dict) -> str:
    erros = corpo.get("errors") or []
    mensagens = []
    for e in erros:
        msg = e.get("message") if isinstance(e, dict) else str(e)
        # Erro de validação vem com o detalhe em extensions.validation.
        validacao = (e.get("extensions") or {}).get("validation") if isinstance(e, dict) else None
        if isinstance(validacao, dict):
            for campo, lista in validacao.items():
                mensagens.append(f"{campo}: {'; '.join(map(str, lista))}")
        elif msg:
            mensagens.append(msg)
    return "; ".join(mensagens) or "erro desconhecido"


def _traduzir(msg: str) -> str:
    """As mensagens que o usuário pode ver, em português."""
    conhecidas = {
        "too_many_resent_emails": "O e-mail de assinatura foi reenviado há pouco. "
                                  "Espere alguns minutos e tente de novo.",
        "unauthenticated": "A Autentique recusou o token do HIPO (AUTENTIQUE_API_TOKEN).",
        "not_found": "O documento não existe mais na Autentique.",
    }
    for chave, texto in conhecidas.items():
        if chave in msg.lower():
            return texto
    return f"A Autentique recusou o pedido: {msg}"


async def _post(*, json_body: dict | None = None, data: dict | None = None,
                files: dict | None = None, timeout: float = TIMEOUT_S) -> dict:
    """Uma chamada GraphQL. Devolve `data` ou levanta AutentiqueErro."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as cliente:
            resp = await cliente.post(
                settings.AUTENTIQUE_URL, headers=_cabecalhos(),
                json=json_body, data=data, files=files,
            )
    except httpx.HTTPError as exc:
        log.warning("autentique: falha de rede: %s", exc)
        raise AutentiqueErro(
            "Não foi possível falar com a Autentique agora. Tente de novo em instantes."
        ) from exc

    if resp.status_code in (401, 403):
        raise AutentiqueErro(_traduzir("unauthenticated"))
    try:
        corpo = resp.json()
    except ValueError as exc:
        raise AutentiqueErro(
            f"A Autentique respondeu {resp.status_code} sem JSON."
        ) from exc
    if corpo.get("errors"):
        msg = _erro_legivel(corpo)
        log.warning("autentique: erro GraphQL: %s", msg)
        raise AutentiqueErro(_traduzir(msg))
    if resp.status_code >= 400:
        raise AutentiqueErro(f"A Autentique respondeu {resp.status_code}.")
    return corpo.get("data") or {}


# ── Operações ────────────────────────────────────────────────────────

_CRIAR = (
    "mutation CriarDocumento($document: DocumentInput!, $signers: [SignerInput!]!, "
    "$file: Upload!, $sandbox: Boolean) { createDocument(document: $document, "
    "signers: $signers, file: $file, sandbox: $sandbox) { id name sortable "
    "signatures { public_id name email action { name } link { short_link } } } }"
)


def _assinaturas(lista) -> list[Assinatura]:
    saida = []
    for a in lista or []:
        user = a.get("user") or {}
        saida.append(Assinatura(
            public_id=a.get("public_id"),
            email=(a.get("email") or user.get("email") or None),
            nome=(a.get("name") or user.get("name") or None),
            acao=((a.get("action") or {}).get("name") if isinstance(a.get("action"), dict)
                  else a.get("action")),
            link=((a.get("link") or {}).get("short_link")
                  if isinstance(a.get("link"), dict) else None),
        ))
    return saida


async def criar_documento(
    *,
    nome: str,
    mensagem: str,
    pdf: bytes,
    nome_arquivo: str,
    signatarios: list[dict],
    posicoes: dict[str, dict] | None = None,
) -> DocumentoCriado:
    """
    signatarios: [{'papel', 'nome', 'email', 'acao'}], NA ORDEM de assinatura.
    posicoes: {papel: {'x', 'y', 'z'}} (contrato_render.localizar_assinaturas).
    """
    posicoes = posicoes or {}
    signers = []
    for s in signatarios:
        signer = {"email": s["email"], "action": s["acao"], "name": s["nome"]}
        pos = posicoes.get(s["papel"])
        if pos:
            signer["positions"] = [{
                "x": pos["x"], "y": pos["y"], "z": pos["z"], "element": "SIGNATURE",
            }]
        signers.append(signer)

    documento = {
        "name": nome,
        "message": mensagem,
        "sortable": True,
        "refusable": True,
        "stop_on_rejected": True,
        "reminder": "WEEKLY",
    }
    operacoes = {
        "query": _CRIAR,
        "variables": {
            "document": documento, "signers": signers, "file": None,
            "sandbox": em_sandbox(),
        },
    }
    dados = await _post(
        data={"operations": json.dumps(operacoes), "map": json.dumps({"file": ["variables.file"]})},
        files={"file": (nome_arquivo, pdf, "application/pdf")},
        timeout=TIMEOUT_UPLOAD_S,
    )
    criado = dados.get("createDocument") or {}
    if not criado.get("id"):
        raise AutentiqueErro("A Autentique não devolveu o id do documento.")
    return DocumentoCriado(id=criado["id"], assinaturas=_assinaturas(criado.get("signatures")))


# Os ids vão como LITERAL na consulta (json.dumps escapa), e não como
# variável: o tipo declarado da variável (String, UUID, ID) varia entre
# operações da Autentique, e declarar errado é erro de validação.
_CONSULTAR = """
query {
  document(id: %s) {
    id name created_at deleted_at
    files { original signed }
    signatures {
      public_id name email created_at
      action { name }
      link { short_link }
      user { name email }
      email_events { sent opened delivered refused reason }
      viewed { created_at }
      signed { created_at }
      rejected { reason created_at }
    }
  }
}
"""


async def consultar(documento_id: str) -> dict:
    """O documento como a Autentique o vê agora. None não existe: some = erro."""
    dados = await _post(json_body={"query": _CONSULTAR % json.dumps(str(documento_id))})
    doc = dados.get("document")
    if not doc:
        raise AutentiqueErro(_traduzir("not_found"))
    return doc


async def reenviar(public_ids: list[str]) -> None:
    if not public_ids:
        return
    ids = ", ".join(json.dumps(str(i)) for i in public_ids)
    await _post(json_body={"query": f"mutation {{ resendSignatures(public_ids: [{ids}]) }}"})


async def cancelar(documento_id: str, agora: datetime | None = None) -> None:
    """
    Bloqueia novas assinaturas (prazo = agora) e tira o documento da lista.
    O delete é melhor-esforço: o que bloqueia é o prazo.
    """
    agora = agora or datetime.now(timezone.utc)
    prazo = agora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    literal = json.dumps(str(documento_id))
    await _post(json_body={
        "query": (f"mutation {{ updateDocument(id: {literal}, document: "
                  f"{{ deadline_at: {json.dumps(prazo)} }}) {{ id }} }}"),
    })
    try:
        await _post(json_body={"query": f"mutation {{ deleteDocument(id: {literal}) }}"})
    except AutentiqueErro as exc:
        log.info("autentique: delete de %s falhou depois do bloqueio: %s", documento_id, exc)


async def baixar(url: str) -> bytes:
    """
    Baixa um arquivo do documento (files.original / files.signed). Manda o
    token: as URLs da API exigem autenticação em parte dos planos, e não
    custa nada mandar quando não exigem.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_UPLOAD_S, follow_redirects=True) as cliente:
            resp = await cliente.get(url, headers=_cabecalhos())
    except httpx.HTTPError as exc:
        raise AutentiqueErro("Não foi possível baixar o arquivo da Autentique agora.") from exc
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
        raise AutentiqueErro(
            f"A Autentique não entregou o PDF (resposta {resp.status_code})."
        )
    return resp.content
