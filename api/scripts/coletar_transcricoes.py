"""
HIPO — Coletor de transcrições do Google Meet.

Roda a cada 15 minutos pelo hipo-transcricoes.timer. A cada passada:

  1. procura reuniões com sala do Meet que terminaram nos últimos 3 dias e
     ainda não têm transcrição definitiva;
  2. para cada uma, faz a MESMA passada do botão "Buscar agora" da tela
     (services/coleta_transcricao.coletar): espera, coleta ou desiste;
  3. gera o resumo das prontas que ficaram sem (a chave da IA entrou
     depois, ou a passada anterior caiu entre o texto e o resumo);
  4. avalia contra o Roteiro de Vendas (scorecard, entrega 030) as reuniões
     de oportunidade com transcrição pronta e sem avaliação — inclusive as
     que acabaram de chegar no passo 2. É assim que o vendedor tem a nota
     minutos depois da call, sem clicar em nada.

     A avaliação leva até dois minutos por reunião e a unit tem 300 s de
     teto: a passada só COMEÇA uma avaliação nova enquanto não passou de
     ORCAMENTO_AVALIACAO_S. O que sobrar fica para a próxima passada.

USO
  cd /home/hipo/app/api
  python3 -m scripts.coletar_transcricoes                # uma passada
  python3 -m scripts.coletar_transcricoes --so-listar    # só mostra o que olharia
  python3 -m scripts.coletar_transcricoes --reuniao <uuid>   # uma reunião, como o botão

IDEMPOTENTE. Reunião pronta ou indisponível sai da lista; rodar duas vezes
seguidas faz, na segunda, só o que ainda está aguardando.

UMA REUNIÃO COM PROBLEMA NÃO PARA AS OUTRAS. Cada uma roda protegida; a
exceção inesperada é logada com o id e a passada segue. O código de saída
só é 1 quando NENHUMA deu certo e havia alguma para olhar — é o sinal de
configuração quebrada (banco, credencial), e não de uma sala esquisita.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from uuid import UUID

import asyncpg

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])  # permite rodar de api/

from config import settings  # noqa: E402
from services import avaliacao_roteiro  # noqa: E402
from services import coleta_avaliacao  # noqa: E402
from services import coleta_transcricao as coleta  # noqa: E402
from services import google_meet, resumo_reuniao  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("hipo.coletar_transcricoes")

# Segundos de passada depois dos quais nenhuma avaliacao NOVA comeca. Com
# o timeout da chamada (avaliacao_roteiro.TIMEOUT_S = 150) cabe nos 300 s
# da unit com folga para a coleta.
ORCAMENTO_AVALIACAO_S = 120


async def avaliar_pendentes(conn, inicio: float, so_listar: bool = False) -> int:
    """A passada do scorecard. Devolve quantas avaliou."""
    if not avaliacao_roteiro.configurado():
        return 0
    ids = await coleta_avaliacao.pendentes(conn)
    log.info("%d reuniao(oes) para avaliar no scorecard", len(ids))
    if so_listar:
        for i in ids:
            print(f"avaliar  {i}")
        return 0
    feitas = 0
    for rid in ids:
        if time.monotonic() - inicio > ORCAMENTO_AVALIACAO_S:
            log.info("orcamento da passada esgotado; %d avaliacao(oes) ficam para a proxima",
                     len(ids) - feitas)
            break
        try:
            estado = await coleta_avaliacao.avaliar(conn, rid)
        except (coleta_avaliacao.AvaliacaoIndisponivel, coleta_avaliacao.EmAndamento) as e:
            log.info("reuniao %s: scorecard: %s", rid, e)
            continue
        except Exception:
            log.exception("reuniao %s: falha inesperada no scorecard", rid)
            continue
        feitas += 1
        if estado.get("erro"):
            log.warning("reuniao %s: scorecard: %s", rid, estado["erro"])
        else:
            log.info("reuniao %s: scorecard %s/%s", rid, estado["nota_total"],
                     estado["nota_maxima"])
    return feitas


async def executar(so_listar: bool = False, reuniao: UUID | None = None) -> int:
    if not google_meet.configurado():
        # Desligado é estado válido: o timer pode estar instalado antes de
        # a chave existir. Sai limpo para o journal não encher de erro.
        log.info("Google não configurado (GOOGLE_SA_ARQUIVO vazio); nada a fazer.")
        return 0

    inicio = time.monotonic()
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        ids = [reuniao] if reuniao else await coleta.pendentes(conn)
        faltam_resumo = [] if reuniao else (
            await coleta.sem_resumo(conn) if resumo_reuniao.configurado() else []
        )
        log.info("%d reuniao(oes) para olhar, %d sem resumo", len(ids), len(faltam_resumo))
        if so_listar:
            for i in ids:
                print(f"coletar  {i}")
            for i in faltam_resumo:
                print(f"resumir  {i}")
            if not reuniao:
                await avaliar_pendentes(conn, inicio, so_listar=True)
            return 0

        ok = falhas = 0
        contagem: dict[str, int] = {}
        for rid in ids:
            try:
                estado = await coleta.coletar(conn, rid, manual=bool(reuniao))
            except Exception:
                falhas += 1
                log.exception("reuniao %s: falha inesperada", rid)
                continue
            ok += 1
            contagem[estado["status"]] = contagem.get(estado["status"], 0) + 1
            if estado.get("erro"):
                log.warning("reuniao %s: %s", rid, estado["erro"])

        for rid in faltam_resumo:
            try:
                estado = await coleta.resumir(conn, rid)
                if estado.get("resumo_erro"):
                    log.warning("reuniao %s: resumo: %s", rid, estado["resumo_erro"])
            except Exception:
                log.exception("reuniao %s: falha inesperada no resumo", rid)

        avaliadas = 0 if reuniao else await avaliar_pendentes(conn, inicio)

        log.info(
            "passada concluida: %d ok, %d com falha inesperada; status %s; "
            "%d scorecard(s)",
            ok, falhas, contagem or "{}", avaliadas,
        )
        return 1 if (ids and ok == 0) else 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Coleta transcrições do Google Meet")
    p.add_argument("--so-listar", action="store_true",
                   help="mostra o que seria olhado, sem chamar o Google")
    p.add_argument("--reuniao", type=UUID,
                   help="uma reunião só (reunioes.id), como o botão da tela")
    a = p.parse_args()
    return asyncio.run(executar(so_listar=a.so_listar, reuniao=a.reuniao))


if __name__ == "__main__":
    sys.exit(main())
