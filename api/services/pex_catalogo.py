"""
Catálogo dos 30 indicadores do PEX (manual oficial v8.01/2026).

Fonte da verdade pra:
  - Faixas de pontuação (fixas)
  - Quais indicadores têm meta numérica editável pelo ADM
  - Mapeamento código <-> coluna do pex_snapshot
  - Metas variáveis por cluster (Integração Contábil, Eventos)

Estrutura:
    PILAR: 'RESULTADO' | 'GESTAO' | 'ENGAJAMENTO'
    pts:   peso máximo do indicador
    tipo:  'PCT_HIGHER_BETTER'  → % maior é melhor (atingimento)
           'PCT_LOWER_BETTER'   → % menor é melhor (Early Churn, Util Desconto, Turnover)
           'VALOR_HIGHER_BETTER'→ valor absoluto, maior é melhor (Reuniões/du, Demo/du)
           'BINARIO'            → Sim/Não (Rem Variável, Instagram)
           'ESCALA_DISCRETA'    → 0/1/2/3 ações (Big3)
    faixas: lista (lim_inf, lim_sup, pts) — limites inclusivos
    meta_editavel: True se ADM informa a meta no painel; False se a meta é universal
    meta_por_cluster: dict cluster→meta (sobrepõe meta_editavel)
"""
from decimal import Decimal

PILAR_RESULTADO = "RESULTADO"
PILAR_GESTAO = "GESTAO"
PILAR_ENGAJAMENTO = "ENGAJAMENTO"

# Clusters oficiais Omie
CLUSTERS = ["INCUBADORA", "AVANCA_PLUS", "BASE", "OURO", "PLATINA", "PRIME", "BLACK"]

# Faixa especial: regras NMRR (proporcional entre 85-100%)
NMRR_PROPORCIONAL = "PROPORCIONAL"

