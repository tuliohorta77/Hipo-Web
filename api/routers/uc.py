"""
HIPO — Universidade Corporativa: a tela de quem aprende ("Minha UC").

Módulo 'crm' no `main.py`, e não um módulo próprio: todo cargo válido
aprende, e módulo novo só valeria depois de cada pessoa relogar — mesma
escolha do Monitor e do RPeR. A escrita de conteúdo mora em
routers/uc_estudio.py, barrada por gestão.

O QUE A TELA RECEBE NUMA CHAMADA SÓ (`GET /uc/painel`)
  a próxima aula (um cartão, não uma lista), o andamento por pilar, o
  manual da função (trilhas obrigatórias do cargo, com prazo) e as demais
  trilhas abertas ao cargo. A gestão pede `?usuario_id=` e recebe a mesma
  tela de outra pessoa em modo leitura.

QUEM VÊ QUAL TRILHA
  Trilha PUBLICADA com o cargo da pessoa em `uc_trilha_cargos`, ou sem
  cargo nenhum (aberta a todos). Rascunho e arquivada não aparecem aqui;
  a gestão as enxerga no estúdio.

PROGRESSO É POR VERSÃO DA AULA
  Aula que mudou de forma relevante sobe de versão e volta a ficar
  pendente para todos, sem apagar o registro da versão anterior.

QUIZ FINAL DA TRILHA (024 + 025)
  As aulas concluem pela trava de tempo. O quiz é um só, no fim da
  trilha, numa tela própria (`/trilhas/{id}/quiz`): abre quando todas as
  aulas publicadas estão concluídas, sorteia 10 perguntas do banco das
  aulas e aprova com 85%. A trilha só fica "Concluída" com aprovação.
  Reprovou: nova tentativa em 10 minutos, com outro sorteio. O gabarito
  nunca sai daqui; o resultado diz quais perguntas errou e de qual aula.

Especificação: claude/universidade-corporativa.md.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import get_conn
from routers.auth import usuario_atual
from routers.permissions import CARGO_UC, CARGOS_GESTAO
from services import uc as regras
from services import uc_material as material
from services.tarefa import FUSO_OPERACAO

router = APIRouter()


# ── Tempo ────────────────────────────────────────────────────────────

def _hoje() -> date:
    return datetime.now(FUSO_OPERACAO).date()


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# ── Schemas ──────────────────────────────────────────────────────────

class SituacaoOut(BaseModel):
    codigo: str
    rotulo: str
    dias_restantes: int | None


class TrilhaResumo(BaseModel):
    id: UUID
    titulo: str
    descricao: str | None
    pilar: str
    pilar_rotulo: str
    obrigatoria: bool
    prazo: date | None
    situacao: SituacaoOut
    aulas_total: int
    aulas_concluidas: int
    percentual: int | None
    proxima_aula_id: UUID | None
    quiz: QuizResumo | None = None


class ProximaAula(BaseModel):
    # tipo "quiz": aulas feitas, falta o quiz final (aula_id vem nulo).
    tipo: str = "aula"
    aula_id: UUID | None
    aula_titulo: str
    trilha_id: UUID
    trilha_titulo: str
    pilar: str
    pilar_rotulo: str
    motivo: str
    motivo_texto: str
    prazo: date | None
    duracao_min: int | None


class PilarResumo(BaseModel):
    pilar: str
    rotulo: str
    trilhas: int
    aulas_total: int
    aulas_concluidas: int
    percentual: int | None


class ManualResumo(BaseModel):
    trilhas_total: int
    trilhas_concluidas: int
    atrasadas: int
    trilhas: list[TrilhaResumo]


class PessoaOut(BaseModel):
    id: UUID
    nome: str
    cargo: str | None


class PainelOut(BaseModel):
    usuario: PessoaOut
    modo_leitura: bool
    pode_editar_conteudo: bool
    hoje: date
    proxima: ProximaAula | None
    pilares: list[PilarResumo]
    manual: ManualResumo
    outras: list[TrilhaResumo]


class AulaItem(BaseModel):
    id: UUID
    ordem: int
    titulo: str
    resumo: str | None
    duracao_min: int | None
    tem_video: bool
    materiais: int
    estado: str            # concluida | atualizada | pendente
    status: str


class TrilhaDetalhe(BaseModel):
    id: UUID
    titulo: str
    descricao: str | None
    pilar: str
    pilar_rotulo: str
    status: str
    obrigatoria: bool
    prazo: date | None
    situacao: SituacaoOut
    percentual: int | None
    aulas: list[AulaItem]
    quiz: QuizResumo | None = None


class MaterialOut(BaseModel):
    id: UUID
    nome_original: str
    tipo_mime: str
    bytes: int
    eh_imagem: bool
    criado_em: datetime


class AulaVizinha(BaseModel):
    id: UUID
    titulo: str


class PassoTour(BaseModel):
    rota: str
    alvo: str | None
    titulo: str
    texto: str
    clicar: list[str] = []


class QuizResumo(BaseModel):
    """O quiz final de uma trilha, visto de fora (painel, trilha, aula)."""
    perguntas: int
    aprovado: bool
    liberado: bool


class AlternativaQuiz(BaseModel):
    id: UUID
    texto: str


class PerguntaQuiz(BaseModel):
    id: UUID
    numero: int
    enunciado: str
    alternativas: list[AlternativaQuiz]


class ErradaOut(BaseModel):
    """
    Uma pergunta errada: o enunciado e a alternativa que a pessoa marcou.
    Nunca a certa. `enunciado`/`sua_resposta` vêm nulos se a pergunta foi
    apagada do banco depois de uma tentativa antiga.
    """
    numero: int
    aula_ordem: int
    aula_titulo: str
    enunciado: str | None = None
    sua_resposta: str | None = None


class TentativaOut(BaseModel):
    acertos: int
    total: int
    nota: int
    aprovada: bool
    erradas: list[ErradaOut]
    em: datetime


class QuizTrilhaOut(BaseModel):
    trilha_id: UUID
    trilha_titulo: str
    pilar: str
    pilar_rotulo: str
    total: int
    nota_minima: int
    acertos_para_aprovar: int
    tentativas: int
    aprovado: bool
    aprovado_em: datetime | None
    liberado: bool
    aulas_pendentes: int
    ultima: TentativaOut | None
    segundos_para_refazer: int
    espera_minutos: int
    modo_leitura: bool
    # Só vem quando há o que responder: liberado, não aprovado, fora da
    # espera e fora do modo leitura.
    perguntas: list[PerguntaQuiz]


class RespostasQuiz(BaseModel):
    respostas: dict[str, str]


class AulaDetalhe(BaseModel):
    id: UUID
    trilha_id: UUID
    trilha_titulo: str
    pilar: str
    pilar_rotulo: str
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
    materiais: list[MaterialOut]
    anterior: AulaVizinha | None
    proxima: AulaVizinha | None
    aberta_em: datetime | None
    concluida_em: datetime | None
    concluiu_versao_anterior: bool
    segundos_para_liberar: int
    modo_leitura: bool
    tour: list[PassoTour] | None = None
    quiz_da_trilha: QuizResumo | None = None


class UrlMaterial(BaseModel):
    url: str
    expira_em_segundos: int


# ── Apoio ────────────────────────────────────────────────────────────

def eh_gestao(user: dict) -> bool:
    return user.get("cargo") in CARGOS_GESTAO


async def _pessoa_alvo(conn, user: dict, usuario_id: UUID | None) -> tuple[dict, bool]:
    """
    De quem é a tela. Sem `usuario_id`, da própria pessoa. Com ele, só a
    gestão pode — e a tela volta em modo leitura (sem registrar abertura,
    sem botão de concluir).
    """
    if usuario_id is None or usuario_id == user["id"]:
        return user, False
    if not eh_gestao(user):
        raise HTTPException(403, "Só a gestão abre a UC de outra pessoa.")
    alvo = await conn.fetchrow(
        "SELECT id, nome, cargo, created_at FROM usuarios WHERE id = $1 AND ativo",
        usuario_id,
    )
    if alvo is None:
        raise HTTPException(404, "Pessoa não encontrada.")
    return dict(alvo), True


# Trilhas publicadas visíveis para um cargo, com a linha do manual quando
# existir. `NOT EXISTS` = trilha sem cargo nenhum é aberta a todos.
# Cargo UC (conta que só estuda) vê TODAS as publicadas, nenhuma como
# obrigatória: `validar_cargo` não deixa a UC entrar em uc_trilha_cargos,
# então o LEFT JOIN nunca casa e `obrigatoria` sai FALSE.
_SQL_TRILHAS_VISIVEIS = f"""
    SELECT t.id, t.titulo, t.descricao, t.pilar,
           COALESCE(tc.obrigatoria, FALSE) AS obrigatoria,
           tc.prazo_dias, tc.desde
      FROM uc_trilhas t
      LEFT JOIN uc_trilha_cargos tc
             ON tc.trilha_id = t.id AND tc.cargo = $1
     WHERE t.status = 'publicada'
       AND (tc.cargo IS NOT NULL
            OR $1 = '{CARGO_UC}'
            OR NOT EXISTS (SELECT 1 FROM uc_trilha_cargos x WHERE x.trilha_id = t.id))
