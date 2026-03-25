"""
Score de comparabilidade por grupo — indica quão confiável é a comparação.
"""

from __future__ import annotations

import statistics

from market_comparison.constants import (
    FAIXA_ALTA,
    FAIXA_MEDIA,
    PESO_AMOSTRA,
    PESO_DISPERSAO,
    PESO_ESCALA,
    PESO_HOMOLOGADOS,
    PESO_NCM,
    PESO_UNIDADE,
    RAZAO_MAXIMA_ESCALA,
)
from market_comparison.types import ObservedItem


def calcular_score(
    chave: str,
    itens_por_plataforma: dict[str, list[ObservedItem]],
    taxa_consistencia_unidade: float,
) -> tuple[float, str]:
    """
    Score de comparabilidade 0-100 para um grupo.

    Fatores:
    - NCM presente: 20pts
    - Unidade consistente (>80%): 20pts
    - Amostra (>=5 por plataforma): 15pts
    - Baixa dispersão (CV < 30%): 15pts
    - Proporção homologados (>50%): 15pts
    - Escala comparável (max/min < 10): 15pts

    Retorna (score, faixa).
    """
    score = 0.0

    # 1. NCM presente (20pts)
    if chave.startswith("ncm:"):
        score += PESO_NCM

    # 2. Unidade consistente (20pts)
    if taxa_consistencia_unidade >= 0.8:
        score += PESO_UNIDADE
    elif taxa_consistencia_unidade >= 0.5:
        score += PESO_UNIDADE * 0.5

    # 3. Amostra por plataforma (15pts)
    tamanhos = [len(itens) for itens in itens_por_plataforma.values()]
    min_amostra = min(tamanhos) if tamanhos else 0
    if min_amostra >= 5:
        score += PESO_AMOSTRA
    elif min_amostra >= 3:
        score += PESO_AMOSTRA * 0.7
    elif min_amostra >= 1:
        score += PESO_AMOSTRA * 0.3

    # 4. Baixa dispersão — CV médio entre plataformas (15pts)
    cvs = []
    for itens in itens_por_plataforma.values():
        valores = [i.valor for i in itens]
        if len(valores) >= 2:
            media = statistics.mean(valores)
            if media > 0:
                cv = (statistics.stdev(valores) / media) * 100
                cvs.append(cv)

    if cvs:
        cv_medio = statistics.mean(cvs)
        if cv_medio < 15:
            score += PESO_DISPERSAO
        elif cv_medio < 30:
            score += PESO_DISPERSAO * 0.6
        elif cv_medio < 50:
            score += PESO_DISPERSAO * 0.2

    # 5. Proporção de homologados (15pts)
    todos = [i for itens in itens_por_plataforma.values() for i in itens]
    total = len(todos)
    if total > 0:
        hom = sum(1 for i in todos if i.fonte_preco == "homologado")
        ratio = hom / total
        if ratio >= 0.8:
            score += PESO_HOMOLOGADOS
        elif ratio >= 0.5:
            score += PESO_HOMOLOGADOS * 0.7
        elif ratio > 0:
            score += PESO_HOMOLOGADOS * 0.3

    # 6. Escala comparável (15pts)
    medias = []
    for itens in itens_por_plataforma.values():
        valores = [i.valor for i in itens]
        if valores:
            medias.append(statistics.mean(valores))

    if len(medias) >= 2:
        mn, mx = min(medias), max(medias)
        if mn > 0:
            razao = mx / mn
            if razao <= 5:
                score += PESO_ESCALA
            elif razao <= 10:
                score += PESO_ESCALA * 0.6
            elif razao <= RAZAO_MAXIMA_ESCALA:
                score += PESO_ESCALA * 0.2

    score = round(min(score, 100), 2)
    faixa = "alta" if score >= FAIXA_ALTA else "media" if score >= FAIXA_MEDIA else "baixa"

    return score, faixa
