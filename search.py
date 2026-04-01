"""
Motor de busca — wrappers para prospection_engine.

Expõe tanto o pipeline legado (buscar_licitacoes) quanto os novos:
- coletar_licitacoes: coleta genérica sem keywords
- prospectar_para_org: prospecção por organização
- prospectar_todas_orgs: prospecção para todas as orgs
"""

# Pipeline legado (backward compatibility)
from prospection_engine.services.orchestration import (  # noqa: F401
    buscar_licitacoes,
    iterar_contratacoes,
)

# Novo pipeline: coleta genérica
from prospection_engine.services.collection import (  # noqa: F401
    coletar_licitacoes,
)

# Novo pipeline: prospecção por org
from prospection_engine.services.prospection import (  # noqa: F401
    prospectar_para_org,
    prospectar_todas_orgs,
)

from prospection_engine.types import BuscaConfig, ResultadoLicitacao  # noqa: F401
