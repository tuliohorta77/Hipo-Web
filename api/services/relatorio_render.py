"""
HIPO — Render do e-mail de fechamento (HTML + texto puro).

Função pura: recebe o dicionário de métricas e devolve strings. Sem banco,
sem rede — roda no pytest local do Windows sem Postgres.

POR QUE HTML NA MÃO, COM ESTILO INLINE
Cliente de e-mail não é navegador: Outlook ignora <style> em <head>, Gmail
remove classes CSS. Toda regra visual vai inline no elemento. É feio de
escrever e é o único jeito que chega igual dos dois lados.

A paleta segue os tokens do Manual de Marca (hipo-blue como acento, cinzas
frios para estrutura), traduzidos para hex literal — variável CSS também não
sobrevive à maioria dos clientes.
"""
from __future__ import annotations

from datetime import date, datetime

AZUL = "#2563eb"
TINTA = "#0f172a"
TEXTO = "#334155"
SUAVE = "#64748b"
BORDA = "#e2e8f0"
FUNDO = "#f8fafc"
VERDE = "#059669"
VERMELHO = "#dc2626"
AMBAR = "#b45309"

DIAS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
           "sexta-feira", "sábado", "domingo"]
MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
            "agosto", "setembro", "outubro", "novembro", "dezembro"]


def data_por_extenso(d: date) -> str:
    """>>> data_por_extenso(date(2026, 8, 17))
    'segunda-feira, 17 de agosto de 2026'
    """
    return f"{DIAS_PT[d.weekday()]}, {d.day} de {MESES_PT[d.month - 1]} de {d.year}"


def hora_curta(iso: str | None) -> str:
    """'2026-08-17T14:32:05-03:00' → '14:32'. Entrada inválida vira '—'."""
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except ValueError:
        return "—"


def variacao(atual, anterior) -> str:
    """
    Texto da diferença contra o dia comparável. Devolve '' quando não há base.

    Sem isso o relatório vira uma foto: 12 ações é bom ou ruim? Só a segunda
    foto responde.
    """
    if anterior is None or atual is None:
        return ""
    delta = atual - anterior
    if delta == 0:
        return "igual ao dia anterior"
    sinal = "+" if delta > 0 else ""
    return f"{sinal}{delta} vs. dia anterior"


def _esc(v) -> str:
    """Escape de HTML. Nome com & ou < viraria tag no cliente de e-mail."""
    return (
        str(v)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _kpi(rotulo: str, valor, rodape: str = "", cor: str = TINTA) -> str:
    rodape_html = (
        f'<div style="font-size:11px;color:{SUAVE};margin-top:2px">{_esc(rodape)}</div>'
        if rodape else ""
    )
    return (
        f'<td style="padding:12px 14px;background:{FUNDO};border:1px solid {BORDA};'
        f'border-radius:8px" valign="top">'
        f'<div style="font-size:11px;color:{SUAVE};text-transform:uppercase;'
        f'letter-spacing:.4px">{_esc(rotulo)}</div>'
        f'<div style="font-size:24px;font-weight:700;color:{cor};line-height:1.2;'
        f'margin-top:4px">{_esc(valor)}</div>{rodape_html}</td>'
    )


def _linha_kpis(kpis: list[str]) -> str:
    celulas = f'<td style="width:10px"></td>'.join(kpis)
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="margin-bottom:10px"><tr>{celulas}</tr></table>'
    )


def _titulo(texto: str) -> str:
    return (
        f'<h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.6px;'
        f'color:{SUAVE};margin:26px 0 10px;font-weight:600">{_esc(texto)}</h2>'
    )


def _tabela(colunas: list[str], linhas: list[list[str]], alinhamento: list[str] | None = None) -> str:
    if not linhas:
        return f'<p style="color:{SUAVE};font-size:13px;margin:0 0 8px">Nada no período.</p>'
    al = alinhamento or ["left"] * len(colunas)
    th = "".join(
        f'<th style="text-align:{al[i]};font-size:11px;color:{SUAVE};font-weight:600;'
        f'text-transform:uppercase;letter-spacing:.4px;padding:6px 8px;'
        f'border-bottom:1px solid {BORDA}">{_esc(c)}</th>'
        for i, c in enumerate(colunas)
    )
    trs = []
    for linha in linhas:
        tds = "".join(
            f'<td style="text-align:{al[i]};font-size:13px;color:{TEXTO};padding:7px 8px;'
            f'border-bottom:1px solid {BORDA}">{celula}</td>'
            for i, celula in enumerate(linha)
        )
        trs.append(f"<tr>{tds}</tr>")
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="border-collapse:collapse;margin-bottom:6px">'
        f"<tr>{th}</tr>{''.join(trs)}</table>"
    )


