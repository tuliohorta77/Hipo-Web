#!/usr/bin/env bash
#
# HIPO - mede a ACURACIA do quadro de pessoal da Oportunidados.
#
# POR QUE ESTE SCRIPT EXISTE
#
# A licao do Econodata: cobertura nao e acuracia. Um campo que vem
# preenchido em 90% das empresas e inutil se o numero estiver errado --
# e la estava, por 13 a 38 vezes, sempre para baixo. Medir "vem
# preenchido?" aprovaria a assinatura de novo.
#
# Entao este script nao mede cobertura. Ele compara a faixa devolvida
# com a quantidade de vidas que VOCE JA SABE, empresa por empresa.
# Verdade conhecida e a unica regua possivel: nao da para medir a fonte
# contra ela mesma.
#
# COMO RODAR
#
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       infra/sondar-oportunidados.sh ec2-user@hipogestao.com.br:/tmp/
#   ssh -t -i $HOME/Downloads/chave-hipo.pem ec2-user@hipogestao.com.br \
#       bash /tmp/sondar-oportunidados.sh 05352393000116:115 34028316000103
#
# O `-t` E OBRIGATORIO: o script pede o token pelo terminal.
#
# TRES FORMAS DE PASSAR CADA ALVO
#
#   CNPJ                 so consulta e mostra o que veio
#   CNPJ:VIDAS           consulta E compara com a quantidade real
#   CNPJ+CNPJ+CNPJ:VIDAS SOMA os estabelecimentos e compara a soma
#
# A terceira existe por um motivo concreto: a fonte responde POR CNPJ,
# e a quantidade que voce conhece costuma ser a do GRUPO. Uma empresa
# de 115 vidas com matriz e duas filiais pode devolver 94 na matriz --
# e 94 nao esta errado, esta respondendo outra pergunta.
#
# O mesmo cuidado que fez a gente NUNCA usar headcountMatrizFiliais do
# Econodata (que somava o grupo quando queriamos o estabelecimento)
# vale aqui ao contrario: nao julgue o numero do estabelecimento com a
# verdade do grupo.
#
# A resposta traz `cnpj_raiz` e se e matriz ou filial -- o script mostra
# os dois, entao da para descobrir se ha irmaos a somar.
#
# NAO PRECISA DO .env, E ISSO E DE PROPOSITO
#
# O token e pedido no terminal e vive so neste processo. Nao encoste no
# /home/hipo/app/.env ainda: o `Settings` e pydantic com `extra="forbid"`,
# entao variavel que o config.py de producao nao declara ABORTA a subida
# da API e o nginx passa a devolver 502 em tudo. Foi assim que a
# producao caiu em 21/09. Credencial vai para o .env DEPOIS que o codigo
# que a declara estiver no ar.
#
# Token tambem nunca entra como argumento de linha de comando: vazaria no
# historico do shell, no `ps` de qualquer usuario da maquina enquanto
# roda, e no terminal de quem estiver olhando.

set -uo pipefail

BASE="${OPORTUNIDADOS_URL:-https://app.oportunidados.com.br}"

linha() { printf '%s\n' "----------------------------------------------------------------------"; }

if [ "$#" -eq 0 ]; then
    echo "Uso: bash $0 CNPJ[:VIDAS] [CNPJ[:VIDAS] ...]"
    echo
    echo "Exemplos:"
    echo "  bash $0 05352393000116:115"
    echo "  bash $0 05352393000116:115 34028316000103:8 11222333000181"
    echo
    echo "O :VIDAS e a quantidade que voce SABE. Sem ele o script so"
    echo "mostra o que a fonte diz, e nao da para julgar nada."
    exit 1
fi

for c in curl python3; do
    command -v "$c" >/dev/null 2>&1 || { echo "ERRO: falta '$c' nesta maquina."; exit 1; }
done

# ── o token ───────────────────────────────────────────────────────────
if ! ( exec 3< /dev/tty ) 2>/dev/null; then
    echo "ERRO: sem terminal. Rode com 'ssh -t'."
    exit 1
fi

echo "Cole o token da Oportunidados (NAO vai aparecer enquanto voce digita)."
printf '  token: '
read -rs TOKEN < /dev/tty
echo

