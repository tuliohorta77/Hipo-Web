#!/usr/bin/env bash
#
# HIPO - confere a delegacao do Gmail (entrega 050) SEM enviar e-mail.
#
# Rodar NA EC2, como ec2-user:
#   bash /tmp/testar-delegacao-gmail.sh tulio.horta@controllermedseg.com
#
# Para cada escopo, pede um token personificando a caixa informada. Token
# que vem = o Admin Console autorizou aquele escopo para a conta de servico.
# Depois le a assinatura (gmail.settings.basic), que e uma leitura real na
# API: prova tambem que a Gmail API esta habilitada no projeto hipo-agenda.
#
# Leitura do erro:
#   unauthorized_client  -> escopo faltando na Delegacao em todo o dominio
#                           (ou ainda propagando: ate ~10 min depois de salvar)
#   invalid_grant        -> esse e-mail nao existe no Workspace
#   SERVICE_DISABLED     -> Gmail API nao habilitada no Cloud Console
#
# Codigos de saida: 0 tudo ok | 1 algo faltando.

set -uo pipefail

CAIXA="${1:-}"
if [ -z "$CAIXA" ]; then
    echo "uso: bash $0 <email@controllermedseg.com>"
    exit 1
fi
CHAVE="$(sudo grep -E '^GOOGLE_SA_ARQUIVO=' /home/hipo/app/.env | head -1 | cut -d= -f2-)"
if [ -z "$CHAVE" ]; then
    echo "ERRO: GOOGLE_SA_ARQUIVO vazio no /home/hipo/app/.env"
    exit 1
fi

CAIXA="$CAIXA" CHAVE="$CHAVE" python3 - <<'PY'
import os, sys
from google.oauth2 import service_account
from google.auth.transport.requests import Request, AuthorizedSession

caixa, chave = os.environ["CAIXA"], os.environ["CHAVE"]
escopos = {
    "envio      (gmail.send)": "https://www.googleapis.com/auth/gmail.send",
    "assinatura (gmail.settings.basic)": "https://www.googleapis.com/auth/gmail.settings.basic",
    "resposta   (gmail.metadata)": "https://www.googleapis.com/auth/gmail.metadata",
    "agenda     (calendar.events)": "https://www.googleapis.com/auth/calendar.events",
}
falhou = False
for rotulo, escopo in escopos.items():
    try:
        c = service_account.Credentials.from_service_account_file(
            chave, scopes=[escopo]).with_subject(caixa)
        c.refresh(Request())
        print(f"  OK    {rotulo}")
    except Exception as e:
        falhou = True
        print(f"  FALTA {rotulo}: {str(e)[:160]}")

try:
    c = service_account.Credentials.from_service_account_file(
        chave, scopes=[escopos["assinatura (gmail.settings.basic)"]]).with_subject(caixa)
    r = AuthorizedSession(c).get(
        "https://gmail.googleapis.com/gmail/v1/users/me/settings/sendAs", timeout=30)
    if r.status_code >= 400:
        falhou = True
        print(f"  FALTA leitura da Gmail API ({r.status_code}): {r.text[:200]}")
    else:
        itens = r.json().get("sendAs") or []
        alvo = next((s for s in itens if (s.get("sendAsEmail") or "").lower() == caixa.lower()),
                    None) or next((s for s in itens if s.get("isPrimary")), {})
        tem = bool((alvo.get("signature") or "").strip())
        print(f"  OK    Gmail API responde; assinatura de {caixa}: "
              + ("configurada" if tem else "NAO configurada (o e-mail sai sem)"))
except Exception as e:
    falhou = True
    print(f"  FALTA leitura da Gmail API: {str(e)[:200]}")

sys.exit(1 if falhou else 0)
PY
