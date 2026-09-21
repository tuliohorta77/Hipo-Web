#!/usr/bin/env bash
#
# HIPO - sonda a API da LeadCNPJ DE DENTRO DA EC2.
#
# POR QUE ESTE SCRIPT EXISTE
#
# A EC2 alcanca a LeadCNPJ -- ela responde 400, e 400 e resposta de
# servidor, nao timeout (da maquina do Tulio nem conectava). 400 tambem nao
# e "caminho errado" (seria 404) nem "credencial errada" (seria 401/403):
# e "entendi o pedido e ele esta malformado". Ou seja, falta um parametro,
# ou o CNPJ vai em outro lugar (query em vez de caminho), ou o corpo do
# pedido tem outro formato.
#
# O CORPO DA RESPOSTA DIZ QUAL. Toda API que devolve 400 explica o motivo
# no corpo, e e isso que este script mostra -- o que o log da aplicacao
# trunca em 200 caracteres.
#
# CUSTO: praticamente zero. Consulta so consome credito quando responde
# 200, e o script PARA no primeiro 200 que encontrar.
#
# COMO RODAR, na EC2:
#   scp -i $HOME/Downloads/chave-hipo.pem infra/sondar-leadcnpj.sh \
#       ec2-user@63.179.88.212:/tmp/
#   ssh -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212 \
#       'bash /tmp/sondar-leadcnpj.sh'
#
# A chave e lida do .env e NUNCA aparece na saida.

set -uo pipefail

CNPJ="${1:-33000167000101}"
ENV_PATH=/home/hipo/app/.env

# Mesma cascata de leitura do aplicar-014: o .env e 600 e o dono pode ser
# root, hipo ou ec2-user.
ler_env() {
    sudo cat "$ENV_PATH" 2>/dev/null && return 0
    sudo -iu hipo cat "$ENV_PATH" 2>/dev/null && return 0
    cat "$ENV_PATH" 2>/dev/null && return 0
    return 1
}

if ! CONTEUDO=$(ler_env); then
    echo "ERRO: nao consegui ler $ENV_PATH"
    exit 1
fi

CHAVE=$(printf '%s\n' "$CONTEUDO" | grep -E '^LEADCNPJ_API_KEY=' | head -1 | cut -d= -f2-)
BASE=$(printf '%s\n' "$CONTEUDO" | grep -E '^LEADCNPJ_URL=' | head -1 | cut -d= -f2-)
BASE="${BASE:-https://leadcnpj.com.br/api}"
BASE="${BASE%/}"

if [ -z "$CHAVE" ]; then
    echo "ERRO: LEADCNPJ_API_KEY vazia no .env"
    exit 1
fi

# Mascara a chave em qualquer coisa que va para a tela.
mascarar() { sed "s#${CHAVE}#<CHAVE>#g"; }

CNPJ_MASCARA=$(echo "$CNPJ" | sed -E 's/(..)(...)(...)(....)(..)/\1.\2.\3\/\4-\5/')

echo "============================================================"
echo " HIPO - sonda da API LeadCNPJ (de dentro da EC2)"
echo " $(date '+%d/%m/%Y %H:%M:%S')"
echo " Base : $BASE"
echo " CNPJ : $CNPJ"
echo "============================================================"
echo

ACERTOU=0

