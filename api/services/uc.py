"""
HIPO — Universidade Corporativa (UC): regras puras.

Sem banco, sem rede e sem relógio: `agora` e `hoje` chegam por parâmetro,
como no resto da casa. Rodam no pytest local do Windows.

O que mora aqui:

  * vocabulário (pilares, status, cargos que fazem trilha)
  * vídeo: de uma URL colada pela gestão para (provedor, id) — e só isso
    vai para o banco
  * conclusão de aula sem quiz: a trava de tempo mínimo
  * prazo e situação das trilhas obrigatórias (o "manual da função")
  * a PRÓXIMA AULA, que é o cartão que abre a tela

Especificação: claude/universidade-corporativa.md.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

# ── Vocabulário ──────────────────────────────────────────────────────

PILARES: dict[str, str] = {
    "tecnica": "Técnica",
    "metodo": "Método",
    "energia": "Energia",
}

STATUS_TRILHA = ("rascunho", "publicada", "arquivada")
STATUS_AULA = ("rascunho", "publicada")

# Medidas da avaliação mensal que uma trilha pode reforçar (elo com o PDI).
REFORCOS: dict[str, str] = {
    "obrigatorias": "Trilhas obrigatórias em dia",
    "tarefas_no_prazo": "Tarefas concluídas no prazo",
    "desfecho_em_dia": "Desfecho de reunião registrado em dia",
    "roteiro": "Roteiro de vendas",
    "metas": "Metas do mês",
}

# Quem pode receber trilha. Mesmos cargos que operam o HIPO; a conta de
# TV (Monitor) não aprende nada.
CARGOS_UC = ("Franqueado", "ADM", "EC", "SDR", "EV", "EP")

# Fração da duração estimada que precisa passar entre abrir a aula e poder
# marcar "Concluí". Não mede se a pessoa assistiu (vídeo do Drive não
# avisa nada); impede abrir e fechar em três segundos.
FRACAO_TEMPO_MINIMO = 0.5


class ConteudoInvalido(ValueError):
    """Recusa com mensagem pronta para a tela."""


def validar_pilar(pilar: str | None) -> str:
    p = (pilar or "").strip().lower()
    if p not in PILARES:
        raise ConteudoInvalido(
            "Pilar inválido. Use um destes: " + ", ".join(PILARES.values()) + "."
        )
    return p


def validar_status_trilha(status: str | None) -> str:
    s = (status or "").strip().lower()
    if s not in STATUS_TRILHA:
        raise ConteudoInvalido("Status da trilha inválido: rascunho, publicada ou arquivada.")
    return s


def validar_status_aula(status: str | None) -> str:
    s = (status or "").strip().lower()
    if s not in STATUS_AULA:
        raise ConteudoInvalido("Status da aula inválido: rascunho ou publicada.")
    return s


def validar_reforca(reforca: str | None) -> str | None:
    if reforca is None or str(reforca).strip() == "":
        return None
    r = str(reforca).strip().lower()
    if r not in REFORCOS:
        raise ConteudoInvalido(
            "Medida de reforço inválida. Use uma destas: "
            + ", ".join(REFORCOS.values()) + "."
        )
    return r


def validar_cargo(cargo: str | None) -> str:
    c = (cargo or "").strip()
    if c not in CARGOS_UC:
        raise ConteudoInvalido(
            f"Cargo '{c or 'vazio'}' não recebe trilha. Use: " + ", ".join(CARGOS_UC) + "."
        )
    return c


# ── Vídeo ────────────────────────────────────────────────────────────

PROVEDORES: dict[str, str] = {
    "youtube": "YouTube",
    "vimeo": "Vimeo",
    "loom": "Loom",
    "drive": "Google Drive",
}

_ID_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ID_VIMEO = re.compile(r"^\d{6,12}$")
_ID_LOOM = re.compile(r"^[A-Za-z0-9]{20,40}$")
_ID_DRIVE = re.compile(r"^[A-Za-z0-9_-]{20,80}$")


def _host(u) -> str:
    h = (u.hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def normalizar_video(url: str | None) -> tuple[str, str] | None:
    """
    De uma URL colada pela gestão para (provedor, id).

    Vazio → None (aula sem vídeo). Host fora da lista, esquema que não é
    http(s) ou id que não tem a forma do provedor → ConteudoInvalido, com
    a lista do que se aceita. O banco nunca vê a URL: o front monta o
    endereço de embed a partir do par, então nenhum texto colado aqui
    vira `<iframe src>`.

    >>> normalizar_video("https://youtu.be/dQw4w9WgXcQ")
    ('youtube', 'dQw4w9WgXcQ')
    """
    bruto = (url or "").strip()
    if not bruto:
        return None

    u = urlparse(bruto)
    if u.scheme not in ("http", "https"):
        raise ConteudoInvalido("O link do vídeo precisa começar com https://.")

    host = _host(u)
    partes = [p for p in u.path.split("/") if p]

    candidato: tuple[str, str] | None = None

    if host in ("youtube.com", "m.youtube.com", "youtube-nocookie.com"):
        q = parse_qs(u.query)
        if partes[:1] == ["watch"] and q.get("v"):
            candidato = ("youtube", q["v"][0])
        elif len(partes) >= 2 and partes[0] in ("embed", "shorts", "live", "v"):
            candidato = ("youtube", partes[1])
    elif host == "youtu.be" and partes:
        candidato = ("youtube", partes[0])
    elif host == "vimeo.com" and partes:
        candidato = ("vimeo", partes[0])
    elif host == "player.vimeo.com" and len(partes) >= 2 and partes[0] == "video":
        candidato = ("vimeo", partes[1])
    elif host == "loom.com" and len(partes) >= 2 and partes[0] in ("share", "embed"):
        candidato = ("loom", partes[1])
    elif host == "drive.google.com":
        q = parse_qs(u.query)
        if len(partes) >= 3 and partes[0] == "file" and partes[1] == "d":
            candidato = ("drive", partes[2])
        elif partes[:1] == ["open"] and q.get("id"):
            candidato = ("drive", q["id"][0])

    if candidato is None:
        raise ConteudoInvalido(
            "Link de vídeo não reconhecido. Aceitos: YouTube (pode ser não listado), "
            "Vimeo, Loom e Google Drive (arquivo compartilhado)."
        )

    provedor, ref = candidato
    padrao = {
        "youtube": _ID_YOUTUBE, "vimeo": _ID_VIMEO,
        "loom": _ID_LOOM, "drive": _ID_DRIVE,
    }[provedor]
    if not padrao.match(ref):
        raise ConteudoInvalido(
            f"O link parece ser do {PROVEDORES[provedor]}, mas o código do vídeo "
            "não está completo. Copie o link de novo pelo botão Compartilhar."
        )
    return provedor, ref


def url_do_video(provedor: str | None, ref: str | None) -> str | None:
    """Endereço público (para o "abrir no site"), nunca guardado."""
    if not provedor or not ref:
        return None
    return {
        "youtube": f"https://www.youtube.com/watch?v={ref}",
        "vimeo": f"https://vimeo.com/{ref}",
        "loom": f"https://www.loom.com/share/{ref}",
        "drive": f"https://drive.google.com/file/d/{ref}/view",
    }.get(provedor)


# ── Conclusão sem quiz ───────────────────────────────────────────────

def minutos_minimos(duracao_min: int | None) -> int:
    """Minutos entre abrir e poder concluir. Sem duração estimada: zero."""
    if not duracao_min or duracao_min <= 0:
        return 0
    return math.ceil(duracao_min * FRACAO_TEMPO_MINIMO)


def liberada_em(aberta_em: datetime, duracao_min: int | None) -> datetime:
    return aberta_em + timedelta(minutes=minutos_minimos(duracao_min))


def segundos_para_liberar(aberta_em: datetime | None, duracao_min: int | None,
                          agora: datetime) -> int:
    """
    Quanto falta para o "Concluí" valer. Aula nunca aberta conta como
    aberta agora — a rota de concluir abre antes de checar.
    """
    inicio = aberta_em or agora
    falta = (liberada_em(inicio, duracao_min) - agora).total_seconds()
    return max(0, math.ceil(falta))


# ── Manual da função: prazo e situação ───────────────────────────────

@dataclass(frozen=True)
class SituacaoTrilha:
    codigo: str      # concluida | atrasada | vence_logo | em_dia | sem_prazo
    rotulo: str
    prazo: date | None
    dias_restantes: int | None


# Obrigatória vencendo em até esta quantidade de dias sobe para "vence logo"
# e passa na frente na próxima aula.
DIAS_ALERTA = 7


def prazo_da_obrigatoria(entrada_no_cargo: datetime | date | None,
                         obrigatoria_desde: datetime | date | None,
                         prazo_dias: int | None) -> date | None:
    """
    O prazo conta do que vier DEPOIS: a entrada da pessoa no cargo ou o dia
    em que a trilha virou obrigatória para o cargo. Sem a segunda data, a
    primeira trilha publicada nasceria atrasada para quem já estava na
    equipe — e a tela abriria toda vermelha no primeiro dia.

    Enquanto não existe o cadastro de colaboradores (Bloco B1), a entrada no
    cargo é `usuarios.created_at`.
    """
    if not prazo_dias:
        return None
    datas = [d.date() if isinstance(d, datetime) else d
             for d in (entrada_no_cargo, obrigatoria_desde) if d is not None]
    if not datas:
        return None
    return max(datas) + timedelta(days=int(prazo_dias))


def situacao_trilha(total_aulas: int, concluidas: int, prazo: date | None,
                    hoje: date) -> SituacaoTrilha:
    if total_aulas > 0 and concluidas >= total_aulas:
        return SituacaoTrilha("concluida", "Concluída", prazo, None)
    if prazo is None:
        return SituacaoTrilha("sem_prazo", "Sem prazo", None, None)
    dias = (prazo - hoje).days
    if dias < 0:
        return SituacaoTrilha("atrasada", "Atrasada", prazo, dias)
    if dias <= DIAS_ALERTA:
        return SituacaoTrilha("vence_logo", "Vence logo", prazo, dias)
    return SituacaoTrilha("em_dia", "Em dia", prazo, dias)


def percentual(concluidas: int, total: int) -> int | None:
    """None quando não há aula: 0% seria mentira sobre trilha vazia."""
    if total <= 0:
        return None
    return round(100 * concluidas / total)


# ── Próxima aula ─────────────────────────────────────────────────────

# Ordem de prioridade do cartão "Sua próxima aula". Quanto menor, mais na
# frente. Empate desempata por prazo e depois pela ordem da trilha/aula.
PRIORIDADE = {
    "atrasada": 0,
    "vence_logo": 1,
    # Toda obrigatória em dia cai nesta faixa, começada ou não, e o PRAZO
    # decide entre elas. É o que faz o manual andar na ordem em que a gestão
    # o montou (01 com prazo de 10 dias antes da 03 com 30), mesmo que a
    # pessoa já tenha adiantado uma aula da 03.
    "obrigatoria": 2,
    "atualizada": 3,     # aula concluída que mudou de versão (trilha livre)
    "em_andamento": 4,   # trilha livre começada
    "nova": 5,
}

MOTIVOS = {
    "atrasada": "Trilha obrigatória atrasada",
    "vence_logo": "Trilha obrigatória vence logo",
    "atualizada": "Aula atualizada desde que você concluiu",
    "em_andamento": "Continue de onde parou",
    "obrigatoria": "Do manual da sua função",
    "nova": "Trilha disponível para você",
}


@dataclass(frozen=True)
class AulaPendente:
    aula_id: str
    aula_titulo: str
    aula_ordem: int
    trilha_id: str
    trilha_titulo: str
    pilar: str
    obrigatoria: bool
    situacao_trilha: str          # código de SituacaoTrilha
    prazo: date | None
    trilha_iniciada: bool         # alguma aula da trilha já concluída
    concluiu_versao_anterior: bool


def motivo(p: AulaPendente) -> str:
    if p.obrigatoria and p.situacao_trilha in ("atrasada", "vence_logo"):
        return p.situacao_trilha
    if p.concluiu_versao_anterior:
        return "atualizada"
    if p.trilha_iniciada:
        return "em_andamento"
    if p.obrigatoria:
        return "obrigatoria"
    return "nova"


def proxima_aula(pendentes: list[AulaPendente]) -> tuple[AulaPendente, str] | None:
    """
    A próxima aula da pessoa, com o motivo. Uma só — a tela abre num
    cartão, não numa lista (diretriz "próxima tarefa").

    Recebe as aulas PUBLICADAS ainda não concluídas na versão atual, de
    trilhas publicadas visíveis para o cargo. Dentro de uma trilha só a
    primeira pendente conta: a aula 3 não passa na frente da 2.
    """
    if not pendentes:
        return None

    primeira_por_trilha: dict[str, AulaPendente] = {}
    for p in pendentes:
        atual = primeira_por_trilha.get(p.trilha_id)
        if atual is None or p.aula_ordem < atual.aula_ordem:
            primeira_por_trilha[p.trilha_id] = p

    def faixa(p: AulaPendente) -> int:
        m = motivo(p)
        if p.obrigatoria and m not in ("atrasada", "vence_logo"):
            return PRIORIDADE["obrigatoria"]
        return PRIORIDADE[m]

    def chave(p: AulaPendente):
        return (
            faixa(p),
            p.prazo or date.max,
            0 if p.obrigatoria else 1,
            p.trilha_titulo.lower(),
            p.aula_ordem,
        )

    escolhida = min(primeira_por_trilha.values(), key=chave)
    return escolhida, motivo(escolhida)
