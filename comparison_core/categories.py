"""
Classificação de itens por categoria.
Impede comparações entre categorias incompatíveis (Golden Rule).
"""

from __future__ import annotations

from comparison_core.normalizer import normalizar_descricao
from comparison_core.constants import CATEGORIAS


def classificar_item(descricao: str) -> str:
    """
    Classifica um item em: servico, licenca, consumivel ou produto.

    Prioridade: serviço > licença > consumível > produto (fallback).
    Busca keywords da categoria na descrição normalizada.
    """
    texto = normalizar_descricao(descricao)
    tokens = set(texto.split())

    # Ordem de prioridade
    for categoria in ("servico", "licenca", "consumivel"):
        keywords = CATEGORIAS[categoria]
        for kw in keywords:
            if kw in tokens:
                return categoria

    return "produto"
