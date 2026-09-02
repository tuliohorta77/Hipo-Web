"""
HIPO — Carga única das oportunidades ativas vindas do CRM Omie.

Isto NÃO é funcionalidade do produto. É um script de migração de uso único,
rodado à mão, para trazer o estoque que já existia no CRM antigo. O HIPO
continua sendo a fonte primária: nada aqui vira rota, tela ou rotina.

O QUE ELE FAZ
  1. Cria as origens que faltarem (idempotente por slug).
  2. Cria as contas que faltarem (idempotente por CNPJ).
  3. Cria os contatos que faltarem e os vincula à conta.
  4. Cria as oportunidades, todas com status 'ativa'.
  5. Marca os envolvidos (SDR e EV) e grava o evento 'criacao'.
  6. Cria as tarefas (FUP do Omie), presas à oportunidade correspondente.

IDEMPOTÊNCIA
  Cada oportunidade carrega no fim de observacoes a marca
      [importado do CRM Omie em AAAA-MM-DD — omie:<chave>]
  e cada tarefa a mesma coisa no fim de descricao
      [importado do CRM Omie em AAAA-MM-DD — tarefa:linha-<n>]
  e o script pula qualquer chave que já esteja no banco. Rodar duas vezes
  não duplica nada; rodar de novo depois de corrigir o JSON importa só o
  que faltou.

  A tarefa é procurada pela própria marca, não pela oportunidade: importar
  a oportunidade numa rodada e a tarefa na seguinte funciona.

USO
  cd api
  export DATABASE_URL=...            # confira o host antes! (linha abaixo)
  echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'

  python -m scripts.importar_crm_omie                    # dry-run (rollback)
  python -m scripts.importar_crm_omie --commit           # grava de verdade

  --arquivo CAMINHO      JSON da carga (default: scripts/dados/<nome padrão>)
  --criado-por EMAIL     autor dos registros (default: tulio.horta@...)

TUDO OU NADA
  A carga inteira roda numa transação só. Qualquer erro no meio desfaz o
  que já tinha entrado — não existe estado pela metade.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import asyncpg

DEFAULT_JSON = Path(__file__).resolve().parent / "dados" / "crm_omie_ativas_2026-09-01.json"
DEFAULT_AUTOR = "tulio.horta@controllermedseg.com"


def mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


def como_data(valor):
    """O JSON traz a data em ISO; o asyncpg exige datetime.date."""
    return date.fromisoformat(valor) if valor else None


def como_instante(valor):
    """Prazo e conclusão vêm em ISO com fuso (-03:00) — viram datetime aware."""
    return datetime.fromisoformat(valor) if valor else None


async def resolver_usuario(conn, email: str) -> str:
    uid = await conn.fetchval(
        "SELECT id FROM usuarios WHERE lower(email) = lower($1)", email
    )
    if uid is None:
        raise SystemExit(
            f"Usuário '{email}' não existe no banco. Rode `python -m scripts.seed_usuarios` antes."
        )
    return uid


async def garantir_origem(conn, slug: str, nome: str, autor) -> int:
    oid = await conn.fetchval("SELECT id FROM origens WHERE slug = $1", slug)
    if oid is not None:
        return oid
    return await conn.fetchval(
        "INSERT INTO origens (nome, slug, criado_por) VALUES ($1, $2, $3) RETURNING id",
        nome, slug, autor,
    )


async def garantir_conta(conn, c: dict, autor) -> tuple[str, bool]:
    cid = await conn.fetchval("SELECT id FROM contas WHERE cnpj = $1", c["cnpj"])
    if cid is not None:
        return cid, False
    cid = await conn.fetchval(
        """
        INSERT INTO contas (razao_social, cnpj, cidade, uf, telefone, email,
                            observacoes, criado_por)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        c["razao_social"], c["cnpj"], c["cidade"], c["uf"],
        c["telefone"], c["email"], c["observacoes"], autor,
    )
    return cid, True


