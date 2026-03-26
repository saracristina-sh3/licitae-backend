"""
Estratégia de agrupamento NCM + lexical v2.
Gera múltiplas chaves por item para maximizar cruzamentos entre plataformas.
"""

from __future__ import annotations

import re

from utils import normalizar
from market_comparison.constants import SINONIMOS, STOPWORDS
from market_comparison.services.unit_validation import _normalizar_unidade, _grupo_da_unidade
from market_comparison.types import ObservedItem

# Regex: aceita alfanuméricos mas descarta tokens puramente numéricos
_RE_TOKEN_VALIDO = re.compile(r"^(?!\d+$)[a-z0-9]{2,}$")


def _extrair_palavras_chave(descricao: str) -> list[str]:
    """
    Extrai palavras significativas da descrição.
    - Aceita alfanuméricos (a4, usb3, 500ml) mas não puramente numéricos (123)
    - Remove stopwords
    - Aplica sinônimos canônicos
    - Ordena alfabeticamente para garantir mesma chave independente da ordem
    """
    tokens = normalizar(descricao).split()
    palavras = []
    for t in tokens:
        if not _RE_TOKEN_VALIDO.match(t):
            continue
        if t in STOPWORDS:
            continue
        # Aplica sinônimo se existir
        t = SINONIMOS.get(t, t)
        palavras.append(t)

    # Ordena para que "papel sulfite a4" == "sulfite papel a4"
    return sorted(set(palavras))


def _unidade_chave(unidade: str) -> str:
    """Normaliza unidade para usar como parte da chave."""
    unidade = _normalizar_unidade(unidade)
    grupo = _grupo_da_unidade(unidade)
    return next(iter(sorted(grupo))) if grupo else unidade


class NcmLexicalStrategy:
    """
    Agrupamento NCM + lexical v2.

    Gera até 3 chaves por item (do mais específico ao mais genérico):
    1. NCM exato:     ncm:{ncm_completo}:{unidade}
    2. NCM categoria: ncm4:{ncm[:4]}:{4_palavras}:{unidade}
    3. Lexical:       desc:{4_palavras_ordenadas}:{unidade}

    Palavras são ordenadas alfabeticamente e sinônimos aplicados,
    garantindo que o mesmo produto gere a mesma chave entre plataformas.
    """

    def gerar_chaves(self, item: ObservedItem) -> list[str]:
        """Gera lista de chaves de agrupamento (múltiplas por item).

        Inclui fonte (hom/est) na chave para nunca misturar preços
        homologados com estimados — são dados de natureza diferente.
        """
        unidade = _unidade_chave(item.unidade)
        palavras = _extrair_palavras_chave(item.descricao)
        fonte = "hom" if item.fonte_preco == "homologado" else "est"
        chaves: list[str] = []

        # 1. NCM exato (alta confiança)
        if item.ncm and len(item.ncm) >= 4:
            chaves.append(f"ncm:{item.ncm}:{unidade}:{fonte}")

        # 2. NCM categoria + palavras (média confiança)
        if item.ncm and len(item.ncm) >= 4 and len(palavras) >= 2:
            ncm4 = item.ncm[:4]
            desc_part = " ".join(palavras[:4])
            chaves.append(f"ncm4:{ncm4}:{desc_part}:{unidade}:{fonte}")

        # 3. Lexical puro (baixa confiança)
        if len(palavras) >= 2:
            desc_part = " ".join(palavras[:4])
            chaves.append(f"desc:{desc_part}:{unidade}:{fonte}")

        return chaves

    def gerar_chave(self, item: ObservedItem) -> str:
        """Compatibilidade: retorna a melhor chave (mais específica)."""
        chaves = self.gerar_chaves(item)
        return chaves[0] if chaves else ""
