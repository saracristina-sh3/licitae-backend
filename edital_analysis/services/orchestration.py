"""
Orquestração do pipeline de análise de editais v2.
Coordena busca, extração, análise, scoring e persistência.
"""

from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config
from edital_analysis.constants import LIMITE_TEXTO_BANCO
from edital_analysis.services.confidence import calcular_score_confianca
from edital_analysis.services.file_selection import ranquear_arquivos
from edital_analysis.services.pdf_extraction import (
    avaliar_qualidade,
    baixar_melhor_pdf,
    contar_paginas,
    extrair_texto,
)
from edital_analysis.services.persistence import (
    buscar_arquivos_pncp,
    buscar_licitacoes_pendentes,
    extrair_cnpj_ano_seq,
    gravar_analise,
    ja_analisada,
)
from edital_analysis.services.prazo_extraction import extrair_prazos
from edital_analysis.services.regex_extraction import (
    extrair_documentos,
    extrair_qualificacao,
    extrair_requisitos,
    extrair_riscos,
)
from edital_analysis.services.risk_scoring import calcular_score_risco
from edital_analysis.services.text_preprocessing import preprocessar
from edital_analysis.types import ResultadoAnalise

log = logging.getLogger(__name__)


def _criar_session() -> requests.Session:
    """Sessão HTTP com retry automático."""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "LicitacoesSoftware/2.0"})
    return session


SESSION = _criar_session()


def analisar_licitacao(
    client,
    licitacao_id: str,
    cnpj: str,
    ano: int,
    seq: int,
) -> ResultadoAnalise | None:
    """
    Pipeline completo de análise v2:

    1. Verifica cache
    2. Busca e ranqueia arquivos do PNCP
    3. Baixa melhor PDF
    4. Extrai texto + avalia qualidade
    5. Pré-processa texto
    6. Extrai achados estruturados (docs, req, riscos, qualif, prazos)
    7. Calcula score de risco
    8. Calcula score de confiança
    9. Grava tudo (novos + legados)
    """
    t0 = time.time()

    # 1. Cache
    if ja_analisada(client, licitacao_id):
        log.debug("[%s] Já analisada, pulando", licitacao_id[:8])
        return None

    # 2. Busca e ranqueia arquivos
    t1 = time.time()
    arquivos_raw = buscar_arquivos_pncp(SESSION, Config.PNCP_COMPRAS_URL, cnpj, ano, seq)
    if not arquivos_raw:
        log.warning("[%s] Sem arquivos no PNCP", licitacao_id[:8])
        return None

    ranqueados = ranquear_arquivos(arquivos_raw)
    t_busca = time.time() - t1

    # 3. Baixa melhor PDF
    t2 = time.time()
    pdf_bytes, arquivo_escolhido = baixar_melhor_pdf(SESSION, ranqueados)
    t_download = time.time() - t2

    if not pdf_bytes:
        log.warning("[%s] Nenhum PDF baixável (%d testados)", licitacao_id[:8], len(ranqueados))
        return None

    # 4. Extrai texto + avalia qualidade
    t3 = time.time()
    texto_raw = extrair_texto(pdf_bytes)
    t_extracao = time.time() - t3

    if not texto_raw or len(texto_raw) < 100:
        log.warning("[%s] Texto muito curto (%d chars)", licitacao_id[:8], len(texto_raw or ""))
        return None

    qualidade = avaliar_qualidade(texto_raw)
    paginas = contar_paginas(texto_raw)

    # 5. Pré-processa
    texto = preprocessar(texto_raw)

    # 6. Extrai achados estruturados
    t4 = time.time()
    documentos = extrair_documentos(texto)
    requisitos = extrair_requisitos(texto)
    riscos = extrair_riscos(texto)
    qualificacao = extrair_qualificacao(texto)
    prazos = extrair_prazos(texto)
    t_analise = time.time() - t4

    # 7. Score de risco
    score_risco = calcular_score_risco(
        riscos=riscos,
        prazos=prazos,
        total_documentos=len(documentos),
        total_requisitos=len(requisitos),
    )

    # 8. Score de confiança
    score_confianca = calcular_score_confianca(
        qualidade=qualidade,
        arquivo=arquivo_escolhido,
        documentos=documentos,
        requisitos=requisitos,
        riscos=riscos,
        qualificacao=qualificacao,
        prazos=prazos,
        texto=texto,
    )

    tempo_ms = int((time.time() - t0) * 1000)

    # Trunca texto se necessário
    if len(texto_raw) > LIMITE_TEXTO_BANCO:
        log.info("[%s] Texto truncado de %d para %d chars", licitacao_id[:8], len(texto_raw), LIMITE_TEXTO_BANCO)

    # 9. Monta resultado
    resultado = ResultadoAnalise(
        licitacao_id=licitacao_id,
        documentos=documentos,
        requisitos=requisitos,
        riscos=riscos,
        qualificacao=qualificacao,
        prazos=prazos,
        confianca=score_confianca,
        risco=score_risco,
        qualidade_extracao=qualidade,
        arquivo=arquivo_escolhido,
        paginas=paginas,
        url_documento=arquivo_escolhido.url if arquivo_escolhido else "",
        texto_extraido=texto_raw[:LIMITE_TEXTO_BANCO],
        tempo_ms=tempo_ms,
    )

    # 10. Grava
    gravado = gravar_analise(client, resultado)

    if gravado:
        log.info(
            "[%s] Análise v2: %d docs, %d req, %d riscos, %d qualif, %d prazos | "
            "Risco=%s (%.0f) | Conf=%s (%.0f) | Qualidade=%s | %dms "
            "(busca=%.0fms download=%.0fms extracao=%.0fms analise=%.0fms)",
            licitacao_id[:8],
            len(documentos), len(requisitos), len(riscos), len(qualificacao), len(prazos),
            score_risco.nivel, score_risco.score,
            score_confianca.faixa, score_confianca.score,
            qualidade.faixa,
            tempo_ms,
            t_busca * 1000, t_download * 1000, t_extracao * 1000, t_analise * 1000,
        )

    return resultado


