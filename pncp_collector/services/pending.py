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
    Usa RPC com LEFT JOIN; fallback para duas queries.
    """
    try:
        result = client.rpc(
            "licitacoes_sem_itens",
            {"p_limite": limite},
        ).execute()
        return result.data or []
    except Exception:
        log.debug("RPC licitacoes_sem_itens indisponível, usando fallback")

    result = (
        client.table("licitacoes")
        .select(
            "hash_dedup, cnpj_orgao, url_fonte, uf, municipio_nome, "
            "modalidade"
        )
        .neq("cnpj_orgao", "")
        .neq("url_fonte", "")
        .limit(limite * 3)
        .execute()
    )
    licitacoes = result.data or []
    if not licitacoes:
        return []

    # Descobre quais já têm itens em uma única query
    cnpj_ano_seqs = []
    for lic in licitacoes:
        parts = extrair_url_parts(lic.get("url_fonte", ""))
        if parts:
            cnpj_ano_seqs.append(f"{parts[0]}/{parts[1]}/{parts[2]}")

    ja_coletadas: set[str] = set()
    if cnpj_ano_seqs:
        existing = (
            client.table("itens_contratacao")
            .select("cnpj_orgao, ano_compra, sequencial_compra")
            .in_(
                "cnpj_orgao",
                list({p.split("/")[0] for p in cnpj_ano_seqs}),
            )
            .execute()
        )
        for row in existing.data or []:
            chave = f"{row['cnpj_orgao']}/{row['ano_compra']}/{row['sequencial_compra']}"
            ja_coletadas.add(chave)

    pendentes = []
    for lic in licitacoes:
        parts = extrair_url_parts(lic.get("url_fonte", ""))
        if not parts:
            continue
        chave = f"{parts[0]}/{parts[1]}/{parts[2]}"
        if chave not in ja_coletadas:
            lic["_parts"] = parts
            pendentes.append(lic)
        if len(pendentes) >= limite:
            break

    return pendentes


def buscar_itens_sem_resultado(limite: int, client: Any) -> list[dict]:
    """
    Retorna itens com tem_resultado=True que ainda não têm resultado gravado.
    Usa RPC com LEFT JOIN; fallback para duas queries.
    """
    try:
        result = client.rpc(
            "itens_sem_resultado",
            {"p_limite": limite},
        ).execute()
        return result.data or []
    except Exception:
        log.debug("RPC itens_sem_resultado indisponível, usando fallback")

    result = (
        client.table("itens_contratacao")
        .select("id, cnpj_orgao, ano_compra, sequencial_compra, numero_item")
        .eq("tem_resultado", True)
        .limit(limite * 3)
        .execute()
    )
    itens = result.data or []
    if not itens:
        return []

    ids = [i["id"] for i in itens]

    # Busca em lotes de 100 para não estourar URL
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
