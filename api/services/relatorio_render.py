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
from zoneinfo import ZoneInfo

_FUSO = ZoneInfo("America/Sao_Paulo")

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
    """
    ISO com fuso -> 'HH:MM' no horário de Brasília. Entrada inválida vira '—'.

    CONVERTE ANTES DE FORMATAR. O asyncpg devolve timestamptz em UTC, e o
    `.isoformat()` grava '2026-09-15T11:46:00+00:00' no JSON. Formatar direto
    mostrava a equipe entrando às 11h e saindo às 21h -- três horas à frente
    -- no e-mail de 15/09. Datetime sem fuso é tratado como já local.

    >>> hora_curta("2026-09-15T11:46:00+00:00")
    '08:46'
    """
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return "—"
    if dt.tzinfo is not None:
        dt = dt.astimezone(_FUSO)
    return dt.strftime("%H:%M")


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


# ── Conteúdo do CRM ─────────────────────────────────────────────────────
#
# Estes blocos são o motivo de o e-mail existir depois de 31/08. A telemetria
# diz quem clicou; isto diz o que está aberto e cobrando ação. Cada linha
# carrega o MOTIVO junto — sem ele o leitor teria de adivinhar por que aquela
# oportunidade está na lista, e uma lista que precisa ser decifrada não é lida.

def _dinheiro(v) -> str:
    """R$ 4.200 — sem centavos, que a esta distância só fazem ruído."""
    if v is None:
        return "—"
    return "R$ " + f"{float(v):,.0f}".replace(",", ".")


def _motivos(ms: list[str]) -> str:
    return _esc(" · ".join(ms)) if ms else "—"


def _e_mais(n: int, oque: str) -> str:
    if not n:
        return ""
    return (f'<p style="font-size:12px;color:{SUAVE};margin:6px 0 0">'
            f'e mais {n} {oque}.</p>')


def _bloco_conteudo(cont: dict) -> list[str]:
    """As quatro listas. Bloco vazio não é desenhado — nem como 'nenhum'."""
    from services.oportunidade import ROTULOS_FASE

    saida: list[str] = []
    w = saida.append

    acao = cont.get("precisa_de_acao", [])
    if acao:
        w(_titulo("Precisa de ação"))
        w(_tabela(
            ["Oportunidade", "Conta", "Fase", "Valor", "Por quê"],
            [[
                f'<strong>{_esc(o["numero"])}</strong>', _esc(o["conta"]),
                _esc(ROTULOS_FASE.get(o["fase"], o["fase"])),
                _dinheiro(o["valor"]),
                f'<span style="color:{VERMELHO}">{_motivos(o["motivos"])}</span>',
            ] for o in acao],
            ["left", "left", "left", "right", "left"],
        ))
        w(_e_mais(cont.get("precisa_de_acao_mais", 0), "com pendência"))

    fechar = cont.get("perto_de_fechar", [])
    if fechar:
        w(_titulo("Perto de fechar"))
        w(_tabela(
            ["Oportunidade", "Conta", "Fase", "Valor", "Por quê"],
            [[
                f'<strong>{_esc(o["numero"])}</strong>', _esc(o["conta"]),
                _esc(ROTULOS_FASE.get(o["fase"], o["fase"])),
                _dinheiro(o["valor"]),
                f'<span style="color:{VERDE}">{_motivos(o["motivos"])}</span>',
            ] for o in fechar],
            ["left", "left", "left", "right", "left"],
        ))
        w(_e_mais(cont.get("perto_de_fechar_mais", 0), "maduras"))

    parceiros = cont.get("parceiros_para_acionar", [])
    if parceiros:
        w(_titulo("Parceiros para acionar"))
        w(_tabela(
            ["Parceiro", "Situação", "Indicações", "Fechadas", "Sem indicar"],
            [[
                _esc(p["conta"]),
                _esc(p["situacao"].replace("_", " ")),
                str(p["indicacoes"]), str(p["conquistadas"]),
                f'{p["dias_sem_indicar"]} dias',
            ] for p in parceiros],
            ["left", "left", "right", "right", "right"],
        ))
        w(_e_mais(cont.get("parceiros_para_acionar_mais", 0), "esfriando"))

    atrasadas = cont.get("tarefas_atrasadas", [])
    if atrasadas:
        total = cont.get("tarefas_atrasadas_total", len(atrasadas))
        w(_titulo(f"Tarefas atrasadas ({total})"))
        w(_tabela(
            ["Tarefa", "Responsável", "Onde", "Atraso"],
            [[
                _esc(t_["titulo"]), _esc(t_["responsavel"]), _esc(t_["alvo"]),
                f'<span style="color:{VERMELHO}">{t_["dias_atraso"]} dias</span>',
            ] for t_ in atrasadas],
            ["left", "left", "left", "right"],
        ))
        w(_e_mais(max(0, total - len(atrasadas)), "atrasadas"))

    return saida


