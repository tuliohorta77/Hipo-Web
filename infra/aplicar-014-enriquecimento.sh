#!/usr/bin/env bash
#
# HIPO - aplica a migration 014 (enriquecimento cadastral) em producao.
#
# ORDEM OBRIGATORIA, porque tem migration:
#   1. testes verdes  ->  2. ESTE SCRIPT  ->  3. push
# Invertido, o codigo novo sobe pedindo coluna que ainda nao existe.
#
# Rodar NA EC2, como ec2-user:
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       api/migrations/014_enriquecimento.sql \
#       infra/aplicar-014-enriquecimento.sh \
#       ec2-user@63.179.88.212:/tmp/
#   ssh -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212
#   bash /tmp/aplicar-014-enriquecimento.sh
#
# A migration e ADITIVA e IDEMPOTENTE: nenhum DROP, nenhum DELETE, e rodar
# duas vezes nao faz nada na segunda. Por isso NAO exige export previo em
# CSV -- a regra de export vale para migration destrutiva, e esta nao e.

set -euo pipefail

SQL="${1:-/tmp/014_enriquecimento.sql}"

if [ ! -f "$SQL" ]; then
    echo "ERRO: nao achei $SQL"
    echo "Mande o arquivo por scp antes de rodar este script."
    exit 1
fi

ENV_PATH=/home/hipo/app/.env

# LER O .env NAO E TRIVIAL AQUI, e ja custou um deploy.
#
# O arquivo e 600 e o dono NAO e necessariamente o usuario `hipo`: em
# producao ele e de root (foi assim que o ensaio do fechamento diario de
# 31/08 quebrou, e foi assim que a 014 parou na primeira tentativa, com
# "Permission denied" mesmo passando por `sudo -iu hipo`).
#
# Entao tenta na ordem que cobre os tres estados possiveis, em vez de
# apostar num deles: root, depois o usuario do app, depois o proprio
# usuario da sessao.
ler_env() {
    sudo cat "$ENV_PATH" 2>/dev/null && return 0
    sudo -iu hipo cat "$ENV_PATH" 2>/dev/null && return 0
    cat "$ENV_PATH" 2>/dev/null && return 0
    return 1
}

if ! CONTEUDO_ENV=$(ler_env); then
    echo "ERRO: nao consegui ler $ENV_PATH de jeito nenhum."
    echo
    echo "Quem e o dono e qual o modo:"
    sudo ls -l "$ENV_PATH" 2>/dev/null || ls -l "$ENV_PATH" 2>/dev/null \
        || echo "  (nem o ls funcionou -- o arquivo existe?)"
    echo
    echo "Voce esta como: $(whoami)"
    exit 1
fi

DATABASE_URL=$(printf '%s\n' "$CONTEUDO_ENV" \
    | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2-)

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERRO: o $ENV_PATH foi lido, mas nao tem linha DATABASE_URL=."
    exit 1
fi

# Mascara a senha ANTES de qualquer coisa ir para a tela. Confira o host: e
# a unica barreira contra rodar no banco errado -- o psql nao tem safeguard
# como o conftest tem.
echo "Banco: $(echo "$DATABASE_URL" | sed 's/:[^:@]*@/:****@/')"
echo

# LER A CONFIRMACAO DO TERMINAL, E NAO DO STDIN.
#
# Quando este script chega pela rede como `base64 -d | bash`, o stdin do
# bash E O PROPRIO SCRIPT -- e ele ja acabou quando a execucao chega aqui.
# Um `read` comum devolve falha na hora, e com `set -e` o script morre em
# silencio logo depois de imprimir o banco. Foi o que aconteceu na segunda
# tentativa da 014.
#
# /dev/tty e o terminal de verdade (o `ssh -t` aloca um), independente de
# para onde o stdin esteja apontando.
# O teste e ABRIR o /dev/tty, nao `[ -r /dev/tty ]`: o arquivo existe em
# qualquer sessao, mas abrir so funciona quando ha terminal controlador. Num
# ssh sem `-t` o teste de leitura passa e a abertura estoura com
# "No such device or address".
if [ -n "${HIPO_CONFIRMADO:-}" ]; then
    echo "Confirmado por HIPO_CONFIRMADO=1 (sem pergunta)."
elif ( exec 3< /dev/tty ) 2>/dev/null; then
    # O teste roda num SUBSHELL para que a mensagem do bash quando nao ha
    # terminal ("No such device or address") morra no 2>/dev/null. Com
    # `exec` direto, o redirecionamento falha antes de o 2>/dev/null valer
    # e o usuario ve um erro cru antes da explicacao.
    read -r -p "Aplicar a migration 014 nesse banco? [s/N] " resposta < /dev/tty
    if [ "$resposta" != "s" ] && [ "$resposta" != "S" ]; then
        echo "Cancelado."
        exit 0
    fi
else
    echo "ERRO: sem terminal para confirmar (rodando sem tty)."
    echo
    echo "Confira o host acima e, se for o banco certo, rode de novo com:"
    echo "  HIPO_CONFIRMADO=1 bash $0 $SQL"
    exit 1
fi

echo
echo "== antes =="
psql "$DATABASE_URL" -At <<'EOF'
SELECT 'tabelas novas presentes: ' || count(*)
  FROM information_schema.tables
 WHERE table_name IN ('cnaes','conta_socios','conta_enriquecimentos',
                      'conta_cnaes_secundarios');
SELECT 'colunas novas em contas: ' || count(*)
  FROM information_schema.columns
 WHERE table_name = 'contas'
   AND column_name IN ('cnae_codigo','porte','situacao_cadastral',
                       'data_abertura','capital_social',
                       'num_funcionarios_origem','num_funcionarios_em',
                       'enriquecida_em','enriquecida_fonte');
EOF

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$SQL"

echo
echo "== depois =="
# Esperado: 4 tabelas e 9 colunas.
psql "$DATABASE_URL" -At <<'EOF'
SELECT 'tabelas novas presentes: ' || count(*)
  FROM information_schema.tables
 WHERE table_name IN ('cnaes','conta_socios','conta_enriquecimentos',
                      'conta_cnaes_secundarios');
SELECT 'colunas novas em contas: ' || count(*)
  FROM information_schema.columns
 WHERE table_name = 'contas'
   AND column_name IN ('cnae_codigo','porte','situacao_cadastral',
                       'data_abertura','capital_social',
                       'num_funcionarios_origem','num_funcionarios_em',
                       'enriquecida_em','enriquecida_fonte');
SELECT 'contas: ' || count(*) FROM contas;
EOF

echo
echo "============================================================"
echo " Migration 014 aplicada. Esperado acima: 4 tabelas, 9 colunas."
echo
echo " FALTA AINDA, e nesta ordem:"
echo "   1. Acrescentar ao /home/hipo/app/.env:"
echo "        ENRIQUECIMENTO_FONTES=leadcnpj,brasilapi"
echo "        ENRIQUECIMENTO_TTL_DIAS=90"
echo "        LEADCNPJ_API_KEY=<a chave>"
echo "      (sem a chave, so a BrasilAPI responde -- tudo funciona,"
echo "       menos o numero de funcionarios)"
echo "   2. git push: o CI faz rsync e reinicia o servico."
echo "   3. Logout/login na tela. O front le os modulos do"
echo "      localStorage, gravado no login -- Ctrl+Shift+R nao zera."
echo "============================================================"
