"""
Preços de referência — wrapper para compatibilidade com main.py.
A lógica real está em pricing_reference/.
"""

from __future__ import annotations

import logging

from pricing_reference.services.orquestracao import calcular_precos_pendentes


__all__ = ["calcular_precos_pendentes"]


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    calcular_precos_pendentes()
