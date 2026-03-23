"""
Geração de relatórios: Excel (.xlsx) e envio por email.
"""

from __future__ import annotations

import logging
import os
import smtplib

log = logging.getLogger(__name__)
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd

from config import Config


def gerar_excel(resultados: list[dict], caminho: str | None = None) -> str:
    """
    Gera relatório Excel com as licitações encontradas.
    Retorna o caminho do arquivo gerado.
    """
    os.makedirs(Config.RELATORIOS_DIR, exist_ok=True)

    if caminho is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = os.path.join(Config.RELATORIOS_DIR, f"licitacoes_software_{timestamp}.xlsx")

    if not resultados:
        df = pd.DataFrame(
            columns=[
                "Relevância",
                "Município",
                "UF",
                "População",
                "FPM",
                "Órgão",
                "CNPJ Órgão",
                "Objeto",
                "Modalidade",
                "Valor Estimado",
                "Valor Homologado",
                "Situação",
                "Data Publicação",
                "Abertura Proposta",
                "Encerramento Proposta",
                "URL PNCP",
                "Palavras-chave",
            ]
        )
    else:
        df = pd.DataFrame(resultados)
        df = df.rename(
            columns={
                "relevancia": "Relevância",
                "municipio": "Município",
                "uf": "UF",
                "populacao": "População",
                "fpm": "FPM",
                "orgao": "Órgão",
                "cnpj_orgao": "CNPJ Órgão",
                "objeto": "Objeto",
                "modalidade": "Modalidade",
                "valor_estimado": "Valor Estimado",
                "valor_homologado": "Valor Homologado",
                "situacao": "Situação",
                "data_publicacao": "Data Publicação",
                "data_abertura_proposta": "Abertura Proposta",
                "data_encerramento_proposta": "Encerramento Proposta",
                "url_pncp": "URL PNCP",
                "palavras_chave_encontradas": "Palavras-chave",
                "exclusivo_me_epp": "Exclusivo ME/EPP",
            }
        )

    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        # Aba principal
        df.to_excel(writer, sheet_name="Licitações", index=False)

        # Aba resumo
        if resultados:
            resumo_data = []

            # Por relevância
            for rel in ["ALTA", "MEDIA", "BAIXA"]:
                count = len([r for r in resultados if r["relevancia"] == rel])
                valor = sum(r["valor_estimado"] for r in resultados if r["relevancia"] == rel)
                resumo_data.append(
                    {"Categoria": f"Relevância {rel}", "Quantidade": count, "Valor Total Estimado": valor}
                )

            # Por UF
            for uf in Config.UFS:
                count = len([r for r in resultados if r["uf"] == uf])
                valor = sum(r["valor_estimado"] for r in resultados if r["uf"] == uf)
                resumo_data.append({"Categoria": f"UF {uf}", "Quantidade": count, "Valor Total Estimado": valor})

            # Por modalidade
            modalidades = set(r["modalidade"] for r in resultados)
            for mod in sorted(modalidades):
                count = len([r for r in resultados if r["modalidade"] == mod])
                valor = sum(r["valor_estimado"] for r in resultados if r["modalidade"] == mod)
                resumo_data.append({"Categoria": mod, "Quantidade": count, "Valor Total Estimado": valor})

            # Total
            resumo_data.append(
                {
                    "Categoria": "TOTAL",
                    "Quantidade": len(resultados),
                    "Valor Total Estimado": sum(r["valor_estimado"] for r in resultados),
                }
            )

            df_resumo = pd.DataFrame(resumo_data)
            df_resumo.to_excel(writer, sheet_name="Resumo", index=False)

        # Formata colunas
        ws = writer.sheets["Licitações"]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

    log.info("Relatório gerado: %s", caminho)
    _rotacionar_relatorios()
    return caminho


def _rotacionar_relatorios(manter: int = 10):
    """Remove relatórios antigos, mantendo apenas os N mais recentes."""
    try:
        arquivos = sorted(
            [
                os.path.join(Config.RELATORIOS_DIR, f)
                for f in os.listdir(Config.RELATORIOS_DIR)
                if f.endswith(".xlsx")
            ],
            key=os.path.getmtime,
        )
        if len(arquivos) > manter:
            for arq in arquivos[: len(arquivos) - manter]:
                os.remove(arq)
                log.info("Relatório antigo removido: %s", os.path.basename(arq))
    except OSError as e:
        log.warning("Erro na rotação de relatórios: %s", e)


