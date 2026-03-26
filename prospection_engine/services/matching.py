"""Matching multi-campo com exclusão fail-fast."""

from __future__ import annotations

import logging

from prospection_engine.types import MatchResult
from utils import normalizar

log = logging.getLogger(__name__)


def match_contratacao(
    contratacao: dict,
    palavras_chave: list[str],
    termos_exclusao: list[str] | None = None,
) -> MatchResult:
    """
    Faz matching multi-campo e retorna resultado estruturado.

    Verifica exclusão ANTES de confirmar match (fail-fast).
    Busca em dois campos: objetoCompra e informacaoComplementar.
    """
    objeto = contratacao.get("objetoCompra", "") or ""
    complementar = contratacao.get("informacaoComplementar", "") or ""

    objeto_norm = normalizar(objeto)
    compl_norm = normalizar(complementar)
    texto_norm = f"{objeto_norm} {compl_norm}"

    # Exclusão fail-fast
    if termos_exclusao:
        for t in termos_exclusao:
            if normalizar(t) in texto_norm:
                return MatchResult(matched=False)

    # Match separado por campo
    palavras_norm = [(p, normalizar(p)) for p in palavras_chave]

    matches_objeto = [p for p, pn in palavras_norm if pn in objeto_norm]
    matches_compl = [p for p, pn in palavras_norm if pn in compl_norm]

    # Unifica sem duplicatas, preservando ordem
    todos: list[str] = []
    vistos: set[str] = set()
    for m in matches_objeto + matches_compl:
        if m not in vistos:
            todos.append(m)
            vistos.add(m)

    campos: list[str] = []
    if matches_objeto:
        campos.append("objeto")
    if matches_compl:
        campos.append("complementar")

    return MatchResult(
        matched=bool(todos),
        termos_encontrados=todos,
        score=0.0,  # calculado pelo scoring service
        campos_matched=campos,
    )
