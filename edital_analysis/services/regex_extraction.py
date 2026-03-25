"""
Extração estruturada por regex com taxonomia e confiança.
Transforma matches de regex em achados estruturados com código, label e score.
"""

from __future__ import annotations

import re

from edital_analysis.constants import (
    RE_REQUISITOS_TECNICOS,
    TAXONOMIA_DOCUMENTOS,
    TAXONOMIA_QUALIFICACAO,
    TAXONOMIA_RISCOS,
)
from edital_analysis.types import AchadoEstruturado


def _confianca_por_tamanho(trecho: str) -> float:
    """
    Estima confiança do achado pelo tamanho do trecho.
    Trechos muito curtos são menos confiáveis (possível falso positivo).
    """
    n = len(trecho)
    if n >= 50:
        return 0.9
    if n >= 30:
        return 0.8
    if n >= 15:
        return 0.7
    return 0.5


def extrair_documentos(texto: str, max_resultados: int = 20) -> list[AchadoEstruturado]:
    """
    Extrai documentos exigidos usando taxonomia.
    Cada match é classificado com código e label.
    """
    achados: list[AchadoEstruturado] = []
    vistos: set[str] = set()

    for codigo, (label, padroes) in TAXONOMIA_DOCUMENTOS.items():
        for padrao in padroes:
            for match in padrao.finditer(texto):
                trecho = re.sub(r"\s+", " ", match.group(0).strip())[:200]

                if len(trecho) > 10 and trecho not in vistos:
                    vistos.add(trecho)
                    achados.append(AchadoEstruturado(
                        codigo=codigo,
                        label=label,
                        trecho=trecho,
                        confianca=_confianca_por_tamanho(trecho),
                    ))

                    if len(achados) >= max_resultados:
                        return achados

    return achados


def extrair_requisitos(texto: str, max_resultados: int = 15) -> list[AchadoEstruturado]:
    """
    Extrai requisitos técnicos do texto.
    Não tem taxonomia fixa — cada match é um requisito genérico.
    """
    achados: list[AchadoEstruturado] = []
    vistos: set[str] = set()

    for padrao in RE_REQUISITOS_TECNICOS:
        for match in padrao.finditer(texto):
            trecho = re.sub(r"\s+", " ", match.group(0).strip())[:200]

            if len(trecho) > 10 and trecho not in vistos:
                vistos.add(trecho)
                achados.append(AchadoEstruturado(
                    codigo="REQ_TECNICO",
                    label="Requisito técnico",
                    trecho=trecho,
                    confianca=_confianca_por_tamanho(trecho),
                ))

                if len(achados) >= max_resultados:
                    return achados

    return achados


def extrair_riscos(texto: str, max_resultados: int = 15) -> list[AchadoEstruturado]:
    """Extrai cláusulas de risco usando taxonomia com código e peso."""
    achados: list[AchadoEstruturado] = []
    vistos: set[str] = set()

    for codigo, (label, padroes, _peso) in TAXONOMIA_RISCOS.items():
        for padrao in padroes:
            for match in padrao.finditer(texto):
                trecho = re.sub(r"\s+", " ", match.group(0).strip())[:200]

                if len(trecho) > 10 and trecho not in vistos:
                    vistos.add(trecho)
                    achados.append(AchadoEstruturado(
                        codigo=codigo,
                        label=label,
                        trecho=trecho,
                        confianca=_confianca_por_tamanho(trecho),
                    ))

                    if len(achados) >= max_resultados:
                        return achados

    return achados


def extrair_qualificacao(texto: str, max_resultados: int = 15) -> list[AchadoEstruturado]:
    """Extrai requisitos de qualificação/habilitação usando taxonomia."""
    achados: list[AchadoEstruturado] = []
    vistos: set[str] = set()

    for codigo, (label, padroes) in TAXONOMIA_QUALIFICACAO.items():
        for padrao in padroes:
            for match in padrao.finditer(texto):
                trecho = re.sub(r"\s+", " ", match.group(0).strip())[:200]

                if len(trecho) > 10 and trecho not in vistos:
                    vistos.add(trecho)
                    achados.append(AchadoEstruturado(
                        codigo=codigo,
                        label=label,
                        trecho=trecho,
                        confianca=_confianca_por_tamanho(trecho),
                    ))

                    if len(achados) >= max_resultados:
                        return achados

    return achados
