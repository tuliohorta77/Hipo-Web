# HIPO — Sequência do Primeiro Commit

## 1. Criar o repositório no GitHub

```
GitHub → New Repository
Nome: hipo
Privado: Sim
NÃO inicializar com README (vamos fazer o push do local)
```

## 2. Configurar os Secrets no GitHub

```
GitHub → Settings → Secrets and variables → Actions → New repository secret
```

| Secret | Valor |
|--------|-------|
| `EC2_SSH_KEY` | Conteúdo da chave .pem do servidor HIPO |
| `EC2_HOST` | IP público do EC2 |
| `EC2_USER` | `ec2-user` |

## 3. Inicializar o repositório local e fazer o primeiro push

```bash
cd hipo/

# Inicializa o Git
git init
git branch -M main

# Configura o remote
git remote add origin git@github.com:SEU_USUARIO/hipo.git

# Primeiro commit — toda a estrutura de uma vez
git add .
git commit -m "feat: estrutura inicial HIPO v1.0

- Schema PostgreSQL (módulos POs e PEX)
- Parser de POs (Comissão, Enabler, Incentivo, Repasse)
- Parser do CROmie com auditoria de schema
- Cálculo dos 17 indicadores do Pilar Resultado do PEX
- API FastAPI (routers: auth, po, pex)
- Frontend React + Tailwind (módulos PEX e POs)
- Testes de backend (pytest) e frontend (Vitest)
- CI/CD GitHub Actions com deploy automático no EC2
- Infraestrutura: setup EC2 + Nginx + systemd"

# Push para a main
git push -u origin main
```

## 4. Fluxo de trabalho diário

```bash
# Nova feature
git checkout -b feature/nome-da-feature

# Trabalhar...
git add .
git commit -m "feat: descrição da mudança"
git push origin feature/nome-da-feature

# Abrir Pull Request no GitHub → develop
# Testes rodam automaticamente no PR
# Após aprovação → merge para develop

# Para subir para produção
git checkout main
git merge develop
git push origin main
# Deploy automático dispara
```

## 5. Convenção de commits

| Prefixo | Quando usar |
|---------|-------------|
| `feat:` | Nova funcionalidade |
| `fix:` | Correção de bug |
| `test:` | Adiciona ou corrige testes |
| `refactor:` | Refatoração sem mudança de comportamento |
| `docs:` | Documentação |
| `chore:` | Configuração, dependências, CI |

## 6. Branch protection rules (configurar no GitHub)

```
Settings → Branches → Add rule → branch: main
✅ Require status checks to pass before merging
  ✅ Backend Tests
  ✅ Frontend Tests
✅ Require branches to be up to date before merging
✅ Restrict pushes that create matching branches
```

Isso garante que **nada vai para produção sem passar nos testes**.
