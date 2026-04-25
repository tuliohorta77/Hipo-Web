# HIPO — Guia de Execução do Fim de Semana

## Sequência exata de execução

---

### ETAPA 1 — Provisionar o servidor EC2 (30 min)

```bash
# No console AWS — lançar nova instância EC2
# Tipo recomendado: t3.medium (2 vCPU, 4GB RAM) — suficiente para 30 usuários + IAs
# AMI: Amazon Linux 2023
# Security Group: portas 22 (SSH), 80 (HTTP), 443 (HTTPS)
# Armazenamento: 30GB gp3

# Conectar e rodar o setup
ssh -i chave-hipo.pem ec2-user@IP_DO_SERVIDOR
sudo bash setup_ec2.sh
```

---

### ETAPA 2 — Criar o banco no RDS PostgreSQL (20 min)

```
Console AWS → RDS → Create Database
Engine: PostgreSQL 15
Template: Free tier (ou db.t3.micro para produção)
DB name: hipo
Username: hipo_user
Password: (gerar uma senha forte)
VPC: mesma da EC2
Security Group: liberar porta 5432 apenas para a EC2
```

Após criar:
```bash
# Na EC2, testar a conexão
psql -h SEU-RDS-ENDPOINT -U hipo_user -d hipo

# Executar o schema
psql -h SEU-RDS-ENDPOINT -U hipo_user -d hipo -f /home/hipo/app/api/schema.sql
```

---

### ETAPA 3 — Deploy do Backend (20 min)

```bash
# Copiar o código para o servidor
scp -i chave-hipo.pem -r hipo/api/* ec2-user@IP:/home/hipo/app/api/

# Na EC2
cd /home/hipo/app
cp api/.env.template .env
nano .env  # Preencher DATABASE_URL e JWT_SECRET

# Testar a API
cd api
python3 -m uvicorn main:app --host 127.0.0.1 --port 8001

# Se funcionar, iniciar o serviço
sudo systemctl start hipo-api
sudo systemctl status hipo-api
```

---

### ETAPA 4 — Build e Deploy do Frontend (15 min)

```bash
# Local
cd hipo/web
npm install
npm run build

# Copiar para o servidor
scp -i chave-hipo.pem -r dist/* ec2-user@IP:/var/www/hipo/

# No servidor
sudo chmod -R 755 /var/www/hipo
sudo systemctl restart nginx
```

---

### ETAPA 5 — Criar o primeiro usuário ADM (5 min)

```python
# Na EC2, rodar este script uma vez
import asyncio
import asyncpg
from passlib.context import CryptContext

async def criar_admin():
    conn = await asyncpg.connect("postgresql://hipo_user:SENHA@RDS-ENDPOINT:5432/hipo")
    pwd = CryptContext(schemes=["bcrypt"]).hash("senha-inicial-segura")
    await conn.execute("""
        INSERT INTO usuarios (nome, email, senha_hash, cargo)
        VALUES ('Administrador', 'adm@suaempresa.com.br', $1, 'ADM')
    """, pwd)
    await conn.close()
    print("Usuário ADM criado.")

asyncio.run(criar_admin())
```

---

### ETAPA 6 — Configurar metas do mês (5 min)

```bash
# Após o sistema subir, configurar as metas de Abril via API
curl -X POST http://IP/api/pex/metas \
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

### ETAPA 7 — Primeiro upload e teste (15 min)

```
1. Acessar http://IP no navegador
2. Fazer login com o usuário ADM
3. Ir para o módulo PEX → Upload CROmie → selecionar o BD_CROMIE.xlsx
4. Verificar se os indicadores foram calculados
5. Ir para o módulo POs → Upload PO → selecionar uma PO da semana
6. Verificar a reconciliação
```

---

## Checklist de validação

- [ ] API respondendo em /health
- [ ] Login funcionando
- [ ] Upload CROmie processa sem erro
- [ ] PEX calcula e mostra pontuação
- [ ] Compliance mostra gaps por usuário
- [ ] Upload PO classifica CONFORME / AUSENTE / DIVERGENTE
- [ ] Auditoria de schema registra mudanças

---

## Troubleshooting rápido

**API não sobe:**
```bash
sudo journalctl -u hipo-api -n 50
```

**Erro de conexão com RDS:**
```bash
# Verificar security group — porta 5432 precisa estar aberta para a EC2
# Testar diretamente:
psql -h ENDPOINT -U hipo_user -d hipo -c "SELECT 1"
```

**Frontend 502 Bad Gateway:**
```bash
sudo systemctl status nginx
sudo systemctl status hipo-api
# A API precisa estar rodando antes do Nginx redirecionar
```

**Parsing de PO falha:**
O parser usa detecção por conteúdo de nome, não por posição de colunas.
Se uma coluna não for encontrada, o campo fica NULL (não quebra).
Ver os logs: sudo journalctl -u hipo-api -n 20
