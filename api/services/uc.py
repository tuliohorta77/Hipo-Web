"""
HIPO — Universidade Corporativa (UC): regras puras.

Sem banco, sem rede e sem relógio: `agora` e `hoje` chegam por parâmetro,
como no resto da casa. Rodam no pytest local do Windows.

O que mora aqui:

  * vocabulário (pilares, status, cargos que fazem trilha)
  * vídeo: de uma URL colada pela gestão para (provedor, id) — e só isso
    vai para o banco
  * conclusão de aula sem quiz: a trava de tempo mínimo
  * quiz final da trilha: banco de perguntas das aulas, sorteio,
    correção, nota e espera entre tentativas (a trilha só conclui com
    aprovação)
  * prazo e situação das trilhas obrigatórias (o "manual da função")
  * a PRÓXIMA AULA, que é o cartão que abre a tela

Especificação: claude/universidade-corporativa.md.
"""
from __future__ import annotations

import json
import math
import random
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


# ── Tour guiado ──────────────────────────────────────────────────────
#
# Passos que abrem a tela real do HIPO e destacam o que a aula explica.
# O tour só olha: o front bloqueia o clique na tela enquanto ele roda, e
# `clicar` só serve para abrir o que mostra (um cartão, uma aba, um
# formulário em branco) — nunca para gravar. Quem escolhe o que clicar é
# o conteúdo da carga, conferido pelos testes contra as âncoras do front.

# Telas onde um tour pode passar. Rota com parâmetro (aula, reunião ao
# vivo) fica de fora: o tour não sabe o id de nada.
ROTAS_TOUR = (
    "/crm/prospeccao", "/crm/oportunidades", "/crm/tarefas", "/crm/agenda",
    "/crm/contas", "/crm/parceiros", "/crm/relatorios", "/monitor", "/uc", "/perfil",
    "/carreira", "/carreira/desempenho",
)
MAX_PASSOS_TOUR = 15
MAX_CLIQUES_TOUR = 3
_ID_ANCORA = re.compile(r"^[a-z][a-z0-9-]{1,59}$")


def validar_tour(passos) -> list[dict] | None:
    """Normaliza o tour da aula. None ou lista vazia = aula sem tour."""
    if passos is None:
        return None
    if not isinstance(passos, list):
        raise ConteudoInvalido("O tour é uma lista de passos.")
    if not passos:
        return None
    if len(passos) > MAX_PASSOS_TOUR:
        raise ConteudoInvalido(f"O tour tem no máximo {MAX_PASSOS_TOUR} passos.")
    saida: list[dict] = []
    for i, p in enumerate(passos, start=1):
        if not isinstance(p, dict):
            raise ConteudoInvalido(f"Passo {i} do tour: formato inválido.")
        sobra = set(p) - {"rota", "alvo", "titulo", "texto", "clicar"}
        if sobra:
            raise ConteudoInvalido(f"Passo {i} do tour: campo desconhecido ({', '.join(sorted(sobra))}).")
        rota = (p.get("rota") or "").strip()
        if rota not in ROTAS_TOUR:
            raise ConteudoInvalido(f"Passo {i} do tour: tela '{rota or 'vazia'}' não aceita tour.")
        alvo = p.get("alvo")
        if alvo is not None:
            alvo = str(alvo).strip()
            if not _ID_ANCORA.match(alvo):
                raise ConteudoInvalido(f"Passo {i} do tour: alvo '{alvo}' inválido.")
        titulo = (p.get("titulo") or "").strip()
        texto = (p.get("texto") or "").strip()
        if not titulo or len(titulo) > 80:
            raise ConteudoInvalido(f"Passo {i} do tour: título vazio ou acima de 80 caracteres.")
        if not texto or len(texto) > 600:
            raise ConteudoInvalido(f"Passo {i} do tour: texto vazio ou acima de 600 caracteres.")
        clicar = p.get("clicar") or []
        if not isinstance(clicar, (list, tuple)) or len(clicar) > MAX_CLIQUES_TOUR:
            raise ConteudoInvalido(
                f"Passo {i} do tour: 'clicar' é uma lista de até {MAX_CLIQUES_TOUR} âncoras."
            )
        clicar = [str(c).strip() for c in clicar]
        for c in clicar:
            if not _ID_ANCORA.match(c):
                raise ConteudoInvalido(f"Passo {i} do tour: âncora de clique '{c}' inválida.")
        passo = {"rota": rota, "alvo": alvo, "titulo": titulo, "texto": texto}
        if clicar:
            passo["clicar"] = clicar
        saida.append(passo)
    return saida


