# HIPO — Hipotálamo Inteligente de Processos e Operações

Stack: **FastAPI + PostgreSQL + React + Tailwind**  
Deploy: **AWS EC2** via GitHub Actions

## Estrutura

```
hipo/
├── api/          # Backend FastAPI
├── web/          # Frontend React + Tailwind
├── infra/        # Scripts de infraestrutura
└── .github/      # CI/CD GitHub Actions
```

## Desenvolvimento local

### Backend
```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env   # preencher variáveis
uvicorn main:app --reload --port 8001
```

### Frontend
```bash
cd web
npm install
npm run dev
```

### Testes
```bash
# Backend
cd api && pytest

# Frontend
cd web && npm run test
```

## Branches

| Branch | Propósito |
|--------|-----------|
| `main` | Produção — deploy automático |
| `develop` | Integração — testes obrigatórios |
| `feature/*` | Features novas |
| `fix/*` | Correções |

## Deploy

Push para `main` → GitHub Actions executa testes → deploy automático no EC2.
