"""
HIPO — Anexos de tarefa: regras e acesso ao S3.

Duas metades, separadas de propósito:

  * as REGRAS (tipos aceitos, limite, nome seguro, chave do objeto, quem
    pode mexer) são funções puras — testáveis sem bucket, sem rede e sem
    credencial. Rodam no CI e no pytest local do Windows, que não tem
    Postgres nem AWS.
  * o ACESSO AO S3 fica no fim do arquivo, atrás de funções pequenas, e
    é o único pedaço que os testes precisam dublar.

O `import boto3` mora DENTRO das funções. Import de biblioteca externa no
topo de um service derruba a API inteira quando a lib falta: a cadeia
`main → routers → services` roda no import, e a suíte inteira morre no
conftest antes do primeiro teste. Foi o que aconteceu com o python-pptx na
009. Faltando a lib, só a feature de anexo cai — com mensagem dizendo o
que instalar.

Credencial: a mesma cadeia padrão do SDK que o email_ses.py usa. Em
produção quem responde é a role `hipo-ec2-ses` da instância; não há chave
no .env e não deve haver.
"""
from __future__ import annotations

import re
import unicodedata
from uuid import UUID

from config import settings

# ── Regras ───────────────────────────────────────────────────────────

# O caso de uso é print de conversa; PDF entra porque é o vizinho óbvio
# (proposta assinada, cartão CNPJ) e usa exatamente o mesmo caminho.
#
# HEIC do iPhone fica de fora de propósito. Navegador nenhum renderiza
# sem conversão, então aceitá-lo produziria um anexo que sobe, ocupa
# storage e aparece como quadrado quebrado — pior que a recusa, porque o
# usuário só descobre depois. A mensagem de erro diz o que fazer.
TIPOS_ACEITOS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}

# 10 MB, e não os 50 do MAX_UPLOAD_MB herdado dos uploads de planilha que
# saíram do produto. Print de celular tem 1–3 MB; 10 cobre foto de câmera
# boa com folga. O limite existe para o acidente (vídeo arrastado por
# engano), não para apertar o uso legítimo.
LIMITE_MB = 10
LIMITE_BYTES = LIMITE_MB * 1024 * 1024

# Teto por tarefa. Não é escassez de storage — é leitura: uma tarefa com
# 40 prints não é mais informativa que uma com 8, e a galeria vira rolagem.
MAX_POR_TAREFA = 10

# Validade da URL de leitura. Curta porque a URL assinada é um segredo
# portátil: quem a copiar abre o arquivo sem passar pelo login. Cinco
# minutos bastam para o navegador buscar a imagem e não bastam para o
# link sobreviver num grupo de WhatsApp.
URL_VALIDA_SEGUNDOS = 300


class AnexoInvalido(ValueError):
    """Recusa com mensagem pronta para o usuário final."""


def validar_tipo(tipo_mime: str | None) -> str:
    """
    Devolve a extensão canônica do tipo, ou levanta AnexoInvalido.

    A extensão vem da TABELA, nunca do nome enviado: ".png" no nome não
    prova que o conteúdo é png, e é o tipo que decide como o navegador
    vai renderizar.
    """
    tipo = (tipo_mime or "").strip().lower()
    # "image/jpeg; charset=binary" chega assim de alguns clientes.
    tipo = tipo.split(";")[0].strip()

    if tipo in TIPOS_ACEITOS:
        return TIPOS_ACEITOS[tipo]

    if tipo in ("image/heic", "image/heif"):
        raise AnexoInvalido(
            "Formato HEIC (foto de iPhone) não é exibível no navegador. "
            "No iPhone: Ajustes → Câmera → Formatos → Mais Compatível, ou "
            "compartilhe a imagem pelo WhatsApp, que já converte para JPG."
        )

    aceitos = ", ".join(sorted(e.lstrip(".").upper() for e in set(TIPOS_ACEITOS.values())))
    raise AnexoInvalido(f"Tipo de arquivo não aceito. Aceitos: {aceitos}.")


def validar_tamanho(bytes_: int) -> None:
    if bytes_ <= 0:
        raise AnexoInvalido("Arquivo vazio.")
    if bytes_ > LIMITE_BYTES:
        mb = bytes_ / (1024 * 1024)
        raise AnexoInvalido(
            f"Arquivo de {mb:.1f} MB excede o limite de {LIMITE_MB} MB."
        )


def validar_quantidade(ja_existentes: int) -> None:
    if ja_existentes >= MAX_POR_TAREFA:
        raise AnexoInvalido(
            f"A tarefa já tem {MAX_POR_TAREFA} anexos, que é o limite. "
            "Remova um antes de enviar outro."
        )


