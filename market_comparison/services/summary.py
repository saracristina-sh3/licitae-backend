"""
Resumo consolidado por plataforma com vitórias ponderadas e ranking.
"""

from __future__ import annotations

import statistics

from market_comparison.types import ComparableGroup, PlatformGroupStats, PlatformSummary


def calcular_resumo_plataformas(
    grupos: list[ComparableGroup],
) -> list[PlatformSummary]:
    """
    Consolida métricas por plataforma a partir dos grupos comparáveis.

    Calcula:
    - vitórias brutas, ponderadas e alta confiança
    - ranking médio
    - delta médio para líder
    - proporções
    """
    # Acumular dados por plataforma
    acumulado: dict[str, dict] = {}

    for grupo in grupos:
        # Ordenar plataformas por valor médio
        stats_list = sorted(
            grupo.stats_por_plataforma.values(),
            key=lambda s: s.resumo["media"] if s.resumo["media"] is not None else float("inf"),
        )

        if not stats_list:
            continue

        menor_valor = stats_list[0].resumo["media"] if stats_list[0].resumo["media"] else 0
        vencedora = stats_list[0].plataforma_nome

        for rank, stats in enumerate(stats_list, 1):
            nome = stats.plataforma_nome
            acc = acumulado.setdefault(nome, {
                "id": stats.plataforma_id,
                "valores": [],
                "descontos": [],
                "cvs": [],
                "scores_comp": [],
                "rankings": [],
                "deltas": [],
                "vitorias_brutas": 0,
                "vitorias_ponderadas": 0.0,
                "vitorias_alta_confianca": 0,
                "total_homologados": 0,
                "total_estimados": 0,
                "total_grupos": 0,
                "grupos_alta": 0,
            })

            if stats.resumo["media"] is not None:
                acc["valores"].append(stats.resumo["media"])
            if stats.economia_media is not None:
                acc["descontos"].append(stats.economia_media)
            if stats.resumo["coeficiente_variacao"] is not None:
                acc["cvs"].append(stats.resumo["coeficiente_variacao"])

            acc["scores_comp"].append(grupo.score_comparabilidade)
            acc["rankings"].append(rank)
            acc["total_homologados"] += stats.total_homologados
            acc["total_estimados"] += stats.total_estimados
            acc["total_grupos"] += 1

            if grupo.faixa_confiabilidade == "alta":
                acc["grupos_alta"] += 1

            # Delta para líder (capped em 500% para evitar outliers extremos)
            if menor_valor and menor_valor > 0 and stats.resumo["media"]:
                delta = ((stats.resumo["media"] - menor_valor) / menor_valor) * 100
                acc["deltas"].append(min(delta, 500.0))

            # Vitórias
            if nome == vencedora:
                acc["vitorias_brutas"] += 1
                acc["vitorias_ponderadas"] += grupo.score_comparabilidade / 100
                if grupo.faixa_confiabilidade == "alta":
                    acc["vitorias_alta_confianca"] += 1

    # Montar resumos
    resumos: list[PlatformSummary] = []
    for nome, acc in acumulado.items():
        total_obs = acc["total_homologados"] + acc["total_estimados"]

        resumos.append(PlatformSummary(
            plataforma_nome=nome,
            plataforma_id=acc["id"],
            valor_medio_unitario=round(statistics.mean(acc["valores"]), 2) if acc["valores"] else 0,
            mediana_unitario=round(statistics.median(acc["valores"]), 2) if acc["valores"] else 0,
            desconto_medio=round(statistics.mean(acc["descontos"]), 2) if acc["descontos"] else None,
            cv_medio=round(statistics.mean(acc["cvs"]), 2) if acc["cvs"] else None,
            total_itens=len(acc["valores"]),
            total_grupos_comparaveis=acc["total_grupos"],
            total_grupos_alta_confianca=acc["grupos_alta"],
            vitorias_brutas=acc["vitorias_brutas"],
            vitorias_ponderadas=round(acc["vitorias_ponderadas"], 2),
            vitorias_alta_confianca=acc["vitorias_alta_confianca"],
            proporcao_vitorias=round(acc["vitorias_brutas"] / acc["total_grupos"], 2) if acc["total_grupos"] else 0,
            proporcao_homologados=round(acc["total_homologados"] / total_obs, 2) if total_obs else 0,
            score_comparabilidade_medio=round(statistics.mean(acc["scores_comp"]), 2) if acc["scores_comp"] else 0,
            ranking_medio=round(statistics.mean(acc["rankings"]), 2) if acc["rankings"] else 0,
            delta_medio_para_lider=round(statistics.mean(acc["deltas"]), 2) if acc["deltas"] else 0,
        ))

    # Ordenar por vitórias ponderadas
    resumos.sort(key=lambda r: r.vitorias_ponderadas, reverse=True)
    return resumos
