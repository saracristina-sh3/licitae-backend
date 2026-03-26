"""
Validação de consistência de unidade de medida em grupos comparáveis.
Delega normalização e validação para comparison_core.
"""

from __future__ import annotations

from collections import Counter

from comparison_core.validator import (
    normalizar_unidade as _normalizar_unidade,
    grupo_da_unidade as _grupo_da_unidade,
    unidade_canonica,
    validar_unidade as unidades_compativeis,
)
from market_comparison.types import ObservedItem


def validar_consistencia(itens: list[ObservedItem]) -> tuple[str, float]:
    """
    Calcula unidade predominante e taxa de consistência do grupo.

    Retorna (unidade_predominante, taxa_consistencia).
    Taxa = proporção de itens com unidade compatível com a predominante.
    """
    if not itens:
        return "", 0.0

    contagem: Counter[str] = Counter()
    for item in itens:
        chave = unidade_canonica(item.unidade)
        contagem[chave] = contagem.get(chave, 0) + 1

    if not contagem:
        return "", 0.0

    predominante = contagem.most_common(1)[0][0]
    total = len(itens)
    compativeis = sum(
        1 for item in itens
        if unidades_compativeis(item.unidade, predominante)
    )

    return predominante, round(compativeis / total, 2)
