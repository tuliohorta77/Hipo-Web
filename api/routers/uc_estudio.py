"""
HIPO — Universidade Corporativa: estúdio de conteúdo e visão do time.

Só gestão (Franqueado, ADM). O guard do router no `main.py` é o módulo
'crm', como o resto da UC; quem barra aqui é `requer_gestao_uc`, em cada
rota. Mesma escolha das metas do Monitor e do RPeR: módulo novo só
refletiria depois de todo mundo relogar.

O QUE O ESTÚDIO GARANTE
  * trilha só é publicada com pelo menos uma aula publicada — trilha
    vazia na tela de quem aprende é promessa sem conteúdo;
  * vídeo entra como LINK e sai daqui como (provedor, id); a URL colada
    nunca chega ao banco;
  * "mudança relevante" numa aula sobe a versão e reabre a pendência para
    quem já concluiu; correção de vírgula não sobe;
  * aula com alguém que já concluiu não é apagada — vira rascunho. Apagar
    levaria junto a prova de que a pessoa fez.

O MANUAL DA FUNÇÃO (`PUT /trilhas/{id}/cargos`)
  Substitui a lista inteira. `desde` é preservado para o cargo que já era
  obrigatório e renasce quando a trilha VIRA obrigatória — é de lá que o
  prazo de quem já estava na equipe começa a contar.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, UploadFile, status as http,
)
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from routers.permissions import CARGOS_GESTAO
from routers.uc import _hoje, montar_painel
from services import uc as regras
from services import uc_material as material
from services.anexo import AnexoInvalido
from services.uc import ConteudoInvalido

router = APIRouter()


async def requer_gestao_uc(user=Depends(usuario_atual)):
    if user.get("cargo") not in CARGOS_GESTAO:
        raise HTTPException(
            403,
            f"Cargo '{user.get('cargo') or 'sem cargo'}' não edita conteúdo da "
            "Universidade. Fale com a gestão.",
        )
    return user


# ── Schemas ──────────────────────────────────────────────────────────

class TrilhaIn(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=160)
    descricao: str | None = None
    pilar: str
    reforca: str | None = None


class TrilhaPatch(BaseModel):
    titulo: str | None = Field(None, min_length=1, max_length=160)
    descricao: str | None = None
    pilar: str | None = None
    reforca: str | None = None
    status: str | None = None


class CargoIn(BaseModel):
    cargo: str
    obrigatoria: bool = True
    prazo_dias: int | None = Field(None, ge=1, le=365)


class CargosIn(BaseModel):
    cargos: list[CargoIn]


class AulaIn(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=160)
    resumo: str | None = None
    conteudo_md: str | None = None
    video_url: str | None = None
    duracao_min: int | None = Field(None, ge=1, le=600)
    status: str = "publicada"


class AulaPatch(BaseModel):
    titulo: str | None = Field(None, min_length=1, max_length=160)
    resumo: str | None = None
    conteudo_md: str | None = None
    # Presente e vazio = tira o vídeo; ausente = não mexe.
    video_url: str | None = None
    duracao_min: int | None = Field(None, ge=1, le=600)
    status: str | None = None
    mudanca_relevante: bool = False


class OrdemIn(BaseModel):
    aulas: list[UUID]


class CargoOut(BaseModel):
    cargo: str
    obrigatoria: bool
    prazo_dias: int | None
    desde: datetime


class TrilhaEstudio(BaseModel):
    id: UUID
    titulo: str
    descricao: str | None
    pilar: str
    pilar_rotulo: str
    reforca: str | None
    status: str
    cargos: list[CargoOut]
    aulas_total: int
    aulas_publicadas: int
    concluintes: int
    atualizado_em: datetime


class MaterialEstudio(BaseModel):
    id: UUID
    nome_original: str
    tipo_mime: str
    bytes: int
    eh_imagem: bool
    criado_em: datetime


class AulaEstudio(BaseModel):
    id: UUID
    trilha_id: UUID
    ordem: int
    titulo: str
    resumo: str | None
    conteudo_md: str | None
    video_provedor: str | None
    video_ref: str | None
    video_url: str | None
    duracao_min: int | None
    versao: int
    status: str
    concluintes: int
    materiais: list[MaterialEstudio]
    # O tour vem da carga do conteúdo (scripts/semear_uc.py); o estúdio só
    # mostra quantos passos a aula tem. Editar a aula não mexe nele.
    tour_passos: int = 0


class TrilhaEstudioDetalhe(TrilhaEstudio):
    aulas: list[AulaEstudio]
    materiais_disponiveis: bool
    materiais_problemas: list[str]


class Vocabulario(BaseModel):
    pilares: dict[str, str]
    reforcos: dict[str, str]
    cargos: list[str]
    provedores: dict[str, str]
    status_trilha: list[str]


class PessoaTime(BaseModel):
    id: UUID
    nome: str
    cargo: str | None
    obrigatorias: int
    obrigatorias_concluidas: int
    atrasadas: int
    aulas_total: int
    aulas_concluidas: int
    percentual: int | None
    proxima_aula: str | None


# ── Apoio ────────────────────────────────────────────────────────────

def _422(e: Exception):
    raise HTTPException(422, str(e))


async def _trilha_ou_404(conn, trilha_id: UUID) -> dict:
    row = await conn.fetchrow("SELECT * FROM uc_trilhas WHERE id = $1", trilha_id)
    if row is None:
        raise HTTPException(404, "Trilha não encontrada.")
    return dict(row)


async def _aula_ou_404(conn, aula_id: UUID) -> dict:
    row = await conn.fetchrow("SELECT * FROM uc_aulas WHERE id = $1", aula_id)
    if row is None:
        raise HTTPException(404, "Aula não encontrada.")
    return dict(row)


_SQL_TRILHAS = """
    SELECT t.*,
           (SELECT count(*) FROM uc_aulas a WHERE a.trilha_id = t.id) AS aulas_total,
           (SELECT count(*) FROM uc_aulas a
             WHERE a.trilha_id = t.id AND a.status = 'publicada') AS aulas_publicadas,
           (SELECT count(DISTINCT p.usuario_id) FROM uc_progresso p
              JOIN uc_aulas a ON a.id = p.aula_id
             WHERE a.trilha_id = t.id AND p.concluida_em IS NOT NULL) AS concluintes
      FROM uc_trilhas t