# $1 metodo | $2 url | $3 rotulo do header | $4 header | $5 corpo (opcional)
tentar() {
    local metodo="$1" url="$2" rotulo="$3" header="$4" corpo="${5:-}"
    [ "$ACERTOU" = "1" ] && return 0

    local args=(-s -S --max-time 20 -X "$metodo" -H "$header"
                -H "Accept: application/json" -w '\n<<<%{http_code}>>>')
    if [ -n "$corpo" ]; then
        args+=(-H "Content-Type: application/json" -d "$corpo")
    fi

    local saida status resposta
    saida=$(curl "${args[@]}" "$url" 2>&1)
    status=$(printf '%s' "$saida" | grep -o '<<<[0-9]*>>>' | tr -d '<>')
    resposta=$(printf '%s' "$saida" | sed 's/<<<[0-9]*>>>//')

    printf '  %-3s  %-6s %s\n' "${status:-000}" "$metodo" \
        "$(printf '%s' "$url" | mascarar)"
    printf '        header: %s\n' "$rotulo"
    [ -n "$corpo" ] && printf '        corpo enviado: %s\n' "$corpo"

    # O CORPO E O QUE INTERESSA: e onde a API diz por que recusou.
    local trecho
    trecho=$(printf '%s' "$resposta" | tr -d '\r' | tr '\n' ' ' | mascarar)
    if [ ${#trecho} -gt 400 ]; then
        trecho="${trecho:0:400}..."
    fi
    [ -n "${trecho// /}" ] && printf '        resposta: %s\n' "$trecho"
    echo

    if [ "$status" = "200" ]; then
        ACERTOU=1
        echo "============================================================"
        echo " ACERTOU"
        echo "   $metodo $(printf '%s' "$url" | mascarar)"
        echo "   $rotulo"
        [ -n "$corpo" ] && echo "   corpo: $corpo"
        echo "============================================================"
        echo
        echo "JSON COMPLETO (chave mascarada):"
        printf '%s\n' "$resposta" | mascarar | head -c 4000
        echo
        echo
        echo "Campos que parecem quadro de pessoal:"
        printf '%s' "$resposta" \
            | grep -oiE '"[a-z_]*(funcion|employee|colaborad|porte|size)[a-z_]*" *: *[^,}]*' \
            | head -10 || echo "  (nenhum no primeiro nivel do texto)"
    fi
}

AUTH_BEARER="Authorization: Bearer $CHAVE"
AUTH_APIKEY="X-API-Key: $CHAVE"

echo "-- 1. CNPJ no CAMINHO (o que o HIPO faz hoje) --"
tentar GET "$BASE/empresas/$CNPJ"   "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"
tentar GET "$BASE/empresa/$CNPJ"    "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"
tentar GET "$BASE/cnpj/$CNPJ"       "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"

echo "-- 2. CNPJ na QUERY (a hipotese mais forte para um 400) --"
tentar GET "$BASE/empresas?cnpj=$CNPJ"  "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"
tentar GET "$BASE/empresa?cnpj=$CNPJ"   "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"
tentar GET "$BASE/consulta?cnpj=$CNPJ"  "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"
tentar GET "$BASE/cnpj?cnpj=$CNPJ"      "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"

echo "-- 3. CNPJ COM MASCARA (algumas APIs exigem) --"
tentar GET "$BASE/empresas/$CNPJ_MASCARA" "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"

echo "-- 4. Outro header, nos dois caminhos mais provaveis --"
tentar GET "$BASE/empresas/$CNPJ"      "X-API-Key: <CHAVE>" "$AUTH_APIKEY"
tentar GET "$BASE/empresas?cnpj=$CNPJ" "X-API-Key: <CHAVE>" "$AUTH_APIKEY"

echo "-- 5. POST com o CNPJ no corpo --"
tentar POST "$BASE/empresas" "Authorization: Bearer <CHAVE>" "$AUTH_BEARER" \
    "{\"cnpj\":\"$CNPJ\"}"
tentar POST "$BASE/consulta" "Authorization: Bearer <CHAVE>" "$AUTH_BEARER" \
    "{\"cnpj\":\"$CNPJ\"}"

echo "-- 6. A raiz da API, so para ver o que ela diz --"
tentar GET "$BASE" "Authorization: Bearer <CHAVE>" "$AUTH_BEARER"

if [ "$ACERTOU" = "0" ]; then
    echo "============================================================"
    echo " Nenhuma combinacao respondeu 200."
    echo
    echo " Leia os CORPOS acima: num 400 a API quase sempre diz o que"
    echo " faltou ('parametro cnpj obrigatorio', 'plano sem acesso a"
    echo " este recurso', 'formato invalido'). Essa frase resolve."
    echo
    echo " Se todos os corpos vierem vazios ou em HTML, e provavel que"
    echo " o /api seja o site e nao a API -- nesse caso o painel deles"
    echo " (menu API / Integracoes) mostra a URL de verdade, e basta"
    echo " ajustar LEADCNPJ_URL no .env."
    echo "============================================================"
fi
