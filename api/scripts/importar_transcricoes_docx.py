"""
HIPO — Importa transcrições do Google Meet exportadas em .docx.

POR QUE ESTE SCRIPT EXISTE
  A coleta automática (Entrega 020) só enxerga a sala do Meet criada pela
  agenda do HIPO. Quem conduziu a reunião por fora da agenda — ou antes de a
  coleta existir — ficou com a transcrição só no Google Drive. Este script
  pega o .docx que o Meet gera ("Reunião iniciada em …", "Participantes",
  "Transcrição", falas "Nome: texto") e grava em `reuniao_transcricoes`, no
  MESMO formato que a coleta automática grava. A tela não distingue uma da
  outra: painel Transcrição, resumo e próximos passos aparecem igual.

COMO ACHA A REUNIÃO
  1. Oportunidade: pelo número OPP-AAAA-NNNNN no nome do arquivo; sem ele,
     pelo CNPJ que o título do evento leva ("<razão> <CNPJ> | Apresentação…").
  2. Tarefa: tipo reuniao/visita da oportunidade NO MESMO DIA (Brasília). Com
     horário conhecido, a mais próxima dele. Tarefa que já tem transcrição
     pronta não é candidata.
  3. O que faltar é criado:
       - tarefa existe, sem linha em `reunioes`  -> cria a reunião (online);
         se a tarefa está concluída, desfecho 'realizada' na data da conclusão.
       - não há tarefa no dia                    -> cria tarefa CONCLUÍDA +
         reunião 'realizada', do responsável informado, no horário da
         transcrição.
     Linhas criadas levam `criado_em` RETROATIVO (o dia do agendamento ou da
     reunião): com NOW(), o relatório de agendamentos do dia de hoje ganharia
     de presente reuniões de setembro inteiro.
  4. Tarefa em OUTRO dia (até 3 dias) e nenhuma no dia: NÃO cria nada — pode
     ser a reunião remarcada ou pode ser outra reunião. Vira REVISAR com a
     sugestão; decide-se com --mapa.

HORÁRIOS DAS FALAS
  O .docx só traz marcas de tempo a cada ~5 min ("00:20:00", relativas ao
  início). As falas entre duas marcas são distribuídas proporcionalmente ao
  tamanho do texto. O "[HH:MM]" de cada linha fica com precisão de minutos,
  suficiente para ler — não é o horário exato do Meet.

O QUE ELE NÃO FAZ
  Não mexe em reunião que já tem transcrição pronta (use --sobrescrever).
  Não conclui tarefa em aberto: a tela de desfecho exige a próxima tarefa, e
  isso é decisão de quem conduziu. Não chama o Google.

USO (na EC2, como ec2-user — o dono do .env)
  cd /home/hipo/app/api
  PYTHONPATH=/home/hipo/app/api python3 /tmp/importar_transcricoes_docx.py \\
      --pasta /tmp/transcricoes_import --responsavel jakeline            # dry-run
  ... --commit --por tulio@controllermedseg.com                          # grava
  ... --mapa "VOXEL=<uuid da tarefa>" --mapa "FQS=novo"                  # decide REVISAR
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import re
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # permite rodar de /tmp com PYTHONPATH=api

from services.transcricao import Fala, entradas_json, texto_corrido  # noqa: E402
from services.tarefa import FUSO_OPERACAO  # noqa: E402

# ── Leitura do .docx (stdlib: python-docx não está no requirements) ──

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def paragrafos_docx(caminho: Path | str) -> list[str]:
    """Texto de cada parágrafo do corpo, na ordem. Vazios ficam de fora."""
    with zipfile.ZipFile(caminho) as z:
        raiz = ET.fromstring(z.read("word/document.xml"))
    saida: list[str] = []
    for p in raiz.iter(f"{_W}p"):
        partes: list[str] = []
        for el in p.iter():
            if el.tag == f"{_W}t" and el.text:
                partes.append(el.text)
            elif el.tag == f"{_W}tab":
                partes.append(" ")
            elif el.tag in (f"{_W}br", f"{_W}cr"):
                partes.append(" ")
        texto = " ".join("".join(partes).split())
        if texto:
            saida.append(texto)
    return saida


# ── Interpretação do documento (puro) ────────────────────────────────

_RE_INICIO = re.compile(
    r"Reuni[ãa]o iniciada em (\d{4})-(\d{2})-(\d{2}) (\d{1,2}):(\d{2})\s*GMT([+-]\d{1,2})?",
    re.I,
)
_RE_MARCA = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})$")
_RE_FIM = re.compile(r"A reuni[ãa]o terminou depois de (\d{1,2}):(\d{2}):(\d{2})", re.I)
_RE_AVISO = re.compile(r"^Esta transcri[çc][ãa]o edit[áa]vel foi gerada", re.I)
_RE_OPP = re.compile(r"OPP-\d{4}-\d{5}", re.I)
_RE_CNPJ = re.compile(r"(\d{2})\.?(\d{3})\.?(\d{3})\s*[/_]?\s*(\d{4})-?(\d{2})")
# Nome padrão do arquivo que o Meet salva no Drive: "... - 2026_09_10 17_44 GMT-03_00 - Transcript"
_RE_CARIMBO_MEET = re.compile(r"(\d{4})_(\d{2})_(\d{2}) (\d{2})_(\d{2}) GMT([+-]\d{2})_(\d{2})")
_RE_DIA_EXTENSO = re.compile(r"\b(\d{1,2}) DE ([A-ZÇ]+)(?: DE (\d{4}))?", re.I)
_RE_FALA_GENERICA = re.compile(r"^([^:]{1,60}): (.+)$")

_MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "MARÇO": 3, "ABRIL": 4, "MAIO": 5,
    "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10,
    "NOVEMBRO": 11, "DEZEMBRO": 12,
}

# Intervalo entre as marcas de tempo que o Meet põe no documento.
PASSO_MARCA = timedelta(minutes=5)


@dataclass
class Linha:
    """Uma fala do documento, antes de ganhar horário."""
    participante: str
    texto: str
    offset: timedelta | None = None  # desde o início da reunião


@dataclass
class TranscricaoDocx:
    arquivo: str
    titulo: str | None = None
    opp_numero: str | None = None
    cnpj: str | None = None
    inicio: datetime | None = None          # com fuso
    dia_no_nome: date | None = None         # o que o nome do arquivo diz
    duracao: timedelta | None = None
    participantes: list[str] = field(default_factory=list)
    linhas: list[Linha] = field(default_factory=list)

    @property
    def dia(self) -> date | None:
        """O dia da reunião: o do conteúdo ganha do nome do arquivo."""
        if self.inicio is not None:
            return self.inicio.astimezone(FUSO_OPERACAO).date()
        return self.dia_no_nome

    @property
    def divergencia_de_dia(self) -> bool:
        return (
            self.inicio is not None and self.dia_no_nome is not None
            and self.inicio.astimezone(FUSO_OPERACAO).date() != self.dia_no_nome
        )


def _fuso_gmt(sinal_horas: str | None) -> timezone:
    if not sinal_horas:
        return FUSO_OPERACAO  # type: ignore[return-value]
    return timezone(timedelta(hours=int(sinal_horas)))


def dia_do_nome(nome: str, ano_padrao: int) -> date | None:
    """'… - 03 DE SETEMBRO DE 2026.docx' ou '… - 09 DE SETEMBRO.docx'."""
    for m in _RE_DIA_EXTENSO.finditer(nome):
        mes = _MESES.get(_sem_acento(m.group(2)).upper()) or _MESES.get(m.group(2).upper())
        if not mes:
            continue
        ano = int(m.group(3)) if m.group(3) else ano_padrao
        try:
            return date(ano, mes, int(m.group(1)))
        except ValueError:
            return None
    return None


def cnpj_de(*textos: str | None) -> str | None:
    for t in textos:
        if not t:
            continue
        m = _RE_CNPJ.search(t)
        if m:
            return "".join(m.groups())
    return None


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalizar_nome(s: str) -> str:
    return " ".join(_sem_acento(s or "").lower().split())


def empresa_do_nome(arquivo: str) -> str | None:
    """'INSTITUTO X LTDA - 01 DE SETEMBRO DE 2026.docx' -> 'INSTITUTO X LTDA'."""
    stem = Path(arquivo).stem
    if " - " not in stem:
        return None
    empresa = stem.split(" - ")[0].strip()
    if not empresa or _RE_OPP.search(empresa) or _RE_DIA_EXTENSO.search(empresa):
        return None
    return empresa


def chave_empresa(nome: str | None) -> str:
    """Razão social comparável: sem acento, caixa, pontuação e espaço duplo."""
    s = _sem_acento(nome or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(s.split())


def _hms(m: re.Match) -> timedelta:
    return timedelta(hours=int(m.group(1)), minutes=int(m.group(2)), seconds=int(m.group(3)))


def interpretar(paragrafos: list[str], arquivo: str, ano_padrao: int = 2026) -> TranscricaoDocx:
    """
    Lê a estrutura do documento do Meet. Puro.

    Cabeçalho: título OU "Reunião iniciada em …", depois "Participantes",
    a lista, e "Transcrição". Corpo: marcas "HH:MM:SS" e falas "Nome: texto".
    Rodapé: "A reunião terminou depois de …" e o aviso de transcrição editável.
    """
    t = TranscricaoDocx(arquivo=arquivo)
    nome = Path(arquivo).stem
    t.opp_numero = (m.group(0).upper() if (m := _RE_OPP.search(nome)) else None)

    i = 0
    cabecalho: list[str] = []
    while i < len(paragrafos) and paragrafos[i].strip().lower() != "participantes":
        cabecalho.append(paragrafos[i])
        i += 1
    for linha in cabecalho:
        m = _RE_INICIO.search(linha)
        if m:
            a, me, d, h, mi, gmt = m.groups()
            t.inicio = datetime(int(a), int(me), int(d), int(h), int(mi), tzinfo=_fuso_gmt(gmt))
        elif t.titulo is None:
            t.titulo = linha

    if t.inicio is None:
        m = _RE_CARIMBO_MEET.search(nome)
        if m:
            a, me, d, h, mi, gh, gm = m.groups()
            sinal = -1 if gh.startswith("-") else 1
            fuso = timezone(sinal * timedelta(hours=abs(int(gh)), minutes=int(gm)))
            t.inicio = datetime(int(a), int(me), int(d), int(h), int(mi), tzinfo=fuso)

    t.dia_no_nome = dia_do_nome(nome, t.inicio.year if t.inicio else ano_padrao)
    if t.dia_no_nome is None and t.inicio is None:
        m = _RE_CARIMBO_MEET.search(nome)
        if m:
            t.dia_no_nome = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    t.cnpj = cnpj_de(t.titulo, nome)

    # Participantes: a linha seguinte ao rótulo, separada por vírgula.
    if i < len(paragrafos):
        i += 1
        if i < len(paragrafos) and paragrafos[i].strip().lower() != "transcrição":
            t.participantes = [p.strip() for p in paragrafos[i].split(",") if p.strip()]
            i += 1
    if i < len(paragrafos) and _sem_acento(paragrafos[i]).strip().lower() == "transcricao":
        i += 1

    # O mais longo primeiro: "FULANO's Presentation" antes de "FULANO".
    nomes = sorted(t.participantes, key=len, reverse=True)
    marca_atual: timedelta | None = None
    for par in paragrafos[i:]:
        s = par.strip()
        if (m := _RE_FIM.search(s)):
            t.duracao = _hms(m)
            break
        if _RE_AVISO.search(s):
            break
        if (m := _RE_MARCA.match(s)):
            marca_atual = _hms(m)
            t.linhas.append(Linha(participante="", texto="", offset=marca_atual))  # marcador
            continue
        quem, fala = None, None
        for n in nomes:
            if s.startswith(n + ":"):
                quem, fala = n, s[len(n) + 1:].strip()
                break
        if quem is None and (m := _RE_FALA_GENERICA.match(s)):
            quem, fala = m.group(1).strip(), m.group(2).strip()
        if quem is None:
            # Continuação da fala anterior (quebra de parágrafo no meio).
            falas = [x for x in t.linhas if x.participante]
            if falas:
                falas[-1].texto = f"{falas[-1].texto} {s}".strip()
            continue
        if fala:
            t.linhas.append(Linha(participante=quem, texto=fala))
    return t


def distribuir_horarios(linhas: list[Linha], duracao: timedelta | None) -> list[tuple[timedelta, timedelta, Linha]]:
    """
    (inicio, fim, fala) de cada fala, a partir das marcas de 5 em 5 minutos.

    Entre duas marcas, as falas dividem o intervalo proporcionalmente ao
    número de caracteres. Antes da primeira marca, o intervalo é os 5
    minutos que a antecedem; depois da última, até o fim da reunião (ou
    mais 5 minutos, se o fim não veio no documento).
    """
    blocos: list[tuple[timedelta | None, list[Linha]]] = [(None, [])]
    for ln in linhas:
        if not ln.participante:
            blocos.append((ln.offset, []))
        else:
            blocos[-1][1].append(ln)

    saida: list[tuple[timedelta, timedelta, Linha]] = []
    for k, (ini, falas) in enumerate(blocos):
        if not falas:
            continue
        proxima = next((b[0] for b in blocos[k + 1:] if b[0] is not None), None)
        if ini is None:
            fim = proxima if proxima is not None else (duracao or PASSO_MARCA)
            ini = max(timedelta(0), fim - PASSO_MARCA)
        else:
            if proxima is not None:
                fim = proxima
            elif duracao is not None and duracao > ini:
                fim = duracao
            else:
                fim = ini + PASSO_MARCA
        if fim <= ini:
            fim = ini + PASSO_MARCA
        total = sum(max(len(f.texto), 1) for f in falas)
        acumulado = 0
        for f in falas:
            peso = max(len(f.texto), 1)
            a = ini + (fim - ini) * (acumulado / total)
            acumulado += peso
            b = ini + (fim - ini) * (acumulado / total)
            saida.append((a, b, f))
    return saida


def falas_do_documento(t: TranscricaoDocx, inicio: datetime) -> list[Fala]:
    """As falas com horário absoluto, no formato da coleta automática."""
    base = inicio.astimezone(timezone.utc)
    return [
        Fala(inicio=base + a, fim=base + b, participante=ln.participante, texto=ln.texto)
        for a, b, ln in distribuir_horarios(t.linhas, t.duracao)
    ]


def duracao_min(t: TranscricaoDocx, padrao: int = 30) -> int:
    if t.duracao is None:
        return padrao
    return max(5, min(480, math.ceil(t.duracao.total_seconds() / 60)))


# ── Escolha da tarefa (puro) ─────────────────────────────────────────

JANELA_SUGESTAO_DIAS = 3


@dataclass
class Plano:
    acao: str                    # ANEXAR | CRIAR_REUNIAO | CRIAR_TUDO | JA_TEM | REVISAR | ERRO
    candidato: dict | None = None
    avisos: list[str] = field(default_factory=list)


def dia_local(dt: datetime) -> date:
    return dt.astimezone(FUSO_OPERACAO).date()


def escolher(
    candidatos: list[dict], dia: date | None, inicio: datetime | None,
    usados: set, sobrescrever: bool = False,
) -> Plano:
    """
    Qual tarefa recebe a transcrição. `candidatos` são linhas com
    tarefa_id, prazo, reuniao_id, rt_status (e o que mais for para a tela).
    `usados` são tarefas já tomadas por outro arquivo desta mesma rodada.
    """
    if dia is None:
        return Plano("REVISAR", avisos=["Sem data: nem o conteúdo nem o nome do arquivo dizem o dia."])

    livres = [c for c in candidatos if c["tarefa_id"] not in usados]
    no_dia = [c for c in livres if dia_local(c["prazo"]) == dia]
    prontas = [c for c in no_dia if c.get("rt_status") == "pronta"]
    abertas = no_dia if sobrescrever else [c for c in no_dia if c.get("rt_status") != "pronta"]

    if abertas:
        if len(abertas) > 1 and inicio is None:
            return Plano("REVISAR", avisos=[
                f"{len(abertas)} reuniões no dia e o documento não tem horário: escolha com --mapa."
            ])
        if inicio is not None:
            abertas = sorted(abertas, key=lambda c: abs((c["prazo"] - inicio).total_seconds()))
        c = abertas[0]
        avisos = []
        if inicio is not None:
            dif = abs((c["prazo"] - inicio).total_seconds()) / 3600
            if dif > 2:
                avisos.append(f"Horário da tarefa difere {dif:.1f}h do início da transcrição.")
        if c.get("cancelada_em") is not None:
            avisos.append("Tarefa está CANCELADA no HIPO, mas a transcrição mostra que a reunião aconteceu.")
        return Plano("ANEXAR" if c.get("reuniao_id") else "CRIAR_REUNIAO", c, avisos)

    if prontas:
        return Plano("JA_TEM", prontas[0], ["Já tem transcrição pronta (use --sobrescrever para trocar)."])

    perto = [
        c for c in livres
        if c.get("rt_status") != "pronta"
        and abs((dia_local(c["prazo"]) - dia).days) <= JANELA_SUGESTAO_DIAS
    ]
    if perto:
        perto.sort(key=lambda c: abs((dia_local(c["prazo"]) - dia).days))
        s = perto[0]
        return Plano("REVISAR", s, [
            f"Nenhuma reunião no dia {dia:%d/%m}; há uma em {dia_local(s['prazo']):%d/%m} "
            f"(tarefa {s['tarefa_id']}). Use --mapa ARQUIVO={s['tarefa_id']} ou ARQUIVO=novo."
        ])
    if inicio is None:
        return Plano("REVISAR", avisos=["Não há tarefa no dia e o documento não tem horário para criar uma."])
    return Plano("CRIAR_TUDO")


def aplicar_mapa(mapa: list[str]) -> list[tuple[str, str]]:
    """'TRECHO_DO_ARQUIVO=uuid|novo' -> [(trecho_normalizado, alvo)]."""
    saida = []
    for item in mapa or []:
        if "=" not in item:
            raise SystemExit(f"--mapa inválido: {item!r} (esperado TRECHO=uuid ou TRECHO=novo)")
        trecho, alvo = item.rsplit("=", 1)
        saida.append((normalizar_nome(trecho), alvo.strip().lower()))
    return saida


def alvo_do_mapa(arquivo: str, mapa: list[tuple[str, str]]) -> str | None:
    n = normalizar_nome(arquivo)
    for trecho, alvo in mapa:
        if trecho and trecho in n:
            return alvo
    return None


# ── Banco ────────────────────────────────────────────────────────────

_CANDIDATOS = """
    SELECT t.id AS tarefa_id, t.titulo, t.prazo, t.concluida_em, t.cancelada_em,
           t.criado_por, t.criado_em, t.responsavel_id, u.nome AS responsavel_nome,
           r.id AS reuniao_id, r.duracao_min, rt.status AS rt_status
      FROM tarefas t
      LEFT JOIN usuarios u ON u.id = t.responsavel_id
      LEFT JOIN reunioes r ON r.tarefa_id = t.id
      LEFT JOIN reuniao_transcricoes rt ON rt.reuniao_id = r.id
     WHERE t.oportunidade_id = $1
       AND t.tipo IN ('reuniao', 'visita')
       AND t.prazo >= $2 AND t.prazo < $3
     ORDER BY t.prazo
