"""
Pipeline de prospecção por organização.

Consulta licitações já coletadas no banco e aplica:
1. Filtro geográfico (UFs, microrregiões, FPM)
2. Matching de keywords no objeto + complementar
3. Matching de keywords nos itens (se coletados)
4. Score composto (processo + itens + NCM)
5. Persistência em oportunidades_org
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from prospection_engine.services.scoring import calcular_urgencia, score_para_relevancia
from utils import normalizar

log = logging.getLogger(__name__)


def _match_texto(texto: str, palavras_chave: list[str], termos_exclusao: list[str]) -> dict:
    """
    Match de keywords em um texto.
    Retorna {matched, termos_encontrados}.
    """
    texto_norm = normalizar(texto)

    # Exclusão fail-fast
    for t in termos_exclusao:
        if normalizar(t) in texto_norm:
            return {"matched": False, "termos_encontrados": []}

    encontrados = [p for p in palavras_chave if normalizar(p) in texto_norm]
    return {"matched": bool(encontrados), "termos_encontrados": encontrados}


def _calcular_score_composto(
    match_objeto: dict,
    match_complementar: dict,
    match_itens: list[dict],
    itens: list[dict],
    config: dict,
) -> tuple[float, list[str]]:
    """
    Calcula score composto 0-100 baseado em matches no processo e itens.

    Distribuição:
    - Match no objeto: 25 pts
    - Match no complementar: 10 pts
    - Match em >= 1 item: 20 pts
    - Termo alta no objeto/itens: 20 pts
    - Termo media (se não tem alta): 10 pts
    - NCM alvo em >= 1 item: 10 pts
    - ME/EPP: 5 pts
    """
    score = 0.0
    campos: list[str] = []

    # 1. Match no objeto (25 pts)
    if match_objeto["matched"]:
        termos_obj = len(match_objeto["termos_encontrados"])
        total_kw = max(len(config.get("palavras_chave", [])), 1)
        ratio = min(termos_obj / total_kw * 3, 1.0)
        score += 25 * ratio
        campos.append("objeto")

    # 2. Match no complementar (10 pts)
    if match_complementar["matched"]:
        score += 10
        campos.append("complementar")

    # 3. Match em itens (20 pts)
    itens_com_match = [m for m in match_itens if m["matched"]]
    if itens_com_match:
        score += 20
        campos.append("itens")

    # 4. Termos alta relevância (20 pts)
    termos_alta = config.get("termos_alta", [])
    todos_termos_encontrados = set()
    for m in [match_objeto, match_complementar] + match_itens:
        todos_termos_encontrados.update(m.get("termos_encontrados", []))

    tem_alta = False
    for t in termos_alta:
        t_norm = normalizar(t)
        # Verificar nos termos encontrados ou diretamente nos textos
        if any(normalizar(te) == t_norm or t_norm in normalizar(te) for te in todos_termos_encontrados):
            score += 20
            tem_alta = True
            break

    # 5. Termos media (10 pts, só se não pegou alta)
    if not tem_alta:
        termos_media = config.get("termos_media", [])
        for t in termos_media:
            t_norm = normalizar(t)
            if any(normalizar(te) == t_norm or t_norm in normalizar(te) for te in todos_termos_encontrados):
                score += 10
                break

    # 6. NCM alvo (10 pts)
    ncms_alvo = config.get("ncms_alvo", [])
    if ncms_alvo and itens:
        for item in itens:
            ncm = item.get("ncm_nbs_codigo", "") or ""
            if any(ncm.startswith(n) for n in ncms_alvo):
                score += 10
                if "itens" not in campos:
                    campos.append("itens")
                break

    # 7. ME/EPP (5 pts) — lido do campo da licitação
    # (será verificado no caller)

    return round(min(score, 100.0), 1), campos


def prospectar_para_org(org_config: dict, dias_retroativos: int = 7) -> dict:
    """
    Executa prospecção para uma organização específica.
    Busca licitações do banco, aplica matching e persiste oportunidades.

    Args:
        org_config: Config normalizada da org (de carregar_configs_org)
        dias_retroativos: Janela de busca no banco

    Returns:
        {"org_id": str, "total": int, "alta": int, "media": int, "baixa": int}
    """
    from db import (
        buscar_itens_licitacao,
        buscar_licitacoes_para_prospeccao,
        upsert_oportunidades_org,
    )

    run_id = uuid.uuid4().hex[:8]
    t0 = time.monotonic()
    org_id = org_config.get("org_id")

    log.info(
        "[%s] Prospecção org=%s | UFs=%s | Keywords=%d | Microrregiões=%d",
        run_id,
        org_id,
        org_config.get("ufs", []),
        len(org_config.get("palavras_chave", [])),
        len(org_config.get("microrregioes", [])),
    )

    palavras_chave = org_config.get("palavras_chave", [])
    termos_exclusao = org_config.get("termos_exclusao", [])
    microrregioes = org_config.get("microrregioes", [])

    if not palavras_chave:
        log.warning("[%s] Org %s sem palavras-chave, pulando prospecção", run_id, org_id)
        return {"org_id": org_id, "total": 0, "alta": 0, "media": 0, "baixa": 0}

    # 1. Buscar licitações do banco
    licitacoes = buscar_licitacoes_para_prospeccao(
        ufs=org_config.get("ufs", []),
        populacao_maxima=org_config.get("fpm_maximo", 91692),
        dias_retroativos=dias_retroativos,
        microrregioes_ids=microrregioes if microrregioes else None,
    )
    log.info("[%s] Licitações candidatas: %d", run_id, len(licitacoes))

    # 2. Matching e scoring
    oportunidades: list[dict] = []

    for lic in licitacoes:
        objeto = lic.get("objeto", "") or ""
        complementar = lic.get("informacao_complementar", "") or ""

        # Exclusão fail-fast: se objeto ou complementar contém termo de exclusão, pula
        texto_completo = normalizar(f"{objeto} {complementar}")
        excluida = any(normalizar(t) in texto_completo for t in termos_exclusao)
        if excluida:
            continue

        # Match no objeto e complementar (sem exclusão, já verificada acima)
        match_obj = _match_texto(objeto, palavras_chave, [])
        match_compl = _match_texto(complementar, palavras_chave, [])

        # Match nos itens (se coletados)
        match_itens: list[dict] = []
        itens: list[dict] = []
        cnpj = lic.get("cnpj_orgao", "")

        if lic.get("itens_coletados") and cnpj:
            # Extrair ano/seq da URL
            url = lic.get("url_fonte", "") or ""
            url_match = re.search(r"/editais/[^/]+/(\d+)/(\d+)", url)
            if url_match:
                ano = int(url_match.group(1))
                seq = int(url_match.group(2))
                itens = buscar_itens_licitacao(cnpj, ano, seq)
            for item in itens:
                descricao = item.get("descricao", "") or ""
                match_item = _match_texto(descricao, palavras_chave, [])
                match_item["numero_item"] = item.get("numero_item")
                match_item["descricao"] = descricao
                match_item["quantidade"] = item.get("quantidade", 0)
                match_item["valor_unitario"] = item.get("valor_unitario_estimado", 0)
                match_item["valor_total"] = item.get("valor_total_estimado", 0)
                match_itens.append(match_item)

        # Verificar se há match em algum campo
        tem_match = (
            match_obj["matched"]
            or match_compl["matched"]
            or any(m["matched"] for m in match_itens)
        )

        if not tem_match:
            continue

        # Calcular score
        score, campos = _calcular_score_composto(
            match_obj, match_compl, match_itens, itens, org_config
        )

        # Bônus ME/EPP
        if lic.get("exclusivo_me_epp"):
            score = min(score + 5, 100.0)

        relevancia = score_para_relevancia(score)
        urgencia = calcular_urgencia(lic.get("data_encerramento_proposta"))

        # Coletar todos os termos encontrados
        todos_termos: list[str] = []
        vistos: set[str] = set()
        for m in [match_obj, match_compl] + match_itens:
            for t in m.get("termos_encontrados", []):
                if t not in vistos:
                    todos_termos.append(t)
                    vistos.add(t)

        # Itens que deram match (para exibição)
        itens_matched = [
            {
                "numero_item": m["numero_item"],
                "descricao": m["descricao"],
                "quantidade": m.get("quantidade", 0),
                "valor_unitario": m.get("valor_unitario", 0),
                "valor_total": m.get("valor_total", 0),
            }
            for m in match_itens if m["matched"]
        ]

        valor_itens_relevantes = sum(
            m.get("valor_total", 0) or 0 for m in itens_matched
        )

        oportunidades.append({
            "licitacao_id": lic["id"],
            "score": score,
            "relevancia": relevancia,
            "urgencia": urgencia,
            "palavras_chave_encontradas": todos_termos,
            "campos_matched": campos,
            "itens_matched": itens_matched,
            "total_itens": len(itens),
            "itens_relevantes": len(itens_matched),
            "valor_itens_relevantes": valor_itens_relevantes,
        })

    # 3. Persistir oportunidades
    if oportunidades and org_id:
        upsert_oportunidades_org(org_id, oportunidades)

    # Stats
    alta = sum(1 for o in oportunidades if o["relevancia"] == "ALTA")
    media = sum(1 for o in oportunidades if o["relevancia"] == "MEDIA")
    baixa = sum(1 for o in oportunidades if o["relevancia"] == "BAIXA")

    duracao = time.monotonic() - t0
    log.info(
        "[%s] Prospecção org=%s concluída: %d oportunidades "
        "(ALTA=%d, MEDIA=%d, BAIXA=%d) | %.1fs",
        run_id, org_id, len(oportunidades), alta, media, baixa, duracao,
    )

    # 4. Notificar novas oportunidades de alta relevância
    if alta > 0 and org_id:
        oportunidades_alta = [o for o in oportunidades if o["relevancia"] == "ALTA"]
        _notificar_novas_oportunidades(org_id, oportunidades_alta, licitacoes)

    return {
        "org_id": org_id,
        "total": len(oportunidades),
        "alta": alta,
        "media": media,
        "baixa": baixa,
    }


def _notificar_novas_oportunidades(org_id: str, oportunidades: list[dict], licitacoes: list[dict]):
    """Notifica membros da org sobre novas oportunidades de alta relevância."""
    try:
        from db import get_client
        client = get_client()

        # Busca membros da org com suas configs
        membros = client.table("org_membros").select(
            "user_id"
        ).eq("org_id", org_id).execute()

        if not membros.data:
            return

        # Mapa de licitações por ID
        lic_map = {str(l["id"]): l for l in licitacoes}

        for membro in membros.data:
            user_id = membro["user_id"]

            try:
                uc = client.table("user_config").select(
                    "alertas_email, alertas_telegram, telegram_chat_id"
                ).eq("user_id", user_id).single().execute()
            except Exception:
                continue

            if not uc.data:
                continue

            config_user = uc.data

            # Montar lista de oportunidades
            items_texto = []
            for op in oportunidades[:10]:
                lic = lic_map.get(str(op["licitacao_id"]), {})
                mun = f"{lic.get('municipio_nome', '?')}/{lic.get('uf', '?')}"
                objeto = (lic.get("objeto") or "")[:80]
                score = op.get("score", 0)
                items_texto.append({"municipio": mun, "objeto": objeto, "score": score})

            # Email
            if config_user.get("alertas_email"):
                _enviar_email_novas_oportunidades(client, user_id, items_texto)

            # Telegram
            if config_user.get("alertas_telegram") and config_user.get("telegram_chat_id"):
                _enviar_telegram_novas_oportunidades(
                    config_user["telegram_chat_id"], items_texto
                )

    except Exception as exc:
        log.warning("Erro ao notificar novas oportunidades: %s", exc)


def _enviar_email_novas_oportunidades(client, user_id: str, items: list[dict]):
    """Envia email com novas oportunidades de alta relevância."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from config import Config

    if not Config.SMTP_USER:
        return

    try:
        profile = client.table("profiles").select("email").eq("user_id", user_id).single().execute()
        email = profile.data.get("email") if profile.data else None
        if not email:
            return
    except Exception:
        return

    linhas = ""
    for item in items:
        linhas += f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #e2e8f0;">{item['municipio']}</td>
            <td style="padding: 8px; border: 1px solid #e2e8f0;">{item['objeto']}</td>
            <td style="padding: 8px; border: 1px solid #e2e8f0; font-weight: 600; color: #e53e3e;">{item['score']:.0f}</td>
        </tr>"""

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #2d3748;">
        <h2 style="color: #e53e3e;">Novas oportunidades de alta relevancia — Licitae</h2>
        <p><strong>{len(items)}</strong> nova(s) licitacao(oes) com alta relevancia para sua organizacao:</p>
        <table style="border-collapse: collapse; width: 100%; font-size: 14px;">
            <tr style="background: #2d3748; color: white;">
                <th style="padding: 8px;">Municipio</th>
                <th style="padding: 8px;">Objeto</th>
                <th style="padding: 8px;">Score</th>
            </tr>
            {linhas}
        </table>
        <p style="margin-top: 16px;">Abra o <strong>Licitae</strong> para ver os detalhes.</p>
        <hr>
        <p style="color: #718096; font-size: 12px;">Alerta automatico — Licitae</p>
    </body>
    </html>"""

    msg = MIMEMultipart("alternative")
    msg["From"] = Config.SMTP_USER
    msg["To"] = email
    msg["Subject"] = f"Licitae — {len(items)} nova(s) oportunidade(s) de alta relevancia"
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASS)
            server.sendmail(Config.SMTP_USER, email, msg.as_string())
        log.info("Email de novas oportunidades enviado para %s (%d)", email, len(items))
    except Exception as e:
        log.error("Erro ao enviar email de oportunidades para %s: %s", email, e)


