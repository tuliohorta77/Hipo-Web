"""
HIPO — Enriquecimento cadastral por CNPJ.

Três camadas, e a divisão não é estética:

    modelo.py       funções puras — normalizam o JSON de qualquer fonte para
                    um formato só. Rodam no pytest local do Windows, sem
                    Postgres e sem rede.
    fontes.py       as chamadas HTTP. Nunca levantam exceção; devolvem
                    (payload, erro).
    persistencia.py cache, gravação e as regras de sobrescrita.

Quem usa isto é `routers/crm_enriquecimento.py`. Nenhum outro módulo do HIPO
precisa saber que a BrasilAPI ou a LeadCNPJ existem.

PARA LIGAR, no .env:

    ENRIQUECIMENTO_FONTES=brasilapi,econodata
    ECONODATA_API_KEY=...

Vazio = recurso desligado, e a API sobe igual — mesma regra do S3, do SES e
da chave da IA. Sem chave paga, só a BrasilAPI responde: some o nº de
funcionários estimado, continua tudo o mais.

A ORDEM IMPORTA, e a acima é a recomendada. A BrasilAPI vem primeiro
porque cobre todo o cadastro de graça, da mesma base da Receita; a fonte
paga vem depois só para completar o que faltou. Invertida, a paga venceria
em campos que não precisava ter vencido.
"""
from . import cnae_estrutura  # noqa: F401
from .fontes import (  # noqa: F401
    BRASILAPI,
    ECONODATA,
    LEADCNPJ,
    configurada,
    empresas_do_socio,
    fontes_habilitadas,
)
from .modelo import (  # noqa: F401
    DECLARADO,
    ESTIMADO,
    DadosEmpresa,
    Socio,
    codigo_cnae,
    mascarar_documento,
    mesclar,
    normalizar_brasilapi,
    normalizar_econodata,
    normalizar_leadcnpj,
    normalizar_nome,
)
from .persistencia import (  # noqa: F401
    CAMPOS_ENRIQUECIVEIS,
    aplicar,
    consultar,
    garantir_cnae,
    vertical_por_slug,
)
