"""
Interface para estratégias de agrupamento de itens.

Preparada para evolução com embeddings/pgvector.
"""

from __future__ import annotations

from typing import Protocol

from market_comparison.types import ObservedItem


class GroupingStrategy(Protocol):
    """Interface para estratégias de agrupamento."""

    def gerar_chave(self, item: ObservedItem) -> str:
        """Gera chave de agrupamento para um item. Vazia = descartar."""
        ...