def montar_html(metricas: dict, narrativa: str | None = None) -> str:
    """E-mail completo. `narrativa` ausente simplesmente não desenha a seção."""
    dia = date.fromisoformat(metricas["dia"])
    ad = metricas.get("adocao", {})
    op = metricas.get("operacao", {})
    comp = metricas.get("comparativo", {}) or {}
    tem_base = comp.get("disponivel")

    partes: list[str] = []
    w = partes.append

    w(f'<div style="background:{TINTA};padding:22px 26px">'
      f'<div style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:-.3px">'
      f'HIPO — fechamento do dia</div>'
      f'<div style="font-size:13px;color:#94a3b8;margin-top:3px">'
      f'{_esc(data_por_extenso(dia))}</div></div>')

    w('<div style="padding:22px 26px">')

    if narrativa:
        blocos = "".join(
            f'<p style="margin:0 0 10px;font-size:14px;line-height:1.6;color:{TEXTO}">'
            f'{_esc(p.strip())}</p>'
            for p in narrativa.split("\n") if p.strip()
        )
        w(f'<div style="border-left:3px solid {AZUL};background:{FUNDO};'
          f'padding:14px 16px;border-radius:0 8px 8px 0;margin-bottom:8px">{blocos}'
          f'<div style="font-size:11px;color:{SUAVE};margin-top:8px">'
          f'Leitura gerada por IA sobre os números abaixo. Os números vêm do banco.'
          f'</div></div>')

    w(_titulo("Uso do sistema"))
    w(_linha_kpis([
        _kpi("Ações", ad.get("acoes", 0),
             variacao(ad.get("acoes"), comp.get("acoes")) if tem_base else ""),
        _kpi("Pessoas ativas", ad.get("pessoas_ativas", 0),
             variacao(ad.get("pessoas_ativas"), comp.get("pessoas_ativas")) if tem_base else ""),
        _kpi("Erros", ad.get("erros", 0),
             f"{ad.get('taxa_erro_pct')}% das ações" if ad.get("taxa_erro_pct") is not None else "",
             VERMELHO if (ad.get("erros") or 0) else TINTA),
        _kpi("Latência p95", f"{ad.get('latencia_p95_ms', 0)} ms",
             f"média {ad.get('latencia_media_ms', 0)} ms"),
    ]))

    w(_titulo("Por colaborador"))
    w(_tabela(
        ["Pessoa", "Cargo", "Ações", "Telas", "Entrada", "Saída"],
        [[
            _esc(p["nome"]), _esc(p["cargo"] or "—"), str(p["acoes"]), str(p["telas"]),
            hora_curta(p.get("primeira")), hora_curta(p.get("ultima")),
        ] for p in ad.get("por_pessoa", [])],
        ["left", "left", "right", "right", "right", "right"],
    ))

    ausentes = ad.get("sem_acesso_hoje", [])
    if ausentes:
        nomes = ", ".join(f'{_esc(a["nome"])} ({_esc(a["cargo"] or "sem cargo")})' for a in ausentes)
        w(f'<p style="font-size:13px;color:{AMBAR};background:#fffbeb;border:1px solid #fde68a;'
          f'padding:10px 12px;border-radius:8px;margin:4px 0 0">'
          f'<strong>Não acessaram hoje:</strong> {nomes}</p>')

    w(_titulo("Operação"))
    w(_linha_kpis([
        _kpi("Oportunidades criadas", op.get("oportunidades_criadas", 0),
             variacao(op.get("oportunidades_criadas"), comp.get("oportunidades_criadas")) if tem_base else ""),
        _kpi("Mudanças de fase", op.get("mudancas_de_fase", 0)),
        _kpi("Conquistadas", op.get("conquistadas", 0), "", VERDE),
        _kpi("Perdidas", op.get("perdidas", 0), "", VERMELHO if op.get("perdidas") else TINTA),
    ]))
    w(_linha_kpis([
        _kpi("Tarefas concluídas", op.get("tarefas_concluidas", 0),
             variacao(op.get("tarefas_concluidas"), comp.get("tarefas_concluidas")) if tem_base else ""),
        _kpi("Tarefas em atraso", op.get("tarefas_em_atraso", 0), "",
             AMBAR if op.get("tarefas_em_atraso") else TINTA),
        _kpi("Contas criadas", op.get("contas_criadas", 0)),
        _kpi("Carteira de parceiros", op.get("carteira_parceiros", 0),
             f"{op.get('parceiros_sem_ec', 0)} sem EC"),
    ]))

    w(_titulo("Telas mais usadas"))
    w(_tabela(
        ["Rota", "Método", "Ações", "Média"],
        [[
            f'<code style="font-size:12px;color:{TINTA}">{_esc(r["rota"])}</code>',
            _esc(r["metodo"]), str(r["acoes"]), f'{r["media_ms"]} ms',
        ] for r in ad.get("rotas_mais_usadas", [])[:10]],
        ["left", "left", "right", "right"],
    ))

    erros = ad.get("erros_por_rota", [])
    if erros:
        w(_titulo("Erros do dia"))
        w(_tabela(
            ["Rota", "Método", "Status", "Ocorrências"],
            [[
                f'<code style="font-size:12px;color:{TINTA}">{_esc(e["rota"])}</code>',
                _esc(e["metodo"]),
                f'<span style="color:{VERMELHO};font-weight:600">{e["status"]}</span>',
                str(e["ocorrencias"]),
            ] for e in erros],
            ["left", "left", "right", "right"],
        ))

    w(f'<p style="font-size:11px;color:{SUAVE};margin-top:26px;padding-top:14px;'
      f'border-top:1px solid {BORDA}">HIPO · gerado automaticamente no fechamento '
      f'do dia · fuso {_esc(metricas.get("fuso", "America/Sao_Paulo"))}</p>')
    w("</div>")

    corpo = "".join(partes)
    return (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>HIPO — fechamento do dia</title></head>"
        f'<body style="margin:0;padding:0;background:#eef2f7;'
        f'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="background:#eef2f7;padding:20px 10px"><tr><td align="center">'
        f'<table width="680" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="max-width:680px;background:#ffffff;border-radius:12px;overflow:hidden;'
        f'border:1px solid {BORDA}"><tr><td>{corpo}</td></tr></table>'
        f"</td></tr></table></body></html>"
    )


