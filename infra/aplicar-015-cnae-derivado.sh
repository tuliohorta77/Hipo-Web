#!/usr/bin/env bash
#
# HIPO - aplica a migration 015 (procedencia do mapeamento de CNAE) e
# classifica de uma vez os CNAEs que ja estao na base.
#
# ORDEM OBRIGATORIA, porque tem migration:
#   1. testes verdes  ->  2. ESTE SCRIPT  ->  3. push
# Invertido, o codigo novo sobe pedindo coluna que ainda nao existe.
#
# Rodar NA EC2, como ec2-user:
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       api/migrations/015_cnae_derivado.sql \
#       infra/aplicar-015-cnae-derivado.sh \
#       ec2-user@63.179.88.212:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212 \
#       bash /tmp/aplicar-015-cnae-derivado.sh
#
# O `-t` do ssh nao e detalhe: este script pergunta antes de gravar, e a
# pergunta so funciona com terminal alocado.
#
# A migration e ADITIVA e IDEMPOTENTE: nenhum DROP, nenhum DELETE, e rodar
# duas vezes nao faz nada na segunda. Por isso NAO exige export previo em
# CSV -- a regra de export vale para migration destrutiva, e esta nao e.
#
# O QUE ESTE SCRIPT FAZ, EM DUAS PARTES
#
#   Parte 1 (SQL): cria a coluna `cnaes.mapeamento_origem` e marca como
#   'humano' tudo que ja estava classificado -- porque antes da 015 a unica
#   forma de classificar era a tela, ou seja, foi gente.
#
#   Parte 2 (Python, OPCIONAL): roda scripts/semear_cnae_verticais.py, que
#   deriva a vertical dos CNAEs antigos pela secao da CNAE 2.0 e preenche
#   contas.vertical_id onde esta vazio. Sempre em simulacao primeiro; so
#   grava depois de voce ver os numeros e confirmar.
#
#   A parte 2 SO roda depois do push, porque ela importa
#   services/enriquecimento/cnae_estrutura.py, que e codigo novo. Se o push
#   ainda nao foi feito, o script avisa e para -- rode de novo depois.

set -euo pipefail

SQL="${1:-/tmp/015_cnae_derivado.sql}"

if [ ! -f "$SQL" ]; then
    echo "ERRO: nao achei $SQL"
    echo "Mande o arquivo por scp antes de rodar este script."
    exit 1
fi

ENV_PATH=/home/hipo/app/.env
APP_DIR=/home/hipo/app/api

# LER O .env NAO E TRIVIAL AQUI, e ja custou um deploy na 014.
#
# O arquivo e 600 e o dono NAO e necessariamente o usuario `hipo`. Entao
# tenta na ordem que cobre os tres estados possiveis, em vez de apostar num
# deles: root, depois o usuario do app, depois o proprio usuario da sessao.
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
# silencio logo depois de imprimir o banco.
#
# O teste e ABRIR o /dev/tty num SUBSHELL, nao `[ -r /dev/tty ]`: o arquivo
# existe em qualquer sessao, mas abrir so funciona quando ha terminal
# controlador.
tem_tty() { ( exec 3< /dev/tty ) 2>/dev/null; }

perguntar() {  # perguntar "texto" -> 0 se sim
    local texto="$1" resposta
    if [ -n "${HIPO_CONFIRMADO:-}" ]; then
        echo "  ($texto -> sim, por HIPO_CONFIRMADO=1)"
        return 0
    fi
    if ! tem_tty; then
        echo "ERRO: sem terminal para confirmar (rodando sem tty)."
        echo
        echo "Use 'ssh -t', ou rode de novo com:"
        echo "  HIPO_CONFIRMADO=1 bash $0 $SQL"
        exit 1
    fi
    read -r -p "$texto [s/N] " resposta < /dev/tty
    [ "$resposta" = "s" ] || [ "$resposta" = "S" ]
}

# ── Parte 1: a migration ──────────────────────────────────────────────

if ! perguntar "Aplicar a migration 015 nesse banco?"; then
    echo "Cancelado."
    exit 0
fi

echo
echo "== antes =="
psql "$DATABASE_URL" -At <<'EOF'
SELECT 'coluna mapeamento_origem existe: ' || count(*)
  FROM information_schema.columns
 WHERE table_name = 'cnaes' AND column_name = 'mapeamento_origem';
SELECT 'CNAEs conhecidos: ' || count(*) FROM cnaes;
SELECT 'CNAEs ja com vertical: ' || count(*)
  FROM cnaes WHERE vertical_id IS NOT NULL;
SELECT 'contas ativas sem vertical: ' || count(*)
  FROM contas WHERE ativo AND vertical_id IS NULL;
EOF

echo
echo "== aplicando =="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$SQL"

echo
echo "== depois =="
# Esperado: coluna presente, e os CNAEs que ja tinham vertical marcados
# como 'humano' (a decisao anterior a 015 era sempre de gente).
psql "$DATABASE_URL" -At <<'EOF'
SELECT 'coluna mapeamento_origem existe: ' || count(*)
  FROM information_schema.columns
 WHERE table_name = 'cnaes' AND column_name = 'mapeamento_origem';
SELECT 'marcados como humano: ' || count(*)
  FROM cnaes WHERE mapeamento_origem = 'humano';
EOF

echo
echo "============================================================"
echo " Migration 015 aplicada."
echo "============================================================"

# ── Parte 2: a carga das verticais ────────────────────────────
#
# Nao acontece aqui, de proposito: a carga precisa do codigo novo, que so
# chega no servidor depois do push. E ela tem suas proprias armadilhas
# (achar o Python certo, carregar o .env no ambiente), que moram num script
# so delas.

echo
if [ -f "$APP_DIR/services/enriquecimento/cnae_estrutura.py" ]; then
    echo " O codigo novo ja esta no servidor. Rode agora a carga:"
    echo
    echo "   bash /tmp/carregar-verticais.sh"
else
    echo " O codigo novo ainda NAO esta no servidor."
    echo
    echo " Ordem daqui pra frente:"
    echo "   1. git push (o CI faz rsync e reinicia o servico)"
    echo "   2. bash /tmp/carregar-verticais.sh"
fi
echo
echo " A carga deriva a vertical dos CNAEs antigos pela secao da CNAE 2.0"
echo " e preenche as contas que estao sem vertical. Ela simula primeiro e"
echo " so grava depois que voce confirmar."
echo
echo "============================================================"
echo " FALTA AINDA:"
echo "   * A carga (acima)."
echo "   * Logout/login na tela. O front le os modulos do"
echo "     localStorage, gravado no login -- Ctrl+Shift+R nao zera."
echo "   * Conferir as sugestoes em CRM > CNAEs. A lista chega"
echo "     preenchida; o trabalho agora e discordar onde couber."
echo "============================================================"
