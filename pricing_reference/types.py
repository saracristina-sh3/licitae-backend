"""Tipos e estruturas de dados do motor de preços de referência."""

from __future__ import annotations

from typing import TypedDict


class ResumoEstatistico(TypedDict):
    """Resumo estatístico completo de uma lista de valores."""
    total: int
    minimo: float | None
    maximo: float | None
    media: float | None
    mediana: float | None
    media_saneada: float | None
    desvio_padrao: float | None
    coeficiente_variacao: float | None
    percentil_25: float | None
    percentil_50: float | None
    percentil_75: float | None


class ScoreConfiabilidade(TypedDict):
    """Score de confiabilidade com fatores explicáveis."""
    score: float
    faixa: str  # 'alta' | 'media' | 'baixa' | 'insuficiente'
    fatores: dict[str, float]


class ResultadoSimilaridade(TypedDict):
    """Resultado de busca de similaridade com score e fonte."""
    registro: dict
    score: float
    fonte_preco: str  # 'homologado' | 'estimado'
    valor: float
    compativel_unidade: bool


class ResumoPrecoReferencia(TypedDict):
    """Resultado completo do cálculo de preço de referência."""
    licitacao_id: str
    # Licitações similares — todos
    resumo_geral: ResumoEstatistico
    # Licitações similares — só homologados
    resumo_homologado: ResumoEstatistico
    # Licitações similares — só estimados
    resumo_estimado: ResumoEstatistico
    fonte_predominante: str
    # Itens similares
    resumo_itens: ResumoEstatistico
    desconto_medio_itens: float | None
    # Confiabilidade
    confiabilidade: ScoreConfiabilidade
    # Metadados
    janela_meses: int
    versao_algoritmo: str
    metodo_similaridade: str
    metodo_outlier: str