def montar_texto(metricas: dict, narrativa: str | None = None) -> str:
    """
    Versão texto puro do mesmo conteúdo.

    Não é enfeite: e-mail só-HTML pontua pior em filtro de spam, e cliente com
    imagens/HTML bloqueado mostra esta parte. Vai como alternativa no mesmo
    envio (multipart/alternative).
    """
    dia = date.fromisoformat(metricas["dia"])
    ad = metricas.get("adocao", {})
    op = metricas.get("operacao", {})
    linhas = [
        "HIPO — FECHAMENTO DO DIA",
        data_por_extenso(dia),
        "",
    ]
    if narrativa:
        linhas += [narrativa.strip(), ""]

    linhas += [
        "USO DO SISTEMA",
        f"  Ações: {ad.get('acoes', 0)}",
        f"  Pessoas ativas: {ad.get('pessoas_ativas', 0)}",
        f"  Erros: {ad.get('erros', 0)} ({ad.get('taxa_erro_pct')}%)",
        f"  Latência p95: {ad.get('latencia_p95_ms', 0)} ms",
        "",
        "POR COLABORADOR",
    ]
    for p in ad.get("por_pessoa", []) or [None]:
        if p is None:
            linhas.append("  (ninguém usou o sistema hoje)")
            break
        linhas.append(
            f"  {p['nome']} ({p['cargo'] or 'sem cargo'}): {p['acoes']} ações, "
            f"{p['telas']} telas, {hora_curta(p.get('primeira'))}–{hora_curta(p.get('ultima'))}"
        )

    ausentes = ad.get("sem_acesso_hoje", [])
    if ausentes:
        linhas += ["", "NÃO ACESSARAM HOJE"]
        linhas += [f"  {a['nome']} ({a['cargo'] or 'sem cargo'})" for a in ausentes]

    linhas += [
        "",
        "OPERAÇÃO",
        f"  Oportunidades criadas: {op.get('oportunidades_criadas', 0)}",
        f"  Mudanças de fase: {op.get('mudancas_de_fase', 0)}",
        f"  Conquistadas: {op.get('conquistadas', 0)} | Perdidas: {op.get('perdidas', 0)}",
        f"  Tarefas concluídas: {op.get('tarefas_concluidas', 0)} | "
        f"em atraso: {op.get('tarefas_em_atraso', 0)}",
        f"  Contas criadas: {op.get('contas_criadas', 0)}",
        f"  Carteira de parceiros: {op.get('carteira_parceiros', 0)} "
        f"({op.get('parceiros_sem_ec', 0)} sem EC)",
        "",
        "HIPO · gerado automaticamente no fechamento do dia",
    ]
    return "\n".join(linhas)


def assunto(metricas: dict) -> str:
    """
    Assunto com o resumo do dia: quem lê no celular decide se abre por aqui.

    >>> assunto({"dia": "2026-08-17", "adocao": {"pessoas_ativas": 4},
    ...          "operacao": {"oportunidades_criadas": 2}})
    'HIPO 17/08 — 4 pessoas, 2 oportunidades'
    """
    dia = date.fromisoformat(metricas["dia"])
    pessoas = metricas.get("adocao", {}).get("pessoas_ativas", 0)
    opps = metricas.get("operacao", {}).get("oportunidades_criadas", 0)
    return (
        f"HIPO {dia.strftime('%d/%m')} — {pessoas} "
        f"{'pessoa' if pessoas == 1 else 'pessoas'}, {opps} "
        f"{'oportunidade' if opps == 1 else 'oportunidades'}"
    )
