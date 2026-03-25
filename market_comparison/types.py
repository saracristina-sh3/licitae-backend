"""Tipos e estruturas de dados do comparativo de mercado v2."""

from __future__ import annotations

from dataclasses import dataclass, field

from pricing_reference.types import ResumoEstatistico


@dataclass
class ObservedItem:
    """Item observado de uma plataforma com preço selecionado."""
    descricao: str
    ncm: str | None
    unidade: str
    plataforma_nome: str
    plataforma_id: int
    valor: float
    fonte_preco: str  # 'homologado' | 'estimado'
    desconto: float | None = None


@dataclass
class PlatformGroupStats:
    """Estatísticas de uma plataforma dentro de um grupo comparável."""
    plataforma_nome: str
    plataforma_id: int
    resumo: ResumoEstatistico
    total_homologados: int = 0
    total_estimados: int = 0
    fonte_predominante: str = "misto"
    economia_media: float | None = None


@dataclass
class ComparableGroup:
    """Grupo de itens comparáveis entre plataformas."""
    chave: str
    descricao: str
    ncm: str | None
    unidade_predominante: str
    taxa_consistencia_unidade: float
    stats_por_plataforma: dict[str, PlatformGroupStats] = field(default_factory=dict)
    menor_preco_plataforma: str = ""
    score_comparabilidade: float = 0.0
    faixa_confiabilidade: str = "baixa"
    fonte_predominante: str = "misto"
    total_observacoes: int = 0


@dataclass
class PlatformSummary:
    """Resumo consolidado de uma plataforma no comparativo."""
    plataforma_nome: str
    plataforma_id: int
    valor_medio_unitario: float = 0.0
    mediana_unitario: float = 0.0
    desconto_medio: float | None = None
    cv_medio: float | None = None
    total_itens: int = 0
    total_grupos_comparaveis: int = 0
    total_grupos_alta_confianca: int = 0
    vitorias_brutas: int = 0
    vitorias_ponderadas: float = 0.0
    vitorias_alta_confianca: int = 0
    proporcao_vitorias: float = 0.0
    proporcao_homologados: float = 0.0
    score_comparabilidade_medio: float = 0.0
    ranking_medio: float = 0.0
    delta_medio_para_lider: float = 0.0