# ── Atividade da equipe ─────────────────────────────────────────────────
#
# A partir de 16/09 o e-mail mede o que foi LANCADO, nao o que foi clicado.
# "Acoes" (toda request) saiu da tela: 89% eram leitura, e o numero fazia
# quem navega muito parecer quem produz muito. O dado bruto continua em
# `adocao` para quem consultar a API.

_CALOR = ("#eff6ff", "#dbeafe", "#bfdbfe", "#93c5fd")

_COR_SITUACAO = {
    "realizada": VERDE,
    "no_show": VERMELHO,
    "cancelada": SUAVE,
    "pendente": AMBAR,
    "agendada": TEXTO,
}


def _celula_calor(n: int, maximo: int) -> str:
    """Celula da tabela usuario x hora. Zero fica apagado; o resto ganha tom."""
    base = ("text-align:center;font-size:11px;padding:6px 2px;"
            f"border-bottom:1px solid {BORDA};")
    if not n:
        return f'<td style="{base}color:#cbd5e1">·</td>'
    nivel = min(len(_CALOR) - 1, (n * len(_CALOR) - 1) // max(maximo, 1))
    return (f'<td style="{base}background:{_CALOR[nivel]};color:{TINTA};'
            f'font-weight:600">{n}</td>')


def _nome_com_cargo(nome, cargo) -> str:
    cargo_html = (f'<div style="font-size:10px;color:{SUAVE}">{_esc(cargo)}</div>'
                  if cargo else "")
    return f'<div style="font-size:12px;color:{TINTA}">{_esc(nome)}</div>{cargo_html}'


def _tabela_usuario_hora(at: dict) -> str:
    horas = at.get("horas") or []
    pessoas = at.get("por_pessoa") or []
    if not pessoas:
        return f'<p style="color:{SUAVE};font-size:13px;margin:0 0 8px">Ninguém entrou no sistema.</p>'

    maximo = max([n for p in pessoas for n in p["por_hora"]] + [1])
    th_base = (f"font-size:10px;color:{SUAVE};font-weight:600;text-transform:uppercase;"
               f"padding:6px 2px;border-bottom:1px solid {BORDA}")
    cab = (f'<th style="{th_base};text-align:left;padding-left:6px">Pessoa</th>'
           f'<th style="{th_base};text-align:left">Expediente</th>'
           + "".join(f'<th style="{th_base};text-align:center">{h}h</th>' for h in horas)
           + f'<th style="{th_base};text-align:right">Total</th>'
           + f'<th style="{th_base};text-align:right" title="Oportunidades trabalhadas">Opp.</th>'
           + f'<th style="{th_base};text-align:right;padding-right:6px">1ª vez</th>')

    td = f"padding:6px 2px;border-bottom:1px solid {BORDA};"
    trs = []
    for p in pessoas:
        expediente = (f'{_esc(p.get("entrada") or "—")}–{_esc(p.get("saida") or "—")}')
        trs.append(
            "<tr>"
            f'<td style="{td}padding-left:6px">{_nome_com_cargo(p["nome"], p.get("cargo"))}</td>'
            f'<td style="{td}font-size:11px;color:{TEXTO};white-space:nowrap">{expediente}</td>'
            + "".join(_celula_calor(n, maximo) for n in p["por_hora"])
            + f'<td style="{td}text-align:right;font-size:13px;'
              f'font-weight:700;color:{TINTA}">{p["total"]}</td>'
            + f'<td style="{td}text-align:right;font-size:13px;color:{TINTA}">'
              f'{p.get("oportunidades_trabalhadas", 0)}</td>'
            + f'<td style="{td}text-align:right;padding-right:6px;font-size:13px;color:{AZUL}">'
              f'{p.get("oportunidades_primeira_vez", 0)}</td>'
            "</tr>"
        )

    totais = at.get("total_por_hora") or [0] * len(horas)
    tf = f"padding:7px 2px;border-top:2px solid {BORDA};font-size:11px;font-weight:700;color:{TINTA};"
    trs.append(
        "<tr>"
        f'<td style="{tf}padding-left:6px" colspan="2">Equipe</td>'
        + "".join(f'<td style="{tf}text-align:center">{n or ""}</td>' for n in totais)
        + f'<td style="{tf}text-align:right;font-size:13px">{at.get("total", 0)}</td>'
        + f'<td style="{tf}text-align:right;font-size:13px">{at.get("oportunidades_trabalhadas", 0)}</td>'
        + f'<td style="{tf}text-align:right;padding-right:6px;font-size:13px;color:{AZUL}">'
          f'{at.get("oportunidades_primeira_vez", 0)}</td>'
        "</tr>"
    )
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="border-collapse:collapse;margin-bottom:6px"><tr>{cab}</tr>{"".join(trs)}</table>'
        f'<p style="font-size:11px;color:{SUAVE};margin:4px 0 0">Atividade = registro criado, '
        f'alterado ou concluído com sucesso. Consultas e navegação não contam. '
        f'Opp. = oportunidades com tarefa concluída no dia; 1ª vez = a primeira '
        f'tarefa concluída da história dela. Na linha Equipe, oportunidade '
        f'trabalhada por duas pessoas conta uma vez. Horário de Brasília.</p>'
    )


