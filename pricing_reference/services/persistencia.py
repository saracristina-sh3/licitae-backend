"""
Serviço de persistência — grava e lê resultados de preços de referência.
Isola todas as operações de banco em um único local.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime

from pricing_reference.constants import DESCONTO_MAXIMO
from pricing_reference.types import ResultadoSimilaridade

log = logging.getLogger(__name__)


def limpar_referencia_existente(client, licitacao_id: str) -> None:
    """Remove todos os dados de preço de referência para uma licitação."""
    existing = (
        client.table("preco_referencia_licitacao")
        .select("id")
        .eq("licitacao_id", licitacao_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        ref_id = existing.data["id"]
        # Cascade vai limpar detalhes, itens e plataformas
        client.table("preco_referencia_detalhe").delete().eq("preco_referencia_id", ref_id).execute()
        client.table("preco_referencia_itens").delete().eq("preco_referencia_id", ref_id).execute()
        client.table("preco_referencia_plataformas").delete().eq("preco_referencia_id", ref_id).execute()
        client.table("preco_referencia_licitacao").delete().eq("id", ref_id).execute()


def gravar_resumo(client, registro: dict) -> int | None:
    """
    Grava resumo de preço de referência.
    Retorna o ID do registro ou None se falhou.
    """
    licitacao_id = registro["licitacao_id"]

    # Limpa dados anteriores
    limpar_referencia_existente(client, licitacao_id)

    # Insere novo
    client.table("preco_referencia_licitacao").insert(registro).execute()

    # Busca o ID
    result = (
        client.table("preco_referencia_licitacao")
        .select("id")
        .eq("licitacao_id", licitacao_id)
        .single()
        .execute()
    )

    if not result.data:
        log.error("Falha ao gravar resumo para %s", licitacao_id)
        return None

    return result.data["id"]


def gravar_detalhes_licitacoes(
    client,
    ref_id: int,
    similares: list[ResultadoSimilaridade],
) -> int:
    """Grava detalhes de licitações similares. Retorna quantidade gravada."""
    rows = []
    for sim in similares:
        s = sim["registro"]
        if sim["valor"] <= 0:
            continue
        rows.append({
            "preco_referencia_id": ref_id,
            "licitacao_similar_id": s["id"],
            "municipio_nome": s.get("municipio_nome") or "",
            "uf": s.get("uf") or "",
            "objeto": (s.get("objeto") or "")[:200],
            "modalidade": s.get("modalidade") or "",
            "valor_homologado": sim["valor"] if sim["fonte_preco"] == "homologado" else None,
            "data_publicacao": s.get("data_publicacao"),
            "score_similaridade": sim["score"],
            "fonte_preco": sim["fonte_preco"],
        })

    if rows:
        client.table("preco_referencia_detalhe").insert(rows).execute()

    return len(rows)


def gravar_detalhes_itens(
    client,
    ref_id: int,
    itens: list[ResultadoSimilaridade],
) -> int:
    """Grava detalhes de itens similares. Retorna quantidade gravada."""
    rows = []
    for item_sim in itens:
        item = item_sim["registro"]
        resultado_usado = item.get("_resultado_usado")
        desc = None
        nome_forn = ""

        if resultado_usado:
            nome_forn = (resultado_usado.get("nome_fornecedor") or "")[:100]
            # Recalcula desconto a partir dos valores reais
            estimado = float(item.get("valor_unitario_estimado", 0) or 0)
            homologado = float(resultado_usado.get("valor_unitario_homologado", 0) or 0)
            if estimado > 0 and homologado > 0:
                d = ((estimado - homologado) / estimado) * 100
                if 0 <= d <= DESCONTO_MAXIMO:
                    desc = round(d, 2)

        rows.append({
            "preco_referencia_id": ref_id,
            "descricao": (item.get("descricao") or "")[:200],
            "unidade_medida": item.get("unidade_medida") or "",
            "valor_unitario": round(item_sim["valor"], 2),
            "plataforma_nome": item.get("plataforma_nome") or "Não identificada",
            "municipio": item.get("municipio") or "",
            "uf": item.get("uf") or "",
            "nome_fornecedor": nome_forn,
            "percentual_desconto": desc,
            "fonte_preco": item_sim["fonte_preco"],
            "score_similaridade": item_sim["score"],
            "compativel_unidade": item_sim["compativel_unidade"],
        })

    # Insere em lotes de 50
    for i in range(0, len(rows), 50):
        batch = rows[i:i + 50]
        client.table("preco_referencia_itens").insert(batch).execute()

    return len(rows)


def gravar_resumo_plataformas(
    client,
    ref_id: int,
    itens: list[ResultadoSimilaridade],
) -> int:
    """Calcula e grava resumo por plataforma. Retorna quantidade gravada."""
    plat_map: dict[str, list[float]] = {}
    for item_sim in itens:
        plat = item_sim["registro"].get("plataforma_nome") or "Não identificada"
        plat_map.setdefault(plat, []).append(item_sim["valor"])

    rows = []
    for plat, vals in plat_map.items():
        rows.append({
            "preco_referencia_id": ref_id,
            "plataforma_nome": plat,
            "media_unitario": round(statistics.mean(vals), 2),
            "total_itens": len(vals),
        })

    if rows:
        client.table("preco_referencia_plataformas").insert(rows).execute()

    return len(rows)


def buscar_licitacoes_pendentes(client, limite: int) -> list[dict]:
    """Busca licitações abertas sem preço calculado."""
    result = (
        client.table("licitacoes")
        .select("id, objeto, modalidade, uf, palavras_chave")
        .eq("proposta_aberta", True)
        .order("relevancia", desc=False)
        .order("data_publicacao", desc=True)
        .limit(limite * 2)
        .execute()
    )
    licitacoes = result.data or []

    if not licitacoes:
        return []

    # Filtra as que já têm preço calculado
    lic_ids = [l["id"] for l in licitacoes]
    ja_calculadas = (
        client.table("preco_referencia_licitacao")
        .select("licitacao_id")
        .in_("licitacao_id", lic_ids)
        .execute()
    )
    ids_calculados = {r["licitacao_id"] for r in (ja_calculadas.data or [])}

    return [l for l in licitacoes if l["id"] not in ids_calculados][:limite]
