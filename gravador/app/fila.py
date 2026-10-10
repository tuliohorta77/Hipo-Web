"""
A fila em disco das gravações que ainda não chegaram ao HIPO.

Cada gravação são dois arquivos na pasta `fila/`:

  <id>.flac   o áudio
  <id>.json   início, fim, duração e o estado do envio

Nada se perde se a internet cair, o notebook fechar a tampa ou o Windows
reiniciar no meio do envio: na próxima vez que o gravador subir, a fila
continua de onde parou. O `id` vai para o servidor como `id_local`, então o
reenvio cai na MESMA ligação lá — não duplica.

Gravação que o servidor recusa de vez (curta demais, formato) vai para
`descartadas/` com o motivo, e some depois de 7 dias. Gravação que não
consegue ser enviada em 7 dias também vai para lá: é o limite para um
áudio de cliente ficar parado na máquina.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from pathlib import Path

log = logging.getLogger("gravador.fila")

PRAZO_S = 7 * 24 * 3600


def espera_apos_falha(tentativas: int) -> float:
    """
    30 s, 1 min, 2 min, 4 min… até 30 min. Servidor fora não é martelado.

    >>> [espera_apos_falha(n) for n in (1, 2, 3, 10)]
    [30, 60, 120, 1800]
    """
    return min(30 * (2 ** max(0, tentativas - 1)), 1800)


class Fila:
    def __init__(self, pasta: Path):
        self.pasta = pasta / "fila"
        self.descartes = pasta / "descartadas"
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.descartes.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def novo_id() -> str:
        return uuid.uuid4().hex

    def audio(self, id_: str) -> Path:
        return self.pasta / f"{id_}.flac"

    def _meta(self, id_: str) -> Path:
        return self.pasta / f"{id_}.json"

    def adicionar(self, id_: str, meta: dict) -> None:
        meta = {"id": id_, "tentativas": 0, "proxima_em": 0, "criado_em": time.time(), **meta}
        tmp = self._meta(id_).with_suffix(".tmp")
        tmp.write_text(json.dumps(meta), encoding="utf-8")
        tmp.replace(self._meta(id_))

    def atualizar(self, meta: dict) -> None:
        self.adicionar(meta["id"], meta)

    def pendentes(self, agora: float | None = None) -> list[dict]:
        agora = time.time() if agora is None else agora
        itens = []
        for p in self.pasta.glob("*.json"):
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                log.warning("metadado ilegivel: %s", p.name)
                continue
            if not self.audio(meta["id"]).is_file():
                p.unlink(missing_ok=True)
                continue
            if meta.get("proxima_em", 0) <= agora:
                itens.append(meta)
        return sorted(itens, key=lambda m: m.get("inicio", ""))

    def quantidade(self) -> int:
        return len(list(self.pasta.glob("*.json")))

    def remover(self, id_: str) -> None:
        self.audio(id_).unlink(missing_ok=True)
        self._meta(id_).unlink(missing_ok=True)

    def descartar(self, id_: str, motivo: str) -> None:
        log.warning("gravacao %s descartada: %s", id_, motivo)
        for p in (self.audio(id_), self._meta(id_)):
            if p.exists():
                shutil.move(str(p), str(self.descartes / p.name))
        (self.descartes / f"{id_}.motivo.txt").write_text(motivo, encoding="utf-8")

    def falhou(self, meta: dict, agora: float | None = None) -> dict:
        agora = time.time() if agora is None else agora
        meta = {**meta, "tentativas": int(meta.get("tentativas", 0)) + 1}
        meta["proxima_em"] = agora + espera_apos_falha(meta["tentativas"])
        self.atualizar(meta)
        return meta

    def limpar(self, agora: float | None = None) -> int:
        """Descarta o que passou do prazo na fila e apaga descartes velhos."""
        agora = time.time() if agora is None else agora
        n = 0
        for p in self.pasta.glob("*.json"):
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if agora - meta.get("criado_em", agora) > PRAZO_S:
                self.descartar(meta["id"], "nao foi possivel enviar em 7 dias")
                n += 1
        for p in self.descartes.iterdir():
            try:
                if agora - p.stat().st_mtime > PRAZO_S:
                    p.unlink()
            except OSError:
                pass
        return n
