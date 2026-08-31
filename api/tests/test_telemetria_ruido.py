"""
HIPO — O que a telemetria se recusa a gravar.

Puro: sem Postgres, sem HTTP. A decisão de gravar mora numa função sozinha
justamente para poder ser testada assim.

O QUE ESTES TESTES TRAVAM

Os 11 primeiros dias em produção gravaram 2927 eventos, dos quais 1104 eram
varredura automatizada da internet batendo em caminhos inexistentes contra o
IP público — 38% da tabela, sem nenhuma pessoa por trás.

`services/telemetria.adocao()` conta `acoes` sobre a tabela inteira e `erros`
sobre tudo acima de 400. Com o ruído dentro, um domingo em que ninguém
trabalhou fechava com "102 ações, 0 pessoas, taxa de erro 100%" — e relatório
que mente no fim de semana não é lido na segunda.

Se alguém remover o filtro, os dois primeiros testes caem. Os outros existem
para que o filtro não cresça demais e passe a comer sinal de verdade.
"""
from __future__ import annotations

import pytest

from middleware.telemetria import SEM_ROTA, eh_ruido_externo

PESSOA = "aline.martins@controllermedseg.com"


class TestRuidoExterno:
    """A interseção que deve ser descartada: anônima E sem rota."""

    def test_anonima_sem_rota_e_ruido(self):
        assert eh_ruido_externo(None, SEM_ROTA) is True

    @pytest.mark.parametrize("metodo_irrelevante", ["GET", "POST", "PUT", "DELETE"])
    def test_o_metodo_nao_muda_a_decisao(self, metodo_irrelevante):
        """
        Varredura usa GET e POST. A regra olha identidade e rota, não verbo —
        um filtro por método deixaria metade do ruído passar.
        """
        assert eh_ruido_externo(None, SEM_ROTA) is True


class TestOQueNaoPodeSerDescartado:
    """
    Cada condição SOZINHA é sinal legítimo. Só a interseção é ruído.

    É a parte frágil da regra: apertar um pouco mais o filtro parece
    inofensivo e apaga exatamente o dado que a telemetria existe para pegar.
    """

    def test_anonima_com_rota_e_sessao_expirada(self):
        """
        121 `GET /crm/contas` com 401 nos 11 primeiros dias: o front tentando
        de novo com token vencido. Isso é uso de uma pessoa real, e o
        docstring do módulo diz explicitamente que é para capturar.
        """
        assert eh_ruido_externo(None, "/crm/contas") is False

    def test_autenticada_sem_rota_e_bug_de_front(self):
        """
        Alguém de dentro batendo em endpoint que não existe. É defeito nosso,
        e é o caso mais valioso que a telemetria pega sozinha.
        """
        assert eh_ruido_externo(PESSOA, SEM_ROTA) is False

    def test_autenticada_com_rota_e_uso_normal(self):
        assert eh_ruido_externo(PESSOA, "/crm/parceiros/resumo") is False

    def test_login_continua_entrando(self):
        """
        `POST /auth/login` chega sem token — o token é o que ele devolve.
        Como CASA rota, não é ruído. É dele que sai a contagem de quem entrou
        no sistema no dia; descartá-lo zeraria a única métrica de acesso.
        """
        assert eh_ruido_externo(None, "/auth/login") is False


class TestContratoDoMarcador:
    def test_o_marcador_e_o_mesmo_que_o_dispatch_grava(self):
        """
        O `dispatch` e o filtro precisam concordar no literal. Quando eram
        duas strings soltas, mudar uma delas desligava o filtro em silêncio —
        sem erro, sem teste vermelho, só a tabela voltando a encher.
        """
        assert SEM_ROTA == "<sem_rota>"

    def test_rota_vazia_nao_e_tratada_como_sem_rota(self):
        """
        `dispatch` já converte falsy em SEM_ROTA antes de chamar aqui. Se um
        dia passar string vazia direto, é bug de quem chama — e a função não
        deve encobrir isso descartando o evento.
        """
        assert eh_ruido_externo(None, "") is False
