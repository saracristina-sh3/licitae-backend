"""
Monitor de licitações — verifica mudanças no PNCP para licitações monitoradas.
Roda periodicamente (cron ou schedule) e grava alertas no Supabase.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

CAMPOS_MONITORADOS = {
    "situacaoCompraNome": ("situacao", "ultimo_situacao"),
    "valorTotalEstimado": ("valor_estimado", "ultimo_valor_estimado"),
    "valorTotalHomologado": ("valor_homologado", "ultimo_valor_homologado"),
    "dataEncerramentoProposta": ("data_encerramento", "ultimo_data_encerramento"),
}


def _extrair_url_parts(url_fonte: str) -> tuple[str, str, str] | None:
    """Extrai cnpj, ano e seq da URL do PNCP."""
    if not url_fonte:
        return None
    # https://pncp.gov.br/app/editais/CNPJ/ANO/SEQ
    import re
    match = re.search(r"/editais/([^/]+)/(\d+)/(\d+)", url_fonte)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None


def verificar_mudancas():
    """Busca licitações monitoradas e verifica mudanças no PNCP."""
    from db import get_client
    from pncp_client import PNCPClient

    client = get_client()
    pncp = PNCPClient()

    # Busca monitoramentos ativos
    result = client.table("monitoramento").select(
        "*, licitacoes(url_fonte, cnpj_orgao, situacao, valor_estimado, "
        "valor_homologado, data_encerramento_proposta, proposta_aberta)"
    ).eq("ativo", True).execute()

    monitoramentos = result.data or []

    if not monitoramentos:
        log.info("Nenhuma licitação sendo monitorada")
        return {"verificadas": 0, "mudancas": 0}

    log.info("Verificando %d licitações monitoradas...", len(monitoramentos))

    total_mudancas = 0

    for mon in monitoramentos:
        lic = mon.get("licitacoes") or {}
        url_fonte = lic.get("url_fonte", "")
        parts = _extrair_url_parts(url_fonte)

        if not parts:
            log.debug("Sem URL PNCP para monitoramento %d, pulando", mon["id"])
            continue

        cnpj, ano, seq = parts

        # Busca dados atuais no PNCP
        try:
            detalhes = pncp.buscar_contratacao_detalhes(cnpj, int(ano), int(seq))
        except Exception as e:
            log.warning("Erro ao buscar PNCP para monitoramento %d: %s", mon["id"], e)
            continue

        if not detalhes:
            continue

        # Compara campos
        alertas = []
        snapshot_update = {"ultimo_check_at": datetime.now().isoformat()}

        for campo_pncp, (campo_nome, campo_snapshot) in CAMPOS_MONITORADOS.items():
            valor_novo = detalhes.get(campo_pncp)
            valor_anterior = mon.get(campo_snapshot)

            if valor_novo is None:
                continue

            # Converte para string para comparação uniforme
            str_novo = str(valor_novo).strip() if valor_novo else ""
            str_anterior = str(valor_anterior).strip() if valor_anterior else ""

            if str_novo and str_novo != str_anterior:
                alertas.append({
                    "monitoramento_id": mon["id"],
                    "user_id": mon["user_id"],
                    "licitacao_id": mon["licitacao_id"],
                    "campo": campo_nome,
                    "valor_anterior": str_anterior or None,
                    "valor_novo": str_novo,
                })
                snapshot_update[campo_snapshot] = valor_novo

        # Verifica proposta_aberta separadamente
        enc = detalhes.get("dataEncerramentoProposta")
        if enc:
            try:
                dt_enc = datetime.fromisoformat(enc.replace("Z", "+00:00"))
                nova_proposta_aberta = dt_enc.replace(tzinfo=None) > datetime.now()
            except (ValueError, TypeError):
                nova_proposta_aberta = None

            if nova_proposta_aberta is not None and nova_proposta_aberta != mon.get("ultimo_proposta_aberta"):
                alertas.append({
                    "monitoramento_id": mon["id"],
                    "user_id": mon["user_id"],
                    "licitacao_id": mon["licitacao_id"],
                    "campo": "proposta_aberta",
                    "valor_anterior": str(mon.get("ultimo_proposta_aberta")),
                    "valor_novo": str(nova_proposta_aberta),
                })
                snapshot_update["ultimo_proposta_aberta"] = nova_proposta_aberta

        # Grava alertas e notifica
        if alertas:
            log.info("Monitoramento %d: %d mudança(s) detectada(s)", mon["id"], len(alertas))
            client.table("monitoramento_alertas").insert(alertas).execute()
            total_mudancas += len(alertas)

            # Envia notificações
            _notificar_mudanca_email(client, mon["user_id"], mon["licitacao_id"], alertas, lic)
            _notificar_mudanca_telegram(client, mon["user_id"], mon["licitacao_id"], alertas, lic)

            # Atualiza licitação no banco com dados novos
            lic_update = {}
            if "ultimo_situacao" in snapshot_update:
                lic_update["situacao"] = snapshot_update["ultimo_situacao"]
            if "ultimo_valor_estimado" in snapshot_update:
                lic_update["valor_estimado"] = snapshot_update["ultimo_valor_estimado"]
            if "ultimo_valor_homologado" in snapshot_update:
                lic_update["valor_homologado"] = snapshot_update["ultimo_valor_homologado"]
            if "ultimo_data_encerramento" in snapshot_update:
                lic_update["data_encerramento_proposta"] = snapshot_update["ultimo_data_encerramento"]

            if lic_update:
                client.table("licitacoes").update(lic_update).eq("id", mon["licitacao_id"]).execute()

        # Atualiza snapshot do monitoramento
        client.table("monitoramento").update(snapshot_update).eq("id", mon["id"]).execute()

    log.info("Verificação concluída: %d licitações, %d mudanças", len(monitoramentos), total_mudancas)
    return {"verificadas": len(monitoramentos), "mudancas": total_mudancas}


def _notificar_mudanca_email(client, user_id: str, licitacao_id: str, alertas: list[dict], lic: dict):
    """Envia notificação de mudança via email se o usuário habilitou."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from config import Config

    if not Config.SMTP_USER:
        return

    try:
        uc = client.table("user_config").select(
            "alertas_email"
        ).eq("user_id", user_id).single().execute()

        if not uc.data or not uc.data.get("alertas_email"):
            return

        profile = client.table("profiles").select("email").eq("user_id", user_id).single().execute()
        email = profile.data.get("email") if profile.data else None
        if not email:
            return
    except Exception:
        return

    municipio = f"{lic.get('municipio_nome', '?')}/{lic.get('uf', '?')}"
    objeto = (lic.get("objeto") or "")[:120]

    linhas_html = ""
    for a in alertas:
        anterior = a["valor_anterior"] or "—"
        novo = a["valor_novo"] or "—"
        linhas_html += f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #e2e8f0; font-weight: 600;">{a['campo']}</td>
            <td style="padding: 8px; border: 1px solid #e2e8f0; color: #718096;">{anterior}</td>
            <td style="padding: 8px; border: 1px solid #e2e8f0; color: #2b6cb0; font-weight: 600;">{novo}</td>
        </tr>"""

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #2d3748;">
        <h2 style="color: #e53e3e;">Mudanca detectada — Licitae</h2>
        <p><strong>{municipio}</strong></p>
        <p>{objeto}</p>
        <table style="border-collapse: collapse; width: 100%; font-size: 14px; margin-top: 12px;">
            <tr style="background: #2d3748; color: white;">
                <th style="padding: 8px;">Campo</th>
                <th style="padding: 8px;">Anterior</th>
                <th style="padding: 8px;">Novo</th>
            </tr>
            {linhas_html}
        </table>
        <p style="margin-top: 16px;">Abra o <strong>Licitae</strong> para ver os detalhes.</p>
        <hr>
        <p style="color: #718096; font-size: 12px;">Alerta automatico — Licitae</p>
    </body>
    </html>"""

    msg = MIMEMultipart("alternative")
    msg["From"] = Config.SMTP_USER
    msg["To"] = email
    msg["Subject"] = f"Licitae — Mudanca em {municipio}"
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASS)
            server.sendmail(Config.SMTP_USER, email, msg.as_string())

        client.table("alertas_enviados").insert({
            "licitacao_id": licitacao_id,
            "user_id": user_id,
            "canal": "email",
            "destinatario": email,
        }).execute()

        log.info("Email de mudanca enviado para %s", email)
    except Exception as e:
        log.error("Erro ao enviar email de mudanca para %s: %s", email, e)


