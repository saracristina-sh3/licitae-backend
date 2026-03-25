"""
Score de risco do edital baseado nos achados estruturados.

Score 0-100 onde:
- 0-30: baixo risco
- 31-60: médio risco
- 61+: alto risco
"""

from __future__ import annotations

from edital_analysis.constants import TAXONOMIA_RISCOS
from edital_analysis.types import AchadoEstruturado, PrazoClassificado, ScoreRisco

# Pesos fixos para fatores não-regex
PESO_PRAZO_CURTO = 10        # Prazo de implantação < 30 dias
PESO_MUITOS_DOCUMENTOS = 10  # > 10 documentos exigidos
PESO_MUITOS_REQUISITOS = 10  # > 8 requisitos técnicos


def calcular_score_risco(
    riscos: list[AchadoEstruturado],
    prazos: list[PrazoClassificado],
    total_documentos: int = 0,
    total_requisitos: int = 0,
) -> ScoreRisco:
    """
    Calcula score de risco (0-100) baseado nos achados.

    Fatores:
    - Cada tipo de risco encontrado: +peso da taxonomia
    - Prazo de implantação < 30 dias: +10
    - Excesso de documentos (>10): +10
    - Excesso de requisitos técnicos (>8): +10

    Score é capped em 100.
    """
    score = 0.0
    fatores: list[str] = []

    # Pontuação por tipo de risco encontrado (usando peso da taxonomia)
    codigos_encontrados: set[str] = set()
    for risco in riscos:
        if risco.codigo not in codigos_encontrados:
            codigos_encontrados.add(risco.codigo)
            info = TAXONOMIA_RISCOS.get(risco.codigo)
            if info:
                _label, _padroes, peso = info
                score += peso
                fatores.append(risco.label)

    # Prazo curto de implantação
    for prazo in prazos:
        if prazo.tipo == "implantacao" and prazo.unidade == "dia" and prazo.valor < 30:
            score += PESO_PRAZO_CURTO
            fatores.append(f"prazo curto de implantação ({prazo.valor} dias)")
            break

    # Excesso de documentos
    if total_documentos > 10:
        score += PESO_MUITOS_DOCUMENTOS
        fatores.append(f"muitos documentos exigidos ({total_documentos})")

    # Excesso de requisitos técnicos
    if total_requisitos > 8:
        score += PESO_MUITOS_REQUISITOS
        fatores.append(f"muitos requisitos técnicos ({total_requisitos})")

    score = min(score, 100)

    if score >= 61:
        nivel = "alto"
    elif score >= 31:
        nivel = "medio"
    else:
        nivel = "baixo"

    return ScoreRisco(
        score=round(score, 1),
        nivel=nivel,
        fatores=fatores,
    )
