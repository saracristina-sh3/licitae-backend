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

# Pega chat_id do argumento ou do user_config
chat_id = sys.argv[1] if len(sys.argv) > 1 else None

if not chat_id:
    # Tenta puxar do banco
    from db import get_client
    c = get_client()
    r = c.table("user_config").select("telegram_chat_id, user_id").eq("alertas_telegram", True).limit(1).execute()
    if r.data and r.data[0].get("telegram_chat_id"):
        chat_id = r.data[0]["telegram_chat_id"]
        print(f"Chat ID do banco: {chat_id}")
    else:
        print("ERRO: Nenhum chat_id encontrado. Passe como argumento: python test_telegram.py 123456789")
        sys.exit(1)

ok = enviar_mensagem(
    chat_id,
    "✅ <b>Licitaê — Teste de conexão</b>\n\n"
    "Se você está vendo esta mensagem, as notificações do Telegram estão funcionando!",
)

if ok:
    print("Mensagem enviada com sucesso!")
else:
    print("FALHA ao enviar. Verifique o token e o chat_id.")
