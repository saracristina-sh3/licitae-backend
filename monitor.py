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

        # Grava alertas e atualiza snapshot
        if alertas:
            log.info("Monitoramento %d: %d mudança(s) detectada(s)", mon["id"], len(alertas))
            client.table("monitoramento_alertas").insert(alertas).execute()
            total_mudancas += len(alertas)

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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    verificar_mudancas()
