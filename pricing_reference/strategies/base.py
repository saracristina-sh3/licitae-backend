"""
Interface para estratégias de similaridade.

Preparada para evolução futura com embeddings/pgvector.
A implementação atual (TextSearchStrategy) usa text_search + ilike do PostgreSQL.

Para adicionar embeddings no futuro:
1. Criar HybridStrategy que combina text_search com pgvector
2. Adicionar campo embedding na tabela licitacoes/itens
3. Usar cosine similarity como componente do score
4. A interface permanece a mesma — só muda a implementação interna
"""

from __future__ import annotations

from typing import Protocol

from pricing_reference.types import ResultadoSimilaridade


class SimilarityStrategy(Protocol):
    """Interface para estratégias de busca de similaridade."""

    def buscar_licitacoes(
        self,
        client,
        licitacao: dict,
        data_limite: str,
    ) -> list[ResultadoSimilaridade]:
        """Busca licitações similares com score e classificação de fonte."""
        ...

    def buscar_itens(
        self,
        client,
        licitacao: dict,
    ) -> list[ResultadoSimilaridade]:
        """Busca itens similares com score e classificação de fonte."""
        ...