"""


_CANDIDATO_POR_ID = _CANDIDATOS.split("AND t.prazo >= $2")[0] + "AND t.id = $2\n"


async def achar_oportunidade(conn, t: TranscricaoDocx) -> tuple[dict | None, str | None]:
    """
    A oportunidade do arquivo. Pelo OPP do nome; sem ele, pelo CNPJ do título.
    CNPJ com várias oportunidades desempata pela que tem reunião no dia.
    """
    opp, erro = await _achar_oportunidade(conn, t)
    if opp is not None or not isinstance(erro, list):
        return opp, erro
    origem = f"CNPJ {t.cnpj}" if t.cnpj else f"A razão social '{empresa_do_nome(t.arquivo)}'"
    if t.dia is not None:
        com_reuniao = []
        for o in erro:
            if any(dia_local(c["prazo"]) == t.dia for c in await candidatos(conn, o["id"], t.dia)):
                com_reuniao.append(o)
        if len(com_reuniao) == 1:
            return com_reuniao[0], None
    return None, (f"{origem} tem {len(erro)} oportunidades e nenhuma se destaca "
                  f"pela reunião no dia: renomeie o arquivo com o OPP.")


async def _achar_oportunidade(conn, t: TranscricaoDocx):
    if t.opp_numero:
        o = await conn.fetchrow(
            """SELECT o.id, o.numero, c.id AS conta_id,
                      COALESCE(c.nome_fantasia, c.razao_social) AS empresa, c.razao_social
                 FROM oportunidades o JOIN contas c ON c.id = o.conta_id
                WHERE o.numero = $1""",
            t.opp_numero,
        )
        return (dict(o), None) if o else (None, f"{t.opp_numero} não existe no HIPO.")
    if t.cnpj:
        rows = await conn.fetch(
            """SELECT o.id, o.numero, c.id AS conta_id,
                      COALESCE(c.nome_fantasia, c.razao_social) AS empresa, c.razao_social
                 FROM oportunidades o JOIN contas c ON c.id = o.conta_id
                WHERE c.cnpj = $1 ORDER BY o.criado_em DESC""",
            t.cnpj,
        )
        if len(rows) == 1:
            return dict(rows[0]), None
        if not rows:
            return None, f"Nenhuma oportunidade para o CNPJ {t.cnpj}."
        return None, [dict(r) for r in rows]
    empresa = empresa_do_nome(t.arquivo)
    if empresa:
        # Último recurso: o nome do arquivo começa pela razão social
        # ("INSTITUTO X LTDA - 01 DE SETEMBRO.docx"). Comparação exata depois
        # de tirar acento, caixa e pontuação: parecido não basta.
        alvo = chave_empresa(empresa)
        # Filtro grosso no banco por uma palavra SEM acento (o ILIKE não
        # ignora acento, e o cadastro pode ter ou não ter); o fino é o
        # `chave_empresa` abaixo.
        palavras = [w for w in re.split(r"[^\w]+", empresa) if len(w) >= 4 and w == _sem_acento(w)]
        primeira = max(palavras, key=len) if palavras else ""
        rows = await conn.fetch(
            """SELECT o.id, o.numero, c.id AS conta_id,
                      COALESCE(c.nome_fantasia, c.razao_social) AS empresa, c.razao_social,
                      c.nome_fantasia
                 FROM oportunidades o JOIN contas c ON c.id = o.conta_id
                WHERE c.razao_social ILIKE '%' || $1 || '%'
                   OR c.nome_fantasia ILIKE '%' || $1 || '%'
                ORDER BY o.criado_em DESC""",
            primeira,
        )
        rows = [dict(r) for r in rows
                if alvo in (chave_empresa(r["razao_social"]), chave_empresa(r["nome_fantasia"]))]
        for r in rows:
            r.pop("nome_fantasia", None)
        if len(rows) == 1:
            return rows[0], None
        if rows:
            return None, rows
        return None, (f"Arquivo sem OPP no nome e nenhuma conta com a razão social "
                      f"'{empresa}': renomeie o arquivo com o OPP.")
    return None, "Arquivo sem OPP-AAAA-NNNNN no nome e sem CNPJ no título."


async def candidatos(conn, oportunidade_id, dia: date) -> list[dict]:
    ini = datetime.combine(dia - timedelta(days=JANELA_SUGESTAO_DIAS), time.min, tzinfo=FUSO_OPERACAO)
    fim = datetime.combine(dia + timedelta(days=JANELA_SUGESTAO_DIAS + 1), time.min, tzinfo=FUSO_OPERACAO)
    return [dict(r) for r in await conn.fetch(_CANDIDATOS, oportunidade_id, ini, fim)]


async def usuario_por(conn, termo: str) -> dict:
    rows = await conn.fetch(
        """SELECT id, nome, email FROM usuarios
            WHERE COALESCE(ativo, TRUE)
              AND (lower(email) = lower($1) OR nome ILIKE '%' || $1 || '%')""",
        termo,
    )
    if len(rows) != 1:
        nomes = ", ".join(f"{r['nome']} <{r['email']}>" for r in rows) or "nenhum"
        raise SystemExit(f"'{termo}' deveria achar 1 usuário ativo; achou {len(rows)}: {nomes}")
    return dict(rows[0])


async def tipo_id(conn, sigla: str | None):
    if not sigla:
        return None
    tid = await conn.fetchval("SELECT id FROM tipos_reuniao WHERE sigla = $1", sigla.upper())
    if tid is None:
        raise SystemExit(f"Tipo de reunião '{sigla}' não existe em tipos_reuniao.")
    return tid


async def participantes_internos(conn, nomes: list[str], excluir: set) -> list:
    """Usuários do HIPO que aparecem na lista de participantes do Meet."""
    usuarios = await conn.fetch("SELECT id, nome FROM usuarios WHERE COALESCE(ativo, TRUE)")
    por_nome = {normalizar_nome(u["nome"]): u["id"] for u in usuarios}
    ids = []
    for n in nomes:
        uid = por_nome.get(normalizar_nome(n))
        if uid and uid not in excluir and uid not in ids:
            ids.append(uid)
    return ids


async def gravar_transcricao(conn, reuniao_id, t: TranscricaoDocx, inicio: datetime,
                             sobrescrever: bool) -> bool:
    falas = falas_do_documento(t, inicio)
    texto = texto_corrido(falas)
    if not texto.strip():
        raise ValueError("documento sem nenhuma fala")
    status = await conn.fetchval(
        "SELECT status FROM reuniao_transcricoes WHERE reuniao_id = $1", reuniao_id,
    )
    if status == "pronta" and not sobrescrever:
        return False
    await conn.execute(
        """
        INSERT INTO reuniao_transcricoes (
            reuniao_id, status, motivo, erro, tentativas, ultima_tentativa_em,
            conferencias, documento_url, idioma, entradas, texto, coletada_em,
            resumo, proximos_passos, resumo_modelo, resumo_em, resumo_erro
        )
        VALUES ($1, 'pronta', NULL, NULL, 0, NULL, $2, NULL, 'pt-BR', $3::jsonb, $4, NOW(),
                NULL, NULL, NULL, NULL, NULL)
        ON CONFLICT (reuniao_id) DO UPDATE
           SET status = 'pronta', motivo = NULL, erro = NULL,
               conferencias = EXCLUDED.conferencias, documento_url = NULL,
               idioma = EXCLUDED.idioma, entradas = EXCLUDED.entradas,
               texto = EXCLUDED.texto, coletada_em = NOW(),
               resumo = NULL, proximos_passos = NULL, resumo_modelo = NULL,
               resumo_em = NULL, resumo_erro = NULL, atualizado_em = NOW()
        """,
        reuniao_id,
        # Rastro de origem no lugar dos conferenceRecords: diz de onde veio o texto.
        [f"importado-docx:{t.arquivo}"],
        json.dumps(entradas_json(falas), ensure_ascii=False),
        texto,
    )
    return True


async def executar(a) -> int:
    import asyncpg
    from config import settings
    from services import agenda as regras_agenda
    from services import coleta_transcricao, resumo_reuniao

    pasta = Path(a.pasta)
    arquivos = sorted(p for p in pasta.rglob("*.docx") if not p.name.startswith("~$"))
    if not arquivos:
        raise SystemExit(f"Nenhum .docx em {pasta}")
    mapa = aplicar_mapa(a.mapa)

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        resp = await usuario_por(conn, a.responsavel)
        operador = await usuario_por(conn, a.por) if a.por else None
        if a.commit and operador is None:
            raise SystemExit("--commit exige --por <e-mail de quem está lançando> (vai em criado_por).")
        tid = await tipo_id(conn, a.tipo)

        docs = []
        for p in arquivos:
            try:
                d = interpretar(paragrafos_docx(p), p.name)
            except Exception as e:  # arquivo corrompido não para os outros
                docs.append((p, None, f"não consegui ler o .docx: {e}"))
                continue
            docs.append((p, d, None))
        # Quem tem horário escolhe primeiro: resolve dois arquivos da mesma
        # empresa no mesmo dia (o com horário pega a tarefa certa, o outro a que sobra).
        docs.sort(key=lambda x: (x[1] is None or x[1].inicio is None, x[0].name))

        print(f"responsável : {resp['nome']} <{resp['email']}>")
        print(f"lançado por : {operador['nome'] if operador else '(dry-run)'}")
        print(f"tipo criado : {a.tipo or '(sem tipo)'}")
        print(f"modo        : {'COMMIT' if a.commit else 'DRY-RUN (nada é gravado)'}\n")

        usados: set = set()
        relatorio = []
        for p, d, erro in docs:
            linha = {"arquivo": p.name, "acao": "ERRO", "opp": "", "empresa": "", "dia": "",
                     "inicio": "", "falas": "", "tarefa_id": "", "reuniao_id": "",
                     "responsavel_tarefa": "", "avisos": "", "resultado": ""}
            relatorio.append(linha)
            if d is None:
                linha["avisos"] = erro
                continue
            linha.update(dia=f"{d.dia:%d/%m/%Y}" if d.dia else "",
                         inicio=d.inicio.astimezone(FUSO_OPERACAO).strftime("%H:%M") if d.inicio else "",
                         falas=str(sum(1 for x in d.linhas if x.participante)))
            avisos = []
            if d.divergencia_de_dia:
                avisos.append(f"Nome do arquivo diz {d.dia_no_nome:%d/%m}, o conteúdo diz {d.dia:%d/%m}: vale o conteúdo.")
            if not any(x.participante for x in d.linhas):
                linha["avisos"] = ("Documento sem falas no formato da transcrição do Meet "
                                  "(anotações do Gemini, conversa de WhatsApp...): ficou de fora.")
                continue

            opp, erro = await achar_oportunidade(conn, d)
            if opp is None:
                linha["avisos"] = erro
                continue
            linha.update(opp=opp["numero"], empresa=opp["empresa"])

            cands = await candidatos(conn, opp["id"], d.dia) if d.dia else []
            alvo = alvo_do_mapa(p.name, mapa)
            if alvo == "novo":
                plano = Plano("CRIAR_TUDO") if d.inicio else Plano(
                    "REVISAR", avisos=["--mapa novo exige horário no documento."])
            elif alvo:
                c = next((c for c in cands if str(c["tarefa_id"]) == alvo), None)
                if c is None:
                    row = await conn.fetchrow(_CANDIDATO_POR_ID, opp["id"], UUID(alvo))
                    c = dict(row) if row else None
                plano = (Plano("ANEXAR" if c["reuniao_id"] else "CRIAR_REUNIAO", c, ["escolhida por --mapa"])
                         if c else Plano("ERRO", avisos=[f"--mapa: tarefa {alvo} não é reunião da {opp['numero']}."]))
                if c and c.get("rt_status") == "pronta" and not a.sobrescrever:
                    plano = Plano("JA_TEM", c, ["Já tem transcrição pronta (use --sobrescrever)."])
            else:
                plano = escolher(cands, d.dia, d.inicio, usados, a.sobrescrever)

            linha["acao"] = plano.acao
            linha["avisos"] = " | ".join(avisos + plano.avisos)
            c = plano.candidato
            if c:
                linha.update(tarefa_id=str(c["tarefa_id"]),
                             reuniao_id=str(c["reuniao_id"] or ""),
                             responsavel_tarefa=c.get("responsavel_nome") or "")
                if plano.acao in ("ANEXAR", "CRIAR_REUNIAO", "JA_TEM"):
                    usados.add(c["tarefa_id"])
                    if c["responsavel_id"] != resp["id"]:
                        linha["avisos"] = " | ".join(filter(None, [
                            linha["avisos"], f"Tarefa é de {c.get('responsavel_nome')}, não de {resp['nome']}."]))

            if plano.acao not in ("ANEXAR", "CRIAR_REUNIAO", "CRIAR_TUDO") or not a.commit:
                continue

            # ── Grava ────────────────────────────────────────────────
            try:
                async with conn.transaction():
                    if plano.acao == "CRIAR_TUDO":
                        inicio = d.inicio
                        dur = duracao_min(d)
                        fim = inicio + timedelta(minutes=dur)
                        titulo = regras_agenda.rotulo(
                            sigla_tipo=(a.tipo or "").upper() or None, empresa=opp["empresa"],
                            anfitriao=resp["nome"], modalidade="online",
                        ) or "Reunião"
                        tarefa_id = await conn.fetchval(
                            """
                            INSERT INTO tarefas (oportunidade_id, tipo, titulo, descricao,
                                responsavel_id, prazo, concluida_em, resultado,
                                criado_por, criado_em, atualizado_em)
                            VALUES ($1, 'reuniao', $2, $3, $4, $5, $6, $7, $8, $5, NOW())
                            RETURNING id
                            """,
                            opp["id"], titulo[:200],
                            f"Reunião registrada a posteriori a partir da transcrição do Google Meet "
                            f"(arquivo: {p.name}).",
                            resp["id"], inicio, fim,
                            "Reunião realizada — transcrição importada do Google Meet.",
                            operador["id"],
                        )
                        reuniao_id = await conn.fetchval(
                            """
                            INSERT INTO reunioes (tarefa_id, duracao_min, tipo_id, modalidade,
                                criado_por, agendado_por, desfecho, desfecho_em, desfecho_por,
                                desfecho_observacao, desfecho_antecedencia_horas,
                                criado_em, atualizado_em)
                            VALUES ($1, $2, $3, 'online', $4, NULL, 'realizada', $5, $4,
                                    'Registrada a partir da transcrição do Google Meet.', $6,
                                    $7, NOW())
                            RETURNING id
                            """,
                            tarefa_id, dur, tid, operador["id"], fim,
                            regras_agenda.antecedencia_horas(inicio, fim), inicio,
                        )
                        for uid in await participantes_internos(conn, d.participantes, {resp["id"]}):
                            await conn.execute(
                                "INSERT INTO reuniao_participantes (reuniao_id, usuario_id) "
                                "VALUES ($1, $2) ON CONFLICT DO NOTHING", reuniao_id, uid,
                            )
                        inicio_texto = inicio
                    else:
                        tarefa_id = c["tarefa_id"]
                        reuniao_id = c["reuniao_id"]
                        if plano.acao == "CRIAR_REUNIAO":
                            concluida = c["concluida_em"]
                            reuniao_id = await conn.fetchval(
                                """
                                INSERT INTO reunioes (tarefa_id, duracao_min, tipo_id, modalidade,
                                    criado_por, agendado_por, desfecho, desfecho_em, desfecho_por,
                                    desfecho_observacao, desfecho_antecedencia_horas,
                                    criado_em, atualizado_em)
                                VALUES ($1, $2, $3, 'online', $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                                RETURNING id
                                """,
                                tarefa_id, duracao_min(d), tid, operador["id"],
                                # Crédito do agendamento: quem criou a tarefa (mesma regra do desfecho).
                                c["criado_por"],
                                "realizada" if concluida else None,
                                concluida,
                                operador["id"] if concluida else None,
                                "Registrada a partir da transcrição do Google Meet." if concluida else None,
                                regras_agenda.antecedencia_horas(c["prazo"], concluida) if concluida else None,
                                # Retroativo: o dia em que a tarefa (o agendamento) nasceu.
                                c["criado_em"],
                            )
                        # Sem horário no documento, o relógio das falas parte do prazo da tarefa.
                        inicio_texto = d.inicio or c["prazo"]
                    gravou = await gravar_transcricao(conn, reuniao_id, d, inicio_texto, a.sobrescrever)
                linha.update(tarefa_id=str(tarefa_id), reuniao_id=str(reuniao_id),
                             resultado="gravada" if gravou else "já tinha transcrição")
                if c and c.get("concluida_em") is None and c.get("cancelada_em") is None:
                    linha["avisos"] = " | ".join(filter(None, [
                        linha["avisos"], "Tarefa segue EM ABERTO: registrar o desfecho na tela."]))
            except Exception as e:
                linha["resultado"] = f"FALHOU: {e}"
                continue

            if gravou and not a.sem_resumo and resumo_reuniao.configurado():
                est = await coleta_transcricao.resumir(conn, reuniao_id)
                linha["resultado"] += " + resumo" if est.get("resumo") else f" (resumo: {est.get('resumo_erro')})"

        # ── Saída ────────────────────────────────────────────────────
        for r in relatorio:
            print(f"[{r['acao']:<13}] {r['arquivo']}")
            print(f"    {r['opp'] or '-'} {r['empresa'] or ''} | dia {r['dia'] or '?'} {r['inicio']} | "
                  f"{r['falas'] or 0} falas | tarefa {r['tarefa_id'] or '-'} ({r['responsavel_tarefa'] or '-'})")
            if r["avisos"]:
                print(f"    ! {r['avisos']}")
            if r["resultado"]:
                print(f"    = {r['resultado']}")
        cont: dict[str, int] = {}
        for r in relatorio:
            cont[r["acao"]] = cont.get(r["acao"], 0) + 1
        print("\nresumo:", ", ".join(f"{k} {v}" for k, v in sorted(cont.items())))
        if not a.commit:
            print("DRY-RUN: nada foi gravado. ANEXAR/CRIAR_* serão gravados com --commit; "
                  "REVISAR/ERRO/JA_TEM ficam de fora até decidir com --mapa.")
        if a.csv:
            with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(relatorio[0].keys()), delimiter=";")
                w.writeheader()
                w.writerows(relatorio)
            print(f"csv: {a.csv}")
        falhas = [r for r in relatorio if r["resultado"].startswith("FALHOU")]
        return 1 if falhas else 0
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Importa transcrições do Meet (.docx) para o HIPO")
    ap.add_argument("--pasta", required=True, help="pasta com os .docx (busca recursiva)")
    ap.add_argument("--responsavel", required=True,
                    help="e-mail ou trecho do nome de quem conduziu (responsável das tarefas criadas)")
    ap.add_argument("--por", help="e-mail de quem está lançando (criado_por); obrigatório com --commit")
    ap.add_argument("--tipo", default="AP", help="sigla do tipo das reuniões criadas (padrão AP; '' = sem tipo)")
    ap.add_argument("--mapa", action="append", default=[],
                    help="TRECHO_DO_ARQUIVO=<uuid da tarefa> ou TRECHO=novo (repetível)")
    ap.add_argument("--sobrescrever", action="store_true", help="troca transcrição já pronta")
    ap.add_argument("--sem-resumo", action="store_true", help="não chama a IA")
    ap.add_argument("--csv", help="grava o relatório neste CSV")
    ap.add_argument("--commit", action="store_true", help="grava (sem isto é dry-run)")
    return asyncio.run(executar(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
