#!/bin/bash
# ============================================================
# Setup completo do VPS — Licitaê
# Rodar como root: bash setup-vps.sh
# ============================================================

set -euo pipefail

echo "=== 1/6 — Atualizando sistema ==="
apt update && apt upgrade -y

echo "=== 2/6 — Instalando Docker ==="
if ! command -v docker &> /dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
else
  echo "Docker já instalado: $(docker --version)"
fi

echo "=== 3/6 — Instalando Docker Compose plugin ==="
apt install -y docker-compose-plugin git

echo "=== 4/6 — Criando usuário deploy ==="
if ! id "deploy" &>/dev/null; then
  adduser --disabled-password --gecos "" deploy
  usermod -aG docker deploy
  echo "Usuário 'deploy' criado"
else
  echo "Usuário 'deploy' já existe"
  usermod -aG docker deploy
fi

echo "=== 5/6 — Configurando firewall ==="
apt install -y ufw
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "=== 6/6 — Instalando Nginx (para o site + reverse proxy) ==="
apt install -y nginx certbot python3-certbot-nginx

# Cria config do Nginx para licitae.app
cat > /etc/nginx/sites-available/licitae <<'NGINX'
server {
    listen 80;
    server_name licitae.app www.licitae.app;

    # Site estático
    root /home/deploy/licitae-backend/site;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache de imagens
    location /img/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Headers de segurança
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
NGINX

ln -sf /etc/nginx/sites-available/licitae /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "============================================"
echo " VPS configurado com sucesso!"
echo "============================================"
echo ""
echo "Próximos passos:"
echo "  1. Apontar DNS de licitae.app para este IP"
echo "  2. Clonar o repo:  git clone https://github.com/saracristina-sh3/licitae-backend.git /home/deploy/licitae-backend"
echo "  3. Criar .env e subir Docker"
echo "  4. Gerar SSL:  certbot --nginx -d licitae.app -d www.licitae.app"
echo ""
