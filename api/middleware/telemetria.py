"""
HIPO — Captura de uso (telemetria).

Uma linha em uso_eventos por request autenticada: quem, qual rota, que
status, quanto demorou.

DECISÕES QUE ESTE MÓDULO MATERIALIZA

  * Middleware, não instrumentação manual. Tela nova é capturada sem
    ninguém lembrar de instrumentar. O custo é uma tabela que cresce por
    request — resolvido pela retenção no fechamento diário.

  * Grava o TEMPLATE da rota (`/crm/contas/{conta_id}`), nunca o path com
    o id preenchido. O log não herda o controle de acesso da tabela de
    origem; guardar ids de cliente ali seria vazar dado para um lugar
    menos protegido. Pelo mesmo motivo, querystring e corpo não entram.

  * Buffer em memória com descarga em lote. Um INSERT por request abriria
    uma conexão asyncpg por request só para telemetria — dobraria o custo
    de conexão de toda a API para gravar um dado acessório.

  * Telemetria NUNCA quebra a request. Todo o caminho está sob try/except
    largo e falha em silêncio. Se o buffer estourar, descarta o excedente
    e conta o descarte: perder amostra é aceitável, derrubar o CRM porque
    o log de uso falhou não é.

  * Identidade vem do JWT, sem ida ao banco. O e-mail sai do token; o id e
    o cargo são resolvidos por subquery no INSERT do lote. Request sem
    token válido entra como anônima (usuario_id NULL) — é o que mostra
    tentativa de acesso e sessão expirada.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import asyncpg
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

log = logging.getLogger("hipo.telemetria")

# Rotas que não dizem nada sobre uso: healthcheck do CI/ALB e a doc.
ROTAS_IGNORADAS = frozenset({
    "/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico",
})

# Acima disso o buffer descarta em vez de crescer sem limite. 5 mil eventos
# são ~20 minutos de pico numa operação deste tamanho; se encher, o problema
# é a descarga não estar rodando, e aí segurar mais memória não ajuda.
LIMITE_BUFFER = 5_000

# Descarga automática quando o buffer chega neste tamanho.
LOTE_DESCARGA = 5

# Descarga por IDADE, além da descarga por tamanho.
#
# Só o gatilho por tamanho não serve a esta operação. O buffer é global POR
# PROCESSO e o uvicorn roda --workers 4, então "100 eventos" viram 400
# requisições espalhadas por quatro buffers antes da primeira gravação. Com
# sete pessoas, isso é telemetria que quase nunca chega ao banco — e que se
# perde inteira a cada deploy.
#
# Trinta segundos é o atraso máximo que um relatório diário tolera sem
# esforço, e custa no máximo uma conexão a cada 30s por worker.
#
# Ressalva conhecida: o gatilho é avaliado ao REGISTRAR. Se o tráfego parar,
# os últimos eventos ficam no buffer até a próxima requisição — ou até a
# descarga do desligamento, no lifespan de main.py.
IDADE_MAXIMA_S = 10.0

# Intervalo da descarga periódica (ver `descarga_periodica`).
#
# É esta que garante o dado no banco; os dois gatilhos acima passam a ser
# redundância barata para pico de tráfego. Dez segundos porque o consumidor é
# um relatório diário: a diferença entre 10s e 60s de atraso não muda nada
# para ele, e 10s mantém a janela de perda por queda abrupta bem pequena.
INTERVALO_DESCARGA_S = 10.0

_SQL_INSERT = """
    INSERT INTO uso_eventos
        (usuario_id, cargo, metodo, rota, modulo, status, duracao_ms, criado_em)
    VALUES (
        (SELECT id    FROM usuarios WHERE email = $1),
        (SELECT cargo FROM usuarios WHERE email = $1),
        $2, $3, $4, $5, $6, $7
    )