def _bloco_equipe(metricas: dict) -> list[str]:
    at = metricas.get("atividades")
    if not at:
        return []
    ad = metricas.get("adocao", {}) or {}
    re_ = metricas.get("reunioes", {}) or {}
    comp = metricas.get("comparativo", {}) or {}
    tem_base = comp.get("disponivel")

    saida: list[str] = []
    w = saida.append
    w(_titulo("Atividade da equipe"))

    taxa = re_.get("taxa_realizacao_pct")
    w(_linha_kpis([
        _kpi("Atividades", at.get("total", 0),
             variacao(at.get("total"), comp.get("atividades")) if tem_base else ""),
        _kpi("Pessoas ativas", ad.get("pessoas_ativas", 0),
             variacao(ad.get("pessoas_ativas"), comp.get("pessoas_ativas")) if tem_base else ""),
        _kpi("Reuniões realizadas", f'{re_.get("realizadas", 0)}/{re_.get("total", 0)}',
             f"{str(taxa).replace('.', ',')}% das que tiveram desfecho" if taxa is not None else "",
             VERDE if re_.get("realizadas") else TINTA),
        _kpi("No-show", re_.get("no_show", 0),
             f'{re_.get("pendentes", 0)} sem desfecho' if re_.get("pendentes") else "",
             VERMELHO if re_.get("no_show") else TINTA),
    ]))
    w(_linha_kpis([
        _kpi("Oportunidades trabalhadas", at.get("oportunidades_trabalhadas", 0),
             variacao(at.get("oportunidades_trabalhadas"),
                      comp.get("oportunidades_trabalhadas")) if tem_base else "",),
        _kpi("Trabalhadas pela 1ª vez", at.get("oportunidades_primeira_vez", 0),
             "primeira tarefa concluída da oportunidade", AZUL),
    ]))

    w(_tabela_usuario_hora(at))

    if not ad.get("disponivel", True):
        w(f'<p style="font-size:13px;color:{TINTA};background:#f1f5f9;'
          f'border:1px solid #e2e8f0;padding:10px 12px;border-radius:8px;'
          f'margin:8px 0 0"><strong>Sem telemetria neste dia.</strong> '
          f'A captura de uso ainda não estava ativa, então não dá para dizer '
          f'quem acessou nem o que foi lançado.</p>')

    ausentes = ad.get("sem_acesso_hoje", [])
    if ausentes:
        nomes = ", ".join(f'{_esc(a["nome"])} ({_esc(a["cargo"] or "sem cargo")})' for a in ausentes)
        w(f'<p style="font-size:13px;color:{AMBAR};background:#fffbeb;border:1px solid #fde68a;'
          f'padding:10px 12px;border-radius:8px;margin:8px 0 0">'
          f'<strong>Não acessaram:</strong> {nomes}</p>')
    return saida


