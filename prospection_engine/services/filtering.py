"""Filtros de contratações: proposta, município."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def proposta_encerrada(contratacao: dict) -> bool:
    """
    Retorna True se a proposta já encerrou (deve ser descartada).
    Retorna False quando a data está ausente ou não pode ser interpretada.
    """
    enc_str = contratacao.get("dataEncerramentoProposta")
    if not enc_str:
        return False
    try:
        dt_enc = datetime.fromisoformat(enc_str.replace("Z", "+00:00"))
        return dt_enc < datetime.now(tz=timezone.utc)
    except (ValueError, TypeError):
        log.debug("Data de encerramento inválida: %r", enc_str)
        return False


def resolver_municipio(
    contratacao: dict,
    mapa_municipios: dict[str, dict],
) -> dict | None:
    """
    Retorna mun_info se o município da contratação está no mapa-alvo.
    Retorna None se deve ser descartada (município fora do alvo).
    """
    unidade = contratacao.get("unidadeOrgao", {}) or {}
    orgao = contratacao.get("orgaoEntidade", {}) or {}
    codigo_mun = str(
        unidade.get("codigoIbge", "")
        or orgao.get("codigoMunicipioIbge", "")
        or ""
    )
    return mapa_municipios.get(codigo_mun)
