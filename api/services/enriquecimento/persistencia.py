"""
HIPO — Enriquecimento: cache, gravação e as regras de sobrescrita.

Aqui moram as três decisões que o resto do sistema não precisa conhecer:

  1. CACHE POR (CNPJ, FONTE), COM TTL. Consulta repetida dentro do prazo lê
     de `conta_enriquecimentos` em vez de ir à rede. Numa fonte paga isso é
     dinheiro: reabrir a mesma conta cinco vezes na semana custaria cinco
     consultas. Numa fonte pública é educação — a BrasilAPI não cobra, mas
     também não tem SLA, e quem a martela leva 429.

  2. ENRIQUECIMENTO NÃO SOBRESCREVE TRABALHO HUMANO. Campo já preenchido
     fica como está, e a divergência é devolvida para a tela mostrar lado a
     lado. Quem decide é quem está olhando. A carga da Oraculus já ensinou
     isso: `ORACULU'S CONTABIL LTDA` no banco contra `Oraculus Contabil
     Ltda` na planilha, e o banco venceu porque veio de gente.

  3. ESTIMADO NUNCA SOBRESCREVE DECLARADO. Vale para `num_funcionarios` e
     é a regra mais cara de furar: o número que o cliente informou vira
     proposta; o número estimado pela fonte paga é de base anual defasada.
     Nem com `sobrescrever=True` um estimado passa por cima de um declarado
     — o único jeito de mudar um declarado é alguém digitar outro.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from config import settings

from . import cnae_estrutura
from . import fontes as fontes_mod
from .modelo import (
    DECLARADO,
    ESTIMADO,
    DadosEmpresa,
    mesclar,
    normalizar_brasilapi,
    normalizar_leadcnpj,
)

log = logging.getLogger("hipo.enriquecimento")

NORMALIZADORES = {
    fontes_mod.BRASILAPI: normalizar_brasilapi,
    fontes_mod.LEADCNPJ: normalizar_leadcnpj,
}

# Campos de `contas` que o enriquecimento sabe preencher. `vertical_id` está
# aqui mas não vem da fonte: é derivado do mapeamento do CNAE.
CAMPOS_ENRIQUECIVEIS = (
    "razao_social", "nome_fantasia", "cnae_codigo", "porte",
    "situacao_cadastral", "data_abertura", "capital_social",
    "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
    "telefone", "telefone_2", "email", "num_funcionarios", "vertical_id",
)

# Colunas NUMERIC. asyncpg recusa float em NUMERIC — precisa de Decimal, e
# `Decimal(str(x))` em vez de `Decimal(x)` para não arrastar o lixo binário
# do float ("1000.0000000000001").
CAMPOS_NUMERICOS = {"capital_social"}


def _vazio(valor) -> bool:
    """Campo ausente para efeito de sobrescrita."""
    if valor is None:
        return True
    if isinstance(valor, str) and not valor.strip():
        return True
    return False


def _para_banco(campo: str, valor):
    if campo in CAMPOS_NUMERICOS and valor is not None:
        return Decimal(str(valor))
    return valor


def _chave_texto(valor) -> str:
    """
    Forma comparável de um texto: sem acento, sem caixa, sem espaço sobrando.

    NÃO remove espaços internos, só colapsa repetição. A diferença importa:
    `ARUJÁ` e `ARUJA` são a mesma cidade escrita com e sem acento, mas
    `A COSTA IMOVEIS` e `ACOSTA IMOVEIS` são duas grafias diferentes da
    razão social, e essa o usuário precisa ver para decidir.
    """
    texto = unicodedata.normalize("NFKD", str(valor).strip())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).casefold()


# Campos em que SÓ OS DÍGITOS importam: a máscara é escolha de quem
# digitou, não informação. `(11) 6860-7201` no cadastro e `1168607201` na
# fonte são o mesmo telefone, e oferecer a troca só tiraria a formatação
# que a pessoa pôs.
CAMPOS_SO_DIGITOS = {"telefone", "telefone_2", "cep"}


def _mesmo_valor(campo: str, atual, sugerido) -> bool:
    """
    O cadastro e a fonte dizem a mesma coisa?

    Comparar com `str()` puro produzia divergência onde não há nenhuma. O
    capital social é `NUMERIC` no banco e volta do asyncpg como
    `Decimal('200000.00')`; a Receita manda `200000.0`. Texto diferente,
    número idêntico — e a tela pedia ao usuário que escolhesse entre dois
    valores iguais, em toda conta consultada.

    Número compara por VALOR. Texto compara sem acento e sem caixa, porque
    trocar `ARUJÁ` por `ARUJA` só pioraria o cadastro. Telefone e CEP
    comparam só os dígitos: a máscara é formatação, não conteúdo.
    """
    if atual is None or sugerido is None:
        return atual is sugerido
    if campo in CAMPOS_SO_DIGITOS:
        so = lambda v: re.sub(r"\D", "", str(v))  # noqa: E731
        return so(atual) == so(sugerido)
    numero = (int, float, Decimal)
    if isinstance(atual, numero) and isinstance(sugerido, numero) \
            and not isinstance(atual, bool) and not isinstance(sugerido, bool):
        try:
            return Decimal(str(atual)) == Decimal(str(sugerido))
        except (ArithmeticError, ValueError):
            return False
    return _chave_texto(atual) == _chave_texto(sugerido)


# ── Consulta com cache ───────────────────────────────────────────────────────

async def _do_cache(conn, cnpj: str, fonte: str, ttl_dias: int) -> dict | None:
    if ttl_dias <= 0:
        return None
    limite = datetime.now(timezone.utc) - timedelta(days=ttl_dias)
    row = await conn.fetchrow(
        """
        SELECT payload
          FROM conta_enriquecimentos
         WHERE cnpj = $1 AND fonte = $2 AND sucesso AND consultado_em >= $3
         ORDER BY consultado_em DESC
         LIMIT 1
        """,
        cnpj, fonte, limite,
    )
    if not row or row["payload"] is None:
        return None
    bruto = row["payload"]
    # asyncpg devolve jsonb como str quando não há codec registrado.
    if isinstance(bruto, str):
        try:
            return json.loads(bruto)
        except ValueError:
            return None
    return bruto if isinstance(bruto, dict) else None


async def _registrar(
    conn, cnpj: str, fonte: str, sucesso: bool,
    payload: dict | None, erro: str | None, user_id, conta_id=None,
) -> None:
    await conn.execute(
        """
        INSERT INTO conta_enriquecimentos
            (cnpj, conta_id, fonte, sucesso, erro, payload, consultado_por)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
        """,
        cnpj, conta_id, fonte, sucesso, erro,
        json.dumps(payload, ensure_ascii=False, default=str) if payload else None,
        user_id,
    )


async def consultar(
    conn, cnpj: str, user_id=None, conta_id=None, forcar: bool = False,
) -> tuple[DadosEmpresa | None, list[str]]:
    """
    Consulta todas as fontes habilitadas e devolve `(dados, avisos)`.

    `dados` é None só quando NENHUMA fonte respondeu. Uma que falhou com
    outra que respondeu produz dados + aviso — o cadastro segue com o que
    deu para obter, e a tela conta o que faltou.

    `forcar=True` ignora o cache. É o botão "Atualizar" da tela: quando o
    usuário aperta, ele quer o dado de hoje, não o de noventa dias atrás.
    """
    habilitadas = fontes_mod.fontes_habilitadas()
    if not habilitadas:
        return None, ["Nenhuma fonte de enriquecimento configurada."]

    ttl = int(getattr(settings, "ENRIQUECIMENTO_TTL_DIAS", 90) or 0)
    avisos: list[str] = []
    resultados: list[DadosEmpresa] = []

    for fonte in habilitadas:
        payload = None if forcar else await _do_cache(conn, cnpj, fonte, ttl)
        veio_do_cache = payload is not None

        if payload is None:
            buscador = fontes_mod.BUSCADORES.get(fonte)
            if buscador is None:
                continue
            payload, erro = await buscador(cnpj)
            await _registrar(
                conn, cnpj, fonte, payload is not None, payload, erro,
                user_id, conta_id,
            )
            if payload is None:
                avisos.append(f"{fonte}: {erro}")
                continue

        normalizador = NORMALIZADORES.get(fonte)
        if normalizador is None:
            continue
        try:
            dados = normalizador(payload)
        except Exception as e:  # pragma: no cover - blindagem de parser
            # Payload que muda de forma não pode derrubar o cadastro. Vira
            # aviso e o enriquecimento segue com as outras fontes.
            log.exception("enriquecimento: %s falhou ao normalizar", fonte)
            avisos.append(f"{fonte}: resposta em formato inesperado ({type(e).__name__}).")
            continue

        # O CNPJ da resposta pode vir vazio; o que vale é o consultado.
        if not dados.cnpj:
            dados = dataclasses.replace(dados, cnpj=cnpj)
        resultados.append(dados)
        if veio_do_cache:
            avisos.append(f"{fonte}: dado do cache local (até {ttl} dias).")

    return mesclar(*resultados), avisos


# ── CNAEs ────────────────────────────────────────────────────────────────────

async def vertical_por_slug(conn, slug: str, nome: str) -> int | None:
    """
    Id da vertical com este slug, criando-a se ainda não existir.

    O slug é a chave real das listas de domínio (é ele que tem UNIQUE), e é
    por isso que a derivação nunca duplica nem renomeia: se a operação já
    tem uma vertical "Saúde", a derivação reaproveita aquele id em vez de
    criar outra.
    """
    return await conn.fetchval(
        """
        INSERT INTO verticais (nome, slug)
        VALUES ($2, $1)
        ON CONFLICT (slug) DO UPDATE SET nome = verticais.nome
     RETURNING id
        """,
        slug, nome,
    )


async def garantir_cnae(
    conn, codigo: str | None, descricao: str | None, derivar: bool = True,
) -> dict | None:
    """
    Cria o CNAE se ainda não existir e devolve o registro com o mapeamento.

    NASCE COM A VERTICAL DERIVADA DA SEÇÃO DA CNAE 2.0 (015).

    Antes nascia vazio, esperando alguém classificar um a um — e com
    centenas de códigos na base isso é trabalho que não termina. A derivação
    não é chute: a CNAE é uma hierarquia oficial do IBGE, e a seção de um
    código é um fato da classificação, não uma opinião. Ver
    `cnae_estrutura.py`.

    A marca `mapeamento_origem='derivado'` é o que mantém a honestidade: a
    tela mostra como sugestão, e corrigir uma sugestão continua sendo
    trabalho operacional. O que uma pessoa decidiu fica 'humano' e a
    derivação nunca encosta.

    O GRAU DE RISCO CONTINUA NULO — ele vale por subclasse no Anexo I da
    NR-4, não por seção.

    A descrição é atualizada quando chega uma não vazia e a guardada é o
    placeholder — a Receita às vezes devolve o CNAE sem texto.
    """
    if not codigo:
        return None
    texto = (descricao or "").strip() or "CNAE sem descrição"

    vertical_id = None
    if derivar:
        secao = cnae_estrutura.secao_de(codigo)
        if secao:
            _, slug, nome = secao
            vertical_id = await vertical_por_slug(conn, slug, nome)

    # O DO UPDATE só preenche o que está VAZIO: um CNAE já classificado (por
    # gente ou por derivação anterior) não é tocado por uma nova consulta.
    row = await conn.fetchrow(
        """
        INSERT INTO cnaes (codigo, descricao, vertical_id, mapeado_em,
                           mapeamento_origem)
        VALUES ($1, $2, $3,
                CASE WHEN $3::int IS NULL THEN NULL ELSE NOW() END,
                CASE WHEN $3::int IS NULL THEN NULL ELSE 'derivado' END)
        ON CONFLICT (codigo) DO UPDATE
           SET descricao = CASE
                   WHEN cnaes.descricao = 'CNAE sem descrição'
                    AND EXCLUDED.descricao <> 'CNAE sem descrição'
                   THEN EXCLUDED.descricao
                   ELSE cnaes.descricao
               END,
               vertical_id = COALESCE(cnaes.vertical_id, EXCLUDED.vertical_id),
               mapeado_em = COALESCE(cnaes.mapeado_em, EXCLUDED.mapeado_em),
               mapeamento_origem = COALESCE(
                   cnaes.mapeamento_origem, EXCLUDED.mapeamento_origem
               )
     RETURNING codigo, descricao, vertical_id, grau_risco, mapeado_em,
               mapeamento_origem
        """,
        codigo, texto, vertical_id,
    )
    return dict(row) if row else None


async def _gravar_secundarios(conn, conta_id, dados: DadosEmpresa) -> int:
    if not dados.cnaes_secundarios:
        return 0
    gravados = 0
    for codigo, descricao in dados.cnaes_secundarios:
        await garantir_cnae(conn, codigo, descricao)
        resultado = await conn.execute(
            """
            INSERT INTO conta_cnaes_secundarios (conta_id, cnae_codigo)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            conta_id, codigo,
        )
        if resultado.endswith(" 1"):
            gravados += 1
    return gravados