def analisar_licitacoes_pendentes(
    limite: int = 10,
    db_client=None,
) -> dict[str, int]:
    """Processa licitações pendentes. Chamado pelo cron."""
    from db import get_client

    client = db_client or get_client()
    log.info("=" * 50)
    log.info("ANÁLISE DE EDITAIS v2")
    log.info("=" * 50)

    pendentes = buscar_licitacoes_pendentes(client, limite)

    if not pendentes:
        log.info("Nenhuma licitação pendente para análise")
        return {"analisadas": 0, "erros": 0, "sem_pdf": 0}

    log.info("Analisando %d edital(is)...", len(pendentes))

    analisadas = 0
    erros = 0
    sem_pdf = 0

    for lic in pendentes:
        licitacao_id = lic["id"]
        dados = extrair_cnpj_ano_seq(lic)

        if not dados:
            log.warning("[%s] Sem cnpj/ano/seq e URL fora do padrão", licitacao_id[:8])
            erros += 1
            continue

        cnpj, ano, seq = dados
        log.info("[%s] Processando (cnpj=%s, ano=%d, seq=%d)", licitacao_id[:8], cnpj, ano, seq)

        try:
            resultado = analisar_licitacao(client, licitacao_id, cnpj, ano, seq)
            if resultado:
                analisadas += 1
            else:
                sem_pdf += 1
        except Exception as e:
            log.error("[%s] Erro: %s", licitacao_id[:8], e, exc_info=True)
            erros += 1

    log.info("Concluído: %d analisadas, %d sem PDF, %d erros", analisadas, sem_pdf, erros)
    return {"analisadas": analisadas, "erros": erros, "sem_pdf": sem_pdf}
