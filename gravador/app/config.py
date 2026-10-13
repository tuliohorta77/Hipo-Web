"""
Configuração do gravador e as pastas onde ele guarda as coisas.

  %APPDATA%\\HIPO Gravador\\config.json      endereço do HIPO, token, ajustes
  %LOCALAPPDATA%\\HIPO Gravador\\fila\\        gravações esperando envio
  %LOCALAPPDATA%\\HIPO Gravador\\gravador.log  diário (gira em 5 arquivos de 1 MB)

HIPO_GRAVADOR_DIR no ambiente troca as duas pastas por uma só (testes).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

URL_PADRAO = "https://hipogestao.com.br/api"

# Nomes de executável (sem .exe) do softphone. A busca é por TRECHO, sem
# diferenciar maiúscula: "accession" pega "Accession Communicator.exe".
# O cliente desktop do Vivo Voz Negócio é da Metaswitch; o nome exato muda
# entre versões, por isso a lista é larga e configurável. Para descobrir o
# da sua máquina: hipo_gravador.pyw --descobrir (durante uma ligação).
PROCESSOS_PADRAO = [
    "Vivo Voz",
    "VivoVoz",
    "Accession",
    "MaX UC",
    "MaXUC",
    "CommPortal",
    "Metaswitch",
]


@dataclass
class Config:
    url: str = URL_PADRAO
    token: str = ""
    processos: list[str] = field(default_factory=lambda: list(PROCESSOS_PADRAO))
    # Como saber que a chamada está acontecendo:
    #   som       = está passando som pela SAÍDA do softphone (padrão desde a
    #               1.0.4). Fora de chamada a saída dele é zero absoluto; na
    #               chamada nunca é -- até no silêncio do cliente tem o ruído
    #               da linha. Medido em 13/10/2026 com headset Logitech USB, em
    #               que o Vivo deixa microfone e saída abertos o tempo todo.
    #   microfone = o softphone abriu o microfone (o modo da 1.0.0 a 1.0.3;
    #               só serve se o softphone fecha o microfone entre chamadas);
    #   saida     = a sessão de saída do softphone está aberta.
    detectar_por: str = "som"
    # Pico de som (0 a 1) acima do qual a saída "está passando som". O ruído
    # da linha numa chamada medido foi ~0,0013; fora de chamada, 0,00000.
    limiar_som: float = 0.0002
    # Versão do formato do config.json. A 2 trocou o padrão de detecção para
    # "som"; config gravado antes disso é migrado no carregar().
    config_versao: int = 2
    # Qual microfone e qual saída gravar:
    #   comunicacao = o dispositivo padrão de COMUNICAÇÃO do Windows (o
    #                 headset, normalmente — é o que softphone usa);
    #   padrao      = o dispositivo padrão comum;
    #   outro texto = trecho do nome do dispositivo ("Jabra", "Headset").
    entrada: str = "comunicacao"
    saida: str = "comunicacao"
    taxa: int = 16000
    # Segundos sem sinal de chamada para considerar que desligou.
    fim_apos_silencio_s: float = 4.0
    # Chamada mais curta que isso não é enviada (discou errado, desligou).
    min_duracao_s: float = 8.0
    # Teto de uma gravação. Duas horas cobrem qualquer ligação de venda e
    # seguram a memória (~500 MB no pico ao fechar o arquivo).
    max_duracao_s: float = 2 * 3600

    def ok(self) -> bool:
        return bool(self.url and self.token.startswith("hipograv_"))


def pasta_config() -> Path:
    base = os.environ.get("HIPO_GRAVADOR_DIR")
    if base:
        return Path(base)
    return Path(os.environ.get("APPDATA", Path.home())) / "HIPO Gravador"


def pasta_dados() -> Path:
    base = os.environ.get("HIPO_GRAVADOR_DIR")
    if base:
        return Path(base)
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "HIPO Gravador"


def caminho_config() -> Path:
    return pasta_config() / "config.json"


def carregar(caminho: Path | None = None) -> Config:
    caminho = caminho or caminho_config()
    if not caminho.is_file():
        return Config()
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    padrao = Config()
    campos = {k: bruto[k] for k in asdict(padrao) if k in bruto}
    cfg = Config(**{**asdict(padrao), **campos})
    cfg.url = (cfg.url or URL_PADRAO).rstrip("/")
    if int(bruto.get("config_versao", 1) or 1) < 2:
        # Instalações até a 1.0.3 gravaram "microfone" sem ninguém escolher.
        # Passam para "som", que funciona com e sem o microfone preso.
        if cfg.detectar_por == "microfone":
            cfg.detectar_por = "som"
        cfg.config_versao = 2
        try:
            salvar(cfg, caminho)
        except OSError:
            pass
    return cfg


def salvar(cfg: Config, caminho: Path | None = None) -> Path:
    caminho = caminho or caminho_config()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho
