"""
Motor de busca — thin wrapper para prospection_engine v1.

Mantém compatibilidade com main.py e qualquer outro importador.
"""

from prospection_engine.services.orchestration import (  # noqa: F401
    buscar_licitacoes,
    iterar_contratacoes,
)
from prospection_engine.types import BuscaConfig, ResultadoLicitacao  # noqa: F401
