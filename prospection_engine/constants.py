"""Constantes centralizadas do motor de prospecção v1."""

from __future__ import annotations

VERSAO_ALGORITMO = "v1"

# ── Modalidades PNCP ────────────────────────────────────────

MODALIDADE_NOMES: dict[int, str] = {
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência Eletrônica",
    5: "Concorrência Presencial",
    6: "Pregão Eletrônico",
    7: "Pregão Presencial",
    8: "Dispensa de Licitação",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
}

# ── Termos de relevância (migrados de utils.py) ─────────────

TERMOS_ALTA: list[str] = [
    "permissão de uso", "licença de uso", "cessão de uso",
    "locação de software", "sistema integrado de gestão",
    "hospedagem de e-mails", "e-mails institucionais",
]

TERMOS_MEDIA: list[str] = [
    "software", "sistema de gestão", "solução tecnológica",
    "email", "e-mail",
]

TERMOS_ME_EPP: list[str] = [
    "exclusivo para microempresa", "exclusivo para me",
    "exclusivo me/epp", "exclusivo me e epp",
    "participação exclusiva", "cota reservada", "lei complementar 123",
]

# ── Pesos do scoring (total = 100) ──────────────────────────

PESO_MATCH_OBJETO = 30        # match no objetoCompra
PESO_MATCH_COMPLEMENTAR = 15  # match no informacaoComplementar
PESO_TERMOS_ALTA = 25         # presença de termos de alta relevância
PESO_TERMOS_MEDIA = 10        # presença de termos de média
PESO_VALOR_ESTIMADO = 10      # valor dentro da faixa esperada
PESO_ME_EPP = 10              # licitação exclusiva ME/EPP (bônus)

# ── Faixas de score → relevância textual ─────────────────────

FAIXA_ALTA = 65   # score >= 65 → "ALTA"
FAIXA_MEDIA = 35  # score >= 35 → "MEDIA"
                   # score < 35  → "BAIXA"

# ── Urgência baseada em dias até encerramento ────────────────

URGENCIA_CRITICA_DIAS = 3
URGENCIA_PROXIMA_DIAS = 7

# ── Faixa de valor esperado para licitações de software ──────

VALOR_MIN_ESPERADO: float = 5_000.0
VALOR_MAX_ESPERADO: float = 2_000_000.0
