"""
HIPO — Sincroniza os contratos com a Autentique (entrega 053).

Roda a cada 30 minutos pelo hipo-contratos.timer. É a rede de segurança do
webhook: entrega perdida (HIPO fora do ar, nginx reiniciando, segredo
trocado) não deixa contrato parado em "aguardando". A cada passada:

  * lê na Autentique cada contrato aguardando assinatura e aplica o estado
    (mesma função do webhook e do botão "Atualizar" da tela);
  * para contrato assinado sem o PDF no S3, tenta guardar de novo.

USO
  cd /home/hipo/app/api
  python3 -m scripts.sincronizar_contratos              # uma passada
  python3 -m scripts.sincronizar_contratos --so-listar  # só mostra a fila

IDEMPOTENTE. Aplicar o mesmo documento duas vezes não gera evento nem
tarefa repetidos.

UM CONTRATO COM PROBLEMA NÃO PARA OS OUTROS. O erro fica em
contratos.sincronizacao_erro (a tela mostra). Saída 1 só quando NENHUM deu
certo e havia fila — sinal de token ou rede quebrados.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import asyncpg

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])  # permite rodar de api/

from config import settings  # noqa: E402
from routers.crm_contratos import pendentes_de_sincronizacao, sincronizar_um  # noqa: E402
from services import autentique  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("hipo.sincronizar_contratos")

# Cada leitura leva ~0,5 s; a unit tem 300 s.
MAX_POR_PASSADA = 300


async def executar(so_listar: bool = False) -> int:
    if not settings.AUTENTIQUE_API_TOKEN:
        log.info("AUTENTIQUE_API_TOKEN vazio; nada a fazer.")
        return 0
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        fila = (await pendentes_de_sincronizacao(conn))[:MAX_POR_PASSADA]
        log.info("%d contrato(s) para olhar", len(fila))
        if so_listar:
            for c in fila:
                print(f"{c['id']}  {c['status']:9}  v{c['versao']}  {c['nome_documento']}")
            return 0
        ok = erros = 0
        for c in fila:
            try:
                atualizado = await sincronizar_um(conn, c)
                ok += 1
                if atualizado["status"] != c["status"]:
                    log.info("contrato %s: %s -> %s", c["id"], c["status"], atualizado["status"])
            except autentique.AutentiqueErro as e:
                erros += 1
                log.warning("contrato %s: %s", c["id"], e)
            except Exception:
                erros += 1
                log.exception("contrato %s: falha inesperada", c["id"])
        log.info("passada concluida: %d ok, %d com erro", ok, erros)
        return 1 if (fila and ok == 0) else 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Sincroniza os contratos com a Autentique")
    p.add_argument("--so-listar", action="store_true",
                   help="só mostra a fila, sem chamar a Autentique")
    args = p.parse_args()
    return asyncio.run(executar(so_listar=args.so_listar))


if __name__ == "__main__":
    sys.exit(main())
