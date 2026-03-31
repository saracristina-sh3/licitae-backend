"""
Alertas de prazo — verifica oportunidades com prazos próximos e notifica usuários.
Roda diariamente às 8h (configurado em main.py).
"""

from __future__ import annotations

import logging
import smtplib
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import Config

log = logging.getLogger(__name__)

DIAS_ALERTA = [3, 1, 0]


def verificar_prazos():
    """Verifica oportunidades com prazos próximos e grava alertas."""
    from db import get_client

    client = get_client()
    hoje = date.today()

    # Busca oportunidades ativas com prazos
    result = client.table("oportunidades").select(
        "id, user_id, licitacao_id, prazo_interno, status, "
        "licitacoes(data_encerramento_proposta, municipio_nome, uf, objeto)"
    ).not_.in_("status", ["ganha", "perdida", "descartada"]).execute()

    oportunidades = result.data or []

    if not oportunidades:
        log.info("Nenhuma oportunidade ativa para verificar prazos")
        return {"verificadas": 0, "alertas_criados": 0}

    log.info("Verificando prazos de %d oportunidades...", len(oportunidades))

    alertas_para_inserir = []

    for op in oportunidades:
        lic = op.get("licitacoes") or {}

        # Verifica prazo_interno
        if op.get("prazo_interno"):
            try:
                prazo = date.fromisoformat(op["prazo_interno"])
                dias = (prazo - hoje).days
                if dias in DIAS_ALERTA:
                    alertas_para_inserir.append({
                        "oportunidade_id": op["id"],
                        "user_id": op["user_id"],
                        "licitacao_id": op["licitacao_id"],
                        "tipo": "prazo_interno",
                        "dias_restantes": dias,
                        "data_prazo": op["prazo_interno"],
                    })
            except (ValueError, TypeError):
                pass

        # Verifica data_encerramento_proposta
        enc = lic.get("data_encerramento_proposta")
        if enc:
            try:
                dt_enc = datetime.fromisoformat(enc.replace("Z", "+00:00"))
                prazo = dt_enc.date()
                dias = (prazo - hoje).days
                if dias in DIAS_ALERTA:
                    alertas_para_inserir.append({
                        "oportunidade_id": op["id"],
                        "user_id": op["user_id"],
                        "licitacao_id": op["licitacao_id"],
                        "tipo": "encerramento_proposta",
                        "dias_restantes": dias,
                        "data_prazo": prazo.isoformat(),
                    })
            except (ValueError, TypeError):
                pass

    if not alertas_para_inserir:
        log.info("Nenhum prazo próximo detectado")
        return {"verificadas": len(oportunidades), "alertas_criados": 0}

    # Insere com ignore_duplicates (constraint unique evita duplicatas)
    result = client.table("prazo_alertas").upsert(
        alertas_para_inserir,
        on_conflict="oportunidade_id,tipo,dias_restantes",
        ignore_duplicates=True,
    ).execute()

    total_criados = len(result.data) if result.data else 0
    log.info("Alertas de prazo criados: %d", total_criados)

    # Envia notificações agrupadas por usuário
    if total_criados > 0:
        _enviar_emails_prazo(client, alertas_para_inserir)
        _enviar_telegram_prazo(client, alertas_para_inserir)

    return {"verificadas": len(oportunidades), "alertas_criados": total_criados}


def _enviar_emails_prazo(client, alertas: list[dict]):
    """Envia email de alerta de prazo agrupado por usuário."""
    if not Config.SMTP_USER:
        log.warning("SMTP não configurado, pulando envio de email de prazo")
        return

    # Agrupa por user_id
    por_usuario: dict[str, list[dict]] = {}
    for alerta in alertas:
        uid = alerta["user_id"]
        por_usuario.setdefault(uid, []).append(alerta)

    for user_id, user_alertas in por_usuario.items():
        # Busca email do usuário
        try:
            profile = client.table("profiles").select("email").eq("user_id", user_id).single().execute()
            email = profile.data.get("email") if profile.data else None
        except Exception:
            # Fallback: busca na auth.users via admin
            email = None

        if not email:
            log.debug("Sem email para user %s, pulando", user_id)
            continue

        # Busca dados das licitações para o email
        lic_ids = list({a["licitacao_id"] for a in user_alertas})
        lics_result = client.table("licitacoes").select(
            "id, municipio_nome, uf, objeto"
        ).in_("id", lic_ids).execute()
        lics_map = {l["id"]: l for l in (lics_result.data or [])}

        _enviar_email_prazo(email, user_alertas, lics_map)


