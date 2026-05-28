"""
HIPO — Testes de endpoint do estado de ATENÇÃO (tarefa para hoje, v1.3.2).

Insere oportunidades com ult_prox_tarefa = CURRENT_DATE e verifica que
os endpoints de conformidade (Agendamento e Vendas) devolvem o estado
'atencao' e o campo atencao_hoje no resumo.

Usa CURRENT_DATE do Postgres no INSERT para casar com a data do servidor
(o serviço usa date.today() do mesmo servidor — sem o parâmetro 'hoje',
o default é hoje).
"""
import bcrypt


_SENHA_TESTE = "test123"


async def _criar_usuario(db_conn, client, email, cargo):
    pwd_hash = bcrypt.hashpw(_SENHA_TESTE.encode(), bcrypt.gensalt()).decode()
    await db_conn.execute(
        """
        INSERT INTO usuarios (nome, email, senha_hash, cargo, ativo)
        VALUES ($1, $2, $3, $4, TRUE)
        """,
        f"User {cargo}", email, pwd_hash, cargo,
    )
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _SENHA_TESTE},
    )
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed_upload(db_conn) -> str:
    row = await db_conn.fetchrow(
        """
        INSERT INTO cliente_upload
            (tipo, nome_arquivo, total_linhas, total_validos, processado)
        VALUES ('OPORTUNIDADES', 'seed.xlsx', 1, 1, TRUE)
        RETURNING id
        """
    )
    return str(row["id"])


async def _seed_op_data(db_conn, upload_id, op_id, fase, *, tf=0,
                        offset_dias=None, temp=None, prev="Não", ticket="Não"):
    """
    Insere uma OP. offset_dias controla ult_prox_tarefa relativo a hoje:
      None -> NULL ; 0 -> hoje ; -1 -> ontem ; 1 -> amanhã.
    """
    if offset_dias is None:
        upt_sql = "NULL"
    else:
        upt_sql = f"CURRENT_DATE + {int(offset_dias)}"
    await db_conn.execute(
        f"""
        INSERT INTO cliente_oportunidade (
            upload_id, op_id, cnpj, razao_social, fase, status,
            temperatura, tarefa_futura, ult_prox_tarefa,
            previsao_preenchido, ticket_preenchido,
            sdr_fr, executivo_vendas
        ) VALUES ($1,$2,$3,$4,$5,'ativo',$6,$7,{upt_sql},$8,$9,'SDR X','Exec X')
        """,
        upload_id, op_id, f"{op_id:014d}", f"Empresa {op_id}", fase,
        temp, tf, prev, ticket,
    )


class TestEstadoAtencaoAgendamento:
    async def test_tarefa_hoje_vira_atencao(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op_data(db_conn, up, 1, "01. Suspect", tf=0, offset_dias=0)   # hoje
        await _seed_op_data(db_conn, up, 2, "01. Suspect", tf=1)                  # conforme
        await _seed_op_data(db_conn, up, 3, "01. Suspect", tf=0, offset_dias=-1)  # vencida

        resp = await client.get("/agendamento/conformidade", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["resumo"]["atencao_hoje"] == 1
        assert data["resumo"]["conformes"] == 1
        assert data["resumo"]["nao_conformes"] == 1
        # total_analisadas exclui a de atenção.
        assert data["resumo"]["total_analisadas"] == 2

        por_op = {it["op_id"]: it["classificacao"] for it in data["itens"]}
        assert por_op[1]["estado"] == "atencao"
        assert por_op[1]["tarefa_hoje"] is True
        assert por_op[2]["estado"] == "conforme"
        assert por_op[3]["estado"] == "problema"

    async def test_so_problema_nao_inclui_atencao(self, db_conn, client):
        headers = await _criar_usuario(db_conn, client, "sdr@teste.com", "SDR")
        up = await _seed_upload(db_conn)
        await _seed_op_data(db_conn, up, 1, "01. Suspect", tf=0, offset_dias=0)   # atenção
        await _seed_op_data(db_conn, up, 2, "01. Suspect", tf=0, offset_dias=-1)  # problema

        resp = await client.get(
            "/agendamento/conformidade?so_problema=true", headers=headers
        )
        data = resp.json()
        ids = [it["op_id"] for it in data["itens"]]
        assert ids == [2]  # só a problema; a atenção (1) fica fora


class TestEstadoAtencaoVendas:
    async def test_tarefa_hoje_vira_atencao_em_vendas(self, db_conn, client):
        # Vendas usa o módulo 'clientes' — ADM tem acesso.
        headers = await _criar_usuario(db_conn, client, "adm@teste.com", "ADM")
        up = await _seed_upload(db_conn)
        await _seed_op_data(db_conn, up, 1, "01. Suspect", tf=0, offset_dias=0)

        resp = await client.get("/vendas/funil-cromie", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["resumo"]["atencao_hoje"] == 1
        assert data["itens"][0]["classificacao"]["estado"] == "atencao"