"""


async def _cargos(conn, trilha_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT cargo, obrigatoria, prazo_dias, desde FROM uc_trilha_cargos
         WHERE trilha_id = $1 ORDER BY cargo
        """,
        trilha_id,
    )
    return [dict(r) for r in rows]


def _trilha_out(row: dict, cargos: list[dict]) -> dict:
    d = dict(row)
    d["pilar_rotulo"] = regras.PILARES[d["pilar"]]
    d["cargos"] = cargos
    return d


async def _aula_out(conn, a: dict) -> dict:
    materiais = await conn.fetch(
        """
        SELECT id, nome_original, tipo_mime, bytes, criado_em
          FROM uc_materiais WHERE aula_id = $1 ORDER BY criado_em
        """,
        a["id"],
    )
    concluintes = await conn.fetchval(
        """
        SELECT count(DISTINCT usuario_id) FROM uc_progresso
         WHERE aula_id = $1 AND aula_versao = $2 AND concluida_em IS NOT NULL
        """,
        a["id"], a["versao"],
    )
    return {
        "id": a["id"], "trilha_id": a["trilha_id"], "ordem": a["ordem"],
        "titulo": a["titulo"], "resumo": a["resumo"], "conteudo_md": a["conteudo_md"],
        "video_provedor": a["video_provedor"], "video_ref": a["video_ref"],
        "video_url": regras.url_do_video(a["video_provedor"], a["video_ref"]),
        "duracao_min": a["duracao_min"], "versao": a["versao"], "status": a["status"],
        "concluintes": concluintes,
        "tour_passos": len(regras.ler_tour(a.get("tour")) or []),
        "materiais": [
            {**dict(m), "eh_imagem": m["tipo_mime"].startswith("image/")} for m in materiais
        ],
    }


async def _detalhe(conn, trilha_id: UUID) -> dict:
    row = await conn.fetchrow(_SQL_TRILHAS + " WHERE t.id = $1", trilha_id)
    if row is None:
        raise HTTPException(404, "Trilha não encontrada.")
    aulas = await conn.fetch(
        "SELECT * FROM uc_aulas WHERE trilha_id = $1 ORDER BY ordem", trilha_id,
    )
    problemas = material.problemas()
    d = _trilha_out(dict(row), await _cargos(conn, trilha_id))
    d["aulas"] = [await _aula_out(conn, dict(a)) for a in aulas]
    d["materiais_disponiveis"] = not problemas
    d["materiais_problemas"] = problemas
    return d


