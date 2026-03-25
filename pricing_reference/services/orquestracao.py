"""
Orquestração do pipeline de preços de referência.
Coordena busca, cálculo, confiabilidade e persistência.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from pricing_reference.constants import (
    AMOSTRA_MINIMA,
    DESCONTO_MAXIMO,
    JANELA_MESES,
    METODO_OUTLIER,
    METODO_SIMILARIDADE,
    VERSAO_ALGORITMO,
)
from pricing_reference.services.confiabilidade import calcular_score
from pricing_reference.services.estatistica import (
    calcular_resumo,
    remover_outliers_iqr,
)
from pricing_reference.services.persistencia import (
    buscar_licitacoes_pendentes,
    gravar_detalhes_itens,
    gravar_detalhes_licitacoes,
    gravar_resumo,
    gravar_resumo_plataformas,
)
from pricing_reference.services.similaridade import (
    buscar_itens_similares,
    buscar_licitacoes_similares,
)
from pricing_reference.types import ResultadoSimilaridade

log = logging.getLogger(__name__)


def _data_limite() -> str:
    """Retorna data ISO de JANELA_MESES atrás."""
    return (datetime.utcnow() - timedelta(days=JANELA_MESES * 30)).isoformat()


def _calcular_recencia_media(similares: list[ResultadoSimilaridade]) -> float:
    """Calcula média de dias desde a publicação dos similares."""
    dias = []
    for s in similares:
        data_pub = s["registro"].get("data_publicacao")
        if data_pub:
            try:
                dt = datetime.fromisoformat(data_pub.replace("Z", "+00:00"))
                d = (datetime.now(dt.tzinfo) - dt).days if dt.tzinfo else (datetime.utcnow() - dt).days
                dias.append(d)
            except (ValueError, TypeError):
                pass
    return sum(dias) / len(dias) if dias else 365


def processar_licitacao(client, licitacao: dict) -> dict | None:
    """
    Pipeline completo de cálculo de preço de referência para uma licitação.

    Etapas:
    1. Busca licitações similares (com score e fonte)
    2. Busca itens similares (com score e fonte)
    3. Separa homologados vs estimados
    4. Calcula estatísticas por grupo (com IQR + resumo completo)
    5. Calcula score de confiabilidade
    6. Grava tudo

    Retorna o registro resumo ou None se sem dados.
    """
    lic_id = licitacao["id"]
    t0 = time.time()

    data_limite = _data_limite()

    # ── 1. Busca similares ──

    t1 = time.time()
    similares_lic = buscar_licitacoes_similares(client, licitacao, data_limite)
    t_busca_lic = time.time() - t1

    t2 = time.time()
    similares_itens = buscar_itens_similares(client, licitacao)
    t_busca_itens = time.time() - t2

    if not similares_lic and not similares_itens:
        log.debug("[%s] Sem similares encontrados (%.1fs)", lic_id[:8], time.time() - t0)
        return None

    # ── 2. Separar por fonte (licitações) ──

    valores_todos = [s["valor"] for s in similares_lic if s["valor"] > 0]
    valores_hom = [s["valor"] for s in similares_lic if s["fonte_preco"] == "homologado" and s["valor"] > 0]
    valores_est = [s["valor"] for s in similares_lic if s["fonte_preco"] == "estimado" and s["valor"] > 0]

    # ── 3. Remover outliers e calcular estatísticas ──

    valores_limpos = remover_outliers_iqr(valores_todos)
    resumo_geral = calcular_resumo(valores_limpos)
    resumo_hom = calcular_resumo(remover_outliers_iqr(valores_hom))
    resumo_est = calcular_resumo(remover_outliers_iqr(valores_est))

    # Fonte predominante
    if len(valores_hom) > len(valores_est):
        fonte_predominante = "homologado"
    elif len(valores_est) > len(valores_hom):
        fonte_predominante = "estimado"
    else:
        fonte_predominante = "misto"

    # ── 4. Itens similares ──

    valores_itens = [s["valor"] for s in similares_itens if s["valor"] > 0]
    itens_limpos = remover_outliers_iqr(valores_itens)
    resumo_itens = calcular_resumo(itens_limpos)

    # Desconto médio dos itens
    descontos = []
    for s in similares_itens:
        r = s["registro"].get("_resultado_usado")
        if r:
            d = r.get("percentual_desconto")
            if d is not None and 0 <= d <= DESCONTO_MAXIMO:
                descontos.append(float(d))
    desconto_medio = round(sum(descontos) / len(descontos), 2) if descontos else None

    # ── 5. Score de confiabilidade ──

    total_amostra = resumo_geral["total"] + resumo_itens["total"]
    cv = resumo_geral["coeficiente_variacao"] or resumo_itens["coeficiente_variacao"]
    pct_hom = len(valores_hom) / max(len(valores_todos), 1)
    recencia = _calcular_recencia_media(similares_lic + similares_itens)
    scores_sim = [s["score"] for s in similares_lic + similares_itens]
    score_sim_medio = sum(scores_sim) / len(scores_sim) if scores_sim else 0

    confiabilidade = calcular_score(
        total_amostra=total_amostra,
        cv=cv,
        pct_homologados=pct_hom,
        recencia_dias_media=recencia,
        score_similaridade_medio=score_sim_medio,
    )

    # ── 6. Montar registro e gravar ──

    registro = {
        "licitacao_id": lic_id,
        # Geral
        "total_similares": resumo_geral["total"],
        "valor_minimo": resumo_geral["minimo"],
        "valor_maximo": resumo_geral["maximo"],
        "valor_media": resumo_geral["media"],
        "valor_mediana": resumo_geral["mediana"],
        "valor_media_saneada": resumo_geral["media_saneada"],
        "coeficiente_variacao": resumo_geral["coeficiente_variacao"],
        "amostra_suficiente": resumo_geral["total"] >= AMOSTRA_MINIMA,
        "percentil_25": resumo_geral["percentil_25"],
        "percentil_75": resumo_geral["percentil_75"],
        # Homologados
        "valor_media_homologado": resumo_hom["media"],
        "valor_mediana_homologado": resumo_hom["mediana"],
        "valor_media_saneada_homologado": resumo_hom["media_saneada"],
        "cv_homologado": resumo_hom["coeficiente_variacao"],
        "total_homologados": resumo_hom["total"],
        # Estimados
        "valor_media_estimado": resumo_est["media"],
        "valor_mediana_estimado": resumo_est["mediana"],
        "cv_estimado": resumo_est["coeficiente_variacao"],
        "total_estimados": resumo_est["total"],
        "fonte_predominante": fonte_predominante,
        # Itens
        "total_itens_similares": resumo_itens["total"],
        "item_minimo_unitario": resumo_itens["minimo"],
        "item_maximo_unitario": resumo_itens["maximo"],
        "item_media_unitario": resumo_itens["media"],
        "item_mediana_unitario": resumo_itens["mediana"],
        "item_media_saneada": resumo_itens["media_saneada"],
        "item_desconto_medio": desconto_medio,
        "item_coeficiente_variacao": resumo_itens["coeficiente_variacao"],
        "item_percentil_25": resumo_itens["percentil_25"],
        "item_percentil_75": resumo_itens["percentil_75"],
        # Confiabilidade
        "score_confiabilidade": confiabilidade["score"],
        "faixa_confiabilidade": confiabilidade["faixa"],
        # Metadados
        "janela_meses": JANELA_MESES,
        "versao_algoritmo": VERSAO_ALGORITMO,
        "metodo_similaridade": METODO_SIMILARIDADE,
        "metodo_outlier": METODO_OUTLIER,
        "calculado_em": datetime.utcnow().isoformat(),
    }

    t3 = time.time()
    ref_id = gravar_resumo(client, registro)
    if ref_id is None:
        return None

    n_lic = gravar_detalhes_licitacoes(client, ref_id, similares_lic)
    n_itens = gravar_detalhes_itens(client, ref_id, similares_itens)
    n_plat = gravar_resumo_plataformas(client, ref_id, similares_itens)
    t_persistencia = time.time() - t3

    t_total = time.time() - t0

    log.info(
        "[%s] Preços v2: %d lic (%d hom/%d est), %d itens, %d plat | "
        "CV=%.1f%% | Conf=%.0f (%s) | %.1fs (busca_lic=%.1fs busca_itens=%.1fs persist=%.1fs)",
        lic_id[:8],
        resumo_geral["total"], resumo_hom["total"], resumo_est["total"],
        n_itens, n_plat,
        resumo_geral["coeficiente_variacao"] or 0,
        confiabilidade["score"], confiabilidade["faixa"],
        t_total, t_busca_lic, t_busca_itens, t_persistencia,
    )

    return registro


def calcular_precos_pendentes(limite: int = 50) -> dict[str, int]:
    """
    Processa licitações abertas sem preço de referência calculado.
    Chamado pelo cron diariamente.
    """
    from db import get_client

    client = get_client()
    log.info("=" * 50)
    log.info("PREÇOS DE REFERÊNCIA v2")
    log.info("=" * 50)

    pendentes = buscar_licitacoes_pendentes(client, limite)

    if not pendentes:
        log.info("Nenhuma licitação pendente para cálculo de preços")
        return {"calculadas": 0, "erros": 0, "sem_dados": 0}

    log.info("Processando %d licitações...", len(pendentes))

    calculadas = 0
    erros = 0
    sem_dados = 0

    for lic in pendentes:
        try:
            resultado = processar_licitacao(client, lic)
            if resultado:
                calculadas += 1
            else:
                sem_dados += 1
        except Exception as e:
            log.error("[%s] Erro: %s", lic["id"][:8], e, exc_info=True)
            erros += 1

    log.info(
        "Concluído: %d calculadas, %d sem dados, %d erros",
        calculadas, sem_dados, erros,
    )
    return {"calculadas": calculadas, "erros": erros, "sem_dados": sem_dados}
