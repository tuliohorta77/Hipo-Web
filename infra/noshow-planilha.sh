#!/usr/bin/env bash
# Marca como NO-SHOW no HIPO as reunioes com "NAO" na coluna E (REUNIAO) da
# planilha CONTROLE DE VENDAS 1.xlsx, aba AGENDAMENTOS.
#
# Casamento: CNPJ da empresa (oportunidade -> conta, ou conta do parceiro)
# + DIA da reuniao (tarefas.prazo no fuso de Sao Paulo). Se o CNPJ nao
# achar nada, tenta pelo nome da empresa.
#
# Decisoes do Tulio (23/09/2026):
#   1. Tarefa CONCLUIDA sem desfecho registrado (fechada pela tela de
#      Tarefas) e CONVERTIDA: concluida_em vira cancelada_em (mesmo
#      instante), resultado anterior vai para o motivo. A proxima tarefa
#      criada no fechamento continua existindo.
#   2. Mais de uma reuniao no dia: fica a de CLIENTE cujo responsavel e o
#      EV da planilha; se ainda sobrar mais de uma, a que nao esta
#      concluida.
#   3. Sem reuniao no dia: CRIA tarefa + reuniao ja como no-show, na
#      oportunidade mais recente da conta, anfitriao = EV da planilha,
#      credito (agendado_por/criado_por) = SDR da planilha, criado_em = data
#      do agendamento, 10:00, sem Google. Conta sem oportunidade: pula.
#
# NUNCA sobrescreve desfecho REGISTRADO (realizada/cancelada): vira CONFLITO.
#
# Uso (no EC2):
#   sudo bash noshow-planilha.sh                      # SIMULA: so lista
#   sudo bash noshow-planilha.sh --aplicar            # grava (uma transacao)
#   sudo bash noshow-planilha.sh --aplicar --por email@dominio
set -euo pipefail

ENV_FILE="${ENV_FILE:-/home/hipo/app/.env}"

if [ -z "${DATABASE_URL:-}" ]; then
  if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  else
    echo "ERRO: DATABASE_URL nao esta no ambiente e $ENV_FILE nao e legivel." >&2
    echo "      Rode com sudo ou exporte DATABASE_URL." >&2
    exit 1
  fi
fi

echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

PY=""
for candidato in /home/hipo/app/.venv/bin/python /home/hipo/app/venv/bin/python /usr/bin/python3 python3; do
  if [ -x "$candidato" ] || command -v "$candidato" >/dev/null 2>&1; then
    if "$candidato" -c 'import asyncpg' >/dev/null 2>&1; then
      PY="$candidato"
      break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "ERRO: nao achei um python com asyncpg." >&2
  exit 1
fi

"$PY" - "$@" <<'PYCODE'
import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg

TZ = "America/Sao_Paulo"
SP = ZoneInfo(TZ)
HORA_PADRAO = time(10, 0)

# Nome na planilha -> inicio do nome no HIPO
EV_NOME = {"JAKE": "Jakeline", "BRUNO": "Bruno"}
SDR_NOME = {"Kethlleen": "Kethlleen", "Gabriel": "Gabriel"}

