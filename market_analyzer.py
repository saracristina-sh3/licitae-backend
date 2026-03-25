"""
Comparativo de mercado — wrapper para compatibilidade com main.py.
A lógica real está em market_comparison/.
"""

from __future__ import annotations

import logging

from market_comparison.services.orchestration import executar_comparativo

__all__ = ["executar_comparativo"]

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    executar_comparativo()
