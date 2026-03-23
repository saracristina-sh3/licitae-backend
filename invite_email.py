"""
Envio de emails de convite para organização.
Verifica convites pendentes (email_enviado = false) e envia.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import Config

log = logging.getLogger(__name__)


def enviar_convites_pendentes():
    """Busca convites não enviados e envia email."""
    from db import get_client

    client = get_client()

    result = client.table("org_convites").select(
        "id, email, nome_convidante, nome_organizacao, created_at"
    ).eq("email_enviado", False).eq("aceito", False).execute()

    convites = result.data or []

    if not convites:
        log.info("Nenhum convite pendente para envio")
        return {"enviados": 0}

    log.info("Enviando %d convite(s)...", len(convites))
    enviados = 0

    for convite in convites:
        ok = _enviar_email_convite(
            destinatario=convite["email"],
            nome_convidante=convite.get("nome_convidante") or "Um colega",
            nome_organizacao=convite.get("nome_organizacao") or "uma equipe",
        )

        if ok:
            client.table("org_convites").update(
                {"email_enviado": True}
            ).eq("id", convite["id"]).execute()
            enviados += 1

    log.info("Convites enviados: %d/%d", enviados, len(convites))
    return {"enviados": enviados}


def _enviar_email_convite(destinatario: str, nome_convidante: str, nome_organizacao: str) -> bool:
    """Envia email de convite."""
    if not Config.SMTP_USER:
        log.warning("SMTP não configurado")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = Config.SMTP_USER
    msg["To"] = destinatario
    msg["Subject"] = f"Convite para o Licitaê — {nome_organizacao}"

    texto = (
        f"Você foi convidado(a) para fazer parte do time no Licitaê!\n\n"
        f"Convidado por: {nome_convidante}\n"
        f"Equipe: {nome_organizacao}\n\n"
        f"Para aceitar, baixe o app Licitaê e faça login com este email ({destinatario}).\n"
        f"O convite aparecerá automaticamente na seção de Equipe.\n\n"
        f"Equipe Licitaê"
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8" /></head>
<body style="margin:0; padding:0; background-color:#f4f6f8; font-family: Arial, Helvetica, sans-serif; color:#1f2937;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f6f8; padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px; background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 18px rgba(0,0,0,0.06);">

          <tr>
            <td align="center" style="background:#0f766e; padding:28px 24px; color:#ffffff;">
              <h1 style="margin:0; font-size:28px;">Licitaê</h1>
              <p style="margin:8px 0 0; font-size:14px; opacity:0.95;">
                Plataforma para gestão e acompanhamento de licitações
              </p>
            </td>
          </tr>

          <tr>
            <td style="padding:32px 28px;">
              <h2 style="margin:0 0 16px; font-size:24px; color:#111827;">
                Você foi convidado(a) para fazer parte do time Licitaê
              </h2>

              <p style="margin:0 0 16px; font-size:16px; line-height:1.7;">
                Olá,
              </p>

              <p style="margin:0 0 16px; font-size:16px; line-height:1.7;">
                <strong>{nome_convidante}</strong> convidou você para fazer parte da equipe
                <strong>{nome_organizacao}</strong> no Licitaê.
              </p>

              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0; background:#f9fafb; border:1px solid #e5e7eb; border-radius:10px;">
                <tr>
                  <td style="padding:20px;">
                    <p style="margin:0 0 10px; font-size:14px; color:#374151;">
                      <strong>Convidado por:</strong> {nome_convidante}
                    </p>
                    <p style="margin:0; font-size:14px; color:#374151;">
                      <strong>Equipe:</strong> {nome_organizacao}
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 16px; font-size:16px; line-height:1.7;">
                Para aceitar o convite:
              </p>

              <ol style="margin:0 0 16px; padding-left:20px; font-size:16px; line-height:2;">
                <li>Baixe o app <strong>Licitaê</strong></li>
                <li>Crie sua conta com o email <strong>{destinatario}</strong></li>
                <li>Vá em <strong>Config → Gerenciar Organização</strong></li>
                <li>O convite aparecerá automaticamente — clique em <strong>Aceitar</strong></li>
              </ol>

              <p style="margin:0 0 16px; font-size:16px; line-height:1.7;">
                Ao aceitar, você poderá acessar as licitações e oportunidades compartilhadas pela equipe.
              </p>

              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 0; background:#fffbeb; border:1px solid #f59e0b; border-radius:10px;">
                <tr>
                  <td style="padding:18px;">
                    <p style="margin:0 0 10px; font-size:14px; font-weight:bold; color:#92400e;">
                      Aviso de segurança
                    </p>
                    <p style="margin:0; font-size:14px; line-height:1.7; color:#92400e;">
                      Se você não esperava este convite, pode ignorar este e-mail com segurança.
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:28px 0 0; font-size:16px; line-height:1.7;">
                Atenciosamente,<br />
                <strong>Equipe Licitaê</strong>
              </p>
            </td>
          </tr>

          <tr>
            <td align="center" style="background:#f9fafb; padding:20px 24px; border-top:1px solid #e5e7eb;">
              <p style="margin:0 0 8px; font-size:12px; color:#6b7280;">
                Este é um e-mail automático. Por favor, não responda esta mensagem.
              </p>
              <p style="margin:0; font-size:12px; color:#9ca3af;">
                licitae.app · Licitaê
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASS)
            server.sendmail(Config.SMTP_USER, destinatario, msg.as_string())
        log.info("Convite enviado para: %s", destinatario)
        return True
    except Exception as e:
        log.error("Erro ao enviar convite para %s: %s", destinatario, e)
        return False


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    enviar_convites_pendentes()
