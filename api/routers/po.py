"""
HIPO — Router de POs
Endpoints: upload, reconciliação, painel ADM, calendário de repasses.
"""
import os
import uuid
import shutil
from datetime import date
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from database import get_conn
from routers.auth import usuario_atual
from parsers.po_parser import parse_po_arquivo, detectar_tipo

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/home/hipo/app/uploads")


# ── UPLOAD DE PO ──────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_po(
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Recebe um arquivo de PO, detecta o tipo, persiste e executa a reconciliação.
    """
    nome = arquivo.filename
    try:
        tipo, tem_enabler = detectar_tipo(nome)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Salva o arquivo temporariamente
    dest_dir = os.path.join(UPLOAD_DIR, "po")
    os.makedirs(dest_dir, exist_ok=True)
    caminho = os.path.join(dest_dir, f"{uuid.uuid4()}_{nome}")
    with open(caminho, "wb") as f:
        shutil.copyfileobj(arquivo.file, f)

    # Parseia
    resultado = parse_po_arquivo(caminho)

    if resultado["erros"]:
        os.remove(caminho)
        raise HTTPException(422, {"erros": resultado["erros"]})

    # Registra o upload
    upload_id = await conn.fetchval(
        """
        INSERT INTO po_uploads (nome_arquivo, tipo, tem_enabler, semana_ref, total_linhas)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        nome,
        resultado["tipo"],
        resultado["tem_enabler"],
        resultado["semana_ref"],
        resultado["total"],
    )

    # Insere as linhas
    for linha in resultado["linhas"]:
        await conn.execute(
            """
            INSERT INTO po_linhas (
                upload_id, tipo, tem_enabler, referencia_aplicativo,
                razao_social, cnpj, plano, valor_bruto, valor_liquido,
                impostos, fundo_marketing, data_ativacao,
                contador_nome, contador_cnpj, comissao_contador,
                ativado_por_email, premio,
                parcela_numero, parcela_total, ep_email
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20
            )
            """,
            str(upload_id),
            linha["tipo"],
            linha["tem_enabler"],
            linha.get("referencia_aplicativo"),
            linha.get("razao_social"),
            linha.get("cnpj"),
            linha.get("plano"),
            linha.get("valor_bruto"),
            linha.get("valor_liquido"),
            linha.get("impostos"),
            linha.get("fundo_marketing"),
            linha.get("data_ativacao"),
            linha.get("contador_nome"),
            linha.get("contador_cnpj"),
            linha.get("comissao_contador"),
            linha.get("ativado_por_email"),
            linha.get("premio"),
            linha.get("parcela_numero"),
            linha.get("parcela_total"),
            linha.get("ep_email"),
        )

    # Executa reconciliação
    await _reconciliar(conn, str(upload_id), resultado["semana_ref"])

    # Atualiza repasse_calendario se for REPASSE
    if resultado["tipo"] == "REPASSE":
        await _atualizar_repasse_calendario(conn, str(upload_id))

    # Marca como processado
    await conn.execute(
        "UPDATE po_uploads SET processado = TRUE WHERE id = $1",
        upload_id
    )

    return {
        "upload_id": str(upload_id),
        "tipo": resultado["tipo"],
        "tem_enabler": resultado["tem_enabler"],
        "total_linhas": resultado["total"],
        "semana_ref": str(resultado["semana_ref"]) if resultado["semana_ref"] else None,
        "message": "PO processada e reconciliação executada com sucesso.",
    }


# ── RECONCILIAÇÃO ─────────────────────────────────────────────────────────────

