"""
HIPO — Importação de transcrições do Meet exportadas em .docx.

Duas partes:
  * puras: leitura do documento, horário das falas, escolha da tarefa;
  * com banco: o script inteiro em dry-run e em --commit, cobrindo anexar à
    reunião existente, criar a reunião de uma tarefa solta, criar tarefa +
    reunião, não tocar em transcrição pronta e não chutar em dia vizinho.

Os .docx são montados no teste (zip com word/document.xml mínimo): nenhum
arquivo de cliente entra no repositório.
"""
import zipfile
from argparse import Namespace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from xml.sax.saxutils import escape

import pytest

from scripts import importar_transcricoes_docx as imp
from services import resumo_reuniao
from services.resumo_reuniao import Resumo
from services.tarefa import FUSO_OPERACAO

UTC = timezone.utc


def montar_docx(caminho, paragrafos):
    corpo = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(p)}</w:t></w:r></w:p>' for p in paragrafos
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{corpo}</w:body></w:document>"
    )
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("word/document.xml", xml)
    return caminho


def doc_meet(inicio="2026-09-28 13:56", participantes="Cliente Um, JAKELINE SANTANA",
             titulo=None, fim="00:17:43"):
    cab = [titulo] if titulo else [f"Reunião iniciada em {inicio} GMT-3"] if inicio else []
    return cab + [
        "Participantes", participantes, "Transcrição",
        "Cliente Um: Olá, boa tarde.",
        "JAKELINE SANTANA: Boa tarde! Tudo bem?",
        "00:05:00",
        "Cliente Um: Tudo. Somos 40 funcionários.",
        "JAKELINE SANTANA: Perfeito.",
        "JAKELINE SANTANA: Vou mandar a proposta.",
        f"A reunião terminou depois de {fim} 👋",
        "Esta transcrição editável foi gerada por computador e pode conter erros.",
    ]


# ── Puras ────────────────────────────────────────────────────────────


class TestLeitura:
    def test_cabecalho_participantes_e_falas(self, tmp_path):
        p = montar_docx(tmp_path / "ACME - OPP-2026-00320 - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        d = imp.interpretar(imp.paragrafos_docx(p), p.name)
        assert d.opp_numero == "OPP-2026-00320"
        assert d.inicio == datetime(2026, 9, 28, 13, 56, tzinfo=timezone(timedelta(hours=-3)))
        assert d.duracao == timedelta(minutes=17, seconds=43)
        assert d.participantes == ["Cliente Um", "JAKELINE SANTANA"]
        falas = [x for x in d.linhas if x.participante]
        assert len(falas) == 5
        assert falas[2].texto == "Tudo. Somos 40 funcionários."
        assert not d.divergencia_de_dia

    def test_titulo_do_evento_da_cnpj_e_nome_do_meet_da_horario(self, tmp_path):
        nome = "REART 74.390.246_0001-53 _ Apresentação - 2026_09_10 17_44 GMT-03_00 - Transcript.docx"
        p = montar_docx(tmp_path / nome, doc_meet(
            inicio=None, titulo="REART 74.390.246/0001-53 | Apresentação Controller MedSeg"))
        d = imp.interpretar(imp.paragrafos_docx(p), p.name)
        assert d.opp_numero is None
        assert d.cnpj == "74390246000153"
        assert d.inicio.astimezone(FUSO_OPERACAO).strftime("%d/%m %H:%M") == "10/09 17:44"

    def test_sem_horario_usa_o_dia_do_nome_sem_ano(self, tmp_path):
        p = montar_docx(tmp_path / "FQS OPP-2026-00381 - 10 DE SETEMBRO.docx",
                        doc_meet(inicio=None, titulo="FQS | Apresentação"))
        d = imp.interpretar(imp.paragrafos_docx(p), p.name)
        assert d.inicio is None
        assert d.dia == date(2026, 9, 10)

    def test_conteudo_ganha_do_nome_e_avisa(self, tmp_path):
        p = montar_docx(tmp_path / "VOXEL - OPP-2026-04494 - 19 DE SETEMBRO DE 2026.docx",
                        doc_meet(inicio="2026-09-18 10:12"))
        d = imp.interpretar(imp.paragrafos_docx(p), p.name)
        assert d.dia == date(2026, 9, 18)
        assert d.divergencia_de_dia

    def test_apresentacao_nao_vira_fala_do_anfitriao(self):
        pars = ["Reunião iniciada em 2026-09-02 10:55 GMT-3", "Participantes",
                "JAKELINE SANTANA, JAKELINE SANTANA's Presentation, Lucas", "Transcrição",
                "JAKELINE SANTANA's Presentation: slide", "Lucas: oi"]
        d = imp.interpretar(pars, "x.docx")
        assert [x.participante for x in d.linhas] == ["JAKELINE SANTANA's Presentation", "Lucas"]


class TestHorarios:
    def test_falas_ficam_entre_as_marcas_e_nao_passam_do_fim(self):
        d = imp.interpretar(doc_meet(), "a.docx")
        ts = imp.distribuir_horarios(d.linhas, d.duracao)
        inicios = [a for a, _, _ in ts]
        assert inicios == sorted(inicios)
        assert all(a < timedelta(minutes=5) for a, _, _ in ts[:2])
        assert all(timedelta(minutes=5) <= a for a, _, _ in ts[2:])
        assert ts[-1][1] == d.duracao

    def test_texto_no_formato_da_coleta(self):
        d = imp.interpretar(doc_meet(), "a.docx")
        falas = imp.falas_do_documento(d, d.inicio)
        from services.transcricao import texto_corrido
        texto = texto_corrido(falas)
        assert texto.splitlines()[0] == "[13:56] Cliente Um: Olá, boa tarde."
        # falas seguidas da mesma pessoa são juntadas, como na coleta
        assert "Perfeito. Vou mandar a proposta." in texto

    def test_duracao_limitada(self):
        d = imp.TranscricaoDocx(arquivo="x", duracao=timedelta(minutes=2))
        assert imp.duracao_min(d) == 5
        assert imp.duracao_min(imp.TranscricaoDocx(arquivo="x")) == 30


def cand(tid, prazo, reuniao=None, rt=None, **kw):
    return {"tarefa_id": tid, "prazo": prazo, "reuniao_id": reuniao, "rt_status": rt,
            "cancelada_em": None, **kw}


class TestEscolha:
    D = date(2026, 9, 10)
    INI = datetime(2026, 9, 10, 17, 44, tzinfo=FUSO_OPERACAO)

    def h(self, hora, dia=10):
        return datetime(2026, 9, dia, hora, 0, tzinfo=FUSO_OPERACAO)

    def test_mais_proxima_do_horario(self):
        p = imp.escolher([cand("a", self.h(10), "r1"), cand("b", self.h(17))],
                         self.D, self.INI, set())
        assert (p.acao, p.candidato["tarefa_id"]) == ("CRIAR_REUNIAO", "b")

    def test_sem_horario_e_duas_no_dia_pede_revisao(self):
        p = imp.escolher([cand("a", self.h(10)), cand("b", self.h(17))], self.D, None, set())
        assert p.acao == "REVISAR"

    def test_sem_horario_pega_a_que_sobrou(self):
        p = imp.escolher([cand("a", self.h(10)), cand("b", self.h(17))], self.D, None, {"b"})
        assert (p.acao, p.candidato["tarefa_id"]) == ("CRIAR_REUNIAO", "a")

    def test_pronta_nao_e_tocada(self):
        p = imp.escolher([cand("a", self.h(17), "r", "pronta")], self.D, self.INI, set())
        assert p.acao == "JA_TEM"

    def test_dia_vizinho_nao_e_chutado(self):
        p = imp.escolher([cand("a", self.h(10, dia=11), "r")], self.D, self.INI, set())
        assert p.acao == "REVISAR" and p.candidato["tarefa_id"] == "a"

    def test_nada_no_dia_cria(self):
        assert imp.escolher([], self.D, self.INI, set()).acao == "CRIAR_TUDO"
        assert imp.escolher([], self.D, None, set()).acao == "REVISAR"

    def test_mapa(self):
        m = imp.aplicar_mapa(["voxel=novo", "Manutenção=abc"])
        assert imp.alvo_do_mapa("VOXEL - OPP-1.docx", m) == "novo"
        assert imp.alvo_do_mapa("NN MANUTENCAO - OPP.docx", m) == "abc"
        assert imp.alvo_do_mapa("OUTRA.docx", m) is None


# ── Com banco ────────────────────────────────────────────────────────


@pytest.fixture
async def cena(db_conn, client, usuario_adm):
    h = usuario_adm["headers"]
    conta = (await client.post(
        "/crm/contas",
        json={"razao_social": "Metalurgica Alfa LTDA", "cnpj": "11.222.333/0001-81"},
        headers=h,
    )).json()
    opp = (await client.post("/crm/oportunidades", json={"conta_id": conta["id"]}, headers=h)).json()
    me = (await client.get("/auth/me", headers=h)).json()
    uid = UUID(me["id"])
    await db_conn.execute("UPDATE usuarios SET nome = 'JAKELINE SANTANA' WHERE id = $1", uid)
    await db_conn.execute(
        "INSERT INTO tipos_reuniao (sigla, nome, slug) VALUES ('AP', 'Apresentação', 'apresentacao') "
        "ON CONFLICT DO NOTHING")
    return {"conn": db_conn, "opp": opp, "uid": uid, "email": me["email"]}


async def tarefa(conn, opp_id, uid, prazo, concluida=False, com_reuniao=False):
    tid = await conn.fetchval(
        """INSERT INTO tarefas (oportunidade_id, tipo, titulo, responsavel_id, prazo,
               concluida_em, criado_por, criado_em)
           VALUES ($1, 'reuniao', 'Reunião', $2, $3, $4, $2, $5)
           RETURNING id""",
        UUID(opp_id), uid, prazo, prazo + timedelta(minutes=30) if concluida else None,
        prazo - timedelta(days=2),
    )
    rid = None
    if com_reuniao:
        rid = await conn.fetchval(
            "INSERT INTO reunioes (tarefa_id, criado_por, agendado_por) VALUES ($1, $2, $2) RETURNING id",
            tid, uid)
    return tid, rid


def args(pasta, commit=False, **kw):
    base = dict(pasta=str(pasta), responsavel="JAKELINE", por="adm@teste.com", tipo="AP",
                mapa=[], sobrescrever=False, sem_resumo=False, csv=None, commit=commit)
    base.update(kw)
    return Namespace(**base)


@pytest.fixture
def ia_de_mentira(monkeypatch):
    chamadas = []

    async def resumir(texto, ctx):
        chamadas.append(texto)
        return Resumo(resumo="Cliente com 40 funcionários.", proximos_passos=("Enviar proposta",), modelo="m")

    monkeypatch.setattr(resumo_reuniao, "configurado", lambda: True)
    monkeypatch.setattr(resumo_reuniao, "resumir", resumir)
    return chamadas


INI = datetime(2026, 9, 28, 13, 56, tzinfo=FUSO_OPERACAO)


class TestScript:
    async def test_dry_run_nao_grava(self, cena, tmp_path, ia_de_mentira):
        n = cena["opp"]["numero"]
        montar_docx(tmp_path / f"ACME - {n} - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        assert await imp.executar(args(tmp_path)) == 0
        c = cena["conn"]
        assert await c.fetchval("SELECT count(*) FROM tarefas") == 0
        assert await c.fetchval("SELECT count(*) FROM reuniao_transcricoes") == 0
        assert ia_de_mentira == []

    async def test_anexa_a_reuniao_da_agenda(self, cena, tmp_path, ia_de_mentira):
        c = cena["conn"]
        tid, rid = await tarefa(c, cena["opp"]["id"], cena["uid"], INI, com_reuniao=True)
        n = cena["opp"]["numero"]
        montar_docx(tmp_path / f"ACME - {n} - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        assert await imp.executar(args(tmp_path, commit=True)) == 0
        rt = await c.fetchrow("SELECT * FROM reuniao_transcricoes WHERE reuniao_id = $1", rid)
        assert rt["status"] == "pronta"
        assert rt["texto"].startswith("[13:56] Cliente Um:")
        assert rt["resumo"] == "Cliente com 40 funcionários."
        assert rt["conferencias"][0].startswith("importado-docx:")
        assert await c.fetchval("SELECT count(*) FROM tarefas") == 1

    async def test_tarefa_concluida_sem_agenda_ganha_reuniao_realizada(self, cena, tmp_path, ia_de_mentira):
        c = cena["conn"]
        tid, _ = await tarefa(c, cena["opp"]["id"], cena["uid"], INI, concluida=True)
        n = cena["opp"]["numero"]
        montar_docx(tmp_path / f"ACME - {n} - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        assert await imp.executar(args(tmp_path, commit=True)) == 0
        r = await c.fetchrow("SELECT * FROM reunioes WHERE tarefa_id = $1", tid)
        assert r["desfecho"] == "realizada"
        assert r["duracao_min"] == 18
        # retroativo: o dia do agendamento, não hoje
        assert r["criado_em"] == INI - timedelta(days=2)
        assert r["agendado_por"] == cena["uid"]
        assert await c.fetchval(
            "SELECT status FROM reuniao_transcricoes WHERE reuniao_id = $1", r["id"]) == "pronta"

    async def test_sem_tarefa_cria_tarefa_concluida_e_reuniao(self, cena, tmp_path, ia_de_mentira):
        c = cena["conn"]
        n = cena["opp"]["numero"]
        montar_docx(tmp_path / f"ACME - {n} - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        assert await imp.executar(args(tmp_path, commit=True)) == 0
        t = await c.fetchrow("SELECT * FROM tarefas")
        assert t["tipo"] == "reuniao" and t["responsavel_id"] == cena["uid"]
        assert t["prazo"] == INI and t["concluida_em"] == INI + timedelta(minutes=18)
        assert t["criado_em"] == INI
        assert t["titulo"].startswith("AP - ")
        r = await c.fetchrow("SELECT * FROM reunioes WHERE tarefa_id = $1", t["id"])
        assert r["desfecho"] == "realizada" and r["agendado_por"] is None
        assert r["tipo_id"] is not None

    async def test_rodar_de_novo_nao_duplica(self, cena, tmp_path, ia_de_mentira):
        c = cena["conn"]
        n = cena["opp"]["numero"]
        montar_docx(tmp_path / f"ACME - {n} - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        await imp.executar(args(tmp_path, commit=True))
        await imp.executar(args(tmp_path, commit=True))
        assert await c.fetchval("SELECT count(*) FROM tarefas") == 1
        assert await c.fetchval("SELECT count(*) FROM reuniao_transcricoes") == 1
        assert len(ia_de_mentira) == 1

    async def test_dia_vizinho_nao_cria_nada(self, cena, tmp_path, ia_de_mentira):
        c = cena["conn"]
        await tarefa(c, cena["opp"]["id"], cena["uid"], INI + timedelta(days=1), com_reuniao=True)
        n = cena["opp"]["numero"]
        montar_docx(tmp_path / f"ACME - {n} - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        await imp.executar(args(tmp_path, commit=True))
        assert await c.fetchval("SELECT count(*) FROM tarefas") == 1
        assert await c.fetchval("SELECT count(*) FROM reuniao_transcricoes") == 0

    async def test_mapa_resolve_o_dia_vizinho(self, cena, tmp_path, ia_de_mentira):
        c = cena["conn"]
        tid, rid = await tarefa(c, cena["opp"]["id"], cena["uid"], INI + timedelta(days=1), com_reuniao=True)
        n = cena["opp"]["numero"]
        montar_docx(tmp_path / f"ACME - {n} - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        await imp.executar(args(tmp_path, commit=True, mapa=[f"ACME={tid}"]))
        assert await c.fetchval(
            "SELECT status FROM reuniao_transcricoes WHERE reuniao_id = $1", rid) == "pronta"

    async def test_commit_exige_quem_lanca(self, cena, tmp_path):
        montar_docx(tmp_path / "A - OPP-2026-00001 - 28 DE SETEMBRO.docx", doc_meet())
        with pytest.raises(SystemExit):
            await imp.executar(args(tmp_path, commit=True, por=None))


class TestEmpresaPeloNome:
    def test_extrai_a_razao_social_do_nome(self):
        assert imp.empresa_do_nome("INSTITUTO EDUCACIONAL PAPIRO LTDA - 01 DE SETEMBRO DE 2026.docx") \
            == "INSTITUTO EDUCACIONAL PAPIRO LTDA"
        assert imp.empresa_do_nome("SEMHIFEN.docx") is None
        assert imp.empresa_do_nome("OPP-2026-00001 - 01 DE SETEMBRO.docx") is None

    def test_chave_ignora_acento_caixa_e_pontuacao(self):
        assert imp.chave_empresa("Encontrar Núcleo Terapêutico Ltda.") == \
            imp.chave_empresa("ENCONTRAR NUCLEO TERAPEUTICO LTDA")

    async def test_arquivo_sem_opp_acha_pela_razao_social(self, cena, tmp_path, ia_de_mentira):
        c = cena["conn"]
        montar_docx(tmp_path / "Metalúrgica Alfa Ltda. - 28 DE SETEMBRO DE 2026.docx", doc_meet())
        assert await imp.executar(args(tmp_path, commit=True)) == 0
        t = await c.fetchrow("SELECT * FROM tarefas")
        assert t["oportunidade_id"] == UUID(cena["opp"]["id"])

    async def test_documento_que_nao_e_transcricao_fica_de_fora(self, cena, tmp_path, ia_de_mentira):
        c = cena["conn"]
        n = cena["opp"]["numero"]
        montar_docx(tmp_path / f"ACME - {n} - 25 DE SETEMBRO DE 2026.docx",
                    ["set. 25, 2026", "Resumo", "Reunião estratégica.", "Próximas etapas"])
        assert await imp.executar(args(tmp_path, commit=True)) == 0
        assert await c.fetchval("SELECT count(*) FROM tarefas") == 0
