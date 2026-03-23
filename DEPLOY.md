# Deploy — Licitações Software (Hostinger VPS)

## Arquitetura em Produção

```
┌─────────────────────────────────────────────────────┐
│  Hostinger VPS (Ubuntu 22.04 — São Paulo)           │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  Docker                                      │   │
│  │                                              │   │
│  │  ┌─────────────────┐  ┌──────────────────┐   │   │
│  │  │ licitacoes-cron  │  │ watchtower       │   │   │
│  │  │ (Python + cron)  │  │ (auto-update)    │   │   │
│  │  │ 12h diário       │  │                  │   │   │
│  │  └────────┬─────────┘  └──────────────────┘   │   │
│  │           │                                    │   │
│  │     volumes: cache + relatorios                │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  APIs externas:          Serviços:                  │
│  ← PNCP (gov.br)        → Supabase (DB + Auth)     │
│  ← IBGE                 → Gmail SMTP (email)        │
│  ← Querido Diário                                   │
│  ← TCE-RJ                                          │
└─────────────────────────────────────────────────────┘
```

## Requisitos do VPS

| Requisito | Mínimo | Recomendado |
|-----------|--------|-------------|
| **Plano** | KVM 1 | KVM 2 |
| **RAM** | 1 GB | 2 GB |
| **CPU** | 1 vCPU | 2 vCPU |
| **Disco** | 20 GB SSD | 40 GB SSD |
| **OS** | Ubuntu 22.04 | Ubuntu 22.04 |
| **Localização** | São Paulo | São Paulo |

O app é IO-bound (espera respostas de API), então KVM 1 é suficiente para começar.
Localização São Paulo reduz latência para as APIs do governo.

---

## Fase 1 — Contratar VPS

1. Hostinger → VPS → **KVM 1** (~R$25/mês)
2. Localização: **São Paulo**
3. OS: **Ubuntu 22.04**
4. Anotar: IP do servidor e senha root

---

## Fase 2 — Configurar servidor

### 2.1 Acesso e segurança

```bash
# Acessar como root
ssh root@SEU_IP

# Criar usuário não-root
adduser deploy
usermod -aG sudo deploy

# Configurar SSH key
mkdir -p /home/deploy/.ssh
nano /home/deploy/.ssh/authorized_keys   # colar sua chave pública
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# Desabilitar login root por senha
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

# Firewall
ufw allow OpenSSH
ufw enable
```

### 2.2 Instalar Docker

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
apt install docker-compose-plugin -y

# Verificar (como deploy)
su - deploy
docker --version
docker compose version
```

---

## Fase 3 — Preparar credenciais

### 3.1 Gmail App Password

1. Acessar https://myaccount.google.com/security
2. Ativar verificação em duas etapas (se ainda não ativou)
3. Ir em "Senhas de app" → gerar senha para "Outro (nome personalizado)"
4. Usar essa senha no `SMTP_PASS`

### 3.2 Supabase

1. Garantir que todas as migrations SQL (`001` a `006`) foram aplicadas no SQL Editor
2. Copiar `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` do painel do projeto

### 3.3 Criar `.env` no servidor

```bash
ssh deploy@SEU_IP
cd licitacoes-software
cp .env.example .env
nano .env
```

Preencher:
```env
SUPABASE_URL=https://SEU_PROJETO.supabase.co
SUPABASE_SERVICE_KEY=eyJ...sua-service-role-key

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu-email@gmail.com
SMTP_PASS=sua-app-password-do-gmail
EMAIL_DESTINATARIOS=dest1@email.com,dest2@email.com

DIAS_RETROATIVOS=7
UFS=MG,RJ
POPULACAO_MAXIMA=91692
```

---

## Fase 4 — Deploy

### 4.1 Primeiro deploy

```bash
ssh deploy@SEU_IP

# Clonar repositório
git clone https://github.com/SEU_USUARIO/licitacoes-software.git
cd licitacoes-software

# Criar .env (ver Fase 3.3)
cp .env.example .env
nano .env

# Subir
./deploy.sh primeiro
```

### 4.2 Verificar

```bash
./deploy.sh status    # ver containers rodando
./deploy.sh logs      # ver logs em tempo real
./deploy.sh buscar    # rodar busca manual de teste
```

### 4.3 Comandos do deploy.sh

| Comando | O que faz |
|---------|-----------|
| `./deploy.sh primeiro` | Clone + build + start (1a vez) |
| `./deploy.sh atualizar` | Git pull + rebuild + restart |
| `./deploy.sh logs` | Logs em tempo real (últimas 100 linhas) |
| `./deploy.sh status` | Containers + uso de recursos |
| `./deploy.sh parar` | Para todos os serviços |
| `./deploy.sh buscar` | Executa busca manual (sem email) |

---

## Fase 5 — Rotina de atualização

Após fazer mudanças e push no GitHub:

```bash
ssh deploy@SEU_IP
cd licitacoes-software
./deploy.sh atualizar
```

---

## Monitoramento

| O quê | Como |
|-------|------|
| **Logs** | `./deploy.sh logs` — JSON, rotação 10MB x 3 arquivos |
| **Container caiu?** | `restart: unless-stopped` reinicia automaticamente |
| **Atualizações** | Watchtower checa 1x/dia ou `./deploy.sh atualizar` manual |
| **Disco cheio?** | Rotação automática de relatórios (mantém 10) + `docker image prune` |
| **App travou?** | Verificar com `./deploy.sh status` e `./deploy.sh logs` |

---

## Custo mensal estimado

| Item | Custo |
|------|-------|
| Hostinger VPS KVM 1 | ~R$25/mês |
| Supabase (Free tier) | R$0 (até 500MB DB) |
| Gmail SMTP | R$0 |
| **Total** | **~R$25/mês** |

---

## Checklist pré-deploy

- [ ] Repositório no GitHub (privado)
- [ ] `.env` com credenciais reais preenchidas
- [ ] Gmail App Password gerada
- [ ] Migrations SQL aplicadas no Supabase (`001` a `006`)
- [ ] Teste local com Docker: `docker compose up --build`
- [ ] Teste com `--dry-run`: `python main.py --dry-run`
- [ ] VPS contratado e acessível via SSH

---

## Troubleshooting

### Container não inicia
```bash
docker compose -f docker-compose.prod.yml logs licitacoes-cron
```

### Erro de conexão com Supabase
- Verificar `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` no `.env`
- Testar: `docker compose -f docker-compose.prod.yml run --rm licitacoes-cron --dry-run`

### Erro de envio de email
- Verificar `SMTP_USER` e `SMTP_PASS` no `.env`
- Gmail: verificar se App Password está ativa e conta não bloqueou por login suspeito
- Testar: `./deploy.sh buscar` (sem `--sem-email`)

### Disco cheio
```bash
docker system prune -af    # remove imagens/containers não usados
docker volume prune -f     # remove volumes órfãos (cuidado: perde cache)
```

### Atualizar migrations SQL
1. Criar novo arquivo `supabase/007_nome.sql`
2. Rodar manualmente no SQL Editor do Supabase
3. Commitar e `./deploy.sh atualizar`