def ler_tour(valor) -> list[dict] | None:
    """O JSONB chega do asyncpg como texto. Tour quebrado no banco = sem tour."""
    if valor is None:
        return None
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return None
    try:
        return validar_tour(valor)
    except ConteudoInvalido:
        return None


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


# ── Quiz ─────────────────────────────────────────────────────────────
#
# A trava de tempo garante presença, não entendimento. Decisões do Tulio
# (05/10/2026): o quiz é UM SÓ, no FINAL DA TRILHA, numa tela própria. As
# aulas concluem pela trava de tempo; o quiz abre quando todas estão
# concluídas, e a trilha só conclui com aprovação (85%). Reprovou: nova
# tentativa 10 minutos depois, com OUTRO sorteio.
#
# Cada aula guarda um BANCO de perguntas (as da carga têm 7). O quiz da
# trilha sorteia QUIZ_TRILHA_PERGUNTAS delas, espalhadas pelas aulas
# (rodízio: uma de cada aula, na ordem, até completar). O sorteio sai de
# uma semente (pessoa + trilha + nº de tentativas): o F5 mostra o mesmo
# quiz, e a correção refaz o mesmo sorteio — nada de estado entre o GET e
# o POST.
#
# O gabarito nunca sai do servidor: a tela recebe as alternativas sem
# `correta`, embaralhadas, e o resultado diz QUAIS perguntas errou (e de
# qual aula), nunca qual era a certa.

PERGUNTAS_POR_QUIZ = 7          # tamanho do banco de cada aula da CARGA
MAX_PERGUNTAS_POR_AULA = 10     # banco que a gestão escreve no estúdio
QUIZ_TRILHA_PERGUNTAS = 10      # perguntas sorteadas no quiz final
NOTA_MINIMA_QUIZ = 85
ALTERNATIVAS_MIN = 3
ALTERNATIVAS_MAX = 5
ESPERA_REPROVACAO_MIN = 10
MAX_ENUNCIADO = 300
MAX_ALTERNATIVA = 200


