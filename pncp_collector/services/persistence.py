"""Persistência em lote — batch upsert para itens e resultados."""

from __future__ import annotations

import logging
from typing import Any

from pncp_collector.constants import BATCH_SIZE_ITENS, BATCH_SIZE_RESULTADOS, TipoFalha

log = logging.getLogger(__name__)


def _chunks(lst: list, size: int):
    """Divide lista em lotes de tamanho fixo."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def persistir_itens_batch(
    client: Any,
    itens: list[dict],
    batch_size: int = BATCH_SIZE_ITENS,
) -> tuple[int, list[tuple[str, str]]]:
    """
    Upsert de itens em lotes.

    Retorna (total_persistidos, lista de (tipo_falha, mensagem)).
    O retorno do upsert NÃO contém IDs individuais em batch,
    então precisamos buscar IDs depois.
    """
    persistidos = 0
    falhas: list[tuple[str, str]] = []

    for batch in _chunks(itens, batch_size):
        try:
            client.table("itens_contratacao").upsert(
                batch,
                on_conflict="cnpj_orgao,ano_compra,sequencial_compra,numero_item",
            ).execute()
            persistidos += len(batch)
        except Exception as exc:
            falhas.append((TipoFalha.PERSIST, f"Batch de {len(batch)} itens: {exc}"))
            log.warning("Erro ao persistir batch de %d itens: %s", len(batch), exc)

    if persistidos:
        log.debug("Persistidos %d itens em %d lotes", persistidos, -(-len(itens) // batch_size))

    return persistidos, falhas


def persistir_resultados_batch(
    client: Any,
    resultados: list[dict],
    batch_size: int = BATCH_SIZE_RESULTADOS,
) -> tuple[int, list[tuple[str, str]]]:
    """
    Upsert de resultados em lotes.

    Retorna (total_persistidos, lista de (tipo_falha, mensagem)).
    """
    persistidos = 0
    falhas: list[tuple[str, str]] = []

    for batch in _chunks(resultados, batch_size):
        try:
            client.table("resultados_item").upsert(
                batch,
                on_conflict="item_id,sequencial_resultado",
            ).execute()
            persistidos += len(batch)
        except Exception as exc:
            falhas.append((TipoFalha.PERSIST, f"Batch de {len(batch)} resultados: {exc}"))
            log.warning("Erro ao persistir batch de %d resultados: %s", len(batch), exc)

    if persistidos:
        log.debug("Persistidos %d resultados em %d lotes", persistidos, -(-len(resultados) // batch_size))

    return persistidos, falhas


def buscar_ids_itens(
    client: Any,
    cnpj: str,
    ano: int,
    sequencial: int,
) -> dict[int, str]:
    """
    Busca IDs dos itens de uma contratação.
    Retorna {numero_item: id}.
    """
    try:
        result = (
            client.table("itens_contratacao")
            .select("id, numero_item")
            .eq("cnpj_orgao", cnpj)
            .eq("ano_compra", ano)
            .eq("sequencial_compra", sequencial)
            .execute()
        )
        return {row["numero_item"]: row["id"] for row in (result.data or [])}
    except Exception as exc:
        log.warning("Erro ao buscar IDs de itens %s/%d/%d: %s", cnpj, ano, sequencial, exc)
        return {}
