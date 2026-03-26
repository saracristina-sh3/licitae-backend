"""Constantes centralizadas do coletor PNCP v2."""

from __future__ import annotations

import re

VERSAO_COLETOR = "v2"

# ── Delays e retry ───────────────────────────────────────────
DELAY_BASE: float = 0.3          # segundos entre requests
DELAY_RATE_LIMIT: float = 30.0   # segundos após 429
DELAY_ERRO: float = 5.0          # segundos após erro genérico
MAX_RETRIES: int = 3
BACKOFF_FACTOR: float = 2.0      # delay *= factor a cada retry

# ── Batch ────────────────────────────────────────────────────
BATCH_SIZE_ITENS: int = 50
BATCH_SIZE_RESULTADOS: int = 50

# ── Regex ────────────────────────────────────────────────────
RE_URL_PARTS = re.compile(r"/(?:editais|compras)/([^/]+)/(\d+)/(\d+)")

# ── Classificação de falhas ──────────────────────────────────

class TipoFalha:
    NETWORK = "network_error"
    TIMEOUT = "timeout_error"
    RATE_LIMIT = "rate_limit_error"
    API = "api_error"
    VALIDATION = "validation_error"
    PERSIST = "persist_error"
    PARTIAL = "partial_collection_error"

# Falhas que permitem retry
FALHAS_RETRIABLE: frozenset[str] = frozenset({
    TipoFalha.NETWORK,
    TipoFalha.TIMEOUT,
    TipoFalha.RATE_LIMIT,
})
