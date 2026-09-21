"""
HIPO — CRM: enriquecimento cadastral por CNPJ.

O que este módulo entrega, e o que ele deliberadamente NÃO faz:

  * CONSULTA NÃO GRAVA. `GET /cnpj/{cnpj}` devolve sugestão e nada mais. A
    gravação é um POST separado, disparado por quem está olhando a tela.
    Isso não é purismo de verbo HTTP: é a diretriz do produto — todo dado
    entra por formulário, atribuído a quem lançou. Um GET que grava
    produziria cadastro sem autor.

  * O DV É CONFERIDO ANTES DA CONSULTA. `services/cnpj.valido()` custa
    microssegundos; a consulta na fonte paga custa 0,5 crédito. Os sete
    CNPJs com dígito errado da carga da Oraculus teriam virado sete
    consultas pagas jogadas fora.

  * MAPEAR CNAE É AÇÃO OPERACIONAL, REMAPEAR É DE GESTÃO. Quem está
    cadastrando encontra um CNAE novo e classifica ali mesmo — travar isso
    em gestão pararia o cadastro no meio. Mas trocar o mapeamento de um
    CNAE já classificado muda a vertical de TODAS as contas futuras com
    aquele CNAE, e isso é decisão comercial, não correção de cadastro. É o
    mesmo raciocínio que separa editar conta de bloquear prospecção.

  * BUSCA REVERSA DE SÓCIO COM GRAU DE CONFIANÇA. Casar pessoa por nome
    produz falso positivo — a carga do CRM Omie já fundiu homônimos assim.
    Aqui o resultado vem etiquetado: 'alta' quando nome e documento
    mascarado batem, 'media' quando só o nome bate. A tela mostra a
    diferença em vez de afirmar parentesco societário que ninguém verificou.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database import get_conn
from routers.auth import usuario_atual
from routers.permissions import CARGOS_GESTAO
from services import cnpj as cnpj_svc
from services import enriquecimento as enriq

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class SocioOut(BaseModel):
    id: UUID | None = None
    nome: str
    documento_mascarado: str | None = None
    qualificacao: str | None = None
    faixa_etaria: str | None = None
    entrada_em: date | None = None
    eh_pj: bool = False
    fonte: str | None = None
    capturado_em: datetime | None = None


class CnaeOut(BaseModel):
    codigo: str
    descricao: str
    vertical_id: int | None = None
    vertical_nome: str | None = None
    grau_risco: int | None = None
    mapeado_em: datetime | None = None
    qtd_contas: int | None = None


class ContaExistente(BaseModel):
    """Devolvido quando o CNPJ consultado já está cadastrado."""
    conta_id: UUID
    razao_social: str
    ativo: bool
    nao_prospectar: bool


class SugestaoOut(BaseModel):
    cnpj: str
    cnpj_formatado: str
    fonte: str | None = None
    # Avisos NÃO são erro: "a LeadCNPJ não respondeu, isto veio da Receita"
    # é informação que muda o que o usuário faz com o número na tela.
    avisos: list[str] = []
    encontrado: bool
    operando: bool = True

    razao_social: str | None = None
    nome_fantasia: str | None = None
    cnae_codigo: str | None = None
    cnae_descricao: str | None = None
    cnae: CnaeOut | None = None
    cnaes_secundarios: list[dict] = []
    porte: str | None = None
    situacao_cadastral: str | None = None
    data_abertura: date | None = None
    capital_social: float | None = None
    natureza_juridica: str | None = None

    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    telefone: str | None = None
    telefone_2: str | None = None
    email: str | None = None

    num_funcionarios: int | None = None
    num_funcionarios_origem: str | None = None

    # A vertical que o mapeamento do CNAE sugere. None = CNAE ainda não
    # mapeado, e a tela oferece mapear.
    vertical_id: int | None = None
    vertical_nome: str | None = None

    socios: list[SocioOut] = []
    conta_existente: ContaExistente | None = None


class AplicarIn(BaseModel):
    # None = aplica tudo que couber. Lista = só o que o usuário marcou.
    campos: list[str] | None = None
    # Sobrescrever é escolha consciente e por isso não é o padrão. Nem
    # assim um número declarado pelo cliente é trocado por estimativa —
    # essa trava mora em services/enriquecimento/persistencia.py.
    sobrescrever: bool = False
    forcar: bool = False


class AplicarOut(BaseModel):
    conta_id: UUID
    fonte: str | None = None
    avisos: list[str] = []
    aplicados: dict = {}
    mantidos: list[dict] = []
    cnae: CnaeOut | None = None
    socios_novos: int = 0
    cnaes_secundarios_novos: int = 0


class MapearCnaeIn(BaseModel):
    vertical_id: int | None = None
    grau_risco: int | None = Field(None, ge=1, le=4)


class EmpresaDoSocio(BaseModel):
    conta_id: UUID | None = None
    razao_social: str
    cnpj_formatado: str | None = None
    qualificacao: str | None = None
    entrada_em: date | None = None
    confianca: str
    externa: bool = False


class EmpresasDoSocioOut(BaseModel):
    nome: str
    avisos: list[str] = []
    empresas: list[EmpresaDoSocio] = []


class ResumoEnriquecimento(BaseModel):
    fontes: list[str]
    contas_ativas: int
    contas_enriquecidas: int
    contas_sem_cnae: int
    cnaes_conhecidos: int
    cnaes_a_mapear: int
    contas_em_cnae_nao_mapeado: int


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validar_cnpj(valor: str) -> str:
    digitos = cnpj_svc.normalizar(valor)
    if not cnpj_svc.valido(digitos):
        raise HTTPException(422, "CNPJ inválido.")
    return digitos


async def _cnae_completo(conn, codigo: str | None) -> dict | None:
    if not codigo:
        return None
    row = await conn.fetchrow(
        """
        SELECT c.codigo, c.descricao, c.vertical_id, v.nome AS vertical_nome,
               c.grau_risco, c.mapeado_em,
               (SELECT count(*) FROM contas ct WHERE ct.cnae_codigo = c.codigo)
                   AS qtd_contas
          FROM cnaes c
          LEFT JOIN verticais v ON v.id = c.vertical_id
         WHERE c.codigo = $1
        """,
        codigo,
    )
    return dict(row) if row else None


# ── Consulta ─────────────────────────────────────────────────────────────────

@router.get("/cnpj/{cnpj}", response_model=SugestaoOut)
async def consultar_cnpj(
    cnpj: str,
    forcar: bool = Query(False, description="Ignora o cache e vai à fonte."),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Consulta o CNPJ nas fontes configuradas e devolve a SUGESTÃO.

    Não grava nada na conta. Serve ao formulário de nova conta e ao botão
    "Atualizar" da conta existente.

    Quando o CNPJ já está cadastrado, `conta_existente` vem preenchido — é
    o mesmo serviço que o 409 do POST /crm/contas presta, oferecido antes de
    o usuário digitar o resto do formulário.
    """
    digitos = _validar_cnpj(cnpj)

    existente = await conn.fetchrow(
        """
        SELECT id, razao_social, ativo, nao_prospectar
          FROM contas WHERE cnpj = $1
        """,
        digitos,
    )
    conta_existente = None
    if existente:
        conta_existente = {
            "conta_id": existente["id"],
            "razao_social": existente["razao_social"],
            "ativo": existente["ativo"],
            "nao_prospectar": existente["nao_prospectar"],
        }

    dados, avisos = await enriq.consultar(
        conn, digitos,
        user_id=user["id"],
        conta_id=existente["id"] if existente else None,
        forcar=forcar,
    )

    base = {
        "cnpj": digitos,
        "cnpj_formatado": cnpj_svc.formatar(digitos),
        "avisos": avisos,
        "conta_existente": conta_existente,
    }
    if dados is None:
        return {**base, "encontrado": False, "fonte": None}

    # O CNAE é registrado na consulta, não só na aplicação: é assim que a
    # lista de "CNAEs a mapear" enxerga uma atividade nova antes de a conta
    # existir. Registrar o código não classifica nada — nasce não mapeado.
    cnae = await enriq.garantir_cnae(conn, dados.cnae_codigo, dados.cnae_descricao)
    cnae_completo = await _cnae_completo(conn, dados.cnae_codigo)

    return {
        **base,
        "encontrado": True,
        "fonte": dados.fonte,
        "operando": dados.operando,
        "razao_social": dados.razao_social,
        "nome_fantasia": dados.nome_fantasia,
        "cnae_codigo": dados.cnae_codigo,
        "cnae_descricao": dados.cnae_descricao,
        "cnae": cnae_completo,
        "cnaes_secundarios": [
            {"codigo": c, "descricao": d} for c, d in dados.cnaes_secundarios
        ],
        "porte": dados.porte,
        "situacao_cadastral": dados.situacao_cadastral,
        "data_abertura": dados.data_abertura,
        "capital_social": dados.capital_social,
        "natureza_juridica": dados.natureza_juridica,
        "cep": dados.cep,
        "logradouro": dados.logradouro,
        "numero": dados.numero,
        "complemento": dados.complemento,
        "bairro": dados.bairro,
        "cidade": dados.cidade,
        "uf": dados.uf,
        "telefone": dados.telefone,
        "telefone_2": dados.telefone_2,
        "email": dados.email,
        "num_funcionarios": dados.num_funcionarios,
        "num_funcionarios_origem": dados.num_funcionarios_origem,
        "vertical_id": (cnae or {}).get("vertical_id"),
        "vertical_nome": (cnae_completo or {}).get("vertical_nome"),
        "socios": [
            {
                "nome": s.nome,
                "documento_mascarado": s.documento_mascarado,
                "qualificacao": s.qualificacao,
                "faixa_etaria": s.faixa_etaria,
                "entrada_em": s.entrada_em,
                "eh_pj": s.eh_pj,
                "fonte": dados.fonte,
            }
            for s in dados.socios
        ],
    }


