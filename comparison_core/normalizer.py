"""
Normalização unificada de descrições e extração de termos.
Fonte única — usado por pricing_reference e market_comparison.
"""

from __future__ import annotations

from utils import normalizar
from comparison_core.constants import RE_TOKEN_VALIDO, SINONIMOS, STOPWORDS


def normalizar_descricao(texto: str) -> str:
    """Remove acentos, lowercase, strip espaços extras."""
    return " ".join(normalizar(texto).split())


def aplicar_sinonimos(termos: list[str]) -> list[str]:
    """Substitui termos pelo canônico usando SINONIMOS."""
    return [SINONIMOS.get(t, t) for t in termos]


def extrair_termos(texto: str, min_len: int = 2, max_termos: int | None = None) -> list[str]:
    """
    Extrai termos significativos de uma descrição.

    1. Normaliza (acentos, case)
    2. Tokeniza
    3. Filtra: alfanumérico ≥ min_len chars, não puramente numérico, não stopword
    4. Aplica sinônimos canônicos
    5. Deduplica e ordena alfabeticamente

    Retorna lista ordenada para gerar chaves determinísticas.
    """
    tokens = normalizar(texto).split()
    termos = []

    for t in tokens:
        if len(t) < min_len:
            continue
        if not RE_TOKEN_VALIDO.match(t):
            continue
        if t in STOPWORDS:
            continue
        # Aplica sinônimo
        t = SINONIMOS.get(t, t)
        termos.append(t)

    # Deduplica e ordena
    resultado = sorted(set(termos))

    if max_termos is not None:
        return resultado[:max_termos]
    return resultado


def gerar_chave_lexical(termos: list[str], max_termos: int = 4) -> str:
    """Gera chave de agrupamento a partir de termos normalizados."""
    return " ".join(termos[:max_termos])
