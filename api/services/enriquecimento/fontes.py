"""
HIPO — Enriquecimento: as fontes externas.

Cada fonte é uma função `async buscar(cnpj) -> (payload, erro)`. Nunca
levanta exceção: devolve `(None, "motivo")`. A razão é a mesma do
`services/ia.py` — recurso acessório não derruba o essencial. Se a Receita
estiver fora do ar, o cadastro continua sendo feito à mão, com a tela
dizendo o que aconteceu.

FONTE NÃO CONFIGURADA É FONTE DESLIGADA, e não erro de inicialização. Sem
`LEADCNPJ_API_KEY` no .env, a LeadCNPJ simplesmente não entra na lista e a
API sobe igual — mesma regra do S3, do SES e da chave da IA.

POR QUE OS CAMINHOS SÃO CONFIGURÁVEIS

`LEADCNPJ_CAMINHO_CNPJ`, `LEADCNPJ_HEADER` e `LEADCNPJ_PREFIXO_HEADER` vêm
do .env em vez de estarem fixos no código. A documentação da LeadCNPJ exige
login, então o formato exato foi escrito a partir do que é padrão de
mercado. Se a resposta real divergir, o ajuste é uma linha no .env e um
restart — não um deploy. O que NÃO é configurável é a leitura do payload:
isso é trabalho de `modelo.normalizar_leadcnpj`, e é lá que se mexe.
"""
from __future__ import annotations

import logging

import httpx

from config import settings

log = logging.getLogger("hipo.enriquecimento")

TIMEOUT_S = 20.0

# Nomes canônicos. Entram no .env (ENRIQUECIMENTO_FONTES) e na coluna
# `conta_enriquecimentos.fonte`.
BRASILAPI = "brasilapi"
LEADCNPJ = "leadcnpj"


def _url_base(valor: str, padrao: str) -> str:
    return (valor or padrao).rstrip("/")


def configurada(fonte: str) -> bool:
    """
    True se a fonte pode ser chamada agora.

    A BrasilAPI é pública e não exige chave — está sempre configurada. A
    LeadCNPJ depende da chave no .env.
    """
    if fonte == BRASILAPI:
        return True
    if fonte == LEADCNPJ:
        return bool(getattr(settings, "LEADCNPJ_API_KEY", "").strip())
    return False


def fontes_habilitadas() -> list[str]:
    """
    Lê `ENRIQUECIMENTO_FONTES` (lista separada por vírgula) e devolve só as
    que estão configuradas, NA ORDEM DECLARADA.

    A ordem importa: é a precedência do `modelo.mesclar`. Com
    `leadcnpj,brasilapi`, a paga responde primeiro (é ela que traz o nº de
    funcionários) e a gratuita completa o que faltou.

    Nome desconhecido no .env é ignorado com aviso no log, em vez de
    derrubar a API — erro de digitação em config de recurso acessório não
    pode impedir o sistema de subir.
    """
    bruto = getattr(settings, "ENRIQUECIMENTO_FONTES", "") or ""
    pedidas = [f.strip().lower() for f in bruto.split(",") if f.strip()]
    habilitadas: list[str] = []
    for fonte in pedidas:
        if fonte not in (BRASILAPI, LEADCNPJ):
            log.warning("enriquecimento: fonte desconhecida no .env: %r", fonte)
            continue
        if not configurada(fonte):
            log.info("enriquecimento: fonte %s pedida mas sem credencial", fonte)
            continue
        if fonte not in habilitadas:
            habilitadas.append(fonte)
    return habilitadas


# ── BrasilAPI ────────────────────────────────────────────────────────────────

async def buscar_brasilapi(cnpj: str) -> tuple[dict | None, str | None]:
    """
    `GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}`.

    Pública, sem chave, sem SLA. O 429 (uso excessivo) e o 504 acontecem —
    por isso o cache de 90 dias existe e por isso a falha é devolvida como
    mensagem, não como exceção.
    """
    url = f"{_url_base(getattr(settings, 'BRASILAPI_URL', ''), 'https://brasilapi.com.br/api/cnpj/v1')}/{cnpj}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
            resp = await cliente.get(url)
    except Exception as e:
        log.warning("brasilapi: falhou (%s: %s)", type(e).__name__, e)
        return None, f"Não foi possível falar com a Receita ({type(e).__name__})."

    if resp.status_code == 404:
        return None, "CNPJ não encontrado na base da Receita."
    if resp.status_code == 429:
        return None, "Limite de consultas da BrasilAPI atingido. Tente em alguns minutos."
    if resp.status_code != 200:
        log.warning("brasilapi: HTTP %s — %s", resp.status_code, resp.text[:200])
        return None, f"A consulta à Receita respondeu {resp.status_code}."

    try:
        corpo = resp.json()
    except ValueError:
        return None, "A Receita respondeu num formato inesperado."
    if not isinstance(corpo, dict):
        return None, "A Receita respondeu num formato inesperado."
    return corpo, None