TOKEN=$(printf '%s' "$TOKEN" | tr -d '\r\n' \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
          -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

if [ -z "$TOKEN" ]; then
    echo "ERRO: token vazio."
    exit 1
fi
echo "Token recebido: ${TOKEN:0:4}... (${#TOKEN} caracteres)"
echo "Base          : $BASE"
echo "Empresas      : $#"
echo
echo "ATENCAO: o tier gratuito e de 100 consultas/mes. Esta rodada gasta $#."
printf 'Continuar? [s/N] '
read -r RESP < /dev/tty
case "$RESP" in s|S) ;; *) echo "Nada foi consultado."; exit 0 ;; esac

# Arquivo temporario com permissao fechada: a resposta traz socios.
RESPOSTAS=$(mktemp -d)
chmod 700 "$RESPOSTAS"
trap 'rm -rf "$RESPOSTAS"' EXIT

linha
printf '%-20s %-30s %-24s %s\n' "CNPJ" "EMPRESA" "FONTE DIZ" "CONFERE?"
linha

INDICE=0
for ALVO in "$@"; do
    LISTA="${ALVO%%:*}"
    VIDAS=""
    case "$ALVO" in *:*) VIDAS=$(printf '%s' "${ALVO#*:}" | tr -cd '0-9') ;; esac

    ARQUIVOS=""
    RUIM=0
    OLD_IFS="$IFS"; IFS='+'
    for PEDACO in $LISTA; do
        IFS="$OLD_IFS"
        CNPJ=$(printf '%s' "$PEDACO" | tr -cd '0-9')
        if [ "${#CNPJ}" -ne 14 ]; then
            printf '%-20s %s\n' "$PEDACO" "IGNORADO: CNPJ precisa de 14 digitos"
            RUIM=1
            IFS='+'
            continue
        fi
        ARQ="$RESPOSTAS/$CNPJ.json"
        HTTP=$(curl -sS -o "$ARQ" -w '%{http_code}' \
            -H "Authorization: Bearer $TOKEN" \
            -H "Accept: application/json" \
            --max-time 25 \
            "$BASE/api/v1/brazilian_companies/$CNPJ/company" 2>"$RESPOSTAS/erro.txt")
        if [ -z "$HTTP" ]; then
            printf '%-20s %s\n' "$CNPJ" "FALHA DE REDE: $(head -1 "$RESPOSTAS/erro.txt")"
            RUIM=1
            IFS='+'
            continue
        fi
        ARQUIVOS="$ARQUIVOS $CNPJ:$HTTP:$ARQ"
        INDICE=$((INDICE + 1))
        IFS='+'
    done
    IFS="$OLD_IFS"

    [ -z "$ARQUIVOS" ] && continue

    VIDAS="$VIDAS" python3 - $ARQUIVOS <<'PY'
import json, os, sys, re

vidas = os.environ.get("VIDAS") or ""

DICAS = {
    "401": "token invalido ou ausente",
    "403": "conta inelegivel ou quota mensal",
    "404": "CNPJ nao esta na base",
    "429": "limite por minuto -- espere",
}

def ler(texto):
    """
    (piso, teto, exato). exato=True quando a fonte deu UM numero, nao faixa.

    O plano pago devolve contagem ("94"); o basico devolve rotulo de faixa
    ("101 a 500 funcionarios"). Os dois passam por aqui, e a diferenca muda
    como o resultado e julgado: faixa se avalia por conter ou nao conter,
    contagem se avalia por quanto desvia.
    """
    t = (texto or "").strip()
    if not t:
        return None, None, False
    baixo = t.lower()
    if "nenhum" in baixo:
        return 0, 0, True
    numeros = [int(n) for n in re.findall(r"\d+", t)]
    if not numeros:
        return None, None, False          # "Sem dados oficiais"
    if "mais de" in baixo:
        return numeros[0], float("inf"), False
    if len(numeros) >= 2:
        return numeros[0], numeros[1], False
    return numeros[0], numeros[0], True