def _resumo_html(resultados: list[dict]) -> str:
    """Gera resumo HTML para o corpo do email."""
    if not resultados:
        return "<p>Nenhuma licitação de software encontrada no período.</p>"

    alta = [r for r in resultados if r["relevancia"] == "ALTA"]
    media = [r for r in resultados if r["relevancia"] == "MEDIA"]
    baixa = [r for r in resultados if r["relevancia"] == "BAIXA"]
    valor_total = sum(r["valor_estimado"] for r in resultados)

    html = f"""
    <h2>Resumo</h2>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; font-family: Arial, sans-serif;">
        <tr style="background: #2d3748; color: white;">
            <th>Relevância</th><th>Quantidade</th><th>Valor Estimado</th>
        </tr>
        <tr style="background: #fed7d7;">
            <td>ALTA</td><td>{len(alta)}</td><td>R$ {sum(r['valor_estimado'] for r in alta):,.2f}</td>
        </tr>
        <tr style="background: #fefcbf;">
            <td>MÉDIA</td><td>{len(media)}</td><td>R$ {sum(r['valor_estimado'] for r in media):,.2f}</td>
        </tr>
        <tr>
            <td>BAIXA</td><td>{len(baixa)}</td><td>R$ {sum(r['valor_estimado'] for r in baixa):,.2f}</td>
        </tr>
        <tr style="background: #e2e8f0; font-weight: bold;">
            <td>TOTAL</td><td>{len(resultados)}</td><td>R$ {valor_total:,.2f}</td>
        </tr>
    </table>
    """

    # Top 10 relevância alta
    destaques = alta[:10] if alta else media[:5]
    if destaques:
        html += "<h2>Destaques</h2><table border='1' cellpadding='6' cellspacing='0' style='border-collapse: collapse; font-family: Arial, sans-serif;'>"
        html += "<tr style='background: #2d3748; color: white;'><th>Município</th><th>Objeto</th><th>Valor</th><th>Situação</th><th>Link</th></tr>"
        for r in destaques:
            obj_resumido = r["objeto"][:120] + "..." if len(r["objeto"]) > 120 else r["objeto"]
            html += f"""
            <tr>
                <td>{r['municipio']}/{r['uf']}</td>
                <td>{obj_resumido}</td>
                <td>R$ {r['valor_estimado']:,.2f}</td>
                <td>{r['situacao']}</td>
                <td><a href="{r['url_pncp']}">Ver no PNCP</a></td>
            </tr>
            """
        html += "</table>"

    return html


def enviar_email(resultados: list[dict], arquivo_excel: str) -> bool:
    """Envia relatório por email com o Excel em anexo."""
    if not Config.SMTP_USER or not Config.EMAIL_DESTINATARIOS:
        log.warning("Email não configurado. Configure SMTP_USER e EMAIL_DESTINATARIOS no .env")
        return False

    hoje = datetime.now().strftime("%d/%m/%Y")
    assunto = f"Licitações de Software - {len(resultados)} encontradas - {hoje}"

    msg = MIMEMultipart("alternative")
    msg["From"] = Config.SMTP_USER
    msg["To"] = ", ".join(Config.EMAIL_DESTINATARIOS)
    msg["Subject"] = assunto

    # Corpo texto (fallback para clientes sem HTML)
    ufs_str = ", ".join(Config.UFS)
    if resultados:
        alta = len([r for r in resultados if r["relevancia"] == "ALTA"])
        media = len([r for r in resultados if r["relevancia"] == "MEDIA"])
        baixa = len([r for r in resultados if r["relevancia"] == "BAIXA"])
        valor = sum(r["valor_estimado"] for r in resultados)
        texto_plain = (
            f"Relatório de Licitações de Software - {hoje}\n"
            f"Municípios de {ufs_str} com FPM até 2.8\n\n"
            f"Total: {len(resultados)} licitações encontradas\n"
            f"  ALTA: {alta} | MÉDIA: {media} | BAIXA: {baixa}\n"
            f"  Valor total estimado: R$ {valor:,.2f}\n\n"
            f"Planilha completa em anexo.\n"
        )
    else:
        texto_plain = (
            f"Relatório de Licitações de Software - {hoje}\n"
            f"Nenhuma licitação encontrada no período.\n"
        )
    msg.attach(MIMEText(texto_plain, "plain", "utf-8"))

    # Corpo HTML
    corpo = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #2d3748;">
        <h1 style="color: #2b6cb0;">Relatório de Licitações de Software</h1>
        <p>Busca realizada em {hoje} para municípios de {ufs_str} com FPM até 2.8.</p>
        <p>Palavras-chave: {', '.join(Config.PALAVRAS_CHAVE)}</p>
        {_resumo_html(resultados)}
        <hr>
        <p style="color: #718096; font-size: 12px;">
            Relatório gerado automaticamente. Planilha completa em anexo.
        </p>
    </body>
    </html>
    """
    msg.attach(MIMEText(corpo, "html", "utf-8"))

    # Anexo Excel
    if os.path.exists(arquivo_excel):
        with open(arquivo_excel, "rb") as f:
            anexo = MIMEApplication(f.read(), _subtype="xlsx")
            anexo.add_header(
                "Content-Disposition", "attachment", filename=os.path.basename(arquivo_excel)
            )
            msg.attach(anexo)

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASS)
            server.send_message(msg)
        log.info("Email enviado para: %s", ", ".join(Config.EMAIL_DESTINATARIOS))
        return True
    except Exception as e:
        log.error("Erro ao enviar email: %s", e)
        return False
