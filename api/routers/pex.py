"""
HIPO — Router de PEX
Endpoints: upload CROmie, cálculo de indicadores, compliance, painel.
"""
import os
import uuid
import shutil
from datetime import date
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from database import get_conn
from routers.auth import usuario_atual
from parsers.cromie_parser import parse_cromie_arquivo
from services.pex_calc import calcular_pex_snapshot, calcular_gaps_compliance

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/home/hipo/app/uploads")


# ── UPLOAD CROmie ─────────────────────────────────────────────────────────────

@router.post("/cromie/upload")
async def upload_cromie(
    arquivo: UploadFile = File(...),
    conn=Depends(get_conn),
    _user=Depends(usuario_atual),
):
    """
    Recebe o Excel do CROmie, processa as 4 abas,
    audita o schema e calcula os indicadores PEX.
    """
    nome = arquivo.filename
    dest_dir = os.path.join(UPLOAD_DIR, "cromie")
    os.makedirs(dest_dir, exist_ok=True)
    caminho = os.path.join(dest_dir, f"{uuid.uuid4()}_{nome}")
    with open(caminho, "wb") as f:
        shutil.copyfileobj(arquivo.file, f)

    resultado = parse_cromie_arquivo(caminho)

    if resultado["erros"] and not resultado["abas"]:
        os.remove(caminho)
        raise HTTPException(422, {"erros": resultado["erros"]})

    # Consolida auditoria de schema
    schema_alterado = resultado["schema_alterado"]
    colunas_novas = []
    colunas_removidas = []
    colunas_por_aba = {}
    totais_por_aba = {}

    for aba_key, aba_data in resultado["abas"].items():
        audit = aba_data["auditoria"]
        colunas_por_aba[f"colunas_{aba_key}"] = audit["colunas_reais"]
        totais_por_aba[f"total_{aba_key}"] = aba_data["total"]
        if audit["novas"]:
            colunas_novas.extend([f"{aba_key}:{c}" for c in audit["novas"]])
        if audit["removidas"]:
            colunas_removidas.extend([f"{aba_key}:{c}" for c in audit["removidas"]])

    # Registra o upload
    upload_id = await conn.fetchval(
        """
        INSERT INTO cromie_uploads (
            nome_arquivo, status, schema_alterado,
            colunas_novas, colunas_removidas,
            colunas_cliente_final, colunas_tarefa_cliente,
            colunas_contador, colunas_tarefa_contador,
            total_cliente_final, total_tarefa_cliente,
            total_contador, total_tarefa_contador
        ) VALUES (
            $1, 'PROCESSADO', $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        RETURNING id
        """,
        nome,
        schema_alterado,
        colunas_novas or None,
        colunas_removidas or None,
        colunas_por_aba.get("colunas_cliente_final"),
        colunas_por_aba.get("colunas_tarefa_cliente"),
        colunas_por_aba.get("colunas_contador"),
        colunas_por_aba.get("colunas_tarefa_contador"),
        totais_por_aba.get("total_cliente_final", 0),
        totais_por_aba.get("total_tarefa_cliente", 0),
        totais_por_aba.get("total_contador", 0),
        totais_por_aba.get("total_tarefa_contador", 0),
    )

    upload_id_str = str(upload_id)

    # Insere dados de cada aba
    await _inserir_cliente_final(conn, upload_id_str,
        resultado["abas"].get("cliente_final", {}).get("linhas", []))
    await _inserir_tarefa_cliente(conn, upload_id_str,
        resultado["abas"].get("tarefa_cliente", {}).get("linhas", []))
    await _inserir_contador(conn, upload_id_str,
        resultado["abas"].get("contador", {}).get("linhas", []))
    await _inserir_tarefa_contador(conn, upload_id_str,
        resultado["abas"].get("tarefa_contador", {}).get("linhas", []))

    # Calcula indicadores PEX
    mes_ref = date.today().strftime("%Y-%m")
    metas = await conn.fetchrow(
        "SELECT * FROM pex_metas_mensais WHERE mes_ref = $1", mes_ref
    )
    dias_uteis   = int(metas["dias_uteis"])   if metas else 22
    ecs_ativos   = int(metas["ecs_ativos_m3"]) if metas else 2
    evs_ativos   = int(metas["evs_ativos"])   if metas else 1
    carteira     = int(metas["carteira_total_contadores"]) if metas else 1

    snapshot = await calcular_pex_snapshot(
        conn, upload_id_str, mes_ref,
        dias_uteis, ecs_ativos, evs_ativos, carteira
    )
    snapshot["mes_ref"] = mes_ref
    snapshot["data_ref"] = date.today()
    snapshot["upload_cromie_id"] = upload_id_str

    # Upsert snapshot
    await conn.execute(
        """
        INSERT INTO pex_snapshot (
            data_ref, mes_ref, upload_cromie_id,
            nmrr_realizado, nmrr_meta, nmrr_pct, nmrr_pts,
            reunioes_ec_du_realizado, reunioes_ec_du_pts,
            contadores_trabalhados_pct, contadores_trabalhados_pts,
            contadores_indicando_pct, contadores_indicando_pts,
            contadores_ativando_pct, contadores_ativando_pts,
            conversao_total_pct, conversao_total_pts,
            conversao_m0_pct, conversao_m0_pts,
            conversao_inbound_pct, conversao_inbound_pts,
            demo_du_realizado, demo_du_pts,
            demos_outbound_pct, demos_outbound_pts,
            sow_pct, sow_pts,
            mapeamento_carteira_pct, mapeamento_carteira_pts,
            reuniao_contador_inbound_pct, reuniao_contador_inbound_pts,
            integracao_contabil_pct, integracao_contabil_pts,
            early_churn_pct, early_churn_pts,
            crescimento_40_pct, crescimento_40_pts,
            utilizacao_desconto_pct, utilizacao_desconto_pts,
            total_resultado_pts, total_gestao_pts,
            total_engajamento_pts, total_geral_pts,
            risco_classificacao
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,
            $20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36,
            $37,$38,$39,$40,$41,$42,$43,$44
        )
        ON CONFLICT (data_ref) DO UPDATE SET
            upload_cromie_id = EXCLUDED.upload_cromie_id,
            nmrr_realizado = EXCLUDED.nmrr_realizado,
            nmrr_pts = EXCLUDED.nmrr_pts,
            total_geral_pts = EXCLUDED.total_geral_pts,
            risco_classificacao = EXCLUDED.risco_classificacao
        RETURNING id
        """,
        snapshot["data_ref"], snapshot["mes_ref"], snapshot["upload_cromie_id"],
        snapshot.get("nmrr_realizado"), snapshot.get("nmrr_meta"),
        snapshot.get("nmrr_pct"), snapshot.get("nmrr_pts"),
        snapshot.get("reunioes_ec_du_realizado"), snapshot.get("reunioes_ec_du_pts"),
        snapshot.get("contadores_trabalhados_pct"), snapshot.get("contadores_trabalhados_pts"),
        snapshot.get("contadores_indicando_pct"), snapshot.get("contadores_indicando_pts"),
        snapshot.get("contadores_ativando_pct"), snapshot.get("contadores_ativando_pts"),
        snapshot.get("conversao_total_pct"), snapshot.get("conversao_total_pts"),
        snapshot.get("conversao_m0_pct"), snapshot.get("conversao_m0_pts"),
        snapshot.get("conversao_inbound_pct"), snapshot.get("conversao_inbound_pts"),
        snapshot.get("demo_du_realizado"), snapshot.get("demo_du_pts"),
        snapshot.get("demos_outbound_pct"), snapshot.get("demos_outbound_pts"),
        snapshot.get("sow_pct"), snapshot.get("sow_pts"),
        snapshot.get("mapeamento_carteira_pct"), snapshot.get("mapeamento_carteira_pts"),
        snapshot.get("reuniao_contador_inbound_pct"), snapshot.get("reuniao_contador_inbound_pts"),
        snapshot.get("integracao_contabil_pct"), snapshot.get("integracao_contabil_pts"),
        snapshot.get("early_churn_pct", 0), snapshot.get("early_churn_pts", 0),
        snapshot.get("crescimento_40_pct", 0), snapshot.get("crescimento_40_pts", 0),
        snapshot.get("utilizacao_desconto_pct", 0), snapshot.get("utilizacao_desconto_pts", 0),
        snapshot.get("total_resultado_pts"), snapshot.get("total_gestao_pts"),
        snapshot.get("total_engajamento_pts"), snapshot.get("total_geral_pts"),
        snapshot.get("risco_classificacao"),
    )

    # Gaps de compliance por usuário
    gaps = await calcular_gaps_compliance(conn, upload_id_str)
    for gap in gaps:
        await conn.execute(
            """
            INSERT INTO pex_compliance_gaps (
                data_ref, usuario_responsavel,
                leads_sem_tarefa_futura, leads_sem_temperatura,
                leads_sem_previsao, leads_sem_ticket,
                contadores_sem_tarefa_mes, inbound_sem_reuniao_5du,
                pontos_em_risco
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            """,
            date.today(),
            gap["usuario_responsavel"],
            gap["leads_sem_tarefa_futura"],
            gap["leads_sem_temperatura"],
            gap["leads_sem_previsao"],
            gap["leads_sem_ticket"],
            gap["contadores_sem_tarefa_mes"],
            gap["inbound_sem_reuniao_5du"],
            gap["pontos_em_risco"],
        )

    return {
        "upload_id": upload_id_str,
        "schema_alterado": schema_alterado,
        "colunas_novas": colunas_novas,
        "colunas_removidas": colunas_removidas,
        "totais": totais_por_aba,
        "pex": {
            "total_geral_pts": snapshot.get("total_geral_pts"),
            "risco": snapshot.get("risco_classificacao"),
            "resultado_pts": snapshot.get("total_resultado_pts"),
        },
        "erros": resultado["erros"],
        "message": "CROmie processado e PEX calculado com sucesso."
    }


