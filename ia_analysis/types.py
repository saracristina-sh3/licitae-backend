"""Tipos do módulo de análise IA."""

from __future__ import annotations

from typing import TypedDict


class RiscoIdentificado(TypedDict):
    risco: str
    gravidade: str  # alta, media, baixa
    mitigacao: str


class Oportunidade(TypedDict):
    oportunidade: str
    impacto: str  # alto, medio, baixo


class AnaliseIA(TypedDict):
    recomendacao: str  # participar, avaliar, descartar
    score_viabilidade: int
    resumo: str
    riscos_identificados: list[RiscoIdentificado]
    oportunidades: list[Oportunidade]
    preco_sugerido: float | None
    margem_sugerida: float | None
    concorrentes_provaveis: list[str]
    perguntas_esclarecimento: list[str]


class ResultadoAnalise(TypedDict):
    """Resultado completo incluindo metadados."""
    analise: AnaliseIA
    modelo_usado: str
    tokens_input: int
    tokens_output: int
    custo_usd: float
    tempo_ms: int