# ── LeadCNPJ ─────────────────────────────────────────────────────────────────

def _cabecalhos_leadcnpj() -> dict:
    chave = getattr(settings, "LEADCNPJ_API_KEY", "").strip()
    nome = getattr(settings, "LEADCNPJ_HEADER", "") or "Authorization"
    prefixo = getattr(settings, "LEADCNPJ_PREFIXO_HEADER", "")
    valor = f"{prefixo} {chave}".strip() if prefixo else chave
    return {nome: valor, "Accept": "application/json"}


async def _get_leadcnpj(caminho: str) -> tuple[dict | None, str | None]:
    base = _url_base(
        getattr(settings, "LEADCNPJ_URL", ""), "https://leadcnpj.com.br/api"
    )
    url = f"{base}/{caminho.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
            resp = await cliente.get(url, headers=_cabecalhos_leadcnpj())
    except Exception as e:
        log.warning("leadcnpj: falhou (%s: %s)", type(e).__name__, e)
        return None, f"Não foi possível falar com a LeadCNPJ ({type(e).__name__})."

    if resp.status_code in (401, 403):
        # ERROR e não WARNING: chave errada significa que TODA consulta paga
        # está falhando, e isso precisa saltar no journal.
        log.error("leadcnpj: HTTP %s — credencial recusada", resp.status_code)
        return None, "A LeadCNPJ recusou a credencial. Confira LEADCNPJ_API_KEY."
    if resp.status_code == 404:
        return None, "CNPJ não encontrado na LeadCNPJ."
    if resp.status_code == 429:
        return None, "Limite de requisições da LeadCNPJ atingido."
    if resp.status_code == 402:
        log.error("leadcnpj: HTTP 402 — créditos esgotados")
        return None, "Os créditos da LeadCNPJ acabaram."
    if resp.status_code != 200:
        log.warning("leadcnpj: HTTP %s — %s", resp.status_code, resp.text[:200])
        return None, f"A LeadCNPJ respondeu {resp.status_code}."

    try:
        corpo = resp.json()
    except ValueError:
        return None, "A LeadCNPJ respondeu num formato inesperado."

    # Envelope comum em API brasileira: {"data": {...}} ou {"result": {...}}.
    # Desembrulhar aqui, e não no normalizador, mantém o normalizador
    # falando só de campos de negócio.
    if isinstance(corpo, dict):
        for chave in ("data", "result", "resultado", "empresa"):
            interno = corpo.get(chave)
            if isinstance(interno, dict) and len(corpo) <= 3:
                return interno, None
        return corpo, None
    if isinstance(corpo, list) and corpo and isinstance(corpo[0], dict):
        return corpo[0], None
    return None, "A LeadCNPJ respondeu num formato inesperado."


async def buscar_leadcnpj(cnpj: str) -> tuple[dict | None, str | None]:
    """Consulta de CNPJ na LeadCNPJ. Caminho configurável pelo .env."""
    if not configurada(LEADCNPJ):
        return None, "LeadCNPJ não configurada."
    molde = getattr(settings, "LEADCNPJ_CAMINHO_CNPJ", "") or "empresas/{cnpj}"
    return await _get_leadcnpj(molde.format(cnpj=cnpj))


async def empresas_do_socio(
    nome: str, documento: str | None = None
) -> tuple[list[dict], str | None]:
    """
    Busca reversa EXTERNA: outras empresas em que o sócio participa.

    Nenhuma fonte pública faz isso — a Receita só responde no sentido
    CNPJ → sócios. Depende de fonte paga, e o caminho vem do .env porque a
    existência desse endpoint na LeadCNPJ não está documentada publicamente.

    `LEADCNPJ_CAMINHO_SOCIO` vazio = recurso desligado, e a tela mostra só a
    busca reversa DENTRO da base do HIPO, que sempre funciona. Devolver
    lista vazia com o motivo é melhor que esconder o recurso: o usuário
    precisa saber que a resposta "nenhuma outra empresa" é "não procurei
    fora daqui", e não "não existe".
    """
    molde = getattr(settings, "LEADCNPJ_CAMINHO_SOCIO", "") or ""
    if not molde or not configurada(LEADCNPJ):
        return [], "Busca externa de sócio não configurada."

    caminho = molde.format(
        nome=httpx.QueryParams({"q": nome})["q"],
        documento=documento or "",
    )
    corpo, erro = await _get_leadcnpj(caminho)
    if erro:
        return [], erro
    if not isinstance(corpo, dict):
        return [], None

    for chave in ("empresas", "itens", "items", "companies", "resultados"):
        lista = corpo.get(chave)
        if isinstance(lista, list):
            return [i for i in lista if isinstance(i, dict)], None
    return [], None


# Registro consultado pelo orquestrador. Fonte nova entra aqui e em
# `modelo.py`; nenhum outro arquivo precisa saber que ela existe.
BUSCADORES = {
    BRASILAPI: buscar_brasilapi,
    LEADCNPJ: buscar_leadcnpj,
}
