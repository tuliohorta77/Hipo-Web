#!/usr/bin/env bash
#
# HIPO - por que a LeadCNPJ nao esta respondendo?
#
# Rodar NA EC2, como ec2-user:
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       infra/diagnosticar-leadcnpj.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212 \
#       bash /tmp/diagnosticar-leadcnpj.sh
#
# Nao precisa de -t: este script so le, nunca pergunta e nunca grava.
#
# Quando a tela diz "fonte: brasilapi" e o numero de funcionarios vem
# vazio, a fonte paga nao entrou. As causas possiveis sao quatro, e cada
# bloco abaixo elimina uma:
#
#   1. a fonte nem esta na lista do .env
#   2. a chave esta faltando ou vazia
#   3. o codigo em producao ainda e o antigo (CI nao terminou)
#   4. a LeadCNPJ esta recusando a requisicao
#
# A CHAVE NUNCA APARECE NA TELA. So o tamanho e os quatro primeiros
# caracteres, que bastam para saber se ela existe e se e a certa.

set -uo pipefail   # sem -e: um bloco que falha nao pode calar os outros

ENV_PATH=/home/hipo/app/.env
APP_DIR=/home/hipo/app/api

linha() { printf '%s\n' "======================================================"; }

ler_env() {
    sudo cat "$ENV_PATH" 2>/dev/null && return 0
    sudo -iu hipo cat "$ENV_PATH" 2>/dev/null && return 0
    cat "$ENV_PATH" 2>/dev/null && return 0
    return 1
}

if ! ENV_TXT=$(ler_env); then
    echo "ERRO: nao consegui ler $ENV_PATH."
    sudo ls -l "$ENV_PATH" 2>/dev/null
    exit 1
fi

valor_de() {
    printf '%s\n' "$ENV_TXT" | grep -E "^$1=" | head -1 | cut -d= -f2- \
        | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

linha
echo " 1. O QUE O .env DIZ"
linha

FONTES=$(valor_de ENRIQUECIMENTO_FONTES)
CHAVE=$(valor_de LEADCNPJ_API_KEY)
URL_BASE=$(valor_de LEADCNPJ_URL)
CAMINHO=$(valor_de LEADCNPJ_CAMINHO_CNPJ)

echo "ENRIQUECIMENTO_FONTES = ${FONTES:-(ausente)}"
case ",${FONTES}," in
    *,leadcnpj,*) echo "  OK: leadcnpj esta na lista." ;;
    *) echo "  >>> CAUSA ENCONTRADA: 'leadcnpj' NAO esta na lista."
       echo "      A fonte paga nem chega a ser chamada. Corrija com:"
       echo "        sudo sed -i 's/^ENRIQUECIMENTO_FONTES=.*/ENRIQUECIMENTO_FONTES=leadcnpj,brasilapi/' $ENV_PATH"
       echo "        sudo systemctl restart hipo" ;;
esac

if [ -z "${CHAVE:-}" ]; then
    echo "LEADCNPJ_API_KEY     = (ausente ou vazia)"
    echo "  >>> CAUSA ENCONTRADA: sem chave, a fonte nao entra na lista"
    echo "      de habilitadas, mesmo constando no ENRIQUECIMENTO_FONTES."
else
    echo "LEADCNPJ_API_KEY     = ${CHAVE:0:4}... (${#CHAVE} caracteres)"
fi

# Estes dois so aparecem no .env se alguem sobrescreveu o default do
# codigo. Sobrescrita com o valor antigo e exatamente o que faria o
# conserto do endpoint nao surtir efeito nenhum.
if [ -n "${URL_BASE:-}" ] || [ -n "${CAMINHO:-}" ]; then
    echo
    echo "ATENCAO: o .env esta SOBRESCREVENDO o endereco do codigo:"
    [ -n "${URL_BASE:-}" ] && echo "  LEADCNPJ_URL          = $URL_BASE"
    [ -n "${CAMINHO:-}" ]  && echo "  LEADCNPJ_CAMINHO_CNPJ = $CAMINHO"
    echo "  O correto e 'v1/empresa/{cnpj}?enriquecer=true'. Se estiver"
    echo "  diferente, comente ou apague essas linhas: o default do"
    echo "  codigo ja esta certo."