@router.post("/contas/{conta_id}/aplicar", response_model=AplicarOut)
async def aplicar_na_conta(
    conta_id: UUID,
    payload: AplicarIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Consulta e grava na conta, respeitando o que já estava preenchido.

    O corpo permite restringir os campos (`campos`) e autorizar sobrescrita
    (`sobrescrever`). O que NÃO é negociável por parâmetro: número de
    funcionários declarado pelo cliente não é trocado por estimativa de
    fonte paga, nem com `sobrescrever=true`.
    """
    row = await conn.fetchrow("SELECT cnpj FROM contas WHERE id = $1", conta_id)
    if row is None:
        raise HTTPException(404, "Conta não encontrada.")

    dados, avisos = await enriq.consultar(
        conn, row["cnpj"], user_id=user["id"], conta_id=conta_id,
        forcar=payload.forcar,
    )
    if dados is None:
        raise HTTPException(
            422,
            {
                "erro": "enriquecimento_indisponivel",
                "mensagem": "Nenhuma fonte devolveu dados para este CNPJ.",
                "avisos": avisos,
            },
        )

    resultado = await enriq.aplicar(
        conn, conta_id, dados, user["id"],
        campos=payload.campos, sobrescrever=payload.sobrescrever,
    )

    return {
        "conta_id": conta_id,
        "fonte": dados.fonte,
        "avisos": avisos,
        "aplicados": {k: str(v) for k, v in resultado["aplicados"].items()},
        "mantidos": [
            {k: (str(v) if v is not None else None) for k, v in m.items()}
            for m in resultado["mantidos"]
        ],
        "cnae": await _cnae_completo(conn, dados.cnae_codigo),
        "socios_novos": resultado["socios"],
        "cnaes_secundarios_novos": resultado["secundarios"],
    }


# ── CNAEs ────────────────────────────────────────────────────────────────────

@router.get("/cnaes", response_model=list[CnaeOut])
async def listar_cnaes(
    apenas_nao_mapeados: bool = False,
    q: str | None = Query(None, max_length=120),
    limit: int = Query(200, ge=1, le=1000),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    CNAEs conhecidos, com quantas contas usam cada um.

    Ordenado por quantidade de contas: mapear o CNAE de 40 contas antes do
    que aparece uma vez é o que faz a vertical se preencher sozinha na
    próxima consulta.
    """
    rows = await conn.fetch(
        """
        SELECT c.codigo, c.descricao, c.vertical_id, v.nome AS vertical_nome,
               c.grau_risco, c.mapeado_em,
               count(ct.id) AS qtd_contas
          FROM cnaes c
          LEFT JOIN verticais v ON v.id = c.vertical_id
          LEFT JOIN contas ct ON ct.cnae_codigo = c.codigo
         WHERE ($1::bool IS NOT TRUE
                OR (c.vertical_id IS NULL AND c.grau_risco IS NULL))
           AND ($2::text IS NULL OR c.descricao ILIKE $2 OR c.codigo LIKE $2)
         GROUP BY c.codigo, c.descricao, c.vertical_id, v.nome,
                  c.grau_risco, c.mapeado_em
         ORDER BY count(ct.id) DESC, c.descricao
         LIMIT $3
        """,
        apenas_nao_mapeados,
        f"%{q.strip()}%" if q else None,
        limit,
    )
    return [dict(r) for r in rows]


@router.patch("/cnaes/{codigo}", response_model=CnaeOut)
async def mapear_cnae(
    codigo: str,
    payload: MapearCnaeIn,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Define a vertical comercial e o grau de risco (NR-4) de um CNAE.

    CNAE ainda não mapeado: qualquer cargo com o módulo `crm` classifica —
    é o que permite resolver no meio do cadastro em vez de parar e chamar
    alguém.

    CNAE JÁ MAPEADO: só gestão. Remapear muda a classificação de toda conta
    futura com aquele CNAE; é decisão comercial, como liberar prospecção.
    """
    digitos = "".join(ch for ch in codigo if ch.isdigit())
    if len(digitos) != 7:
        raise HTTPException(422, "Código de CNAE deve ter 7 dígitos.")

    atual = await conn.fetchrow(
        "SELECT codigo, vertical_id, grau_risco FROM cnaes WHERE codigo = $1",
        digitos,
    )
    if atual is None:
        raise HTTPException(
            404,
            "CNAE desconhecido. Ele é registrado na primeira consulta de um "
            "CNPJ que o utilize.",
        )

    ja_mapeado = atual["vertical_id"] is not None or atual["grau_risco"] is not None
    if ja_mapeado and user.get("cargo") not in CARGOS_GESTAO:
        raise HTTPException(
            403,
            "Este CNAE já está classificado. Só gestão pode alterar o "
            "mapeamento, porque ele vale para todas as contas.",
        )

    if payload.vertical_id is not None:
        existe = await conn.fetchval(
            "SELECT 1 FROM verticais WHERE id = $1", payload.vertical_id
        )
        if not existe:
            raise HTTPException(422, "vertical_id não existe.")

    # Limpar o mapeamento (os dois campos nulos) tem que zerar a autoria
    # junto: o CHECK ck_cnaes_mapeado aceita mapeado_em preenchido sem
    # classificação, mas isso seria "alguém mapeou para nada".
    limpando = payload.vertical_id is None and payload.grau_risco is None

    # O ::uuid não é decorativo. Dentro de um CASE com NULL no outro ramo,
    # o asyncpg perde a inferência de tipo do parâmetro e manda o id como
    # text — DatatypeMismatchError na cara do usuário. Fora do CASE, como
    # nas outras rotas do projeto, a inferência funciona sozinha.
    row = await conn.fetchrow(
        """
        UPDATE cnaes
           SET vertical_id = $2,
               grau_risco  = $3,
               mapeado_por = CASE WHEN $4 THEN NULL ELSE $5::uuid END,
               mapeado_em  = CASE WHEN $4 THEN NULL ELSE NOW() END
         WHERE codigo = $1
     RETURNING codigo, descricao, vertical_id, grau_risco, mapeado_em
        """,
        digitos, payload.vertical_id, payload.grau_risco, limpando,
        str(user["id"]),
    )
    return await _cnae_completo(conn, row["codigo"])


# ── Sócios ───────────────────────────────────────────────────────────────────

@router.get("/contas/{conta_id}/socios", response_model=list[SocioOut])
async def socios_da_conta(
    conta_id: UUID,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Quadro societário guardado para esta conta.

    Sócio que saiu do QSA continua listado, com a data de captura — a
    informação de que alguém esteve na empresa não é apagada por uma
    reconsulta.
    """
    if not await conn.fetchval("SELECT 1 FROM contas WHERE id = $1", conta_id):
        raise HTTPException(404, "Conta não encontrada.")
    rows = await conn.fetch(
        """
        SELECT id, nome, documento_mascarado, qualificacao, faixa_etaria,
               entrada_em, eh_pj, fonte, capturado_em
          FROM conta_socios
         WHERE conta_id = $1
         ORDER BY eh_pj, nome
        """,
        conta_id,
    )
    return [dict(r) for r in rows]


@router.get("/socios/empresas", response_model=EmpresasDoSocioOut)
async def empresas_do_socio(
    nome: str = Query(..., min_length=3, max_length=200),
    documento: str | None = Query(None, max_length=20),
    excluir_conta_id: UUID | None = None,
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Outras empresas em que este sócio aparece.

    DUAS BUSCAS, E A DIFERENÇA IMPORTA.

    A interna varre `conta_socios` — só enxerga empresas que já estão no
    HIPO e foram enriquecidas. É rápida, de graça e sempre disponível.

    A externa depende de fonte paga (`LEADCNPJ_CAMINHO_SOCIO` no .env) e é
    a única que enxerga empresa fora da base. Desligada, a resposta traz o
    aviso: "nenhuma outra empresa" precisa poder ser lido como "não
    procurei fora daqui", nunca como "não existe".

    CONFIANÇA: 'alta' quando nome e documento mascarado batem; 'media'
    quando só o nome bate. Homônimo é real — a carga do CRM Omie fundiu
    duas pessoas diferentes casando por nome.
    """
    normalizado = enriq.normalizar_nome(nome)
    if not normalizado:
        raise HTTPException(422, "Nome de sócio inválido.")

    rows = await conn.fetch(
        """
        SELECT c.id AS conta_id, c.razao_social, c.cnpj,
               s.qualificacao, s.entrada_em, s.documento_mascarado
          FROM conta_socios s
          JOIN contas c ON c.id = s.conta_id
         WHERE s.nome_normalizado = $1
           AND ($2::uuid IS NULL OR c.id <> $2)
         ORDER BY c.razao_social
         LIMIT 100
        """,
        normalizado, excluir_conta_id,
    )

    doc = (documento or "").strip() or None
    empresas = [
        {
            "conta_id": r["conta_id"],
            "razao_social": r["razao_social"],
            "cnpj_formatado": cnpj_svc.formatar(r["cnpj"]),
            "qualificacao": r["qualificacao"],
            "entrada_em": r["entrada_em"],
            "confianca": (
                "alta"
                if doc and r["documento_mascarado"] == doc
                else "media"
            ),
            "externa": False,
        }
        for r in rows
    ]

    avisos: list[str] = []
    externas, erro = await enriq.empresas_do_socio(nome, doc)
    if erro:
        avisos.append(erro)
    for item in externas:
        razao = (
            item.get("razao_social")
            or item.get("nome")
            or item.get("company_name")
        )
        if not razao:
            continue
        documento_externo = (
            item.get("cnpj") or item.get("document") or ""
        )
        empresas.append({
            "conta_id": None,
            "razao_social": str(razao)[:200],
            "cnpj_formatado": cnpj_svc.formatar(documento_externo) or None,
            "qualificacao": item.get("qualificacao") or item.get("role"),
            "entrada_em": None,
            "confianca": "media",
            "externa": True,
        })

    return {"nome": nome, "avisos": avisos, "empresas": empresas}


# ── Resumo ───────────────────────────────────────────────────────────────────

@router.get("/resumo", response_model=ResumoEnriquecimento)
async def resumo(conn=Depends(get_conn), user=Depends(usuario_atual)):
    """
    Estado do enriquecimento na base. É o que alimenta os KPIs da tela.

    `contas_em_cnae_nao_mapeado` é o número que importa: são contas com
    CNAE conhecido esperando alguém dizer qual vertical é aquela. Cada
    mapeamento resolve várias contas de uma vez.
    """
    row = await conn.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM contas WHERE ativo) AS contas_ativas,
            (SELECT count(*) FROM contas WHERE enriquecida_em IS NOT NULL)
                AS contas_enriquecidas,
            (SELECT count(*) FROM contas WHERE ativo AND cnae_codigo IS NULL)
                AS contas_sem_cnae,
            (SELECT count(*) FROM cnaes) AS cnaes_conhecidos,
            (SELECT count(*) FROM cnaes
              WHERE vertical_id IS NULL AND grau_risco IS NULL)
                AS cnaes_a_mapear,
            (SELECT count(*) FROM contas ct
               JOIN cnaes c ON c.codigo = ct.cnae_codigo
              WHERE ct.ativo AND c.vertical_id IS NULL)
                AS contas_em_cnae_nao_mapeado
        """
    )
    return {**dict(row), "fontes": enriq.fontes_habilitadas()}
