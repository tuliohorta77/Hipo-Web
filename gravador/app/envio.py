"""
O envio da fila para o HIPO, um passo de cada vez.

Para cada gravação pendente, em ordem de horário:

  1. pede ao HIPO a ligação e a URL de upload (o HIPO casa com o clique);
  2. sobe o FLAC direto no S3;
  3. avisa o HIPO que subiu (ele confere no S3 e começa a transcrição);
  4. apaga da máquina.

Erro de rede ou servidor fora para o passo (não martela) e reagenda a
gravação com espera crescente. Token inválido para TUDO até alguém
reconfigurar — insistir com um token revogado só enche o log do servidor.
"""
from __future__ import annotations

import logging
import time

from app.cliente import (
    ArquivoNaoChegou, GravacaoRecusada, Indisponivel, NaoEncontrada, TokenInvalido,
)
from app.fila import Fila

log = logging.getLogger("gravador.envio")


class Enviador:
    def __init__(self, fila: Fila, cliente):
        self.fila = fila
        self.cliente = cliente
        self.token_invalido = False
        self.ultimo_erro: str | None = None
        self.enviadas = 0

    def passo(self, agora: float | None = None) -> int:
        """Envia o que der agora. Devolve quantas gravações saíram da fila."""
        if self.token_invalido:
            return 0
        agora = time.time() if agora is None else agora
        feitas = 0
        for meta in self.fila.pendentes(agora):
            try:
                self._enviar(meta, agora)
            except TokenInvalido as e:
                self.token_invalido = True
                self.ultimo_erro = f"Token recusado pelo HIPO: {e}"
                log.error(self.ultimo_erro)
                return feitas
            except GravacaoRecusada as e:
                self.fila.descartar(meta["id"], f"recusada pelo HIPO: {e}")
                continue
            except NaoEncontrada as e:
                # Descartada na tela enquanto subia: não recria a ligação.
                log.info("gravacao %s nao existe mais no HIPO (%s); apagando daqui", meta["id"], e)
                self.fila.remover(meta["id"])
                continue
            except Indisponivel as e:
                self.ultimo_erro = str(e)
                novo = self.fila.falhou(meta, agora)
                log.warning("gravacao %s: %s (tentativa %d)", meta["id"], e, novo["tentativas"])
                return feitas
            feitas += 1
            self.enviadas += 1
            self.ultimo_erro = None
        return feitas

    def _enviar(self, meta: dict, agora: float) -> None:
        arquivo = self.fila.audio(meta["id"])
        tamanho = arquivo.stat().st_size
        # Sem `agora`: o cliente usa o relógio do momento do pedido (ver
        # Cliente.nova_gravacao). O `agora` do passo serve só para a fila.
        r = self.cliente.nova_gravacao(meta, tamanho)
        if r.get("ja_recebida"):
            log.info("gravacao %s ja estava no HIPO (ligacao %s)", meta["id"], r.get("ligacao_id"))
            self.fila.remover(meta["id"])
            return
        for tentativa in (1, 2):
            self.cliente.subir(r["upload_url"], arquivo, r["content_type"])
            try:
                fim = self.cliente.concluir(r["ligacao_id"])
                break
            except ArquivoNaoChegou:
                if tentativa == 2:
                    raise Indisponivel("o S3 nao confirmou o arquivo depois de duas subidas") from None
        log.info(
            "gravacao %s enviada: ligacao %s, %s, %s",
            meta["id"], r["ligacao_id"], fim.get("status"),
            "vinculada ao clique" if r.get("vinculada") else "sem vinculo",
        )
        self.fila.remover(meta["id"])
