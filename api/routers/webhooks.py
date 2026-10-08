"""
HIPO — Webhooks de serviços externos (entrega 053: Autentique).

ÚNICO router sem login. Quem prova a origem é a assinatura HMAC-SHA256 do
corpo cru (header X-Autentique-Signature) com o segredo do endpoint
cadastrado no painel da Autentique — AUTENTIQUE_WEBHOOK_SEGREDO no .env.
Sem segredo configurado, tudo é recusado: webhook aberto deixaria qualquer
um forçar leituras na API da Autentique em nome do HIPO.

Endereço público: https://hipogestao.com.br/api/webhooks/autentique (o
nginx corta o /api).

O CONTEÚDO DO EVENTO NÃO É CONFIADO. Do corpo só se tira o id do documento
e o id do evento; o estado é lido de novo na API da Autentique
(crm_contratos.aplicar_documento). Evento fora de ordem, repetido ou
inventado dá no mesmo resultado.

RESPOSTAS
  200  processado, repetido (o mesmo event.id já entrou) ou documento que
       não é contrato do HIPO (criado no painel, por exemplo);
  401  assinatura ausente ou errada;
  503  segredo não configurado, ou a leitura na Autentique falhou — a
       Autentique tenta de novo em 1, 2 e 5 minutos, e o timer de
       sincronização cobre o resto.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from config import settings
from database import get_conn
from routers.crm_contratos import _linha_contrato, aplicar_documento, guardar_assinado
from services import autentique
from services import contrato as regras

log = logging.getLogger("hipo.webhooks")
router = APIRouter()


@router.post("/autentique")
async def autentique_webhook(request: Request, conn=Depends(get_conn)):
    segredo = settings.AUTENTIQUE_WEBHOOK_SEGREDO
    if not segredo:
        raise HTTPException(503, "Webhook da Autentique não configurado.")

    corpo = await request.body()
    if not regras.assinatura_webhook_valida(
        segredo, corpo, request.headers.get("x-autentique-signature"),
    ):
        raise HTTPException(401, "Assinatura do webhook inválida.")

    try:
        payload = json.loads(corpo or b"{}")
    except ValueError:
        raise HTTPException(400, "Corpo do webhook não é JSON.")
    evento = regras.ler_evento(payload if isinstance(payload, dict) else {})
    if not evento["documento_id"]:
        return {"ok": True, "ignorado": "evento sem documento"}

    contrato_id = await conn.fetchval(
        "SELECT id FROM contratos WHERE autentique_id = $1", evento["documento_id"],
    )
    if contrato_id is None:
        return {"ok": True, "ignorado": "documento não é contrato do HIPO"}

    if evento["id"]:
        ja = await conn.fetchval(
            "SELECT 1 FROM contrato_eventos WHERE evento_externo_id = $1", evento["id"],
        )
        if ja:
            return {"ok": True, "repetido": True}

    contrato = await _linha_contrato(conn, contrato_id)
    if contrato["status"] == regras.STATUS_CANCELADO:
        return {"ok": True, "ignorado": "contrato cancelado no HIPO"}

    try:
        documento = await autentique.consultar(contrato["autentique_id"])
    except autentique.AutentiqueErro as e:
        log.warning("webhook: leitura do documento %s falhou: %s",
                    contrato["autentique_id"], e)
        raise HTTPException(503, "Leitura do documento na Autentique falhou.")

    atualizado = await aplicar_documento(
        conn, contrato, documento, origem="webhook",
        evento_externo_id=evento["id"], evento_tipo=evento["tipo"],
    )
    await guardar_assinado(conn, atualizado, documento)
    return {"ok": True, "status": atualizado["status"]}
