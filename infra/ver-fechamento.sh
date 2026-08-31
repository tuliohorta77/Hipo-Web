#!/usr/bin/env bash
# =====================================================================
# HIPO - Mostra o ultimo fechamento gravado E RENDERIZA o e-mail que sairia.
#
# SO LE. Nao envia nada, nao grava nada.
#
# POR QUE RENDERIZAR, E NAO SO OLHAR A TABELA
#
# A tabela mostra o JSON. O que chega na caixa e o resultado de
# relatorio_render sobre esse JSON -- e e ele que precisa fazer sentido as
# 03:10 da manha, para quem abre no celular. Ver o texto final ANTES do
# primeiro envio e a ultima chance barata de descobrir que um numero esta
# com rotulo errado, ou que a narrativa ficou generica demais.
#
#   scp -i "$HOME/Downloads/chave-hipo.pem" \
#       infra/ver-fechamento.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i "$HOME/Downloads/chave-hipo.pem" ec2-user@63.179.88.212 \
#       'bash /tmp/ver-fechamento.sh'
# =====================================================================
set -o pipefail

titulo() { printf '\n==== %s ====\n' "$1"; }
parar()  { printf '\n!! %s\n' "$1"; exit 1; }

D=$(sudo sed -n 's/^DATABASE_URL=//p' /home/hipo/app/.env)
[ -n "$D" ] || parar "DATABASE_URL vazia."

titulo "1. O que existe em relatorios_diarios"
psql "$D" -c "select dia, gerado_em, enviado_em, narrativa_modelo,
                     length(narrativa) as tam_narrativa,
                     destinatarios, erro
                from relatorios_diarios order by dia desc;" || parar "consulta falhou"

cat > /tmp/hipo_render.py <<'PY'
"""Renderiza o ultimo fechamento gravado, sem enviar."""
import asyncio
import json

import asyncpg

from config import settings
from services import relatorio_render


async def main():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "select dia, metricas, narrativa, narrativa_modelo, enviado_em"
            "  from relatorios_diarios order by dia desc limit 1"
        )
    finally:
        await conn.close()

    if row is None:
        print("nenhum fechamento gravado ainda.")
        return

    m = row["metricas"]
    m = json.loads(m) if isinstance(m, str) else m
    narrativa = row["narrativa"]

    print(f"dia .............. {row['dia']}")
    print(f"enviado_em ....... {row['enviado_em']}  (nulo = o e-mail ainda sai)")
    print(f"narrativa_modelo . {row['narrativa_modelo']}")
    print()

    print("==== NARRATIVA ====")
    if narrativa:
        print(narrativa)
    else:
        # Narrativa vazia com modelo preenchido = a guarda numerica descartou.
        # Vazia com modelo nulo = a chamada a API nem aconteceu.
        print("(vazia)")
        if row["narrativa_modelo"]:
            print(">> modelo preenchido e narrativa vazia: a guarda numerica")
            print(">> descartou. O motivo esta no journal:")
            print(">>   sudo journalctl -u hipo-fechamento -n 50 | grep -i narrativa")
    print()

    print("==== ASSUNTO ====")
    print(relatorio_render.assunto(m))
    print()

    print("==== CORPO EM TEXTO (o que chega em cliente sem HTML) ====")
    print(relatorio_render.montar_texto(m, narrativa))

    destino = f"/tmp/relatorio-{row['dia']}.html"
    with open(destino, "w", encoding="utf-8") as f:
        f.write(relatorio_render.montar_html(m, narrativa))
    print()
    print(f"==== HTML gravado em {destino} ====")


asyncio.run(main())
PY

titulo "2. Renderizando o e-mail (sem enviar)"
sudo systemd-run \
    --uid=ec2-user --gid=ec2-user \
    --property=EnvironmentFile=/home/hipo/app/.env \
    --property=WorkingDirectory=/home/hipo/app/api \
    --setenv=PYTHONPATH=/home/hipo/app/api \
    --setenv=PYTHONUNBUFFERED=1 \
    --wait --pipe --quiet \
    /usr/bin/python3 /tmp/hipo_render.py
CODIGO=$?
rm -f /tmp/hipo_render.py
[ $CODIGO -eq 0 ] || parar "a renderizacao falhou (codigo $CODIGO)"

cat <<'FIM'

==== PARA VER O HTML NO NAVEGADOR ====

    scp -i "$HOME\Downloads\chave-hipo.pem" `
        ec2-user@63.179.88.212:/tmp/relatorio-*.html .

FIM
