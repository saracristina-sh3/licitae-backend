"""
Estratégia de agrupamento NCM + lexical v2.
Gera múltiplas chaves por item para maximizar cruzamentos entre plataformas.
Usa comparison_core para normalização e sinônimos.
"""

from __future__ import annotations

from comparison_core.normalizer import extrair_termos
from comparison_core.validator import unidade_canonica
from market_comparison.types import ObservedItem


class NcmLexicalStrategy:
    """
    Agrupamento NCM + lexical v2.

    Gera até 3 chaves por item (do mais específico ao mais genérico):
    1. NCM exato:     ncm:{ncm_completo}:{unidade}
    2. NCM categoria: ncm4:{ncm[:4]}:{4_palavras}:{unidade}
    3. Lexical:       desc:{4_palavras_ordenadas}:{unidade}

    A fonte (homologado/estimado) NÃO faz parte da chave — é metadado.
    Separar por fonte impediria comparações entre plataformas com fontes
    diferentes, reduzindo drasticamente os grupos comparáveis.
    """

    def gerar_chaves(self, item: ObservedItem) -> list[str]:
        """Gera lista de chaves de agrupamento (múltiplas por item)."""
        unidade = unidade_canonica(item.unidade)
        palavras = extrair_termos(item.descricao, max_termos=6)
        chaves: list[str] = []

        # 1. NCM exato (alta confiança)
        if item.ncm and len(item.ncm) >= 4:
            chaves.append(f"ncm:{item.ncm}:{unidade}")

        # 2. NCM categoria + palavras (média confiança)
        if item.ncm and len(item.ncm) >= 4 and len(palavras) >= 2:
            ncm4 = item.ncm[:4]
            desc_part = " ".join(palavras[:4])
            chaves.append(f"ncm4:{ncm4}:{desc_part}:{unidade}")

        # 3. Lexical puro (baixa confiança)
        if len(palavras) >= 2:
            desc_part = " ".join(palavras[:4])
            chaves.append(f"desc:{desc_part}:{unidade}")

        return chaves

    def gerar_chave(self, item: ObservedItem) -> str:
        """Compatibilidade: retorna a melhor chave (mais específica)."""
        chaves = self.gerar_chaves(item)
        return chaves[0] if chaves else ""
