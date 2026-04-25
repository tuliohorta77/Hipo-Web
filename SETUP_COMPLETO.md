# HIPO — Passo a Passo Completo
## GitHub + EC2 + Primeiro Deploy

---

## PARTE 1 — CONTA E REPOSITÓRIO NO GITHUB

### 1.1 Criar conta no GitHub (se ainda não tiver)

1. Acesse **github.com**
2. Clique em **Sign up**
3. Preencha: email, senha, username
4. Confirme o email recebido
5. Escolha o plano **Free**

---

### 1.2 Criar o repositório

1. Depois de fazer login, clique no **+** no canto superior direito
2. Clique em **New repository**
3. Preencha:
   - **Repository name:** `hipo`
   - **Visibility:** ● Private
   - **NÃO marque** nenhuma das opções de inicialização (sem README, sem .gitignore)
4. Clique em **Create repository**
5. **Guarde a URL** que aparecer — será algo como:
   `https://github.com/SEU_USUARIO/hipo.git`

---

### 1.3 Configurar chave SSH para o GitHub (recomendado)

No seu computador, abra o terminal:

```bash
# Gerar chave SSH (pressione Enter em todas as perguntas)
ssh-keygen -t ed25519 -C "seu@email.com"

# Exibir a chave pública
cat ~/.ssh/id_ed25519.pub
```

Copie o resultado e:
1. No GitHub → clique na sua foto → **Settings**
2. Menu lateral → **SSH and GPG keys**
3. Clique em **New SSH key**
4. **Title:** `Meu computador`
5. Cole a chave no campo **Key**
6. Clique em **Add SSH key**

---

### 1.4 Instalar Git no seu computador

**Mac:**
```bash
# Se não tiver o Homebrew instalado:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install git
```

**Windows:**
1. Acesse **git-scm.com/download/win**
2. Baixe e instale o Git for Windows
3. Use o **Git Bash** para rodar os comandos

**Linux:**
```bash
sudo apt install git    # Ubuntu/Debian
sudo dnf install git    # Amazon Linux / Fedora
```

---

### 1.5 Configurar o Git com suas informações

```bash
git config --global user.name "Seu Nome"
git config --global user.email "seu@email.com"
```

---

### 1.6 Extrair e subir o projeto para o GitHub

```bash
# Descompactar o arquivo hipo_projeto.zip
# Mac/Linux:
unzip hipo_projeto.zip
cd hipo/

# Windows (Git Bash):
unzip hipo_projeto.zip
cd hipo/

# Inicializar o Git no projeto
git init
git branch -M main

# Conectar ao repositório que você criou
git remote add origin git@github.com:SEU_USUARIO/hipo.git

# Primeiro commit com todo o projeto
git add .
git commit -m "feat: estrutura inicial HIPO v1.0 - módulos POs e PEX"

# Subir para o GitHub
git push -u origin main
```

Acesse o GitHub e confirme que todos os arquivos apareceram no repositório.

---

## PARTE 2 — SERVIDOR EC2 NA AWS

### 2.1 Acessar o Console AWS

1. Acesse **console.aws.amazon.com**
2. Faça login com a conta que já usa para o Knotty
3. No menu superior, confirme que a **região** está como **us-east-1** (N. Virginia) ou a mesma que você usa no Knotty

---

### 2.2 Criar o par de chaves (chave SSH para o servidor)

1. No menu de serviços, busque por **EC2**
2. No menu lateral → **Network & Security** → **Key Pairs**
3. Clique em **Create key pair**
4. Preencha:
   - **Name:** `chave-hipo`
   - **Key pair type:** RSA
   - **Private key file format:** .pem
5. Clique em **Create key pair**
6. O arquivo `chave-hipo.pem` será baixado automaticamente
7. **Guarde esse arquivo em local seguro** — não é possível baixar novamente

```bash
# Proteger a chave (Mac/Linux obrigatório)
chmod 400 ~/Downloads/chave-hipo.pem
```

---

### 2.3 Criar o Security Group

1. No menu lateral EC2 → **Network & Security** → **Security Groups**
2. Clique em **Create security group**
3. Preencha:
   - **Security group name:** `hipo-sg`
   - **Description:** `Security group do HIPO`
   - **VPC:** selecione a mesma VPC do Knotty