def _enviar_telegram_novas_oportunidades(chat_id: str, items: list[dict]):
    """Envia novas oportunidades via Telegram."""
    from config import Config
    if not Config.TELEGRAM_BOT_TOKEN:
        return

    from telegram_client import enviar_mensagem

    linhas = []
    for item in items:
        linhas.append(
            f"<b>{item['municipio']}</b> (score {item['score']:.0f})\n"
            f"  {item['objeto']}"
        )

    texto = (
        f"<b>Licitae — {len(items)} nova(s) oportunidade(s) ALTA</b>\n\n"
        + "\n\n".join(linhas)
    )

    enviar_mensagem(chat_id, texto)


def prospectar_todas_orgs(dias_retroativos: int = 7) -> list[dict]:
    """
    Executa prospecção para todas as organizações.
    Retorna lista de stats por org.
    """
    from user_configs import carregar_configs_org

    configs = carregar_configs_org()
    log.info("Prospecção para %d organização(ões)", len(configs))

    resultados: list[dict] = []
    for config in configs:
        try:
            stats = prospectar_para_org(config, dias_retroativos)
            resultados.append(stats)
        except Exception as exc:
            org_id = config.get("org_id", "desconhecida")
            log.error("Erro na prospecção org=%s: %s", org_id, exc, exc_info=True)

    total = sum(r["total"] for r in resultados)
    log.info(
        "Prospecção completa: %d orgs, %d oportunidades total",
        len(resultados), total,
    )
    return resultados