itens = []
for bruto in sys.argv[1:]:
    cnpj, http, caminho = bruto.split(":", 2)
    if http != "200":
        try:
            corpo = json.load(open(caminho, encoding="utf-8"))
            msg = corpo.get("message") or corpo.get("error") or ""
        except Exception:
            msg = ""
        itens.append({"cnpj": cnpj, "nome": f"HTTP {http}",
                      "diz": (DICAS.get(http) or msg)[:23],
                      "piso": None, "teto": None, "exato": False,
                      "sede": "", "falhou": True})
        continue

    dados = json.load(open(caminho, encoding="utf-8"))
    emp = dados.get("company") or {}
    nome = emp.get("razao_social") or emp.get("nome_fantasia") or "(sem nome)"

    # A distincao que vale o script: chave AUSENTE e plano sem o recurso;
    # "Sem dados oficiais" e a fonte declarando que nao sabe ESTA empresa.
    if "numero_funcionarios" not in emp:
        itens.append({"cnpj": cnpj, "nome": nome, "diz": "(chave ausente)",
                      "piso": None, "teto": None, "exato": False,
                      "sede": "", "falhou": True,
                      "aviso": "PLANO SEM O RECURSO"})
        continue

    texto = (emp.get("numero_funcionarios") or "").strip() or "(vazio)"
    piso, teto, exato = ler(texto)

    mf = str(emp.get("matriz_filial") or "").lower()
    sede = "matriz" if "matriz" in mf or mf == "1" else ("filial" if mf else "")
    raiz = emp.get("cnpj_raiz") or ""

    itens.append({"cnpj": cnpj, "nome": nome, "diz": texto,
                  "piso": piso, "teto": teto, "exato": exato,
                  "sede": sede, "raiz": raiz, "falhou": False})

def linha(c, nome, diz, veredicto):
    print(f"{c:<20} {nome[:29]:<30} {diz[:23]:<24} {veredicto}")

def julgar(piso, teto, exato, v):
    if piso is None:
        return f"NAO SABE (real: {v})"
    if exato and piso == teto:
        desvio = piso - v
        pct = (desvio / v * 100) if v else 0
        if abs(pct) <= 10:
            return f"OK  {pct:+.0f}% (real: {v})"
        lado = "SUBESTIMA" if desvio < 0 else "SUPERESTIMA"
        return f"{lado} {pct:+.0f}% (real: {v})"
    if piso <= v <= teto:
        return f"OK  faixa contem (real: {v})"
    lado = "SUBESTIMA" if v > teto else "SUPERESTIMA"
    return f"{lado} -- faixa (real: {v})"

grupo = len(itens) > 1
for it in itens:
    marca = f" [{it['sede']}]" if it.get("sede") else ""
    if it["falhou"]:
        linha(it["cnpj"], it["nome"] + marca, it["diz"], it.get("aviso", "-"))
        continue
    if grupo:
        linha(it["cnpj"], it["nome"] + marca, it["diz"], "")
    else:
        v = it["cnpj"]
        raiz = it.get("raiz")
        extra = f"  raiz {raiz}" if raiz and it.get("sede") else ""
        veredicto = julgar(it["piso"], it["teto"], it["exato"], int(vidas)) if vidas \
            else "(sem verdade informada)"
        linha(v, it["nome"] + marca, it["diz"], veredicto)
        if extra:
            print(f"{'':<20} {extra}")

if grupo:
    uteis = [i for i in itens if not i["falhou"] and i["piso"] is not None]
    faltam = [i for i in itens if i["falhou"] or i["piso"] is None]
    if not uteis:
        linha("= SOMA", "", "(nada somavel)", "-")
    else:
        soma_piso = sum(i["piso"] for i in uteis)
        soma_teto = sum(i["teto"] for i in uteis)
        exato = all(i["exato"] for i in uteis)
        diz = str(soma_piso) if exato else f"{soma_piso} a {soma_teto}"
        nota = f" ({len(faltam)} sem dado)" if faltam else ""
        veredicto = julgar(soma_piso, soma_teto, exato, int(vidas)) if vidas \
            else "(sem verdade informada)"
        linha("= SOMA DE " + str(len(uteis)), "", diz + nota, veredicto)
PY
done

linha
echo
echo " COMO LER"
echo
echo "  OK                  a faixa contem a quantidade real"
echo "  ERRA -- SUBESTIMA   o pior caso: proposta sai subdimensionada e o"
echo "                      problema so aparece na execucao do servico"
echo "  NAO SABE            honesto: eles declaram que nao tem o dado"
echo "  PLANO SEM O RECURSO nao e falha de dado -- e feature de plano;"
echo "                      fale com eles antes de concluir qualquer coisa"
echo
echo " O QUE DECIDE"
echo
echo "  Conte so as que tinham verdade informada. Se a maioria der OK e"
echo "  nenhuma SUBESTIMAR feio, a fonte serve para priorizar prospeccao."
echo "  Se repetir o padrao do Econodata -- errar para baixo justo nas"
echo "  maiores --, nao serve, porque o viés e maior exatamente onde tem"
echo "  mais vidas para vender."
echo
echo " E vale sempre: quem precifica e a vida que o cliente declara."
echo " Faixa externa nunca vira proposta."
linha