# (linha, empresa, cnpj, data da reuniao, data do agendamento, SDR, EV)
PLANILHA = [
    (3,  "GADE SOLUCOES", "41713146000161", "2026-08-13", "2026-08-05", "Kethlleen", "JAKE"),
    (7,  "M&G TECH", "56884197000123", "2026-08-17", "2026-08-06", "Kethlleen", "JAKE"),
    (8,  "POWER FIELD SOLUCOES ELETRICAS", "49979247000190", "2026-08-10", "2026-08-06", "Kethlleen", "BRUNO"),
    (23, "DE GRAU", "67237818000101", "2026-08-24", "2026-08-17", "Kethlleen", "BRUNO"),
    (29, "PIZZARIA E PASTELARIA CASTELO AZUL", "04643450000153", "2026-08-20", "2026-08-19", "Gabriel", "JAKE"),
    (30, "HEMF AMBIENTES CORPORATIVOS", "22846435000194", "2026-08-21", "2026-08-19", "Gabriel", "JAKE"),
    (31, "TRAVELUX", "28942396000105", "2026-08-21", "2026-08-19", "Gabriel", "BRUNO"),
    (32, "ISRAEL SOLUCOES INDUSTRIAIS", "65919902000171", "2026-08-20", "2026-08-19", "Gabriel", "JAKE"),
    (33, "JURERE PADARIA E CAFE", "43935359000163", "2026-08-21", "2026-08-19", "Gabriel", "BRUNO"),
    (37, "ALPHACENTRO OPERADOR LOGISTICO", "57934453000102", "2026-08-25", "2026-08-20", "Gabriel", "JAKE"),
    (40, "STAR HOCKEY", "20550640000182", "2026-08-21", "2026-08-20", "Gabriel", "BRUNO"),
    (44, "PRIME FULL PET FOODS", "53204507000123", "2026-08-21", "2026-08-21", "Gabriel", "JAKE"),
    (49, "M&G TECH", "56884197000123", "2026-08-28", "2026-08-24", "Kethlleen", "JAKE"),
    (50, "OPA COMERCIO", "51163417000106", "2026-08-28", "2026-08-24", "Kethlleen", "JAKE"),
    (51, "DIVERBRAS INDUSTRIA E COMERCIO", "57905321000152", "2026-09-02", "2026-08-24", "Kethlleen", "JAKE"),
    (55, "IBL LOGISTICA", "03558055000100", "2026-09-01", "2026-08-25", "Gabriel", "BRUNO"),
    (60, "CONTABILIDADE FQS", "33647776000157", "2026-09-01", "2026-08-28", "Gabriel", "JAKE"),
    (66, "IBL LOGISTICA", "03558055000100", "2026-09-04", "2026-09-01", "Gabriel", "BRUNO"),
    (68, "DIVERBRAS INDUSTRIA E COMERCIO", "57905321000152", "2026-09-08", "2026-09-02", "Kethlleen", "JAKE"),
    (69, "NN MANUTENCAO EM REDUTORES E USINAGEM", "06335181000193", "2026-09-08", "2026-09-01", "Kethlleen", "JAKE"),
    (70, "REART", "74390246000153", "2026-09-09", "2026-09-02", "Gabriel", "JAKE"),
    (80, "IBL LOGISTICA", "03558055000100", "2026-09-14", "2026-09-09", "Gabriel", "BRUNO"),
    (81, "SOUZAFISCO CONTABILIDADE", "23650550000151", "2026-09-11", "2026-09-09", "Kethlleen", "BRUNO"),
    (84, "FLAUMAR GESTAO CONTABIL", "35993019000160", "2026-09-15", "2026-09-11", "Gabriel", "JAKE"),
    (87, "CONTABILIDADE FACANHA", "07023637000142", "2026-09-15", "2026-09-14", "Gabriel", "BRUNO"),
    (95, "INOXTEEL", "05083457000120", "2026-09-18", "2026-09-17", "Gabriel", "JAKE"),
    (97, "FORTRAK LOCACAO E TRANSPORTES", "19646115000186", "2026-09-22", "2026-09-17", "Gabriel", "JAKE"),
]

BUSCA = f"""
SELECT t.id AS tarefa_id, t.tipo, t.prazo, t.concluida_em, t.cancelada_em,
       t.resultado, t.criado_por, (t.prazo AT TIME ZONE '{TZ}')::date AS dia,
       r.id AS reuniao_id, r.desfecho,
       c.id AS conta_id, c.razao_social, c.cnpj,
       u.nome AS responsavel,
       CASE WHEN t.conta_id IS NOT NULL THEN 'parceiro' ELSE 'cliente' END AS alvo
  FROM tarefas t
  LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
  JOIN contas c ON c.id = COALESCE(o.conta_id, t.conta_id)
  LEFT JOIN reunioes r ON r.tarefa_id = t.id
  LEFT JOIN usuarios u ON u.id = t.responsavel_id
 WHERE t.tipo IN ('reuniao', 'visita')
   AND {{filtro}}
 ORDER BY t.prazo
"""

OBS = "No-show (planilha CONTROLE DE VENDAS, linha {linha})"


def dsn_limpo(url: str) -> str:
    for prefixo in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefixo):
            return "postgresql://" + url[len(prefixo):]
    return url


