"""
HIPO — Carreira · PDI (plano de desenvolvimento individual).

A segunda aba da Carreira (Universidade · PDI · Desempenho). Modelo misto:

  * o HIPO SUGERE ações, recalculadas a cada abertura: indicador do mês
    abaixo de 70% da meta (Desempenho) e trilha obrigatória atrasada ou
    vencendo, ou quiz final reprovado 2+ vezes (Universidade);
  * a GESTÃO (Franqueado, ADM) confirma — ajustando objetivo, o que
    fazer, trilha e prazo —, descarta, ou cria uma ação do zero;
  * o COLABORADOR marca a ação como feita (e pode desfazer a própria).

Ação ligada a uma trilha se conclui sozinha quando a trilha fica
concluída (aulas + quiz final).

Montado em main.py com prefixo /carreira e módulo 'crm', como o
Desempenho. Regras puras em services/pdi.py.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import get_conn
from routers.auth import usuario_atual
from routers.carreira import _hoje, mes_da_pessoa
from routers.uc import _lista_json, _pessoa_alvo, eh_gestao, montar_painel
from services import desempenho as regras_desempenho
from services import pdi as regras
from services import rper

router = APIRouter()

CARGOS_COM_PDI = ("SDR", "EV", "EC", "EP", "ADM")


# ── Schemas de entrada ───────────────────────────────────────────────

class AcaoNova(BaseModel):
    usuario_id: UUID
    objetivo: str
    o_que_fazer: str
    prazo: date
    trilha_id: UUID | None = None
    chave_origem: str | None = None


class AcaoPatch(BaseModel):
    objetivo: str | None = None
    o_que_fazer: str | None = None
    prazo: date | None = None
    trilha_id: UUID | None = None
    status: str | None = None
    nota_conclusao: str | None = None


class Descarte(BaseModel):
    usuario_id: UUID
    chave: str


# ── Apoio ────────────────────────────────────────────────────────────

def _422(e: Exception):
    raise HTTPException(422, str(e))


async def _pessoa_por_id(conn, usuario_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT id, nome, cargo, created_at FROM usuarios WHERE id = $1 AND ativo", usuario_id,
    )
    if row is None:
        raise HTTPException(404, "Pessoa não encontrada.")
    return dict(row)


async def _pessoas_para_gestao(conn) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, nome, cargo FROM usuarios
         WHERE ativo AND cargo = ANY($1::text[])
         ORDER BY cargo, nome
        """,
        list(CARGOS_COM_PDI),
    )
    return [{"id": str(r["id"]), "nome": r["nome"], "cargo": r["cargo"]} for r in rows]


async def _quizzes_reprovados(conn, pessoa_id) -> list[dict]:
    """Trilhas com 2+ tentativas no quiz final e nenhuma aprovação."""
    rows = await conn.fetch(
        """
        SELECT t.id AS trilha_id, t.titulo, count(*) AS tentativas,
               (array_agg(x.erradas ORDER BY x.criado_em DESC))[1] AS ultimas_erradas
          FROM uc_tentativas_trilha x
          JOIN uc_trilhas t ON t.id = x.trilha_id AND t.status = 'publicada'
         WHERE x.usuario_id = $1
         GROUP BY t.id, t.titulo
        HAVING count(*) >= $2 AND NOT bool_or(x.aprovada)
        """,
        pessoa_id, regras.QUIZ_TENTATIVAS_SUGESTAO,
    )
    saida = []
    for r in rows:
        rever, vistos = [], set()
        for e in _lista_json(r["ultimas_erradas"]):
            rotulo = f"Aula {e['aula_ordem']}. {e['aula_titulo']}"
            if rotulo not in vistos:
                vistos.add(rotulo)
                rever.append(rotulo)
        saida.append({"trilha_id": r["trilha_id"], "titulo": r["titulo"],
                      "tentativas": r["tentativas"], "aulas_rever": rever})
    return saida


