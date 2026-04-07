"""Teste rápido do Telegram Bot."""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from config import Config
from telegram_client import enviar_mensagem

if not Config.TELEGRAM_BOT_TOKEN:
    print("ERRO: TELEGRAM_BOT_TOKEN não está no .env")
    sys.exit(1)

print(f"Bot token: {Config.TELEGRAM_BOT_TOKEN[:10]}...{Config.TELEGRAM_BOT_TOKEN[-5:]}")

# Modo 1: chat_id direto como argumento
if len(sys.argv) > 1:
    chat_id = sys.argv[1]
    print(f"Testando chat_id: {chat_id}")
    ok = enviar_mensagem(
        chat_id,
        "✅ <b>Licitaê — Teste de conexão</b>\n\n"
        "Se você está vendo esta mensagem, as notificações do Telegram estão funcionando!",
    )
    print("Sucesso!" if ok else "FALHA ao enviar.")
    sys.exit(0)

# Modo 2: testa TODOS os usuários com telegram habilitado
from db import get_client

c = get_client()
r = c.table("profiles").select(
    "id, nome, email, telegram_chat_id",
).eq("alertas_telegram", True).execute()

usuarios = r.data or []
if not usuarios:
    print("Nenhum usuário com alertas_telegram habilitado.")
    sys.exit(1)

print(f"\n{len(usuarios)} usuário(s) com Telegram habilitado:\n")

for u in usuarios:
    nome = u.get("nome") or u.get("email") or u["id"]
    chat_id = u.get("telegram_chat_id") or ""

    # Valida formato
    if not chat_id or not chat_id.strip().lstrip("-").isdigit():
        print(f"  ✗ {nome}: chat_id inválido ({chat_id!r}) — deve ser numérico")
        continue

    ok = enviar_mensagem(
        chat_id,
        "✅ <b>Licitaê — Teste de conexão</b>\n\n"
        f"Olá <b>{nome}</b>! Suas notificações Telegram estão funcionando.",
    )
    status = "✓ enviado" if ok else "✗ FALHA"
    print(f"  {status} — {nome} (chat_id={chat_id})")