def validar_quiz(perguntas: list | None, exatas: int | None = None) -> list[dict]:
    """
    O banco de perguntas de uma aula, normalizado. Lista vazia = a aula
    não entra no quiz final da trilha.

    Recusa com mensagem pronta para a tela: mais de 10 perguntas (ou,
    com `exatas`, quantidade diferente — a carga exige 7), pergunta sem
    texto, alternativas fora de 3..5, repetidas, ou sem exatamente uma
    correta.
    """
    if not perguntas:
        return []
    if not isinstance(perguntas, list):
        raise ConteudoInvalido("As perguntas precisam vir numa lista.")
    if exatas is not None and len(perguntas) != exatas:
        raise ConteudoInvalido(
            f"A aula tem {len(perguntas)} pergunta(s); precisa de exatamente {exatas}."
        )
    if len(perguntas) > MAX_PERGUNTAS_POR_AULA:
        raise ConteudoInvalido(
            f"A aula tem {len(perguntas)} perguntas; o banco vai até {MAX_PERGUNTAS_POR_AULA}."
        )
    saida, vistos = [], set()
    for i, p in enumerate(perguntas, start=1):
        if not isinstance(p, dict):
            raise ConteudoInvalido(f"Pergunta {i}: formato inválido.")
        enunciado = " ".join(str(p.get("enunciado") or "").split())
        if not enunciado:
            raise ConteudoInvalido(f"Pergunta {i}: escreva o enunciado.")
        if len(enunciado) > MAX_ENUNCIADO:
            raise ConteudoInvalido(f"Pergunta {i}: enunciado acima de {MAX_ENUNCIADO} caracteres.")
        if enunciado.lower() in vistos:
            raise ConteudoInvalido(f"Pergunta {i}: enunciado repetido.")
        vistos.add(enunciado.lower())
        alts = p.get("alternativas") or []
        if not isinstance(alts, list) or not (ALTERNATIVAS_MIN <= len(alts) <= ALTERNATIVAS_MAX):
            raise ConteudoInvalido(
                f"Pergunta {i}: use de {ALTERNATIVAS_MIN} a {ALTERNATIVAS_MAX} alternativas."
            )
        norm, textos = [], set()
        for j, alt in enumerate(alts, start=1):
            if not isinstance(alt, dict):
                raise ConteudoInvalido(f"Pergunta {i}, alternativa {j}: formato inválido.")
            texto = " ".join(str(alt.get("texto") or "").split())
            if not texto:
                raise ConteudoInvalido(f"Pergunta {i}, alternativa {j}: escreva o texto.")
            if len(texto) > MAX_ALTERNATIVA:
                raise ConteudoInvalido(
                    f"Pergunta {i}, alternativa {j}: acima de {MAX_ALTERNATIVA} caracteres."
                )
            if texto.lower() in textos:
                raise ConteudoInvalido(f"Pergunta {i}: alternativas repetidas.")
            textos.add(texto.lower())
            norm.append({"texto": texto, "correta": alt.get("correta") is True})
        if sum(1 for a in norm if a["correta"]) != 1:
            raise ConteudoInvalido(f"Pergunta {i}: marque exatamente uma alternativa correta.")
        saida.append({"enunciado": enunciado, "alternativas": norm})
    return saida


def nota_do_quiz(acertos: int, total: int) -> int:
    """
    0..100, arredondada para baixo: 6 de 7 = 85, nunca "86" que faria a
    pessoa achar que passou com folga.

    >>> nota_do_quiz(6, 7)
    85
    >>> nota_do_quiz(7, 7)
    100
    """
    if total <= 0:
        return 0
    return (100 * acertos) // total


def aprovado(acertos: int, total: int, nota_minima: int) -> bool:
    """
    Comparação em inteiros, sem arredondar: 6 de 7 (85,7%) passa em 85.

    >>> aprovado(6, 7, 85), aprovado(5, 7, 85)
    (True, False)
    """
    return total > 0 and acertos * 100 >= nota_minima * total


@dataclass(frozen=True)
class Correcao:
    acertos: int
    total: int
    nota: int
    aprovada: bool
    erradas: list[str]


def corrigir(
    perguntas: list[dict],
    respostas: dict,
    nota_minima: int,
) -> Correcao:
    """
    Corrige um envio. `perguntas` vem do banco, na ordem do quiz:
    [{"id": str, "alternativas": [{"id": str, "correta": bool}]}].
    `respostas` é {pergunta_id: alternativa_id}, como a tela mandou.

    Toda pergunta precisa de resposta, e a resposta precisa ser uma
    alternativa DAQUELA pergunta: resposta faltando, sobrando ou trocada
    é recusada inteira (422), não conta como erro — senão um envio
    malformado queimaria a tentativa e os 10 minutos.
    """
    if not isinstance(respostas, dict):
        raise ConteudoInvalido("Envie uma resposta para cada pergunta.")
    ids = [str(p["id"]) for p in perguntas]
    recebidas = {str(k): str(v) for k, v in respostas.items()}
    faltando = [i for i, pid in enumerate(ids, start=1) if pid not in recebidas]
    if faltando:
        lista = ", ".join(str(n) for n in faltando)
        raise ConteudoInvalido(f"Responda todas as perguntas antes de enviar (falta: {lista}).")
    if set(recebidas) - set(ids):
        raise ConteudoInvalido("O quiz mudou desde que você abriu. Recarregue a página.")
    acertos, erradas = 0, []
    for p in perguntas:
        pid = str(p["id"])
        alts = {str(a["id"]): bool(a["correta"]) for a in p["alternativas"]}
        escolha = recebidas[pid]
        if escolha not in alts:
            raise ConteudoInvalido("Alternativa que não pertence à pergunta.")
        if alts[escolha]:
            acertos += 1
        else:
            erradas.append(pid)
    total = len(perguntas)
    return Correcao(
        acertos=acertos, total=total, nota=nota_do_quiz(acertos, total),
        aprovada=aprovado(acertos, total, nota_minima), erradas=erradas,
    )


