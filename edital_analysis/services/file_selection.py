"""
Seleção inteligente do PDF correto para análise.
Ranqueia arquivos por probabilidade de ser o edital principal.
"""

from __future__ import annotations

import logging

from edital_analysis.constants import (
    SCORE_ARQUIVO_NAO_ANEXO,
    SCORE_ARQUIVO_NOME_EDITAL,
    SCORE_ARQUIVO_NOME_TERMO_REF,
    SCORE_ARQUIVO_TAMANHO,
    SCORE_ARQUIVO_TIPO_DOCUMENTO,
)
from edital_analysis.types import ArquivoRanqueado

log = logging.getLogger(__name__)


def _normalizar_nome(nome: str) -> str:
    return (nome or "").lower().strip()


def ranquear_arquivos(arquivos: list[dict]) -> list[ArquivoRanqueado]:
    """
    Ranqueia PDFs por probabilidade de ser o edital principal.

    Critérios e pesos:
    - Nome contém "edital": +30
    - Nome contém "termo de referência": +25
    - Tipo do documento (da API): +20
    - Tamanho estimado relevante: +15
    - Nome NÃO contém "anexo"/"aviso"/"extrato": +10

    Retorna lista ordenada por score decrescente.
    """
    ranqueados: list[ArquivoRanqueado] = []

    for arq in arquivos:
        url = arq.get("url", "")
        if not url:
            continue

        titulo = arq.get("titulo") or arq.get("title") or ""
        tipo_doc = arq.get("tipoDocumentoNome") or arq.get("tipo") or ""
        nome = _normalizar_nome(titulo)
        tipo_lower = _normalizar_nome(tipo_doc)

        score = 0.0
        motivos: list[str] = []

        # Nome contém "edital"
        if "edital" in nome:
            score += SCORE_ARQUIVO_NOME_EDITAL
            motivos.append("nome contém 'edital'")

        # Nome contém "termo de referência"
        if "termo de refer" in nome or "termo de referencia" in nome:
            score += SCORE_ARQUIVO_NOME_TERMO_REF
            motivos.append("nome contém 'termo de referência'")

        # Tipo do documento
        if tipo_lower and ("edital" in tipo_lower or "termo" in tipo_lower):
            score += SCORE_ARQUIVO_TIPO_DOCUMENTO
            motivos.append(f"tipo do documento: {tipo_doc}")

        # Tamanho — se o primeiro arquivo e sem critério melhor, dá um bônus
        # A API PNCP nem sempre retorna tamanho, então dá bônus genérico
        score += SCORE_ARQUIVO_TAMANHO * 0.5  # bônus base
        motivos.append("arquivo disponível")

        # Penaliza anexos, avisos, extratos
        termos_penalizados = {"anexo", "aviso", "extrato", "minuta", "ata", "errata"}
        if not any(t in nome for t in termos_penalizados):
            score += SCORE_ARQUIVO_NAO_ANEXO
            motivos.append("não é anexo/aviso/extrato")
        else:
            motivos.append("penalizado: nome sugere documento secundário")

        ranqueados.append(ArquivoRanqueado(
            url=url,
            titulo=titulo or url.split("/")[-1],
            score=round(score, 2),
            motivos=motivos,
        ))

    ranqueados.sort(key=lambda a: a.score, reverse=True)

    if ranqueados:
        log.debug(
            "Ranking de arquivos: %s",
            [(a.titulo[:30], a.score) for a in ranqueados[:3]],
        )

    return ranqueados