else
    echo "LEADCNPJ_URL/CAMINHO = (usando o default do codigo)"
fi

linha
echo " 2. O CODIGO EM PRODUCAO JA E O NOVO?"
linha

CFG="$APP_DIR/config.py"
if sudo grep -q 'v1/empresa/{cnpj}' "$CFG" 2>/dev/null; then
    echo "OK: config.py ja tem o caminho corrigido."
else
    echo ">>> CAUSA ENCONTRADA: o config.py em producao ainda tem o"
    echo "    caminho antigo. O rsync do CI nao chegou (ou o job falhou)."
    sudo grep -n 'LEADCNPJ_CAMINHO_CNPJ' "$CFG" 2>/dev/null | sed 's/^/    /'
fi

echo
echo "Servico:"
systemctl show hipo -p ActiveState -p SubState -p ExecMainStartTimestamp 2>/dev/null \
    | sed 's/^/  /'
echo "  (se o servico subiu ANTES do ultimo push, ele ainda esta com o"
echo "   codigo velho na memoria -- sudo systemctl restart hipo)"

linha
echo " 3. A LeadCNPJ RESPONDE?"
linha

if [ -z "${CHAVE:-}" ]; then
    echo "Sem chave, nao ha o que testar."
else
    BASE="${URL_BASE:-https://leadcnpj.com.br/api}"
    # O default NAO vai dentro de ${VAR:-...}: o `}` do proprio {cnpj}
    # fecharia a expansao antes da hora e a URL sairia deformada
    # (`.../v1/empresa/{cnpj?enriquecer=true}`). Custou um ensaio.
    MOLDE_PADRAO='v1/empresa/{cnpj}?enriquecer=true'
    MOLDE="${CAMINHO:-$MOLDE_PADRAO}"
    # CNPJ da propria carteira, real e ativo: CNPJ invalido devolve 404 e
    # confundiria o diagnostico com um problema de credencial.
    TESTE="${1:-22899545000114}"
    ALVO="${BASE%/}/$(printf '%s' "$MOLDE" | sed "s/{cnpj}/$TESTE/")"

    echo "GET ${ALVO}"
    echo "Authorization: Bearer ${CHAVE:0:4}..."
    echo
    CORPO=$(mktemp)
    STATUS=$(curl -s -o "$CORPO" -w '%{http_code}' --max-time 25 \
        -H "Authorization: Bearer $CHAVE" -H "Accept: application/json" \
        "$ALVO")
    echo "HTTP $STATUS"
    echo "--- corpo (primeiros 600 caracteres) ---"
    head -c 600 "$CORPO"; echo
    echo "----------------------------------------"
    case "$STATUS" in
        200) echo "OK: a fonte responde. Procure no corpo acima o campo de"
             echo "    quadro de pessoal -- se ele NAO estiver ai, o plano"
             echo "    contratado nao inclui esse dado, e nenhum ajuste de"
             echo "    codigo faz aparecer." ;;
        400) echo ">>> Ainda 400. O corpo acima diz o motivo -- me mande." ;;
        401|403) echo ">>> Credencial recusada: a chave do .env nao vale."
             echo "    Confira no painel da LeadCNPJ se ela foi revogada." ;;
        402) echo ">>> Creditos esgotados." ;;
        404) echo ">>> Rota ou CNPJ inexistente." ;;
        429) echo ">>> Limite de requisicoes atingido." ;;
        000) echo ">>> Nao conectou: a EC2 nao alcanca o host." ;;
    esac
    rm -f "$CORPO"
fi

linha
echo " 4. O QUE O APP REGISTROU"
linha
sudo journalctl -u hipo --since '2 hours ago' --no-pager 2>/dev/null \
    | grep -i 'leadcnpj\|enriquecimento' | tail -25 \
    || echo "(nada no journal nas ultimas 2 horas)"

linha
echo " Lembrete: o botao 'Atualizar dados publicos' ignora o cache, mas"
echo " abrir a aba NAO reconsulta. Depois de corrigir algo aqui, aperte"
echo " Atualizar na conta -- senao voce ve o resultado antigo."
linha