async def _sugestoes_desempenho(conn, pessoa: dict, hoje: date) -> list[regras.Sugestao]:
    squad = regras_desempenho.squad_do_cargo(pessoa.get("cargo"))
    if squad is None:
        return []
    agora = datetime.now(timezone.utc)
    m = await mes_da_pessoa(conn, pessoa, squad, hoje.year, hoje.month, hoje, agora)
    ano, mes = hoje.year, hoje.month
    if m["dia_util"] < regras.DIA_UTIL_MINIMO:
        # Começo de mês ainda não diz nada: olha o mês anterior, fechado.
        ano, mes = rper.mes_anterior(hoje.year, hoje.month)
        m = await mes_da_pessoa(conn, pessoa, squad, ano, mes, hoje, agora)
    return regras.sugestoes_do_desempenho(squad, m["linhas"], ano, mes, m["aberto"], hoje)


def _acao_out(r: dict, hoje: date) -> dict:
    return {
        "id": str(r["id"]),
        "origem": r["origem"],
        "origem_rotulo": regras.ORIGENS[r["origem"]],
        "objetivo": r["objetivo"],
        "o_que_fazer": r["o_que_fazer"],
        "trilha": ({"id": str(r["trilha_id"]), "titulo": r["trilha_titulo"]}
                   if r["trilha_id"] else None),
        "prazo": r["prazo"],
        "status": r["status"],
        "situacao": regras.situacao(r["status"], r["prazo"], hoje),
        "criado_em": r["criado_em"],
        "criada_por": r["criada_por_nome"],
        "concluida_em": r["concluida_em"],
        "concluida_automatica": r["status"] == "concluida" and r["concluida_por"] is None,
        "nota_conclusao": r["nota_conclusao"],
    }


async def _concluir_pelas_trilhas(conn, pessoa_id, painel: dict) -> None:
    """Ação ligada a trilha concluída se fecha sozinha."""
    concluidas = [
        t["id"] for t in painel["manual"]["trilhas"] + painel["outras"]
        if t["situacao"]["codigo"] == "concluida"
    ]
    if not concluidas:
        return
    await conn.execute(
        """
        UPDATE pdi_acoes
           SET status = 'concluida', concluida_em = NOW(), concluida_por = NULL,
               nota_conclusao = COALESCE(nota_conclusao, 'Trilha concluída na Universidade.'),
               atualizado_em = NOW()
         WHERE usuario_id = $1 AND status = 'aberta' AND trilha_id = ANY($2::uuid[])
        """,
        pessoa_id, concluidas,
    )


async def _estado(conn, user: dict, pessoa: dict, leitura: bool, hoje: date) -> dict:
    """A tela inteira do PDI de uma pessoa."""
    gestao = eh_gestao(user)
    painel = await montar_painel(conn, pessoa, hoje)
    await _concluir_pelas_trilhas(conn, pessoa["id"], painel)

    rows = [dict(r) for r in await conn.fetch(
        """
        SELECT a.*, t.titulo AS trilha_titulo, u.nome AS criada_por_nome
          FROM pdi_acoes a
          LEFT JOIN uc_trilhas t ON t.id = a.trilha_id
          LEFT JOIN usuarios u ON u.id = a.criada_por
         WHERE a.usuario_id = $1
         ORDER BY a.prazo, a.criado_em
        """,
        pessoa["id"],
    )]
    chaves = {r["chave_origem"] for r in rows if r["chave_origem"]}
    acoes = [r for r in rows if r["status"] != "descartada"]
    abertas = [_acao_out(r, hoje) for r in acoes if r["status"] == "aberta"]
    feitas = sorted(
        (_acao_out(r, hoje) for r in acoes if r["status"] in ("concluida", "cancelada")),
        key=lambda a: a["concluida_em"] or a["criado_em"], reverse=True,
    )[:20]
    prox = regras.proxima_acao([r for r in acoes])

    sugestoes = regras.filtrar_sugestoes(
        await _sugestoes_desempenho(conn, pessoa, hoje)
        + regras.sugestoes_da_uc(painel["manual"]["trilhas"],
                                 await _quizzes_reprovados(conn, pessoa["id"]), hoje),
        chaves,
    )
    inicio_mes = hoje.replace(day=1)
    trilhas = sorted(
        ({"id": str(t["id"]), "titulo": t["titulo"], "pilar_rotulo": t["pilar_rotulo"]}
         for t in painel["manual"]["trilhas"] + painel["outras"]),
        key=lambda t: (t["pilar_rotulo"], t["titulo"].lower()),
    )
    return {
        "pessoa": {"id": str(pessoa["id"]), "nome": pessoa["nome"], "cargo": pessoa.get("cargo")},
        "modo_leitura": leitura,
        "pode_gerir": gestao,
        "pode_concluir": not leitura,
        "pessoas": await _pessoas_para_gestao(conn) if gestao else [],
        "hoje": hoje,
        "proxima": _acao_out(prox, hoje) if prox else None,
        "resumo": {
            "abertas": len(abertas),
            "atrasadas": sum(1 for a in abertas if a["situacao"]["codigo"] == "atrasada"),
            "feitas_no_mes": sum(
                1 for r in acoes
                if r["status"] == "concluida" and r["concluida_em"]
                and r["concluida_em"].date() >= inicio_mes
            ),
        },
        "acoes_abertas": abertas,
        "acoes_feitas": feitas,
        "sugestoes": [s.para_tela() for s in sugestoes] if gestao else [],
        "sugestoes_pendentes": len(sugestoes),
        "trilhas": trilhas if gestao else [],
    }


