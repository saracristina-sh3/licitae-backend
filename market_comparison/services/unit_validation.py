"""
Validação de consistência de unidade de medida em grupos comparáveis.
"""

from __future__ import annotations

from collections import Counter

from utils import normalizar
from market_comparison.constants import GRUPOS_UNIDADE
from market_comparison.types import ObservedItem


def _normalizar_unidade(unidade: str) -> str:
    """Normaliza unidade de medida para comparação."""
    return normalizar(unidade).strip()


def _grupo_da_unidade(unidade: str) -> frozenset[str] | None:
    """Retorna o grupo de compatibilidade da unidade, se existir."""
    u = _normalizar_unidade(unidade)
    for grupo in GRUPOS_UNIDADE:
        if u in grupo:
            return grupo
    return None


def unidades_compativeis(u1: str, u2: str) -> bool:
    """Verifica se duas unidades são compatíveis."""
    if not u1 or not u2:
        return True
    n1 = _normalizar_unidade(u1)
    n2 = _normalizar_unidade(u2)
    if n1 == n2:
        return True
    g1 = _grupo_da_unidade(n1)
    g2 = _grupo_da_unidade(n2)
    if g1 and g2:
        return g1 == g2
    return False


def validar_consistencia(itens: list[ObservedItem]) -> tuple[str, float]:
    """
    Calcula unidade predominante e taxa de consistência do grupo.

    Retorna (unidade_predominante, taxa_consistencia).
    Taxa = proporção de itens com unidade compatível com a predominante.
    """
    if not itens:
        return "", 0.0

    # Conta ocorrências de cada unidade (normalizada e agrupada)
    contagem: Counter[str] = Counter()
    for item in itens:
        u = _normalizar_unidade(item.unidade)
        grupo = _grupo_da_unidade(u)
        # Usa representante do grupo ou a unidade em si
        chave = next(iter(sorted(grupo))) if grupo else u
        contagem[chave] = contagem.get(chave, 0) + 1

    if not contagem:
        return "", 0.0

    predominante = contagem.most_common(1)[0][0]
    total = len(itens)
    compatíveis = sum(
        1 for item in itens
        if unidades_compativeis(item.unidade, predominante)
    )

    return predominante, round(compatíveis / total, 2)
