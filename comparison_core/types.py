"""Tipos compartilhados para comparação de itens."""

from __future__ import annotations

from typing import TypedDict


class ItemComparavel(TypedDict):
    """Item normalizado pronto para comparação."""
    descricao: str
    unidade: str
    ncm: str | None
    valor: float
    fonte_preco: str       # "homologado" | "estimado"
    categoria: str         # "produto" | "servico" | "licenca" | "consumivel"
    termos: list[str]      # termos normalizados e ordenados


class ResultadoValidacao(TypedDict):
    """Resultado da validação de comparabilidade entre dois itens."""
    comparavel: bool
    motivo_rejeicao: str | None
    score_ajuste: float    # 0.0 a 1.0 — penalidade aplicada ao score
