"""
HIPO -- trilha de leitura de dado pessoal (032).

Responde "quem viu o telefone da Fulana, e quando" -- o pedido classico do
titular na LGPD, e o que nenhuma outra tabela do HIPO sabe dizer: a
telemetria (uso_eventos) guarda a ROTA, nunca qual registro foi aberto.

INSTRUMENTACAO EXPLICITA, NAO MIDDLEWARE

Middleware enxergaria o path (`/crm/contatos/{id}`) mas nao a resposta: a
listagem e a busca devolvem 50 pessoas e o path nao diz quais. Quem sabe
quais registros saíram e a propria rota, no momento em que monta a
resposta. Por isso cada rota sensivel chama `registrar_leitura` com os ids
que esta devolvendo.

O QUE E "SENSIVEL" AQUI

Dado de PESSOA FISICA: contatos (nome, telefone, e-mail, aniversario,
LinkedIn) e socios (nome, documento mascarado, faixa etaria). Dado de
empresa (razao social, CNPJ, CNAE) e publico na Receita e nao entra.
As rotas instrumentadas estao listadas em ROTAS_INSTRUMENTADAS -- a suite
confere que cada uma grava.

GUARDA OS IDS, NUNCA O CONTEUDO. Senao a trilha viraria uma segunda copia
do dado pessoal (ver o cabecalho da migration 032).

FALHA NAO DERRUBA A LEITURA. Gravar e um INSERT na mesma conexao da
request; se falhar, e log.error (alerta no Sentry) e a resposta sai. A
escolha e consciente: com a tabela fora, o vendedor continua trabalhando e
o alerta avisa que a trilha tem um buraco -- o contrario tiraria o CRM do
ar por causa do registro de auditoria. O INSERT roda num SAVEPOINT quando
ha transacao aberta, para a falha nao envenenar o resto da request.
"""
from __future__ import annotations

import json
import logging
from typing import Iterable
from uuid import UUID

from services.login_limite import ip_do_cliente

log = logging.getLogger("hipo.auditoria")

RECURSO_CONTATO = "contato"
RECURSO_SOCIO = "socio"

# Teto de ids por linha. A maior listagem do sistema e 200 por pagina;
# folga para nao cortar nada legitimo e ainda impedir um array gigante se
# alguma rota futura devolver a base inteira.
MAX_IDS = 500

# Documentacao viva: (metodo, template da rota) -> recurso. O teste de
# cobertura percorre esta lista.
ROTAS_INSTRUMENTADAS: dict[tuple[str, str], str] = {
    ("GET", "/crm/contatos"): RECURSO_CONTATO,
    ("GET", "/crm/contatos/{contato_id}"): RECURSO_CONTATO,
    ("GET", "/crm/contatos/busca"): RECURSO_CONTATO,
    ("GET", "/crm/contatos/por-alvo"): RECURSO_CONTATO,
    ("GET", "/crm/contatos/duplicatas"): RECURSO_CONTATO,
    ("GET", "/crm/oportunidades/{oportunidade_id}/contatos"): RECURSO_CONTATO,
    ("GET", "/crm/enriquecimento/contas/{conta_id}/socios"): RECURSO_SOCIO,
    ("GET", "/crm/enriquecimento/socios/empresas"): RECURSO_SOCIO,
    ("GET", "/crm/enriquecimento/cnpj/{cnpj}"): RECURSO_SOCIO,
}


def _rota_template(request) -> str:
    rota = request.scope.get("route") if request is not None else None
    caminho = getattr(rota, "path", None)
    if caminho:
        # O include_router concatena o prefixo no path da rota, entao o
        # template ja vem completo (/crm/contatos/{contato_id}).
        return caminho[:200]
    return (request.url.path if request is not None else "?")[:200]


def ids_validos(ids: Iterable) -> list[UUID]:
    """
    Normaliza para lista de UUID, sem repetidos, na ordem em que vieram.

    Aceita UUID, str de UUID ou None (ignorado) -- as rotas passam
    `r["id"]` direto das linhas do asyncpg ou dos dicts de resposta.

    >>> ids_validos([None, "6f1c3b1e-0c2a-4c6e-9a51-1d2b3c4d5e6f",
    ...              "6f1c3b1e-0c2a-4c6e-9a51-1d2b3c4d5e6f"])
    [UUID('6f1c3b1e-0c2a-4c6e-9a51-1d2b3c4d5e6f')]
    """
    vistos: set[UUID] = set()
    saida: list[UUID] = []
    for i in ids or ():
        if i is None:
            continue
        try:
            u = i if isinstance(i, UUID) else UUID(str(i))
        except (ValueError, TypeError):
            continue
        if u in vistos:
            continue
        vistos.add(u)
        saida.append(u)
        if len(saida) >= MAX_IDS:
            break
    return saida


def _contexto_serializavel(contexto: dict | None) -> str:
    limpo = {k: (str(v) if isinstance(v, UUID) else v)
             for k, v in (contexto or {}).items() if v is not None}
    return json.dumps(limpo, default=str, ensure_ascii=False)


async def registrar_leitura(
    conn,
    request,
    user: dict,
    recurso: str,
    ids: Iterable,
    contexto: dict | None = None,
) -> None:
    """
    Uma linha em leituras_sensiveis para esta resposta.

    `ids` sao os registros DEVOLVIDOS (lista vazia tambem grava: a busca
    que nao achou ninguem e uma tentativa de ver). `contexto` leva o que
    situa a leitura -- conta, oportunidade, termo buscado -- e nunca o dado
    devolvido.
    """
    try:
        args = (
            user.get("id"),
            user.get("email") or "?",
            user.get("cargo"),
            recurso,
            _rota_template(request),
            ids_validos(ids),
            _contexto_serializavel(contexto),
            ip_do_cliente(request) if request is not None else None,
        )
        sql = """
            INSERT INTO leituras_sensiveis
                (usuario_id, usuario_email, cargo, recurso, rota,
                 registro_ids, contexto, ip)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        """
        if conn.is_in_transaction():
            async with conn.transaction():  # savepoint
                await conn.execute(sql, *args)
        else:
            await conn.execute(sql, *args)
    except Exception:
        log.error("leituras_sensiveis: falha ao gravar leitura de %s", recurso, exc_info=True)