def _bloco_reunioes(re_: dict | None) -> list[str]:
    if re_ is None:
        return []
    saida: list[str] = []
    w = saida.append
    w(_titulo("Reuniões do dia"))

    if not re_.get("total"):
        w(f'<p style="color:{SUAVE};font-size:13px;margin:0 0 8px">Nenhuma reunião marcada para o dia.</p>')
    else:
        w(_tabela(
            ["Anfitrião", "Total", "Realizadas", "Canceladas", "No-show", "Sem desfecho"],
            [[
                _nome_com_cargo(p["nome"], p.get("cargo")), str(p["total"]),
                f'<span style="color:{VERDE};font-weight:600">{p["realizadas"]}</span>',
                str(p["canceladas"]),
                (f'<span style="color:{VERMELHO};font-weight:600">{p["no_show"]}</span>'
                 if p["no_show"] else "0"),
                (f'<span style="color:{AMBAR};font-weight:600">{p["pendentes"]}</span>'
                 if p["pendentes"] else "0"),
            ] for p in re_.get("por_anfitriao", [])],
            ["left", "right", "right", "right", "right", "right"],
        ))
        w(_tabela(
            ["Hora", "Anfitrião", "Empresa", "Tipo", "Marcada por", "Situação"],
            [[
                _esc(i["hora"]), _esc(i["anfitriao"]), _esc(i["empresa"]),
                _esc(i["tipo"]), _esc(i["agendado_por"]),
                f'<span style="color:{_COR_SITUACAO.get(i["situacao"], TEXTO)};'
                f'font-weight:600">{_esc(i["situacao_rotulo"])}</span>',
            ] for i in re_.get("itens", [])],
            ["left", "left", "left", "left", "left", "left"],
        ))
        if re_.get("pendentes"):
            w(f'<p style="font-size:12px;color:{AMBAR};margin:4px 0 0">'
              f'{re_["pendentes"]} reunião(ões) já terminaram e ninguém registrou o que '
              f'aconteceu. Ficam fora da taxa de realização até alguém registrar.</p>')

    ag = re_.get("agendamentos_por_pessoa") or []
    if ag:
        lista = " · ".join(f'{_esc(a["nome"])} <strong>{a["qtd"]}</strong>' for a in ag)
        w(f'<p style="font-size:13px;color:{TEXTO};margin:10px 0 0">'
          f'<strong>Agendamentos marcados no dia ({re_.get("agendamentos_total", 0)}):</strong> '
          f'{lista}</p>')
    return saida


