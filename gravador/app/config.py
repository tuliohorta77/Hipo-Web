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
    #   microfone = o softphone abriu o microfone (padrão: o toque de uma
    #               chamada recebida não abre o microfone, então não grava
    #               o "trim-trim");
    #   saida     = o softphone está tocando som (fallback, se o softphone
    #               deixar o microfone aberto o tempo todo).
    detectar_por: str = "microfone"
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
    return cfg


def salvar(cfg: Config, caminho: Path | None = None) -> Path:
    caminho = caminho or caminho_config()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho
