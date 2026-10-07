#!/usr/bin/env bash
#
# HIPO - mede o volume de fala das reunioes transcritas.
#
# PARA QUE SERVE
#
# Calibrar o custo do copiloto de reuniao (transcricao ao vivo + cartoes de
# pergunta/objecao). A transcricao ao vivo e cobrada por minuto; a IA, por
# token -- e token depende de quantas palavras se fala. Este script mede
# isso nas reunioes reais em vez de chutar.
#
# Rodar NA EC2, como ec2-user (o .ps1 de mesmo nome faz o scp e chama):
#   sudo bash /tmp/medir-falas-reunioes.sh 2026-09-24
#   sudo bash /tmp/medir-falas-reunioes.sh 2026-09-24 bruno.goncalo@controllermedseg.com
#
# SO LE. Nenhum INSERT, UPDATE ou DELETE. A transacao e aberta READ ONLY:
# se alguem editar o SQL abaixo e colocar escrita, o Postgres recusa.
#
# ASCII puro.

set -euo pipefail

DESDE="${1:-2026-09-24}"
EMAIL="${2:-}"
ENV_PATH=/home/hipo/app/.env

case "$DESDE" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
    *) echo "ERRO: data no formato AAAA-MM-DD (veio '$DESDE')."; exit 1 ;;
esac

# -- 1. ler o .env sem eval -------------------------------------------
# Mesmo tratamento do medir-cobertura.sh: o systemd e quem injeta o .env no
# app, entao aqui ele e lido e exportado a mao. Credencial nunca vai para
# linha de comando (apareceria no `ps`).
if ! CONTEUDO_ENV=$(cat "$ENV_PATH" 2>/dev/null); then
    echo "ERRO: nao consegui ler $ENV_PATH (rodou com sudo?)."
    exit 1
fi

while IFS= read -r linha; do
    case "$linha" in
        ''|'#'*) continue ;;
        [A-Za-z_]*=*) ;;
        *) continue ;;
    esac
    chave=${linha%%=*}
    valor=${linha#*=}
    case "$valor" in
        \"*\") valor=${valor#\"}; valor=${valor%\"} ;;
        \'*\') valor=${valor#\'}; valor=${valor%\'} ;;
    esac
    [ "$chave" = "DATABASE_URL" ] && export DATABASE_URL="$valor"
done <<EOF
$CONTEUDO_ENV
EOF

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERRO: $ENV_PATH sem DATABASE_URL."
    exit 1
fi
echo "Banco : $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"

# -- 2. python que importa asyncpg ------------------------------------
PY=""
for c in /usr/bin/python3 python3.11 python3; do
    p=$(command -v "$c" 2>/dev/null) || continue
    if "$p" -c 'import asyncpg' >/dev/null 2>&1; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
    echo "ERRO: nenhum python3 com asyncpg nesta maquina."
    exit 1
fi
echo "Python: $PY"
echo "Desde : $DESDE${EMAIL:+   Anfitriao: $EMAIL}"
echo

export HIPO_DESDE="$DESDE" HIPO_EMAIL="$EMAIL" PYTHONDONTWRITEBYTECODE=1

"$PY" - <<'PY'
import asyncio, json, os, re
from datetime import datetime
from zoneinfo import ZoneInfo

import asyncpg

SQL = """
SELECT t.prazo                         AS inicio,
       r.duracao_min,
       u.nome                          AS anfitriao,
       COALESCE(c1.razao_social, c2.razao_social, '(sem conta)') AS empresa,
       rt.entradas,
       rt.texto
  FROM reuniao_transcricoes rt
  JOIN reunioes r      ON r.id = rt.reuniao_id
  JOIN tarefas  t      ON t.id = r.tarefa_id
  JOIN usuarios u      ON u.id = t.responsavel_id
  LEFT JOIN contas c1  ON c1.id = t.conta_id
  LEFT JOIN oportunidades o ON o.id = t.oportunidade_id
  LEFT JOIN contas c2  ON c2.id = o.conta_id
 WHERE rt.texto IS NOT NULL
   AND t.prazo >= $1::date
   AND ($2 = '' OR lower(u.email) = lower($2))
 ORDER BY t.prazo
"""

PALAVRA = re.compile(r"\w+", re.UNICODE)


def palavras(txt: str) -> int:
    return len(PALAVRA.findall(txt or ""))


def data(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def medir(row):
    entradas = row["entradas"]
    if isinstance(entradas, str):
        entradas = json.loads(entradas)
    entradas = entradas or []

    por_pessoa: dict[str, int] = {}
    inicios, fins = [], []
    for e in entradas:
        n = palavras(e.get("texto"))
        quem = e.get("participante") or "Participante"
        por_pessoa[quem] = por_pessoa.get(quem, 0) + n
        i, f = data(e.get("inicio")), data(e.get("fim"))
        if i:
            inicios.append(i)
        if f or i:
            fins.append(f or i)

    total = sum(por_pessoa.values()) if entradas else palavras(row["texto"])
    minutos = None
    if inicios and fins:
        minutos = max((max(fins) - min(inicios)).total_seconds() / 60, 1)
    return {
        "total": total,
        "falas": len(entradas),
        "minutos": minutos,
        "chars": len(row["texto"] or ""),
        "por_pessoa": por_pessoa,
    }


async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(SQL, datetime.strptime(os.environ["HIPO_DESDE"], "%Y-%m-%d").date(),
                                    os.environ.get("HIPO_EMAIL", ""))
    finally:
        await conn.close()

    if not rows:
        print("Nenhuma reuniao com transcricao no filtro.")
        return

    medidas = []
    for row in rows:
        m = medir(row)
        medidas.append(m)
        ini = row["inicio"].astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m %H:%M")
        dur = f"{m['minutos']:.0f} min falados" if m["minutos"] else "duracao ?"
        ppm = f"{m['total'] / m['minutos']:.0f} pal/min" if m["minutos"] else "-"
        print(f"{ini} | {row['anfitriao']} | {row['empresa'][:45]}")
        print(f"   agendada {row['duracao_min']} min | {dur} | {m['falas']} falas | "
              f"{m['total']} palavras | {ppm} | {m['chars']} caracteres")
        tot = m["total"] or 1
        for quem, n in sorted(m["por_pessoa"].items(), key=lambda x: -x[1]):
            print(f"      {quem[:30]:30} {n:6} palavras ({100 * n / tot:.0f}%)")
        print()

    com_min = [m for m in medidas if m["minutos"]]
    print("=" * 70)
    print(f"Reunioes: {len(medidas)}")
    print(f"Palavras por reuniao (media): {sum(m['total'] for m in medidas) / len(medidas):.0f}")
    print(f"Caracteres por reuniao (media): {sum(m['chars'] for m in medidas) / len(medidas):.0f}")
    if com_min:
        pal = sum(m["total"] for m in com_min)
        mins = sum(m["minutos"] for m in com_min)
        print(f"Minutos falados (media): {mins / len(com_min):.1f}")
        print(f"Ritmo medio: {pal / mins:.0f} palavras/min")
        print(f"Projecao para 30 min: {30 * pal / mins:.0f} palavras")


asyncio.run(main())
PY