async def _toca_trilha(conn, trilha_id: UUID) -> None:
    await conn.execute("UPDATE uc_trilhas SET atualizado_em = NOW() WHERE id = $1", trilha_id)


# ── Vocabulário e time ───────────────────────────────────────────────

@router.get("/vocabulario", response_model=Vocabulario,
            dependencies=[Depends(requer_gestao_uc)])
async def vocabulario():
    """Rótulos do estúdio vindos do servidor: o front não crava nenhum."""
    return {
        "pilares": regras.PILARES,
        "reforcos": regras.REFORCOS,
        "cargos": list(regras.CARGOS_UC),
        "provedores": regras.PROVEDORES,
        "status_trilha": list(regras.STATUS_TRILHA),
    }


@router.get("/time", response_model=list[PessoaTime],
            dependencies=[Depends(requer_gestao_uc)])
async def time(
    hoje: date | None = Query(None),
    conn=Depends(get_conn),
):
    """
    Uma linha por pessoa ativa que recebe trilha: manual em dia, atrasadas,
    andamento geral e a próxima aula. Clique na linha abre a UC da pessoa
    em modo leitura (`GET /uc/painel?usuario_id=`).
    """
    dia = hoje or _hoje()
    pessoas = await conn.fetch(
        """
        SELECT id, nome, cargo, created_at FROM usuarios
         WHERE ativo AND cargo = ANY($1::text[])
         ORDER BY nome
        """,
        list(regras.CARGOS_UC),
    )
    saida = []
    for p in pessoas:
        painel = await montar_painel(conn, dict(p), dia)
        total = sum(x["aulas_total"] for x in painel["pilares"])
        feitas = sum(x["aulas_concluidas"] for x in painel["pilares"])
        saida.append({
            "id": p["id"], "nome": p["nome"], "cargo": p["cargo"],
            "obrigatorias": painel["manual"]["trilhas_total"],
            "obrigatorias_concluidas": painel["manual"]["trilhas_concluidas"],
            "atrasadas": painel["manual"]["atrasadas"],
            "aulas_total": total, "aulas_concluidas": feitas,
            "percentual": regras.percentual(feitas, total),
            "proxima_aula": painel["proxima"]["aula_titulo"] if painel["proxima"] else None,
        })
    return saida


# ── Trilhas ──────────────────────────────────────────────────────────

@router.get("/trilhas", response_model=list[TrilhaEstudio],
            dependencies=[Depends(requer_gestao_uc)])
async def listar_trilhas(conn=Depends(get_conn)):
    rows = await conn.fetch(
        _SQL_TRILHAS
        + " ORDER BY (t.status = 'arquivada'), t.pilar, lower(t.titulo)"
    )
    return [_trilha_out(dict(r), await _cargos(conn, r["id"])) for r in rows]


@router.post("/trilhas", response_model=TrilhaEstudioDetalhe,
             status_code=http.HTTP_201_CREATED)
async def criar_trilha(
    body: TrilhaIn,
    conn=Depends(get_conn),
    user=Depends(requer_gestao_uc),
):
    """Nasce em rascunho: publicar exige aula, e aula exige a trilha existir."""
    try:
        pilar = regras.validar_pilar(body.pilar)
        reforca = regras.validar_reforca(body.reforca)
    except ConteudoInvalido as e:
        _422(e)
    titulo = body.titulo.strip()
    if not titulo:
        raise HTTPException(422, "Dê um título à trilha.")
    row = await conn.fetchrow(
        """
        INSERT INTO uc_trilhas (titulo, descricao, pilar, reforca, criado_por)
        VALUES ($1, $2, $3, $4, $5) RETURNING id
        """,
        titulo, (body.descricao or "").strip() or None, pilar, reforca, user["id"],
    )
    return await _detalhe(conn, row["id"])


@router.get("/trilhas/{trilha_id}", response_model=TrilhaEstudioDetalhe,
            dependencies=[Depends(requer_gestao_uc)])
async def detalhe_trilha(trilha_id: UUID, conn=Depends(get_conn)):
    return await _detalhe(conn, trilha_id)


@router.patch("/trilhas/{trilha_id}", response_model=TrilhaEstudioDetalhe,
              dependencies=[Depends(requer_gestao_uc)])