def nome_seguro(nome: str | None, extensao: str) -> str:
    """
    Nome de exibição e de download, higienizado.

    Não é o caminho no bucket — a chave do objeto é derivada de ids (ver
    `chave_do_objeto`). Mesmo assim este nome volta num header
    Content-Disposition e aparece na tela, então precisa perder barra,
    acento e caractere de controle: eles quebram o header e são o vetor
    clássico de travessia de caminho quando alguém, um dia, usar isto
    para montar um caminho.

    Vazio vira 'anexo' — arquivo colado do clipboard costuma chegar sem
    nome nenhum, e "image.png" é melhor rótulo que "".
    """
    bruto = (nome or "").strip()
    # Só o último segmento: "..\\..\\etc\\senha.png" vira "senha.png".
    bruto = re.split(r"[\\/]", bruto)[-1]
    # Tira a extensão que veio; a canônica é acrescentada no fim.
    bruto = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", bruto)

    # Acento vira letra simples; o resto que não for seguro vira "-".
    sem_acento = unicodedata.normalize("NFKD", bruto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    limpo = re.sub(r"[^A-Za-z0-9._ -]+", "-", sem_acento)
    limpo = re.sub(r"[-\s]+", "-", limpo).strip("-. ")

    if not limpo:
        limpo = "anexo"

    # 120 deixa folga para a extensão dentro dos 255 da coluna.
    return f"{limpo[:120]}{extensao}"


def chave_do_objeto(tarefa_id: UUID | str, anexo_id: UUID | str, extensao: str) -> str:
    """
    Caminho do objeto no bucket, derivado só de ids.

    Prefixo por tarefa para que um `aws s3 ls` de diagnóstico agrupe
    sozinho, e para que uma futura limpeza de órfãos consiga varrer por
    tarefa sem ler o banco inteiro.
    """
    return f"tarefas/{tarefa_id}/{anexo_id}{extensao}"


def pode_alterar(concluida_em, cancelada_em) -> bool:
    """
    Anexo entra e sai enquanto a tarefa está ABERTA. Depois de concluída
    ou cancelada, congela junto com o resto do histórico.

    A razão é a mesma que já vale para o texto: o anexo é prova do que
    aconteceu. Prova que pode ser trocada depois do fato não é prova — e
    o resultado e o motivo de cancelamento já são imutáveis por isso.
    """
    return concluida_em is None and cancelada_em is None


# ── Acesso ao S3 ─────────────────────────────────────────────────────

def problemas() -> list[str]:
    """
    O que impede o anexo de funcionar, em linguagem de quem vai resolver.

    Mesma forma do email_ses.py: a tela pergunta antes de oferecer o botão
    de anexar, em vez de deixar o usuário descobrir no meio do upload.
    """
    achados: list[str] = []
    if not settings.S3_BUCKET_ANEXOS:
        achados.append(
            "S3_BUCKET_ANEXOS não configurado no .env "
            "(e o serviço precisa ser reiniciado depois de configurar)"
        )
    try:
        import boto3  # noqa: F401
    except ImportError:
        achados.append("boto3 não instalado (pip install boto3)")
    return achados


def disponivel() -> bool:
    return not problemas()


def _cliente():
    import boto3

    return boto3.client("s3", region_name=settings.AWS_REGION)


def subir(chave: str, conteudo: bytes, tipo_mime: str) -> None:
    """
    Grava o objeto. ContentType explícito para que a URL assinada sirva a
    imagem com o tipo certo — sem ele o S3 devolve
    application/octet-stream e o navegador oferece download em vez de
    mostrar a figura na tela.
    """
    _cliente().put_object(
        Bucket=settings.S3_BUCKET_ANEXOS,
        Key=chave,
        Body=conteudo,
        ContentType=tipo_mime,
    )


def url_temporaria(chave: str, nome_download: str | None = None) -> str:
    """URL assinada de leitura, válida por URL_VALIDA_SEGUNDOS."""
    params = {"Bucket": settings.S3_BUCKET_ANEXOS, "Key": chave}
    if nome_download:
        # inline: imagem abre na aba em vez de baixar. O nome só vale
        # quando a pessoa escolhe salvar.
        params["ResponseContentDisposition"] = f'inline; filename="{nome_download}"'
    return _cliente().generate_presigned_url(
        "get_object", Params=params, ExpiresIn=URL_VALIDA_SEGUNDOS
    )


def remover(chave: str) -> None:
    """
    Apaga o objeto. O bucket tem versionamento, então isto cria um delete
    marker e a versão anterior continua recuperável por um tempo — de
    propósito: exclusão acidental de prova tem volta.
    """
    _cliente().delete_object(Bucket=settings.S3_BUCKET_ANEXOS, Key=chave)
