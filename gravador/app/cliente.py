"""
Conversa com o HIPO (e com o S3, pela URL que o HIPO assina).

As respostas de erro do servidor viram exceções com significado para o
gravador (ver routers/ligacoes_gravador.py no HIPO):

  401 → TokenInvalido          para de enviar e avisa na bandeja
  422 → GravacaoRecusada       descarta a gravação
  409 → ArquivoNaoChegou       sobe de novo
  404 → NaoEncontrada          a gravação foi descartada no HIPO: apaga daqui
  503, 5xx, rede → Indisponivel  guarda e tenta depois
"""
from __future__ import annotations

import logging
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("gravador.cliente")

TIMEOUT = (10, 60)            # conectar, ler
TIMEOUT_UPLOAD = (10, 600)


class ErroHipo(Exception):
    pass


class TokenInvalido(ErroHipo):
    pass


class GravacaoRecusada(ErroHipo):
    pass


class ArquivoNaoChegou(ErroHipo):
    pass


class Indisponivel(ErroHipo):
    pass


class NaoEncontrada(ErroHipo):
    """404: o HIPO não tem mais esta gravação (descartada na tela)."""


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _detalhe(resp) -> str:
    try:
        d = resp.json().get("detail")
        return d if isinstance(d, str) else str(d)
    except Exception:  # noqa: BLE001
        return (resp.text or "")[:200]


class Cliente:
    def __init__(self, url: str, token: str, versao: str, sessao=None):
        import requests

        self.url = url.rstrip("/")
        self.versao = versao
        self.http = sessao or requests.Session()
        self.http.headers.update({
            "Authorization": f"Bearer {token}",
            "User-Agent": f"HIPO-Gravador/{versao}",
        })

    def _post(self, caminho: str, corpo: dict | None = None) -> dict:
        import requests

        try:
            r = self.http.post(f"{self.url}{caminho}", json=corpo or {}, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise Indisponivel(f"sem conexao com o HIPO: {type(e).__name__}") from e
        if r.status_code == 401:
            raise TokenInvalido(_detalhe(r))
        if r.status_code == 422:
            raise GravacaoRecusada(_detalhe(r))
        if r.status_code == 409:
            raise ArquivoNaoChegou(_detalhe(r))
        if r.status_code == 404:
            raise NaoEncontrada(_detalhe(r))
        if r.status_code >= 400:
            raise Indisponivel(f"HIPO respondeu {r.status_code}: {_detalhe(r)}")
        return r.json()

    def pulso(self) -> dict:
        return self._post("/ligacoes/gravador/pulso", {
            "versao": self.versao,
            "maquina": (os.environ.get("COMPUTERNAME") or platform.node() or "")[:120],
        })

    def nova_gravacao(self, meta: dict, tamanho: int, agora: float | None = None) -> dict:
        # `agora` é o relógio da máquina NO MOMENTO do pedido: o servidor
        # usa a diferença para corrigir o desvio do relógio. Um valor de
        # minutos atrás (fila longa, upload lento antes deste) seria lido
        # como desvio e empurraria a ligação para fora da janela do clique.
        agora = time.time() if agora is None else agora
        return self._post("/ligacoes/gravador/gravacoes", {
            "inicio": iso(meta["inicio_ts"]),
            "fim": iso(meta["fim_ts"]),
            "agora": iso(agora),
            "duracao_s": round(meta["duracao_s"], 1),
            "tamanho_bytes": tamanho,
            "formato": "flac",
            "id_local": meta["id"],
        })

    def subir(self, url: str, arquivo: Path, content_type: str) -> None:
        """PUT direto no S3. Sem o Authorization do HIPO: a URL já é a credencial."""
        import requests

        tamanho = arquivo.stat().st_size
        try:
            with open(arquivo, "rb") as f:
                r = requests.put(url, data=f, timeout=TIMEOUT_UPLOAD, headers={
                    "Content-Type": content_type, "Content-Length": str(tamanho),
                })
        except requests.RequestException as e:
            raise Indisponivel(f"upload falhou: {type(e).__name__}") from e
        if r.status_code >= 300:
            raise Indisponivel(f"S3 recusou o upload ({r.status_code}): {r.text[:200]}")

    def concluir(self, ligacao_id: str) -> dict:
        return self._post(f"/ligacoes/gravador/gravacoes/{ligacao_id}/concluir")
