"""
HIPO — Verifica se o cliente respondeu os e-mails comerciais (entrega 050).

Roda a cada 15 minutos pelo hipo-emails.timer. A cada passada, para cada
e-mail enviado nos últimos 30 dias que ainda não tem resposta, lê os
CABEÇALHOS do fio no Gmail do remetente (escopo gmail.metadata — o corpo da
resposta nunca é lido) e grava `respondido_em` quando aparece mensagem do
cliente depois da nossa.

É a mesma passada do botão "Ver se respondeu" da tela
(routers/crm_emails.verificar_um).

USO
  cd /home/hipo/app/api
  python3 -m scripts.verificar_respostas_email              # uma passada
  python3 -m scripts.verificar_respostas_email --so-listar  # só mostra a fila

IDEMPOTENTE. Respondido sai da fila; rodar duas vezes seguidas só repete a
leitura do que continua sem resposta.

UM E-MAIL COM PROBLEMA NÃO PARA OS OUTROS. O erro de cada um vai para a
coluna `verificacao_erro`. O código de saída só é 1 quando NENHUM deu certo
e havia algum na fila — sinal de configuração quebrada (delegação sem o
escopo gmail.metadata, chave), e não de uma conversa apagada.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import asyncpg

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])  # permite rodar de api/

from config import settings  # noqa: E402
from routers.crm_emails import pendentes_de_verificacao, verificar_um  # noqa: E402
from services import gmail  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("hipo.verificar_respostas_email")

# Teto por passada. A unit tem 300 s; cada leitura de fio leva ~0,3 s. O que
# sobrar fica para a próxima passada — a fila é ordenada pelo que foi
# verificado há mais tempo.
MAX_POR_PASSADA = 400


async def executar(so_listar: bool = False) -> int:
    if not gmail.configurado():
        log.info("Google não configurado (GOOGLE_SA_ARQUIVO vazio); nada a fazer.")
        return 0
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        fila = (await pendentes_de_verificacao(conn))[:MAX_POR_PASSADA]
        log.info("%d e-mail(s) sem resposta para olhar", len(fila))
        if so_listar:
            for e in fila:
                print(f"{e['id']}  {e['remetente_email']}  fio={e['gmail_thread_id']}")
            return 0
        contagem = {"respondido": 0, "sem_resposta": 0, "erro": 0}
        for e in fila:
            try:
                contagem[await verificar_um(conn, e)] += 1
            except Exception:
                contagem["erro"] += 1
                log.exception("e-mail %s: falha inesperada", e["id"])
        log.info("passada concluida: %s", contagem)
        ok = contagem["respondido"] + contagem["sem_resposta"]
        return 1 if (fila and ok == 0) else 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Verifica respostas dos e-mails comerciais")
    p.add_argument("--so-listar", action="store_true",
                   help="mostra a fila, sem chamar o Google")
    a = p.parse_args()
    return asyncio.run(executar(so_listar=a.so_listar))


if __name__ == "__main__":
    sys.exit(main())