CATALOGO = [
    # ─────────── PILAR RESULTADO (17 indicadores, 60 pts) ───────────
    {
        "codigo": "nmrr",
        "pilar": PILAR_RESULTADO,
        "nome": "NMRR",
        "pts": 10,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 84.99, 5), (85, 100, NMRR_PROPORCIONAL)],
        "meta_editavel": True,
        "meta_label": "Meta NMRR (R$)",
        "snapshot_col": "nmrr_meta",
    },
    {
        "codigo": "sow",
        "pilar": PILAR_RESULTADO,
        "nome": "Share of Wallet (SoW)",
        "pts": 3,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 5,
        "faixas": [(0, 3.99, 0), (4, 4.99, 1.5), (5, 100, 3)],
        "meta_editavel": False,  # denominador (apps_ativos) é global do mês
    },
    {
        "codigo": "mapeamento_carteira",
        "pilar": PILAR_RESULTADO,
        "nome": "Mapeamento de carteira",
        "pts": 2,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 60,
        "faixas": [(0, 47.99, 0), (48, 59.99, 1), (60, 100, 2)],
        "meta_editavel": False,
    },
    {
        "codigo": "early_churn",
        "pilar": PILAR_RESULTADO,
        "nome": "Early Churn",
        "pts": 3,
        "tipo": "PCT_LOWER_BETTER",
        "meta_universal_pct": 5.7,
        "faixas": [(0, 5.7, 3), (5.71, 7.1, 1.5), (7.11, 100, 0)],
        "meta_editavel": False,
    },
    {
        "codigo": "utilizacao_desconto",
        "pilar": PILAR_RESULTADO,
        "nome": "Utilização cupom de desconto",
        "pts": 2,
        "tipo": "PCT_LOWER_BETTER",
        "meta_universal_pct": 15,
        "faixas": [(0, 15, 2), (15.01, 19, 1), (19.01, 100, 0)],
        "meta_editavel": False,
    },
    {
        "codigo": "crescimento_40",
        "pilar": PILAR_RESULTADO,
        "nome": "Crescimento de 40%",
        "pts": 5,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 40,
        "faixas": [(0, 31.99, 0), (32, 39.99, 2.5), (40, 100, 5)],
        "meta_editavel": False,
    },
    {
        "codigo": "reunioes_ec_du",
        "pilar": PILAR_RESULTADO,
        "nome": "Reuniões por EC/dia útil",
        "pts": 3,
        "tipo": "VALOR_HIGHER_BETTER",
        "meta_universal_pct": 4,  # 4 reuniões/EC/du
        "faixas": [(0, 3.1, 0), (3.11, 3.99, 1.5), (4, 999, 3)],
        "meta_editavel": False,  # denominador (ECs M3 + dias úteis) é global do mês
    },
    {
        "codigo": "contadores_trabalhados",
        "pilar": PILAR_RESULTADO,
        "nome": "Contadores trabalhados",
        "pts": 2,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 90,
        "faixas": [(0, 71.99, 0), (72, 89.99, 1), (90, 100, 2)],
        "meta_editavel": False,
    },
    {
        "codigo": "contadores_indicando",
        "pilar": PILAR_RESULTADO,
        "nome": "Contadores indicando",
        "pts": 3,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 25,
        "faixas": [(0, 19.99, 0), (20, 24.99, 1.5), (25, 100, 3)],
        "meta_editavel": False,
    },
    {
        "codigo": "contadores_ativando",
        "pilar": PILAR_RESULTADO,
        "nome": "Contadores ativando",
        "pts": 4,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 8,
        "faixas": [(0, 6.3, 0), (6.31, 7.99, 2), (8, 100, 4)],
        "meta_editavel": False,
    },
    {
        "codigo": "demos_outbound",
        "pilar": PILAR_RESULTADO,
        "nome": "Número de demos Outbound",
        "pts": 3,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 99.99, 1.5), (100, 100, 3)],
        "meta_editavel": True,
        "meta_label": "Meta de demos outbound (qtd)",
        "snapshot_col": "demos_outbound_meta",
    },
    {
        "codigo": "reuniao_contador_inbound",
        "pilar": PILAR_RESULTADO,
        "nome": "Reunião com contador do lead Inbound",
        "pts": 4,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 80,
        "faixas": [(0, 63.99, 0), (64, 79.99, 2), (80, 100, 4)],
        "meta_editavel": False,
    },
    {
        "codigo": "conversao_inbound",
        "pilar": PILAR_RESULTADO,
        "nome": "Conversão total leads Inbound",
        "pts": 2,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 45,
        "faixas": [(0, 35.99, 0), (36, 44.99, 1), (45, 100, 2)],
        "meta_editavel": False,
    },
    {
        "codigo": "conversao_total",
        "pilar": PILAR_RESULTADO,
        "nome": "Conversão total de leads",
        "pts": 4,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 35,
        "faixas": [(0, 27.99, 0), (28, 34.99, 2), (35, 100, 4)],
        "meta_editavel": False,
    },
    {
        "codigo": "conversao_m0",
        "pilar": PILAR_RESULTADO,
        "nome": "Conversão de leads no M0",
        "pts": 3,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 20,
        "faixas": [(0, 15.99, 0), (16, 19.99, 1.5), (20, 100, 3)],
        "meta_editavel": False,
    },
    {
        "codigo": "demo_du",
        "pilar": PILAR_RESULTADO,
        "nome": "Apresentação (demo) por dia útil",
        "pts": 4,
        "tipo": "VALOR_HIGHER_BETTER",
        "meta_universal_pct": 4,  # 4 demos/EV/du
        "faixas": [(0, 3.1, 0), (3.11, 3.99, 2), (4, 999, 4)],
        "meta_editavel": False,  # denominador (EVs + du) é global do mês
    },
    {
        "codigo": "integracao_contabil",
        "pilar": PILAR_RESULTADO,
        "nome": "Integração Contábil",
        "pts": 3,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 99.99, 1.5), (100, 100, 3)],
        "meta_editavel": True,  # meta numérica vem do cluster (auto-preenchida)
        "meta_label": "Meta de indicações/mês (cluster)",
        "meta_por_cluster": {
            "INCUBADORA":   3,
            "AVANCA_PLUS":  5,
            "BASE":         5,
            "OURO":         5,
            "PLATINA":      8,
            "PRIME":        8,
            "BLACK":        8,
        },
    },

    # ─────────── PILAR GESTÃO (7 indicadores, 20 pts) ───────────
    {
        "codigo": "remuneracao_variavel",
        "pilar": PILAR_GESTAO,
        "nome": "Aderência ao Modelo Remuneração Variável",
        "pts": 2,
        "tipo": "BINARIO",
        "faixas": [(0, 0, 0), (1, 1, 2)],
        "meta_editavel": False,
    },
    {
        "codigo": "uso_correto_cromie",
        "pilar": PILAR_GESTAO,
        "nome": "Utilização correta do CROmie",
        "pts": 2,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 99.99, 1), (100, 100, 2)],
        "meta_editavel": False,
    },
    {
        "codigo": "gestao_quartis",
        "pilar": PILAR_GESTAO,
        "nome": "Adesão à gestão dos quartis",
        "pts": 4,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 80,
        "faixas": [(0, 63.99, 0), (64, 79.99, 2), (80, 100, 4)],
        "meta_editavel": False,
    },
    {
        "codigo": "headcount_recomendado",
        "pilar": PILAR_GESTAO,
        "nome": "Adesão ao headcount recomendado",
        "pts": 5,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 99.99, 2.5), (100, 100, 5)],
        "meta_editavel": True,
        "meta_label": "Headcount alvo da unidade",
        "snapshot_col": None,  # entra direto no cabeçalho
    },
    {
        "codigo": "politica_contratacao",
        "pilar": PILAR_GESTAO,
        "nome": "Adesão à política de contratação e remuneração",
        "pts": 3,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 99.99, 1.5), (100, 100, 3)],
        "meta_editavel": False,
    },
    {
        "codigo": "trilhas_uc",
        "pilar": PILAR_GESTAO,
        "nome": "Conclusão das trilhas obrigatórias da UC",
        "pts": 2,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 99.99, 1), (100, 100, 2)],
        "meta_editavel": False,
    },
    {
        "codigo": "turnover_voluntario",
        "pilar": PILAR_GESTAO,
        "nome": "Turnover Voluntário",
        "pts": 2,
        "tipo": "PCT_LOWER_BETTER",
        "meta_universal_pct": 0,
        "faixas": [],  # manual não detalhou faixas; será zerado até a franqueadora informar
        "meta_editavel": False,
    },

    # ─────────── PILAR ENGAJAMENTO (6 indicadores, 20 pts) ───────────
    {
        "codigo": "treinamentos_franqueadora",
        "pilar": PILAR_ENGAJAMENTO,
        "nome": "Participação em treinamentos da franqueadora",
        "pts": 4,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 90,
        "faixas": [(0, 71.99, 0), (72, 89.99, 2), (90, 100, 4)],
        "meta_editavel": False,
    },
    {
        "codigo": "leitura_yungas",
        "pilar": PILAR_ENGAJAMENTO,
        "nome": "Leitura dos informes na Yungas",
        "pts": 3,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 99.99, 1.5), (100, 100, 3)],
        "meta_editavel": False,
    },
    {
        "codigo": "verba_cooperada",
        "pilar": PILAR_ENGAJAMENTO,
        "nome": "Utilização de verba cooperada",
        "pts": 2,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [],  # pro-rata semestral; lógica especial no pex_calc
        "meta_editavel": False,
    },
    {
        "codigo": "instagram",
        "pilar": PILAR_ENGAJAMENTO,
        "nome": "Mídias sociais — Instagram",
        "pts": 2,
        "tipo": "BINARIO",
        "faixas": [(0, 0, 0), (1, 1, 2)],
        "meta_editavel": False,
    },
    {
        "codigo": "big3",
        "pilar": PILAR_ENGAJAMENTO,
        "nome": "BIG 3 — Ações mensais",
        "pts": 6,
        "tipo": "ESCALA_DISCRETA",
        "faixas": [(0, 0, 0), (1, 1, 2), (2, 2, 4), (3, 3, 6)],
        "meta_editavel": False,  # tratado em tabela separada (pex_metas_big3)
    },
    {
        "codigo": "eventos",
        "pilar": PILAR_ENGAJAMENTO,
        "nome": "Realização de eventos",
        "pts": 3,
        "tipo": "PCT_HIGHER_BETTER",
        "meta_universal_pct": 100,
        "faixas": [(0, 79.99, 0), (80, 99.99, 1.5), (100, 100, 3)],
        "meta_editavel": True,
        "meta_label": "Meta de eventos/mês (cluster)",
        "meta_por_cluster": {
            "INCUBADORA":   2,  # 1 Otimiza + 1 outro
            "AVANCA_PLUS":  2,
            "BASE":         3,  # 2 Otimizas + 1 outro
            "OURO":         4,  # 3 Otimizas + 1 outro
            "PLATINA":      5,  # 4 Otimizas + 1 outro
            "PRIME":        6,  # 5 Otimizas + 1 outro
            "BLACK":        6,
        },
    },
]