def segundos_para_refazer(ultima_reprovada_em: datetime | None, agora: datetime) -> int:
    """Quanto falta para a nova tentativa depois de reprovar. 0 = pode."""
    if ultima_reprovada_em is None:
        return 0
    libera = ultima_reprovada_em + timedelta(minutes=ESPERA_REPROVACAO_MIN)
    return max(0, math.ceil((libera - agora).total_seconds()))


def acertos_para_aprovar(total: int, nota_minima: int) -> int:
    """
    >>> acertos_para_aprovar(10, 85), acertos_para_aprovar(7, 85)
    (9, 6)
    """
    return -(-nota_minima * total // 100)


def sortear_quiz(banco: list[dict], semente: str, quantas: int = QUIZ_TRILHA_PERGUNTAS) -> list[dict]:
    """
    As perguntas do quiz da trilha. `banco` traz cada pergunta com
    `aula_ordem` (e o que mais a tela precisar). Rodízio pelas aulas na
    ordem da trilha — uma de cada, depois a segunda de cada — para o quiz
    cobrir a trilha inteira; dentro da aula, a escolha é sorteada. Sai na
    ordem das aulas, para o resultado dizer "reveja a aula 3".
    """
    por_aula: dict[int, list[dict]] = {}
    for p in banco:
        por_aula.setdefault(p["aula_ordem"], []).append(p)
    filas = [
        embaralhar(sorted(lista, key=lambda x: str(x["id"])), f"{semente}:{ordem}")
        for ordem, lista in sorted(por_aula.items())
    ]
    escolhidas: list[tuple[int, int, dict]] = []
    rodada = 0
    while len(escolhidas) < quantas and any(rodada < len(f) for f in filas):
        for i, f in enumerate(filas):
            if rodada < len(f) and len(escolhidas) < quantas:
                escolhidas.append((i, rodada, f[rodada]))
        rodada += 1
    return [p for _, _, p in sorted(escolhidas, key=lambda x: (x[0], x[1]))]


def embaralhar(itens: list, semente: str) -> list:
    """
    Cópia embaralhada, estável para a mesma semente. A rota usa
    pessoa + aula + nº de tentativas: o F5 não muda a ordem, a tentativa
    seguinte muda.
    """
    copia = list(itens)
    random.Random(semente).shuffle(copia)
    return copia


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
                    hoje: date, quiz_pendente: bool = False) -> SituacaoTrilha:
    """`quiz_pendente`: a trilha tem quiz final e ele não foi aprovado."""
    if total_aulas > 0 and concluidas >= total_aulas and not quiz_pendente:
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
    "quiz_final": 4,     # aulas feitas, falta o quiz (trilha livre)
    "em_andamento": 4,   # trilha livre começada
    "nova": 5,
}

MOTIVOS = {
    "atrasada": "Trilha obrigatória atrasada",
    "vence_logo": "Trilha obrigatória vence logo",
    "atualizada": "Aula atualizada desde que você concluiu",
    "em_andamento": "Continue de onde parou",
    "quiz_final": "Falta o quiz final da trilha",
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
    tipo: str = "aula"            # aula | quiz (o quiz final da trilha)


def motivo(p: AulaPendente) -> str:
    if p.obrigatoria and p.situacao_trilha in ("atrasada", "vence_logo"):
        return p.situacao_trilha
    if p.tipo == "quiz":
        return "quiz_final"
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
