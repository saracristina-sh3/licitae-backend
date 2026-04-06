"""Descoberta de pendências — licitações sem itens e itens sem resultado."""

from __future__ import annotations

import logging
from typing import Any

from pncp_collector.constants import RE_URL_PARTS

log = logging.getLogger(__name__)


def extrair_url_parts(url_fonte: str) -> tuple[str, str, str] | None:
    """Extrai (cnpj, ano, seq) da URL do PNCP."""
    if not url_fonte:
        return None
    match = RE_URL_PARTS.search(url_fonte)
    return (match.group(1), match.group(2), match.group(3)) if match else None


def buscar_licitacoes_sem_itens(limite: int, client: Any) -> list[dict]:
    """
    Retorna licitações que ainda não possuem itens coletados.
    Usa o campo itens_coletados para filtrar.
    """
    result = (
        client.table("licitacoes")
        .select(
            "hash_dedup, cnpj_orgao, url_fonte, uf, municipio_nome, "
            "modalidade, modalidade_id, "
            "municipios(codigo_ibge)"
        )
        .neq("cnpj_orgao", "")
        .neq("url_fonte", "")
        .eq("itens_coletados", False)
        .order("created_at", desc=True)
        .limit(limite)
        .execute()
    )
    licitacoes = result.data or []

    log.info("Licitações sem itens: %d (limite=%d)", len(licitacoes), limite)

    pendentes = []
    for lic in licitacoes:
        parts = extrair_url_parts(lic.get("url_fonte", ""))
        if parts:
            lic["_parts"] = parts
            pendentes.append(lic)
        else:
            log.debug("URL sem padrão esperado: %s", lic.get("url_fonte", ""))

    return pendentes


def buscar_itens_sem_resultado(limite: int, client: Any) -> list[dict]:
    """
    Retorna itens que ainda não têm resultado gravado.
    """
    result = (
        client.table("itens_contratacao")
        .select("id, cnpj_orgao, ano_compra, sequencial_compra, numero_item")
        .eq("tem_resultado", True)
        .order("created_at", desc=True)
        .limit(limite * 3)
        .execute()
    )
    itens = result.data or []
    if not itens:
        return []

    ids = [i["id"] for i in itens]

    # Busca em lotes de 100
    ids_com_resultado: set[str] = set()
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        ja = (
            client.table("resultados_item")
            .select("item_id")
            .in_("item_id", batch)
            .execute()
        )
        ids_com_resultado.update(r["item_id"] for r in (ja.data or []))

    return [i for i in itens if i["id"] not in ids_com_resultado][:limite]
