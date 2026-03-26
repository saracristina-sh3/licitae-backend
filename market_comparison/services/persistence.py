"""
Persistência do comparativo de mercado — operações em lote.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime

from market_comparison.constants import METODO_AGRUPAMENTO, METODO_OUTLIER, VERSAO_ALGORITMO
from market_comparison.types import ComparableGroup, PlatformSummary

log = logging.getLogger(__name__)


def humanizar_chave(chave: str, descricao: str, ncm: str | None) -> str:
    """Converte chave técnica em descrição legível para o frontend."""
    if chave.startswith("ncm:"):
        # ncm:84713000:un → "NCM 8471.30 — Computador Desktop — Unidade"
        partes = chave.split(":")
        ncm_fmt = partes[1]
        if len(ncm_fmt) >= 6:
            ncm_fmt = f"{ncm_fmt[:4]}.{ncm_fmt[4:6]}"
        unidade = partes[2] if len(partes) > 2 else ""
        return f"NCM {ncm_fmt} — {descricao} — {unidade.upper()}"

    if chave.startswith("ncm4:"):
        # ncm4:8471:computador desktop memoria:un
        partes = chave.split(":")
        ncm4 = partes[1]
        palavras = partes[2] if len(partes) > 2 else ""
        unidade = partes[3] if len(partes) > 3 else ""
        return f"NCM {ncm4}.xx — {palavras} — {unidade.upper()}"

    if chave.startswith("desc:"):
        # desc:computador desktop memoria:un
        partes = chave.split(":")
        palavras = partes[1] if len(partes) > 1 else ""
        unidade = partes[2] if len(partes) > 2 else ""
        return f"{palavras} — {unidade.upper()}"

    return chave


def limpar_por_uf(client, uf: str | None) -> None:
    """Remove todos os dados do comparativo para uma UF."""
    if uf:
        client.table("comparativo_plataformas").delete().eq("uf", uf).execute()
        existing = client.table("comparativo_itens").select("id").eq("uf", uf).execute()
    else:
        client.table("comparativo_plataformas").delete().is_("uf", "null").execute()
        existing = client.table("comparativo_itens").select("id").is_("uf", "null").execute()

    if existing.data:
        ids = [r["id"] for r in existing.data]
        # Cascade cuida dos preços
        for i in range(0, len(ids), 100):
            batch = ids[i:i + 100]
            client.table("comparativo_itens").delete().in_("id", batch).execute()


def gravar_plataformas(client, resumos: list[PlatformSummary], uf: str | None) -> None:
    """Grava resumo por plataforma em lote."""
    agora = datetime.utcnow().isoformat()

    rows = [{
        "plataforma_nome": r.plataforma_nome,
        "plataforma_id": r.plataforma_id,
        "total_itens": r.total_itens,
        "valor_medio_unitario": r.valor_medio_unitario,
        "mediana_unitario": r.mediana_unitario,
        "desconto_medio": r.desconto_medio,
        "cv_medio": r.cv_medio,
        "vitorias": r.vitorias_brutas,
        "vitorias_ponderadas": r.vitorias_ponderadas,
        "vitorias_alta_confianca": r.vitorias_alta_confianca,
        "total_grupos_comparaveis": r.total_grupos_comparaveis,
        "total_grupos_alta_confianca": r.total_grupos_alta_confianca,
        "proporcao_vitorias": r.proporcao_vitorias,
        "proporcao_homologados": r.proporcao_homologados,
        "score_comparabilidade_medio": r.score_comparabilidade_medio,
        "ranking_medio": r.ranking_medio,
        "delta_medio_para_lider": r.delta_medio_para_lider,
        "versao_algoritmo": VERSAO_ALGORITMO,
        "uf": uf,
        "calculado_em": agora,
    } for r in resumos]

    if rows:
        client.table("comparativo_plataformas").insert(rows).execute()
        log.info("  Gravadas %d plataformas", len(rows))


def gravar_itens_e_precos(
    client,
    grupos: list[ComparableGroup],
    uf: str | None,
) -> int:
    """Grava itens comparáveis e seus preços em lote. Retorna quantidade."""
    agora = datetime.utcnow().isoformat()
    gravados = 0

    # Insere itens em lote
    item_rows = [{
        "chave_agrupamento": g.chave,
        "descricao": g.descricao,
        "descricao_agrupamento": humanizar_chave(g.chave, g.descricao, g.ncm),
        "ncm_nbs_codigo": g.ncm,
        "unidade_medida": g.unidade_predominante,
        "menor_preco_plataforma": g.menor_preco_plataforma,
        "score_comparabilidade": g.score_comparabilidade,
        "faixa_confiabilidade": g.faixa_confiabilidade,
        "fonte_predominante": g.fonte_predominante,
        "unidade_predominante": g.unidade_predominante,
        "taxa_consistencia_unidade": g.taxa_consistencia_unidade,
        "total_observacoes": g.total_observacoes,
        "versao_algoritmo": VERSAO_ALGORITMO,
        "metodo_agrupamento": METODO_AGRUPAMENTO,
        "metodo_outlier": METODO_OUTLIER,
        "uf": uf,
        "calculado_em": agora,
    } for g in grupos]

    if not item_rows:
        return 0

    # Insere itens em lotes
    for i in range(0, len(item_rows), 50):
        batch = item_rows[i:i + 50]
        client.table("comparativo_itens").insert(batch).execute()

    # Busca IDs dos itens inseridos
    if uf:
        id_result = client.table("comparativo_itens").select("id, chave_agrupamento").eq("uf", uf).execute()
    else:
        id_result = client.table("comparativo_itens").select("id, chave_agrupamento").is_("uf", "null").execute()

    id_map = {r["chave_agrupamento"]: r["id"] for r in (id_result.data or [])}

    # Grava preços por plataforma
    preco_rows = []
    for grupo in grupos:
        item_id = id_map.get(grupo.chave)
        if not item_id:
            continue

        for nome, stats in grupo.stats_por_plataforma.items():
            preco_rows.append({
                "comparativo_item_id": item_id,
                "plataforma_nome": nome,
                "plataforma_id": stats.plataforma_id,
                "valor_medio": stats.resumo["media"],
                "mediana": stats.resumo["mediana"],
                "cv": stats.resumo["coeficiente_variacao"],
                "percentil_25": stats.resumo["percentil_25"],
                "percentil_75": stats.resumo["percentil_75"],
                "total_ocorrencias": stats.resumo["total"],
                "total_homologados": stats.total_homologados,
                "total_estimados": stats.total_estimados,
                "fonte_predominante": stats.fonte_predominante,
                "economia_media": stats.economia_media,
            })

        gravados += 1

    if preco_rows:
        for i in range(0, len(preco_rows), 50):
            batch = preco_rows[i:i + 50]
            client.table("comparativo_itens_precos").insert(batch).execute()

    log.info("  Gravados %d itens com %d preços", gravados, len(preco_rows))
    return gravados


def buscar_ufs_com_dados(client, ids_concorrentes: list[int]) -> list[str]:
    """Descobre quais UFs têm dados de itens."""
    result = (
        client.table("itens_contratacao")
        .select("uf")
        .in_("plataforma_id", ids_concorrentes)
        .gt("valor_unitario_estimado", 0)
        .limit(10000)
        .execute()
    )
    return sorted({r["uf"] for r in (result.data or []) if r.get("uf")})


def buscar_itens_plataforma(client, plat_id: int, uf: str | None, limite: int) -> list[dict]:
    """Busca itens de uma plataforma."""
    from market_comparison.constants import SELECT_ITENS

    query = (
        client.table("itens_contratacao")
        .select(SELECT_ITENS)
        .gt("valor_unitario_estimado", 0)
        .eq("plataforma_id", plat_id)
        .order("created_at", desc=True)
        .limit(limite)
    )
    if uf:
        query = query.eq("uf", uf)

    result = query.execute()
    return result.data or []
