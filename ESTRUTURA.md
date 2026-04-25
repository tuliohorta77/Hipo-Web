# HIPO — Estrutura do Projeto

hipo/
├── infra/
│   ├── setup_ec2.sh          # Script de setup do servidor
│   └── nginx.conf            # Configuração do Nginx
├── api/
│   ├── main.py               # Entry point FastAPI
│   ├── database.py           # Conexão PostgreSQL
│   ├── config.py             # Variáveis de ambiente
│   ├── models/
│   │   ├── po.py             # Modelos de POs
│   │   └── pex.py            # Modelos de PEX/CROmie
│   ├── parsers/
│   │   ├── po_parser.py      # Parser dos 4 tipos de PO
│   │   ├── cromie_parser.py  # Parser do CROmie (4 abas)
│   │   └── bd_ativados.py    # Parser do BD Ativados
│   ├── routers/
│   │   ├── po.py             # Endpoints de POs
│   │   └── pex.py            # Endpoints de PEX
│   └── services/
│       ├── reconciliacao.py  # Lógica de reconciliação de POs
│       └── pex_calc.py       # Cálculo dos indicadores PEX
└── web/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── pages/
        │   ├── POs.jsx
        │   └── PEX.jsx
        ├── components/
        │   ├── UploadZone.jsx
        │   ├── POTable.jsx
        │   ├── PEXDashboard.jsx
        │   └── CompliancePanel.jsx
        └── hooks/
            └── useApi.js