def _bloco_detalhe(at: dict | None) -> list[str]:
    if not at:
        return []
    pessoas = at.get("por_pessoa") or []
    if not pessoas:
        return []
    saida: list[str] = []
    w = saida.append
    w(_titulo("O que cada um lançou"))
    for p in pessoas:
        cargo = f' <span style="color:{SUAVE};font-weight:400">· {_esc(p["cargo"])}</span>' if p.get("cargo") else ""
        w(f'<div style="font-size:14px;font-weight:700;color:{TINTA};margin:16px 0 6px">'
          f'{_esc(p["nome"])}{cargo}'
          f'<span style="float:right;font-size:13px;color:{AZUL}">{p["total"]} '
          f'{"atividade" if p["total"] == 1 else "atividades"}</span></div>')
        if not p["por_tipo"]:
            w(f'<p style="font-size:13px;color:{AMBAR};margin:0 0 6px">'
              f'Entrou no sistema ({_esc(p.get("entrada") or "—")}–{_esc(p.get("saida") or "—")}) '
              f'e não lançou nada.</p>')
            continue
        linhas = []
        grupo_atual = None
        for t_ in p["por_tipo"]:
            grupo = t_["grupo"] if t_["grupo"] != grupo_atual else ""
            grupo_atual = t_["grupo"]
            linhas.append([
                f'<span style="color:{SUAVE};font-size:12px">{_esc(grupo)}</span>',
                _esc(t_["tipo"]),
                f'<strong>{t_["qtd"]}</strong>',
            ])
        w(_tabela(["Área", "Tipo", "Qtd"], linhas, ["left", "left", "right"]))
    return saida


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

    equipe = _bloco_equipe(metricas)
    if equipe:
        w("".join(equipe))
        w("".join(_bloco_reunioes(metricas.get("reunioes"))))
        w("".join(_bloco_detalhe(metricas.get("atividades"))))
    else:
        # Fechamento gravado antes de 16/09 (sem `atividades`), reprocessado
        # para reenvio: mostra a tabela antiga em vez de um e-mail sem equipe.
        w(_titulo("Por colaborador"))
        w(_tabela(
            ["Pessoa", "Cargo", "Ações", "Telas", "Entrada", "Saída"],
            [[
                _esc(p["nome"]), _esc(p["cargo"] or "—"), str(p["acoes"]), str(p["telas"]),
                hora_curta(p.get("primeira")), hora_curta(p.get("ultima")),
            ] for p in ad.get("por_pessoa", [])],
            ["left", "left", "right", "right", "right", "right"],
        ))

    w("".join(_bloco_conteudo(metricas.get("conteudo", {}) or {})))

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

    # "Uso do sistema" (ações brutas, erros, latência) saiu em 16/09, e as
    # tabelas de rota já tinham saído em 31/08: é diagnóstico de
    # desenvolvedor. Os dados seguem em `adocao` para quem consultar a API.

    w(f'<p style="font-size:11px;color:{SUAVE};margin-top:26px;padding-top:14px;'
      f'border-top:1px solid {BORDA}">HIPO · gerado automaticamente no fechamento '
      f'do dia · horários de Brasília ({_esc(metricas.get("fuso", "America/Sao_Paulo"))})</p>')
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


def _texto_equipe(metricas: dict) -> list[str]:
    at = metricas.get("atividades")
    if not at:
        return []
    ad = metricas.get("adocao", {}) or {}
    linhas = [f"ATIVIDADE DA EQUIPE ({at.get('total', 0)} atividades, "
              f"{ad.get('pessoas_ativas', 0)} pessoas)"]
    horas = at.get("horas") or []
    pessoas = at.get("por_pessoa") or []
    if not pessoas:
        linhas += ["  (ninguém entrou no sistema)", ""]
        return linhas
    largura = max(len(p["nome"] or "") for p in pessoas)
    largura = max(largura, len("Equipe"))
    linhas.append(f"  Oportunidades trabalhadas: {at.get('oportunidades_trabalhadas', 0)} "
                  f"(pela 1ª vez: {at.get('oportunidades_primeira_vez', 0)})")
    cab = " " * (largura + 2) + "".join(f"{h:>4}" for h in horas) + "  Total  Opp  1ªvez"
    linhas.append(cab)
    for p in pessoas:
        celulas = "".join(f"{(n or '.'):>4}" for n in p["por_hora"])
        linhas.append(f"  {p['nome']:<{largura}}{celulas}  {p['total']:>5}"
                      f"  {p.get('oportunidades_trabalhadas', 0):>3}"
                      f"  {p.get('oportunidades_primeira_vez', 0):>5}"
                      f"   ({p.get('entrada') or '—'}–{p.get('saida') or '—'})")
    totais = at.get("total_por_hora") or []
    linhas.append(f"  {'Equipe':<{largura}}" + "".join(f"{(n or ''):>4}" for n in totais)
                  + f"  {at.get('total', 0):>5}"
                  + f"  {at.get('oportunidades_trabalhadas', 0):>3}"
                  + f"  {at.get('oportunidades_primeira_vez', 0):>5}")
    linhas.append("  Atividade = registro criado, alterado ou concluído. Horário de Brasília.")

    if not ad.get("disponivel", True):
        linhas += ["  Sem telemetria neste dia: a captura de uso não estava ativa."]
    ausentes = ad.get("sem_acesso_hoje", [])
    if ausentes:
        linhas += ["", "NÃO ACESSARAM"]
        linhas += [f"  {a['nome']} ({a['cargo'] or 'sem cargo'})" for a in ausentes]
    linhas.append("")
    return linhas


