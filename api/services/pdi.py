"""
HIPO — Carreira · PDI (plano de desenvolvimento individual): regras puras.

Modelo MISTO (decisão do Tulio, 05/10/2026):
  * o HIPO SUGERE ações a partir do Desempenho (indicador abaixo de 70% da
    meta) e da Universidade (trilha obrigatória atrasada ou vencendo, quiz
    final reprovado mais de uma vez);
  * a GESTÃO confirma (e ajusta) a sugestão, descarta, ou cria uma ação
    do zero;
  * o COLABORADOR marca a ação como feita.

Cada ação tem objetivo, o que fazer, trilha opcional, prazo e situação.
Sugestão não é gravada: é recalculada a cada abertura. Só vira linha em
`pdi_acoes` quando a gestão confirma (status aberta) ou descarta (status
descartada) — a `chave_origem` impede que a mesma sugestão volte.

Sem banco, sem relógio: `hoje` chega por parâmetro.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

STATUS = ("aberta", "concluida", "cancelada", "descartada")
ORIGENS = {"desempenho": "Desempenho", "uc": "Universidade", "gestao": "Gestão"}

# Corte da sugestão de Desempenho: abaixo de 70% é a carinha triste/brava
# do Monitor. Até o 4º dia útil o mês ainda não diz nada: olha o anterior.
CORTE_DESEMPENHO = 0.70
DIA_UTIL_MINIMO = 5
MAX_SUGESTOES_DESEMPENHO = 3
DIAS_PRAZO_UC = 7
QUIZ_TENTATIVAS_SUGESTAO = 2
DIAS_ALERTA = 3

MAX_OBJETIVO = 200
MAX_O_QUE_FAZER = 2000


class AcaoInvalida(ValueError):
    """Recusa com mensagem pronta para a tela."""


# O que fazer, pela tela onde o indicador se mexe. Mesmo mapa da tela de
# Desempenho (web/src/pages/carreira/Desempenho.jsx, ONDE_AGIR).
ONDE_AGIR = {
    "SDR": {
        "agendamentos": "agenda", "reunioes_realizadas": "agenda", "noshow": "agenda",
        "leads": "oportunidades", "tarefas": "tarefas", "contas": "prospeccao",
        "taxa_execucao": "tarefas", "pipeline_gerado": "oportunidades", "nmrr": "oportunidades",
    },
    "EV": {
        "followups": "tarefas", "taxa_execucao": "tarefas", "oportunidades": "tarefas",
        "propostas": "oportunidades", "reunioes_realizadas": "agenda", "vendas": "oportunidades",
        "taxa_conversao": "oportunidades", "nmrr": "oportunidades", "ticket_medio": "oportunidades",
        "em_negociacao": "oportunidades", "pipeline": "oportunidades",
    },
    "EC": {
        "contas_gestao": "parceiros", "reunioes_carteira": "agenda", "parcerias": "parceiros",
        "leads": "oportunidades", "tarefas": "tarefas", "taxa_execucao": "tarefas",
        "vendas": "oportunidades", "mrr": "oportunidades",
    },
}

DICA_DA_TELA = {
    "tarefas": "Em Tarefas, zere a coluna Atrasadas todo dia e mantenha a cadência: toda tarefa concluída com a próxima marcada.",
    "agenda": "Na Agenda, confirme a reunião na véspera e registre o desfecho no mesmo dia.",
    "oportunidades": "Em Oportunidades, revise as abertas: fase em dia, próximo passo com data e proposta enviada.",
    "parceiros": "Em Parceiros, comece a semana pelo Sem contato e marque a reunião de carteira.",
    "prospeccao": "Na Prospecção, puxe empresas novas e comece a cadência no mesmo dia.",
}


@dataclass(frozen=True)
class Sugestao:
    chave: str
    origem: str
    objetivo: str
    o_que_fazer: str
    prazo: date
    trilha_id: str | None = None

    def para_tela(self) -> dict:
        d = asdict(self)
        d["origem_rotulo"] = ORIGENS[self.origem]
        return d


def _pct(valor: float | None) -> str:
    return "—" if valor is None else f"{round(valor * 100)}%"


def fim_do_mes(dia: date) -> date:
    proximo = (dia.replace(day=28) + timedelta(days=4)).replace(day=1)
    return proximo - timedelta(days=1)


def sugestoes_do_desempenho(squad: str, linhas: list[dict], ano: int, mes: int,
                            aberto: bool, hoje: date) -> list[Sugestao]:
    """
    Indicadores COM meta abaixo de 70% (meta de hoje, no mês aberto). Os
    três piores, principais primeiro no empate. Prazo: fim do mês corrente.
    """
    candidatas = [
        l for l in linhas
        if l.get("atingimento") is not None and l["atingimento"] < CORTE_DESEMPENHO
    ]
    candidatas.sort(key=lambda l: (l["atingimento"], 0 if l.get("principal") else 1))
    referencia = "da meta de hoje" if aberto else "da meta do mês"
    saida = []
    for l in candidatas[:MAX_SUGESTOES_DESEMPENHO]:
        tela = ONDE_AGIR.get(squad, {}).get(l["chave"])
        dica = DICA_DA_TELA.get(tela, "Converse com a gestão sobre o que travou este número.")
        saida.append(Sugestao(
            chave=f"desempenho:{ano}-{mes:02d}:{l['chave']}",
            origem="desempenho",
            objetivo=f"{l['rotulo']}: sair de {_pct(l['atingimento'])} e chegar a 100% da meta",
            o_que_fazer=(
                f"Está em {_pct(l['atingimento'])} {referencia} "
                f"({l.get('realizado_txt') or '0'} de {l.get('meta_hoje_txt') or l.get('meta_mes_txt') or '—'}). "
                f"{dica}"
            ),
            prazo=fim_do_mes(hoje),
        ))
    return saida


def sugestoes_da_uc(trilhas_do_manual: list[dict], quizzes_reprovados: list[dict],
                    hoje: date) -> list[Sugestao]:
    """
    `trilhas_do_manual`: o manual do painel da UC (situação, prazo, aulas).
    `quizzes_reprovados`: [{trilha_id, titulo, tentativas, aulas_rever}] de
    trilhas com 2+ tentativas e nenhuma aprovação.
    """
    prazo = hoje + timedelta(days=DIAS_PRAZO_UC)
    saida = []
    for t in trilhas_do_manual:
        cod = t["situacao"]["codigo"]
        if cod not in ("atrasada", "vence_logo"):
            continue
        dias = t["situacao"].get("dias_restantes")
        quando = (f"atrasada há {abs(dias)} dia(s)" if cod == "atrasada"
                  else f"vence em {dias} dia(s)")
        falta_quiz = (t.get("quiz") or {}).get("liberado") and not (t.get("quiz") or {}).get("aprovado")
        saida.append(Sugestao(
            chave=f"uc:trilha:{t['id']}",
            origem="uc",
            objetivo=f"Concluir a trilha {t['titulo']}",
            o_que_fazer=(
                f"Obrigatória da função, {quando}: {t['aulas_concluidas']} de {t['aulas_total']} aulas"
                + ("; falta o quiz final." if falta_quiz else ".")
                + " Reserve um horário fixo na agenda para estudar até o prazo."
            ),
            prazo=prazo,
            trilha_id=str(t["id"]),
        ))
    for q in quizzes_reprovados:
        rever = q.get("aulas_rever") or []
        saida.append(Sugestao(
            chave=f"uc:quiz:{q['trilha_id']}",
            origem="uc",
            objetivo=f"Ser aprovado no quiz final de {q['titulo']}",
            o_que_fazer=(
                f"{q['tentativas']} tentativas sem aprovação."
                + (f" Rever: {', '.join(rever)}." if rever else "")
                + " Revisar junto com a gestão antes da próxima tentativa."
            ),
            prazo=prazo,
            trilha_id=str(q["trilha_id"]),
        ))
    return saida


def filtrar_sugestoes(sugestoes: list[Sugestao], chaves_usadas: set[str]) -> list[Sugestao]:
    """Tira o que já virou ação (ou foi descartado)."""
    return [s for s in sugestoes if s.chave not in chaves_usadas]


def origem_da_chave(chave: str | None) -> str:
    if not chave:
        return "gestao"
    prefixo = chave.split(":", 1)[0]
    if prefixo not in ("desempenho", "uc"):
        raise AcaoInvalida("Sugestão desconhecida.")
    return prefixo


def validar_texto(valor, campo: str, maximo: int) -> str:
    texto = " ".join(str(valor or "").split()) if campo == "objetivo" else str(valor or "").strip()
    if len(texto) < 3:
        raise AcaoInvalida(f"Escreva {'o objetivo' if campo == 'objetivo' else 'o que fazer'}.")
    if len(texto) > maximo:
        raise AcaoInvalida(f"{'Objetivo' if campo == 'objetivo' else 'O que fazer'} acima de {maximo} caracteres.")
    return texto


def validar_prazo(prazo: date | None, hoje: date, novo: bool) -> date:
    if prazo is None:
        raise AcaoInvalida("Defina o prazo.")
    if novo and prazo < hoje:
        raise AcaoInvalida("O prazo não pode estar no passado.")
    if prazo > hoje + timedelta(days=366):
        raise AcaoInvalida("Prazo acima de um ano: quebre em ações menores.")
    return prazo


def situacao(status: str, prazo: date, hoje: date) -> dict:
    """Rótulo da ação para a tela."""
    if status == "concluida":
        return {"codigo": "concluida", "rotulo": "Feita", "dias_restantes": None}
    if status == "cancelada":
        return {"codigo": "cancelada", "rotulo": "Cancelada", "dias_restantes": None}
    dias = (prazo - hoje).days
    if dias < 0:
        return {"codigo": "atrasada", "rotulo": "Atrasada", "dias_restantes": dias}
    if dias <= DIAS_ALERTA:
        return {"codigo": "vence_logo", "rotulo": "Vence logo", "dias_restantes": dias}
    return {"codigo": "em_dia", "rotulo": "Em dia", "dias_restantes": dias}


def proxima_acao(acoes: list[dict]) -> dict | None:
    """A ação aberta de prazo mais curto: o cartão do topo da tela."""
    abertas = [a for a in acoes if a["status"] == "aberta"]
    if not abertas:
        return None
    return min(abertas, key=lambda a: (a["prazo"], a["criado_em"]))
