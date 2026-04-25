"""
HIPO — Router do BD Ativados
Endpoint para upload diário pelo ADM.
"""
import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from database import get_conn
from parsers.bd_ativados import parse_bd_ativados_arquivo
from routers.auth import usuario_atual

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/home/hipo/app/uploads")


@router.post("/upload")
async def upload_bd_ativados(
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    user=Depends(usuario_atual),
):
    """
    Recebe o BD Ativados (Excel da área restrita do franqueador).
    Substitui o snapshot anterior pela nova versão.
    """
    nome = arquivo.filename
    dest_dir = os.path.join(UPLOAD_DIR, "bd_ativados")
    os.makedirs(dest_dir, exist_ok=True)
    caminho = os.path.join(dest_dir, f"{uuid.uuid4()}_{nome}")
    with open(caminho, "wb") as f:
        shutil.copyfileobj(arquivo.file, f)

    resultado = parse_bd_ativados_arquivo(caminho)

    if resultado["erros"]:
        os.remove(caminho)
        raise HTTPException(422, {"erros": resultado["erros"]})

    if resultado["total"] == 0:
        os.remove(caminho)
        raise HTTPException(422, "Nenhuma linha válida encontrada no arquivo.")

    # Registra o upload
    upload_id = await conn.fetchval("""
        INSERT INTO bd_ativados_upload
            (usuario_id, nome_arquivo, total_registros, processado)
        VALUES ($1, $2, $3, FALSE)
        RETURNING id
    """, user["id"], nome, resultado["total"])

    # Limpa snapshot anterior — o BD Ativados é substituído inteiro a cada upload
    await conn.execute("DELETE FROM bd_ativados")

    # Insere as linhas novas
    for l in resultado["linhas"]:
        await conn.execute("""
            INSERT INTO bd_ativados (
                upload_id, referencia_aplicativo, razao_social, cnpj,
                situacao, saude_paciente, dia_faturamento, vencimento,
                tipo_faturamento, valor_mensalidade, integracao_contabil,
                ultimo_acesso, modulo_financeiro, modulo_nfe, modulo_estoque,
                modulo_vendas, modulo_servicos, modulo_compras,
                ativado_por_email, contador_cnpj, contador_nome,
                data_ativacao, data_cancelamento
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                $16,$17,$18,$19,$20,$21,$22,$23
            )
        """,
        upload_id,
        l.get("referencia_aplicativo"), l.get("razao_social"), l.get("cnpj"),
        l.get("situacao"), l.get("saude_paciente"),
        l.get("dia_faturamento"), l.get("vencimento"),
        l.get("tipo_faturamento"), l.get("valor_mensalidade"),
        l.get("integracao_contabil", False),
        l.get("ultimo_acesso"),
        l.get("modulo_financeiro", False), l.get("modulo_nfe", False),
        l.get("modulo_estoque", False), l.get("modulo_vendas", False),
        l.get("modulo_servicos", False), l.get("modulo_compras", False),
        l.get("ativado_por_email"),
        l.get("contador_cnpj"), l.get("contador_nome"),
        l.get("data_ativacao"), l.get("data_cancelamento"),
        )

    await conn.execute(
        "UPDATE bd_ativados_upload SET processado = TRUE WHERE id = $1",
        upload_id
    )

    # Estatísticas rápidas
    stats = await conn.fetchrow("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE LOWER(situacao) = 'active') AS ativos,
            COUNT(*) FILTER (WHERE LOWER(situacao) = 'archived') AS arquivados,
            COALESCE(SUM(valor_mensalidade) FILTER (WHERE LOWER(situacao) = 'active'), 0) AS mrr_total
        FROM bd_ativados
    """)

    return {
        "upload_id": str(upload_id),
        "total_registros": resultado["total"],
        "estatisticas": {
            "total": int(stats["total"]),
            "ativos": int(stats["ativos"]),
            "arquivados": int(stats["arquivados"]),
            "mrr_total": float(stats["mrr_total"]),
        },
        "message": f"BD Ativados atualizado com {resultado['total']} registros."
    }


@router.get("/historico")
async def historico_uploads(conn=Depends(get_conn), user=Depends(usuario_atual)):
    """Lista os últimos uploads do BD Ativados."""
    rows = await conn.fetch("""
        SELECT
            bu.id, bu.data_upload, bu.nome_arquivo,
            bu.total_registros, bu.processado,
            u.nome AS usuario_nome
        FROM bd_ativados_upload bu
        LEFT JOIN usuarios u ON u.id = bu.usuario_id
        ORDER BY bu.data_upload DESC
        LIMIT 20
    """)
    return [dict(r) for r in rows]


@router.get("/resumo")
async def resumo_atual(conn=Depends(get_conn), user=Depends(usuario_atual)):
    """Estatísticas do snapshot atual do BD Ativados."""
    stats = await conn.fetchrow("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE LOWER(situacao) = 'active') AS ativos,
            COUNT(*) FILTER (WHERE LOWER(situacao) = 'archived') AS arquivados,
            COUNT(*) FILTER (WHERE integracao_contabil = TRUE) AS com_integracao,
            COALESCE(SUM(valor_mensalidade) FILTER (WHERE LOWER(situacao) = 'active'), 0) AS mrr_total,
            COUNT(DISTINCT contador_cnpj) AS contadores_distintos
        FROM bd_ativados
    """)

    ultimo = await conn.fetchrow("""
        SELECT data_upload, nome_arquivo
        FROM bd_ativados_upload
        WHERE processado = TRUE
        ORDER BY data_upload DESC LIMIT 1
    """)

    return {
        "total": int(stats["total"]) if stats else 0,
        "ativos": int(stats["ativos"]) if stats else 0,
        "arquivados": int(stats["arquivados"]) if stats else 0,
        "com_integracao": int(stats["com_integracao"]) if stats else 0,
        "mrr_total": float(stats["mrr_total"]) if stats else 0,
        "contadores_distintos": int(stats["contadores_distintos"]) if stats else 0,
        "ultimo_upload": dict(ultimo) if ultimo else None,
    }
