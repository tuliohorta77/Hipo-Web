"""
HIPO — CRM: leitura da telemetria (gestão).

Endpoints, todos de leitura:

  GET /telemetria/dia          — métricas de um dia (padrão: hoje, ao vivo)
  GET /telemetria/relatorios   — os últimos fechamentos já gravados
  GET /telemetria/leituras-sensiveis — quem leu dado pessoal (032)
  GET /telemetria/logins       — histórico de tentativas de login (032)

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
from uuid import UUID

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


# ── Trilhas de seguranca (032) ───────────────────────────────────────
#
# Leitura de gestao, mesmo modulo 'telemetria'. Quem pode ver QUEM leu o
# dado de quem e a gestao -- e o pedido do titular (LGPD) chega a ela.
# Nenhuma das duas rotas grava; as linhas nascem em services/auditoria e
# services/login_limite.

def _intervalo(desde: date | None, ate: date | None) -> tuple[date | None, date | None]:
    if desde and ate and desde > ate:
        raise HTTPException(422, "'desde' precisa ser anterior ou igual a 'ate'.")
    return desde, ate


@router.get("/leituras-sensiveis")
async def leituras_sensiveis(
    registro_id: UUID | None = Query(
        None, description="Quem leu ESTE contato/socio. O pedido do titular."
    ),
    usuario_id: UUID | None = Query(None, description="O que esta pessoa leu."),
    recurso: str | None = Query(None, max_length=30),
    desde: date | None = Query(None, description="AAAA-MM-DD, inclusive."),
    ate: date | None = Query(None, description="AAAA-MM-DD, inclusive."),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    A trilha de leitura de dado pessoal, mais recente primeiro.

    `registro_id` usa o indice GIN de `registro_ids`: "quem viu a Fulana"
    responde sem varrer a tabela. Datas no fuso de Sao Paulo, que e o dia
    que a pessoa que pergunta tem na cabeca.
    """
    desde, ate = _intervalo(desde, ate)
    where, params = [], []

    def add(clausula: str, valor) -> None:
        params.append(valor)
        where.append(clausula.format(n=len(params)))

    if registro_id is not None:
        add("l.registro_ids @> ARRAY[${n}::uuid]", registro_id)
    if usuario_id is not None:
        add("l.usuario_id = ${n}", usuario_id)
    if recurso:
        add("l.recurso = ${n}", recurso.strip())
    if desde:
        add("(l.criado_em AT TIME ZONE 'America/Sao_Paulo')::date >= ${n}", desde)
    if ate:
        add("(l.criado_em AT TIME ZONE 'America/Sao_Paulo')::date <= ${n}", ate)

    clausula = f"WHERE {' AND '.join(where)}" if where else ""
    total = await conn.fetchval(f"SELECT count(*) FROM leituras_sensiveis l {clausula}", *params)
    linhas = await conn.fetch(
        f"""
        SELECT l.id, l.criado_em, l.usuario_id, l.usuario_email,
               u.nome AS usuario_nome, l.cargo, l.recurso, l.rota,
               l.registro_ids, l.contexto, l.ip
          FROM leituras_sensiveis l
          LEFT JOIN usuarios u ON u.id = l.usuario_id
          {clausula}
         ORDER BY l.criado_em DESC, l.id DESC
         LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )
    itens = []
    for r in linhas:
        d = dict(r)
        ctx = d.get("contexto")
        d["contexto"] = json.loads(ctx) if isinstance(ctx, str) else (ctx or {})
        d["registro_ids"] = [str(i) for i in (d.get("registro_ids") or [])]
        itens.append(d)
    return {"total": total, "limit": limit, "offset": offset, "itens": itens}


@router.get("/logins")
async def logins(
    email: str | None = Query(None, max_length=150),
    ip: str | None = Query(None, max_length=64),
    so_falhas: bool = False,
    desde: date | None = Query(None),
    ate: date | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Historico de tentativas de login -- o que o JWT stateless nao guarda.

    `resumo` traz as falhas das ultimas 24 h por motivo: e o numero que diz
    se alguem esta martelando o login agora.
    """
    desde, ate = _intervalo(desde, ate)
    where, params = [], []

    def add(clausula: str, valor) -> None:
        params.append(valor)
        where.append(clausula.format(n=len(params)))

    if email:
        add("t.email = ${n}", email.strip().lower())
    if ip:
        add("t.ip = ${n}", ip.strip())
    if so_falhas:
        where.append("NOT t.sucesso")
    if desde:
        add("(t.criado_em AT TIME ZONE 'America/Sao_Paulo')::date >= ${n}", desde)
    if ate:
        add("(t.criado_em AT TIME ZONE 'America/Sao_Paulo')::date <= ${n}", ate)

    clausula = f"WHERE {' AND '.join(where)}" if where else ""
    total = await conn.fetchval(f"SELECT count(*) FROM login_tentativas t {clausula}", *params)
    linhas = await conn.fetch(
        f"""
        SELECT t.id, t.criado_em, t.email, t.ip, t.sucesso, t.motivo, t.user_agent
          FROM login_tentativas t
          {clausula}
         ORDER BY t.criado_em DESC, t.id DESC
         LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )
    resumo = await conn.fetch(
        """
        SELECT motivo, count(*) AS qtd
          FROM login_tentativas
         WHERE NOT sucesso AND criado_em > NOW() - INTERVAL '24 hours'
         GROUP BY motivo
        """
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "itens": [dict(r) for r in linhas],
        "falhas_24h": {r["motivo"]: r["qtd"] for r in resumo},
    }
