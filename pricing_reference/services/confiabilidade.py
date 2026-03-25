"""
Score de confiabilidade do resultado de preço de referência.

Produz um score 0-100 com fatores explicáveis, permitindo ao usuário
e à equipe técnica avaliar a qualidade da referência.

Fórmula documentada:
  score = Σ (peso_fator × ratio_fator)

onde ratio_fator varia de 0.0 a 1.0 conforme o quão bom é o indicador.
"""

from __future__ import annotations

from pricing_reference.constants import (
    AMOSTRA_MINIMA,
    FAIXA_ALTA,
    FAIXA_MEDIA,
    PESO_AMOSTRA,
    PESO_BAIXA_DISPERSAO,
    PESO_HOMOLOGADOS,
    PESO_RECENCIA,
    PESO_SIMILARIDADE,
)
from pricing_reference.types import ScoreConfiabilidade


def _ratio_amostra(total: int) -> float:
    """
    0 amostras = 0.0
    >= AMOSTRA_MINIMA = 0.5
    >= 10 = 1.0
    Interpolação linear entre os marcos.
    """
    if total <= 0:
        return 0.0
    if total >= 10:
        return 1.0
    if total >= AMOSTRA_MINIMA:
        return 0.5 + 0.5 * (total - AMOSTRA_MINIMA) / (10 - AMOSTRA_MINIMA)
    return total / AMOSTRA_MINIMA * 0.5


def _ratio_recencia(dias_media: float) -> float:
    """
    Dados com média de 0-90 dias = 1.0 (muito recentes).
    90-180 dias = 0.5-1.0.
    180-365 dias = 0.0-0.5.
    > 365 = 0.0.
    """
    if dias_media <= 0:
        return 1.0
    if dias_media <= 90:
        return 1.0
    if dias_media <= 180:
        return 1.0 - 0.5 * (dias_media - 90) / 90
    if dias_media <= 365:
        return 0.5 - 0.5 * (dias_media - 180) / 185
    return 0.0


def _ratio_homologados(pct: float) -> float:
    """
    100% homologados = 1.0.
    80% = 0.9.
    50% = 0.5.
    0% = 0.2 (estimados são melhor que nada).
    """
    if pct >= 0.8:
        return 0.8 + 0.2 * (pct - 0.8) / 0.2
    return max(0.2, pct)


def _ratio_dispersao(cv: float | None) -> float:
    """
    CV <= 10% = 1.0 (muito consistente).
    CV 10-25% = 0.5-1.0.
    CV 25-50% = 0.0-0.5.
    CV > 50% = 0.0.
    None = 0.0 (sem dados suficientes).
    """
    if cv is None:
        return 0.0
    if cv <= 10:
        return 1.0
    if cv <= 25:
        return 1.0 - 0.5 * (cv - 10) / 15
    if cv <= 50:
        return 0.5 - 0.5 * (cv - 25) / 25
    return 0.0


def _ratio_similaridade(score_medio: float) -> float:
    """
    Score médio >= 70 = 1.0.
    50-70 = 0.5-1.0.
    0-50 = 0.0-0.5.
    """
    if score_medio >= 70:
        return 1.0
    if score_medio >= 50:
        return 0.5 + 0.5 * (score_medio - 50) / 20
    return max(0.0, score_medio / 50 * 0.5)


def _determinar_faixa(score: float, total_amostra: int) -> str:
    """Determina faixa textual baseado no score e tamanho da amostra."""
    if total_amostra < AMOSTRA_MINIMA:
        return "insuficiente"
    if score >= FAIXA_ALTA:
        return "alta"
    if score >= FAIXA_MEDIA:
        return "media"
    return "baixa"


def calcular_score(
    total_amostra: int,
    cv: float | None,
    pct_homologados: float,
    recencia_dias_media: float,
    score_similaridade_medio: float,
) -> ScoreConfiabilidade:
    """
    Calcula score de confiabilidade do preço de referência.

    Parâmetros
    ----------
    total_amostra : int
        Número total de itens/licitações na amostra.
    cv : float | None
        Coeficiente de variação da amostra (%).
    pct_homologados : float
        Proporção de preços homologados (0.0 a 1.0).
    recencia_dias_media : float
        Média de dias de antiguidade dos dados.
    score_similaridade_medio : float
        Score médio de similaridade dos registros (0-100).

    Retorna
    -------
    ScoreConfiabilidade com score, faixa e fatores detalhados.
    """
    f_amostra = round(_ratio_amostra(total_amostra) * PESO_AMOSTRA, 1)
    f_recencia = round(_ratio_recencia(recencia_dias_media) * PESO_RECENCIA, 1)
    f_homologados = round(_ratio_homologados(pct_homologados) * PESO_HOMOLOGADOS, 1)
    f_dispersao = round(_ratio_dispersao(cv) * PESO_BAIXA_DISPERSAO, 1)
    f_similaridade = round(_ratio_similaridade(score_similaridade_medio) * PESO_SIMILARIDADE, 1)

    score = round(f_amostra + f_recencia + f_homologados + f_dispersao + f_similaridade, 1)
    faixa = _determinar_faixa(score, total_amostra)

    return ScoreConfiabilidade(
        score=score,
        faixa=faixa,
        fatores={
            "amostra": f_amostra,
            "recencia": f_recencia,
            "homologados": f_homologados,
            "baixa_dispersao": f_dispersao,
            "similaridade": f_similaridade,
        },
    )
