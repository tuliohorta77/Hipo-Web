#!/bin/bash
# ============================================================
# HIPO — Setup EC2 (Amazon Linux 2023)
# Executar como: sudo bash setup_ec2.sh
# ============================================================

set -e

echo "=== [1/8] Atualizando pacotes ==="
dnf update -y

echo "=== [2/8] Instalando dependências do sistema ==="
dnf install -y python3.11 python3.11-pip python3.11-devel \
    postgresql15 git nginx gcc make \
    nodejs npm

echo "=== [3/8] Configurando Python 3.11 como padrão ==="
alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.11 1

echo "=== [4/8] Criando usuário hipo ==="
useradd -m -s /bin/bash hipo || true
mkdir -p /home/hipo/app
chown -R hipo:hipo /home/hipo/app

echo "=== [5/8] Instalando dependências Python ==="
pip3 install \
    fastapi==0.115.0 \
    uvicorn[standard]==0.30.0 \
    asyncpg==0.29.0 \
    psycopg2-binary==2.9.9 \
    alembic==1.13.0 \
    pandas==2.2.0 \
    openpyxl==3.1.2 \
    python-multipart==0.0.9 \
    python-jose[cryptography]==3.3.0 \
    passlib[bcrypt]==1.7.4 \
    pydantic==2.8.0 \
    pydantic-settings==2.3.0 \
    httpx==0.27.0

echo "=== [6/8] Configurando Nginx ==="
cat > /etc/nginx/conf.d/hipo.conf << 'EOF'
server {
    listen 80;
    server_name _;

    # Frontend React
    location / {
        root /var/www/hipo;
        try_files $uri $uri/ /index.html;
    }

    # API FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        client_max_body_size 50M;
    }
}
EOF

mkdir -p /var/www/hipo
systemctl enable nginx
systemctl start nginx

echo "=== [7/8] Configurando serviço systemd ==="
cat > /etc/systemd/system/hipo-api.service << 'EOF'
[Unit]
Description=HIPO FastAPI
After=network.target

[Service]
User=hipo
WorkingDirectory=/home/hipo/app/api
EnvironmentFile=/home/hipo/app/.env
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8001 --workers 4
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable hipo-api

echo "=== [8/8] Configurando diretório de uploads ==="
mkdir -p /home/hipo/app/uploads/{po,cromie,bd_ativados}
chown -R hipo:hipo /home/hipo/app/uploads

echo ""
echo "=== Setup concluído! ==="
echo ""
echo "Próximos passos:"
echo "  1. Criar o banco no RDS PostgreSQL"
echo "  2. Copiar o código da API para /home/hipo/app/api/"
echo "  3. Criar o arquivo /home/hipo/app/.env com as variáveis"
echo "  4. Executar: alembic upgrade head"
echo "  5. Executar: systemctl start hipo-api"
echo "  6. Build do frontend e copiar para /var/www/hipo"
