"""Tipos e estruturas de dados do analisador de editais v2."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AchadoEstruturado:
    """Achado extraído do edital com taxonomia e confiança."""
    codigo: str
    label: str
    trecho: str
    confianca: float = 0.0


@dataclass
class PrazoClassificado:
    """Prazo extraído com classificação de tipo."""
    valor: int
    unidade: str
    tipo: str  # vigencia, execucao, entrega, implantacao, etc.
    contexto: str
    confianca: float = 0.0


@dataclass
class QualidadeExtracao:
    """Avaliação da qualidade do texto extraído."""
    score: float  # 0.0 a 1.0
    faixa: str  # 'boa', 'regular', 'ruim'
    motivos: list[str] = field(default_factory=list)


@dataclass
class ArquivoRanqueado:
    """PDF ranqueado por probabilidade de ser o edital."""
    url: str
    titulo: str
    score: float
    motivos: list[str] = field(default_factory=list)


@dataclass
class ScoreConfianca:
    """Score de confiança da análise."""
    score: float
    faixa: str
    fatores: dict[str, float] = field(default_factory=dict)


@dataclass
class ScoreRisco:
    """Score de risco do edital."""
    score: float
    nivel: str  # 'alto', 'medio', 'baixo'
    fatores: list[str] = field(default_factory=list)


@dataclass
class ResultadoAnalise:
    """Resultado completo da análise de um edital."""
    licitacao_id: str
    # Achados estruturados
    documentos: list[AchadoEstruturado] = field(default_factory=list)
    requisitos: list[AchadoEstruturado] = field(default_factory=list)
    riscos: list[AchadoEstruturado] = field(default_factory=list)
    qualificacao: list[AchadoEstruturado] = field(default_factory=list)
    prazos: list[PrazoClassificado] = field(default_factory=list)
    # Scores
    confianca: ScoreConfianca | None = None
    risco: ScoreRisco | None = None
    qualidade_extracao: QualidadeExtracao | None = None
    # Arquivo
    arquivo: ArquivoRanqueado | None = None
    # Metadados
    paginas: int = 0
    url_documento: str = ""
    texto_extraido: str = ""
    tempo_ms: int = 0
    houve_fallback: bool = False
