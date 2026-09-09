"""
HIPO — Carga única da carteira da Oraculus como suspects.

Isto NÃO é funcionalidade do produto. É migração de uso único, rodada à mão.

O QUE ELE FAZ
  1. Resolve a conta da Oraculus e a marca como finder (eh_finder).
  2. Cria a origem 'Carteira Oraculus' (idempotente por slug).
  3. Cria as contas que faltarem (idempotente por CNPJ).
  4. Cria os contatos que faltarem e os vincula à conta.
  5. Cria uma oportunidade por conta, em 'suspect', com finder_conta_id
     apontando para a Oraculus, e grava o evento 'criacao'.

POR QUE SUSPECT
  É a definição da fase no doc: empresa que entrou na base e que ninguém
  ainda tocou. Uma carteira recebida de parceiro é exatamente isso.

FINDER, E NÃO SÓ ORIGEM
  `finder_conta_id` é o que faz a tela de Parceiros contar estas empresas
  como indicações da Oraculus e medir a conversão delas depois. A origem
  existe em paralelo para dizer COMO chegaram (carteira em bloco, não
  indicação uma a uma) — as duas respondem perguntas diferentes.

TEMPERATURA 0
  `ck_opp_temperatura_ativa` exige temperatura em oportunidade ativa, e 0 é
  a única leitura honesta de quem nunca foi contatado. Qualquer outro valor
  seria afirmar interesse que ninguém verificou.

O QUE NASCE VAZIO, DE PROPÓSITO
  `valor_mensalidade` (não existe catálogo de serviços) e
  `previsao_fechamento` (não existe conversa). Preencher com zero ou com uma
  data qualquer contaminaria o funil com número inventado.

CONTA QUE JA EXISTE COM NEGOCIO EM ANDAMENTO
  A conta e reaproveitada pelo CNPJ, e o modelo permite varias oportunidades
  simultaneas na mesma conta -- entao a carga cria o suspect do mesmo jeito.
  Mas se ja houver negocio ABERTO ali, esse suspect novo aparece na fila de
  um SDR para uma empresa que um EV ja esta conduzindo: duas pessoas nossas
  ligando para o mesmo cliente, com discursos diferentes.
  O script nao decide isso sozinho -- lista essas contas no fim, com o numero
  e a fase da oportunidade que ja existe, para voce cancelar o suspect (ou
  nao cria-lo, com --pular-com-negocio) antes de soltar a fila.

ADOTAR O FINDER NA OPORTUNIDADE QUE JA EXISTE (--adotar-finder-no-suspect)
  Pular resolve a duplicata mas perde um fato verdadeiro: a Oraculus TROUXE
  aquela empresa, e a oportunidade que ja esta la nao sabe disso (a carga do
  CRM Omie nao importou finder).

  Com esta flag, em vez de criar um segundo cartao, o script grava
  finder_conta_id na oportunidade existente. So faz isso quando as tres
  condicoes valem ao mesmo tempo:

      fase = 'suspect'      -- ninguem tocou; nao ha versao concorrente da
                               historia de onde o lead veio
      status = 'ativa'      -- desfecho fechado nao se reescreve
      finder_conta_id nulo  -- nunca sobrescreve atribuicao existente

  Lead e negociacao ficam de fora de proposito: atribuir origem retroativa a
  negocio em andamento e afirmar algo que ninguem verificou, e a metrica de
  qualidade de indicacao do parceiro passaria a contar conversao que talvez
  nao tenha vindo dele.

  A marca fica no fim de observacoes, e o `finder_conta_id IS NULL` do UPDATE
  torna a segunda rodada um no-op.

CONTA BLOQUEADA GANHA A DISPUTA
  Se um CNPJ da carteira já estiver marcado como "não prospectar", a conta é
  reaproveitada mas a oportunidade NÃO é criada — a mesma regra que a API
  aplica. Hoje as duas listas não se cruzam; a guarda existe para a próxima
  versão da planilha, que pode cruzar.

OS ENVOLVIDOS SÃO DIVIDIDOS AO MEIO
  Metade das oportunidades entra no nome do Gabriel e metade no da Kethlleen,
  ambos como SDR. É o padrão do script: sem envolvido, o filtro por
  envolvimento esconderia as 946 de todo mundo que não for gestão.

  A divisão é por POSIÇÃO na carteira, não por ordem de criação:
  a empresa da linha i sempre cai no mesmo responsável, rode você a carga
  inteira de uma vez ou em cinco lotes com --limite. Um contador de criadas
  reiniciaria a cada rodada e dois lotes ímpares dariam 4 x 2 em vez de 3 x 3.

  `--responsaveis` troca a lista (qualquer quantidade, sempre em rodízio) e
  `--sem-responsavel` carrega sem ninguém, para distribuir pela tela depois.

  O PAPEL VEM DO CARGO de cada um no HIPO, não é fixo em 'SDR'. Se um dia
  entrar um EV ou EC na lista, o vínculo nasce com o papel certo — e é o
  papel que a tela de Contas usa para derivar o vendedor da conta.

IDEMPOTÊNCIA
  Cada oportunidade carrega no fim de observacoes a marca
      [carteira Oraculus AAAA-MM-DD — oraculus:<cnpj>]
  e o script pula qualquer chave já presente. Rodar duas vezes não duplica.
  Com --limite, a segunda rodada continua de onde a primeira parou.

USO
  cd api
  export DATABASE_URL=...            # confira o host antes!
  echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/'

  python -m scripts.importar_oraculus --finder-cnpj 00000000000000
  python -m scripts.importar_oraculus --finder-cnpj 00000000000000 --commit

  --finder-cnpj CNPJ     obrigatorio: a conta da Oraculus no HIPO
  --finder-razao TEXTO   cria a conta da Oraculus se ela ainda nao existir
  --finder-razao-b64 X   o mesmo, em base64 (usado pelo .ps1 -- ver abaixo)
  --limite N             importa so as N primeiras que faltam (carga em lotes)
  --pular-com-negocio    nao cria suspect em conta que ja tem negocio aberto
  --adotar-finder-no-suspect
                         marca a Oraculus como finder da oportunidade que ja
                         existe, quando ela esta em suspect/ativa e sem finder
  --responsaveis EMAILS  troca a lista padrao (Gabriel + Kethlleen)
  --sem-responsavel      carrega sem envolvido nenhum
  --arquivo CAMINHO      JSON da carga
  --criado-por EMAIL     autor dos registros

POR QUE EXISTE --finder-razao-b64
  O PowerShell 5.1 REMOVE as aspas duplas ao montar a linha de comando de um
  programa externo. Entao `--finder-razao "RAZAO COM ESPACO"` sai do Windows
  como tres palavras soltas, o ssh entrega tres argumentos ao bash e o
  argparse morre com "unrecognized arguments". Aspas simples resolveriam o
  espaco, mas nao a apostrofe -- e uma das razoes sociais reais desta
  operacao e "ORACULU'S CONTABIL LTDA".

  Base64 nao tem espaco, aspa, apostrofe nem qualquer metacaractere de shell:
  atravessa PowerShell, ssh e bash sem precisar de quoting nenhum. O .ps1
  sempre usa esta flag; `--finder-razao` continua para quem roda na mao na EC2.

TUDO OU NADA
  Uma transação só. Erro no meio desfaz a carga inteira.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import json
import os
import re
import sys
from pathlib import Path

import asyncpg

DEFAULT_JSON = Path(__file__).resolve().parent / "dados" / "oraculus_2026-09-09.json"
DEFAULT_AUTOR = "tulio.horta@controllermedseg.com"

# Os dois SDR da operação. Metade da carteira para cada um.
DEFAULT_RESPONSAVEIS = (
    "gabriel.lira@controllermedseg.com,"
    "comercial@controllermedseg.com"
)

# ck_envolvido_papel. Um cargo fora desta lista não pode ser envolvido, e
# a mensagem precisa dizer isso antes de o INSERT estourar CheckViolation.
PAPEIS_VALIDOS = {"EC", "SDR", "EV"}


def mascarar(url: str) -> str:
    return re.sub(r":[^:@/]*@", ":****@", url or "")


def so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


async def resolver_usuario(conn, email: str) -> str:
    uid = await conn.fetchval(
        "SELECT id FROM usuarios WHERE lower(email) = lower($1)", email
    )
    if uid is None:
        raise SystemExit(
            f"Usuário '{email}' não existe. Rode `python -m scripts.seed_usuarios` antes."
        )
    return uid


async def resolver_responsavel(conn, email: str) -> tuple[str, str]:
    """
    Devolve (usuario_id, papel). O papel é o CARGO da pessoa no HIPO.

    Fixar 'SDR' funcionaria hoje — os dois padrão são SDR —, mas na primeira
    troca por um EV o vínculo nasceria com papel errado, e é o papel 'EV' que
    a tela de Contas usa para derivar o vendedor da conta. Erro silencioso,
    descoberto meses depois numa coluna vazia.
    """
    row = await conn.fetchrow(
        "SELECT id, cargo FROM usuarios WHERE lower(email) = lower($1)", email
    )
    if row is None:
        raise SystemExit(
            f"Usuário '{email}' não existe. Rode `python -m scripts.seed_usuarios` antes."
        )
    if row["cargo"] not in PAPEIS_VALIDOS:
        raise SystemExit(
            f"'{email}' tem cargo '{row['cargo']}', que não pode ser envolvido "
            f"numa oportunidade (o CHECK do banco aceita {sorted(PAPEIS_VALIDOS)}). "
            f"Use --responsaveis com outra lista, ou --sem-responsavel."
        )
    return row["id"], row["cargo"]


async def garantir_origem(conn, slug: str, nome: str, autor) -> tuple[int, bool]:
    oid = await conn.fetchval("SELECT id FROM origens WHERE slug = $1", slug)
    if oid is not None:
        return oid, False
    oid = await conn.fetchval(
        "INSERT INTO origens (nome, slug, criado_por) VALUES ($1, $2, $3) RETURNING id",
        nome, slug, autor,
    )
    return oid, True


async def resolver_finder(conn, cnpj: str, razao: str | None, autor) -> str:
    row = await conn.fetchrow(
        "SELECT id, razao_social, eh_finder FROM contas WHERE cnpj = $1", cnpj
    )
    if row is None:
        if not razao:
            raise SystemExit(
                f"A conta da Oraculus (CNPJ {cnpj}) não existe no HIPO.\n"
                f"Cadastre-a pela tela de Contas, ou rode de novo passando\n"
                f"--finder-razao \"Razao Social da Oraculus\" para o script criá-la."
            )
        fid = await conn.fetchval(
            """
            INSERT INTO contas (razao_social, cnpj, eh_finder, observacoes, criado_por)
            VALUES ($1, $2, TRUE, 'Parceiro indicador. Conta criada pela carga da carteira Oraculus.', $3)
            RETURNING id
            """,
            razao, cnpj, autor,
        )
        print(f"finder  : criada '{razao}' ({cnpj})")
        return fid

    if not row["eh_finder"]:
        await conn.execute("UPDATE contas SET eh_finder = TRUE WHERE id = $1", row["id"])
        print(f"finder  : '{row['razao_social']}' marcada como parceira")
    else:
        print(f"finder  : '{row['razao_social']}'")
    return row["id"]


async def garantir_conta(conn, c: dict, marca: str, autor) -> tuple[str, bool, bool]:
    """Devolve (id, criada, bloqueada)."""
    row = await conn.fetchrow(
        "SELECT id, nao_prospectar FROM contas WHERE cnpj = $1", c["cnpj"]
    )
    if row is not None:
        return row["id"], False, row["nao_prospectar"]

    obs = " | ".join(x for x in [c["observacoes"], marca] if x)
    cid = await conn.fetchval(
        """
        INSERT INTO contas (razao_social, cnpj, cidade, uf, num_funcionarios,
                            telefone, observacoes, criado_por)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        c["razao_social"], c["cnpj"], c["cidade"], c["uf"],
        c["num_funcionarios"], c["telefone"], obs, autor,
    )
    return cid, True, False


