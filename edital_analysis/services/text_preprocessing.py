"""
Pré-processamento de texto extraído de PDFs de editais.
Limpeza, normalização e segmentação antes da análise por regex.
"""

from __future__ import annotations

import re


def preprocessar(texto: str) -> str:
    """
    Pipeline de limpeza do texto extraído:
    1. Normaliza encoding
    2. Remove numeração de página
    3. Remove cabeçalhos/rodapés repetidos
    4. Une linhas quebradas no meio de palavras
    5. Normaliza espaços
    6. Colapsa linhas vazias
    """
    if not texto:
        return ""

    texto = _normalizar_encoding(texto)
    texto = _remover_numeracao_pagina(texto)
    texto = _unir_linhas_quebradas(texto)
    texto = _normalizar_espacos(texto)
    texto = _colapsar_linhas_vazias(texto)

    return texto.strip()


def _normalizar_encoding(texto: str) -> str:
    """Remove caracteres de controle exceto newline, tab e form feed."""
    return re.sub(r"[\x00-\x08\x0b\x0e-\x1f\x7f-\x9f]", "", texto)


def _remover_numeracao_pagina(texto: str) -> str:
    """Remove padrões comuns de numeração de página."""
    # "Página 1 de 10", "Pág. 1/10", "1/10", "- 1 -"
    texto = re.sub(r"(?i)p[áa]g(?:ina)?\.?\s*\d+\s*(?:de|/)\s*\d+", "", texto)
    texto = re.sub(r"^\s*-?\s*\d{1,3}\s*-?\s*$", "", texto, flags=re.MULTILINE)
    return texto


def _unir_linhas_quebradas(texto: str) -> str:
    """
    Une linhas que foram quebradas no meio de uma frase.
    Ex: "contrata-\\nção" → "contratação"
    Ex: "contrato de\\nprestação" → "contrato de prestação"
    """
    # Hífen no final da linha (quebra de palavra)
    texto = re.sub(r"-\s*\n\s*", "", texto)
    # Linha que termina com letra minúscula seguida de linha que começa com minúscula
    texto = re.sub(r"([a-záéíóúâêôãõç])\s*\n\s*([a-záéíóúâêôãõç])", r"\1 \2", texto)
    return texto


def _normalizar_espacos(texto: str) -> str:
    """Normaliza múltiplos espaços em um único."""
    return re.sub(r"[ \t]+", " ", texto)


def _colapsar_linhas_vazias(texto: str) -> str:
    """Reduz 3+ linhas vazias consecutivas para 2."""
    return re.sub(r"\n{3,}", "\n\n", texto)
