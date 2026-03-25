"""
Download e extração de texto de PDFs com avaliação de qualidade.
"""

from __future__ import annotations

import io
import logging
import re

import requests
from pdfminer.high_level import extract_text

from edital_analysis.constants import TERMOS_JURIDICOS
from edital_analysis.types import ArquivoRanqueado, QualidadeExtracao

log = logging.getLogger(__name__)


def baixar_pdf(session: requests.Session, url: str) -> bytes | None:
    """
    Baixa PDF validando magic bytes (%PDF).
    Timeout: 5s connect, 60s read (PDFs grandes).
    """
    try:
        resp = session.get(url, timeout=(5, 60))
        resp.raise_for_status()
        content = resp.content
        if content[:4] != b"%PDF":
            log.debug("Não é PDF (magic bytes): %s", url)
            return None
        return content
    except requests.RequestException as exc:
        log.warning("Erro ao baixar PDF %s — %s", url, exc)
        return None


def extrair_texto(pdf_bytes: bytes) -> str:
    """Extrai texto de bytes de PDF via pdfminer."""
    try:
        return extract_text(io.BytesIO(pdf_bytes))
    except Exception as exc:
        log.warning("Erro ao extrair texto — %s", exc)
        return ""


def baixar_melhor_pdf(
    session: requests.Session,
    ranqueados: list[ArquivoRanqueado],
) -> tuple[bytes | None, ArquivoRanqueado | None]:
    """
    Tenta baixar PDFs em ordem de ranking até encontrar um válido.
    Retorna (bytes, arquivo_escolhido) ou (None, None).
    """
    for arq in ranqueados:
        pdf_bytes = baixar_pdf(session, arq.url)
        if pdf_bytes:
            return pdf_bytes, arq
    return None, None


def avaliar_qualidade(texto: str) -> QualidadeExtracao:
    """
    Avalia qualidade do texto extraído do PDF.

    Score 0.0-1.0 baseado em:
    - Tamanho do texto (>5000 chars = bom)
    - Proporção de caracteres alfabéticos (>70% = bom)
    - Presença de termos jurídicos típicos
    - Baixa fragmentação (poucos blocos <3 palavras)
    """
    if not texto:
        return QualidadeExtracao(score=0.0, faixa="ruim", motivos=["texto vazio"])

    motivos: list[str] = []
    pontos = 0.0

    # Tamanho (0-25pts)
    tam = len(texto)
    if tam >= 10000:
        pontos += 25
        motivos.append("texto longo (bom)")
    elif tam >= 5000:
        pontos += 20
        motivos.append("texto suficiente")
    elif tam >= 1000:
        pontos += 10
        motivos.append("texto curto")
    else:
        motivos.append("texto muito curto")

    # Proporção alfabética (0-25pts)
    if tam > 0:
        alfa = sum(1 for c in texto if c.isalpha())
        ratio = alfa / tam
        if ratio >= 0.7:
            pontos += 25
            motivos.append("boa proporção de texto")
        elif ratio >= 0.5:
            pontos += 15
            motivos.append("proporção aceitável")
        else:
            pontos += 5
            motivos.append("muitos caracteres não-textuais")

    # Termos jurídicos (0-25pts)
    texto_lower = texto.lower()
    termos_encontrados = sum(1 for t in TERMOS_JURIDICOS if t in texto_lower)
    ratio_termos = min(termos_encontrados / 10, 1.0)
    pontos += 25 * ratio_termos
    if ratio_termos >= 0.5:
        motivos.append(f"{termos_encontrados} termos jurídicos encontrados")
    else:
        motivos.append("poucos termos jurídicos")

    # Fragmentação (0-25pts) — blocos muito curtos indicam PDF mal extraído
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    if linhas:
        curtas = sum(1 for l in linhas if len(l.split()) < 3)
        ratio_curtas = curtas / len(linhas)
        if ratio_curtas < 0.3:
            pontos += 25
            motivos.append("baixa fragmentação")
        elif ratio_curtas < 0.5:
            pontos += 15
            motivos.append("fragmentação moderada")
        else:
            pontos += 5
            motivos.append("alta fragmentação")

    score = round(pontos / 100, 2)
    faixa = "boa" if score >= 0.7 else "regular" if score >= 0.4 else "ruim"

    return QualidadeExtracao(score=score, faixa=faixa, motivos=motivos)


def contar_paginas(texto: str) -> int:
    """Aproxima páginas contando form feeds do pdfminer."""
    return texto.count("\f") + 1
