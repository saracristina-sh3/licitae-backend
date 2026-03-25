"""
Estratégia de agrupamento NCM + lexical.
Inclui unidade de medida na chave para evitar comparações incompatíveis.
"""

from __future__ import annotations

from utils import normalizar
from market_comparison.constants import STOPWORDS
from market_comparison.services.unit_validation import _normalizar_unidade, _grupo_da_unidade
from market_comparison.types import ObservedItem


def _extrair_palavras_chave(descricao: str) -> list[str]:
    """Extrai palavras significativas (sem stopwords, >3 chars, só alfabéticos)."""
    return [
        p for p in normalizar(descricao).split()
        if len(p) > 3 and p.isalpha() and p not in STOPWORDS
    ]


class NcmLexicalStrategy:
    """
    Agrupamento por NCM (quando disponível) ou palavras-chave da descrição.
    Inclui unidade normalizada na chave para garantir comparabilidade.

    Chave: "ncm:{ncm}:{unidade}" ou "desc:{palavras}:{unidade}"
    """

    def gerar_chave(self, item: ObservedItem) -> str:
        """Gera chave de agrupamento incluindo unidade."""
        unidade = _normalizar_unidade(item.unidade)
        grupo = _grupo_da_unidade(unidade)
        unidade_chave = next(iter(sorted(grupo))) if grupo else unidade

        if item.ncm:
            return f"ncm:{item.ncm}:{unidade_chave}"

        palavras = _extrair_palavras_chave(item.descricao)[:5]
        if len(palavras) < 2:
            return ""  # Descrição muito genérica

        return f"desc:{' '.join(palavras)}:{unidade_chave}"