# Sanity checks (valida no import — falha rápido se alguém mexer errado)
def _validar_catalogo():
    pesos_por_pilar = {PILAR_RESULTADO: 0, PILAR_GESTAO: 0, PILAR_ENGAJAMENTO: 0}
    contagem = {PILAR_RESULTADO: 0, PILAR_GESTAO: 0, PILAR_ENGAJAMENTO: 0}
    for ind in CATALOGO:
        pesos_por_pilar[ind["pilar"]] += ind["pts"]
        contagem[ind["pilar"]] += 1

    assert pesos_por_pilar[PILAR_RESULTADO] == 60, \
        f"Resultado deve somar 60, soma {pesos_por_pilar[PILAR_RESULTADO]}"
    assert pesos_por_pilar[PILAR_GESTAO] == 20, \
        f"Gestão deve somar 20, soma {pesos_por_pilar[PILAR_GESTAO]}"
    assert pesos_por_pilar[PILAR_ENGAJAMENTO] == 20, \
        f"Engajamento deve somar 20, soma {pesos_por_pilar[PILAR_ENGAJAMENTO]}"
    assert contagem[PILAR_RESULTADO] == 17, f"Resultado deve ter 17, tem {contagem[PILAR_RESULTADO]}"
    assert contagem[PILAR_GESTAO] == 7, f"Gestão deve ter 7, tem {contagem[PILAR_GESTAO]}"
    assert contagem[PILAR_ENGAJAMENTO] == 6, f"Engajamento deve ter 6, tem {contagem[PILAR_ENGAJAMENTO]}"
    assert len(CATALOGO) == 30, f"Total deve ter 30, tem {len(CATALOGO)}"

    # Códigos únicos
    codigos = [i["codigo"] for i in CATALOGO]
    assert len(codigos) == len(set(codigos)), "Códigos duplicados no catálogo"


_validar_catalogo()


# Helpers
def get_indicador(codigo: str) -> dict:
    """Retorna o indicador pelo código, ou levanta KeyError."""
    for ind in CATALOGO:
        if ind["codigo"] == codigo:
            return ind
    raise KeyError(f"Indicador desconhecido: {codigo}")


def indicadores_editaveis() -> list[dict]:
    """Subset que aparece com campo de input na página /metas."""
    return [i for i in CATALOGO if i.get("meta_editavel")]


def indicadores_por_pilar(pilar: str) -> list[dict]:
    """Lista (na ordem de definição) os indicadores de um pilar."""
    return [i for i in CATALOGO if i["pilar"] == pilar]


def meta_para_cluster(codigo: str, cluster: str) -> float | None:
    """Devolve a meta numérica derivada do cluster, se houver."""
    ind = get_indicador(codigo)
    por_cluster = ind.get("meta_por_cluster") or {}
    return por_cluster.get(cluster)
