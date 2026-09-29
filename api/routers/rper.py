"""
HIPO — RPeR: Reunião de Planejamento e Resultados.

Todo 1º dia útil do mês o time comercial se reúne em cima de um PPT com o
resultado do mês fechado e o planejamento do seguinte. Este router gera
esse PPT a partir do HIPO e mantém as metas que ele cobra.

  GET  /rper/status          o que o servidor consegue gerar (pptx, pdf, IA)
  GET  /rper/previa          os números do RPeR, sem IA e sem arquivo
  GET  /rper/arquivo         o .pptx (ou .pdf) pronto
  GET  /rper/metas           metas do mês: por squad e por pessoa
  PUT  /rper/metas           grava as metas do mês, numa transação
  POST /rper/metas/copiar    copia as metas do mês anterior, sem sobrescrever

TUDO É DE GESTÃO. O RPeR expõe o resultado individual de cada pessoa ao
lado do squad, e as metas são a régua pela qual cada um é cobrado. Mesma
guarda de metas e feriados do Monitor (`requer_gestao`), e pelo mesmo
motivo não há módulo novo: módulo novo só valeria depois de todo mundo
relogar, e o recorte aqui é cargo, não tela.

O PARÂMETRO É O MÊS FECHADO. `?ano=2026&mes=8` gera o RPeR de setembro
(resultados de agosto, planejamento de setembro). Sem parâmetro, o mês
fechado é o anterior ao de hoje — o caso do 1º dia útil.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from database import get_conn
from routers.permissions import requer_gestao
from services import ia as ia_base
from services import proposta_render
from services import rper as regras
from services import rper_dados as dados_rper
from services import rper_ia
from services import rper_render
from services.proposta_render import BibliotecaIndisponivel, PdfIndisponivel
from services.rper import RperInvalido
from services.tarefa import FUSO_OPERACAO

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class MetaIn(BaseModel):
    squad: str
    # None = meta do SQUAD. Preenchido = meta daquela pessoa no squad.
    usuario_id: UUID | None = None
    indicador: str
    # None APAGA a meta; zero é "este mês não se cobra" e continua valendo.
    valor: float | None = Field(None, ge=0)


class MetasIn(BaseModel):
    ano: int = Field(..., ge=2020, le=2100)
    mes: int = Field(..., ge=1, le=12)
    metas: list[MetaIn]


# ── Tempo ────────────────────────────────────────────────────────────

def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _mes_fechado(ano: int | None, mes: int | None) -> tuple[int, int]:
    if ano is None and mes is None:
        hoje = datetime.now(FUSO_OPERACAO).date()
        return regras.mes_anterior(hoje.year, hoje.month)
    if ano is None or mes is None:
        raise HTTPException(422, "Informe ano e mês juntos, ou nenhum dos dois.")
    return ano, mes


def _mes_das_metas(ano: int | None, mes: int | None) -> tuple[int, int]:
    """Metas abrem no mês CORRENTE: é o planejamento que se está fazendo."""
    if ano is None and mes is None:
        hoje = datetime.now(FUSO_OPERACAO).date()
        return hoje.year, hoje.month
    if ano is None or mes is None:
        raise HTTPException(422, "Informe ano e mês juntos, ou nenhum dos dois.")
    return ano, mes


# ── Montagem ─────────────────────────────────────────────────────────

async def _montar(conn, ano: int, mes: int, agora: datetime) -> dict:
    pessoas = await dados_rper.pessoas_dos_squads(conn)
    dados = await dados_rper.coletar(conn, ano, mes, agora)
    ano_novo, mes_novo = regras.mes_seguinte(ano, mes)
    return regras.montar(
        ano=ano, mes=mes, dados=dados, pessoas=pessoas,
        metas_fechado=await dados_rper.metas(conn, ano, mes),
        metas_novo=await dados_rper.metas(conn, ano_novo, mes_novo),
        agora=agora,
    )


def _resumo(r: dict) -> dict:
    """A prévia: só o que a tela mostra. Nada de linhas brutas."""
    return {
        "ano": r["ano"],
        "mes": r["mes"],
        "ano_novo": r["ano_novo"],
        "mes_novo": r["mes_novo"],
        "rotulo_fechado": r["rotulo_fechado"],
        "rotulo_novo": r["rotulo_novo"],
        "gerado_em": r["gerado_em"],
        "squads": [
            {
                "squad": s,
                "nome": regras.NOME_SQUAD[s],
                "total": [
                    {k: l[k] for k in ("chave", "rotulo", "formato", "realizado",
                                       "meta", "atingimento", "realizado_txt",
                                       "meta_txt", "atingimento_txt", "carinha",
                                       "posicao")}
                    for l in r["squads"][s]["total"]
                ],
                "pessoas": [
                    {
                        "id": p["id"],
                        "nome": p["nome"],
                        "indicadores": [
                            {k: l[k] for k in ("chave", "realizado", "meta",
                                               "realizado_txt", "meta_txt",
                                               "atingimento_txt", "carinha")}
                            for l in p["indicadores"]
                        ],
                    }
                    for p in r["squads"][s]["pessoas"]
                ],
            }
            for s in regras.SQUADS
        ],
    }


# ── Rotas ────────────────────────────────────────────────────────────

@router.get("/status")
async def status(user=Depends(requer_gestao)):
    """
    O que este servidor consegue entregar. Lido do servidor, não assumido:
    a tela desliga o botão do PDF onde não há LibreOffice, e avisa que o
    texto sai sem IA onde não há chave.
    """
    ano, mes = _mes_fechado(None, None)
    ano_novo, mes_novo = regras.mes_seguinte(ano, mes)
    return {
        "pptx_disponivel": proposta_render.pptx_disponivel(),
        "pdf_disponivel": proposta_render.libreoffice_disponivel() is not None,
        "ia_configurada": ia_base.configurada(),
        "ano": ano,
        "mes": mes,
        "rotulo_fechado": regras.rotulo_mes(ano, mes),
        "rotulo_novo": regras.rotulo_mes(ano_novo, mes_novo),
    }


@router.get("/previa")
async def previa(
    ano: int | None = Query(None, ge=2020, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    """Os números do RPeR em JSON. Mesma montagem do arquivo, sem IA."""
    ano, mes = _mes_fechado(ano, mes)
    r = await _montar(conn, ano, mes, _agora())
    return jsonable_encoder(_resumo(r))


@router.get("/arquivo")
async def arquivo(
    ano: int | None = Query(None, ge=2020, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    formato: str = Query("pptx", pattern="^(pptx|pdf)$"),
    ia: bool = Query(True, description="False gera só com o texto padrão, sem chamar a IA."),
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    """
    O RPeR pronto. Gerado na hora e não guardado: o arquivo se remonta dos
    dados, e guardar um .pptx por mês só criaria a pergunta "qual versão é
    a certa" quando alguém corrige um lançamento depois.
    """
    ano, mes = _mes_fechado(ano, mes)
    r = await _montar(conn, ano, mes, _agora())
    padrao = regras.textos_padrao(r)
    if ia:
        textos, stats = await rper_ia.escrever(r, padrao)
    else:
        textos, stats = padrao, {"ia": False, "aceitos": 0, "descartados": 0}

    try:
        corpo = rper_render.montar_pptx(r, textos)
    except BibliotecaIndisponivel as e:
        raise HTTPException(503, str(e))
    tipo = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if formato == "pdf":
        try:
            corpo = proposta_render.para_pdf(corpo)
        except PdfIndisponivel as e:
            raise HTTPException(503, str(e))
        tipo = "application/pdf"

    nome = rper_render.nome_do_arquivo(r, formato)
    return Response(
        content=corpo,
        media_type=tipo,
        headers={
            "Content-Disposition": f'attachment; filename="{nome}"',
            # A tela diz se o texto veio da IA e quantas caixas caíram no
            # padrão. Cabeçalho, e não corpo: o corpo é o arquivo.
            "X-RPeR-IA": "1" if stats["ia"] else "0",
            "X-RPeR-Textos-Descartados": str(stats["descartados"]),
            "Access-Control-Expose-Headers":
                "Content-Disposition, X-RPeR-IA, X-RPeR-Textos-Descartados",
        },
    )


# ── Metas ────────────────────────────────────────────────────────────

async def _ler_metas(conn, ano: int, mes: int) -> dict:
    pessoas = await dados_rper.pessoas_dos_squads(conn)
    rows = await conn.fetch(
        """
        SELECT m.squad, m.usuario_id, m.indicador, m.valor, m.atualizado_em,
               u.nome AS atualizado_por_nome
          FROM metas_comerciais m
          LEFT JOIN usuarios u ON u.id = m.atualizado_por
         WHERE m.ano = $1 AND m.mes = $2
        """,
        ano, mes,
    )
    do_squad: dict = {}
    da_pessoa: dict = {}
    ultima = None
    for row in rows:
        if ultima is None or row["atualizado_em"] > ultima["atualizado_em"]:
            ultima = row
        if row["usuario_id"] is None:
            do_squad[(row["squad"], row["indicador"])] = float(row["valor"])
        else:
            da_pessoa[(row["squad"], row["usuario_id"], row["indicador"])] = float(row["valor"])

    return {
        "ano": ano,
        "mes": mes,
        "rotulo": regras.rotulo_mes(ano, mes),
        "atualizado_em": ultima["atualizado_em"] if ultima else None,
        "atualizado_por_nome": ultima["atualizado_por_nome"] if ultima else None,
        # Todos os indicadores de cada squad, com `null` onde não há meta:
        # a tela monta a grade sem cruzar listas, e indicador novo aparece
        # sozinho (mesma decisão de /monitor/metas).
        "squads": [
            {
                "squad": s,
                "nome": regras.NOME_SQUAD[s],
                "indicadores": [
                    {"chave": i.chave, "rotulo": i.rotulo, "formato": i.formato,
                     "natureza": i.natureza, "fonte": i.fonte, "posicao": i.posicao,
                     "principal": i.principal}
                    for i in regras.INDICADORES[s]
                ],
                "squad_metas": {
                    i.chave: do_squad.get((s, i.chave)) for i in regras.INDICADORES[s]
                },
                "pessoas": [
                    {
                        "id": p["id"],
                        "nome": p["nome"],
                        "metas": {
                            i.chave: da_pessoa.get((s, p["id"], i.chave))
                            for i in regras.INDICADORES[s]
                        },
                    }
                    for p in pessoas[s]
                ],
            }
            for s in regras.SQUADS
        ],
    }


@router.get("/metas")
async def listar_metas(
    ano: int | None = Query(None, ge=2020, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    ano, mes = _mes_das_metas(ano, mes)
    return jsonable_encoder(await _ler_metas(conn, ano, mes))


@router.put("/metas")
async def gravar_metas(
    payload: MetasIn,
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    """
    Grava as metas do mês de uma vez, numa transação — a tela salva a grade
    inteira, e metade gravada seria pior que nenhuma.

    Meta de pessoa exige que ela TENHA o cargo do squad: meta de EV para
    quem é SDR não aparece em slide nenhum, e ficaria gravada sem ninguém
    ver. Não exige que esteja ativa — planejar a meta de quem volta de
    férias é legítimo.
    """
    cargos: dict[UUID, str] = {}
    ids = {m.usuario_id for m in payload.metas if m.usuario_id is not None}
    if ids:
        rows = await conn.fetch(
            "SELECT id, cargo FROM usuarios WHERE id = ANY($1::uuid[])", list(ids)
        )
        cargos = {r["id"]: r["cargo"] for r in rows}

    for m in payload.metas:
        try:
            regras.validar_indicador(m.squad, m.indicador)
        except RperInvalido as e:
            raise HTTPException(422, str(e))
        if m.usuario_id is not None:
            if m.usuario_id not in cargos:
                raise HTTPException(422, f"Usuário {m.usuario_id} não existe.")
            if cargos[m.usuario_id] != m.squad:
                raise HTTPException(
                    422,
                    f"Meta de {m.squad} para quem tem o cargo "
                    f"'{cargos[m.usuario_id] or 'sem cargo'}'.",
                )

    async with conn.transaction():
        for m in payload.metas:
            if m.usuario_id is None:
                if m.valor is None:
                    await conn.execute(
                        """
                        DELETE FROM metas_comerciais
                         WHERE usuario_id IS NULL AND squad = $1 AND indicador = $2
                           AND ano = $3 AND mes = $4
                        """,
                        m.squad, m.indicador, payload.ano, payload.mes,
                    )
                    continue
                await conn.execute(
                    """
                    INSERT INTO metas_comerciais
                        (squad, usuario_id, indicador, ano, mes, valor, atualizado_por)
                    VALUES ($1, NULL, $2, $3, $4, $5, $6)
                    ON CONFLICT (squad, indicador, ano, mes) WHERE usuario_id IS NULL
                    DO UPDATE SET valor = EXCLUDED.valor,
                                  atualizado_por = EXCLUDED.atualizado_por,
                                  atualizado_em = NOW()
                    """,
                    m.squad, m.indicador, payload.ano, payload.mes, m.valor, user["id"],
                )
            else:
                if m.valor is None:
                    await conn.execute(
                        """
                        DELETE FROM metas_comerciais
                         WHERE usuario_id = $1 AND squad = $2 AND indicador = $3
                           AND ano = $4 AND mes = $5
                        """,
                        m.usuario_id, m.squad, m.indicador, payload.ano, payload.mes,
                    )
                    continue
                await conn.execute(
                    """
                    INSERT INTO metas_comerciais
                        (squad, usuario_id, indicador, ano, mes, valor, atualizado_por)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (squad, usuario_id, indicador, ano, mes)
                        WHERE usuario_id IS NOT NULL
                    DO UPDATE SET valor = EXCLUDED.valor,
                                  atualizado_por = EXCLUDED.atualizado_por,
                                  atualizado_em = NOW()
                    """,
                    m.squad, m.usuario_id, m.indicador, payload.ano, payload.mes,
                    m.valor, user["id"],
                )

    return jsonable_encoder(await _ler_metas(conn, payload.ano, payload.mes))


@router.post("/metas/copiar")
async def copiar_metas(
    ano: int = Query(..., ge=2020, le=2100),
    mes: int = Query(..., ge=1, le=12),
    conn=Depends(get_conn),
    user=Depends(requer_gestao),
):
    """
    Copia para `ano/mes` as metas do mês anterior — do squad e das pessoas.
    Não sobrescreve o que já foi definido no mês destino.
    """
    ano_ant, mes_ant = regras.mes_anterior(ano, mes)
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO metas_comerciais
                (squad, usuario_id, indicador, ano, mes, valor, atualizado_por)
            SELECT squad, NULL, indicador, $1, $2, valor, $5
              FROM metas_comerciais
             WHERE ano = $3 AND mes = $4 AND usuario_id IS NULL
            ON CONFLICT (squad, indicador, ano, mes) WHERE usuario_id IS NULL
            DO NOTHING
            """,
            ano, mes, ano_ant, mes_ant, user["id"],
        )
        await conn.execute(
            """
            INSERT INTO metas_comerciais
                (squad, usuario_id, indicador, ano, mes, valor, atualizado_por)
            SELECT squad, usuario_id, indicador, $1, $2, valor, $5
              FROM metas_comerciais
             WHERE ano = $3 AND mes = $4 AND usuario_id IS NOT NULL
            ON CONFLICT (squad, usuario_id, indicador, ano, mes)
                WHERE usuario_id IS NOT NULL
            DO NOTHING
            """,
            ano, mes, ano_ant, mes_ant, user["id"],
        )
    return jsonable_encoder(await _ler_metas(conn, ano, mes))