def _requer_gestao(user: dict) -> None:
    if not eh_gestao(user):
        raise HTTPException(403, "Só a gestão monta o PDI. Fale com a gestão.")


async def _trilha_ou_422(conn, trilha_id: UUID | None) -> None:
    if trilha_id is not None and not await conn.fetchval(
        "SELECT 1 FROM uc_trilhas WHERE id = $1 AND status <> 'arquivada'", trilha_id,
    ):
        raise HTTPException(422, "Trilha não encontrada.")


# ── Rotas ────────────────────────────────────────────────────────────

@router.get("/pdi")
async def pdi(
    usuario_id: UUID | None = Query(None),
    hoje: date | None = Query(None, description="Só para teste determinístico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    pessoa, leitura = await _pessoa_alvo(conn, user, usuario_id)
    return await _estado(conn, user, pessoa, leitura, hoje or _hoje())


@router.post("/pdi/acoes", status_code=201)
async def criar_acao(body: AcaoNova, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    A gestão cria uma ação: do zero ou confirmando uma sugestão (com a
    `chave_origem` dela, já ajustada no formulário). Devolve o PDI da pessoa.
    """
    _requer_gestao(user)
    hoje = _hoje()
    pessoa = await _pessoa_por_id(conn, body.usuario_id)
    try:
        origem = regras.origem_da_chave(body.chave_origem)
        objetivo = regras.validar_texto(body.objetivo, "objetivo", regras.MAX_OBJETIVO)
        fazer = regras.validar_texto(body.o_que_fazer, "o_que_fazer", regras.MAX_O_QUE_FAZER)
        prazo = regras.validar_prazo(body.prazo, hoje, novo=True)
    except regras.AcaoInvalida as e:
        _422(e)
    await _trilha_ou_422(conn, body.trilha_id)
    if body.chave_origem and await conn.fetchval(
        "SELECT 1 FROM pdi_acoes WHERE usuario_id = $1 AND chave_origem = $2",
        pessoa["id"], body.chave_origem,
    ):
        raise HTTPException(409, "Essa sugestão já virou ação (ou foi descartada).")
    await conn.execute(
        """
        INSERT INTO pdi_acoes (usuario_id, origem, chave_origem, objetivo, o_que_fazer,
                               trilha_id, prazo, criada_por)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        pessoa["id"], origem, body.chave_origem, objetivo, fazer, body.trilha_id, prazo, user["id"],
    )
    return await _estado(conn, user, pessoa, pessoa["id"] != user["id"], hoje)


@router.patch("/pdi/acoes/{acao_id}")
async def editar_acao(acao_id: UUID, body: AcaoPatch, conn=Depends(get_conn),
                      user=Depends(usuario_atual)):
    """
    Gestão: edita tudo (objetivo, o que fazer, trilha, prazo, situação).
    Colaborador: só marca a PRÓPRIA ação como feita (com nota opcional) ou
    desfaz o que ele mesmo marcou.
    """
    a = await conn.fetchrow("SELECT * FROM pdi_acoes WHERE id = $1 AND status <> 'descartada'", acao_id)
    if a is None:
        raise HTTPException(404, "Ação não encontrada.")
    a = dict(a)
    gestao = eh_gestao(user)
    dono = a["usuario_id"] == user["id"]
    campos = body.model_dump(exclude_unset=True)
    hoje = _hoje()

    if not gestao:
        if not dono:
            raise HTTPException(403, "Essa ação é do PDI de outra pessoa.")
        if set(campos) - {"status", "nota_conclusao"}:
            raise HTTPException(403, "Só a gestão muda objetivo, prazo e trilha. Você marca como feita.")
        novo = campos.get("status")
        if novo not in ("concluida", "aberta"):
            raise HTTPException(422, "Marque como feita, ou desfaça.")
        if novo == "aberta" and not (a["status"] == "concluida" and a["concluida_por"] == user["id"]):
            raise HTTPException(403, "Só dá para desfazer o que você mesmo marcou como feito.")

    sets, valores = [], []
    try:
        if "objetivo" in campos:
            sets.append("objetivo")
            valores.append(regras.validar_texto(campos["objetivo"], "objetivo", regras.MAX_OBJETIVO))
        if "o_que_fazer" in campos:
            sets.append("o_que_fazer")
            valores.append(regras.validar_texto(campos["o_que_fazer"], "o_que_fazer", regras.MAX_O_QUE_FAZER))
        if "prazo" in campos:
            sets.append("prazo")
            valores.append(regras.validar_prazo(campos["prazo"], hoje, novo=False))
    except regras.AcaoInvalida as e:
        _422(e)
    if "trilha_id" in campos:
        await _trilha_ou_422(conn, campos["trilha_id"])
        sets.append("trilha_id")
        valores.append(campos["trilha_id"])
    if "nota_conclusao" in campos:
        sets.append("nota_conclusao")
        valores.append((campos["nota_conclusao"] or "").strip()[:1000] or None)

    extra = ""
    if "status" in campos:
        novo = campos["status"]
        if novo not in ("aberta", "concluida", "cancelada"):
            raise HTTPException(422, "Situação inválida: aberta, concluida ou cancelada.")
        sets.append("status")
        valores.append(novo)
        if novo == "concluida" and a["status"] != "concluida":
            sets.append("concluida_por")
            valores.append(user["id"])
            extra = ", concluida_em = NOW()"
        elif novo != "concluida":
            extra = ", concluida_em = NULL, concluida_por = NULL"

    if sets:
        atribuicoes = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(sets))
        await conn.execute(
            f"UPDATE pdi_acoes SET {atribuicoes}{extra}, atualizado_em = NOW() WHERE id = $1",
            acao_id, *valores,
        )
    pessoa = await _pessoa_por_id(conn, a["usuario_id"])
    return await _estado(conn, user, pessoa, not dono, hoje)


@router.post("/pdi/sugestoes/descartar")
async def descartar(body: Descarte, conn=Depends(get_conn), user=Depends(usuario_atual)):
    """A sugestão não volta: grava a chave como descartada."""
    _requer_gestao(user)
    pessoa = await _pessoa_por_id(conn, body.usuario_id)
    try:
        origem = regras.origem_da_chave(body.chave)
    except regras.AcaoInvalida as e:
        _422(e)
    if origem == "gestao":
        raise HTTPException(422, "Sugestão desconhecida.")
    hoje = _hoje()
    await conn.execute(
        """
        INSERT INTO pdi_acoes (usuario_id, origem, chave_origem, objetivo, o_que_fazer,
                               prazo, status, criada_por)
        VALUES ($1, $2, $3::varchar, 'Sugestão descartada', $3::text, $4, 'descartada', $5)
        ON CONFLICT (usuario_id, chave_origem) DO NOTHING
        """,
        pessoa["id"], origem, body.chave[:120], hoje, user["id"],
    )
    return await _estado(conn, user, pessoa, pessoa["id"] != user["id"], hoje)