# ── HELPERS DE INSERÇÃO ───────────────────────────────────────────────────────

async def _inserir_cliente_final(conn, upload_id, linhas):
    for l in linhas:
        if not l.get("empresa") and not l.get("op_id"):
            continue
        await conn.execute("""
            INSERT INTO cromie_cliente_final (
                upload_id, op_id, empresa, cnpj, responsavel, fase, temperatura,
                origem, tarefa_futura, temperatura_preenchida, previsao_preenchida,
                ticket_preenchido, demo_realizada, ticket, previsao_fechamento,
                usuario_responsavel, contador_cnpj, contador_nome,
                data_criacao, data_ganho, data_perda, motivo_perda
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
        """,
        upload_id, l.get("op_id"), l.get("empresa"), l.get("cnpj"),
        l.get("responsavel"), l.get("fase"), l.get("temperatura"),
        l.get("origem"), l.get("tarefa_futura", False),
        l.get("temperatura_preenchida", False), l.get("previsao_preenchida", False),
        l.get("ticket_preenchido", False), l.get("demo_realizada", False),
        l.get("ticket"), l.get("previsao_fechamento"),
        l.get("usuario_responsavel"), l.get("contador_cnpj"), l.get("contador_nome"),
        l.get("data_criacao"), l.get("data_ganho"), l.get("data_perda"), l.get("motivo_perda"),
        )

