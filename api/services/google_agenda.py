"""
HIPO — Espelho da agenda no Google Calendar.

O evento é criado DENTRO do calendário do anfitrião, por uma conta de
serviço com delegação em todo o domínio (domain-wide delegation) do
Workspace. Quem manda o convite para o cliente é o próprio Google, com o
nome do vendedor no remetente — que é o ponto: um convite que chega como
"HIPO <no-reply@...>" é um convite que o cliente ignora.

Ninguém precisa conectar nada. A alternativa (OAuth por usuário) exigiria
cada EV autorizar, guardar refresh token criptografado e um caminho de
fallback para quem ainda não autorizou — três peças novas para resolver um
problema que uma configuração única no Admin Console já resolve.

═══ COMO LIGAR EM PRODUÇÃO (uma vez) ═══════════════════════════════════

  1. Google Cloud Console → criar projeto (ou usar um existente) →
     APIs & Services → habilitar a "Google Calendar API".
  2. Criar uma Service Account. Anotar o Client ID numérico dela.
  3. Gerar uma chave JSON da conta de serviço e gravá-la na EC2 em
     /home/hipo/app/google-sa.json, com dono `hipo` e modo 600.
  4. Admin Console do Workspace → Segurança → Controle de acesso a dados
     → Controles de API → Delegação em todo o domínio → Adicionar novo:
       Client ID: o numérico do passo 2
       Escopos:   https://www.googleapis.com/auth/calendar.events
  5. No /home/hipo/app/.env:
       GOOGLE_SA_ARQUIVO=/home/hipo/app/google-sa.json
  6. Instalar as bibliotecas NA MÃO — o deploy faz rsync e reinicia, NÃO
     roda pip install:
       sudo -iu hipo pip install google-api-python-client==2.149.0 \
                                google-auth==2.35.0
  7. Reiniciar o serviço.

O DIAGNÓSTICO de tudo isso é `problemas()`, que roda sem chamar a rede.

═══ AS TRÊS REGRAS DESTE MÓDULO ════════════════════════════════════════

DESLIGADO É ESTADO VÁLIDO. `GOOGLE_SA_ARQUIVO` vazio sobe a API igual, e
a reunião é criada igual — só não vira evento. Mesma regra do S3 dos
anexos, da chave da IA e do SES: configuração de recurso acessório não
pode impedir o sistema de subir, e no CI nenhum desses existe.

FALHA NÃO DERRUBA A REUNIÃO. Toda função devolve o erro em vez de
levantar até o router. A reunião nasce no HIPO mesmo que o Google recuse,
e o erro fica visível na tela com um botão de tentar de novo. O contrário
— transação que aborta porque o Google estava fora do ar — perderia o
registro do que foi combinado com o cliente por causa de uma indisponi-
bilidade de terceiro.

MAS FALHA NÃO PODE SER SILENCIOSA. O erro vira coluna (`reunioes.
google_erro`), não linha de log: um convite que o cliente nunca recebeu é
uma reunião que não vai acontecer, e descobrir isso pelo silêncio custa a
reunião. Ver a nota equivalente em services/email_ses.py, que resolve o
mesmo dilema ao contrário porque lá quem chama é um cron, não uma tela.

═══ SÍNCRONO DENTRO DE UM MUNDO ASSÍNCRONO ═════════════════════════════

O cliente do Google é síncrono, como o boto3. Diferente do boto3, ele É
chamado pela API — e uma chamada de rede de ~1s bloqueando o event loop
travaria TODAS as requisições do worker enquanto durasse. Por isso cada
função pública é `async` e joga o trabalho em `asyncio.to_thread`. É
exatamente o "se um dia for, o envio precisa ir para uma thread" que o
docstring de email_ses.py previu.

Os imports das bibliotecas do Google são LOCAIS, dentro das funções, pelo
mesmo motivo do `import boto3` de email_ses: o pacote pode não estar
instalado (CI, máquina de desenvolvimento, EC2 antes do passo 6 acima) e
o import no topo do arquivo derrubaria a API inteira no boot.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from config import settings
from services.agenda import FUSO_OPERACAO

log = logging.getLogger("hipo.google_agenda")

ESCOPOS = ["https://www.googleapis.com/auth/calendar.events"]

# Mandar o convite para todo mundo (anfitrião, nossa equipe e o cliente).
# É o parâmetro que faz o e-mail sair; sem ele o evento aparece só na
# agenda de quem foi adicionado, sem aviso nenhum.
ENVIAR_CONVITES = "all"


@dataclass(frozen=True)
class ResultadoSync:
    """
    O que aconteceu com a tentativa de sincronizar.

    Nunca levanta: quem chama grava `erro` na coluna e segue. `ok=False`
    com `erro=None` é impossível por construção — ou deu certo, ou tem uma
    frase em português dizendo o quê.
    """
    ok: bool
    event_id: str | None = None
    calendar_id: str | None = None
    link: str | None = None
    erro: str | None = None


@dataclass
class DadosEvento:
    """O que o Google precisa saber. Montado pelo router, a partir do banco."""
    titulo: str
    inicio: datetime
    fim: datetime
    anfitriao_email: str
    descricao: str = ""
    endereco: str | None = None
    convidados: list[str] = field(default_factory=list)
    criar_meet: bool = False


# ── Configuração ─────────────────────────────────────────────────────


def configurado() -> bool:
    """Ligado? Vazio = recurso desligado, e isso é estado válido."""
    return bool((getattr(settings, "GOOGLE_SA_ARQUIVO", "") or "").strip())


def problemas() -> list[str]:
    """
    Devolve a lista de problemas. Vazia = pronto para sincronizar.

    Checagem local, sem chamar a rede: existe para a tela dizer "falta o
    arquivo da conta de serviço" em vez de um erro críptico de OAuth
    quinze segundos depois. Mesmo papel de
    `email_ses.verificar_configuracao()`.
    """
    achados: list[str] = []
    caminho = (getattr(settings, "GOOGLE_SA_ARQUIVO", "") or "").strip()
    if not caminho:
        achados.append(
            "GOOGLE_SA_ARQUIVO não definido no .env — a integração com o "
            "Google Calendar está desligada."
        )
    else:
        if not os.path.isfile(caminho):
            achados.append(f"Arquivo da conta de serviço não encontrado: {caminho}")
        elif not os.access(caminho, os.R_OK):
            # O mesmo tropeço que derrubou o ensaio do fechamento diário em
            # 31/08: arquivo 600 de um dono e processo rodando como outro.
            achados.append(
                f"Sem permissão de leitura no arquivo da conta de serviço: {caminho}"
            )
    try:  # pragma: no cover - depende do ambiente
        import google.oauth2.service_account  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
    except ImportError:
        achados.append(
            "Bibliotecas do Google não instaladas na máquina "
            "(pip install google-api-python-client google-auth)."
        )
    return achados


# ── O cliente ────────────────────────────────────────────────────────


def _servico(email_anfitriao: str):  # pragma: no cover - exige rede/credencial
    """
    Um cliente do Calendar PERSONIFICANDO o anfitrião.

    `with_subject` é a delegação em ação: a conta de serviço age como
    aquela pessoa, então o evento nasce no calendário DELA e o convite sai
    com o nome dela. Sem isso o evento moraria num calendário da conta de
    serviço, que ninguém abre.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credenciais = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SA_ARQUIVO, scopes=ESCOPOS
    ).with_subject(email_anfitriao)

    # cache_discovery=False: o cache em disco do discovery escreve em
    # ~/.cache e enche o log de aviso quando o usuário do systemd não tem
    # HOME gravável — barulho puro num serviço.
    return build("calendar", "v3", credentials=credenciais, cache_discovery=False)


