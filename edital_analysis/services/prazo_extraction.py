"""
Extração e classificação de prazos do edital.
Identifica valor, unidade e tipo (vigência, execução, implantação, etc.).
"""

from __future__ import annotations

import re

from edital_analysis.constants import RE_PRAZOS, TIPOS_PRAZO
from edital_analysis.types import PrazoClassificado


def _classificar_tipo(contexto: str) -> tuple[str, float]:
    """
    Classifica o tipo de prazo pelo contexto textual.
    Retorna (tipo, confiança).
    """
    contexto_lower = contexto.lower()

    for tipo, termos in TIPOS_PRAZO.items():
        for termo in termos:
            if termo in contexto_lower:
                return tipo, 0.85

    return "outros", 0.4


def extrair_prazos(texto: str, max_resultados: int = 15) -> list[PrazoClassificado]:
    """
    Extrai prazos com classificação de tipo.

    Cada prazo retorna:
    - valor numérico
    - unidade normalizada (dia, mes, ano, hora)
    - tipo classificado (vigencia, execucao, implantacao, etc.)
    - contexto textual
    - confiança
    """
    prazos: list[PrazoClassificado] = []
    vistos: set[str] = set()

    for padrao in RE_PRAZOS:
        for match in padrao.finditer(texto):
            grupos = match.groups()
            if len(grupos) < 2:
                continue

            valor_str, unidade_raw = grupos[0], grupos[1]

            try:
                valor = int(valor_str)
            except (ValueError, TypeError):
                continue

            # Normaliza unidade
            unidade = unidade_raw.lower().rstrip("s")
            if unidade.startswith("mese"):
                unidade = "mes"

            # Deduplicação
            chave = f"{valor}_{unidade}"
            if chave in vistos:
                continue
            vistos.add(chave)

            # Contexto expandido (250 chars ao redor do match)
            start = max(0, match.start() - 50)
            end = min(len(texto), match.end() + 100)
            contexto_amplo = re.sub(r"\s+", " ", texto[start:end].strip())[:250]

            # Contexto curto (do match em si)
            contexto = re.sub(r"\s+", " ", match.group(0).strip())[:150]

            # Classificar tipo usando contexto amplo
            tipo, confianca = _classificar_tipo(contexto_amplo)

            prazos.append(PrazoClassificado(
                valor=valor,
                unidade=unidade,
                tipo=tipo,
                contexto=contexto,
                confianca=confianca,
            ))

            if len(prazos) >= max_resultados:
                return prazos

    return prazos
