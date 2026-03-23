#!/bin/bash
# ============================================================
# Deploy — Licitaê Backend
# Uso: ./deploy.sh [primeiro|atualizar|logs|status|parar|buscar]
# ============================================================

set -euo pipefail

APP_DIR="/home/deploy/licitae-backend"
COMPOSE_FILE="docker-compose.prod.yml"

case "${1:-atualizar}" in
  primeiro)
    echo "=== PRIMEIRO DEPLOY ==="

    # Clonar repo (troque pela URL do seu repo)
    if [ ! -d "$APP_DIR" ]; then
      git clone https://github.com/saracristina-sh3/licitae-backend.git "$APP_DIR"
    fi

    cd "$APP_DIR"

    # Verificar .env
    if [ ! -f .env ]; then
      echo "ERRO: Crie o arquivo .env antes de continuar"
      echo "  cp .env.example .env && nano .env"
      exit 1
    fi

    # Build e start
    docker compose -f "$COMPOSE_FILE" up -d --build

    echo ""
    echo "=== Deploy concluído! ==="
    echo "  Logs: docker compose -f $COMPOSE_FILE logs -f"
    echo "  Status: docker compose -f $COMPOSE_FILE ps"
    ;;

  atualizar)
    echo "=== ATUALIZANDO ==="
    cd "$APP_DIR"

    git pull origin main
    docker compose -f "$COMPOSE_FILE" up -d --build
    docker image prune -f

    echo "=== Atualização concluída! ==="
    ;;

  logs)
    cd "$APP_DIR"
    docker compose -f "$COMPOSE_FILE" logs -f --tail=100
    ;;

  status)
    cd "$APP_DIR"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    docker stats --no-stream
    ;;

  parar)
    cd "$APP_DIR"
    docker compose -f "$COMPOSE_FILE" down
    echo "Serviços parados."
    ;;

  buscar)
    echo "=== Executando busca manual ==="
    cd "$APP_DIR"
    docker compose -f "$COMPOSE_FILE" run --rm licitacoes-cron --sem-email
    ;;

  *)
    echo "Uso: $0 [primeiro|atualizar|logs|status|parar|buscar]"
    exit 1
    ;;
esac
