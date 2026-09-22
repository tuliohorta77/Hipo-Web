#!/usr/bin/env bash
#
# HIPO - sonda a API da Econodata e mostra a resposta CRUA.
#
# Rodar NA EC2, como ec2-user (nao precisa de -t, so le):
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       infra/sondar-econodata.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212 \
#       bash /tmp/sondar-econodata.sh [CNPJ]
#
# POR QUE SONDAR ANTES DE LIGAR
#
# A Econodata cobra por TIPO DE INFORMACAO pedida em cada empresa. Ligar a
# fonte e sair consultando a carteira para descobrir o nome do campo
# gastaria token em cada tentativa. Uma consulta aqui mostra a resposta
# inteira, e o normalizador ja nasce certo.
#
# O QUE ELE ESCONDE
#
# CPF, CNPJ de socio e e-mail sao mascarados. O que interessa e o NOME e o
# FORMATO dos campos, nunca o conteudo.

set -uo pipefail

ENV_PATH=/home/hipo/app/.env

ler_env() {
    sudo cat "$ENV_PATH" 2>/dev/null && return 0
    sudo -iu hipo cat "$ENV_PATH" 2>/dev/null && return 0
    cat "$ENV_PATH" 2>/dev/null && return 0
    return 1
}

if ! ENV_TXT=$(ler_env); then
    echo "ERRO: nao consegui ler $ENV_PATH."
    exit 1
fi

valor_de() {
    printf '%s\n' "$ENV_TXT" | tr -d '\r' | grep -E "^$1=" | head -1 \
        | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

CHAVE=$(valor_de ECONODATA_API_KEY)
BASE=$(valor_de ECONODATA_URL)
CAMINHO=$(valor_de ECONODATA_CAMINHO)
BLOCOS=$(valor_de ECONODATA_BLOCOS)

BASE="${BASE:-https://api.econodata.com.br/v4}"
CAMINHO="${CAMINHO:-companies/search}"
BLOCOS="${BLOCOS:-estrategico}"
CNPJ="${1:-15436940000103}"

if [ -z "$CHAVE" ]; then
    echo "ERRO: ECONODATA_API_KEY vazia ou ausente no $ENV_PATH."
    echo
    echo "Para por a chave sem que ela apareca na tela nem no histerico:"
    echo "  bash /tmp/corrigir-env-leadcnpj.sh   # mesmo padrao, outra chave"
    echo "ou, direto:"
    echo "  sudo sh -c 'printf \"ECONODATA_API_KEY=%s\\n\" \"\$CHAVE\" >> $ENV_PATH'"
    exit 1
fi

echo "Chave  : ${CHAVE:0:4}... (${#CHAVE} caracteres)"
echo "POST   : ${BASE%/}/${CAMINHO#/}"
echo "Blocos : $BLOCOS"
echo "CNPJ   : $CNPJ"
echo

# Monta o JSON com python para nao depender de jq e para escapar direito.
CORPO=$(python3 - "$CNPJ" "$BLOCOS" <<'PYJSON'
import json, sys
cnpj, blocos = sys.argv[1], sys.argv[2]
print(json.dumps({
    "criterios": {"cnpj": cnpj},
    "incluir": [b.strip() for b in blocos.split(",") if b.strip()],
}, ensure_ascii=False))
PYJSON
)
echo "Corpo  : $CORPO"
echo

RESP=$(mktemp)
STATUS=$(curl -s -o "$RESP" -w '%{http_code}' --max-time 30 \
    -X POST "${BASE%/}/${CAMINHO#/}" \
    -H "Authorization: Bearer $CHAVE" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "$CORPO")

echo "HTTP $STATUS"
echo

case "$STATUS" in
    401|403) echo ">>> Credencial recusada. Confira a chave no painel." ;;
    402) echo ">>> Tokens esgotados." ;;
    404) echo ">>> Rota inexistente. O caminho mudou?" ;;
    429) echo ">>> Limite de requisicoes." ;;
    000) echo ">>> Nao conectou." ;;
esac

if grep -qi '<html' "$RESP"; then
    echo ">>> A resposta e HTML de servidor web, nao JSON da API."
    head -c 400 "$RESP"; echo
    rm -f "$RESP"
    exit 1
fi

PY=""
for c in /home/hipo/app/.venv/bin/python python3.11 python3; do
    caminho=$(command -v "$c" 2>/dev/null || { [ -x "$c" ] && printf '%s' "$c"; })
    [ -n "$caminho" ] && { PY="$caminho"; break; }
done
[ -z "$PY" ] && { echo "ERRO: sem python3."; rm -f "$RESP"; exit 1; }

"$PY" - "$RESP" <<'PYCODE'
import json, re, sys

MASCARAR = re.compile(r"\d{11,14}")


def limpar(valor, chave=""):
    baixa = chave.lower()
    if isinstance(valor, dict):
        return {k: limpar(v, k) for k, v in valor.items()}
    if isinstance(valor, list):
        return [limpar(v, chave) for v in valor]
    if isinstance(valor, str):
        if "mail" in baixa:
            return "<email oculto>"
        if any(p in baixa for p in ("cpf", "documento", "document")):
            return "<documento oculto>"
        return MASCARAR.sub(lambda m: "*" * len(m.group()), valor)
    return valor


try:
    dados = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as e:
    print("Resposta nao e JSON:", e)
    print(open(sys.argv[1], encoding="utf-8", errors="replace").read()[:600])
    raise SystemExit(1)

print("=" * 62)
print(" ONDE ESTA O QUADRO DE PESSOAL")
print("=" * 62)
ALVOS = ("funcion", "employee", "colaborad", "pessoal", "headcount",
         "quadro", "porte", "staff", "vidas")
achou = False


def varrer(obj, pre=""):
    global achou
    if isinstance(obj, dict):
        for k, v in obj.items():
            caminho = f"{pre}{k}"
            if any(a in k.lower() for a in ALVOS):
                achou = True
                print(f"  {caminho}")
                print(f"    = {json.dumps(limpar(v, k), ensure_ascii=False)[:200]}")
            varrer(v, caminho + ".")
    elif isinstance(obj, list) and obj:
        varrer(obj[0], pre + "0.")


varrer(dados)
if not achou:
    print("  NENHUM campo de quadro de pessoal na resposta.")
    print("  Se o bloco pedido foi 'estrategico', tente outro em")
    print("  ECONODATA_BLOCOS -- ou pergunte a eles em qual bloco mora.")

print()
print("=" * 62)
print(" RESPOSTA COMPLETA (mascarada)")
print("=" * 62)
print(json.dumps(limpar(dados), indent=2, ensure_ascii=False)[:10000])
PYCODE

rm -f "$RESP"
