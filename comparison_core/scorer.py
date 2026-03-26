"""
Helpers de scoring reutilizáveis.
Funções puras que mapeiam indicadores para ratios 0.0–1.0.
"""

from __future__ import annotations


def ratio_amostra(total: int, minimo: int = 3, ideal: int = 10) -> float:
    """Ratio de adequação da amostra. 0.0 se vazio, 1.0 se >= ideal."""
    if total <= 0:
        return 0.0
    if total >= ideal:
        return 1.0
    if total >= minimo:
        return 0.5 + 0.5 * ((total - minimo) / (ideal - minimo))
    return 0.5 * (total / minimo)


def ratio_recencia(dias: float) -> float:
    """Ratio de recência. 1.0 se < 90 dias, decai até 0.0 em 365 dias."""
    if dias <= 90:
        return 1.0
    if dias <= 180:
        return 1.0 - 0.5 * ((dias - 90) / 90)
    if dias <= 365:
        return 0.5 - 0.5 * ((dias - 180) / 185)
    return 0.0


def ratio_dispersao(cv: float | None) -> float:
    """Ratio de baixa dispersão. CV <= 10% = 1.0, > 50% = 0.0."""
    if cv is None:
        return 0.5  # Sem dados = neutro
    if cv <= 10:
        return 1.0
    if cv <= 25:
        return 1.0 - 0.5 * ((cv - 10) / 15)
    if cv <= 50:
        return 0.5 - 0.5 * ((cv - 25) / 25)
    return 0.0


def ratio_homologados(pct: float) -> float:
    """Ratio de proporção de homologados. 100% = 1.0, 0% = 0.2."""
    if pct >= 1.0:
        return 1.0
    if pct >= 0.8:
        return 0.9
    if pct >= 0.5:
        return 0.5 + 0.4 * ((pct - 0.5) / 0.3)
    if pct > 0:
        return 0.2 + 0.3 * (pct / 0.5)
    return 0.2


def ratio_similaridade(score: float) -> float:
    """Ratio de qualidade da similaridade. Score 70+ = 1.0, < 50 = proporcional."""
    if score >= 70:
        return 1.0
    if score >= 50:
        return 0.5 + 0.5 * ((score - 50) / 20)
    return max(0.0, score / 100)
