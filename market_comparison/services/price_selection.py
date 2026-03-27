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


def _calcular_desconto(estimado: float, homologado: float) -> float | None:
    """
    Calcula desconto real: (estimado - homologado) / estimado * 100.
    Ignora a API do PNCP que pode ter valores inconsistentes.
    Retorna None se não for possível calcular ou se fora da faixa válida.
    """
    if estimado <= 0 or homologado <= 0:
        return None
    desconto = ((estimado - homologado) / estimado) * 100
    if 0 <= desconto <= DESCONTO_MAXIMO:
        return round(desconto, 2)
    return None


def selecionar_preco(
    resultados_item: list[dict],
    valor_estimado: float,
) -> tuple[float, str, float | None]:
    """
    Seleciona o melhor preço disponível para um item.

    Regra:
    1. Menor homologado válido (> 0) → fonte="homologado"
    2. Estimado como fallback → fonte="estimado"

    Desconto: recalculado a partir de (estimado - homologado) / estimado.
    Não usa percentual_desconto da API (dados inconsistentes).

    Retorna (valor, fonte_preco, desconto).
    """
    if isinstance(resultados_item, dict):
        resultados_item = [resultados_item]

    est = float(valor_estimado) if valor_estimado else 0.0

    # Busca menor homologado válido
    melhor_hom = None

    for r in resultados_item:
        v = r.get("valor_unitario_homologado", 0)
        if v and float(v) > 0:
            fv = float(v)
            if melhor_hom is None or fv < melhor_hom:
                melhor_hom = fv

    if melhor_hom is not None:
        desconto = _calcular_desconto(est, melhor_hom)
        return melhor_hom, "homologado", desconto

    # Sem homologado = não entra no comparativo
    # O comparativo compara resultados reais de processos finalizados,
    # não estimativas. Estimado é teto antes da disputa, não preço de mercado.
    return 0.0, "estimado", None