# ── Sócios ───────────────────────────────────────────────────────────────────

async def _gravar_socios(conn, conta_id, dados: DadosEmpresa, user_id) -> int:
    """
    Insere os sócios novos. NÃO apaga os antigos.

    Sócio que saiu do QSA continua na tabela com a data de captura antiga —
    apagar perderia a informação de que aquela pessoa esteve na empresa, que
    é justamente o que interessa numa conversa comercial. A tela ordena por
    captura e mostra a data.
    """
    inseridos = 0
    for socio in dados.socios:
        resultado = await conn.execute(
            """
            INSERT INTO conta_socios
                (conta_id, nome, nome_normalizado, documento_mascarado,
                 qualificacao, faixa_etaria, entrada_em, eh_pj, fonte,
                 criado_por)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (conta_id, nome_normalizado,
                         COALESCE(documento_mascarado, '')) DO NOTHING
            """,
            conta_id, socio.nome, socio.nome_normalizado,
            socio.documento_mascarado, socio.qualificacao, socio.faixa_etaria,
            socio.entrada_em, socio.eh_pj, dados.fonte, user_id,
        )
        if resultado.endswith(" 1"):
            inseridos += 1
    return inseridos


# ── Aplicação na conta ───────────────────────────────────────────────────────

async def aplicar(
    conn,
    conta_id,
    dados: DadosEmpresa,
    user_id,
    campos: list[str] | None = None,
    sobrescrever: bool = False,
) -> dict:
    """
    Grava o enriquecimento na conta e devolve o que foi feito.

    `campos=None` aplica todos os que a fonte trouxe; uma lista restringe ao
    que o usuário marcou na tela.

    Devolve:
        aplicados  — {campo: valor gravado}
        mantidos   — [{campo, atual, sugerido}] para a tela mostrar a
                     divergência e deixar a decisão com quem está olhando
        cnae       — o registro do CNAE principal, com o mapeamento atual
        socios     — quantos sócios novos entraram
        secundarios— quantos CNAEs secundários novos entraram
    """
    atual = await conn.fetchrow(
        """
        SELECT id, razao_social, nome_fantasia, cnae_codigo, porte,
               situacao_cadastral, data_abertura, capital_social,
               cep, logradouro, numero, complemento, bairro, cidade, uf,
               telefone, telefone_2, email, num_funcionarios,
               num_funcionarios_origem, vertical_id
          FROM contas WHERE id = $1
        """,
        conta_id,
    )
    if atual is None:
        raise ValueError("Conta não encontrada.")

    cnae = await garantir_cnae(conn, dados.cnae_codigo, dados.cnae_descricao)

    sugestoes = dados.campos_de_conta()

    # A vertical não vem da fonte: vem do mapeamento do CNAE. Só entra como
    # sugestão quando alguém já mapeou aquele CNAE — senão o campo fica
    # vazio e a tela pede o mapeamento ali mesmo.
    if cnae and cnae.get("vertical_id"):
        sugestoes["vertical_id"] = cnae["vertical_id"]

    permitidos = set(campos) if campos else set(CAMPOS_ENRIQUECIVEIS)

    aplicados: dict = {}
    mantidos: list[dict] = []

    for campo, sugerido in sugestoes.items():
        if campo not in CAMPOS_ENRIQUECIVEIS or campo not in permitidos:
            continue

        valor_atual = atual[campo]

        # A regra que protege a proposta comercial. Ver o cabeçalho.
        if campo == "num_funcionarios":
            origem_atual = atual["num_funcionarios_origem"]
            if valor_atual is not None and origem_atual == DECLARADO:
                mantidos.append({
                    "campo": campo,
                    "atual": valor_atual,
                    "sugerido": sugerido,
                    "motivo": "número declarado pelo cliente",
                })
                continue

        if not _vazio(valor_atual) and not sobrescrever:
            if not _mesmo_valor(campo, valor_atual, sugerido):
                mantidos.append({
                    "campo": campo,
                    "atual": valor_atual,
                    "sugerido": sugerido,
                    "motivo": "já preenchido",
                })
            continue

        aplicados[campo] = sugerido

    if aplicados:
        colunas = list(aplicados.keys())
        valores = [_para_banco(c, aplicados[c]) for c in colunas]
        sets = [f"{c} = ${i}" for i, c in enumerate(colunas, start=1)]

        # A procedência do número acompanha o número, na mesma escrita.
        if "num_funcionarios" in aplicados:
            valores.append(dados.num_funcionarios_origem or ESTIMADO)
            sets.append(f"num_funcionarios_origem = ${len(valores)}")
            sets.append("num_funcionarios_em = NOW()")

        sets.append("atualizado_em = NOW()")
        valores.append(conta_id)
        await conn.execute(
            f"UPDATE contas SET {', '.join(sets)} WHERE id = ${len(valores)}",
            *valores,
        )

    await conn.execute(
        "UPDATE contas SET enriquecida_em = NOW(), enriquecida_fonte = $2 WHERE id = $1",
        conta_id, dados.fonte[:30],
    )

    return {
        "aplicados": aplicados,
        "mantidos": mantidos,
        "cnae": cnae,
        "socios": await _gravar_socios(conn, conta_id, dados, user_id),
        "secundarios": await _gravar_secundarios(conn, conta_id, dados),
    }
