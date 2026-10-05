"""
HIPO — Carreira · Desempenho.

A terceira aba da Carreira (Universidade · PDI · Desempenho): cada pessoa
vê o próprio mês com os indicadores do squad dela (os mesmos da RPeR),
contra as metas individuais gravadas pela gestão no Monitor ("Metas por
squad e pessoa"), o funil com as taxas de conversão e os últimos meses.

Quem vê o quê: cada um vê só o próprio desempenho (não há ranking). A
gestão (Franqueado, ADM) escolhe a pessoa por `usuario_id` e vê em modo
leitura, a mesma regra da Universidade.

Regras puras em services/desempenho.py; dados em services/rper_dados.py.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_conn
from routers.auth import usuario_atual
from routers.uc import _pessoa_alvo, eh_gestao
from services import desempenho as regras
from services import dias_uteis
from services import rper
from services import rper_dados
from services.tarefa import FUSO_OPERACAO, janela_utc

router = APIRouter()


def _hoje() -> date:
    return datetime.now(FUSO_OPERACAO).date()


async def _dias_nao_uteis(conn, ano: int, mes: int) -> list[date]:
    ultimo = date(ano, mes, monthrange(ano, mes)[1])
    rows = await conn.fetch(
        "SELECT data FROM dia_nao_util WHERE data >= $1 AND data <= $2",
        date(ano, mes, 1), ultimo,
    )
    return [r["data"] for r in rows]


async def _metas_da_pessoa(conn, squad: str, usuario_id, ano: int, mes: int) -> dict[str, float]:
    rows = await conn.fetch(
        """
        SELECT indicador, valor FROM metas_comerciais
         WHERE squad = $1 AND usuario_id = $2 AND ano = $3 AND mes = $4
        """,
        squad, usuario_id, ano, mes,
    )
    return {r["indicador"]: float(r["valor"]) for r in rows}


async def _pessoas_para_gestao(conn) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, nome, cargo FROM usuarios
         WHERE ativo AND cargo = ANY($1::text[])
         ORDER BY cargo, nome
        """,
        list(regras.SQUAD_DO_CARGO),
    )
    return [{"id": str(r["id"]), "nome": r["nome"], "cargo": r["cargo"]} for r in rows]


async def mes_da_pessoa(conn, pessoa: dict, squad: str, ano: int, mes: int,
                        referencia: date, agora: datetime) -> dict:
    """
    Os indicadores de uma pessoa num mês (o aberto vai até `referencia`).
    Separado da rota porque o PDI usa a mesma conta para sugerir ações.
    """
    aberto = (ano, mes) == (referencia.year, referencia.month)
    primeiro = date(ano, mes, 1)
    ultimo = date(ano, mes, monthrange(ano, mes)[1])
    ate = min(referencia, ultimo) if aberto else ultimo
    nao_uteis = await _dias_nao_uteis(conn, ano, mes)
    uteis = len(dias_uteis.dias_uteis_no_mes(primeiro, nao_uteis))
    corridos = dias_uteis.dia_util_atual_no_mes(primeiro, nao_uteis, ate) if aberto else uteis
    inicio, fim = janela_utc(primeiro, ate)
    dados = await rper_dados.coletar_janela(conn, inicio, fim, agora)
    bruto = rper.CALCULO[squad](dados, [pessoa["id"]])
    metas = await _metas_da_pessoa(conn, squad, pessoa["id"], ano, mes)
    linhas = regras.linhas(squad, bruto, metas, aberto=aberto,
                           dia_util=corridos, dias_uteis=uteis)
    return {"aberto": aberto, "dia_util": corridos, "dias_uteis": uteis,
            "bruto": bruto, "metas": metas, "linhas": linhas}


@router.get("/desempenho")
async def desempenho(
    usuario_id: UUID | None = Query(None),
    ano: int | None = Query(None, ge=2020, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    hoje: date | None = Query(None, description="Só para teste determinístico."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    O desempenho da pessoa no mês (padrão: o mês corrente, até hoje).

    Mês futuro é recusado. Cargo sem squad (EP, ADM, Franqueado) recebe a
    resposta com `squad = null`: a tela explica que o cargo não tem metas
    individuais na RPeR, em vez de mostrar zeros.
    """
    pessoa, leitura = await _pessoa_alvo(conn, user, usuario_id)
    referencia = hoje or _hoje()
    if (ano is None) != (mes is None):
        raise HTTPException(422, "Informe ano e mês juntos, ou nenhum dos dois.")
    if ano is None:
        ano, mes = referencia.year, referencia.month
    if (ano, mes) > (referencia.year, referencia.month):
        raise HTTPException(422, "Esse mês ainda não começou.")

    aberto = (ano, mes) == (referencia.year, referencia.month)
    squad = regras.squad_do_cargo(pessoa.get("cargo"))
    base = {
        "pessoa": {"id": str(pessoa["id"]), "nome": pessoa["nome"], "cargo": pessoa.get("cargo")},
        "modo_leitura": leitura,
        "pode_escolher_pessoa": eh_gestao(user),
        "pessoas": await _pessoas_para_gestao(conn) if eh_gestao(user) else [],
        "ano": ano, "mes": mes, "rotulo": rper.rotulo_mes(ano, mes),
        "aberto": aberto,
        "mes_atual": {"ano": referencia.year, "mes": referencia.month},
        "squad": squad,
    }
    if squad is None:
        return {**base, "indicadores": [], "funil": [], "historico": [],
                "ponto_de_atencao": None, "tem_meta": False,
                "dia_util": None, "dias_uteis": None}

    agora = datetime.now(timezone.utc)
    m = await mes_da_pessoa(conn, pessoa, squad, ano, mes, referencia, agora)
    bruto, metas, linhas = m["bruto"], m["metas"], m["linhas"]
    corridos, uteis = m["dia_util"], m["dias_uteis"]

    historico = []
    for (a, m) in regras.meses_anteriores(ano, mes, regras.MESES_HISTORICO - 1):
        d = await rper_dados.coletar(conn, a, m, agora)
        historico.append(regras.ponto_historico(
            squad, a, m, rper.CALCULO[squad](d, [pessoa["id"]]),
            await _metas_da_pessoa(conn, squad, pessoa["id"], a, m),
        ))
    historico.append(regras.ponto_historico(squad, ano, mes, bruto, metas))

    return {
        **base,
        "dia_util": corridos if aberto else None,
        "dias_uteis": uteis,
        "tem_meta": bool(metas),
        "indicadores": linhas,
        "ponto_de_atencao": regras.ponto_de_atencao(linhas),
        "funil": regras.funil(squad, bruto),
        "historico": historico,
    }
