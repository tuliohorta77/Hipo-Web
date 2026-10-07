"""
HIPO -- limite de tentativas de login (032).

Contra forca bruta no POST /auth/login. Sem dependencia nova (slowapi e
afins): a contagem mora no Postgres, em `login_tentativas`.

POR QUE NO BANCO E NAO EM MEMORIA

O uvicorn roda --workers 4 na base principal (2 na MOS). Um contador em
memoria e POR PROCESSO: "5 tentativas" virariam 20, espalhadas entre
quatro contadores que nao se enxergam, e todo restart do deploy zeraria
tudo. O banco ja e compartilhado entre os workers e sobrevive ao deploy;
o custo e um SELECT indexado por login, que perto do bcrypt (~277 ms a 12
rounds) nao aparece.

AS DUAS CONTAGENS

  * Por E-MAIL: falhas para aquele e-mail na janela, contadas a partir do
    ultimo login BEM-SUCEDIDO dele. Quem errou a senha duas vezes e
    acertou na terceira nao carrega as duas falhas para a proxima vez.
  * Por IP: falhas daquele IP na janela, para qualquer e-mail. Pega quem
    varre varios e-mails a partir da mesma maquina. Sucesso NAO zera esta:
    acertar a propria senha nao pode virar salvo-conduto para seguir
    testando as dos outros.

Tentativa barrada pelo limite ('bloqueado') e gravada mas NAO conta: senao
quem insiste ficaria bloqueado para sempre, e um atacante poderia manter a
conta de alguem travada indefinidamente batendo de minuto em minuto. Sem
contar, o bloqueio dura no maximo uma janela depois da ultima falha real.

A CHECAGEM VEM ANTES DO BCRYPT. Barrado, o login nem confere a senha: e o
que tira a forca bruta do ar (nenhuma senha e testada) e o que impede que o
proprio limite vire um jeito barato de gastar CPU do servidor.

Regras puras (`avaliar`, `segundos_para_liberar`) separadas do acesso ao
banco, para teste deterministico sem relogio de verdade -- mesmo padrao de
services/tarefa.py.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from config import settings

log = logging.getLogger("hipo.login")

# Peers que significam "veio pelo nginx da propria EC2". Atras deles, o IP
# real esta no X-Real-IP que o nginx grava (e sobrescreve, entao o cliente
# nao consegue forjar).
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


@dataclass(frozen=True)
class Decisao:
    bloqueado: bool
    # Por qual das contagens. None quando liberado.
    por: str | None = None
    # Segundos ate a contagem cair abaixo do limite. 0 quando liberado.
    segundos: int = 0

    def mensagem(self) -> str:
        minutos = max(1, math.ceil(self.segundos / 60))
        plural = "minuto" if minutos == 1 else "minutos"
        return (
            "Muitas tentativas de login sem sucesso. "
            f"Tente de novo em {minutos} {plural}."
        )


def normalizar_email(email: str | None) -> str:
    return (email or "").strip().lower()[:150]


def ip_do_cliente(request) -> str | None:
    """
    IP de quem chamou.

    Em producao o peer e o nginx (127.0.0.1) -- a nao ser que o uvicorn ja
    tenha reescrito pelo X-Forwarded-For, caso em que o peer ja e o IP
    real. Os dois caminhos chegam no mesmo lugar: atras de loopback, vale o
    X-Real-IP; fora disso, o peer.
    """
    cliente = getattr(request, "client", None)
    peer = getattr(cliente, "host", None) if cliente else None
    if peer in _LOOPBACK or peer is None:
        real = (request.headers.get("x-real-ip") or "").strip()
        if real:
            return real[:64]
    return (peer or None) and peer[:64]


def avaliar(
    falhas_email: int,
    falhas_ip: int,
    *,
    max_email: int,
    max_ip: int,
) -> str | None:
    """
    Qual limite estourou: 'email', 'ip' ou None.

    E-mail primeiro: e o caso comum (alguem testando a senha de uma conta) e
    o que tem a mensagem mais util para a pessoa legitima que errou.

    >>> avaliar(4, 0, max_email=5, max_ip=20)
    >>> avaliar(5, 0, max_email=5, max_ip=20)
    'email'
    >>> avaliar(0, 20, max_email=5, max_ip=20)
    'ip'
    """
    if max_email > 0 and falhas_email >= max_email:
        return "email"
    if max_ip > 0 and falhas_ip >= max_ip:
        return "ip"
    return None


def segundos_para_liberar(
    momento_que_libera: datetime | None,
    agora: datetime,
    janela: timedelta,
) -> int:
    """
    Quanto falta para a falha que destrava a contagem sair da janela.

    `momento_que_libera` e a falha que, ao vencer, deixa a contagem um
    abaixo do limite (ver `_SQL_LIBERA_EMAIL`). Nunca negativo, e no
    minimo 1 s enquanto bloqueado -- "tente de novo em 0 minutos" seria
    convite para martelar.
    """
    if momento_que_libera is None:
        return int(janela.total_seconds())
    restante = (momento_que_libera + janela - agora).total_seconds()
    return max(1, math.ceil(restante))


# ── Banco ──────────────────────────────────────────────────────────────

# Falhas que contam: dentro da janela, nao barradas pelo proprio limite.
# Para o e-mail, so as posteriores ao ultimo sucesso dele.
_SQL_FALHAS_EMAIL = """
    SELECT count(*) FROM login_tentativas
     WHERE email = $1
       AND NOT sucesso AND motivo <> 'bloqueado'
       AND criado_em > GREATEST(
             $2::timestamptz,
             COALESCE((SELECT max(criado_em) FROM login_tentativas
                        WHERE email = $1 AND sucesso), '-infinity'::timestamptz)
           )
