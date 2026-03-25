"""
Orquestração do pipeline de comparativo de mercado v2.
"""

from __future__ import annotations

import logging
import statistics
import time

from market_comparison.constants import (
    IDS_CONCORRENTES,
    LIMITE_ITENS_POR_PLATAFORMA,
    RAZAO_MAXIMA_ESCALA,
)
from market_comparison.services.comparability import calcular_score
from market_comparison.services.grouping import agrupar_itens, montar_grupo_comparavel
from market_comparison.services.persistence import (
    buscar_itens_plataforma,
    buscar_ufs_com_dados,
    gravar_itens_e_precos,
    gravar_plataformas,
    limpar_por_uf,
)
from market_comparison.services.summary import calcular_resumo_plataformas
from market_comparison.types import ComparableGroup, ObservedItem, PlatformGroupStats

# Reutiliza estatísticas do pricing_reference
from pricing_reference.services.estatistica import calcular_resumo, remover_outliers_iqr

log = logging.getLogger(__name__)


def _valores_comparaveis(medias: list[float]) -> bool:
    """Verifica se as médias entre plataformas estão na mesma escala."""
    if len(medias) < 2:
        return False
    mn, mx = min(medias), max(medias)
    return mn > 0 and mx / mn <= RAZAO_MAXIMA_ESCALA


def calcular_comparativo(client, uf: str | None = None) -> dict:
    """
    Pipeline completo do comparativo v2:

    1. Busca itens por plataforma
    2. Agrupa por chave (NCM/descrição + unidade)
    3. Filtra grupos comparáveis (2+ plataformas, mesma escala)
    4. Calcula estatísticas por plataforma/grupo (com IQR)
    5. Calcula score de comparabilidade
    6. Calcula resumo com vitórias ponderadas
    7. Grava tudo em lote
    """
    sufixo = f" (UF={uf})" if uf else " (geral)"
    t0 = time.time()

    # 1. Busca
    t1 = time.time()
    todos_itens: list[dict] = []
    for plat_id in IDS_CONCORRENTES:
        itens = buscar_itens_plataforma(client, plat_id, uf, LIMITE_ITENS_POR_PLATAFORMA)
        todos_itens.extend(itens)
        log.debug("  Plat %d: %d itens", plat_id, len(itens))
    t_busca = time.time() - t1

    if not todos_itens:
        log.info("Sem itens%s", sufixo)
        return {"itens_comparaveis": 0, "plataformas": 0, "descartados": 0}

    # 2. Agrupa
    t2 = time.time()
    grupos_raw = agrupar_itens(todos_itens)
    t_agrupamento = time.time() - t2

    # 3. Filtra e calcula
    t3 = time.time()
    grupos_comparaveis: list[ComparableGroup] = []
    descartados = 0

    for chave, itens in grupos_raw.items():
        grupo = montar_grupo_comparavel(chave, itens)
        if not grupo:
            descartados += 1
            continue

        # Agrupar por plataforma
        por_plat: dict[str, list[ObservedItem]] = {}
        for item in itens:
            por_plat.setdefault(item.plataforma_nome, []).append(item)

        # Verificar escala
        medias = []
        for plat_itens in por_plat.values():
            vals = [i.valor for i in plat_itens]
            if vals:
                medias.append(statistics.mean(vals))

        if not _valores_comparaveis(medias):
            descartados += 1
            continue

        # Calcular stats por plataforma (com IQR)
        for nome, plat_itens in por_plat.items():
            valores = [i.valor for i in plat_itens]
            valores_limpos = remover_outliers_iqr(valores)
            if not valores_limpos:
                valores_limpos = valores

            resumo = calcular_resumo(valores_limpos)

            total_hom = sum(1 for i in plat_itens if i.fonte_preco == "homologado")
            total_est = len(plat_itens) - total_hom

            descontos = [i.desconto for i in plat_itens if i.desconto is not None]
            eco = round(statistics.mean(descontos), 2) if descontos else None

            fonte = "homologado" if total_hom > total_est else "estimado" if total_est > total_hom else "misto"

            grupo.stats_por_plataforma[nome] = PlatformGroupStats(
                plataforma_nome=nome,
                plataforma_id=plat_itens[0].plataforma_id,
                resumo=resumo,
                total_homologados=total_hom,
                total_estimados=total_est,
                fonte_predominante=fonte,
                economia_media=eco,
            )

        # Menor preço
        stats_ordenados = sorted(
            grupo.stats_por_plataforma.values(),
            key=lambda s: s.resumo["media"] if s.resumo["media"] is not None else float("inf"),
        )
        if stats_ordenados:
            grupo.menor_preco_plataforma = stats_ordenados[0].plataforma_nome

        # Score de comparabilidade
        grupo.score_comparabilidade, grupo.faixa_confiabilidade = calcular_score(
            chave, por_plat, grupo.taxa_consistencia_unidade,
        )

        grupos_comparaveis.append(grupo)

    t_calculo = time.time() - t3

    log.info(
        "Comparativo%s: %d comparáveis, %d descartados (de %d grupos) — "
        "busca=%.1fs agrup=%.1fs calc=%.1fs",
        sufixo, len(grupos_comparaveis), descartados, len(grupos_raw),
        t_busca, t_agrupamento, t_calculo,
    )

    if not grupos_comparaveis:
        return {"itens_comparaveis": 0, "plataformas": 0, "descartados": descartados}

    # 4. Resumo por plataforma
    resumos = calcular_resumo_plataformas(grupos_comparaveis)

    # 5. Grava
    t4 = time.time()
    limpar_por_uf(client, uf)
    gravar_plataformas(client, resumos, uf)
    gravar_itens_e_precos(client, grupos_comparaveis, uf)
    t_persist = time.time() - t4

    t_total = time.time() - t0

    # Log resumo
    for r in resumos[:4]:
        log.info(
            "  %s: %d vitórias (%.1f pond, %d alta conf) | ranking=%.1f | delta=%.1f%%",
            r.plataforma_nome[:20], r.vitorias_brutas,
            r.vitorias_ponderadas, r.vitorias_alta_confianca,
            r.ranking_medio, r.delta_medio_para_lider,
        )

    log.info("Total%s: %.1fs (persist=%.1fs)", sufixo, t_total, t_persist)

    return {
        "itens_comparaveis": len(grupos_comparaveis),
        "plataformas": len(resumos),
        "descartados": descartados,
    }


def executar_comparativo():
    """Calcula comparativo para todas as UFs + geral. Chamado pelo cron."""
    from db import get_client

    client = get_client()
    log.info("=" * 50)
    log.info("COMPARATIVO DE MERCADO v2")
    log.info("=" * 50)

    ufs = buscar_ufs_com_dados(client, IDS_CONCORRENTES)
    log.info("UFs com dados: %s", ", ".join(ufs) if ufs else "nenhuma")

    stats_geral = calcular_comparativo(client, uf=None)
    log.info("Geral: %s", stats_geral)

    for uf in ufs:
        stats = calcular_comparativo(client, uf=uf)
        if stats["itens_comparaveis"] > 0:
            log.info("%s: %s", uf, stats)

    log.info("Comparativo de mercado v2 concluído!")
