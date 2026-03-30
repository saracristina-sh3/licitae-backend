"""Score numérico 0-100 e cálculo de urgência."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from prospection_engine.constants import (
    FAIXA_ALTA,
    FAIXA_MEDIA,
    PESO_MATCH_COMPLEMENTAR,
    PESO_MATCH_OBJETO,
    PESO_ME_EPP,
    PESO_TERMOS_ALTA,
    PESO_TERMOS_MEDIA,
    PESO_VALOR_ESTIMADO,
    URGENCIA_CRITICA_DIAS,
    URGENCIA_PROXIMA_DIAS,
    VALOR_MAX_ESPERADO,
    VALOR_MIN_ESPERADO,
)
from prospection_engine.types import BuscaConfig, MatchResult
from utils import normalizar

# Códigos PNCP de tipoBeneficio que indicam exclusividade ME/EPP
_BENEFICIO_ME_EPP = {1, 2, 3}

log = logging.getLogger(__name__)


def calcular_score(
    match: MatchResult,
    contratacao: dict,
    cfg: BuscaConfig,
) -> float:
    """
    Score composto 0-100 baseado em múltiplos fatores.

    Fatores:
    - Match no objeto (30 pts, proporcional ao nº de termos)
    - Match no complementar (15 pts)
    - Termos de alta relevância (25 pts)
    - Termos de média relevância (10 pts, só se não pegou alta)
    - Valor estimado dentro da faixa (10 pts)
    - Exclusivo ME/EPP (10 pts bônus)
    """
    score = 0.0

    objeto = contratacao.get("objetoCompra", "") or ""
    complementar = contratacao.get("informacaoComplementar", "") or ""
    objeto_norm = normalizar(objeto)
    texto_norm = f"{objeto_norm} {normalizar(complementar)}"

    # 1. Match no objeto (30 pts) — proporcional ao nº de termos
    if "objeto" in match.campos_matched:
        termos_no_objeto = sum(
            1 for t in match.termos_encontrados if normalizar(t) in objeto_norm
        )
        total_palavras = max(len(cfg.palavras_chave), 1)
        ratio = min(termos_no_objeto / total_palavras * 3, 1.0)  # boost x3, cap 1.0
        score += PESO_MATCH_OBJETO * ratio

    # 2. Match no complementar (15 pts)
    if "complementar" in match.campos_matched:
        score += PESO_MATCH_COMPLEMENTAR

    # 3. Termos de alta relevância (25 pts)
    tem_alta = False
    for t in cfg.termos_alta:
        if normalizar(t) in texto_norm:
            score += PESO_TERMOS_ALTA
            tem_alta = True
            break

    # 4. Termos de média relevância (10 pts, só se não pegou alta)
    if not tem_alta:
        for t in cfg.termos_media:
            if normalizar(t) in texto_norm:
                score += PESO_TERMOS_MEDIA
                break

    # 5. Valor estimado dentro da faixa (10 pts)
    valor = contratacao.get("valorTotalEstimado", 0) or 0
    if VALOR_MIN_ESPERADO <= valor <= VALOR_MAX_ESPERADO:
        score += PESO_VALOR_ESTIMADO
    elif valor > 0:
        score += PESO_VALOR_ESTIMADO * 0.5  # valor existe mas fora da faixa

    # 6. Exclusivo ME/EPP (10 pts bônus) — via código PNCP tipoBeneficioId
    if contratacao.get("tipoBeneficioId", 0) in _BENEFICIO_ME_EPP:
        score += PESO_ME_EPP

    return round(min(score, 100.0), 1)


def score_para_relevancia(score: float) -> str:
    """Converte score numérico para classificação textual."""
    if score >= FAIXA_ALTA:
        return "ALTA"
    if score >= FAIXA_MEDIA:
        return "MEDIA"
    return "BAIXA"


def calcular_urgencia(data_encerramento: str | None) -> str:
    """
    Calcula urgência baseada nos dias até o encerramento.

    Retorna "URGENTE", "PROXIMA" ou "NORMAL".
    """
    if not data_encerramento:
        return "NORMAL"

    try:
        dt_enc = datetime.fromisoformat(data_encerramento.replace("Z", "+00:00"))
        agora = datetime.now(tz=timezone.utc)
        dias = (dt_enc - agora).days

        if dias <= URGENCIA_CRITICA_DIAS:
            return "URGENTE"
        if dias <= URGENCIA_PROXIMA_DIAS:
            return "PROXIMA"
        return "NORMAL"
    except (ValueError, TypeError):
        return "NORMAL"
