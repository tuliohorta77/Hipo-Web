"""
HIPO — Fechamento do dia: telemetria, narrativa por IA e e-mail.

USO
  cd /home/hipo/app/api
  python -m scripts.fechamento_diario              # fecha ONTEM
  python -m scripts.fechamento_diario --dia 2026-08-17
  python -m scripts.fechamento_diario --sem-email  # calcula e grava, não envia
  python -m scripts.fechamento_diario --so-imprime # nem grava, só mostra

POR QUE FECHA ONTEM E NÃO HOJE
  O timer roda de madrugada. "Hoje" às 3h da manhã é um dia com três horas de
  dados. O fechamento sempre olha para o dia anterior completo.

IDEMPOTENTE
  Rodar duas vezes para o mesmo dia recalcula e faz UPSERT na linha daquele
  dia. O e-mail, porém, só sai UMA vez: se `enviado_em` já está preenchido, o
  envio é pulado, a menos que venha --forcar-email. Cron que reexecuta por
  falha transitória não pode significar quatro cópias do relatório na caixa
  de quem lê.

ORDEM DAS OPERAÇÕES
  Métricas → grava → IA → e-mail → marca enviado → retenção. As métricas são
  gravadas ANTES de chamar a IA e o SES de propósito: se a rede cair no meio,
  o número do dia já está salvo e a próxima execução só completa o que faltou.
  A retenção é a última coisa — nunca apagar evento bruto antes de o fechado
  estar no banco.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime, timedelta

import asyncpg

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])  # permite rodar de api/

from config import settings  # noqa: E402
from services import email_ses, ia, relatorio_render  # noqa: E402
from services import telemetria as tel  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("hipo.fechamento")


def ontem() -> date:
    """Data de ontem no fuso da operação, não em UTC."""
    from zoneinfo import ZoneInfo
    agora = datetime.now(ZoneInfo(tel.FUSO_OPERACAO))
    return (agora - timedelta(days=1)).date()


async def gravar(conn, dia: date, metricas: dict) -> None:
    """UPSERT do fechamento. Preserva enviado_em de uma execução anterior."""
    await conn.execute("""
        INSERT INTO relatorios_diarios (dia, metricas, gerado_em, atualizado_em)
        VALUES ($1, $2::jsonb, NOW(), NOW())
        ON CONFLICT (dia) DO UPDATE
        SET metricas = EXCLUDED.metricas, atualizado_em = NOW()
    """, dia, json.dumps(metricas, ensure_ascii=False))


async def gravar_narrativa(conn, dia: date, narrativa: str | None, modelo: str | None) -> None:
    await conn.execute("""
        UPDATE relatorios_diarios
        SET narrativa = $2, narrativa_modelo = $3, atualizado_em = NOW()
        WHERE dia = $1
    """, dia, narrativa, modelo)


async def marcar_enviado(conn, dia: date, para: list[str], erro: str | None) -> None:
    await conn.execute("""
        UPDATE relatorios_diarios
        SET enviado_em = CASE WHEN $3::text IS NULL THEN NOW() ELSE enviado_em END,
            destinatarios = $2,
            erro = $3,
            atualizado_em = NOW()
        WHERE dia = $1
    """, dia, para, erro)


async def ja_enviado(conn, dia: date) -> bool:
    return bool(await conn.fetchval(
        "SELECT enviado_em IS NOT NULL FROM relatorios_diarios WHERE dia = $1", dia
    ))


async def executar(dia: date, enviar_email: bool, forcar_email: bool, so_imprime: bool) -> int:
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        log.info("fechando %s", dia.isoformat())
        metricas = await tel.metricas_do_dia(conn, dia)

        ad, op = metricas["adocao"], metricas["operacao"]
        log.info(
            "adoção: %d ações, %d pessoas, %d erros | operação: %d opp, %d tarefas concluídas",
            ad["acoes"], ad["pessoas_ativas"], ad["erros"],
            op["oportunidades_criadas"], op["tarefas_concluidas"],
        )

        if so_imprime:
            print(json.dumps(metricas, ensure_ascii=False, indent=2))
            return 0

        await gravar(conn, dia, metricas)

        narrativa, modelo = await ia.narrar(metricas)
        if narrativa:
            await gravar_narrativa(conn, dia, narrativa, modelo)
            log.info("narrativa gerada por %s (%d caracteres)", modelo, len(narrativa))

        if enviar_email:
            if await ja_enviado(conn, dia) and not forcar_email:
                log.info("relatório de %s já foi enviado; use --forcar-email para repetir",
                         dia.isoformat())
            else:
                para = email_ses.destinatarios()
                try:
                    email_ses.enviar(
                        assunto=relatorio_render.assunto(metricas),
                        html=relatorio_render.montar_html(metricas, narrativa),
                        texto=relatorio_render.montar_texto(metricas, narrativa),
                        para=para,
                    )
                    await marcar_enviado(conn, dia, para, None)
                except Exception as e:
                    # Registra a falha na própria linha do dia: o erro fica
                    # visível para quem consultar o relatório, não só no
                    # journalctl que ninguém abre.
                    msg = f"{type(e).__name__}: {e}"
                    log.error("envio falhou: %s", msg)
                    await marcar_enviado(conn, dia, para, msg[:500])
                    return 1

        apagados = await tel.aplicar_retencao(conn, settings.TELEMETRIA_RETENCAO_DIAS)
        if apagados:
            log.info("retenção: %d evento(s) com mais de %d dias apagado(s)",
                     apagados, settings.TELEMETRIA_RETENCAO_DIAS)
        return 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Fechamento diário do HIPO")
    p.add_argument("--dia", help="AAAA-MM-DD (padrão: ontem no fuso da operação)")
    p.add_argument("--sem-email", action="store_true", help="calcula e grava, não envia")
    p.add_argument("--forcar-email", action="store_true", help="reenvia mesmo já enviado")
    p.add_argument("--so-imprime", action="store_true", help="imprime o JSON e sai")
    args = p.parse_args()

    try:
        dia = date.fromisoformat(args.dia) if args.dia else ontem()
    except ValueError:
        print(f"ERRO: data inválida: {args.dia}", file=sys.stderr)
        return 1

    if dia > date.today():
        print(f"ERRO: {dia} está no futuro.", file=sys.stderr)
        return 1

    return asyncio.run(executar(
        dia,
        enviar_email=not args.sem_email,
        forcar_email=args.forcar_email,
        so_imprime=args.so_imprime,
    ))


if __name__ == "__main__":
    sys.exit(main())
