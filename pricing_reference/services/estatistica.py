"""
Funções estatísticas puras para cálculo de preços de referência.
Todas as funções são puras (sem side effects) e seguras para listas vazias.
"""

from __future__ import annotations

import math
import statistics

from pricing_reference.constants import TRIM_PERCENT
from pricing_reference.types import ResumoEstatistico


def remover_outliers_iqr(valores: list[float]) -> list[float]:
    """
    Remove outliers usando Interquartile Range (IQR).
    Valores fora de [Q1 - 1.5*IQR, Q3 + 1.5*IQR] são descartados.

    Retorna a lista original se < 4 valores (IQR não faz sentido).
    """
    if len(valores) < 4:
        return list(valores)

    sorted_v = sorted(valores)
    n = len(sorted_v)
    q1 = sorted_v[n // 4]
    q3 = sorted_v[3 * n // 4]
    iqr = q3 - q1

    limite_inferior = q1 - 1.5 * iqr
    limite_superior = q3 + 1.5 * iqr

    return [v for v in valores if limite_inferior <= v <= limite_superior]


def media_saneada(valores: list[float], trim: float = TRIM_PERCENT) -> float | None:
    """
    Trimmed mean — descarta trim% dos extremos de cada lado.
    Retorna None para lista vazia. Fallback para média simples se < 4 valores.
    """
    if not valores:
        return None
    if len(valores) < 4:
        return statistics.mean(valores)

    sorted_v = sorted(valores)
    corte = max(1, math.floor(len(sorted_v) * trim))
    saneados = sorted_v[corte:len(sorted_v) - corte]
    return statistics.mean(saneados) if saneados else statistics.mean(valores)


def coeficiente_variacao(valores: list[float]) -> float | None:
    """
    CV = (desvio padrão / média) * 100.
    Retorna None se < 2 valores ou média zero.
    """
    if len(valores) < 2:
        return None
    media = statistics.mean(valores)
    if media == 0:
        return None
    return round((statistics.stdev(valores) / media) * 100, 2)


def calcular_percentis(valores: list[float]) -> tuple[float | None, float | None, float | None]:
    """
    Retorna (p25, p50, p75). None para cada se dados insuficientes.
    p50 é a mediana.
    """
    if not valores:
        return None, None, None
    if len(valores) == 1:
        v = valores[0]
        return v, v, v

    sorted_v = sorted(valores)
    n = len(sorted_v)

    def _percentil(p: float) -> float:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_v[int(k)]
        return sorted_v[f] * (c - k) + sorted_v[c] * (k - f)

    return _percentil(0.25), _percentil(0.50), _percentil(0.75)


def calcular_resumo(valores: list[float]) -> ResumoEstatistico:
    """
    Calcula resumo estatístico completo de uma lista de valores.
    Seguro para listas vazias e com 1 único valor.
    """
    if not valores:
        return ResumoEstatistico(
            total=0,
            minimo=None, maximo=None,
            media=None, mediana=None, media_saneada=None,
            desvio_padrao=None, coeficiente_variacao=None,
            percentil_25=None, percentil_50=None, percentil_75=None,
        )

    p25, p50, p75 = calcular_percentis(valores)
    dp = statistics.stdev(valores) if len(valores) >= 2 else None

    return ResumoEstatistico(
        total=len(valores),
        minimo=round(min(valores), 2),
        maximo=round(max(valores), 2),
        media=round(statistics.mean(valores), 2),
        mediana=round(statistics.median(valores), 2),
        media_saneada=round(media_saneada(valores), 2) if media_saneada(valores) is not None else None,
        desvio_padrao=round(dp, 2) if dp is not None else None,
        coeficiente_variacao=coeficiente_variacao(valores),
        percentil_25=round(p25, 2) if p25 is not None else None,
        percentil_50=round(p50, 2) if p50 is not None else None,
        percentil_75=round(p75, 2) if p75 is not None else None,
    )
