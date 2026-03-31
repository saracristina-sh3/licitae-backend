"""
Orquestração da comparação customizada de preços por sessão.
Reutiliza módulos existentes de agrupamento e estatística.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from comparison_core.categories import classificar_item
from comparison_core.normalizer import extrair_termos
from comparison_core.validator import unidade_canonica
from market_comparison.services.grouping import agrupar_itens, montar_grupo_comparavel
from market_comparison.types import ObservedItem
from pricing_reference.services.estatistica import calcular_resumo, remover_outliers_iqr

from comparison_session.services.session_persistence import (
    carregar_itens_sessao,
    gravar_resultado,
)

log = logging.getLogger(__name__)


def _converter_item_sessao(item: dict) -> ObservedItem | None:
    """Converte item da RPC em ObservedItem para agrupamento."""
    descricao = (item.get("descricao") or "")[:120]
    if not descricao:
        return None

    # Determinar valor: preferir homologado
    resultados = item.get("resultados") or []
    valor = 0.0
    fonte = "estimado"
    desconto = None

    if resultados and isinstance(resultados, list):
        for r in resultados:
            hom = r.get("valor_unitario_homologado")
            if hom and float(hom) > 0:
                valor = float(hom)
                fonte = "homologado"
                desconto = r.get("percentual_desconto")
                break

    if valor <= 0:
        estimado = item.get("valor_unitario_estimado")
        valor = float(estimado) if estimado and float(estimado) > 0 else 0

    if valor <= 0:
        return None

    return ObservedItem(
        descricao=descricao,
        ncm=item.get("ncm_nbs_codigo"),
        unidade=item.get("unidade_medida") or "",
        plataforma_nome=item.get("plataforma_nome") or "desconhecida",
        plataforma_id=item.get("plataforma_id") or 0,
        valor=valor,
        fonte_preco=fonte,
        desconto=float(desconto) if desconto else None,
        categoria=classificar_item(descricao),
    )


def comparar_itens_sessao(client, sessao_id: str) -> dict:
    """
    Pipeline completo de comparação por sessão:
    1. Carrega itens selecionados
    2. Converte para ObservedItem
    3. Agrupa via NCM/lexical
    4. Calcula estatísticas com IQR
    5. Gera visão por edital
    6. Persiste resultados
    """
    # 1. Carregar itens
    itens_raw = carregar_itens_sessao(client, sessao_id)
    log.info("Sessão %s: %d itens carregados", sessao_id, len(itens_raw))

    if not itens_raw:
        return {"por_item": [], "por_edital": [], "total_itens": 0}

    # 2. Converter para ObservedItem
    itens_obs: list[ObservedItem] = []
    itens_por_licitacao: dict[str, list[dict]] = defaultdict(list)

    for raw in itens_raw:
        obs = _converter_item_sessao(raw)
        if obs:
            itens_obs.append(obs)
        # Agrupar por licitação para visão "por_edital"
        lic_id = raw.get("licitacao_id", "")
        if lic_id:
            itens_por_licitacao[lic_id].append(raw)

    log.info("Sessão %s: %d itens convertidos", sessao_id, len(itens_obs))

    # 3. Agrupar
    # Reutiliza agrupar_itens mas precisa converter format
    itens_como_raw = []
    for raw, obs in zip(itens_raw, itens_obs if len(itens_obs) == len(itens_raw) else []):
        if obs:
            itens_como_raw.append({
                "descricao": obs.descricao,
                "ncm_nbs_codigo": obs.ncm,
                "unidade_medida": obs.unidade,
                "plataforma_nome": obs.plataforma_nome,
                "plataforma_id": obs.plataforma_id,
                "valor_unitario_estimado": obs.valor,
                "resultados_item": raw.get("resultados", []),
            })

    grupos = agrupar_itens(itens_como_raw)
    log.info("Sessão %s: %d grupos formados", sessao_id, len(grupos))

    # 4. Calcular estatísticas por grupo
    resultados_por_item = []
    for chave, itens_grupo in grupos.items():
        grupo_comp = montar_grupo_comparavel(chave, itens_grupo)
        if not grupo_comp:
            continue

        # Stats por plataforma
        plataformas_stats = []
        valores_por_plat: dict[str, list[float]] = defaultdict(list)
        for item in itens_grupo:
            valores_por_plat[item.plataforma_nome].append(item.valor)

        for plat_nome, valores in valores_por_plat.items():
            valores_limpos = remover_outliers_iqr(valores)
            resumo = calcular_resumo(valores_limpos)
            plataformas_stats.append({
                "plataforma_nome": plat_nome,
                "valor_medio": resumo["media"],
                "mediana": resumo["mediana"],
                "total_ocorrencias": resumo["total"],
                "cv": resumo.get("coeficiente_variacao"),
                "economia_media": None,
            })

        # Ordenar por valor médio (menor primeiro)
        plataformas_stats.sort(key=lambda p: p["valor_medio"])

        # Calcular economia relativa ao mais caro
        if len(plataformas_stats) >= 2:
            mais_caro = plataformas_stats[-1]["valor_medio"]
            if mais_caro > 0:
                for p in plataformas_stats:
                    p["economia_media"] = round(
                        (1 - p["valor_medio"] / mais_caro) * 100, 1
                    )

        resultados_por_item.append({
            "chave": chave,
            "descricao": grupo_comp.descricao,
            "ncm": grupo_comp.ncm,
            "unidade_predominante": grupo_comp.unidade_predominante,
            "total_observacoes": grupo_comp.total_observacoes,
            "score_comparabilidade": None,
            "faixa_confiabilidade": None,
            "plataformas": plataformas_stats,
        })

    # 5. Visão por edital
    resultados_por_edital = []
    for lic_id, itens_lic in itens_por_licitacao.items():
        if not itens_lic:
            continue

        primeiro = itens_lic[0]
        valores_estimados = [
            float(i["valor_unitario_estimado"])
            for i in itens_lic
            if i.get("valor_unitario_estimado") and float(i["valor_unitario_estimado"]) > 0
        ]
        valores_homologados = []
        for i in itens_lic:
            for r in (i.get("resultados") or []):
                v = r.get("valor_unitario_homologado")
                if v and float(v) > 0:
                    valores_homologados.append(float(v))

        valor_est_total = sum(valores_estimados) if valores_estimados else 0
        valor_hom_total = sum(valores_homologados) if valores_homologados else 0
        economia = None
        if valor_est_total > 0 and valor_hom_total > 0:
            economia = round((1 - valor_hom_total / valor_est_total) * 100, 1)

        resultados_por_edital.append({
            "licitacao_id": lic_id,
            "objeto": primeiro.get("licitacao_objeto", ""),
            "municipio": f"{primeiro.get('licitacao_municipio', '')}/{primeiro.get('licitacao_uf', '')}",
            "relevancia": primeiro.get("relevancia", ""),
            "total_itens": len(itens_lic),
            "valor_estimado": valor_est_total,
            "valor_homologado": valor_hom_total,
            "economia": economia,
        })

    resultados_por_edital.sort(key=lambda e: e.get("economia") or 0, reverse=True)

    # 6. Persistir
    resultado = {
        "por_item": resultados_por_item,
        "por_edital": resultados_por_edital,
        "total_itens": len(itens_obs),
        "total_grupos": len(resultados_por_item),
    }

    gravar_resultado(client, sessao_id, "por_item", resultados_por_item)
    gravar_resultado(client, sessao_id, "por_edital", resultados_por_edital)

    log.info(
        "Sessão %s: comparação concluída — %d itens, %d grupos, %d editais",
        sessao_id, len(itens_obs), len(resultados_por_item), len(resultados_por_edital),
    )

    return resultado
