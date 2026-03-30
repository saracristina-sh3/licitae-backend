"""Tipos e estruturas de dados do motor de prospecção v1."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import TypedDict

from config import Config
from prospection_engine.constants import TERMOS_ALTA, TERMOS_MEDIA


# ── Configuração da busca ────────────────────────────────────


@dataclass
class BuscaConfig:
    """
    Configuração completa de uma busca.
    Todos os campos possuem defaults vindos do Config (.env).
    """

    ufs: list[str] = field(default_factory=lambda: list(Config.UFS))
    palavras_chave: list[str] = field(default_factory=lambda: list(Config.PALAVRAS_CHAVE))
    modalidades: list[int] = field(default_factory=lambda: list(Config.MODALIDADES))
    fpm_maximo: int = field(default_factory=lambda: Config.POPULACAO_MAXIMA)
    termos_alta: list[str] = field(default_factory=lambda: list(TERMOS_ALTA))
    termos_media: list[str] = field(default_factory=lambda: list(TERMOS_MEDIA))
    termos_exclusao: list[str] = field(default_factory=list)
    janela_dias: int = field(default_factory=lambda: getattr(Config, "JANELA_DIAS", 1))
    max_workers: int = field(default_factory=lambda: getattr(Config, "MAX_WORKERS", 3))

    @classmethod
    def from_dict(cls, d: dict) -> BuscaConfig:
        """Cria uma BuscaConfig a partir de um dict, ignorando valores None."""
        nomes_campos = {f.name for f in fields(cls)}
        campos_validos = {k: v for k, v in d.items() if v is not None and k in nomes_campos}
        return cls(**campos_validos)


# ── Resultado da busca ───────────────────────────────────────


class ResultadoLicitacao(TypedDict):
    municipio: str
    uf: str
    populacao: int
    fpm: float
    codigo_ibge: str
    orgao: str
    cnpj_orgao: str
    objeto: str
    exclusivo_me_epp: bool
    modalidade: str
    valor_estimado: float
    valor_homologado: float
    situacao: str
    data_publicacao: str
    data_abertura_proposta: str
    data_encerramento_proposta: str
    url_pncp: str
    palavras_chave_encontradas: str
    relevancia: str  # "ALTA" | "MEDIA" | "BAIXA" — derivado do score
    fonte: str
    ano_compra: str
    seq_compra: str
    # Novos campos v1
    score: float                  # 0.0 a 100.0
    informacao_complementar: str  # texto do informacaoComplementar
    urgencia: str                 # "URGENTE" | "PROXIMA" | "NORMAL"


# ── Resultado do matching ────────────────────────────────────


@dataclass
class MatchResult:
    """Resultado do matching de uma contratação."""
    matched: bool
    termos_encontrados: list[str] = field(default_factory=list)
    score: float = 0.0
    campos_matched: list[str] = field(default_factory=list)


# ── Estatísticas de execução ─────────────────────────────────


@dataclass
class SearchStats:
    """Estatísticas da execução para observabilidade."""
    run_id: str = ""
    total_contratacoes: int = 0
    total_filtradas_proposta: int = 0
    total_filtradas_municipio: int = 0
    total_filtradas_keyword: int = 0
    total_filtradas_exclusao: int = 0
    total_duplicatas: int = 0
    total_resultados: int = 0
    stats_por_uf: dict[str, int] = field(default_factory=dict)
    tempo_total_ms: float = 0.0
