"""
HIPO — Coletor das ligações gravadas (entrega 056).

Roda a cada 2 minutos pelo hipo-ligacoes.timer. A cada passada
(services/coleta_ligacao.passada):

  1. clique sem gravação há mais de 6 h      -> sem_gravacao;
  2. upload não confirmado há mais de 2 h    -> confere no S3: chegou,
                                                transcreve; não chegou, erro;
  3. transcrição em andamento                -> pergunta à AWS; pronta,
                                                grava o texto e apaga o job;
  4. pronta sem resumo (últimos 3 dias)      -> gera o resumo;
  5. áudio além de LIGACOES_RETENCAO_DIAS    -> apaga do S3 (o texto fica).

O caminho normal NÃO depende do timer: o agente confirma o upload e a
transcrição começa na hora. O timer é quem termina (o Transcribe responde
em 30 s a alguns minutos) e quem varre o que ficou para trás.

USO
  cd /home/hipo/app/api
  python3 -m scripts.coletar_ligacoes                 # uma passada
  python3 -m scripts.coletar_ligacoes --so-listar     # só mostra o que olharia
  python3 -m scripts.coletar_ligacoes --ligacao <uuid>

Código de saída 1 só quando TODAS as ligações olhadas falharam com exceção
— é o sinal de configuração quebrada (banco, credencial), e não de uma
gravação esquisita.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from uuid import UUID

import asyncpg

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])  # permite rodar de api/

from config import settings  # noqa: E402
from services import coleta_ligacao as coleta  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("hipo.coletar_ligacoes")


async def executar(so_listar: bool = False, ligacao: UUID | None = None) -> int:
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        if ligacao:
            atual = await coleta.processar(conn, ligacao)
            if atual is None:
                log.error("ligacao %s nao existe", ligacao)
                return 1
            log.info("ligacao %s: %s %s", ligacao, atual["status"], atual.get("erro") or "")
            return 0
        ids = await coleta.pendentes(conn)
        log.info("%d ligacao(oes) para olhar", len(ids))
        if so_listar:
            for i in ids:
                print(f"olhar  {i}")
            return 0
        r = await coleta.passada(conn)
        log.info(
            "passada concluida: status %s; %d falha(s) inesperada(s); %d audio(s) removido(s)",
            r["status"] or "{}", r["falhas"], r["audios_removidos"],
        )
        return 1 if (ids and r["falhas"] == len(ids)) else 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Coleta as transcrições das ligações gravadas")
    p.add_argument("--so-listar", action="store_true", help="mostra o que seria olhado")
    p.add_argument("--ligacao", type=UUID, help="uma ligação só (ligacoes.id)")
    a = p.parse_args()
    return asyncio.run(executar(so_listar=a.so_listar, ligacao=a.ligacao))


if __name__ == "__main__":
    sys.exit(main())
