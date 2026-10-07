"""
HIPO — Script que cria a confirmação da véspera das reuniões marcadas
antes da entrega 048 (scripts/criar_confirmacoes_vespera.py).

A reunião "antiga" é simulada marcando pela API e apagando a confirmação
que a 048 criou — é o estado das reuniões marcadas antes do deploy.
"""
from datetime import timedelta

from scripts.criar_confirmacoes_vespera import criar
from tests.test_crm_agenda import (  # noqa: F401  (cenario é fixture)
    as_horas, cenario, nova_reuniao, proxima_segunda,
)


async def antiga(client, db_conn, cenario, dias=1, hora=9):
    r = await nova_reuniao(
        client, cenario["headers"], cenario["oportunidade"]["id"],
        cenario["usuario_id"],
        inicio=as_horas(proxima_segunda(2) + timedelta(days=dias), hora),
    )
    await db_conn.execute("DELETE FROM tarefas WHERE confirmacao_de = $1", r["tarefa_id"])
    return r


async def n_conf(db_conn, tarefa_id):
    return await db_conn.fetchval(
        "SELECT count(*) FROM tarefas WHERE confirmacao_de = $1", tarefa_id
    )


async def rodar(db_conn):
    async with db_conn.transaction():
        return await criar(db_conn)


async def test_cria_para_reuniao_futura_sem_confirmacao(cenario, client, db_conn):
    r = await antiga(client, db_conn, cenario)
    linhas = await rodar(db_conn)
    assert len(linhas) == 1 and linhas[0]["prazo"] is not None
    assert await n_conf(db_conn, r["tarefa_id"]) == 1


async def test_rodar_de_novo_nao_duplica(cenario, client, db_conn):
    r = await antiga(client, db_conn, cenario)
    await rodar(db_conn)
    assert await rodar(db_conn) == []
    assert await n_conf(db_conn, r["tarefa_id"]) == 1


async def test_reuniao_que_ja_tem_confirmacao_e_pulada(cenario, client, db_conn):
    nova = await nova_reuniao(
        client, cenario["headers"], cenario["oportunidade"]["id"],
        cenario["usuario_id"], inicio=as_horas(proxima_segunda(2), 15),
    )
    assert await rodar(db_conn) == []
    assert await n_conf(db_conn, nova["tarefa_id"]) == 1


async def test_reuniao_fechada_nao_ganha(cenario, client, db_conn):
    r = await antiga(client, db_conn, cenario)
    await client.post(
        f"/crm/agenda/reunioes/{r['id']}/desfecho",
        json={"desfecho": "cancelada"}, headers=cenario["headers"],
    )
    assert await rodar(db_conn) == []
    assert await n_conf(db_conn, r["tarefa_id"]) == 0


async def test_rollback_nao_grava(cenario, client, db_conn):
    r = await antiga(client, db_conn, cenario)
    tx = db_conn.transaction()
    await tx.start()
    assert len(await criar(db_conn)) == 1
    await tx.rollback()
    assert await n_conf(db_conn, r["tarefa_id"]) == 0


async def test_vespera_hoje_cria_para_hoje(cenario, client, db_conn, monkeypatch):
    """
    Reunião de amanhã marcada antes da 048: a confirmação ainda cabe hoje.
    O relógio é fixado na segunda; a reunião é na terça.
    """
    from datetime import datetime, timezone as tz

    import scripts.criar_confirmacoes_vespera as mod
    from services.agenda import FUSO_OPERACAO as SP

    segunda = proxima_segunda(2)
    agora = datetime(segunda.year, segunda.month, segunda.day, 11, tzinfo=SP)

    class Relogio(datetime):
        @classmethod
        def now(cls, tzinfo=None):
            return agora.astimezone(tzinfo or tz.utc)

    monkeypatch.setattr(mod, "datetime", Relogio, raising=False)
    await antiga(client, db_conn, cenario, dias=1)
    linhas = await rodar(db_conn)
    assert linhas[0]["prazo"].astimezone(SP).date() == segunda


async def test_reuniao_de_hoje_fica_de_fora(cenario, client, db_conn, monkeypatch):
    from datetime import datetime, timezone as tz

    import scripts.criar_confirmacoes_vespera as mod
    from services.agenda import FUSO_OPERACAO as SP

    terca = proxima_segunda(2) + timedelta(days=1)
    agora = datetime(terca.year, terca.month, terca.day, 7, tzinfo=SP)

    class Relogio(datetime):
        @classmethod
        def now(cls, tzinfo=None):
            return agora.astimezone(tzinfo or tz.utc)

    monkeypatch.setattr(mod, "datetime", Relogio, raising=False)
    r = await antiga(client, db_conn, cenario, dias=1, hora=15)
    linhas = await rodar(db_conn)
    assert linhas[0]["prazo"] is None
    assert await n_conf(db_conn, r["tarefa_id"]) == 0
