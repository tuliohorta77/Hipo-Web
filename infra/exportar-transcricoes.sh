#!/usr/bin/env bash
# Exporta as transcricoes prontas das reunioes para JSON (SO LEITURA).
# Uma linha por reuniao: anfitriao, cargo, tipo, desfecho, oportunidade,
# conta, participantes internos, resumo, proximos passos, falas e texto.
#
# Uso (no EC2):
#   sudo bash exportar-transcricoes.sh /tmp/transcricoes.json
set -euo pipefail

SAIDA="${1:-/tmp/transcricoes.json}"
ENV_FILE="${ENV_FILE:-/home/hipo/app/.env}"

if [ -z "${DATABASE_URL:-}" ]; then
  if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  else
    echo "ERRO: DATABASE_URL nao esta no ambiente e $ENV_FILE nao e legivel." >&2
    exit 1
  fi
fi

echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')" >&2

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

"$PY" - "$SAIDA" <<'PYCODE'
import asyncio
import json
import os
import sys

import asyncpg

SQL = """
SELECT
    r.id::text                                   AS reuniao_id,
    to_char(t.prazo AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM-DD HH24:MI') AS inicio,
    r.duracao_min,
    r.modalidade,
    tr.sigla                                     AS tipo_sigla,
    tr.nome                                      AS tipo_nome,
    r.desfecho,
    t.titulo,
    t.resultado                                  AS resultado_tarefa,
    u.nome                                       AS anfitriao,
    u.cargo                                      AS anfitriao_cargo,
    ag.nome                                      AS agendado_por,
    ag.cargo                                     AS agendado_por_cargo,
    (SELECT array_agg(pu.nome || ' (' || coalesce(pu.cargo,'?') || ')')
       FROM reuniao_participantes rp JOIN usuarios pu ON pu.id = rp.usuario_id
      WHERE rp.reuniao_id = r.id)                AS participantes_internos,
    o.numero                                     AS oportunidade,
    o.fase                                       AS opp_fase_atual,
    o.status                                     AS opp_status_atual,
    o.temperatura                                AS opp_temperatura,
    o.valor_mensalidade::float                   AS opp_valor_mensalidade,
    coalesce(c.razao_social, cp.razao_social)    AS empresa,
    coalesce(c.num_funcionarios, cp.num_funcionarios) AS num_funcionarios,
    (SELECT count(*) FROM tarefas t2
      WHERE t2.tarefa_anterior_id = t.id)        AS tarefas_seguintes,
    x.idioma,
    x.resumo,
    x.proximos_passos,
    x.entradas,
    x.texto
FROM reuniao_transcricoes x
JOIN reunioes r           ON r.id = x.reuniao_id
JOIN tarefas t            ON t.id = r.tarefa_id
JOIN usuarios u           ON u.id = t.responsavel_id
LEFT JOIN usuarios ag     ON ag.id = r.agendado_por
LEFT JOIN tipos_reuniao tr ON tr.id = r.tipo_id
LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
LEFT JOIN contas c        ON c.id = o.conta_id
LEFT JOIN contas cp       ON cp.id = t.conta_id
WHERE x.status = 'pronta'
ORDER BY t.prazo
"""


def dsn_limpo(url: str) -> str:
    for prefixo in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefixo):
            return "postgresql://" + url[len(prefixo):]
    return url


async def main(saida: str) -> None:
    conn = await asyncpg.connect(dsn_limpo(os.environ["DATABASE_URL"]))
    try:
        async with conn.transaction(readonly=True):
            linhas = await conn.fetch(SQL)
    finally:
        await conn.close()

    dados = []
    for l in linhas:
        d = dict(l)
        for campo in ("proximos_passos", "entradas"):
            if isinstance(d.get(campo), str):
                try:
                    d[campo] = json.loads(d[campo])
                except ValueError:
                    pass
        d["participantes_internos"] = list(d["participantes_internos"] or [])
        dados.append(d)

    with open(saida, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1, default=str)

    por_anfitriao = {}
    for d in dados:
        chave = f"{d['anfitriao']} ({d['anfitriao_cargo']})"
        por_anfitriao[chave] = por_anfitriao.get(chave, 0) + 1
    print(f"{len(dados)} transcricoes exportadas para {saida}", file=sys.stderr)
    for k, v in sorted(por_anfitriao.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}", file=sys.stderr)


asyncio.run(main(sys.argv[1]))
PYCODE

chmod 644 "$SAIDA"
