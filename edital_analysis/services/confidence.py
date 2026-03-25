"""
Score de confiança da análise do edital.
Indica quão confiável é o resultado gerado.
"""

from __future__ import annotations

from edital_analysis.constants import (
    FAIXA_CONFIANCA_ALTA,
    FAIXA_CONFIANCA_MEDIA,
    PESO_CONFIANCA_ARQUIVO,
    PESO_CONFIANCA_COBERTURA,
    PESO_CONFIANCA_QUALIDADE_EXTRACAO,
    PESO_CONFIANCA_TERMOS_TIPICOS,
    PESO_CONFIANCA_TEXTO_UTIL,
    TERMOS_JURIDICOS,
)
from edital_analysis.types import (
    AchadoEstruturado,
    ArquivoRanqueado,
    PrazoClassificado,
    QualidadeExtracao,
    ScoreConfianca,
)


def calcular_score_confianca(
    qualidade: QualidadeExtracao,
    arquivo: ArquivoRanqueado | None,
    documentos: list[AchadoEstruturado],
    requisitos: list[AchadoEstruturado],
    riscos: list[AchadoEstruturado],
    qualificacao: list[AchadoEstruturado],
    prazos: list[PrazoClassificado],
    texto: str,
) -> ScoreConfianca:
    """
    Score de confiança 0-100 com fatores explicáveis.

    Fatores:
    - Qualidade da extração: 30pts
    - Score do arquivo escolhido: 20pts
    - Cobertura de categorias: 20pts
    - Tamanho útil do texto: 15pts
    - Presença de termos típicos: 15pts
    """
    fatores: dict[str, float] = {}

    # 1. Qualidade da extração (0-30pts)
    f_qualidade = round(qualidade.score * PESO_CONFIANCA_QUALIDADE_EXTRACAO, 1)
    fatores["qualidade_extracao"] = f_qualidade

    # 2. Arquivo escolhido (0-20pts)
    if arquivo:
        # Score do arquivo normalizado para 0-1 (max possível ~80)
        ratio_arquivo = min(arquivo.score / 80, 1.0)
        f_arquivo = round(ratio_arquivo * PESO_CONFIANCA_ARQUIVO, 1)
    else:
        f_arquivo = 0.0
    fatores["arquivo_escolhido"] = f_arquivo

    # 3. Cobertura de categorias (0-20pts)
    # 5 categorias possíveis: docs, req, riscos, qualif, prazos
    categorias_com_dados = sum([
        len(documentos) > 0,
        len(requisitos) > 0,
        len(riscos) > 0,
        len(qualificacao) > 0,
        len(prazos) > 0,
    ])
    f_cobertura = round((categorias_com_dados / 5) * PESO_CONFIANCA_COBERTURA, 1)
    fatores["cobertura_categorias"] = f_cobertura

    # 4. Tamanho útil do texto (0-15pts)
    tam = len(texto)
    if tam >= 10000:
        ratio_texto = 1.0
    elif tam >= 5000:
        ratio_texto = 0.8
    elif tam >= 2000:
        ratio_texto = 0.5
    else:
        ratio_texto = max(0.1, tam / 2000)
    f_texto = round(ratio_texto * PESO_CONFIANCA_TEXTO_UTIL, 1)
    fatores["texto_util"] = f_texto

    # 5. Presença de termos típicos (0-15pts)
    texto_lower = texto.lower()
    termos_encontrados = sum(1 for t in TERMOS_JURIDICOS if t in texto_lower)
    ratio_termos = min(termos_encontrados / 10, 1.0)
    f_termos = round(ratio_termos * PESO_CONFIANCA_TERMOS_TIPICOS, 1)
    fatores["termos_tipicos"] = f_termos

    score = round(sum(fatores.values()), 1)

    if score >= FAIXA_CONFIANCA_ALTA:
        faixa = "alta"
    elif score >= FAIXA_CONFIANCA_MEDIA:
        faixa = "media"
    else:
        faixa = "baixa"

    return ScoreConfianca(score=score, faixa=faixa, fatores=fatores)
