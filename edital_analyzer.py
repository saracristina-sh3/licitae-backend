"""
Analisador de editais — wrapper para compatibilidade com main.py.
A lógica real está em edital_analysis/.
"""

from __future__ import annotations

import logging

from edital_analysis.services.orchestration import analisar_licitacoes_pendentes

__all__ = ["analisar_licitacoes_pendentes"]

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    analisar_licitacoes_pendentes()