def _texto_reunioes(re_: dict | None) -> list[str]:
    if re_ is None:
        return []
    linhas = [f"REUNIÕES DO DIA ({re_.get('total', 0)} no total: "
              f"realizadas {re_.get('realizadas', 0)}, canceladas {re_.get('canceladas', 0)}, "
              f"no-show {re_.get('no_show', 0)}, sem desfecho {re_.get('pendentes', 0)})"]
    if not re_.get("total"):
        linhas.append("  Nenhuma reunião marcada para o dia.")
    for p in re_.get("por_anfitriao", []):
        linhas.append(f"  {p['nome']}: total {p['total']} · realizadas {p['realizadas']} · "
                      f"canceladas {p['canceladas']} · no-show {p['no_show']} · "
                      f"sem desfecho {p['pendentes']}")
    if re_.get("itens"):
        linhas.append("")
    for i in re_.get("itens", []):
        linhas.append(f"  {i['hora']}  {i['anfitriao']} · {i['empresa']} · {i['tipo']} · "
                      f"marcada por {i['agendado_por']} · {i['situacao_rotulo'].upper()}")
    ag = re_.get("agendamentos_por_pessoa") or []
    if ag:
        linhas.append("")
        linhas.append(f"  Agendamentos marcados no dia ({re_.get('agendamentos_total', 0)}): "
                      + " · ".join(f"{a['nome']} {a['qtd']}" for a in ag))
    linhas.append("")
    return linhas


