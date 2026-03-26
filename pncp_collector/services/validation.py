"""Validação e saneamento de payloads da API PNCP."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def validar_item(item_api: dict) -> dict | None:
    """
    Valida e saneia um item vindo da API PNCP.

    Retorna o dict saneado ou None se inválido.
    Descarta se:
    - Sem numeroItem
    - numeroItem não é inteiro positivo
    """
    numero = item_api.get("numeroItem")
    if numero is None:
        return None

    try:
        numero = int(numero)
    except (ValueError, TypeError):
        return None

    if numero <= 0:
        return None

    # Normaliza strings vazias → None
    saneado = {}
    for k, v in item_api.items():
        if isinstance(v, str) and not v.strip():
            saneado[k] = None
        else:
            saneado[k] = v

    saneado["numeroItem"] = numero

    # Converte tipos numéricos
    for campo in ("quantidade", "valorUnitarioEstimado", "valorTotal"):
        val = saneado.get(campo)
        if val is not None:
            try:
                saneado[campo] = float(val)
            except (ValueError, TypeError):
                saneado[campo] = None

    return saneado


def validar_resultado(resultado_api: dict) -> dict | None:
    """
    Valida e saneia um resultado vindo da API PNCP.

    Retorna o dict saneado ou None se inválido.
    Descarta se:
    - Sem sequencialResultado
    - Valores monetários negativos
    """
    seq = resultado_api.get("sequencialResultado")
    if seq is None:
        return None

    try:
        seq = int(seq)
    except (ValueError, TypeError):
        return None

    saneado = {}
    for k, v in resultado_api.items():
        if isinstance(v, str) and not v.strip():
            saneado[k] = None
        else:
            saneado[k] = v

    saneado["sequencialResultado"] = seq

    # Converte e valida valores monetários
    for campo in ("valorUnitarioHomologado", "valorTotalHomologado", "quantidadeHomologada"):
        val = saneado.get(campo)
        if val is not None:
            try:
                val_float = float(val)
                if val_float < 0:
                    return None
                saneado[campo] = val_float
            except (ValueError, TypeError):
                saneado[campo] = None

    # Percentual de desconto
    desc = saneado.get("percentualDesconto")
    if desc is not None:
        try:
            saneado["percentualDesconto"] = float(desc)
        except (ValueError, TypeError):
            saneado["percentualDesconto"] = None

    return saneado