def rotulo_estado(c) -> str:
    if c["desfecho"]:
        return c["desfecho"]
    if c["concluida_em"]:
        return "concluida"
    if c["cancelada_em"]:
        return "cancelada s/ desfecho"
    return "aberta"


def hhmm(dt) -> str:
    return dt.astimezone(SP).strftime("%d/%m %H:%M") if dt else "?"


async def contas_da_linha(conn, cnpj: str, nome: str):
    linhas = await conn.fetch(
        "SELECT id, razao_social FROM contas WHERE cnpj = $1", cnpj
    )
    if linhas:
        return linhas
    return await conn.fetch(
        "SELECT id, razao_social FROM contas "
        "WHERE razao_social ILIKE $1 OR nome_fantasia ILIKE $1",
        f"%{nome}%",
    )


async def candidatos(conn, conta_ids):
    if not conta_ids:
        return []
    return await conn.fetch(BUSCA.format(filtro="c.id = ANY($1::uuid[])"), conta_ids)


async def usuario_por_nome(conn, inicio: str):
    linhas = await conn.fetch(
        "SELECT id, nome FROM usuarios WHERE nome ILIKE $1 ORDER BY ativo DESC NULLS LAST, created_at",
        f"{inicio}%",
    )
    return linhas[0] if linhas else None


def desempatar(no_dia, ev_nome: str):
    """Regra 2: cliente + responsavel = EV da planilha; depois, nao concluida."""
    if len(no_dia) <= 1:
        return no_dia
    filtro = [c for c in no_dia
              if c["alvo"] == "cliente"
              and (c["responsavel"] or "").lower().startswith(ev_nome.lower())]
    if len(filtro) > 1:
        abertas = [c for c in filtro if c["concluida_em"] is None and c["desfecho"] is None]
        if len(abertas) == 1:
            filtro = abertas
    return filtro


def classificar(no_dia) -> tuple[str, str]:
    c = no_dia[0]
    if c["desfecho"] == "no_show":
        return "JA_NOSHOW", ""
    if c["desfecho"]:
        return "CONFLITO", f"desfecho REGISTRADO como {c['desfecho']}"
    if c["prazo"] > datetime.now(timezone.utc):
        return "FUTURA", "reuniao ainda nao aconteceu"
    if c["concluida_em"]:
        return "CONVERTER", "concluida -> no-show"
    return "APLICAR", rotulo_estado(c)


async def marcar_no_show(conn, tarefa_id, reuniao_id, tipo, criado_por,
                         linha: int, por) -> None:
    obs = OBS.format(linha=linha)
    t = await conn.fetchrow(
        "SELECT prazo, concluida_em, cancelada_em, resultado FROM tarefas "
        "WHERE id = $1 FOR UPDATE",
        tarefa_id,
    )
    if t["concluida_em"] is not None:
        # Regra 1: o fechamento vira cancelamento no MESMO instante.
        momento = t["concluida_em"]
        motivo = obs + (f" | resultado anterior: {t['resultado']}" if t["resultado"] else "")
        await conn.execute(
            """
            UPDATE tarefas
               SET concluida_em = NULL, resultado = NULL,
                   cancelada_em = $2, motivo_cancelamento = $3, atualizado_em = NOW()
             WHERE id = $1
            """,
            tarefa_id, momento, motivo,
        )
    elif t["cancelada_em"] is None:
        momento = datetime.now(timezone.utc)
        await conn.execute(
            """
            UPDATE tarefas
               SET cancelada_em = NOW(), motivo_cancelamento = $2, atualizado_em = NOW()
             WHERE id = $1
            """,
            tarefa_id, obs,
        )
    else:
        momento = t["cancelada_em"]
    antecedencia = round((t["prazo"] - momento).total_seconds() / 3600, 2)

    if reuniao_id is None:
        reuniao_id = await conn.fetchval(
            """
            -- criado_em = o da tarefa: o Monitor conta AGEND MES por
            -- reunioes.criado_em, e NOW() jogaria agendamento de agosto em setembro.
            INSERT INTO reunioes (tarefa_id, duracao_min, modalidade, criado_por, agendado_por,
                                  criado_em)
            SELECT $1, 30, $2, $3, $4, t.criado_em FROM tarefas t WHERE t.id = $1
            RETURNING id
            """,
            tarefa_id, "presencial" if tipo == "visita" else "online",
            por, criado_por or por,
        )

    status = await conn.execute(
        """
        UPDATE reunioes
           SET desfecho = 'no_show', desfecho_em = NOW(), desfecho_por = $2,
               desfecho_observacao = $3, desfecho_antecedencia_horas = $4,
               atualizado_em = NOW()
         WHERE id = $1 AND desfecho IS NULL
        """,
        reuniao_id, por, obs, antecedencia,
    )
    if status != "UPDATE 1":
        raise RuntimeError(f"linha {linha}: desfecho mudou no meio do caminho")


