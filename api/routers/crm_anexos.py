"""
HIPO — Anexos de tarefa.

Router próprio, e não mais rotas dentro de crm_tarefas.py, por dois
motivos: aquele arquivo já passa de 35 KB, e o anexo tem um ciclo de vida
seu (sobe, é lido por URL assinada, é removido) que não se mistura com a
máquina de estado de concluir/cancelar.

O ENDEREÇO DO ANEXO NÃO CARREGA A TAREFA
  `/crm/anexos/{id}/url` e `/crm/anexos/{id}` não repetem o id da tarefa.
  Mesma escolha das propostas: o identificador do arquivo tem de bastar
  sozinho, porque ele viaja — para o `<img src>`, para um copiar-e-colar,
  para um log. A tarefa é descoberta pelo JOIN, e a permissão é conferida
  a partir dela.

O UPLOAD PASSA POR AQUI, e não por presigned PUT direto do navegador.
  Presigned PUT seria uma requisição a menos, mas entrega ao cliente a
  decisão de qual tipo e qual tamanho gravar — o servidor assinaria no
  escuro. Passando por aqui, tipo e tamanho são conferidos com o arquivo
  na mão, e o bucket dispensa configuração de CORS.

A LEITURA NÃO PASSA POR AQUI
  A API devolve uma URL assinada e sai da frente. Servir os bytes faria
  cada print de 2 MB atravessar o uvicorn — que é o mesmo processo que
  responde o kanban.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import (
    APIRouter, Depends, File, HTTPException, UploadFile, status as http,
)
from pydantic import BaseModel

from database import get_conn
from routers.auth import usuario_atual
from services import anexo as regras
from services.anexo import AnexoInvalido

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class AnexoOut(BaseModel):
    id: UUID
    tarefa_id: UUID
    nome_original: str
    tipo_mime: str
    bytes: int
    # A tela decide entre <img> e ícone de PDF por aqui, sem repetir a
    # lista de tipos no frontend.
    eh_imagem: bool
    enviado_por: UUID | None
    enviado_por_nome: str | None
    criado_em: datetime


class UrlAnexo(BaseModel):
    url: str
    expira_em_segundos: int


# ── SQL compartilhado ────────────────────────────────────────────────

_SELECT_BASE = """
    SELECT a.id, a.tarefa_id, a.nome_original, a.tipo_mime, a.bytes,
           a.enviado_por, u.nome AS enviado_por_nome, a.criado_em
      FROM tarefa_anexos a
      LEFT JOIN usuarios u ON u.id = a.enviado_por
"""


def _linha(row) -> dict:
    d = dict(row)
    d["eh_imagem"] = d["tipo_mime"].startswith("image/")
    return d


async def _tarefa_ou_404(conn, tarefa_id: UUID) -> dict:
    row = await conn.fetchrow(
        "SELECT id, concluida_em, cancelada_em FROM tarefas WHERE id = $1",
        tarefa_id,
    )
    if row is None:
        raise HTTPException(404, "Tarefa não encontrada.")
    return dict(row)


async def _anexo_ou_404(conn, anexo_id: UUID) -> dict:
    """
    O anexo com o estado da tarefa dona junto. O JOIN evita o N+1 óbvio
    (buscar anexo, depois buscar tarefa) em toda remoção.
    """
    row = await conn.fetchrow(
        """
        SELECT a.id, a.tarefa_id, a.chave_s3, a.nome_original, a.tipo_mime,
               t.concluida_em, t.cancelada_em
          FROM tarefa_anexos a
          JOIN tarefas t ON t.id = a.tarefa_id
         WHERE a.id = $1
        """,
        anexo_id,
    )
    if row is None:
        raise HTTPException(404, "Anexo não encontrado.")
    return dict(row)


def _exigir_servico():
    problemas = regras.problemas()
    if problemas:
        # 503 e não 500: não é bug, é configuração ausente, e a mensagem
        # diz exatamente o que falta. Foi a lição do python-pptx da 009,
        # em que a tela dizia só "erro ao gerar".
        raise HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE,
            "Anexos indisponíveis: " + "; ".join(problemas),
        )


def _exigir_aberta(tarefa: dict) -> None:
    if not regras.pode_alterar(tarefa["concluida_em"], tarefa["cancelada_em"]):
        raise HTTPException(
            422,
            "Tarefa fechada: o histórico é imutável e os anexos dela também.",
        )


# ── Rotas ────────────────────────────────────────────────────────────

@router.get("/tarefas/{tarefa_id}/anexos", response_model=list[AnexoOut])
async def listar(
    tarefa_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Lista sem tocar no S3. A URL de cada arquivo é pedida à parte, só
    para o que a tela vai realmente mostrar — assinar dez URLs para
    quem vai olhar uma é trabalho jogado fora, e cada assinatura tem
    validade curta correndo desde a emissão.
    """
    await _tarefa_ou_404(conn, tarefa_id)
    linhas = await conn.fetch(
        f"{_SELECT_BASE} WHERE a.tarefa_id = $1 ORDER BY a.criado_em",
        tarefa_id,
    )
    return [_linha(r) for r in linhas]


