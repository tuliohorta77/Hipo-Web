"""
O ícone na bandeja do Windows (ao lado do relógio).

  verde    pronto, esperando ligação
  vermelho GRAVANDO — quem está na ligação vê que está sendo gravado
  cinza    pausado (o executivo pausou para uma ligação pessoal)
  amarelo  problema (token recusado, sem conexão com o HIPO)

Menu: o estado por extenso, Pausar/Retomar, abrir a pasta do diário e Sair.
"""
from __future__ import annotations

import logging
import os
import subprocess

log = logging.getLogger("gravador.bandeja")

CORES = {
    "pronto": (34, 160, 90),
    "gravando": (220, 38, 38),
    "pausado": (140, 140, 140),
    "problema": (234, 179, 8),
}


def _imagem(cor):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=cor + (255,), outline=(255, 255, 255, 255), width=4)
    # O "fone" no meio: duas barras brancas.
    d.rounded_rectangle((22, 18, 30, 46), radius=3, fill=(255, 255, 255, 255))
    d.rounded_rectangle((34, 18, 42, 46), radius=3, fill=(255, 255, 255, 255))
    return img


class Bandeja:
    def __init__(self, app, pasta_log):
        import pystray

        self.app = app
        self.pasta_log = pasta_log
        self._cor_atual = None
        self.icone = pystray.Icon(
            "hipo-gravador",
            _imagem(CORES["pronto"]),
            "HIPO Gravador",
            menu=pystray.Menu(
                pystray.MenuItem(lambda _: self.app.texto_estado(), None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Pausar gravação", self._alternar_pausa,
                    checked=lambda _: self.app.pausado,
                ),
                pystray.MenuItem("Abrir pasta do diário", self._abrir_log),
                pystray.MenuItem("Sair", self._sair),
            ),
        )

    def atualizar(self) -> None:
        cor = self.app.cor_estado()
        if cor != self._cor_atual:
            self._cor_atual = cor
            self.icone.icon = _imagem(CORES[cor])
        self.icone.title = f"HIPO Gravador — {self.app.texto_estado()}"[:127]
        try:
            self.icone.update_menu()
        except Exception:  # noqa: BLE001
            pass

    def avisar(self, texto: str) -> None:
        try:
            self.icone.notify(texto, "HIPO Gravador")
        except Exception:  # noqa: BLE001
            pass

    def _alternar_pausa(self, *_):
        self.app.alternar_pausa()
        self.atualizar()

    def _abrir_log(self, *_):
        try:
            os.startfile(str(self.pasta_log))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            subprocess.Popen(["explorer", str(self.pasta_log)])

    def _sair(self, *_):
        self.app.encerrar()
        self.icone.stop()

    def rodar(self) -> None:
        self.icone.run()