async def criar_no_show(conn, plano_criar: dict, linha: int, por) -> None:
    """Regra 3: tarefa + reuniao nascem ja canceladas como no-show."""
    obs = OBS.format(linha=linha)
    prazo = plano_criar["prazo"]
    criado_em = plano_criar["criado_em"]
    tarefa_id = await conn.fetchval(
        """
        INSERT INTO tarefas (oportunidade_id, tipo, titulo, responsavel_id, prazo,
                             cancelada_em, motivo_cancelamento, criado_por,
                             criado_em, atualizado_em)
        VALUES ($1, 'reuniao', $2, $3, $4, $4, $5, $6, $7, NOW())
        RETURNING id
        """,
        plano_criar["oportunidade_id"], plano_criar["titulo"], plano_criar["ev_id"],
        prazo, obs, plano_criar["sdr_id"], criado_em,
    )
    await conn.execute(
        """
        INSERT INTO reunioes (tarefa_id, duracao_min, modalidade, criado_por, agendado_por,
                              observacoes, desfecho, desfecho_em, desfecho_por,
                              desfecho_observacao, desfecho_antecedencia_horas,
                              criado_em, atualizado_em)
        VALUES ($1, 30, 'online', $2, $2, $3, 'no_show', NOW(), $4, $3, 0, $5, NOW())
        """,
        tarefa_id, plano_criar["sdr_id"], obs, por, criado_em,
    )


async def main() -> int:
    args = sys.argv[1:]
    aplicar = "--aplicar" in args
    email_por = args[args.index("--por") + 1] if "--por" in args else None

    conn = await asyncpg.connect(dsn_limpo(os.environ["DATABASE_URL"]))
    try:
        if email_por:
            por = await conn.fetchrow(
                "SELECT id, nome FROM usuarios WHERE lower(email) = lower($1)", email_por
            )
        else:
            por = await conn.fetchrow(
                "SELECT id, nome FROM usuarios WHERE cargo = 'Franqueado' AND ativo "
                "ORDER BY created_at LIMIT 1"
            )
        if por is None:
            print("ERRO: nao achei o usuario que vai registrar (use --por email).", file=sys.stderr)
            return 1

        evs = {k: await usuario_por_nome(conn, v) for k, v in EV_NOME.items()}
        sdrs = {k: await usuario_por_nome(conn, v) for k, v in SDR_NOME.items()}
        print(f"Registrado por: {por['nome']}")
        print("EVs:  " + ", ".join(f"{k}={u['nome'] if u else 'NAO ACHEI'}" for k, u in evs.items()))
        print("SDRs: " + ", ".join(f"{k}={u['nome'] if u else 'NAO ACHEI'}" for k, u in sdrs.items()))
        print("MODO: " + ("APLICAR (grava)" if aplicar else "SIMULACAO (nao grava nada)"))
        print()

        plano = []
        usadas = set()
        for linha, nome, cnpj, data_txt, agend_txt, sdr, ev in PLANILHA:
            dia = date.fromisoformat(data_txt)
            contas = await contas_da_linha(conn, cnpj, nome)
            cands = await candidatos(conn, [c["id"] for c in contas])
            no_dia = desempatar([c for c in cands if c["dia"] == dia], EV_NOME[ev])
            extra = {"cands": cands, "no_dia": no_dia}

            if len(no_dia) > 1:
                acao, det = "AMBIGUO", f"{len(no_dia)} reunioes no dia mesmo apos a regra"
            elif len(no_dia) == 1:
                acao, det = classificar(no_dia)
                if acao in ("APLICAR", "CONVERTER"):
                    if no_dia[0]["tarefa_id"] in usadas:
                        acao, det = "AMBIGUO", "mesma reuniao ja usada por outra linha"
                    else:
                        usadas.add(no_dia[0]["tarefa_id"])
            else:
                # Regra 3: criar
                opp = None
                if contas:
                    opp = await conn.fetchrow(
                        """
                        SELECT o.id, COALESCE(c.nome_fantasia, c.razao_social) AS empresa, o.numero
                          FROM oportunidades o JOIN contas c ON c.id = o.conta_id
                         WHERE o.conta_id = ANY($1::uuid[])
                         ORDER BY (o.status IN ('ativa','suspensa')) DESC, o.criado_em DESC
                         LIMIT 1
                        """,
                        [c["id"] for c in contas],
                    )
                if not contas:
                    acao, det = "SEM_CONTA", "empresa nao existe no HIPO"
                elif opp is None:
                    acao, det = "SEM_OPORTUNIDADE", "conta existe mas nao tem oportunidade"
                elif evs[ev] is None:
                    acao, det = "SEM_USUARIO", f"EV {ev} nao encontrado no HIPO"
                else:
                    prazo = datetime.combine(dia, HORA_PADRAO, SP)
                    criado_em = datetime.combine(date.fromisoformat(agend_txt), time(9, 0), SP)
                    sdr_u = sdrs.get(sdr) or por
                    extra["criar"] = {
                        "oportunidade_id": opp["id"],
                        "titulo": f"Reuniao - {opp['empresa']}"[:200],
                        "ev_id": evs[ev]["id"],
                        "sdr_id": sdr_u["id"],
                        "prazo": prazo,
                        "criado_em": criado_em,
                    }
                    acao = "CRIAR"
                    det = (f"{opp['numero']} {hhmm(prazo)} anfitriao={evs[ev]['nome']} "
                           f"agendado_por={sdr_u['nome']}")
            plano.append((linha, nome, dia, sdr, ev, acao, det, extra))

        ordem = ["APLICAR", "CONVERTER", "CRIAR", "JA_NOSHOW", "CONFLITO", "AMBIGUO",
                 "FUTURA", "SEM_OPORTUNIDADE", "SEM_CONTA", "SEM_USUARIO"]
        for grupo in ordem:
            itens = [p for p in plano if p[5] == grupo]
            if not itens:
                continue
            print(f"== {grupo} ({len(itens)}) " + "=" * 50)
            for linha, nome, dia, sdr, ev, acao, det, extra in itens:
                print(f"  L{linha:<3} {dia:%d/%m}  {nome[:40]:<40} SDR {sdr:<9} EV {ev:<6} {det}")
                for c in extra["no_dia"]:
                    print(f"        HIPO: {hhmm(c['prazo'])} {c['tipo']} {c['alvo']} "
                          f"resp={c['responsavel']} estado={rotulo_estado(c)} "
                          f"conta={c['razao_social'][:40]}")
            print()

        gravar = [p for p in plano if p[5] in ("APLICAR", "CONVERTER", "CRIAR")]
        print(f"Resumo: {len(gravar)} a gravar de {len(PLANILHA)} linhas "
              f"(aplicar {sum(p[5]=='APLICAR' for p in gravar)}, "
              f"converter {sum(p[5]=='CONVERTER' for p in gravar)}, "
              f"criar {sum(p[5]=='CRIAR' for p in gravar)}).")

        if not aplicar:
            print("Nada foi gravado. Rode com -Aplicar para gravar.")
            return 0

        async with conn.transaction():
            for linha, _n, _d, _s, _e, acao, _det, extra in gravar:
                if acao == "CRIAR":
                    await criar_no_show(conn, extra["criar"], linha, por["id"])
                else:
                    c = extra["no_dia"][0]
                    await marcar_no_show(conn, c["tarefa_id"], c["reuniao_id"], c["tipo"],
                                         c["criado_por"], linha, por["id"])
        print(f"OK: {len(gravar)} reunioes gravadas como no-show.")
        return 0
    finally:
        await conn.close()


sys.exit(asyncio.run(main()))
PYCODE
