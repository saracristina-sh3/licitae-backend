"""
Seleção explícita de preço — regra documentada e rastreável.

Estratégia: menor homologado válido > estimado como fallback.

Justificativa: o menor homologado é o preço efetivamente praticado
em disputa competitiva, mais representativo do mercado real do que
o primeiro resultado ou a média. Em licitações, o preço vencedor
reflete a pressão competitiva do certame.
"""

from __future__ import annotations

from market_comparison.constants import DESCONTO_MAXIMO


def selecionar_preco(
    resultados_item: list[dict],
    valor_estimado: float,
) -> tuple[float, str, float | None]:
    """
    Seleciona o melhor preço disponível para um item.

    Regra:
    1. Menor homologado válido (> 0) → fonte="homologado"
    2. Estimado como fallback → fonte="estimado"

    Retorna (valor, fonte_preco, desconto).
    """
    if isinstance(resultados_item, dict):
        resultados_item = [resultados_item]

    # Busca menor homologado válido
    melhor_hom = None
    melhor_desconto = None

    for r in resultados_item:
        v = r.get("valor_unitario_homologado", 0)
        if v and float(v) > 0:
            fv = float(v)
            if melhor_hom is None or fv < melhor_hom:
                melhor_hom = fv
                d = r.get("percentual_desconto")
                melhor_desconto = float(d) if d is not None and 0 <= d <= DESCONTO_MAXIMO else None

    if melhor_hom is not None:
        return melhor_hom, "homologado", melhor_desconto

    # Fallback: estimado
    if valor_estimado and float(valor_estimado) > 0:
        return float(valor_estimado), "estimado", None

    return 0.0, "estimado", None
