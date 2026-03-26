"""Deduplicação de contratações por chave natural."""

from __future__ import annotations

import logging

from prospection_engine.types import MatchResult

log = logging.getLogger(__name__)


def chave_dedup(contratacao: dict) -> str:
    """
    Gera chave única: cnpj_orgao + ano_compra + sequencial_compra.
    Identifica univocamente uma contratação no PNCP.
    """
    orgao = contratacao.get("orgaoEntidade", {}) or {}
    cnpj = orgao.get("cnpj", "")
    ano = contratacao.get("anoCompra", "")
    seq = contratacao.get("sequencialCompra", "")
    return f"{cnpj}_{ano}_{seq}"


def deduplicar(
    candidatos: list[tuple[dict, dict, MatchResult]],
) -> list[tuple[dict, dict, MatchResult]]:
    """
    Remove duplicatas mantendo a versão com maior score.

    Recebe lista de (contratacao, mun_info, match_result).
    Duplicatas surgem de janelas sobrepostas ou queries múltiplas.
    """
    vistos: dict[str, tuple[dict, dict, MatchResult]] = {}

    for contratacao, mun_info, match in candidatos:
        chave = chave_dedup(contratacao)
        existente = vistos.get(chave)
        if existente is None or match.score > existente[2].score:
            vistos[chave] = (contratacao, mun_info, match)

    removidos = len(candidatos) - len(vistos)
    if removidos > 0:
        log.debug("Deduplicação: %d duplicatas removidas de %d candidatos", removidos, len(candidatos))

    return list(vistos.values())
