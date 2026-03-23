"""
Funções utilitárias compartilhadas entre os módulos de busca.
"""

from __future__ import annotations

import unicodedata


# ── Tabela FPM ↔ População ──────────────────────────────────

FAIXAS_FPM = [
    (10188, 0.6), (13584, 0.8), (16980, 1.0), (23772, 1.2),
    (30564, 1.4), (37356, 1.6), (44148, 1.8), (50940, 2.0),
    (61128, 2.2), (71316, 2.4), (81504, 2.6), (91692, 2.8),
    (101880, 3.0), (115464, 3.2), (129048, 3.4), (142632, 3.6),
    (156216, 3.8),
]


def fpm_coeficiente(populacao: int) -> float:
    """Retorna o coeficiente FPM baseado na população."""
    for limite, coef in FAIXAS_FPM:
        if populacao <= limite:
            return coef
    return 4.0


def fpm_para_populacao(fpm: float) -> int:
    """Converte coeficiente FPM para população máxima correspondente."""
    for limite, coef in FAIXAS_FPM:
        if fpm <= coef:
            return limite
    return 999999


# ── Normalização de texto ───────────────────────────────────

def normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def match_palavras_chave(texto: str, palavras_chave: list[str]) -> list[str]:
    """Retorna quais palavras-chave foram encontradas no texto."""
    texto_norm = normalizar(texto)
    return [p for p in palavras_chave if normalizar(p) in texto_norm]


# ── Termos padrão (fonte única de verdade) ──────────────────

TERMOS_ALTA = [
    "permissão de uso", "licença de uso", "cessão de uso",
    "locação de software", "sistema integrado de gestão",
]

TERMOS_MEDIA = [
    "software", "sistema de gestão", "solução tecnológica",
]

TERMOS_ME_EPP = [
    "exclusivo para microempresa", "exclusivo para me",
    "exclusivo me/epp", "exclusivo me e epp",
    "participação exclusiva", "cota reservada", "lei complementar 123",
]


# ── Classificação ───────────────────────────────────────────

def classificar_relevancia(
    matches: list[str],
    objeto: str,
    termos_alta: list[str] | None = None,
    termos_media: list[str] | None = None,
) -> str:
    """Classifica relevância como ALTA, MEDIA ou BAIXA."""
    termos_alta = termos_alta or TERMOS_ALTA
    termos_media = termos_media or TERMOS_MEDIA
    texto_norm = normalizar(objeto)

    for t in termos_alta:
        if normalizar(t) in texto_norm:
            return "ALTA"
    for t in termos_media:
        if normalizar(t) in texto_norm:
            return "MEDIA"
    return "BAIXA"


def detectar_me_epp(texto: str, termos: list[str] | None = None) -> bool:
    """Detecta se a licitação é exclusiva para ME/EPP."""
    termos = termos or TERMOS_ME_EPP
    texto_norm = normalizar(texto)
    return any(normalizar(t) in texto_norm for t in termos)