@router.post(
    "/tarefas/{tarefa_id}/anexos",
    response_model=AnexoOut,
    status_code=http.HTTP_201_CREATED,
)
async def enviar(
    tarefa_id: UUID,
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Recebe o arquivo, valida, grava no S3 e só então registra no banco.

    A ORDEM IMPORTA. Gravar a linha antes do upload deixaria, num S3 fora
    do ar, uma tarefa exibindo um anexo que não existe — e a tela
    quebraria ao pedir a URL dele. Na ordem inversa, a falha no meio
    deixa no máximo um objeto órfão no bucket: invisível, barato, e sem
    nenhum efeito na tela.
    """
    _exigir_servico()
    tarefa = await _tarefa_ou_404(conn, tarefa_id)
    _exigir_aberta(tarefa)

    try:
        extensao = regras.validar_tipo(arquivo.content_type)
        conteudo = await arquivo.read()
        regras.validar_tamanho(len(conteudo))

        ja_tem = await conn.fetchval(
            "SELECT count(*) FROM tarefa_anexos WHERE tarefa_id = $1", tarefa_id
        )
        regras.validar_quantidade(ja_tem)
    except AnexoInvalido as e:
        raise HTTPException(422, str(e))

    anexo_id = uuid4()
    chave = regras.chave_do_objeto(tarefa_id, anexo_id, extensao)
    nome = regras.nome_seguro(arquivo.filename, extensao)
    tipo = arquivo.content_type.split(";")[0].strip().lower()

    try:
        regras.subir(chave, conteudo, tipo)
    except Exception as e:  # pragma: no cover - depende da AWS
        raise HTTPException(502, f"Não foi possível gravar o arquivo: {e}")

    row = await conn.fetchrow(
        """
        INSERT INTO tarefa_anexos
            (id, tarefa_id, chave_s3, nome_original, tipo_mime, bytes, enviado_por)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """,
        anexo_id, tarefa_id, chave, nome, tipo, len(conteudo), user["id"],
    )

    novo = await conn.fetchrow(f"{_SELECT_BASE} WHERE a.id = $1", row["id"])
    return _linha(novo)


@router.get("/anexos/{anexo_id}/url", response_model=UrlAnexo)
async def url(
    anexo_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    URL assinada de leitura. Curta de propósito: a URL é um segredo
    portátil — quem a copiar abre o arquivo sem passar pelo login.
    """
    _exigir_servico()
    anexo = await _anexo_ou_404(conn, anexo_id)
    try:
        assinada = regras.url_temporaria(anexo["chave_s3"], anexo["nome_original"])
    except Exception as e:  # pragma: no cover - depende da AWS
        raise HTTPException(502, f"Não foi possível gerar o link: {e}")
    return {"url": assinada, "expira_em_segundos": regras.URL_VALIDA_SEGUNDOS}


@router.delete("/anexos/{anexo_id}", status_code=http.HTTP_204_NO_CONTENT)
async def remover(
    anexo_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Remove o anexo de uma tarefa ABERTA.

    A linha sai primeiro, o objeto depois. Se o S3 falhar, sobra um
    órfão no bucket — invisível e barato. Na ordem inversa, uma falha no
    banco deixaria a tela exibindo um anexo cujo arquivo já não existe,
    que é o modo de falha ruim.

    O bucket tem versionamento: o delete cria um marker e a versão
    anterior continua recuperável. Exclusão acidental de prova tem volta.
    """
    _exigir_servico()
    anexo = await _anexo_ou_404(conn, anexo_id)
    _exigir_aberta(anexo)

    await conn.execute("DELETE FROM tarefa_anexos WHERE id = $1", anexo_id)

    try:
        regras.remover(anexo["chave_s3"])
    except Exception:  # pragma: no cover - depende da AWS
        # Silencioso: para quem está na tela o anexo saiu, e saiu mesmo.
        # Um erro aqui só significa storage pago a mais.
        pass
    return None