async def _inserir_tarefa_cliente(conn, upload_id, linhas):
    for l in linhas:
        if not l.get("empresa") and not l.get("op_id"):
            continue
        await conn.execute("""
            INSERT INTO cromie_tarefa_cliente (
                upload_id, op_id, empresa, tipo_tarefa, finalidade,
                resultado, canal, usuario_responsavel, data_tarefa
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
        upload_id, l.get("op_id"), l.get("empresa"), l.get("tipo_tarefa"),
        l.get("finalidade"), l.get("resultado"), l.get("canal"),
        l.get("usuario_responsavel"), l.get("data_tarefa"),
        )

async def _inserir_contador(conn, upload_id, linhas):
    for l in linhas:
        if not l.get("razao_social") and not l.get("cnpj"):
            continue
        await conn.execute("""
            INSERT INTO cromie_contador (
                upload_id, cnpj, razao_social, responsavel, status_parceria,
                temperatura, dias_parado, possui_tarefa, status_tarefa,
                sow_preenchido, usuario_responsavel
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        upload_id, l.get("cnpj"), l.get("razao_social"), l.get("responsavel"),
        l.get("status_parceria"), l.get("temperatura"), l.get("dias_parado", 0),
        l.get("possui_tarefa", False), l.get("status_tarefa"),
        l.get("sow_preenchido", False), l.get("usuario_responsavel"),
        )

async def _inserir_tarefa_contador(conn, upload_id, linhas):
    for l in linhas:
        if not l.get("contador_nome") and not l.get("contador_cnpj"):
            continue
        await conn.execute("""
            INSERT INTO cromie_tarefa_contador (
                upload_id, contador_cnpj, contador_nome, tipo_tarefa,
                finalidade, resultado, canal, usuario_responsavel, data_tarefa
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
        upload_id, l.get("contador_cnpj"), l.get("contador_nome"),
        l.get("tipo_tarefa"), l.get("finalidade"), l.get("resultado"),
        l.get("canal"), l.get("usuario_responsavel"), l.get("data_tarefa"),
        )


# ── ENDPOINTS DE CONSULTA ─────────────────────────────────────────────────────

@router.get("/painel")
async def painel_pex(conn=Depends(get_conn)):
    """Painel completo do PEX do mês atual."""
    row = await conn.fetchrow("""
        SELECT * FROM pex_snapshot
        WHERE mes_ref = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
        ORDER BY data_ref DESC LIMIT 1
    """)
    if not row:
        raise HTTPException(404, "Nenhum snapshot encontrado para o mês atual.")
    return dict(row)


@router.get("/compliance")
async def compliance_usuarios(conn=Depends(get_conn)):
    """Gaps de compliance por usuário — hoje."""
    rows = await conn.fetch("""
        SELECT * FROM vw_compliance_usuarios
    """)
    return [dict(r) for r in rows]


@router.get("/indicadores")
async def listar_indicadores(conn=Depends(get_conn)):
    """Lista todos os 30 indicadores com configuração."""
    rows = await conn.fetch("""
        SELECT * FROM pex_indicadores_config
        ORDER BY pilar, pontos_max DESC
    """)
    return [dict(r) for r in rows]


@router.get("/historico")
async def historico_pex(
    meses: int = Query(default=6, ge=1, le=24),
    conn=Depends(get_conn)
):
    """Histórico de pontuação PEX dos últimos N meses."""
    rows = await conn.fetch("""
        SELECT
            mes_ref,
            MAX(total_geral_pts) AS pontuacao,
            MAX(total_resultado_pts) AS resultado_pts,
            MAX(total_gestao_pts) AS gestao_pts,
            MAX(total_engajamento_pts) AS engajamento_pts,
            MAX(risco_classificacao::text) AS risco
        FROM pex_snapshot
        WHERE data_ref >= CURRENT_DATE - INTERVAL '1 month' * $1
        GROUP BY mes_ref
        ORDER BY mes_ref DESC
    """, meses)
    return [dict(r) for r in rows]


@router.post("/metas")
async def configurar_metas(dados: dict, conn=Depends(get_conn)):
    """
    Configura as metas mensais para cálculo do PEX.
    Campos: mes_ref, nmrr_meta, demos_outbound_meta, dias_uteis,
            ecs_ativos_m3, evs_ativos, carteira_total_contadores
    """
    await conn.execute("""
        INSERT INTO pex_metas_mensais (
            mes_ref, nmrr_meta, demos_outbound_meta,
            dias_uteis, ecs_ativos_m3, evs_ativos,
            carteira_total_contadores
        ) VALUES ($1,$2,$3,$4,$5,$6,$7)
        ON CONFLICT (mes_ref) DO UPDATE SET
            nmrr_meta = EXCLUDED.nmrr_meta,
            demos_outbound_meta = EXCLUDED.demos_outbound_meta,
            dias_uteis = EXCLUDED.dias_uteis,
            ecs_ativos_m3 = EXCLUDED.ecs_ativos_m3,
            evs_ativos = EXCLUDED.evs_ativos,
            carteira_total_contadores = EXCLUDED.carteira_total_contadores
    """,
    dados.get("mes_ref"),
    dados.get("nmrr_meta"),
    dados.get("demos_outbound_meta"),
    dados.get("dias_uteis", 22),
    dados.get("ecs_ativos_m3", 2),
    dados.get("evs_ativos", 1),
    dados.get("carteira_total_contadores", 1),
    )
    return {"message": "Metas configuradas com sucesso."}


@router.get("/cromie/auditoria")
async def auditoria_schema(conn=Depends(get_conn)):
    """Histórico de mudanças de schema do CROmie."""
    rows = await conn.fetch("""
        SELECT
            id, data_upload, nome_arquivo,
            schema_alterado, colunas_novas, colunas_removidas,
            total_cliente_final, total_tarefa_cliente,
            total_contador, total_tarefa_contador
        FROM cromie_uploads
        ORDER BY data_upload DESC
        LIMIT 30
    """)
    return [dict(r) for r in rows]