def _texto_detalhe(at: dict | None) -> list[str]:
    if not at or not at.get("por_pessoa"):
        return []
    linhas = ["O QUE CADA UM LANÇOU"]
    for p in at["por_pessoa"]:
        linhas.append(f"  {p['nome']} ({p.get('cargo') or 'sem cargo'}): {p['total']} "
                      f"{'atividade' if p['total'] == 1 else 'atividades'}")
        if not p["por_tipo"]:
            linhas.append("      entrou no sistema e não lançou nada")
        for t_ in p["por_tipo"]:
            linhas.append(f"      {t_['qtd']:>4}  {t_['grupo']} · {t_['tipo']}")
    linhas.append("")
    return linhas


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

    equipe = _texto_equipe(metricas)
    if equipe:
        linhas += equipe
        linhas += _texto_reunioes(metricas.get("reunioes"))
        linhas += _texto_detalhe(metricas.get("atividades"))
    else:
        linhas += ["POR COLABORADOR"]
        for p in ad.get("por_pessoa", []) or [None]:
            if p is None:
                linhas.append(
                    "  (sem telemetria neste dia)"
                    if not ad.get("disponivel", True)
                    else "  (ninguém usou o sistema hoje)"
                )
                break
            linhas.append(
                f"  {p['nome']} ({p['cargo'] or 'sem cargo'}): {p['acoes']} ações, "
                f"{p['telas']} telas, {hora_curta(p.get('primeira'))}–{hora_curta(p.get('ultima'))}"
            )
        linhas.append("")

    cont = metricas.get("conteudo", {}) or {}

    def _dinheiro_txt(v):
        return "—" if v is None else "R$ " + f"{float(v):,.0f}".replace(",", ".")

    if cont.get("precisa_de_acao"):
        linhas += ["PRECISA DE AÇÃO"]
        for o in cont["precisa_de_acao"]:
            linhas.append(
                f"  {o['numero']} · {o['conta']} · {_dinheiro_txt(o['valor'])}"
            )
            linhas.append(f"      {' · '.join(o['motivos'])}")
        if cont.get("precisa_de_acao_mais"):
            linhas.append(f"  e mais {cont['precisa_de_acao_mais']} com pendência.")
        linhas.append("")

    if cont.get("perto_de_fechar"):
        linhas += ["PERTO DE FECHAR"]
        for o in cont["perto_de_fechar"]:
            linhas.append(
                f"  {o['numero']} · {o['conta']} · {_dinheiro_txt(o['valor'])}"
            )
            linhas.append(f"      {' · '.join(o['motivos'])}")
        if cont.get("perto_de_fechar_mais"):
            linhas.append(f"  e mais {cont['perto_de_fechar_mais']} maduras.")
        linhas.append("")

    if cont.get("parceiros_para_acionar"):
        linhas += ["PARCEIROS PARA ACIONAR"]
        for pa in cont["parceiros_para_acionar"]:
            linhas.append(
                f"  {pa['conta']} ({pa['situacao'].replace('_', ' ')}) · "
                f"{pa['indicacoes']} "
                f"{'indicação' if pa['indicacoes'] == 1 else 'indicações'}, "
                f"{pa['conquistadas']} fechadas · "
                f"{pa['dias_sem_indicar']} dias sem indicar"
            )
        linhas.append("")

    if cont.get("tarefas_atrasadas"):
        total = cont.get("tarefas_atrasadas_total", len(cont["tarefas_atrasadas"]))
        linhas += [f"TAREFAS ATRASADAS ({total})"]
        for ta in cont["tarefas_atrasadas"]:
            linhas.append(
                f"  {ta['titulo']} · {ta['responsavel']} · {ta['alvo']} · "
                f"{ta['dias_atraso']} dias"
            )
        resto = max(0, total - len(cont["tarefas_atrasadas"]))
        if resto:
            linhas.append(f"  e mais {resto} atrasadas.")
        linhas.append("")

    linhas += [
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
        "HIPO · gerado automaticamente no fechamento do dia · horários de Brasília",
    ]
    return "\n".join(linhas)


def assunto(metricas: dict) -> str:
    """
    Assunto com o resumo do dia: quem lê no celular decide se abre por aqui.

    >>> assunto({"dia": "2026-09-15", "adocao": {"pessoas_ativas": 5},
    ...          "atividades": {"total": 181},
    ...          "reunioes": {"total": 6, "realizadas": 4}})
    'HIPO 15/09 — 5 pessoas, 181 atividades, 4/6 reuniões realizadas'
    """
    dia = date.fromisoformat(metricas["dia"])
    pessoas = metricas.get("adocao", {}).get("pessoas_ativas", 0)
    partes = [f"{pessoas} {'pessoa' if pessoas == 1 else 'pessoas'}"]

    at = metricas.get("atividades")
    if at is not None:
        n = at.get("total", 0)
        partes.append(f"{n} {'atividade' if n == 1 else 'atividades'}")
    else:
        opps = metricas.get("operacao", {}).get("oportunidades_criadas", 0)
        partes.append(f"{opps} {'oportunidade' if opps == 1 else 'oportunidades'}")

    re_ = metricas.get("reunioes") or {}
    if re_.get("total"):
        partes.append(f"{re_.get('realizadas', 0)}/{re_['total']} "
                      f"{'reunião realizada' if re_['total'] == 1 else 'reuniões realizadas'}")

    return f"HIPO {dia.strftime('%d/%m')} — " + ", ".join(partes)