async def garantir_contato(conn, ct: dict, autor) -> tuple[str, bool]:
    """
    Casa por nome + e-mail. Sem e-mail, casa só por nome — o que pode fundir
    homônimos de empresas diferentes; é o preço de não ter chave natural, e
    o volume (297 contatos) torna a revisão manual viável depois.
    """
    if ct["email"]:
        cid = await conn.fetchval(
            "SELECT id FROM contatos WHERE lower(nome) = lower($1) AND lower(email) = lower($2)",
            ct["nome"], ct["email"],
        )
    else:
        cid = await conn.fetchval(
            "SELECT id FROM contatos WHERE lower(nome) = lower($1) AND email IS NULL",
            ct["nome"],
        )
    if cid is not None:
        return cid, False
    cid = await conn.fetchval(
        """
        INSERT INTO contatos (nome, email, telefone, observacoes, criado_por)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        ct["nome"], ct["email"], ct["telefone"], ct["observacoes"], autor,
    )
    return cid, True


async def vincular(conn, conta_id, contato_id) -> None:
    """Vincula contato à conta. Vira principal só se a conta ainda não tem um."""
    ja = await conn.fetchval(
        "SELECT 1 FROM conta_contatos WHERE conta_id = $1 AND contato_id = $2",
        conta_id, contato_id,
    )
    if ja:
        return
    tem_principal = await conn.fetchval(
        "SELECT 1 FROM conta_contatos WHERE conta_id = $1 AND principal AND ativo",
        conta_id,
    )
    await conn.execute(
        "INSERT INTO conta_contatos (conta_id, contato_id, principal) VALUES ($1, $2, $3)",
        conta_id, contato_id, not tem_principal,
    )


async def importar(args) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL não definida.")

    dados = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
    contas = {c["cnpj"]: c for c in dados["contas"]}
    contatos = {c["chave"]: c for c in dados["contatos"]}

    print(f"banco   : {mascarar(url)}")
    print(f"arquivo : {args.arquivo}")
    print(f"modo    : {'COMMIT' if args.commit else 'DRY-RUN (rollback no fim)'}")
    print(f"payload : {len(contas)} contas, {len(contatos)} contatos, "
          f"{len(dados['oportunidades'])} oportunidades, "
          f"{len(dados.get('tarefas', []))} tarefas\n")

    conn = await asyncpg.connect(url)
    novas = {"contas": 0, "contatos": 0, "oportunidades": 0, "origens": 0, "tarefas": 0}
    reaproveitadas = {"contas": 0, "contatos": 0}
    puladas: list[str] = []
    puladas_tarefas: list[str] = []
    sem_envolvido = 0
    concluidas = 0

    try:
        tx = conn.transaction()
        await tx.start()

        autor = await resolver_usuario(conn, args.criado_por)

        origens: dict[str, int] = {}
        for o in dados["origens"]:
            antes = await conn.fetchval("SELECT id FROM origens WHERE slug = $1", o["slug"])
            origens[o["slug"]] = await garantir_origem(conn, o["slug"], o["nome"], autor)
            if antes is None:
                novas["origens"] += 1

        # Usuários dos envolvidos, resolvidos uma vez só.
        emails_env = {
            e for op in dados["oportunidades"]
            for e in op["envolvidos_sdr"] + op.get("envolvidos_ev", [])
        }
        env_ids = {e: await resolver_usuario(conn, e) for e in emails_env}

        ids_conta: dict[str, str] = {}
        ids_contato: dict[str, str] = {}
        ids_opp: dict[str, str] = {}

        for op in dados["oportunidades"]:
            marca = f"— {op['chave']}]"
            existe = await conn.fetchrow(
                "SELECT id, numero FROM oportunidades WHERE observacoes LIKE '%' || $1",
                marca,
            )
            if existe:
                # Guarda o id mesmo assim: a tarefa dessa oportunidade pode
                # ainda não ter entrado.
                ids_opp[op["chave"]] = existe["id"]
                puladas.append(f"{op['chave']} (já está como {existe['numero']})")
                continue

            cnpj = op["cnpj"]
            if cnpj not in ids_conta:
                cid, criada = await garantir_conta(conn, contas[cnpj], autor)
                ids_conta[cnpj] = cid
                novas["contas"] += int(criada)
                reaproveitadas["contas"] += int(not criada)
            conta_id = ids_conta[cnpj]

            contato_id = None
            chave_ct = op["contato_chave"]
            if chave_ct:
                if chave_ct not in ids_contato:
                    ctid, criado = await garantir_contato(conn, contatos[chave_ct], autor)
                    ids_contato[chave_ct] = ctid
                    novas["contatos"] += int(criado)
                    reaproveitadas["contatos"] += int(not criado)
                contato_id = ids_contato[chave_ct]
                await vincular(conn, conta_id, contato_id)

            novo_id = await conn.fetchval(
                """
                INSERT INTO oportunidades (
                    numero, conta_id, contato_id, fase, status, temperatura,
                    valor_mensalidade, previsao_fechamento, descricao,
                    observacoes, origem_id, criado_por
                ) VALUES (
                    'OPP-' || EXTRACT(YEAR FROM NOW())::int || '-'
                           || lpad(nextval('oportunidade_numero_seq')::text, 5, '0'),
                    $1, $2, $3, 'ativa', $4, $5, $6, $7, $8, $9, $10
                )
                RETURNING id
                """,
                conta_id, contato_id, op["fase"], op["temperatura"],
                Decimal(str(op["valor_mensalidade"])), como_data(op["previsao_fechamento"]),
                op["descricao"], op["observacoes"],
                origens.get(op["origem_slug"]), autor,
            )
            novas["oportunidades"] += 1
            ids_opp[op["chave"]] = novo_id

            papeis = ([(e, "SDR") for e in op["envolvidos_sdr"]]
                      + [(e, "EV") for e in op.get("envolvidos_ev", [])])
            if not papeis:
                sem_envolvido += 1
            for email, papel in papeis:
                await conn.execute(
                    """
                    INSERT INTO oportunidade_envolvidos (oportunidade_id, usuario_id, papel)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    novo_id, env_ids[email], papel,
                )

            await conn.execute(
                """
                INSERT INTO oportunidade_eventos (oportunidade_id, tipo, para, usuario_id)
                VALUES ($1, 'criacao', $2, $3)
                """,
                novo_id, op["fase"], autor,
            )

        # ── Tarefas ──────────────────────────────────────────────────
        # Vêm depois porque toda tarefa precisa da oportunidade já criada.
        emails_resp = {t["responsavel_email"] for t in dados.get("tarefas", [])}
        resp_ids = {e: await resolver_usuario(conn, e) for e in emails_resp}

        for tf in dados.get("tarefas", []):
            marca = f"— {tf['chave']}]"
            if await conn.fetchval(
                "SELECT 1 FROM tarefas WHERE descricao LIKE '%' || $1", marca
            ):
                puladas_tarefas.append(tf["chave"])
                continue

            opp_id = ids_opp.get(tf["oportunidade_chave"])
            if opp_id is None:
                # Só acontece se o JSON for editado à mão e a oportunidade
                # alvo sair da carga. Melhor parar do que criar tarefa solta.
                raise RuntimeError(
                    f"{tf['chave']}: oportunidade {tf['oportunidade_chave']} não está na carga."
                )

            await conn.execute(
                """
                INSERT INTO tarefas (oportunidade_id, tipo, titulo, descricao,
                                     responsavel_id, prazo, concluida_em,
                                     resultado, criado_por)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                opp_id, tf["tipo"], tf["titulo"], tf["descricao"],
                resp_ids[tf["responsavel_email"]], como_instante(tf["prazo"]),
                como_instante(tf["concluida_em"]), tf["resultado"], autor,
            )
            novas["tarefas"] += 1
            if tf["concluida_em"]:
                concluidas += 1

        print("origens criadas       :", novas["origens"])
        print("contas criadas        :", novas["contas"],
              f"(reaproveitadas: {reaproveitadas['contas']})")
        print("contatos criados      :", novas["contatos"],
              f"(reaproveitados: {reaproveitadas['contatos']})")
        print("oportunidades criadas :", novas["oportunidades"])
        print("  sem envolvido       :", sem_envolvido)
        print("tarefas criadas       :", novas["tarefas"],
              f"({concluidas} já concluídas, {novas['tarefas'] - concluidas} abertas)")
        print("tarefas já existiam   :", len(puladas_tarefas))
        print("já existiam (puladas) :", len(puladas))
        for p in puladas[:20]:
            print("   -", p)
        if len(puladas) > 20:
            print(f"   ... e mais {len(puladas) - 20}")

        if args.commit:
            await tx.commit()
            print("\nCOMMIT feito. Confira em https://hipogestao.com.br")
        else:
            await tx.rollback()
            print("\nDRY-RUN: nada foi gravado. Rode de novo com --commit.")
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Carga única do CRM Omie no HIPO.")
    p.add_argument("--arquivo", default=str(DEFAULT_JSON))
    p.add_argument("--criado-por", default=DEFAULT_AUTOR)
    p.add_argument("--commit", action="store_true",
                   help="grava de verdade; sem esta flag o script faz rollback")
    args = p.parse_args()
    try:
        asyncio.run(importar(args))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\nFALHOU: {exc}", file=sys.stderr)
        print("Nada foi gravado — a transação inteira foi desfeita.", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