"""


def modulo_da_rota(rota: str) -> str | None:
    """
    Primeiro segmento do path como módulo. `/crm/contas/{id}` → 'crm'.

    Serve à pergunta "qual parte do sistema é usada", que é a única que o
    relatório faz nesse nível. Rota vazia ou raiz devolve None.

    >>> modulo_da_rota("/crm/parceiros/resumo")
    'crm'
    >>> modulo_da_rota("/auth/login")
    'auth'
    >>> modulo_da_rota("/")
    """
    partes = [p for p in (rota or "").split("/") if p]
    return partes[0][:40] if partes else None


def email_do_token(header_autorizacao: str | None) -> str | None:
    """
    E-mail dentro do JWT do header, ou None se não houver token válido.

    Não consulta o banco: o middleware roda em toda request e uma query a
    mais por request para saber quem é seria pior que o dado que ela gera.
    """
    if not header_autorizacao or not header_autorizacao.lower().startswith("bearer "):
        return None
    token = header_autorizacao[7:].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None


class BufferTelemetria:
    """
    Acumula eventos e descarrega em lote.

    Não é uma fila de background com worker próprio de propósito: o
    conftest sobe o app com lifespan desabilitado (para não criar conexão
    asyncpg no event loop errado), então uma task iniciada no startup
    simplesmente não existiria nos testes. A descarga é disparada pelo
    próprio tráfego ao atingir LOTE_DESCARGA, e o fechamento diário pode
    chamar `descarregar()` na mão.
    """

    def __init__(
        self,
        limite: int = LIMITE_BUFFER,
        lote: int = LOTE_DESCARGA,
        idade_maxima: float | None = IDADE_MAXIMA_S,
        relogio=time.monotonic,
    ):
        self._eventos: list[tuple] = []
        self._limite = limite
        self._lock = asyncio.Lock()
        self.descartados = 0

        # Relogio injetavel, mesmo padrao de services/tarefa.py e
        # services/parceiro.py: o teste do gatilho por tempo avanca o relogio
        # em vez de dormir 30 segundos.
        self._relogio = relogio
        self._mais_antigo: float | None = None

        # Publico de proposito: o conftest zera o gatilho por tempo junto com
        # o de tamanho. Com so o lote elevado, um evento parado por mais de
        # IDADE_MAXIMA_S dispararia a descarga sozinho e reencontraria o
        # TRUNCATE CASCADE da fixture db_conn.
        self.idade_maxima = idade_maxima

        # Publico de proposito: a suite de testes eleva o lote para desativar
        # a descarga automatica e chamar `descarregar()` na mao. Sem isso, a
        # task de background disputa lock com o TRUNCATE CASCADE da fixture
        # db_conn (que alcanca uso_eventos pela FK) e a suite trava inteira.
        self.lote = lote

    def __len__(self) -> int:
        return len(self._eventos)

    async def limpar(self) -> None:
        """Descarta o buffer sem gravar. Usado entre testes."""
        async with self._lock:
            self._eventos.clear()
            self.descartados = 0
            self._mais_antigo = None

    async def registrar(self, evento: tuple) -> None:
        async with self._lock:
            if len(self._eventos) >= self._limite:
                self.descartados += 1
                return
            agora = self._relogio()
            if not self._eventos:
                self._mais_antigo = agora
            self._eventos.append(evento)
            precisa_descarregar = (
                len(self._eventos) >= self.lote
                or (
                    self.idade_maxima is not None
                    and self._mais_antigo is not None
                    and agora - self._mais_antigo >= self.idade_maxima
                )
            )
        if precisa_descarregar:
            # Task solta: a resposta não espera o INSERT.
            asyncio.create_task(self.descarregar())

    async def descarregar(self) -> int:
        """
        Grava o que está no buffer e devolve quantos eventos gravou.

        Em caso de erro no banco, os eventos do lote são perdidos — e não
        recolocados no buffer. Reinserir criaria um ciclo de retentativa
        que, num banco fora do ar, cresceria até estourar a memória do
        worker pelo direito de gravar um log de uso.
        """
        async with self._lock:
            if not self._eventos:
                return 0
            lote, self._eventos = self._eventos, []
            self._mais_antigo = None

        conn = None
        try:
            conn = await asyncpg.connect(settings.DATABASE_URL)
            # Teto duro na gravacao: se a tabela estiver sob lock ou o banco
            # lento, a task desiste em vez de ficar pendurada segurando
            # conexao. Perder o lote ja e a politica declarada acima; o que
            # nao pode acontecer e a telemetria consumir o pool do banco
            # esperando por um lock que talvez nunca venha.
            # SET de sessão, não SET LOCAL: LOCAL só vale dentro de uma
            # transação explícita, e o executemany abaixo não abre uma. A
            # conexão é descartada logo em seguida, então o escopo de sessão
            # não vaza para ninguém.
            await conn.execute("SET statement_timeout = '5s'")
            await conn.executemany(_SQL_INSERT, lote)
            return len(lote)
        except Exception as e:  # pragma: no cover - caminho de falha do banco
            log.warning("telemetria: descarga falhou, %d evento(s) perdido(s): %s", len(lote), e)
            return 0
        finally:
            if conn is not None:
                await conn.close()


async def descarga_periodica(
    alvo: BufferTelemetria,
    intervalo: float = INTERVALO_DESCARGA_S,
) -> None:
    """
    Descarrega o buffer a cada `intervalo` segundos, haja tráfego ou não.

    POR QUE ELA PRECISA EXISTIR

    Os gatilhos por tamanho e por idade são avaliados dentro de `registrar` —
    ou seja, só quando chega uma requisição. Se a última ação do dia for às
    18h e ninguém mais tocar na API, esses eventos ficam em memória a noite
    inteira, e o fechamento das 03:10 não os enxerga. Eles apareceriam no
    banco só na manhã seguinte, com `criado_em` de ontem, num dia que já foi
    fechado: dado presente no banco e ausente do relatório, que é pior que
    dado perdido porque ninguém desconfia.

    NÃO RODA NA SUÍTE, DE PROPÓSITO

    Ela é iniciada pelo lifespan de main.py, e o conftest sobe o cliente de
    teste com lifespan desabilitado. Era esse o motivo original para não
    existir uma task de background — descarga automática disputando lock com
    o TRUNCATE CASCADE da fixture `db_conn` travava a suíte inteira. Amarrada
    ao lifespan, o problema deixa de existir sem abrir mão do comportamento
    em produção. Os testes exercitam a função direto, com um buffer próprio.

    Cancelamento sai pelo CancelledError, que herda de BaseException e por
    isso não é capturado pelo `except Exception` abaixo.
    """
    while True:
        await asyncio.sleep(intervalo)
        try:
            await alvo.descarregar()
        except Exception as e:  # pragma: no cover - blindagem
            # `descarregar` já trata falha de banco. Isto aqui existe para o
            # laço nunca morrer: uma task que encerra em silêncio deixaria a
            # telemetria parada até o próximo restart, sem sinal nenhum.
            log.warning("telemetria: descarga periódica falhou: %s", e)


# Instância global: um buffer por worker do uvicorn.
buffer = BufferTelemetria()


class TelemetriaMiddleware(BaseHTTPMiddleware):
    """Mede a request, resolve quem chamou e joga no buffer."""

    async def dispatch(self, request, call_next):
        inicio = time.perf_counter()
        resposta = await call_next(request)

        try:
            if request.method == "OPTIONS":
                return resposta
            if request.url.path in ROTAS_IGNORADAS:
                return resposta

            # O router preenche scope['route'] durante o handling. Sem rota
            # casada (404), o template não existe e o path cru também não
            # serve — viraria uma linha nova a cada id inexistente tentado.
            rota_obj = request.scope.get("route")
            rota = getattr(rota_obj, "path", None) or "<sem_rota>"

            duracao_ms = int((time.perf_counter() - inicio) * 1000)

            await buffer.registrar((
                email_do_token(request.headers.get("authorization")),
                request.method,
                rota[:200],
                modulo_da_rota(rota),
                int(resposta.status_code),
                duracao_ms,
                # Momento do evento, não da descarga: o lote pode ser gravado
                # minutos depois e cair no dia seguinte, contando a ação da
                # noite de ontem no relatório de hoje.
                datetime.now(timezone.utc),
            ))
        except Exception as e:  # pragma: no cover - blindagem
            log.warning("telemetria: evento descartado (%s)", e)

        return resposta
