"""Tipos e estruturas de dados do coletor PNCP v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


# ── TypedDicts para rows do banco ────────────────────────────


class Metadata(TypedDict):
    uf: str | None
    municipio: str | None
    codigo_ibge: str | None
    modalidade_id: int | None
    plataforma_id: int | None
    plataforma_nome: str | None


class ItemRow(TypedDict):
    licitacao_hash: str | None
    cnpj_orgao: str
    ano_compra: int
    sequencial_compra: int
    numero_item: int
    descricao: str | None
    ncm_nbs_codigo: str | None
    quantidade: float | None
    unidade_medida: str | None
    valor_unitario_estimado: float | None
    valor_total_estimado: float | None
    tem_resultado: bool
    plataforma_id: int | None
    plataforma_nome: str | None
    uf: str | None
    municipio: str | None
    codigo_ibge: str | None
    modalidade_id: int | None
    material_ou_servico: str | None
    tipo_beneficio_id: int | None
    criterio_julgamento_id: int | None
    coletado_em: str | None
    versao_coletor: str


class ResultadoRow(TypedDict):
    item_id: str
    sequencial_resultado: int
    valor_unitario_homologado: float | None
    valor_total_homologado: float | None
    quantidade_homologada: float | None
    percentual_desconto: float | None
    cnpj_fornecedor: str | None
    nome_fornecedor: str | None
    porte_fornecedor: str | None
    data_resultado: str | None
    coletado_em: str | None
    versao_coletor: str


# ── Stats de coleta ──────────────────────────────────────────


class StatsItens(TypedDict):
    itens: int
    resultados: int
    erros: int


class StatsColeta(TypedDict):
    licitacoes: int
    itens: int
    resultados: int
    erros: int


class StatsPlataforma(TypedDict):
    contratacoes: int
    itens: int
    resultados: int
    erros: int


class StatsResultados(TypedDict):
    resultados: int
    erros: int


# ── Dataclasses para execução ────────────────────────────────


@dataclass
class StatsExecucao:
    """Estatísticas classificadas de uma execução completa."""
    licitacoes_processadas: int = 0
    itens_retornados: int = 0
    itens_validos: int = 0
    itens_descartados: int = 0
    itens_persistidos: int = 0
    resultados_retornados: int = 0
    resultados_persistidos: int = 0
    falhas: dict[str, int] = field(default_factory=dict)
    tempo_total_ms: float = 0.0
    run_id: str = ""
