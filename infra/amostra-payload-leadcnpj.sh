#!/usr/bin/env bash
#
# HIPO - mostra a RESPOSTA CRUA da LeadCNPJ que ja esta guardada.
#
# Rodar NA EC2, como ec2-user (nao precisa de -t, so le):
#   scp -i $HOME/Downloads/chave-hipo.pem \
#       infra/amostra-payload-leadcnpj.sh ec2-user@63.179.88.212:/tmp/
#   ssh -i $HOME/Downloads/chave-hipo.pem ec2-user@63.179.88.212 \
#       bash /tmp/amostra-payload-leadcnpj.sh
#
# POR QUE ISTO EXISTE
#
# A tabela `conta_enriquecimentos` guarda o payload cru de toda consulta.
# Foi feita para responder "de onde veio esse dado" seis meses depois --
# e serve tambem para isto: escrever o leitor do formato SEM gastar
# consulta paga tentando adivinhar nome de campo.
#
# O QUE ELE ESCONDE
#
# CPF, CNPJ de socio e e-mail sao mascarados antes de imprimir. O que
# interessa aqui e o NOME e o FORMATO dos campos, nunca o conteudo.
# Ainda assim: confira a saida antes de colar em qualquer lugar.

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

DB=$(printf '%s\n' "$ENV_TXT" | tr -d '\r' \
    | grep -E '^DATABASE_URL=' | head -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//')

if [ -z "$DB" ]; then
    echo "ERRO: sem DATABASE_URL no .env."
    exit 1
fi
echo "Banco: $(printf '%s' "$DB" | sed 's/:[^:@]*@/:****@/')"
echo

BRUTO=$(mktemp)
psql "$DB" -At -c "
    SELECT payload::text
      FROM conta_enriquecimentos
     WHERE fonte = 'leadcnpj' AND sucesso AND payload IS NOT NULL
     ORDER BY consultado_em DESC
     LIMIT 1
" > "$BRUTO" 2>/dev/null

if [ ! -s "$BRUTO" ]; then
    echo "Nenhuma consulta bem-sucedida da leadcnpj guardada ainda."
    echo "Aperte 'Atualizar dados publicos' numa conta e rode de novo."
    rm -f "$BRUTO"
    exit 0
fi

PY=""
for c in /home/hipo/app/.venv/bin/python python3.11 python3; do
    caminho=$(command -v "$c" 2>/dev/null || { [ -x "$c" ] && printf '%s' "$c"; })
    [ -n "$caminho" ] && { PY="$caminho"; break; }
done
[ -z "$PY" ] && { echo "ERRO: sem python3."; rm -f "$BRUTO"; exit 1; }

"$PY" - "$BRUTO" <<'PYCODE'
import json, re, sys

MASCARAR = re.compile(r"\d{11,14}")


def mascarar(texto):
    """Qualquer sequencia de 11 a 14 digitos vira ***: CPF, CNPJ, telefone
    longo. Perde-se o numero, mantem-se o formato -- que e o que interessa
    para escrever o leitor."""
    return MASCARAR.sub(lambda m: "*" * len(m.group()), texto)


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
        return mascarar(valor)
    return valor


dados = json.loads(open(sys.argv[1], encoding="utf-8").read())

print("=" * 62)
print(" CAMPOS DO PRIMEIRO NIVEL (nome -> tipo)")
print("=" * 62)
for chave in sorted(dados):
    valor = dados[chave]
    tipo = type(valor).__name__
    if isinstance(valor, dict):
        tipo = "dict{" + ", ".join(sorted(valor)[:6]) + "}"
    elif isinstance(valor, list):
        interno = type(valor[0]).__name__ if valor else "vazio"
        if valor and isinstance(valor[0], dict):
            interno = "dict{" + ", ".join(sorted(valor[0])[:6]) + "}"
        tipo = f"list[{interno}] ({len(valor)})"
    print(f"  {chave:<34} {tipo}")

print()
print("=" * 62)
print(" CANDIDATOS A QUANTIDADE DE FUNCIONARIOS")
print("=" * 62)
ALVOS = ("funcion", "employee", "colaborad", "pessoal", "headcount",
         "quadro", "porte", "vidas", "staff")
achou = False


def varrer(obj, prefixo=""):
    global achou
    if isinstance(obj, dict):
        for k, v in obj.items():
            caminho = f"{prefixo}{k}"
            if any(a in k.lower() for a in ALVOS):
                achou = True
                print(f"  {caminho} = {json.dumps(limpar(v, k), ensure_ascii=False)[:160]}")
            varrer(v, caminho + ".")
    elif isinstance(obj, list) and obj:
        varrer(obj[0], prefixo + "0.")


varrer(dados)
if not achou:
    print("  NENHUM. O plano contratado nao devolve quadro de pessoal --")
    print("  e ai nenhum ajuste de codigo faz o numero aparecer.")

print()
print("=" * 62)
print(" PAYLOAD COMPLETO (mascarado)")
print("=" * 62)
print(json.dumps(limpar(dados), indent=2, ensure_ascii=False)[:12000])
PYCODE

rm -f "$BRUTO"
