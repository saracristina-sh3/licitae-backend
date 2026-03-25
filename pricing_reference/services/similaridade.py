"""
Serviço de similaridade — coordena a busca usando a strategy configurada.
"""

from __future__ import annotations

from pricing_reference.strategies.base import SimilarityStrategy
from pricing_reference.strategies.text_search import TextSearchStrategy
from pricing_reference.types import ResultadoSimilaridade


def criar_strategy(metodo: str = "text_search") -> SimilarityStrategy:
    """Factory para criar a strategy de similaridade."""
    if metodo == "text_search":
        return TextSearchStrategy()
    raise ValueError(f"Método de similaridade desconhecido: {metodo}")


def buscar_licitacoes_similares(
    client,
    licitacao: dict,
    data_limite: str,
    strategy: SimilarityStrategy | None = None,
) -> list[ResultadoSimilaridade]:
    """Busca licitações similares usando a strategy configurada."""
    s = strategy or criar_strategy()
    return s.buscar_licitacoes(client, licitacao, data_limite)


def buscar_itens_similares(
    client,
    licitacao: dict,
    strategy: SimilarityStrategy | None = None,
) -> list[ResultadoSimilaridade]:
    """Busca itens similares usando a strategy configurada."""
    s = strategy or criar_strategy()
    return s.buscar_itens(client, licitacao)
