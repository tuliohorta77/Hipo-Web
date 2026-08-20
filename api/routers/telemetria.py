"""
HIPO — CRM: leitura da telemetria (gestão).

Dois endpoints, ambos de leitura:

  GET /telemetria/dia          — métricas de um dia (padrão: hoje, ao vivo)
  GET /telemetria/relatorios   — os últimos fechamentos já gravados

O de hoje calcula na hora, em cima de uso_eventos; o de fechamento lê o JSONB
congelado. É a mesma estrutura nos dois casos, então a tela que consumir isso
não precisa saber de onde veio.

Este router NÃO cria nada e não expõe corpo de request — a tabela de origem
guarda template de rota, nunca o path com ids (ver migrations/007).

Módulo 'telemetria': só gestão. Não é sigilo, é ruído — mostrar para o SDR
quantas ações o colega fez transforma a ferramenta em painel de vigilância
entre pares, que é o jeito mais rápido de a equipe parar de usar o sistema.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_conn
from routers.auth import usuario_atual
from services import telemetria as tel

router = APIRouter()


@router.get("/dia")
async def dia(
    data: date | None = Query(None, description="AAAA-MM-DD. Padrão: hoje."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Métricas de um dia.

    Se já existe fechamento gravado para a data, devolve o congelado (é o
    mesmo número que foi para o e-mail — divergir do que a pessoa recebeu
    seria pior que estar desatualizado). Caso contrário, calcula ao vivo.
    """
    alvo = data or date.today()

    fechado = await conn.fetchrow("""
        SELECT metricas, narrativa, narrativa_modelo, enviado_em, gerado_em
        FROM relatorios_diarios WHERE dia = $1
    """, alvo)

    if fechado:
        m = fechado["metricas"]
        return {
            "origem": "fechamento",
            "metricas": json.loads(m) if isinstance(m, str) else m,
            "narrativa": fechado["narrativa"],
            "narrativa_modelo": fechado["narrativa_modelo"],
            "gerado_em": fechado["gerado_em"],
            "enviado_em": fechado["enviado_em"],
        }

    return {
        "origem": "ao_vivo",
        "metricas": await tel.metricas_do_dia(conn, alvo),
        "narrativa": None,
        "narrativa_modelo": None,
        "gerado_em": None,
        "enviado_em": None,
    }


@router.get("/relatorios")
async def relatorios(
    limit: int = Query(30, ge=1, le=180),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """Últimos fechamentos, do mais recente para o mais antigo."""
    linhas = await conn.fetch("""
        SELECT dia, metricas, narrativa IS NOT NULL AS tem_narrativa,
               enviado_em, erro
        FROM relatorios_diarios
        ORDER BY dia DESC
        LIMIT $1
    """, limit)

    itens = []
    for r in linhas:
        m = r["metricas"]
        m = json.loads(m) if isinstance(m, str) else (m or {})
        itens.append({
            "dia": r["dia"].isoformat(),
            "acoes": m.get("adocao", {}).get("acoes"),
            "pessoas_ativas": m.get("adocao", {}).get("pessoas_ativas"),
            "erros": m.get("adocao", {}).get("erros"),
            "oportunidades_criadas": m.get("operacao", {}).get("oportunidades_criadas"),
            "tarefas_concluidas": m.get("operacao", {}).get("tarefas_concluidas"),
            "tem_narrativa": r["tem_narrativa"],
            "enviado_em": r["enviado_em"],
            "erro": r["erro"],
        })
    return {"itens": itens, "total": len(itens)}


@router.get("/relatorios/{dia_iso}")
async def relatorio(dia_iso: date, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """Um fechamento específico, com a narrativa completa."""
    r = await conn.fetchrow("""
        SELECT dia, metricas, narrativa, narrativa_modelo, destinatarios,
               enviado_em, erro, gerado_em
        FROM relatorios_diarios WHERE dia = $1
    """, dia_iso)
    if not r:
        raise HTTPException(404, f"Não há fechamento gravado para {dia_iso.isoformat()}.")
    m = r["metricas"]
    return {
        "dia": r["dia"].isoformat(),
        "metricas": json.loads(m) if isinstance(m, str) else m,
        "narrativa": r["narrativa"],
        "narrativa_modelo": r["narrativa_modelo"],
        "destinatarios": r["destinatarios"],
        "enviado_em": r["enviado_em"],
        "erro": r["erro"],
        "gerado_em": r["gerado_em"],
    }