def _enviar_email_prazo(destinatario: str, alertas: list[dict], lics_map: dict):
    """Envia email de alerta de prazo para um usuário."""
    hoje = datetime.now().strftime("%d/%m/%Y")

    msg = MIMEMultipart("alternative")
    msg["From"] = Config.SMTP_USER
    msg["To"] = destinatario
    msg["Subject"] = f"Licitaê — {len(alertas)} prazo(s) próximo(s) - {hoje}"

    # Monta tabela HTML
    linhas = ""
    for a in sorted(alertas, key=lambda x: x["dias_restantes"]):
        lic = lics_map.get(a["licitacao_id"], {})
        municipio = f"{lic.get('municipio_nome', '?')}/{lic.get('uf', '?')}"
        objeto = lic.get("objeto", "")[:100]
        tipo = "Prazo interno" if a["tipo"] == "prazo_interno" else "Encerramento da proposta"

        if a["dias_restantes"] == 0:
            urgencia = "🔴 Vence hoje"
            cor = "#fed7d7"
        elif a["dias_restantes"] == 1:
            urgencia = "🟡 Vence amanhã"
            cor = "#fefcbf"
        else:
            urgencia = "🔵 Vence em 3 dias"
            cor = "#bee3f8"

        linhas += f"""
        <tr style="background: {cor};">
            <td style="padding: 8px; border: 1px solid #e2e8f0;">{urgencia}</td>
            <td style="padding: 8px; border: 1px solid #e2e8f0;">{municipio}</td>
            <td style="padding: 8px; border: 1px solid #e2e8f0;">{objeto}</td>
            <td style="padding: 8px; border: 1px solid #e2e8f0;">{tipo}</td>
            <td style="padding: 8px; border: 1px solid #e2e8f0;">{a['data_prazo']}</td>
        </tr>
        """

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #2d3748;">
        <h1 style="color: #2b6cb0;">⏰ Prazos Próximos — Licitaê</h1>
        <p>Você tem <strong>{len(alertas)} prazo(s)</strong> vencendo nos próximos dias:</p>
        <table style="border-collapse: collapse; width: 100%; font-size: 14px;">
            <tr style="background: #2d3748; color: white;">
                <th style="padding: 8px;">Urgência</th>
                <th style="padding: 8px;">Município</th>
                <th style="padding: 8px;">Objeto</th>
                <th style="padding: 8px;">Tipo</th>
                <th style="padding: 8px;">Data</th>
            </tr>
            {linhas}
        </table>
        <p style="margin-top: 16px;">Abra o <strong>Licitaê</strong> para ver os detalhes.</p>
        <hr>
        <p style="color: #718096; font-size: 12px;">Alerta automático — Licitaê</p>
    </body>
    </html>
    """

    texto = f"Licitaê — {len(alertas)} prazo(s) próximo(s)\n"
    for a in alertas:
        lic = lics_map.get(a["licitacao_id"], {})
        texto += f"- {lic.get('municipio_nome', '?')}: {a['tipo']} vence em {a['data_prazo']}\n"

    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASS)
            server.sendmail(Config.SMTP_USER, destinatario, msg.as_string())
        log.info("Email de prazo enviado para: %s (%d alertas)", destinatario, len(alertas))
    except Exception as e:
        log.error("Erro ao enviar email de prazo para %s: %s", destinatario, e)


def _enviar_telegram_prazo(client, alertas: list[dict]):
    """Envia alertas de prazo via Telegram para usuários que habilitaram."""
    from telegram_client import enviar_mensagem

    if not Config.TELEGRAM_BOT_TOKEN:
        return

    # Agrupa por user_id
    por_usuario: dict[str, list[dict]] = {}
    for alerta in alertas:
        uid = alerta["user_id"]
        por_usuario.setdefault(uid, []).append(alerta)

    for user_id, user_alertas in por_usuario.items():
        # Verifica se usuário habilitou Telegram
        try:
            uc = client.table("user_config").select(
                "alertas_telegram, telegram_chat_id"
            ).eq("user_id", user_id).single().execute()

            if not uc.data or not uc.data.get("alertas_telegram") or not uc.data.get("telegram_chat_id"):
                continue

            chat_id = uc.data["telegram_chat_id"]
        except Exception:
            continue

        # Busca dados das licitações
        lic_ids = list({a["licitacao_id"] for a in user_alertas})
        lics_result = client.table("licitacoes").select(
            "id, municipio_nome, uf, objeto"
        ).in_("id", lic_ids).execute()
        lics_map = {l["id"]: l for l in (lics_result.data or [])}

        # Monta mensagem
        linhas = []
        for a in sorted(user_alertas, key=lambda x: x["dias_restantes"]):
            lic = lics_map.get(a["licitacao_id"], {})
            municipio = f"{lic.get('municipio_nome', '?')}/{lic.get('uf', '?')}"
            objeto = (lic.get("objeto") or "")[:80]
            tipo = "Prazo interno" if a["tipo"] == "prazo_interno" else "Encerramento"

            if a["dias_restantes"] == 0:
                emoji = "🔴"
                urgencia = "HOJE"
            elif a["dias_restantes"] == 1:
                emoji = "🟡"
                urgencia = "AMANHÃ"
            else:
                emoji = "🔵"
                urgencia = f"em {a['dias_restantes']} dias"

            linhas.append(f"{emoji} <b>{urgencia}</b> — {municipio}\n    {tipo} | {objeto}")

        texto = (
            f"⏰ <b>Licitaê — {len(user_alertas)} prazo(s) próximo(s)</b>\n\n"
            + "\n\n".join(linhas)
        )

        if enviar_mensagem(chat_id, texto):
            # Registra envio
            for a in user_alertas:
                try:
                    client.table("alertas_enviados").insert({
                        "licitacao_id": a["licitacao_id"],
                        "user_id": user_id,
                        "canal": "telegram",
                        "destinatario": chat_id,
                    }).execute()
                except Exception:
                    pass

            log.info("Telegram de prazo enviado para chat_id=%s (%d alertas)", chat_id, len(user_alertas))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    verificar_prazos()