async def garantir_contato(conn, ct: dict, autor) -> tuple[str, bool]:
    """
    Casa SÓ por e-mail, em minúsculas. Nunca por nome.

    A carga do CRM Omie casou por nome quando faltava e-mail e registrou o
    efeito: homônimos de empresas diferentes se fundem. Aqui o mesmo endereço
    aparece em até 15 empresas da carteira (é o contador, o financeiro
    compartilhado), então casar por e-mail é o que evita 15 cópias da mesma
    pessoa — e contato sem e-mail é sempre um contato novo, porque não há
    chave nenhuma para afirmar que é a mesma pessoa.
    """
    if ct["email"]:
        cid = await conn.fetchval(
            "SELECT id FROM contatos WHERE lower(email) = lower($1) ORDER BY criado_em LIMIT 1",
            ct["email"],
        )
        if cid is not None:
            return cid, False
    cid = await conn.fetchval(
        """
        INSERT INTO contatos (nome, email, telefone, criado_por)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        ct["nome"], ct["email"], ct["telefone"], autor,
    )
    return cid, True


async def vincular(conn, conta_id, contato_id) -> None:
    """Vincula. Vira principal só se a conta ainda não tem um."""
    if await conn.fetchval(
        "SELECT 1 FROM conta_contatos WHERE conta_id = $1 AND contato_id = $2",
        conta_id, contato_id,
    ):
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

    finder_cnpj = so_digitos(args.finder_cnpj)
    if len(finder_cnpj) != 14:
        raise SystemExit("--finder-cnpj precisa ter 14 dígitos.")

    dados = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
    registros = dados["registros"]
    padrao = dados["oportunidade_padrao"]
    marca_base = f"[carteira Oraculus {dados['gerado_em']}"
    marca_finder = (
        f"[finder Oraculus atribuido pela carga de {dados['gerado_em']}]"
    )

    print(f"banco   : {mascarar(url)}")
    print(f"arquivo : {args.arquivo}")
    print(f"modo    : {'COMMIT' if args.commit else 'DRY-RUN (rollback no fim)'}")
    print(f"payload : {len(registros)} contas"
          + (f" | limite desta rodada: {args.limite}" if args.limite else ""))

    conn = await asyncpg.connect(url)
    novas = {"contas": 0, "contatos": 0, "oportunidades": 0}
    reaproveitadas = {"contas": 0, "contatos": 0}
    puladas = bloqueadas = 0
    sem_contato = 0
    pulou_com_negocio = 0
    adotadas: list[str] = []
    ids_contato: dict[str, str] = {}
    por_responsavel: dict[str, int] = {}
    com_negocio: list[str] = []

    try:
        tx = conn.transaction()
        await tx.start()

        autor = await resolver_usuario(conn, args.criado_por)
        finder_id = await resolver_finder(conn, finder_cnpj, args.finder_razao, autor)
        origem_id, origem_nova = await garantir_origem(
            conn, dados["origem"]["slug"], dados["origem"]["nome"], autor
        )

        # Rodízio entre os responsáveis: com dois, metade para cada um.
        responsaveis: list[tuple[str, str]] = []
        if not args.sem_responsavel:
            emails = [e.strip() for e in args.responsaveis.split(",") if e.strip()]
            if not emails:
                raise SystemExit(
                    "--responsaveis veio vazio. Use --sem-responsavel se a "
                    "intenção é carregar sem envolvido."
                )
            responsaveis = [await resolver_responsavel(conn, e) for e in emails]
            print(f"resp.   : rodízio entre {len(emails)} — "
                  + ", ".join(f"{e} ({p})" for e, (_, p) in zip(emails, responsaveis)))
        else:
            print("resp.   : NENHUM (--sem-responsavel)")
        print()

        # `posicao` é o índice do registro no JSON, e é ele que escolhe o
        # responsável. Usar o contador de criadas faria o rodízio reiniciar a
        # cada rodada: dois lotes de 3 dariam 4 x 2 em vez de 3 x 3, e a
        # divisão pela metade só valeria numa carga de uma tacada só.
        for posicao, r in enumerate(registros):
            if args.limite and novas["oportunidades"] >= args.limite:
                break

            marca = f"{marca_base} — oraculus:{r['chave']}]"
            if await conn.fetchval(
                "SELECT 1 FROM oportunidades WHERE observacoes LIKE '%' || $1", marca
            ):
                puladas += 1
                continue

            conta_id, criada, bloqueada = await garantir_conta(
                conn, r["conta"], marca, autor
            )
            novas["contas"] += int(criada)
            reaproveitadas["contas"] += int(not criada)

            # Contatos entram mesmo em conta bloqueada: o cadastro da empresa
            # é base compartilhada e melhora com o dado. O que não entra é o
            # negócio.
            contato_principal = None
            for ct in r["contatos"]:
                chave = (ct["email"] or f"{r['chave']}::{ct['nome']}").lower()
                if chave not in ids_contato:
                    ctid, novo = await garantir_contato(conn, ct, autor)
                    ids_contato[chave] = ctid
                    novas["contatos"] += int(novo)
                    reaproveitadas["contatos"] += int(not novo)
                ctid = ids_contato[chave]
                await vincular(conn, conta_id, ctid)
                if contato_principal is None:
                    contato_principal = ctid

            if bloqueada:
                bloqueadas += 1
                continue

            # So faz sentido perguntar em conta REAPROVEITADA: a que o script
            # acabou de criar nao tem historico nenhum.
            if not criada:
                abertas = await conn.fetch(
                    """
                    SELECT numero, fase, status FROM oportunidades
                     WHERE conta_id = $1 AND status IN ('ativa', 'suspensa')
                     ORDER BY criado_em
                    """,
                    conta_id,
                )
                if abertas:
                    resumo = ", ".join(
                        f"{a['numero']} ({a['fase']}/{a['status']})" for a in abertas
                    )
                    com_negocio.append(
                        f"{r['conta']['cnpj']} {r['conta']['razao_social']} -> {resumo}"
                    )

                    if args.adotar_finder_no_suspect and conta_id != finder_id:
                        # As tres condicoes estao no proprio WHERE: fase
                        # intocada, status vivo e sem atribuicao anterior.
                        # Deixar a regra no SQL e o que faz a segunda rodada
                        # ser no-op sem precisar de marca para consultar.
                        adotou = await conn.fetch(
                            """
                            UPDATE oportunidades
                               SET finder_conta_id = $2,
                                   observacoes = COALESCE(observacoes || ' ', '') || $3,
                                   atualizado_em = NOW()
                             WHERE conta_id = $1
                               AND fase = 'suspect'
                               AND status = 'ativa'
                               AND finder_conta_id IS NULL
                         RETURNING numero
                            """,
                            conta_id, finder_id, marca_finder,
                        )
                        for a in adotou:
                            adotadas.append(
                                f"{a['numero']}  {r['conta']['razao_social']}"
                            )

                    if args.pular_com_negocio:
                        pulou_com_negocio += 1
                        continue

            if contato_principal is None:
                sem_contato += 1

            novo_id = await conn.fetchval(
                """
                INSERT INTO oportunidades (
                    numero, conta_id, contato_id, fase, status, temperatura,
                    observacoes, origem_id, finder_conta_id, criado_por
                ) VALUES (
                    'OPP-' || EXTRACT(YEAR FROM NOW())::int || '-'
                           || lpad(nextval('oportunidade_numero_seq')::text, 5, '0'),
                    $1, $2, $3, 'ativa', $4, $5, $6, $7, $8
                )
                RETURNING id
                """,
                conta_id, contato_principal, padrao["fase"], padrao["temperatura"],
                marca, origem_id,
                # ck_opp_finder_nao_e_a_conta: a Oraculus não indica a si
                # mesma. Se o CNPJ dela estiver na própria carteira, a
                # oportunidade entra sem finder em vez de estourar o CHECK.
                None if conta_id == finder_id else finder_id,
                autor,
            )
            novas["oportunidades"] += 1

            if responsaveis:
                usuario_id, papel = responsaveis[posicao % len(responsaveis)]
                por_responsavel[usuario_id] = por_responsavel.get(usuario_id, 0) + 1
                await conn.execute(
                    """
                    INSERT INTO oportunidade_envolvidos (oportunidade_id, usuario_id, papel)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    novo_id, usuario_id, papel,
                )

            await conn.execute(
                """
                INSERT INTO oportunidade_eventos (oportunidade_id, tipo, para, usuario_id)
                VALUES ($1, 'criacao', $2, $3)
                """,
                novo_id, padrao["fase"], autor,
            )

        print("origem criada         :", int(origem_nova))
        print("contas criadas        :", novas["contas"],
              f"(reaproveitadas: {reaproveitadas['contas']})")
        print("contatos criados      :", novas["contatos"],
              f"(reaproveitados: {reaproveitadas['contatos']})")
        print("oportunidades criadas :", novas["oportunidades"])
        print("  sem contato         :", sem_contato)
        print("ja existiam (puladas) :", puladas)
        print("bloqueadas p/ prosp.  :", bloqueadas)
        if args.pular_com_negocio:
            print("puladas c/ negocio    :", pulou_com_negocio)

        if adotadas:
            print(f"\nfinder da Oraculus gravado em {len(adotadas)} oportunidade(s)")
            print("que ja existiam, paradas em suspect e sem finder:")
            for x in adotadas:
                print("   -", x)

        if com_negocio:
            rotulo = "NAO receberam suspect" if args.pular_com_negocio else "GANHARAM um suspect"
            print(f"\nATENCAO: {len(com_negocio)} conta(s) da carteira ja existiam no HIPO")
            print(f"com negocio ABERTO, e {rotulo}.")
            if not args.pular_com_negocio:
                print("Um SDR pode ligar para empresa que um EV ja esta conduzindo.")
                print("Cancele o suspect pela tela, ou rode com --pular-com-negocio.")
            for x in com_negocio:
                print("   -", x)

        if por_responsavel:
            print("\ndivisao dos envolvidos:")
            nomes = {uid: await conn.fetchval(
                "SELECT nome FROM usuarios WHERE id = $1", uid) for uid in por_responsavel}
            for uid, qtd in sorted(por_responsavel.items(), key=lambda x: nomes[x[0]]):
                print(f"   {nomes[uid]:<20} {qtd}")
        elif novas["oportunidades"]:
            print("\nATENCAO: as oportunidades nasceram SEM envolvido.")
            print("Enquanto o filtro por envolvimento nao existe, todo mundo as ve.")
            print("Depois dele, so gestao — distribua pela tela antes de ligar o filtro.")

        if args.commit:
            await tx.commit()
            print("\nCOMMIT feito. Confira em https://hipogestao.com.br")
        else:
            await tx.rollback()
            print("\nDRY-RUN: nada foi gravado. Rode de novo com --commit.")
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(
        description="Carga da carteira da Oraculus como suspects no HIPO."
    )
    p.add_argument("--finder-cnpj", required=True)
    p.add_argument("--finder-razao", default=None)
    p.add_argument("--finder-razao-b64", default=None,
                   help="razao social do finder em base64 (UTF-8); "
                        "atravessa PowerShell/ssh/bash sem quoting")
    p.add_argument("--arquivo", default=str(DEFAULT_JSON))
    p.add_argument("--criado-por", default=DEFAULT_AUTOR)
    p.add_argument("--responsaveis", default=DEFAULT_RESPONSAVEIS,
                   help="e-mails separados por virgula, em rodizio "
                        f"(padrao: {DEFAULT_RESPONSAVEIS})")
    p.add_argument("--sem-responsavel", action="store_true",
                   help="carrega sem envolvido nenhum")
    p.add_argument("--limite", type=int, default=0,
                   help="importa so as N primeiras que faltam (carga em lotes)")
    p.add_argument("--pular-com-negocio", action="store_true",
                   help="nao cria suspect em conta que ja tem negocio aberto")
    p.add_argument("--adotar-finder-no-suspect", action="store_true",
                   help="grava o finder na oportunidade que ja existe, quando "
                        "ela esta em suspect/ativa e sem finder")
    p.add_argument("--commit", action="store_true",
                   help="grava de verdade; sem esta flag o script faz rollback")
    args = p.parse_args()

    if args.finder_razao_b64:
        if args.finder_razao:
            raise SystemExit(
                "Passe --finder-razao OU --finder-razao-b64, nunca os dois."
            )
        try:
            args.finder_razao = base64.b64decode(
                args.finder_razao_b64, validate=True
            ).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise SystemExit(f"--finder-razao-b64 nao e base64 valido: {exc}") from exc

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