"""

# Aulas publicadas das trilhas pedidas, com o estado da pessoa na versão
# ATUAL e se ela concluiu alguma versão anterior.
_SQL_AULAS_COM_PROGRESSO = """
    SELECT a.id, a.trilha_id, a.ordem, a.titulo, a.versao, a.duracao_min,
           p.concluida_em IS NOT NULL AS concluida,
           EXISTS (
               SELECT 1 FROM uc_progresso q
                WHERE q.usuario_id = $2 AND q.aula_id = a.id
                  AND q.aula_versao < a.versao AND q.concluida_em IS NOT NULL
           ) AS concluiu_anterior
      FROM uc_aulas a
      LEFT JOIN uc_progresso p
             ON p.aula_id = a.id AND p.usuario_id = $2 AND p.aula_versao = a.versao
     WHERE a.trilha_id = ANY($1::uuid[]) AND a.status = 'publicada'
     ORDER BY a.trilha_id, a.ordem
"""


def _situacao_out(s: regras.SituacaoTrilha) -> dict:
    return {"codigo": s.codigo, "rotulo": s.rotulo, "dias_restantes": s.dias_restantes}


def _quiz_resumo(banco: int, aprovado: bool, aulas: list[dict]) -> dict | None:
    if banco <= 0:
        return None
    return {
        "perguntas": min(banco, regras.QUIZ_TRILHA_PERGUNTAS),
        "aprovado": aprovado,
        "liberado": bool(aulas) and all(a["concluida"] for a in aulas),
    }


def _resumir_trilha(t: dict, aulas: list[dict], entrada, hoje: date,
                    quiz: dict | None = None) -> tuple[dict, regras.SituacaoTrilha]:
    """
    `quiz` = {"banco": nº de perguntas, "aprovado": bool}. Com banco, o
    quiz final conta como um item a mais no percentual, e a trilha só
    fica concluída com ele aprovado.
    """
    total = len(aulas)
    feitas = sum(1 for a in aulas if a["concluida"])
    prazo = (
        regras.prazo_da_obrigatoria(entrada, t["desde"], t["prazo_dias"])
        if t["obrigatoria"] else None
    )
    resumo_quiz = _quiz_resumo((quiz or {}).get("banco", 0), (quiz or {}).get("aprovado", False), aulas)
    pendente = resumo_quiz is not None and not resumo_quiz["aprovado"]
    sit = regras.situacao_trilha(total, feitas, prazo, hoje, quiz_pendente=pendente)
    proxima = next((a["id"] for a in aulas if not a["concluida"]), None)
    itens, itens_feitos = total, feitas
    if resumo_quiz is not None and total:
        itens += 1
        itens_feitos += 1 if resumo_quiz["aprovado"] else 0
    return {
        "id": t["id"],
        "titulo": t["titulo"],
        "descricao": t["descricao"],
        "pilar": t["pilar"],
        "pilar_rotulo": regras.PILARES[t["pilar"]],
        "obrigatoria": t["obrigatoria"],
        "prazo": prazo,
        "situacao": _situacao_out(sit),
        "aulas_total": total,
        "aulas_concluidas": feitas,
        "percentual": regras.percentual(itens_feitos, itens),
        "proxima_aula_id": proxima,
        "quiz": resumo_quiz,
    }, sit


async def _quiz_das_trilhas(conn, trilha_ids: list, pessoa_id) -> dict:
    """{trilha_id: {"banco": n, "aprovado": bool}} — banco só de aula publicada."""
    if not trilha_ids:
        return {}
    banco = await conn.fetch(
        """
        SELECT a.trilha_id, count(*) AS n
          FROM uc_perguntas p JOIN uc_aulas a ON a.id = p.aula_id
         WHERE a.trilha_id = ANY($1::uuid[]) AND a.status = 'publicada'
         GROUP BY a.trilha_id
        """,
        trilha_ids,
    )
    aprovadas = {r["trilha_id"] for r in await conn.fetch(
        """
        SELECT DISTINCT trilha_id FROM uc_tentativas_trilha
         WHERE usuario_id = $2 AND aprovada AND trilha_id = ANY($1::uuid[])
        """,
        trilha_ids, pessoa_id,
    )}
    return {r["trilha_id"]: {"banco": r["n"], "aprovado": r["trilha_id"] in aprovadas} for r in banco}


async def _trilha_visivel_ou_404(conn, trilha_id: UUID, pessoa: dict, gestao: bool) -> dict:
    """
    A trilha, se a pessoa pode vê-la. Gestão vê qualquer uma que não esteja
    arquivada — é assim que confere um rascunho antes de publicar.
    """
    row = await conn.fetchrow(
        _SQL_TRILHAS_VISIVEIS + " AND t.id = $2", pessoa.get("cargo"), trilha_id,
    )
    if row is not None:
        d = dict(row)
        d["status"] = "publicada"
        return d
    if gestao:
        row = await conn.fetchrow(
            """
            SELECT id, titulo, descricao, pilar, status,
                   FALSE AS obrigatoria, NULL::smallint AS prazo_dias,
                   NULL::timestamptz AS desde
              FROM uc_trilhas WHERE id = $1 AND status <> 'arquivada'
            """,
            trilha_id,
        )
        if row is not None:
            return dict(row)
    raise HTTPException(404, "Trilha não encontrada.")


# ── Rotas ────────────────────────────────────────────────────────────

async def montar_painel(conn, pessoa: dict, dia: date) -> dict:
    """
    A tela inteira de uma pessoa. Separada da rota porque a visão do time
    (routers/uc_estudio.py) monta a mesma coisa para cada colaborador — e
    duas contas do "manual em dia" acabariam discordando.
    """
    cargo = pessoa.get("cargo")

    trilhas = [dict(r) for r in await conn.fetch(_SQL_TRILHAS_VISIVEIS, cargo)]
    ids = [t["id"] for t in trilhas]
    aulas = [dict(r) for r in await conn.fetch(_SQL_AULAS_COM_PROGRESSO, ids, pessoa["id"])] if ids else []

    por_trilha: dict[UUID, list[dict]] = {t["id"]: [] for t in trilhas}
    for a in aulas:
        por_trilha[a["trilha_id"]].append(a)
    quizzes = await _quiz_das_trilhas(conn, ids, pessoa["id"])

    manual, outras, pendentes = [], [], []
    for t in sorted(trilhas, key=lambda x: x["titulo"].lower()):
        lista = por_trilha[t["id"]]
        if not lista:
            continue  # trilha publicada sem aula publicada ainda não é trilha
        resumo, sit = _resumir_trilha(t, lista, pessoa.get("created_at"), dia, quizzes.get(t["id"]))
        (manual if t["obrigatoria"] else outras).append(resumo)
        iniciada = any(a["concluida"] for a in lista)
        for a in lista:
            if a["concluida"]:
                continue
            pendentes.append(regras.AulaPendente(
                aula_id=str(a["id"]), aula_titulo=a["titulo"], aula_ordem=a["ordem"],
                trilha_id=str(t["id"]), trilha_titulo=t["titulo"], pilar=t["pilar"],
                obrigatoria=t["obrigatoria"], situacao_trilha=sit.codigo,
                prazo=resumo["prazo"], trilha_iniciada=iniciada,
                concluiu_versao_anterior=a["concluiu_anterior"],
            ))
        q = resumo["quiz"]
        if q and q["liberado"] and not q["aprovado"]:
            pendentes.append(regras.AulaPendente(
                aula_id="", aula_titulo="Quiz final da trilha", aula_ordem=10_000,
                trilha_id=str(t["id"]), trilha_titulo=t["titulo"], pilar=t["pilar"],
                obrigatoria=t["obrigatoria"], situacao_trilha=sit.codigo,
                prazo=resumo["prazo"], trilha_iniciada=True,
                concluiu_versao_anterior=False, tipo="quiz",
            ))

    proxima = None
    escolha = regras.proxima_aula(pendentes)
    if escolha is not None:
        p, motivo = escolha
        duracao = next((a["duracao_min"] for a in aulas if str(a["id"]) == p.aula_id), None)
        proxima = {
            "tipo": p.tipo, "aula_id": p.aula_id or None, "aula_titulo": p.aula_titulo,
            "trilha_id": p.trilha_id, "trilha_titulo": p.trilha_titulo,
            "pilar": p.pilar, "pilar_rotulo": regras.PILARES[p.pilar],
            "motivo": motivo, "motivo_texto": regras.MOTIVOS[motivo],
            "prazo": p.prazo, "duracao_min": duracao,
        }

    pilares = []
    todas = manual + outras
    for codigo, rotulo in regras.PILARES.items():
        do_pilar = [t for t in todas if t["pilar"] == codigo]
        total = sum(t["aulas_total"] for t in do_pilar)
        feitas = sum(t["aulas_concluidas"] for t in do_pilar)
        pilares.append({
            "pilar": codigo, "rotulo": rotulo, "trilhas": len(do_pilar),
            "aulas_total": total, "aulas_concluidas": feitas,
            "percentual": regras.percentual(feitas, total),
        })

    return {
        "usuario": {"id": pessoa["id"], "nome": pessoa["nome"], "cargo": cargo},
        "hoje": dia,
        "proxima": proxima,
        "pilares": pilares,
        "manual": {
            "trilhas_total": len(manual),
            "trilhas_concluidas": sum(1 for t in manual if t["situacao"]["codigo"] == "concluida"),
            "atrasadas": sum(1 for t in manual if t["situacao"]["codigo"] == "atrasada"),
            "trilhas": manual,
        },
        "outras": outras,
    }


@router.get("/painel", response_model=PainelOut)
async def painel(
    usuario_id: UUID | None = Query(None),
    hoje: date | None = Query(None, description="Para testes: dia de referência"),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    pessoa, leitura = await _pessoa_alvo(conn, user, usuario_id)
    corpo = await montar_painel(conn, pessoa, hoje or _hoje())
    corpo["modo_leitura"] = leitura
    corpo["pode_editar_conteudo"] = eh_gestao(user)
    return corpo


@router.get("/trilhas/{trilha_id}", response_model=TrilhaDetalhe)
async def trilha(
    trilha_id: UUID,
    usuario_id: UUID | None = Query(None),
    hoje: date | None = Query(None),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    pessoa, _ = await _pessoa_alvo(conn, user, usuario_id)
    t = await _trilha_visivel_ou_404(conn, trilha_id, pessoa, eh_gestao(user))
    # Rascunho visto pela gestão mostra também as aulas em rascunho.
    so_publicadas = t["status"] == "publicada"
    rows = await conn.fetch(
        """
        SELECT a.id, a.ordem, a.titulo, a.resumo, a.duracao_min, a.status, a.versao,
               a.video_provedor IS NOT NULL AS tem_video,
               (SELECT count(*) FROM uc_materiais m WHERE m.aula_id = a.id) AS materiais,
               EXISTS (SELECT 1 FROM uc_progresso p
                        WHERE p.aula_id = a.id AND p.usuario_id = $2
                          AND p.aula_versao = a.versao AND p.concluida_em IS NOT NULL) AS concluida,
               EXISTS (SELECT 1 FROM uc_progresso q
                        WHERE q.aula_id = a.id AND q.usuario_id = $2
                          AND q.aula_versao < a.versao AND q.concluida_em IS NOT NULL) AS concluiu_anterior
          FROM uc_aulas a
         WHERE a.trilha_id = $1 AND ($3 = FALSE OR a.status = 'publicada')
         ORDER BY a.ordem
        """,
        trilha_id, pessoa["id"], so_publicadas,
    )
    aulas = []
    for r in rows:
        estado = "concluida" if r["concluida"] else ("atualizada" if r["concluiu_anterior"] else "pendente")
        aulas.append({
            "id": r["id"], "ordem": r["ordem"], "titulo": r["titulo"], "resumo": r["resumo"],
            "duracao_min": r["duracao_min"], "tem_video": r["tem_video"],
            "materiais": r["materiais"], "estado": estado, "status": r["status"],
        })
    contaveis = [dict(r) for r in rows if r["status"] == "publicada"]
    quizzes = await _quiz_das_trilhas(conn, [trilha_id], pessoa["id"])
    resumo, sit = _resumir_trilha(t, contaveis, pessoa.get("created_at"), hoje or _hoje(),
                                  quizzes.get(trilha_id))
    return {
        "id": t["id"], "titulo": t["titulo"], "descricao": t["descricao"],
        "pilar": t["pilar"], "pilar_rotulo": regras.PILARES[t["pilar"]],
        "status": t["status"], "obrigatoria": t["obrigatoria"],
        "prazo": resumo["prazo"], "situacao": resumo["situacao"],
        "percentual": resumo["percentual"], "aulas": aulas, "quiz": resumo["quiz"],
    }


async def _aula_ou_404(conn, aula_id: UUID, pessoa: dict, gestao: bool) -> tuple[dict, dict]:
    a = await conn.fetchrow("SELECT * FROM uc_aulas WHERE id = $1", aula_id)
    if a is None:
        raise HTTPException(404, "Aula não encontrada.")
    a = dict(a)
    t = await _trilha_visivel_ou_404(conn, a["trilha_id"], pessoa, gestao)
    if a["status"] != "publicada" and not gestao:
        raise HTTPException(404, "Aula não encontrada.")
    return a, t


def _registra_progresso(aula: dict, trilha: dict, leitura: bool) -> bool:
    """Só conta para quem aprende, e só aula publicada de trilha publicada."""
    return not leitura and aula["status"] == "publicada" and trilha["status"] == "publicada"


async def _perguntas(conn, aula_id: UUID) -> list[dict]:
    """O quiz da aula COM gabarito. Só para corrigir e para o estúdio."""
    rows = await conn.fetch(
        """
        SELECT p.id AS pergunta_id, p.ordem AS pordem, p.enunciado,
               a.id AS alternativa_id, a.ordem AS aordem, a.texto, a.correta
          FROM uc_perguntas p
          JOIN uc_alternativas a ON a.pergunta_id = p.id
         WHERE p.aula_id = $1
         ORDER BY p.ordem, a.ordem
        """,
        aula_id,
    )
    saida: list[dict] = []
    for r in rows:
        if not saida or saida[-1]["id"] != r["pergunta_id"]:
            saida.append({"id": r["pergunta_id"], "ordem": r["pordem"],
                          "enunciado": r["enunciado"], "alternativas": []})
        saida[-1]["alternativas"].append(
            {"id": r["alternativa_id"], "texto": r["texto"], "correta": r["correta"]}
        )
    return saida


def _lista_json(valor) -> list:
    """`erradas` vem do asyncpg como texto JSON (sem codec registrado)."""
    if isinstance(valor, str):
        return json.loads(valor)
    return list(valor or [])


async def _estado_aula(conn, aula: dict, trilha: dict, pessoa: dict, leitura: bool) -> dict:
    prog = await conn.fetchrow(
        """
        SELECT aberta_em, concluida_em FROM uc_progresso
         WHERE usuario_id = $1 AND aula_id = $2 AND aula_versao = $3
        """,
        pessoa["id"], aula["id"], aula["versao"],
    )
    anterior = await conn.fetchval(
        """
        SELECT EXISTS (SELECT 1 FROM uc_progresso
                        WHERE usuario_id = $1 AND aula_id = $2
                          AND aula_versao < $3 AND concluida_em IS NOT NULL)
        """,
        pessoa["id"], aula["id"], aula["versao"],
    )
    materiais = await conn.fetch(
        """
        SELECT id, nome_original, tipo_mime, bytes, criado_em
          FROM uc_materiais WHERE aula_id = $1 ORDER BY criado_em
        """,
        aula["id"],
    )
    so_publicadas = trilha["status"] == "publicada"
    vizinhas = await conn.fetch(
        """
        SELECT id, titulo, ordem FROM uc_aulas
         WHERE trilha_id = $1 AND ($2 = FALSE OR status = 'publicada')
         ORDER BY ordem
        """,
        aula["trilha_id"], so_publicadas,
    )
    ordem = [dict(v) for v in vizinhas]
    idx = next((i for i, v in enumerate(ordem) if v["id"] == aula["id"]), None)
    ant = ordem[idx - 1] if idx is not None and idx > 0 else None
    prox = ordem[idx + 1] if idx is not None and idx + 1 < len(ordem) else None

    aberta_em = prog["aberta_em"] if prog else None
    concluida_em = prog["concluida_em"] if prog else None
    falta = 0 if concluida_em or leitura else regras.segundos_para_liberar(
        aberta_em, aula["duracao_min"], _agora(),
    )
    return {
        "id": aula["id"], "trilha_id": aula["trilha_id"], "trilha_titulo": trilha["titulo"],
        "pilar": trilha["pilar"], "pilar_rotulo": regras.PILARES[trilha["pilar"]],
        "ordem": aula["ordem"], "titulo": aula["titulo"], "resumo": aula["resumo"],
        "conteudo_md": aula["conteudo_md"],
        "video_provedor": aula["video_provedor"], "video_ref": aula["video_ref"],
        "video_url": regras.url_do_video(aula["video_provedor"], aula["video_ref"]),
        "duracao_min": aula["duracao_min"], "versao": aula["versao"], "status": aula["status"],
        "materiais": [
            {**dict(m), "eh_imagem": m["tipo_mime"].startswith("image/")} for m in materiais
        ],
        "anterior": {"id": ant["id"], "titulo": ant["titulo"]} if ant else None,
        "proxima": {"id": prox["id"], "titulo": prox["titulo"]} if prox else None,
        "aberta_em": aberta_em, "concluida_em": concluida_em,
        "concluiu_versao_anterior": bool(anterior),
        "segundos_para_liberar": falta,
        "modo_leitura": leitura,
        "tour": regras.ler_tour(aula.get("tour")),
        "quiz_da_trilha": await _quiz_da_trilha_da_aula(conn, trilha, pessoa),
    }


@router.get("/aulas/{aula_id}", response_model=AulaDetalhe)
async def aula(
    aula_id: UUID,
    usuario_id: UUID | None = Query(None),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Abre a aula. Na primeira abertura da versão atual grava `aberta_em` —
    é dali que conta a trava do "Concluí". Em modo leitura (gestão olhando
    a UC de alguém) nada é gravado.
    """
    pessoa, leitura = await _pessoa_alvo(conn, user, usuario_id)
    a, t = await _aula_ou_404(conn, aula_id, pessoa, eh_gestao(user))
    if _registra_progresso(a, t, leitura):
        await conn.execute(
            """
            INSERT INTO uc_progresso (usuario_id, aula_id, aula_versao)
            VALUES ($1, $2, $3)
            ON CONFLICT (usuario_id, aula_id, aula_versao) DO NOTHING
            """,
            pessoa["id"], a["id"], a["versao"],
        )
    return await _estado_aula(conn, a, t, pessoa, leitura)