4. Em **Inbound rules** → **Add rule** (adicione as 3 regras abaixo):

| Type | Protocol | Port | Source |
|------|----------|------|--------|
| SSH | TCP | 22 | My IP |
| HTTP | TCP | 80 | Anywhere (0.0.0.0/0) |
| HTTPS | TCP | 443 | Anywhere (0.0.0.0/0) |

5. Clique em **Create security group**

---

### 2.4 Lançar a instância EC2

1. No menu lateral EC2 → **Instances** → **Launch instances**
2. Preencha:
   - **Name:** `hipo-server`
   - **AMI:** Amazon Linux 2023 AMI *(busque por "Amazon Linux 2023")*
   - **Instance type:** `t3.medium` *(2 vCPU, 4GB — suporta 30 usuários + IAs)*
   - **Key pair:** selecione `chave-hipo`
3. Em **Network settings** → **Edit**:
   - **VPC:** mesma do Knotty
   - **Auto-assign public IP:** Enable
   - **Firewall:** selecione `hipo-sg`
4. Em **Configure storage:**
   - **30 GiB** → tipo `gp3`
5. Clique em **Launch instance**
6. Aguarde 2-3 minutos e **anote o IP público** que aparecer

---

### 2.5 Criar o banco de dados no RDS

1. No menu de serviços, busque por **RDS**
2. Clique em **Create database**
3. Preencha:
   - **Engine:** PostgreSQL
   - **Version:** PostgreSQL 15.x
   - **Template:** Free tier (ou Production se quiser mais recursos)
   - **DB instance identifier:** `hipo-db`
   - **Master username:** `hipo_user`
   - **Master password:** crie uma senha forte e anote
   - **DB instance class:** `db.t3.micro`
   - **Storage:** 20 GiB, gp2
4. Em **Connectivity:**
   - **VPC:** mesma do EC2
   - **Public access:** No
   - **VPC security group:** crie um novo chamado `hipo-rds-sg`
5. Clique em **Create database**
6. Aguarde 5-10 minutos
7. **Anote o Endpoint** que aparecer (ex: `hipo-db.xxxxx.us-east-1.rds.amazonaws.com`)

**Liberar acesso do EC2 ao RDS:**
1. Vá em **Security Groups** → selecione `hipo-rds-sg`
2. **Inbound rules** → **Edit** → **Add rule:**
   - Type: PostgreSQL | Port: 5432 | Source: selecione `hipo-sg`
3. Salvar

---

### 2.6 Conectar ao servidor e fazer o setup

```bash
# Conectar ao servidor
ssh -i ~/Downloads/chave-hipo.pem ec2-user@IP_DO_SERVIDOR

# Baixar e executar o script de setup
curl -O https://raw.githubusercontent.com/SEU_USUARIO/hipo/main/infra/setup_ec2.sh
sudo bash setup_ec2.sh
```

O script instala automaticamente: Python 3.11, Nginx, PostgreSQL client, dependências Python e configura o systemd.

---

### 2.7 Configurar o ambiente no servidor

```bash
# Criar o arquivo de variáveis de ambiente
sudo nano /home/hipo/app/.env
```

Cole e preencha:
```
DATABASE_URL=postgresql://hipo_user:SUA_SENHA@SEU_ENDPOINT_RDS:5432/hipo
JWT_SECRET=gere-uma-string-aleatoria-longa-aqui
JWT_EXPIRE_HOURS=12
UPLOAD_DIR=/home/hipo/app/uploads
MAX_UPLOAD_MB=50
ENVIRONMENT=production
```

Para gerar o JWT_SECRET:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

### 2.8 Criar o schema no banco de dados

```bash
# Ainda no servidor EC2
# Baixar o schema do GitHub
curl -O https://raw.githubusercontent.com/SEU_USUARIO/hipo/main/api/schema.sql

# Executar no banco
psql postgresql://hipo_user:SUA_SENHA@SEU_ENDPOINT_RDS:5432/hipo -f schema.sql
```

---

## PARTE 3 — CONFIGURAR O CI/CD (GitHub Actions → EC2)

### 3.1 Adicionar os Secrets no GitHub