def _corpo(dados: DadosEvento) -> dict:
    fuso = getattr(settings, "GOOGLE_CALENDAR_FUSO", "") or str(FUSO_OPERACAO)
    corpo: dict = {
        "summary": dados.titulo,
        "description": dados.descricao or "",
        "start": {"dateTime": dados.inicio.isoformat(), "timeZone": fuso},
        "end": {"dateTime": dados.fim.isoformat(), "timeZone": fuso},
        # O anfitrião entra como convidado além de dono do calendário: é o
        # que faz o evento aparecer como "aceito" para ele e o que permite
        # ao cliente ver com quem vai falar na lista de participantes.
        "attendees": [{"email": e} for e in _emails(dados)],
    }
    if dados.endereco:
        corpo["location"] = dados.endereco
    if dados.criar_meet:
        corpo["conferenceData"] = {
            "createRequest": {
                # O requestId é a chave de idempotência do Google: repetir o
                # mesmo id não cria uma segunda sala. Aleatório por chamada
                # porque cada criação é uma sala nova mesmo.
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
    return corpo


def _emails(dados: DadosEvento) -> list[str]:
    """
    Anfitrião primeiro, depois os convidados, sem repetir e sem vazio.

    A deduplicação é por minúscula: o Google recusa o evento inteiro com
    400 quando o mesmo endereço aparece duas vezes na lista, e "Ana@x.com"
    digitado no formulário ao lado de "ana@x.com" vindo do cadastro é
    exatamente como isso acontece na vida real.
    """
    vistos: set[str] = set()
    saida: list[str] = []
    for e in [dados.anfitriao_email, *dados.convidados]:
        limpo = (e or "").strip()
        chave = limpo.lower()
        if limpo and chave not in vistos:
            vistos.add(chave)
            saida.append(limpo)
    return saida


def _traduzir(erro: Exception) -> str:
    """
    Erro do Google em uma frase acionável.

    Os três casos abaixo são os que acontecem na prática, e cada um tem uma
    saída diferente: o 403 é configuração no Admin Console, o 404 é evento
    apagado à mão na agenda, e o resto é rede. Devolver "HttpError 403" na
    tela obrigaria a abrir o log do servidor para descobrir qual dos três.
    """
    texto = str(erro)
    codigo = getattr(getattr(erro, "resp", None), "status", None)
    if codigo == 403 or "unauthorized_client" in texto or "forbidden" in texto.lower():
        return (
            "O Google recusou o acesso. Confira a delegação em todo o domínio "
            "no Admin Console: o Client ID da conta de serviço precisa do "
            "escopo calendar.events."
        )
    if codigo == 404:
        return "O evento não existe mais no Google Calendar."
    if codigo == 400:
        return f"O Google recusou os dados do evento: {texto}"
    return f"Não foi possível falar com o Google Calendar: {texto}"


# ── Operações ────────────────────────────────────────────────────────


def _criar_sync(dados: DadosEvento) -> ResultadoSync:  # pragma: no cover
    from googleapiclient.errors import HttpError

    try:
        servico = _servico(dados.anfitriao_email)
        evento = servico.events().insert(
            calendarId="primary",
            body=_corpo(dados),
            sendUpdates=ENVIAR_CONVITES,
            conferenceDataVersion=1 if dados.criar_meet else 0,
        ).execute()
    except HttpError as e:
        return ResultadoSync(ok=False, erro=_traduzir(e))
    except Exception as e:  # blindagem: credencial inválida, DNS, disco
        return ResultadoSync(ok=False, erro=_traduzir(e))

    return ResultadoSync(
        ok=True,
        event_id=evento.get("id"),
        calendar_id=dados.anfitriao_email,
        link=_link_da_reuniao(evento),
    )


def _link_da_reuniao(evento: dict) -> str | None:
    """
    O link do Meet, se houver; senão o link do próprio evento.

    Os dois servem para coisas diferentes — um entra na reunião, o outro
    abre a agenda — mas para a tela a pergunta é uma só: "onde eu clico".
    """
    entrada = evento.get("hangoutLink")
    if entrada:
        return entrada
    for ponto in (evento.get("conferenceData") or {}).get("entryPoints") or []:
        if ponto.get("entryPointType") == "video" and ponto.get("uri"):
            return ponto["uri"]
    return evento.get("htmlLink")


def _atualizar_sync(
    event_id: str, calendar_email: str, dados: DadosEvento
) -> ResultadoSync:  # pragma: no cover
    from googleapiclient.errors import HttpError

    try:
        servico = _servico(calendar_email)
        evento = servico.events().patch(
            calendarId="primary",
            eventId=event_id,
            body=_corpo(dados),
            sendUpdates=ENVIAR_CONVITES,
        ).execute()
    except HttpError as e:
        return ResultadoSync(ok=False, erro=_traduzir(e))
    except Exception as e:
        return ResultadoSync(ok=False, erro=_traduzir(e))

    return ResultadoSync(
        ok=True,
        event_id=evento.get("id"),
        calendar_id=calendar_email,
        link=_link_da_reuniao(evento),
    )


def _remover_sync(event_id: str, calendar_email: str) -> ResultadoSync:  # pragma: no cover
    from googleapiclient.errors import HttpError

    try:
        _servico(calendar_email).events().delete(
            calendarId="primary",
            eventId=event_id,
            sendUpdates=ENVIAR_CONVITES,
        ).execute()
    except HttpError as e:
        # 404/410 = já não existe. Alguém apagou o evento direto na agenda,
        # que é o caminho mais natural do mundo. Tratar como sucesso é o que
        # impede a tela de ficar exibindo um erro sobre um problema que já
        # está resolvido.
        if getattr(getattr(e, "resp", None), "status", None) in (404, 410):
            return ResultadoSync(ok=True)
        return ResultadoSync(ok=False, erro=_traduzir(e))
    except Exception as e:
        return ResultadoSync(ok=False, erro=_traduzir(e))
    return ResultadoSync(ok=True)


_DESLIGADO = ResultadoSync(
    ok=False,
    erro="Integração com o Google Calendar não configurada neste servidor.",
)


async def criar_evento(dados: DadosEvento) -> ResultadoSync:
    """Cria o evento e dispara os convites. Nunca levanta."""
    if not configurado():
        return _DESLIGADO
    faltando = problemas()
    if faltando:
        return ResultadoSync(ok=False, erro="; ".join(faltando))
    resultado = await asyncio.to_thread(_criar_sync, dados)
    _registrar("criar", dados.anfitriao_email, resultado)
    return resultado


async def atualizar_evento(
    event_id: str, calendar_email: str, dados: DadosEvento
) -> ResultadoSync:
    """
    Atualiza o evento existente e reavisa os convidados. Nunca levanta.

    `calendar_email` vem de `reunioes.google_calendar_id`, e NÃO do
    anfitrião atual: o evento mora no calendário de quem era dono quando
    ele nasceu. Personificar a pessoa errada devolve 404 e deixaria um
    evento fantasma na agenda da anterior.
    """
    if not configurado():
        return _DESLIGADO
    resultado = await asyncio.to_thread(
        _atualizar_sync, event_id, calendar_email, dados
    )
    _registrar("atualizar", calendar_email, resultado)
    return resultado


async def remover_evento(event_id: str, calendar_email: str) -> ResultadoSync:
    """Apaga o evento e avisa os convidados do cancelamento. Nunca levanta."""
    if not configurado():
        return _DESLIGADO
    resultado = await asyncio.to_thread(_remover_sync, event_id, calendar_email)
    _registrar("remover", calendar_email, resultado)
    return resultado


def _registrar(operacao: str, calendario: str, r: ResultadoSync) -> None:
    if r.ok:
        log.info("google_agenda: %s ok (%s, evento=%s)", operacao, calendario, r.event_id)
    else:
        log.warning("google_agenda: %s falhou (%s): %s", operacao, calendario, r.erro)