async def _reconciliar(conn, upload_id: str, semana_ref):
    """
    Cruza as linhas da PO recebida com a projeção da semana.
    Classifica cada linha em CONFORME / DIVERGENTE / INESPERADO.
    Gera registros AUSENTE para os que estavam na projeção mas não chegaram.
    """
    if not semana_ref:
        return

    # Busca projeção da semana
    projecao = await conn.fetch(
        "SELECT * FROM po_projecao_semanal WHERE semana_ref = $1", semana_ref
    )
    proj_map = {r["referencia_aplicativo"]: r for r in projecao}

    # Classifica linhas recebidas
    linhas = await conn.fetch(
        "SELECT * FROM po_linhas WHERE upload_id = $1", upload_id
    )

    for linha in linhas:
        ref = linha["referencia_aplicativo"]
        proj = proj_map.get(ref)

        if proj is None:
            status = "INESPERADO"
            valor_esperado = None
            divergencia = None
            obs = "Não estava na projeção semanal"
        else:
            valor_esperado = float(proj["valor_esperado"] or 0)
            valor_recebido = float(linha["valor_liquido"] or 0)
            divergencia = round(valor_recebido - valor_esperado, 2)
            tolerancia = 0.10  # 10% de tolerância para variações pequenas
            if abs(divergencia) <= valor_esperado * tolerancia:
                status = "CONFORME"
                obs = None
            else:
                status = "DIVERGENTE"
                obs = f"Esperado: R${valor_esperado:.2f} | Recebido: R${valor_recebido:.2f}"

        await conn.execute(
            """
            UPDATE po_linhas
            SET status_reconciliacao = $1,
                valor_esperado = $2,
                divergencia_valor = $3,
                observacao_reconciliacao = $4
            WHERE id = $5
            """,
            status, valor_esperado, divergencia, obs, linha["id"]
        )

    # Gera AUSENTES (estavam na projeção mas não chegaram)
    refs_recebidas = {l["referencia_aplicativo"] for l in linhas}
    for ref, proj in proj_map.items():
        if ref not in refs_recebidas:
            # Busca dados do BD Ativados para enriquecer
            ba = await conn.fetchrow(
                "SELECT razao_social FROM bd_ativados WHERE referencia_aplicativo = $1", ref
            )
            await conn.execute(
                """
                INSERT INTO po_linhas (
                    upload_id, tipo, tem_enabler, referencia_aplicativo,
                    razao_social, status_reconciliacao,
                    valor_esperado, observacao_reconciliacao
                ) VALUES ($1, $2, FALSE, $3, $4, 'AUSENTE', $5, $6)
                """,
                upload_id,
                str(proj["tipo"]),
                ref,
                ba["razao_social"] if ba else None,
                float(proj["valor_esperado"] or 0),
                "Esperado mas não recebido nesta semana",
            )


async def _atualizar_repasse_calendario(conn, upload_id: str):
    """Atualiza o calendário de parcelas de repasse."""
    linhas = await conn.fetch(
        """
        SELECT * FROM po_linhas
        WHERE upload_id = $1 AND tipo = 'REPASSE'
        """, upload_id
    )
    for linha in linhas:
        ref = linha["referencia_aplicativo"]
        num = linha["parcela_numero"]
        total = linha["parcela_total"]
        if not num or not total:
            continue
        # Garante que o calendário existe
        await conn.execute(
            """
            INSERT INTO repasse_calendario (referencia_aplicativo, razao_social, ep_email, total_parcelas, valor_parcela)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (referencia_aplicativo) DO NOTHING
            """,
            ref,
            linha["razao_social"],
            linha["ep_email"],
            total,
            float(linha["valor_liquido"] or 0),
        )
        # Atualiza a parcela específica
        if 1 <= num <= 6:
            await conn.execute(
                f"""
                UPDATE repasse_calendario
                SET parcela_{num}_recebida = TRUE,
                    parcela_{num}_data = CURRENT_DATE,
                    parcela_{num}_upload_id = $1,
                    updated_at = NOW()
                WHERE referencia_aplicativo = $2
                """,
                upload_id, ref
            )


# ── ENDPOINTS DE CONSULTA ─────────────────────────────────────────────────────

@router.get("/reconciliacao/ultima")
async def reconciliacao_ultima(conn=Depends(get_conn)):
    """Resumo da última reconciliação semanal."""
    rows = await conn.fetch("""
        SELECT
            pl.tipo,
            pl.tem_enabler,
            pl.status_reconciliacao,
            COUNT(*) AS quantidade,
            COALESCE(SUM(pl.valor_liquido), 0) AS valor_total,
            COALESCE(SUM(pl.divergencia_valor), 0) AS divergencia_total
        FROM po_linhas pl
        JOIN po_uploads pu ON pu.id = pl.upload_id
        WHERE pu.semana_ref = (
            SELECT MAX(semana_ref) FROM po_uploads WHERE processado = TRUE
        )
        GROUP BY pl.tipo, pl.tem_enabler, pl.status_reconciliacao
        ORDER BY pl.tipo, pl.status_reconciliacao
    """)
    return [dict(r) for r in rows]