"""

_SQL_FALHAS_IP = """
    SELECT count(*) FROM login_tentativas
     WHERE ip = $1
       AND NOT sucesso AND motivo <> 'bloqueado'
       AND criado_em > $2::timestamptz
"""

# A falha cuja saida da janela deixa a contagem em (limite - 1). Com N
# falhas e limite L, e a de posicao N - L (0-based) em ordem crescente --
# sobre o MESMO conjunto que foi contado (para o e-mail, so depois do
# ultimo sucesso).
_SQL_LIBERA_EMAIL = """
    SELECT criado_em FROM login_tentativas
     WHERE email = $1
       AND NOT sucesso AND motivo <> 'bloqueado'
       AND criado_em > GREATEST(
             $2::timestamptz,
             COALESCE((SELECT max(criado_em) FROM login_tentativas
                        WHERE email = $1 AND sucesso), '-infinity'::timestamptz)
           )
     ORDER BY criado_em
     OFFSET $3 LIMIT 1
"""

_SQL_LIBERA_IP = """
    SELECT criado_em FROM login_tentativas
     WHERE ip = $1
       AND NOT sucesso AND motivo <> 'bloqueado'
       AND criado_em > $2::timestamptz
     ORDER BY criado_em
     OFFSET $3 LIMIT 1
"""


async def verificar(conn, email: str, ip: str | None, *, agora: datetime | None = None) -> Decisao:
    """Decide se esta tentativa pode seguir para a conferencia da senha."""
    if not settings.LOGIN_LIMITE_ATIVO:
        return Decisao(bloqueado=False)

    agora = agora or datetime.now(timezone.utc)
    janela = timedelta(minutes=settings.LOGIN_JANELA_MIN)
    desde = agora - janela

    falhas_email = await conn.fetchval(_SQL_FALHAS_EMAIL, email, desde)
    falhas_ip = await conn.fetchval(_SQL_FALHAS_IP, ip, desde) if ip else 0

    por = avaliar(
        falhas_email, falhas_ip,
        max_email=settings.LOGIN_MAX_FALHAS_EMAIL,
        max_ip=settings.LOGIN_MAX_FALHAS_IP,
    )
    if por is None:
        return Decisao(bloqueado=False)

    if por == "email":
        sql, valor, total, limite = (
            _SQL_LIBERA_EMAIL, email, falhas_email, settings.LOGIN_MAX_FALHAS_EMAIL,
        )
    else:
        sql, valor, total, limite = (
            _SQL_LIBERA_IP, ip, falhas_ip, settings.LOGIN_MAX_FALHAS_IP,
        )

    libera = await conn.fetchval(sql, valor, desde, max(0, total - limite))
    segundos = segundos_para_liberar(libera, agora, janela)
    log.warning(
        "login bloqueado por %s: %d falha(s) na janela de %d min",
        por, total, settings.LOGIN_JANELA_MIN,
    )
    return Decisao(bloqueado=True, por=por, segundos=segundos)


async def registrar(
    conn,
    email: str,
    ip: str | None,
    *,
    sucesso: bool,
    motivo: str | None = None,
    user_agent: str | None = None,
) -> None:
    """
    Grava a tentativa.

    Falha ao gravar NAO derruba o login: e log.error (que vira alerta no
    Sentry) e segue. Tirar o sistema do ar porque a trilha nao gravou seria
    trocar um risco teorico por um apagao real. O preco conhecido: com a
    tabela fora, o limite deixa de contar -- e o alerta diz isso.
    """
    try:
        await conn.execute(
            """
            INSERT INTO login_tentativas (email, ip, sucesso, motivo, user_agent)
            VALUES ($1, $2, $3, $4, $5)
            """,
            email, ip, sucesso, None if sucesso else motivo,
            (user_agent or "")[:300] or None,
        )
    except Exception:
        log.error("login_tentativas: falha ao gravar tentativa", exc_info=True)


async def aplicar_retencao(conn, dias: int) -> int:
    """Apaga tentativas mais velhas que `dias`. 0 ou negativo = nao apaga."""
    if dias <= 0:
        return 0
    status = await conn.execute(
        "DELETE FROM login_tentativas WHERE criado_em < NOW() - make_interval(days => $1)",
        dias,
    )
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):  # pragma: no cover
        return 0
