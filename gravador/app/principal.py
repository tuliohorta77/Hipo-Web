"""
O programa: detecção + gravação + fila + envio + bandeja, e os modos de
linha de comando que o instalador e o suporte usam.

  hipo_gravador.pyw                     roda na bandeja (o que a tarefa
                                        agendada do Windows chama no logon)
  hipo_gravador.pyw --console           roda sem bandeja, diário na tela
  hipo_gravador.pyw --configurar URL TOKEN
                                        grava a configuração (instalador)
  hipo_gravador.pyw --testar            confere token, dispositivos e softphone
  hipo_gravador.pyw --descobrir [seg]   lista os programas usando áudio —
                                        rode DURANTE uma ligação para achar o
                                        nome do processo do softphone
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
import threading
import time

from app import VERSAO
from app import config as cfgmod
from app.atendimento import houve_chamando, inicio_do_atendimento
from app.captura import Gravacao, escolher_loopback, escolher_microfone, salvar_flac
from app.cliente import Cliente, ErroHipo, TokenInvalido, iso
from app.deteccao import (
    MaquinaDeChamada, casa_processo, dispositivos_do_softphone, sessoes_windows, softphone_ativo,
)
from app.envio import Enviador
from app.fila import Fila

log = logging.getLogger("gravador")

INTERVALO_DETECCAO_S = 0.7
INTERVALO_ENVIO_S = 15
INTERVALO_PULSO_S = 120


def configurar_log(console: bool) -> None:
    pasta = cfgmod.pasta_dados()
    pasta.mkdir(parents=True, exist_ok=True)
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    arq = logging.handlers.RotatingFileHandler(
        pasta / "gravador.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8",
    )
    arq.setFormatter(fmt)
    raiz.addHandler(arq)
    if console:
        tela = logging.StreamHandler(sys.stdout)
        tela.setFormatter(fmt)
        raiz.addHandler(tela)


# O mutex fica vivo enquanto o processo existir: perder a referência não
# fecha o handle, mas guardar deixa isso explícito.
_MUTEX = None
FOLGA_FIM_S = 1.0


def instancia_unica() -> bool:
    """
    Um gravador por sessão do Windows (mutex nomeado).

    1.0.7: o erro é lido com use_last_error. `ctypes.windll` + GetLastError()
    numa chamada separada pode ler o erro de outra chamada que o próprio
    Python fez no meio -- e aí dois gravadores sobem e gravam a mesma
    ligação duas vezes.
    """
    global _MUTEX
    if sys.platform != "win32":
        return True
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    _MUTEX = k32.CreateMutexW(None, False, "Local\\HIPO-Gravador")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def cortar_rabo(estereo, taxa: int, inicio: float, fim: float | None):
    """
    Corta o silêncio do fim: fica até o último som do softphone + 1 s.

    `inicio`/`fim` são os horários do evento da detecção (time.time()).
    Sem `fim` (gravação fechada à força), devolve inteiro.
    """
    if fim is None or fim <= inicio:
        return estereo
    amostras = int((fim - inicio + FOLGA_FIM_S) * taxa)
    return estereo[:amostras] if amostras < len(estereo) else estereo


def resolver_dispositivos(cfg: cfgmod.Config, sessoes) -> tuple[str, str]:
    """
    O que gravar de fato. "softphone" vira o id do dispositivo que o
    softphone está usando; sem sessão dele, cai em "comunicacao".
    """
    mic, alto = (None, None)
    if "softphone" in (cfg.entrada, cfg.saida):
        try:
            mic, alto = dispositivos_do_softphone(sessoes or [], cfg.processos)
        except Exception:  # noqa: BLE001
            mic, alto = None, None
    entrada = (mic or "comunicacao") if cfg.entrada == "softphone" else cfg.entrada
    saida = (alto or "comunicacao") if cfg.saida == "softphone" else cfg.saida
    return entrada, saida


def softphone_rodando(processos: list[str]) -> list[str]:
    import psutil

    achados = set()
    for p in psutil.process_iter(["name"]):
        if casa_processo(p.info.get("name"), processos):
            achados.add(p.info["name"])
    return sorted(achados)


class App:
    def __init__(self, cfg: cfgmod.Config):
        self.cfg = cfg
        self.fila = Fila(cfgmod.pasta_dados())
        self.cliente = Cliente(cfg.url, cfg.token, VERSAO)
        self.enviador = Enviador(self.fila, self.cliente)
        self.maquina = MaquinaDeChamada(cfg.fim_apos_silencio_s, cfg.max_duracao_s)
        self.gravacao: Gravacao | None = None
        self.gravacao_ignorada = False
        self.pausado = False
        self.encerrando = threading.Event()
        self.acordar_envio = threading.Event()
        self.servidor_ok: bool | None = None
        self.erro_deteccao: str | None = None
        self.bandeja = None
        # A pausa vem da thread da bandeja; o fim da chamada, da detecção.
        self._trava = threading.Lock()
        self._sessoes = []

    # ── Estado para a bandeja ────────────────────────────────────────

    def cor_estado(self) -> str:
        if self.gravacao is not None:
            return "gravando"
        if self.pausado:
            return "pausado"
        if self.enviador.token_invalido or self.servidor_ok is False or self.erro_deteccao:
            return "problema"
        return "pronto"

    def texto_estado(self) -> str:
        fila = self.fila.quantidade()
        sufixo = f" · {fila} na fila" if fila else ""
        if self.gravacao is not None and self.maquina.inicio:
            s = int(time.time() - self.maquina.inicio)
            return f"Gravando ligação ({s // 60:02d}:{s % 60:02d})"
        if self.pausado:
            return "Pausado — não está gravando" + sufixo
        if self.enviador.token_invalido:
            return "Token recusado pelo HIPO — gere outro e reinstale"
        if self.erro_deteccao:
            return f"Não consegue ler o áudio do Windows: {self.erro_deteccao}"[:120]
        if self.servidor_ok is False:
            return "Sem conexão com o HIPO" + sufixo
        return "Pronto — aguardando ligação" + sufixo

    def _avisar(self, texto: str) -> None:
        log.info(texto)
        if self.bandeja:
            self.bandeja.avisar(texto)

    def _redesenhar(self) -> None:
        if self.bandeja:
            self.bandeja.atualizar()

    # ── Pausa ────────────────────────────────────────────────────────

    def alternar_pausa(self) -> None:
        with self._trava:
            self._alternar_pausa()

    def _alternar_pausa(self) -> None:
        self.pausado = not self.pausado
        if self.pausado and self.gravacao is not None:
            # Pausou no meio: o que já foi gravado desta chamada é jogado fora.
            self.gravacao.parar()
            self.gravacao = None
            self.gravacao_ignorada = True
            log.info("pausado no meio da chamada: gravacao descartada")
        log.info("gravacao %s", "pausada" if self.pausado else "retomada")

    # ── Laços ────────────────────────────────────────────────────────

    def laco_deteccao(self) -> None:
        _iniciar_com()
        ultimo_erro_log = 0.0
        while not self.encerrando.is_set():
            agora = time.time()
            try:
                self._sessoes = sessoes_windows()
                ativo = softphone_ativo(
                    self._sessoes, self.cfg.processos, self.cfg.detectar_por, self.cfg.limiar_som,
                )
                self.erro_deteccao = None
            except Exception as e:  # noqa: BLE001
                ativo = False
                self.erro_deteccao = type(e).__name__
                if agora - ultimo_erro_log > 60:
                    log.exception("leitura das sessoes de audio falhou")
                    ultimo_erro_log = agora
            ev = self.maquina.atualizar(ativo, agora)
            if ev is not None:
                try:
                    self._tratar(ev)
                except Exception:  # noqa: BLE001 - a detecção não pode morrer calada
                    log.exception("falha ao tratar %s da chamada", ev.tipo)
                    self.gravacao = None
                    self._avisar("Falha ao gravar a última ligação. Veja o diário.")
                self._redesenhar()
            elif self.gravacao is not None and int(agora) % 5 == 0:
                self._redesenhar()
            self.encerrando.wait(INTERVALO_DETECCAO_S)
        ev = self.maquina.forcar_fim(time.time())
        if ev is not None:
            try:
                self._tratar(ev)
            except Exception:  # noqa: BLE001
                log.exception("falha ao fechar a gravacao na saida")

    def _tratar(self, ev) -> None:
        with self._trava:
            self._tratar_evento(ev)

    def _tratar_evento(self, ev) -> None:
        if ev.tipo == "inicio":
            if self.pausado:
                self.gravacao_ignorada = True
                log.info("chamada detectada com o gravador pausado: nao grava")
                return
            self.gravacao_ignorada = False
            log.info("chamada detectada: gravando")
            entrada, saida = resolver_dispositivos(self.cfg, self._sessoes)
            self.gravacao = Gravacao(entrada, saida, self.cfg.taxa)
            return
        # fim
        grav, self.gravacao = self.gravacao, None
        if grav is None or self.gravacao_ignorada:
            self.gravacao_ignorada = False
            return
        estereo, erros = grav.parar()
        inicio = ev.inicio
        # 1.0.7: a gravação para FIM_APOS_SILENCIO segundos depois do último
        # som do softphone (15 s desde esta versão). Esse rabo de silêncio
        # sai: não é conversa, e somado deixaria bipe de 1 s do Vivo passar
        # do mínimo de duração e ser enviado como ligação.
        estereo = cortar_rabo(estereo, self.cfg.taxa, ev.inicio, ev.fim)
        # 1.0.2: o microfone abre quando a pessoa DISCA. Corta o "chamando"
        # do começo -- só quando houve tom de chamada antes, para não comer o
        # "Controller MedSeg, bom dia" de uma ligação recebida.
        try:
            corte = inicio_do_atendimento(estereo[:, 1], self.cfg.taxa)
            if corte and houve_chamando(estereo[:, 1], self.cfg.taxa, corte + 0.6):
                estereo = estereo[int(corte * self.cfg.taxa):]
                inicio += corte
                log.info("chamando cortado: %.1f s antes do atendimento", corte)
        except Exception:  # noqa: BLE001 - corte é acessório; na dúvida, manda inteiro
            log.exception("deteccao do atendimento falhou; gravacao segue inteira")
        duracao = len(estereo) / self.cfg.taxa
        if duracao < self.cfg.min_duracao_s:
            log.info("chamada de %.1f s: curta demais, nao envia", duracao)
            return
        id_ = self.fila.novo_id()
        try:
            tamanho = salvar_flac(self.fila.audio(id_), estereo, self.cfg.taxa)
        except Exception:  # noqa: BLE001
            log.exception("nao foi possivel salvar a gravacao")
            self._avisar("Não foi possível salvar a gravação da ligação. Veja o diário.")
            return
        self.fila.adicionar(id_, {
            "inicio_ts": inicio,
            "fim_ts": inicio + duracao,
            "duracao_s": duracao,
            "inicio": iso(inicio),
            "erros_captura": erros,
        })
        log.info("ligacao gravada: %.0f s, %d KB, na fila como %s", duracao, tamanho // 1024, id_)
        self.acordar_envio.set()

    def laco_envio(self) -> None:
        while not self.encerrando.is_set():
            try:
                self.enviador.passo()
                self.fila.limpar()
            except Exception:  # noqa: BLE001
                log.exception("envio falhou")
            self._redesenhar()
            self.acordar_envio.wait(INTERVALO_ENVIO_S)
            self.acordar_envio.clear()

    def laco_pulso(self) -> None:
        avisou_token = False
        while not self.encerrando.is_set():
            try:
                r = self.cliente.pulso()
                self.servidor_ok = True
                if not r.get("aceita_gravacao"):
                    log.warning("HIPO sem armazenamento de gravacoes: %s", r.get("problemas"))
                if self.enviador.token_invalido:
                    self.enviador.token_invalido = False  # token voltou a valer
            except TokenInvalido as e:
                self.enviador.token_invalido = True
                if not avisou_token:
                    self._avisar(f"O HIPO recusou o token deste gravador ({e}). Gere outro no seu Perfil.")
                    avisou_token = True
            except ErroHipo as e:
                self.servidor_ok = False
                log.warning("pulso: %s", e)
            self._redesenhar()
            self.encerrando.wait(INTERVALO_PULSO_S)

    def iniciar_lacos(self) -> list[threading.Thread]:
        ts = [
            threading.Thread(target=self.laco_deteccao, name="deteccao", daemon=True),
            threading.Thread(target=self.laco_envio, name="envio", daemon=True),
            threading.Thread(target=self.laco_pulso, name="pulso", daemon=True),
        ]
        for t in ts:
            t.start()
        return ts

    def encerrar(self) -> None:
        log.info("encerrando")
        self.encerrando.set()
        self.acordar_envio.set()


def _iniciar_com() -> None:
    """
    Garante a soundcard importada (ela inicia o COM do processo em MTA)
    ANTES de qualquer coisa do comtypes nesta thread. O inverso faz a
    soundcard receber S_FALSE e recusar o dispositivo (ver hipo_gravador.pyw).
    """
    try:
        import soundcard  # noqa: F401
    except Exception:  # noqa: BLE001 - fora do Windows
        pass
    try:
        import comtypes
        comtypes.CoInitializeEx(0)
    except Exception:  # noqa: BLE001 - já iniciado, ou fora do Windows
        pass


# ── Modos de linha de comando ────────────────────────────────────────


def cmd_configurar(url: str, token: str) -> int:
    cfg = cfgmod.carregar()
    cfg.url = url.rstrip("/")
    cfg.token = token.strip()
    if not cfg.ok():
        print("Token inválido: ele começa com hipograv_ (copie do seu Perfil no HIPO).")
        return 2
    print(f"Configuração gravada em {cfgmod.salvar(cfg)}")
    return 0


def cmd_testar(cfg: cfgmod.Config) -> int:
    ok = True
    print(f"HIPO Gravador {VERSAO}")
    print(f"Configuração: {cfgmod.caminho_config()}")
    if not cfg.ok():
        print("  FALTA: token. Rode o instalador de novo com o token do seu Perfil.")
        return 2
    try:
        r = Cliente(cfg.url, cfg.token, VERSAO).pulso()
        print(f"  HIPO ok: gravador '{r.get('gravador')}' de {r.get('usuario')}")
        if not r.get("aceita_gravacao"):
            print(f"  AVISO: o servidor ainda não aceita gravações: {r.get('problemas')}")
    except ErroHipo as e:
        print(f"  HIPO FALHOU: {type(e).__name__}: {e}")
        ok = False
    _iniciar_com()
    try:
        sessoes = sessoes_windows()
    except Exception:  # noqa: BLE001
        sessoes = []
    entrada, saida = resolver_dispositivos(cfg, sessoes)
    if cfg.entrada == "softphone":
        print("  (microfone e saída: os que o softphone estiver usando)")
    for nome, f, pedido in (("Microfone", escolher_microfone, entrada),
                            ("Saída (cliente)", escolher_loopback, saida)):
        try:
            print(f"  {nome}: {getattr(f(pedido), 'name', '?')}")
        except Exception as e:  # noqa: BLE001
            print(f"  {nome} FALHOU: {e}")
            ok = False
    rodando = softphone_rodando(cfg.processos)
    if rodando:
        print(f"  Softphone aberto: {', '.join(rodando)}")
    else:
        print("  AVISO: nenhum processo do softphone aberto agora (ou o nome não está na lista).")
        print("         Abra o Vivo Voz Negócio, faça uma ligação de teste e rode --descobrir.")
    return 0 if ok else 1


def cmd_descobrir(segundos: int) -> int:
    _iniciar_com()
    print(f"Olhando as sessões de áudio por {segundos} s. Faça (ou atenda) uma ligação agora.")
    vistos: dict[tuple, bool] = {}
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            for s in sessoes_windows():
                chave = (s.processo, s.fluxo)
                if s.ativa and not vistos.get(chave):
                    print(f"  ATIVO  {s.fluxo:9s}  {s.processo}  (pid {s.pid})")
                vistos[chave] = vistos.get(chave, False) or s.ativa
        except Exception as e:  # noqa: BLE001
            print(f"  erro lendo sessões: {e}")
        time.sleep(1)
    print("\nProgramas com áudio vistos (ativo = passou som):")
    for (proc, fluxo), ativo in sorted(vistos.items()):
        print(f"  {'ativo ' if ativo else 'parado'}  {fluxo:9s}  {proc}")
    print("\nO softphone é o que ficou ATIVO no microfone durante a ligação. Se o nome dele")
    print("não estiver na lista 'processos' de config.json, acrescente um trecho do nome lá.")
    return 0


def cmd_gravar_teste(cfg: cfgmod.Config, segundos: int) -> int:
    """
    Diagnóstico: grava N segundos dos MESMOS dispositivos da gravação real e
    diz o volume de cada canal. Fale no headset enquanto roda.

    Canal 0 (microfone) com pico perto de zero enquanto a pessoa fala = o
    Windows está entregando silêncio ao gravador (permissão de microfone,
    dispositivo errado ou outro programa segurando o microfone).
    """
    import numpy as np

    _iniciar_com()
    print(f"Gravando {segundos} s. FALE no headset agora (conte até 10 em voz alta)...")
    try:
        sessoes = sessoes_windows()
    except Exception:  # noqa: BLE001
        sessoes = []
    entrada, saida = resolver_dispositivos(cfg, sessoes)
    g = Gravacao(entrada, saida, cfg.taxa)
    time.sleep(segundos)
    estereo, erros = g.parar()
    for e in erros:
        print(f"  ERRO {e}")
    for canal, nome in ((0, "microfone (você)"), (1, "saída (cliente)")):
        x = estereo[:, canal].astype("float64") / 32767 if len(estereo) else np.zeros(1)
        rms = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
        pico = float(np.max(np.abs(x))) if x.size else 0.0
        print(f"  canal {canal} {nome:18s} pico {pico:.4f}   rms {rms:.5f}")
    destino = cfgmod.pasta_dados() / "teste-gravacao.flac"
    salvar_flac(destino, estereo, cfg.taxa)
    print(f"\nArquivo para ouvir: {destino}")
    print("Microfone com pico abaixo de 0.01 enquanto você falava = o gravador está recebendo silêncio.")
    return 0


def cmd_medir(segundos: int, processos: list[str]) -> int:
    """
    Diagnóstico: o pico de som das sessões do softphone a cada meio segundo.

    Serve para quando o softphone deixa o áudio aberto o tempo todo (sessão
    sempre "ativa"): mostra se, fora de chamada, o som dele é zero absoluto
    -- e então dá para detectar a chamada pelo som que passa.
    """
    _iniciar_com()
    print(f"Medindo o som do softphone por {segundos} s (meio segundo por linha).")
    print("Fique uns 15 s SEM ligar, depois ligue, fale, desligue e espere mais 15 s.\n")
    print("hora      saida      microfone")
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            ss = [s for s in sessoes_windows() if casa_processo(s.processo, processos)]
        except Exception as e:  # noqa: BLE001
            print(f"erro lendo sessões: {e}")
            ss = []

        def maior(fluxo):
            vals = [s.pico for s in ss if s.fluxo == fluxo and s.pico is not None]
            return f"{max(vals):.5f}" if vals else "   -   "

        print(f"{time.strftime('%H:%M:%S')}  {maior('saida'):>9}  {maior('microfone'):>9}", flush=True)
        time.sleep(0.5)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hipo_gravador", description="HIPO Gravador de ligações")
    p.add_argument("--console", action="store_true")
    p.add_argument("--testar", action="store_true")
    p.add_argument("--descobrir", nargs="?", const=60, type=int, metavar="SEGUNDOS")
    p.add_argument("--medir", nargs="?", const=90, type=int, metavar="SEGUNDOS")
    p.add_argument("--gravar-teste", nargs="?", const=8, type=int, metavar="SEGUNDOS")
    p.add_argument("--configurar", nargs=2, metavar=("URL", "TOKEN"))
    p.add_argument("--versao", action="store_true")
    a = p.parse_args(argv)

    if a.versao:
        print(VERSAO)
        return 0
    if a.configurar:
        return cmd_configurar(*a.configurar)
    cfg = cfgmod.carregar()
    if a.testar:
        return cmd_testar(cfg)
    if a.descobrir is not None:
        return cmd_descobrir(a.descobrir)
    if a.medir is not None:
        return cmd_medir(a.medir, cfg.processos)
    if a.gravar_teste is not None:
        return cmd_gravar_teste(cfg, a.gravar_teste)

    configurar_log(a.console)
    if not instancia_unica():
        log.info("outro gravador ja esta rodando nesta sessao; saindo")
        return 0
    if not cfg.ok():
        log.error("sem token configurado; rode o instalador")
        return 2
    log.info("HIPO Gravador %s iniciando (%s)", VERSAO, cfg.url)
    app = App(cfg)
    app.iniciar_lacos()

    if a.console:
        try:
            while not app.encerrando.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            app.encerrar()
            time.sleep(2)
        return 0

    try:
        from app.bandeja import Bandeja
    except Exception:  # noqa: BLE001 - sem pystray/Pillow, roda sem ícone
        log.exception("bandeja indisponivel; rodando sem icone")
        app.encerrando.wait()
        return 0
    app.bandeja = Bandeja(app, cfgmod.pasta_dados())
    app.bandeja.atualizar()
    app.bandeja.rodar()        # bloqueia até "Sair"
    time.sleep(2)              # dá tempo de a última gravação ir para a fila
    return 0