@router.post("/aulas/{aula_id}/concluir", response_model=AulaDetalhe)
async def concluir(
    aula_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Marca a versão atual da aula como concluída. Idempotente: concluir de
    novo devolve o mesmo estado.

    409 enquanto a trava de tempo não passou, dizendo quanto falta. A
    conta é feita aqui, com o relógio do servidor — o botão desabilitado na
    tela é conforto, não regra.
    """
    a, t = await _aula_ou_404(conn, aula_id, user, eh_gestao(user))
    if not _registra_progresso(a, t, False):
        raise HTTPException(422, "Aula em rascunho não conta como concluída. Publique antes.")
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO uc_progresso (usuario_id, aula_id, aula_versao)
            VALUES ($1, $2, $3)
            ON CONFLICT (usuario_id, aula_id, aula_versao) DO NOTHING
            """,
            user["id"], a["id"], a["versao"],
        )
        prog = await conn.fetchrow(
            """
            SELECT aberta_em, concluida_em FROM uc_progresso
             WHERE usuario_id = $1 AND aula_id = $2 AND aula_versao = $3
             FOR UPDATE
            """,
            user["id"], a["id"], a["versao"],
        )
        if prog["concluida_em"] is None:
            falta = regras.segundos_para_liberar(prog["aberta_em"], a["duracao_min"], _agora())
            if falta > 0:
                minutos = -(-falta // 60)
                raise HTTPException(
                    409,
                    f"Ainda não dá para concluir: faltam {minutos} min. "
                    f"A aula tem {a['duracao_min']} min estimados e libera na metade do tempo.",
                )
            await conn.execute(
                """
                UPDATE uc_progresso SET concluida_em = NOW()
                 WHERE usuario_id = $1 AND aula_id = $2 AND aula_versao = $3
                """,
                user["id"], a["id"], a["versao"],
            )
    return await _estado_aula(conn, a, t, user, False)


# ── Quiz final da trilha ─────────────────────────────────────────────

async def _quiz_da_trilha_da_aula(conn, trilha: dict, pessoa: dict) -> dict | None:
    """O resumo do quiz final na tela da aula (para o botão "Ir para o quiz")."""
    if trilha.get("status") != "publicada":
        return None
    aulas = await conn.fetch(
        """
        SELECT EXISTS (SELECT 1 FROM uc_progresso p
                        WHERE p.aula_id = a.id AND p.usuario_id = $2
                          AND p.aula_versao = a.versao AND p.concluida_em IS NOT NULL) AS concluida
          FROM uc_aulas a
         WHERE a.trilha_id = $1 AND a.status = 'publicada'
        """,
        trilha["id"], pessoa["id"],
    )
    info = (await _quiz_das_trilhas(conn, [trilha["id"]], pessoa["id"])).get(trilha["id"])
    if info is None:
        return None
    return _quiz_resumo(info["banco"], info["aprovado"], [dict(a) for a in aulas])


async def _banco_da_trilha(conn, trilha_id: UUID) -> list[dict]:
    """Todas as perguntas das aulas publicadas, COM gabarito, na ordem."""
    rows = await conn.fetch(
        """
        SELECT p.id AS pergunta_id, p.enunciado, a.ordem AS aula_ordem, a.titulo AS aula_titulo,
               x.id AS alternativa_id, x.texto, x.correta
          FROM uc_perguntas p
          JOIN uc_aulas a ON a.id = p.aula_id
          JOIN uc_alternativas x ON x.pergunta_id = p.id
         WHERE a.trilha_id = $1 AND a.status = 'publicada'
         ORDER BY a.ordem, p.ordem, x.ordem
        """,
        trilha_id,
    )
    banco: list[dict] = []
    for r in rows:
        if not banco or banco[-1]["id"] != r["pergunta_id"]:
            banco.append({
                "id": r["pergunta_id"], "enunciado": r["enunciado"],
                "aula_ordem": r["aula_ordem"], "aula_titulo": r["aula_titulo"],
                "alternativas": [],
            })
        banco[-1]["alternativas"].append(
            {"id": r["alternativa_id"], "texto": r["texto"], "correta": r["correta"]}
        )
    return banco


async def _situacao_quiz(conn, t: dict, pessoa: dict, agora: datetime) -> dict:
    """
    Tudo o que a tela do quiz e a correção precisam, inclusive o sorteio
    COM gabarito (`_sorteadas`, nunca vai para a tela).
    """
    banco = await _banco_da_trilha(conn, t["id"])
    if not banco:
        raise HTTPException(404, "Esta trilha não tem quiz final.")
    pendentes = await conn.fetchval(
        """
        SELECT count(*) FROM uc_aulas a
         WHERE a.trilha_id = $1 AND a.status = 'publicada'
           AND NOT EXISTS (SELECT 1 FROM uc_progresso p
                            WHERE p.aula_id = a.id AND p.usuario_id = $2
                              AND p.aula_versao = a.versao AND p.concluida_em IS NOT NULL)
        """,
        t["id"], pessoa["id"],
    )
    tentativas = [dict(r) for r in await conn.fetch(
        """
        SELECT acertos, total, nota, aprovada, erradas, perguntas, respostas, criado_em
          FROM uc_tentativas_trilha
         WHERE usuario_id = $1 AND trilha_id = $2
         ORDER BY criado_em DESC
        """,
        pessoa["id"], t["id"],
    )]
    aprovadas = [x for x in tentativas if x["aprovada"]]
    ultima = tentativas[0] if tentativas else None
    if ultima is not None:
        ultima["erradas"] = await _completar_erradas(conn, ultima)
    reprovada_em = ultima["criado_em"] if ultima and not ultima["aprovada"] else None
    semente = f"{pessoa['id']}:{t['id']}:{len(tentativas)}"
    sorteadas = regras.sortear_quiz(banco, semente)
    total = len(sorteadas)
    return {
        "trilha": t,
        "total": total,
        "nota_minima": regras.NOTA_MINIMA_QUIZ,
        "acertos_para_aprovar": regras.acertos_para_aprovar(total, regras.NOTA_MINIMA_QUIZ),
        "tentativas": len(tentativas),
        "aprovado": bool(aprovadas),
        "aprovado_em": aprovadas[-1]["criado_em"] if aprovadas else None,
        "liberado": t.get("status") == "publicada" and pendentes == 0,
        "aulas_pendentes": pendentes,
        "ultima": ultima,
        "segundos_para_refazer": regras.segundos_para_refazer(reprovada_em, agora),
        "_semente": semente,
        "_sorteadas": sorteadas,
    }


def _dict_json(valor) -> dict:
    if isinstance(valor, str):
        return json.loads(valor)
    return dict(valor or {})


async def _completar_erradas(conn, tentativa: dict) -> list[dict]:
    """
    Tentativas gravadas antes de a correção guardar o texto das erradas só
    têm número e aula. Completa com o enunciado e a alternativa marcada a
    partir do sorteio e das respostas gravados. Nunca devolve a certa.
    """
    erradas = _lista_json(tentativa["erradas"])
    faltam = [e for e in erradas if "enunciado" not in e]
    if not faltam:
        return erradas
    perguntas = _lista_json(tentativa.get("perguntas"))
    resps = _dict_json(tentativa.get("respostas"))
    pares = {}
    for e in faltam:
        n = e.get("numero") or 0
        if 1 <= n <= len(perguntas):
            pid = perguntas[n - 1]
            pares[n] = (pid, resps.get(pid))
    if not pares:
        return erradas
    try:
        pids = [UUID(pid) for pid, _ in pares.values()]
        aids = [UUID(aid) for _, aid in pares.values() if aid]
    except ValueError:
        return erradas
    enunciados = {str(r["id"]): r["enunciado"] for r in await conn.fetch(
        "SELECT id, enunciado FROM uc_perguntas WHERE id = ANY($1::uuid[])", pids)}
    textos = {str(r["id"]): r["texto"] for r in await conn.fetch(
        "SELECT id, texto FROM uc_alternativas WHERE id = ANY($1::uuid[])", aids)}
    for e in faltam:
        pid, aid = pares.get(e.get("numero"), (None, None))
        e["enunciado"] = enunciados.get(pid)
        e["sua_resposta"] = textos.get(aid) if aid else None
    return erradas


def _quiz_out(q: dict, leitura: bool) -> dict:
    t = q["trilha"]
    ultima = q["ultima"]
    responder = (q["liberado"] and not q["aprovado"] and not leitura
                 and q["segundos_para_refazer"] == 0)
    return {
        "trilha_id": t["id"], "trilha_titulo": t["titulo"],
        "pilar": t["pilar"], "pilar_rotulo": regras.PILARES[t["pilar"]],
        "total": q["total"], "nota_minima": q["nota_minima"],
        "acertos_para_aprovar": q["acertos_para_aprovar"],
        "tentativas": q["tentativas"], "aprovado": q["aprovado"], "aprovado_em": q["aprovado_em"],
        "liberado": q["liberado"], "aulas_pendentes": q["aulas_pendentes"],
        "ultima": None if ultima is None else {
            "acertos": ultima["acertos"], "total": ultima["total"], "nota": ultima["nota"],
            "aprovada": ultima["aprovada"], "erradas": ultima["erradas"],
            "em": ultima["criado_em"],
        },
        "segundos_para_refazer": q["segundos_para_refazer"],
        "espera_minutos": regras.ESPERA_REPROVACAO_MIN,
        "modo_leitura": leitura,
        "perguntas": [] if not responder else [
            {
                "id": p["id"], "numero": i, "enunciado": p["enunciado"],
                "alternativas": [
                    {"id": a["id"], "texto": a["texto"]}
                    for a in regras.embaralhar(p["alternativas"], f"{q['_semente']}:{p['id']}")
                ],
            }
            for i, p in enumerate(q["_sorteadas"], start=1)
        ],
    }


@router.get("/trilhas/{trilha_id}/quiz", response_model=QuizTrilhaOut)
async def quiz_da_trilha(
    trilha_id: UUID,
    usuario_id: UUID | None = Query(None),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    A tela do quiz final. As perguntas só vêm quando há o que responder;
    o mesmo sorteio volta no F5 (a semente só muda com uma tentativa nova).
    """
    pessoa, leitura = await _pessoa_alvo(conn, user, usuario_id)
    t = await _trilha_visivel_ou_404(conn, trilha_id, pessoa, eh_gestao(user))
    return _quiz_out(await _situacao_quiz(conn, t, pessoa, _agora()), leitura)


@router.post("/trilhas/{trilha_id}/quiz", response_model=QuizTrilhaOut)
async def responder_quiz(
    trilha_id: UUID,
    body: RespostasQuiz,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Corrige o quiz final e grava a tentativa. Aprovou: a trilha conclui.

    409: aula da trilha ainda não concluída, ou quiz já aprovado.
    429: reprovou há menos de 10 minutos. 422: envio incompleto, com
    alternativa trocada ou de um sorteio antigo — recusado sem gastar
    tentativa.
    """
    t = await _trilha_visivel_ou_404(conn, trilha_id, user, eh_gestao(user))
    if t.get("status") != "publicada":
        raise HTTPException(422, "Trilha em rascunho não tem quiz valendo. Publique antes.")
    agora = _agora()
    async with conn.transaction():
        # Dois envios ao mesmo tempo não viram duas tentativas na mesma espera.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))", f"uc-quiz:{user['id']}:{trilha_id}",
        )
        q = await _situacao_quiz(conn, t, user, agora)
        if q["aprovado"]:
            raise HTTPException(409, "Quiz já aprovado: a trilha está concluída.")
        if not q["liberado"]:
            n = q["aulas_pendentes"]
            raise HTTPException(
                409, f"Conclua {'a aula que falta' if n == 1 else f'as {n} aulas que faltam'} "
                     "da trilha antes do quiz final.",
            )
        espera = q["segundos_para_refazer"]
        if espera > 0:
            minutos = -(-espera // 60)
            raise HTTPException(
                429,
                f"Nova tentativa em {minutos} min. Enquanto isso, reveja as aulas das "
                "perguntas que você errou.",
            )
        sorteadas = q["_sorteadas"]
        try:
            c = regras.corrigir(sorteadas, body.respostas, regras.NOTA_MINIMA_QUIZ)
        except regras.ConteudoInvalido as e:
            raise HTTPException(422, str(e))
        por_id = {str(p["id"]): (i, p) for i, p in enumerate(sorteadas, start=1)}
        marcadas = {str(k): str(v) for k, v in body.respostas.items()}
        # Guarda o texto da pergunta e da alternativa MARCADA (a errada), como
        # estavam na hora: o estúdio pode editar o banco depois. A certa não.
        erradas = []
        for pid in c.erradas:
            numero, p = por_id[pid]
            marcada = next((a["texto"] for a in p["alternativas"]
                            if str(a["id"]) == marcadas.get(pid)), None)
            erradas.append({
                "numero": numero, "aula_ordem": p["aula_ordem"], "aula_titulo": p["aula_titulo"],
                "enunciado": p["enunciado"], "sua_resposta": marcada,
            })
        await conn.execute(
            """
            INSERT INTO uc_tentativas_trilha
                   (usuario_id, trilha_id, acertos, total, nota, nota_minima, aprovada,
                    perguntas, respostas, erradas, criado_em)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11)
            """,
            user["id"], trilha_id, c.acertos, c.total, c.nota, regras.NOTA_MINIMA_QUIZ, c.aprovada,
            json.dumps([str(p["id"]) for p in sorteadas]),
            json.dumps(marcadas),
            json.dumps(erradas), agora,
        )
        q = await _situacao_quiz(conn, t, user, agora)
    return _quiz_out(q, False)


@router.get("/materiais/{material_id}/url", response_model=UrlMaterial)
async def url_material(
    material_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """URL assinada de 5 minutos. Mesmo raciocínio dos anexos de tarefa."""
    problemas = material.problemas()
    if problemas:
        raise HTTPException(503, "Materiais indisponíveis: " + "; ".join(problemas))
    m = await conn.fetchrow(
        "SELECT id, aula_id, chave_s3, nome_original FROM uc_materiais WHERE id = $1",
        material_id,
    )
    if m is None:
        raise HTTPException(404, "Material não encontrado.")
    await _aula_ou_404(conn, m["aula_id"], user, eh_gestao(user))
    try:
        assinada = material.url_temporaria(m["chave_s3"], m["nome_original"])
    except Exception as e:  # pragma: no cover - depende da AWS
        raise HTTPException(502, f"Não foi possível gerar o link: {e}")
    return {"url": assinada, "expira_em_segundos": material.URL_VALIDA_SEGUNDOS}