@router.get("/reconciliacao/ausentes")
async def po_ausentes(conn=Depends(get_conn)):
    """Lista clientes ausentes na última semana."""
    rows = await conn.fetch("""
        SELECT
            pl.referencia_aplicativo,
            pl.razao_social,
            pl.tipo,
            pl.valor_esperado,
            ba.situacao,
            ba.saude_paciente,
            ba.contador_nome,
            ba.dia_faturamento
        FROM po_linhas pl
        LEFT JOIN bd_ativados ba ON ba.referencia_aplicativo = pl.referencia_aplicativo
        JOIN po_uploads pu ON pu.id = pl.upload_id
        WHERE pl.status_reconciliacao = 'AUSENTE'
          AND pu.semana_ref = (
            SELECT MAX(semana_ref) FROM po_uploads WHERE processado = TRUE
          )
        ORDER BY pl.valor_esperado DESC NULLS LAST
    """)
    return [dict(r) for r in rows]


@router.get("/reconciliacao/divergentes")
async def po_divergentes(conn=Depends(get_conn)):
    """Lista POs com divergência de valor."""
    rows = await conn.fetch("""
        SELECT
            pl.referencia_aplicativo,
            pl.razao_social,
            pl.tipo,
            pl.valor_esperado,
            pl.valor_liquido AS valor_recebido,
            pl.divergencia_valor,
            pl.observacao_reconciliacao,
            pu.semana_ref
        FROM po_linhas pl
        JOIN po_uploads pu ON pu.id = pl.upload_id
        WHERE pl.status_reconciliacao = 'DIVERGENTE'
          AND pu.semana_ref = (
            SELECT MAX(semana_ref) FROM po_uploads WHERE processado = TRUE
          )
        ORDER BY ABS(pl.divergencia_valor) DESC NULLS LAST
    """)
    return [dict(r) for r in rows]


@router.get("/repasse/calendario")
async def repasse_calendario(conn=Depends(get_conn)):
    """Calendário completo de parcelas de repasse."""
    rows = await conn.fetch("""
        SELECT *
        FROM repasse_calendario
        ORDER BY referencia_aplicativo
    """)
    return [dict(r) for r in rows]


@router.get("/historico")
async def historico_uploads(conn=Depends(get_conn)):
    """Lista os últimos 20 uploads de PO."""
    rows = await conn.fetch("""
        SELECT
            pu.id,
            pu.nome_arquivo,
            pu.tipo,
            pu.tem_enabler,
            pu.semana_ref,
            pu.total_linhas,
            pu.data_upload,
            COUNT(pl.id) FILTER (WHERE pl.status_reconciliacao = 'CONFORME')   AS conformes,
            COUNT(pl.id) FILTER (WHERE pl.status_reconciliacao = 'AUSENTE')     AS ausentes,
            COUNT(pl.id) FILTER (WHERE pl.status_reconciliacao = 'DIVERGENTE')  AS divergentes,
            COUNT(pl.id) FILTER (WHERE pl.status_reconciliacao = 'INESPERADO')  AS inesperados
        FROM po_uploads pu
        LEFT JOIN po_linhas pl ON pl.upload_id = pu.id
        WHERE pu.processado = TRUE
        GROUP BY pu.id
        ORDER BY pu.data_upload DESC
        LIMIT 20
    """)
    return [dict(r) for r in rows]


@router.get("/resumo/financeiro")
async def resumo_financeiro(conn=Depends(get_conn)):
    """Resumo financeiro: total recebido por tipo no mês atual."""
    rows = await conn.fetch("""
        SELECT
            pl.tipo,
            pl.tem_enabler,
            COUNT(*) FILTER (WHERE pl.status_reconciliacao = 'CONFORME') AS conformes,
            COALESCE(SUM(pl.valor_liquido) FILTER (WHERE pl.status_reconciliacao = 'CONFORME'), 0) AS total_recebido,
            COALESCE(SUM(pl.valor_esperado) FILTER (WHERE pl.status_reconciliacao = 'AUSENTE'), 0) AS total_ausente
        FROM po_linhas pl
        JOIN po_uploads pu ON pu.id = pl.upload_id
        WHERE pu.data_upload >= DATE_TRUNC('month', CURRENT_DATE)
        GROUP BY pl.tipo, pl.tem_enabler
        ORDER BY pl.tipo
    """)
    return [dict(r) for r in rows]