def _notificar_mudanca_telegram(client, user_id: str, licitacao_id: str, alertas: list[dict], lic: dict):
    """Envia notificação de mudança via Telegram se o usuário habilitou."""
    from config import Config

    if not Config.TELEGRAM_BOT_TOKEN:
        return

    try:
        uc = client.table("user_config").select(
            "alertas_telegram, telegram_chat_id"
        ).eq("user_id", user_id).single().execute()

        if not uc.data or not uc.data.get("alertas_telegram") or not uc.data.get("telegram_chat_id"):
            return

        chat_id = uc.data["telegram_chat_id"]
    except Exception:
        return

    municipio = f"{lic.get('municipio_nome', '?')}/{lic.get('uf', '?')}"
    objeto = (lic.get("objeto") or "")[:80]

    mudancas = []
    for a in alertas:
        campo = a["campo"]
        anterior = a["valor_anterior"] or "—"
        novo = a["valor_novo"] or "—"
        mudancas.append(f"  • <b>{campo}</b>: {anterior} → {novo}")

    texto = (
        f"🔔 <b>Licitaê — Mudança detectada</b>\n\n"
        f"📍 {municipio}\n"
        f"📄 {objeto}\n\n"
        f"<b>Alterações:</b>\n"
        + "\n".join(mudancas)
    )

    from telegram_client import enviar_mensagem

    if enviar_mensagem(chat_id, texto):
        try:
            client.table("alertas_enviados").insert({
                "licitacao_id": licitacao_id,
                "user_id": user_id,
                "canal": "telegram",
                "destinatario": chat_id,
            }).execute()
        except Exception:
            pass

        log.info("Telegram de mudança enviado para chat_id=%s", chat_id)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    verificar_mudancas()