async def editar_trilha(trilha_id: UUID, body: TrilhaPatch, conn=Depends(get_conn)):
    await _trilha_ou_404(conn, trilha_id)
    campos = body.model_dump(exclude_unset=True)
    sets, valores = [], []
    try:
        if "titulo" in campos:
            t = (campos["titulo"] or "").strip()
            if not t:
                raise ConteudoInvalido("Dê um título à trilha.")
            sets.append("titulo"); valores.append(t)
        if "descricao" in campos:
            sets.append("descricao"); valores.append((campos["descricao"] or "").strip() or None)
        if "pilar" in campos:
            sets.append("pilar"); valores.append(regras.validar_pilar(campos["pilar"]))
        if "reforca" in campos:
            sets.append("reforca"); valores.append(regras.validar_reforca(campos["reforca"]))
        if "status" in campos:
            novo = regras.validar_status_trilha(campos["status"])
            if novo == "publicada":
                publicadas = await conn.fetchval(
                    "SELECT count(*) FROM uc_aulas WHERE trilha_id = $1 AND status = 'publicada'",
                    trilha_id,
                )
                if publicadas == 0:
                    raise ConteudoInvalido(
                        "Trilha sem aula publicada não pode ser publicada: "
                        "ela apareceria vazia para a equipe."
                    )
            sets.append("status"); valores.append(novo)
    except ConteudoInvalido as e:
        _422(e)

    if sets:
        atribuicoes = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(sets))
        await conn.execute(
            f"UPDATE uc_trilhas SET {atribuicoes}, atualizado_em = NOW() WHERE id = $1",
            trilha_id, *valores,
        )
    return await _detalhe(conn, trilha_id)


@router.put("/trilhas/{trilha_id}/cargos", response_model=TrilhaEstudioDetalhe,
            dependencies=[Depends(requer_gestao_uc)])
async def definir_cargos(trilha_id: UUID, body: CargosIn, conn=Depends(get_conn)):
    """
    Substitui a lista de cargos da trilha. Lista vazia = trilha aberta a
    todos, sem obrigação para ninguém.
    """
    await _trilha_ou_404(conn, trilha_id)
    vistos: set[str] = set()
    limpos = []
    try:
        for c in body.cargos:
            cargo = regras.validar_cargo(c.cargo)
            if cargo in vistos:
                raise ConteudoInvalido(f"Cargo {cargo} repetido na lista.")
            vistos.add(cargo)
            limpos.append((cargo, c.obrigatoria, c.prazo_dias if c.obrigatoria else None))
    except ConteudoInvalido as e:
        _422(e)

    async with conn.transaction():
        antes = {r["cargo"]: dict(r) for r in await _cargos(conn, trilha_id)}
        await conn.execute("DELETE FROM uc_trilha_cargos WHERE trilha_id = $1", trilha_id)
        for cargo, obrig, prazo in limpos:
            anterior = antes.get(cargo)
            # `desde` sobrevive se o cargo já tinha a trilha como obrigatória;
            # renasce agora se a obrigação é nova.
            manter = anterior is not None and anterior["obrigatoria"] and obrig
            await conn.execute(
                """
                INSERT INTO uc_trilha_cargos (trilha_id, cargo, obrigatoria, prazo_dias, desde)
                VALUES ($1, $2, $3, $4, COALESCE($5, NOW()))
                """,
                trilha_id, cargo, obrig, prazo, anterior["desde"] if manter else None,
            )
        await _toca_trilha(conn, trilha_id)
    return await _detalhe(conn, trilha_id)


@router.put("/trilhas/{trilha_id}/ordem", response_model=TrilhaEstudioDetalhe,
            dependencies=[Depends(requer_gestao_uc)])
async def reordenar(trilha_id: UUID, body: OrdemIn, conn=Depends(get_conn)):
    """A lista precisa ter exatamente as aulas da trilha, cada uma uma vez."""
    await _trilha_ou_404(conn, trilha_id)
    atuais = {r["id"] for r in await conn.fetch(
        "SELECT id FROM uc_aulas WHERE trilha_id = $1", trilha_id,
    )}
    if len(body.aulas) != len(set(body.aulas)) or set(body.aulas) != atuais:
        raise HTTPException(422, "A nova ordem precisa listar todas as aulas da trilha, uma vez cada.")
    async with conn.transaction():
        for i, aula_id in enumerate(body.aulas, start=1):
            await conn.execute("UPDATE uc_aulas SET ordem = $2 WHERE id = $1", aula_id, i)
        await _toca_trilha(conn, trilha_id)
    return await _detalhe(conn, trilha_id)


