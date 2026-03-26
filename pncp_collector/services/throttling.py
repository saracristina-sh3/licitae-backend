"""Throttling com backoff exponencial e detecção de rate limit."""

from __future__ import annotations

import logging
import time

from pncp_collector.constants import (
    BACKOFF_FACTOR,
    DELAY_BASE,
    DELAY_ERRO,
    DELAY_RATE_LIMIT,
    FALHAS_RETRIABLE,
    MAX_RETRIES,
    TipoFalha,
)

log = logging.getLogger(__name__)


class Throttler:
    """Controle de velocidade com backoff adaptativo."""

    def __init__(
        self,
        delay_base: float = DELAY_BASE,
        max_retries: int = MAX_RETRIES,
        backoff_factor: float = BACKOFF_FACTOR,
    ):
        self.delay_base = delay_base
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._falhas_consecutivas = 0
        self._delay_atual = delay_base

    def esperar(self) -> None:
        """Espera o delay atual entre requests."""
        if self._delay_atual > 0:
            time.sleep(self._delay_atual)

    def registrar_sucesso(self) -> None:
        """Reseta contadores após sucesso."""
        self._falhas_consecutivas = 0
        self._delay_atual = self.delay_base

    def registrar_falha(self, tipo_falha: str) -> None:
        """Ajusta delay baseado no tipo de falha."""
        self._falhas_consecutivas += 1

        if tipo_falha == TipoFalha.RATE_LIMIT:
            self._delay_atual = DELAY_RATE_LIMIT
            log.warning("Rate limit detectado — aguardando %.0fs", DELAY_RATE_LIMIT)
        elif tipo_falha in (TipoFalha.NETWORK, TipoFalha.TIMEOUT):
            self._delay_atual = min(
                DELAY_ERRO * (self.backoff_factor ** self._falhas_consecutivas),
                DELAY_RATE_LIMIT,
            )
            log.debug("Backoff: %.1fs (falha #%d)", self._delay_atual, self._falhas_consecutivas)
        else:
            self._delay_atual = DELAY_ERRO

    def deve_retry(self, tentativa: int, tipo_falha: str) -> bool:
        """Decide se deve tentar novamente."""
        if tentativa >= self.max_retries:
            return False
        return tipo_falha in FALHAS_RETRIABLE

    @property
    def falhas_consecutivas(self) -> int:
        return self._falhas_consecutivas
