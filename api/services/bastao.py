"""
HIPO -- Service de Passagem de Bastão (Hunter → Farmer).

Lógica de negócio isolada do router. Pode ser reusada/testada
independente de FastAPI.
"""
from __future__ import annotations

import re
from datetime import date
from uuid import UUID

import asyncpg


# Exceções de domínio — o router converte em HTTPException
class BastaoError(Exception):
    """Base — erros de negócio do bastão."""


class CnpjJaTemBastaoAtivo(BastaoError):
    """CNPJ já está em outro bastão (PENDENTE ou APROVADO)."""


class ContadorNaoEncontrado(BastaoError):
    """CNPJ não existe na base de carteira_cnpj."""


class BastaoNaoEncontrado(BastaoError):
    """ID inexistente ou já removido."""


class TransicaoInvalida(BastaoError):
    """Tentativa de mudar status incompatível (ex: aprovar algo já aprovado)."""


# ── Helpers ───────────────────────────────────────────────────

def _normalizar_cnpj(cnpj: str) -> str:
    """
    Retorna o CNPJ com a máscara padrão usada no banco (XX.XXX.XXX/XXXX-XX).

    A base armazena 100% dos CNPJs com máscara (verificado em produção).
    Se vier sem máscara, formata. Se já estiver com máscara, devolve igual.
    """
    if not cnpj:
        return ""
    so_digitos = re.sub(r"\D", "", cnpj)
    if len(so_digitos) != 14:
        # Devolve o que veio — quem chamou trata.
        return cnpj.strip()
    return f"{so_digitos[0:2]}.{so_digitos[2:5]}.{so_digitos[5:8]}/{so_digitos[8:12]}-{so_digitos[12:14]}"


async def _contador_existe(conn, cnpj: str) -> dict | None:
    """Confere se o CNPJ existe em carteira_cnpj. Retorna 1 linha resumida ou None."""
    row = await conn.fetchrow(
        """
        SELECT cnpj_contador, contabilidade, cidade_uf, colaborador_nome
        FROM carteira_cnpj
        WHERE cnpj_contador = $1
        LIMIT 1
        """,
        cnpj,
    )
    return dict(row) if row else None


# ── Operações ─────────────────────────────────────────────────

async def buscar_contador_por_cnpj(conn, cnpj: str) -> dict:
    """
    Lookup pro Hunter no modal — antes de criar o bastão, ele busca
    o CNPJ pra ver se existe e confirmar com quem está hoje.

    Returns: { cnpj, contabilidade, cidade_uf, colaborador_atual }
    Raises: ContadorNaoEncontrado
    """
    cnpj_norm = _normalizar_cnpj(cnpj)
    contador = await _contador_existe(conn, cnpj_norm)
    if not contador:
        raise ContadorNaoEncontrado(f"CNPJ '{cnpj}' não encontrado na carteira.")
    return {
        "cnpj_contador":      contador["cnpj_contador"],
        "contabilidade":      contador["contabilidade"],
        "cidade_uf":          contador["cidade_uf"],
        "colaborador_atual":  contador["colaborador_nome"],
    }