# ── Aulas ────────────────────────────────────────────────────────────

@router.post("/trilhas/{trilha_id}/aulas", response_model=AulaEstudio,
             status_code=http.HTTP_201_CREATED,
             dependencies=[Depends(requer_gestao_uc)])
async def criar_aula(trilha_id: UUID, body: AulaIn, conn=Depends(get_conn)):
    await _trilha_ou_404(conn, trilha_id)
    try:
        video = regras.normalizar_video(body.video_url)
        status = regras.validar_status_aula(body.status)
    except ConteudoInvalido as e:
        _422(e)
    titulo = body.titulo.strip()
    if not titulo:
        raise HTTPException(422, "Dê um título à aula.")
    async with conn.transaction():
        await conn.execute("SELECT 1 FROM uc_trilhas WHERE id = $1 FOR UPDATE", trilha_id)
        ordem = await conn.fetchval(
            "SELECT COALESCE(max(ordem), 0) + 1 FROM uc_aulas WHERE trilha_id = $1", trilha_id,
        )
        row = await conn.fetchrow(
            """
            INSERT INTO uc_aulas (trilha_id, ordem, titulo, resumo, conteudo_md,
                                  video_provedor, video_ref, duracao_min, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            trilha_id, ordem, titulo, (body.resumo or "").strip() or None,
            body.conteudo_md or None,
            video[0] if video else None, video[1] if video else None,
            body.duracao_min, status,
        )
        await _toca_trilha(conn, trilha_id)
    return await _aula_out(conn, dict(row))


@router.patch("/aulas/{aula_id}", response_model=AulaEstudio,
              dependencies=[Depends(requer_gestao_uc)])
async def editar_aula(aula_id: UUID, body: AulaPatch, conn=Depends(get_conn)):
    a = await _aula_ou_404(conn, aula_id)
    campos = body.model_dump(exclude_unset=True)
    sets, valores = [], []
    try:
        if "titulo" in campos:
            t = (campos["titulo"] or "").strip()
            if not t:
                raise ConteudoInvalido("Dê um título à aula.")
            sets.append("titulo"); valores.append(t)
        if "resumo" in campos:
            sets.append("resumo"); valores.append((campos["resumo"] or "").strip() or None)
        if "conteudo_md" in campos:
            sets.append("conteudo_md"); valores.append(campos["conteudo_md"] or None)
        if "video_url" in campos:
            video = regras.normalizar_video(campos["video_url"])
            sets += ["video_provedor", "video_ref"]
            valores += [video[0] if video else None, video[1] if video else None]
        if "duracao_min" in campos:
            sets.append("duracao_min"); valores.append(campos["duracao_min"])
        if "status" in campos:
            novo = regras.validar_status_aula(campos["status"])
            if novo == "rascunho":
                restantes = await conn.fetchval(
                    """
                    SELECT count(*) FROM uc_aulas
                     WHERE trilha_id = $1 AND status = 'publicada' AND id <> $2
                    """,
                    a["trilha_id"], aula_id,
                )
                trilha_status = await conn.fetchval(
                    "SELECT status FROM uc_trilhas WHERE id = $1", a["trilha_id"],
                )
                if trilha_status == "publicada" and restantes == 0:
                    raise ConteudoInvalido(
                        "É a última aula publicada de uma trilha publicada. "
                        "Volte a trilha para rascunho antes, ou publique outra aula."
                    )
            sets.append("status"); valores.append(novo)
    except ConteudoInvalido as e:
        _422(e)

    if body.mudanca_relevante:
        sets.append("versao"); valores.append(a["versao"] + 1)

    if sets:
        atribuicoes = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(sets))
        await conn.execute(
            f"UPDATE uc_aulas SET {atribuicoes}, atualizado_em = NOW() WHERE id = $1",
            aula_id, *valores,
        )
        await _toca_trilha(conn, a["trilha_id"])
    return await _aula_out(conn, await _aula_ou_404(conn, aula_id))


@router.delete("/aulas/{aula_id}", status_code=http.HTTP_204_NO_CONTENT,
               dependencies=[Depends(requer_gestao_uc)])
async def apagar_aula(aula_id: UUID, conn=Depends(get_conn)):
    """
    Só aula que ninguém concluiu. Com conclusão registrada, 409 sugerindo
    rascunho: apagar levaria junto a prova de que a pessoa fez.
    """
    a = await _aula_ou_404(conn, aula_id)
    concluiram = await conn.fetchval(
        "SELECT count(*) FROM uc_progresso WHERE aula_id = $1 AND concluida_em IS NOT NULL",
        aula_id,
    )
    if concluiram:
        raise HTTPException(
            409,
            f"{concluiram} conclusão(ões) registrada(s) nesta aula. "
            "Em vez de apagar, passe a aula para rascunho.",
        )
    restantes = await conn.fetchval(
        "SELECT count(*) FROM uc_aulas WHERE trilha_id = $1 AND status = 'publicada' AND id <> $2",
        a["trilha_id"], aula_id,
    )
    trilha_status = await conn.fetchval("SELECT status FROM uc_trilhas WHERE id = $1", a["trilha_id"])
    if trilha_status == "publicada" and a["status"] == "publicada" and restantes == 0:
        raise HTTPException(
            409, "É a última aula publicada de uma trilha publicada. Volte a trilha para rascunho antes.",
        )
    chaves = [r["chave_s3"] for r in await conn.fetch(
        "SELECT chave_s3 FROM uc_materiais WHERE aula_id = $1", aula_id,
    )]
    async with conn.transaction():
        await conn.execute("DELETE FROM uc_aulas WHERE id = $1", aula_id)
        # Fecha o buraco na numeração: a ordem é o que a tela mostra.
        await conn.execute(
            """
            UPDATE uc_aulas a SET ordem = n.nova
              FROM (SELECT id, row_number() OVER (ORDER BY ordem) AS nova
                      FROM uc_aulas WHERE trilha_id = $1) n
             WHERE a.id = n.id AND a.ordem <> n.nova
            """,
            a["trilha_id"],
        )
        await _toca_trilha(conn, a["trilha_id"])
    for chave in chaves:
        try:
            material.remover(chave)
        except Exception:  # pragma: no cover - depende da AWS
            pass
    return None


# ── Materiais ────────────────────────────────────────────────────────

@router.post("/aulas/{aula_id}/materiais", response_model=MaterialEstudio,
             status_code=http.HTTP_201_CREATED)
async def enviar_material(
    aula_id: UUID,
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    user=Depends(requer_gestao_uc),
):
    """Upload pela API, S3 primeiro e banco depois — a ordem dos anexos."""
    problemas = material.problemas()
    if problemas:
        raise HTTPException(503, "Materiais indisponíveis: " + "; ".join(problemas))
    await _aula_ou_404(conn, aula_id)
    try:
        extensao = material.validar_tipo(arquivo.content_type)
        conteudo = await arquivo.read()
        material.validar_tamanho(len(conteudo))
        material.validar_quantidade(await conn.fetchval(
            "SELECT count(*) FROM uc_materiais WHERE aula_id = $1", aula_id,
        ))
    except AnexoInvalido as e:
        raise HTTPException(422, str(e))

    material_id = uuid4()
    chave = material.chave_do_objeto(aula_id, material_id, extensao)
    nome = material.nome_seguro(arquivo.filename, extensao)
    tipo = arquivo.content_type.split(";")[0].strip().lower()
    try:
        material.subir(chave, conteudo, tipo)
    except Exception as e:  # pragma: no cover - depende da AWS
        raise HTTPException(502, f"Não foi possível gravar o arquivo: {e}")

    row = await conn.fetchrow(
        """
        INSERT INTO uc_materiais (id, aula_id, chave_s3, nome_original, tipo_mime, bytes, enviado_por)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, nome_original, tipo_mime, bytes, criado_em
        """,
        material_id, aula_id, chave, nome, tipo, len(conteudo), user["id"],
    )
    return {**dict(row), "eh_imagem": tipo.startswith("image/")}


@router.delete("/materiais/{material_id}", status_code=http.HTTP_204_NO_CONTENT,
               dependencies=[Depends(requer_gestao_uc)])
async def remover_material(material_id: UUID, conn=Depends(get_conn)):
    """Linha primeiro, objeto depois: falha no S3 deixa só um órfão invisível."""
    m = await conn.fetchrow("SELECT id, chave_s3 FROM uc_materiais WHERE id = $1", material_id)
    if m is None:
        raise HTTPException(404, "Material não encontrado.")
    await conn.execute("DELETE FROM uc_materiais WHERE id = $1", material_id)
    try:
        material.remover(m["chave_s3"])
    except Exception:  # pragma: no cover - depende da AWS
        pass
    return None
