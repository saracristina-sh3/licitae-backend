"""
Cliente Telegram — envia mensagens via Bot API.

Requer TELEGRAM_BOT_TOKEN no .env.
"""

from __future__ import annotations

import logging

import httpx

from config import Config

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _bot_url(method: str) -> str:
    return f"{TELEGRAM_API}/bot{Config.TELEGRAM_BOT_TOKEN}/{method}"


def enviar_mensagem(
    chat_id: str,
    texto: str,
    parse_mode: str = "HTML",
) -> bool:
    """Envia mensagem de texto via Telegram Bot API.

    Retorna True se enviou com sucesso.
    """
    if not Config.TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN não configurado, pulando envio")
        return False

    if not chat_id:
        log.debug("chat_id vazio, pulando envio")
        return False

    # Telegram limita mensagens a 4096 caracteres
    if len(texto) > 4096:
        texto = texto[:4090] + "\n..."

    try:
        resp = httpx.post(
            _bot_url("sendMessage"),
            json={
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )

        if resp.status_code == 200:
            log.debug("Telegram enviado para chat_id=%s", chat_id)
            return True

        data = resp.json()
        log.error(
            "Telegram erro %d para chat_id=%s: %s",
            resp.status_code, chat_id, data.get("description", ""),
        )
        return False

    except Exception as e:
        log.error("Erro ao enviar Telegram para chat_id=%s: %s", chat_id, e)
        return False


def enviar_mensagens_batch(
    destinatarios: list[tuple[str, str]],
) -> int:
    """Envia mesma mensagem para múltiplos chat_ids.

    Args:
        destinatarios: lista de (chat_id, texto)

    Returns:
        Quantidade de mensagens enviadas com sucesso.
    """
    enviados = 0
    for chat_id, texto in destinatarios:
        if enviar_mensagem(chat_id, texto):
            enviados += 1
    return enviados