async def criar_bastao(
    conn,
    *,
    hunter_nome: str,
    farmer_nome: str,
    cnpj_contador: str,
    data_parceria: date,
    leads_iniciais: int,
    criado_por: UUID,
    observacoes: str | None = None,
) -> dict:
    """
    Hunter cria um novo registro de passagem de bastão.
    Status inicial = PENDENTE (precisa ADM aprovar).

    Raises:
        ContadorNaoEncontrado: CNPJ não existe em carteira_cnpj
        CnpjJaTemBastaoAtivo: outro bastão PENDENTE/APROVADO no mesmo CNPJ
    """
    cnpj_norm = _normalizar_cnpj(cnpj_contador)

    # 1) Contador precisa existir na base
    if not await _contador_existe(conn, cnpj_norm):
        raise ContadorNaoEncontrado(f"CNPJ '{cnpj_contador}' não encontrado na carteira.")

    # 2) Pode dar conflito de unicidade (índice parcial). Tratamos antes do INSERT.
    ja_ativo = await conn.fetchrow(
        """
        SELECT id, hunter_nome, status
        FROM carteira_bastao
        WHERE cnpj_contador = $1 AND status IN ('PENDENTE', 'APROVADO')
        """,
        cnpj_norm,
    )
    if ja_ativo:
        raise CnpjJaTemBastaoAtivo(
            f"CNPJ já possui bastão {ja_ativo['status'].lower()} "
            f"com o Hunter '{ja_ativo['hunter_nome']}'."
        )

    # 3) Insert
    row = await conn.fetchrow(
        """
        INSERT INTO carteira_bastao (
            hunter_nome, farmer_nome, cnpj_contador,
            data_parceria, leads_iniciais, observacoes,
            criado_por
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        hunter_nome, farmer_nome, cnpj_norm,
        data_parceria, leads_iniciais, observacoes,
        criado_por,
    )
    return dict(row)


async def listar_bastoes_do_hunter(conn, hunter_nome: str) -> list[dict]:
    """
    Lista todos os bastões deste hunter — pendentes, aprovados, rejeitados
    e removidos. Frontend filtra/agrupa pelo status.

    Inclui dados do contador (contabilidade, cidade) pra evitar 2ª chamada.
    """
    rows = await conn.fetch(
        """
        SELECT
            b.*,
            c.contabilidade,
            c.cidade_uf,
            c.colaborador_nome AS colaborador_atual
        FROM carteira_bastao b
        LEFT JOIN LATERAL (
            SELECT contabilidade, cidade_uf, colaborador_nome
            FROM carteira_cnpj
            WHERE cnpj_contador = b.cnpj_contador
            LIMIT 1
        ) c ON TRUE
        WHERE b.hunter_nome = $1
        ORDER BY
            CASE b.status
                WHEN 'PENDENTE'  THEN 0
                WHEN 'APROVADO'  THEN 1
                WHEN 'REJEITADO' THEN 2
                WHEN 'REMOVIDO'  THEN 3
            END,
            b.criado_em DESC
        """,
        hunter_nome,
    )
    return [dict(r) for r in rows]


async def listar_bastoes_pendentes(conn) -> list[dict]:
    """Fila de aprovação do ADM. Apenas status=PENDENTE."""
    rows = await conn.fetch(
        """
        SELECT
            b.*,
            c.contabilidade,
            c.cidade_uf,
            u.nome AS criado_por_nome,
            u.email AS criado_por_email
        FROM carteira_bastao b
        LEFT JOIN LATERAL (
            SELECT contabilidade, cidade_uf
            FROM carteira_cnpj
            WHERE cnpj_contador = b.cnpj_contador
            LIMIT 1
        ) c ON TRUE
        LEFT JOIN usuarios u ON u.id = b.criado_por
        WHERE b.status = 'PENDENTE'
        ORDER BY b.criado_em ASC
        """,
    )
    return [dict(r) for r in rows]


async def aprovar_bastao(conn, bastao_id: UUID, validado_por: UUID) -> dict:
    """
    ADM aprova. Só transita PENDENTE → APROVADO.
    """
    atual = await conn.fetchrow(
        "SELECT status FROM carteira_bastao WHERE id = $1",
        bastao_id,
    )
    if not atual:
        raise BastaoNaoEncontrado(f"Bastão {bastao_id} não encontrado.")
    if atual["status"] != "PENDENTE":
        raise TransicaoInvalida(
            f"Não é possível aprovar bastão com status '{atual['status']}'."
        )

    row = await conn.fetchrow(
        """
        UPDATE carteira_bastao
        SET status = 'APROVADO',
            validado_por = $2,
            validado_em = NOW()
        WHERE id = $1
        RETURNING *
        """,
        bastao_id, validado_por,
    )
    return dict(row)


async def rejeitar_bastao(
    conn,
    bastao_id: UUID,
    validado_por: UUID,
    motivo: str,
) -> dict:
    """ADM rejeita com motivo obrigatório. Só transita PENDENTE → REJEITADO."""
    if not motivo or not motivo.strip():
        raise TransicaoInvalida("Motivo da rejeição é obrigatório.")

    atual = await conn.fetchrow(
        "SELECT status FROM carteira_bastao WHERE id = $1",
        bastao_id,
    )
    if not atual:
        raise BastaoNaoEncontrado(f"Bastão {bastao_id} não encontrado.")
    if atual["status"] != "PENDENTE":
        raise TransicaoInvalida(
            f"Não é possível rejeitar bastão com status '{atual['status']}'."
        )

    row = await conn.fetchrow(
        """
        UPDATE carteira_bastao
        SET status = 'REJEITADO',
            validado_por = $2,
            validado_em = NOW(),
            motivo_rejeicao = $3
        WHERE id = $1
        RETURNING *
        """,
        bastao_id, validado_por, motivo.strip(),
    )
    return dict(row)


async def remover_bastao(conn, bastao_id: UUID, hunter_nome: str) -> dict:
    """
    Hunter remove o próprio bastão (soft delete).
    Só pode remover seus próprios bastões. Permite transitar a partir de
    qualquer status ativo (PENDENTE ou APROVADO) → REMOVIDO.
    """
    atual = await conn.fetchrow(
        "SELECT status, hunter_nome FROM carteira_bastao WHERE id = $1",
        bastao_id,
    )
    if not atual:
        raise BastaoNaoEncontrado(f"Bastão {bastao_id} não encontrado.")
    if atual["hunter_nome"] != hunter_nome:
        raise TransicaoInvalida("Você só pode remover seus próprios bastões.")
    if atual["status"] not in ("PENDENTE", "APROVADO"):
        raise TransicaoInvalida(
            f"Não é possível remover bastão com status '{atual['status']}'."
        )

    row = await conn.fetchrow(
        """
        UPDATE carteira_bastao
        SET status = 'REMOVIDO',
            removido_em = NOW()
        WHERE id = $1
        RETURNING *
        """,
        bastao_id,
    )
    return dict(row)


async def kpis_do_hunter(conn, hunter_nome: str) -> dict:
    """
    Resumo agregado pro topo da sub-aba Relacionamento:
      - total_passados: bastões APROVADOS deste hunter
      - pendentes: PENDENTES (aguardando ADM)
      - rejeitados: REJEITADOS
      - leads_iniciais_soma: soma dos leads_iniciais dos APROVADOS
    """
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE status = 'APROVADO')   AS total_passados,
            COUNT(*) FILTER (WHERE status = 'PENDENTE')   AS pendentes,
            COUNT(*) FILTER (WHERE status = 'REJEITADO')  AS rejeitados,
            COALESCE(SUM(leads_iniciais) FILTER (WHERE status = 'APROVADO'), 0)
                                                          AS leads_iniciais_soma
        FROM carteira_bastao
        WHERE hunter_nome = $1
        """,
        hunter_nome,
    )
    return {
        "total_passados":      int(row["total_passados"] or 0),
        "pendentes":           int(row["pendentes"] or 0),
        "rejeitados":          int(row["rejeitados"] or 0),
        "leads_iniciais_soma": int(row["leads_iniciais_soma"] or 0),
    }