1. No GitHub → seu repositório `hipo`
2. **Settings** → **Secrets and variables** → **Actions**
3. Clique em **New repository secret** para cada um:

**Secret 1:**
- Name: `EC2_SSH_KEY`
- Value: conteúdo completo do arquivo `chave-hipo.pem`
  ```bash
  # Para ver o conteúdo:
  cat ~/Downloads/chave-hipo.pem
  ```

**Secret 2:**
- Name: `EC2_HOST`
- Value: IP público do seu servidor EC2 (ex: `54.123.45.67`)

**Secret 3:**
- Name: `EC2_USER`
- Value: `ec2-user`

---

### 3.2 Configurar branch protection (impede deploy sem testes)

1. No GitHub → **Settings** → **Branches**
2. Clique em **Add branch protection rule**
3. **Branch name pattern:** `main`
4. Marque:
   - ✅ Require status checks to pass before merging
   - ✅ Backend Tests
   - ✅ Frontend Tests
   - ✅ Require branches to be up to date before merging
5. Clique em **Create**

---

### 3.3 Verificar o primeiro deploy automático

Depois de configurar os secrets, o pipeline já rodou quando você fez o push inicial. Para verificar:

1. No GitHub → aba **Actions**
2. Você verá o workflow `HIPO CI/CD` rodando
3. Deve mostrar 3 jobs: `Backend Tests` ✅, `Frontend Tests` ✅, `Deploy → EC2` ✅

Se algum falhar, clique no job para ver o log de erro.

---

## PARTE 4 — CRIAR O PRIMEIRO USUÁRIO ADM

Com o servidor no ar, criar o usuário inicial:

```bash
# Conectar ao servidor
ssh -i ~/Downloads/chave-hipo.pem ec2-user@IP_DO_SERVIDOR

# Criar o usuário ADM
python3 - <<'EOF'
import asyncio
import asyncpg
from passlib.context import CryptContext

DATABASE_URL = "postgresql://hipo_user:SUA_SENHA@SEU_ENDPOINT_RDS:5432/hipo"

async def criar():
    conn = await asyncpg.connect(DATABASE_URL)
    pwd = CryptContext(schemes=["bcrypt"]).hash("troque-essa-senha")
    await conn.execute("""
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ('Tulio Horta', 'tulio@seudominio.com.br', $1, 'FRANQUEADO')
    """, pwd)
    await conn.close()
    print("Usuário criado com sucesso.")

asyncio.run(criar())
EOF
```

---

## PARTE 5 — CONFIGURAR AS METAS DO MÊS

Acesse a API diretamente para configurar as metas de Abril:

```bash
# No servidor ou de qualquer lugar com curl
curl -X POST http://IP_DO_SERVIDOR/api/pex/metas \
  -H "Content-Type: application/json" \
  -d '{
    "mes_ref": "2026-04",
    "nmrr_meta": 41044,
    "demos_outbound_meta": 100,
    "dias_uteis": 22,
    "ecs_ativos_m3": 2,
    "evs_ativos": 1,
    "carteira_total_contadores": 120
  }'
```

---

## PARTE 6 — TESTE FINAL

1. Abra o navegador em `http://IP_DO_SERVIDOR`
2. Faça login com o usuário ADM criado
3. Módulo **PEX** → faça upload do `BD_CROMIE.xlsx`
4. Verifique se os indicadores foram calculados
5. Módulo **POs** → faça upload de uma PO da semana
6. Verifique a reconciliação

---

## RESUMO DOS DADOS IMPORTANTES

Anote em local seguro:

| Item | Valor |
|------|-------|
| GitHub repo | `https://github.com/SEU_USUARIO/hipo` |
| IP do servidor | `_______________` |
| RDS Endpoint | `_______________` |
| RDS Senha | `_______________` |
| JWT Secret | `_______________` |
| Chave SSH | `~/Downloads/chave-hipo.pem` |

---

## FLUXO DO DIA A DIA (após setup)

```
Desenvolve localmente →
git add . →
git commit -m "feat: descrição" →
git push origin main →
GitHub Actions roda testes →
Se passou → deploy automático no EC2 →
Sistema atualizado em ~2 minutos
```
