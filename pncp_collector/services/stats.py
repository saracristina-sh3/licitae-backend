"""Estatísticas de execução com classificação de falhas."""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict

from pncp_collector.types import StatsExecucao

log = logging.getLogger(__name__)


class StatsTracker:
    """Rastreia métricas de uma execução do coletor."""

    def __init__(self):
        self._contadores: dict[str, int] = defaultdict(int)
        self._falhas: dict[str, int] = defaultdict(int)
        self._t0 = time.time()
        self._run_id = uuid.uuid4().hex[:12]

    def registrar_licitacao(self) -> None:
        self._contadores["licitacoes_processadas"] += 1

    def registrar_itens_retornados(self, qtd: int) -> None:
        self._contadores["itens_retornados"] += qtd

    def registrar_item_valido(self) -> None:
        self._contadores["itens_validos"] += 1

    def registrar_item_descartado(self) -> None:
        self._contadores["itens_descartados"] += 1

    def registrar_itens_persistidos(self, qtd: int) -> None:
        self._contadores["itens_persistidos"] += qtd

    def registrar_resultados_retornados(self, qtd: int) -> None:
        self._contadores["resultados_retornados"] += qtd

    def registrar_resultados_persistidos(self, qtd: int) -> None:
        self._contadores["resultados_persistidos"] += qtd

    def registrar_falha(self, tipo: str, contexto: str = "") -> None:
        self._falhas[tipo] += 1
        if contexto:
            log.debug("Falha [%s]: %s", tipo, contexto)

    def resumo(self) -> StatsExecucao:
        """Gera o resumo final da execução."""
        return StatsExecucao(
            licitacoes_processadas=self._contadores["licitacoes_processadas"],
            itens_retornados=self._contadores["itens_retornados"],
            itens_validos=self._contadores["itens_validos"],
            itens_descartados=self._contadores["itens_descartados"],
            itens_persistidos=self._contadores["itens_persistidos"],
            resultados_retornados=self._contadores["resultados_retornados"],
            resultados_persistidos=self._contadores["resultados_persistidos"],
            falhas=dict(self._falhas),
            tempo_total_ms=round((time.time() - self._t0) * 1000, 1),
            run_id=self._run_id,
        )

    def log_resumo(self, label: str = "Coleta") -> StatsExecucao:
        """Loga e retorna o resumo."""
        stats = self.resumo()
        log.info(
            "%s [%s]: %d licitações | %d itens (%d válidos, %d persistidos) | "
            "%d resultados persistidos | %.1fs",
            label,
            stats.run_id,
            stats.licitacoes_processadas,
            stats.itens_retornados,
            stats.itens_validos,
            stats.itens_persistidos,
            stats.resultados_persistidos,
            stats.tempo_total_ms / 1000,
        )
        if stats.falhas:
            log.info("  Falhas: %s", stats.falhas)
        return stats
