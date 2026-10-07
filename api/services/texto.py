"""
HIPO — Normalização de texto para as listas de domínio.

As listas (verticais, origens, concorrentes, motivos de desfecho) são criadas
livremente por qualquer usuário, direto do combobox. Sem normalização, o banco
acumularia "Metalúrgica", "metalurgica" e "Metalurgica " como três entradas
distintas.

O slug é a chave de deduplicação: coluna UNIQUE no banco, e um POST cujo slug
já existe devolve o registro existente em vez de 409.

Funções puras — testáveis sem banco.
"""
from __future__ import annotations

import re
import unicodedata

_NAO_ALFANUM = re.compile(r"[^a-z0-9]+")
_ESPACOS = re.compile(r"\s+")


def slugify(texto: str | None) -> str:
    """
    Minúsculas, sem acento, sem pontuação, palavras unidas por hífen.

    >>> slugify("  Metalúrgica   Pesada ")
    'metalurgica-pesada'
    >>> slugify("Construção Civil / Obras")
    'construcao-civil-obras'
    >>> slugify("")
    ''
    """
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    slug = _NAO_ALFANUM.sub("-", sem_acento.lower())
    return slug.strip("-")


def limpar_nome(texto: str | None) -> str:
    """
    Versão de exibição: colapsa espaços repetidos e tira as pontas, mas
    preserva acentuação e caixa como o usuário digitou.

    >>> limpar_nome("  Metalúrgica   Pesada ")
    'Metalúrgica Pesada'
    """
    if not texto:
        return ""
    return _ESPACOS.sub(" ", texto).strip()


# ── E-mails num campo só ─────────────────────────────────────────────
#
# O cadastro do contato tem UM campo de e-mail, mas a vida real tem
# contato com dois endereços ("joao@empresa.com; joao.silva@gmail.com").
# Gravado como string única, isso ia inteiro para o Google como um
# convidado só e o evento inteiro voltava 400 "Invalid attendee email".
#
# Regra: o campo aceita vários endereços separados por ; , ou espaço.
# É guardado normalizado como "a@x.com; b@y.com" e quem precisa de
# destinatários (convite da agenda, Para do e-mail) usa separar_emails().

_SEPARADORES_EMAIL = re.compile(r"[;,\s]+")
_EMAIL_UNICO = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]{2,}$")


def separar_emails(texto: str | None) -> list[str]:
    """
    Lista de endereços contidos no campo, sem vazio e sem repetido
    (por minúscula), na ordem digitada. Não valida: quem lê dado antigo
    não pode quebrar por causa dele — use normalizar_emails() na escrita.

    >>> separar_emails("a@x.com; B@y.com, a@X.com")
    ['a@x.com', 'B@y.com']
    >>> separar_emails(None)
    []
    """
    vistos: set[str] = set()
    saida: list[str] = []
    for parte in _SEPARADORES_EMAIL.split(texto or ""):
        limpo = parte.strip()
        if limpo and limpo.lower() not in vistos:
            vistos.add(limpo.lower())
            saida.append(limpo)
    return saida


def email_unico_valido(endereco: str | None) -> bool:
    """
    >>> email_unico_valido("ana@x.com")
    True
    >>> email_unico_valido("ana@x.com; bia@y.com")
    False
    """
    return bool(_EMAIL_UNICO.match((endereco or "").strip()))


def normalizar_emails(texto: str | None) -> str | None:
    """
    Versão de gravação do campo: minúsculas, cada endereço validado,
    unidos por "; ". Vazio vira None. Endereço inválido levanta ValueError
    com a frase que vai para a tela.

    >>> normalizar_emails("Ana@X.com , bia@y.com")
    'ana@x.com; bia@y.com'
    >>> normalizar_emails("  ") is None
    True
    """
    enderecos = separar_emails((texto or "").lower())
    if not enderecos:
        return None
    for e in enderecos:
        if not email_unico_valido(e):
            raise ValueError(
                f"E-mail inválido: '{e}'. Para mais de um endereço, "
                "separe com ponto e vírgula."
            )
    return "; ".join(enderecos)
