"""
Cliente Supabase — usado pelo scraper com service_role key.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os

log = logging.getLogger(__name__)

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


def _hash_licitacao(cnpj: str, ano: str, seq: str, fonte: str) -> str:
    """Gera hash de deduplicação."""
    raw = f"{fonte}:{cnpj}:{ano}:{seq}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _hash_licitacao_texto(municipio: str, objeto: str, data_pub: str, fonte: str) -> str:
    """Hash alternativo quando não tem CNPJ/sequencial."""
    raw = f"{fonte}:{municipio}:{objeto[:100]}:{data_pub[:10]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def sync_municipios(municipios: list[dict], batch_size: int = 100) -> int:
    """Sincroniza municípios no Supabase em lotes. Retorna quantidade inserida/atualizada."""
    client = get_client()
    count = 0

    rows = [
        {
            "codigo_ibge": mun["codigo_ibge"],
            "nome": mun["nome"],
            "uf": mun["uf"],
            "populacao": mun["populacao"],
            "fpm": mun["fpm"],
            "microrregiao_id": mun.get("microrregiao_id"),
        }
        for mun in municipios
    ]

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        client.table("municipios").upsert(
            batch,
            on_conflict="codigo_ibge",
        ).execute()
        count += len(batch)

    return count


def sync_microrregioes(microrregioes: list[dict], batch_size: int = 100) -> int:
    """Sincroniza microrregiões no Supabase em lotes."""
    client = get_client()
    count = 0

    rows = [
        {
            "id": m["id"],
            "nome": m["nome"],
            "mesorregiao_id": m["mesorregiao_id"],
            "mesorregiao_nome": m["mesorregiao_nome"],
            "uf": m["uf"],
        }
        for m in microrregioes
    ]

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        client.table("microrregioes").upsert(
            batch,
            on_conflict="id",
        ).execute()
        count += len(batch)

    return count


def get_municipio_id(codigo_ibge: str) -> int | None:
    """Busca ID do município pelo código IBGE."""
    client = get_client()
    result = (
        client.table("municipios")
        .select("id")
        .eq("codigo_ibge", codigo_ibge)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]
    return None


# Cache de IDs para evitar queries repetidas
_municipio_cache: dict[str, int] = {}


def get_municipio_id_cached(codigo_ibge: str) -> int | None:
    if codigo_ibge in _municipio_cache:
        return _municipio_cache[codigo_ibge]
    mid = get_municipio_id(codigo_ibge)
    if mid is not None:
        _municipio_cache[codigo_ibge] = mid
    return mid


def inserir_licitacoes(resultados: list[dict]) -> dict:
    """
    Insere licitações no Supabase SEM score/relevância (coleta genérica).
    Score e relevância são calculados na prospecção por org.
    Retorna {"inseridas": N, "duplicadas": N, "erros": N}
    """
    client = get_client()
    stats = {"inseridas": 0, "duplicadas": 0, "erros": 0}

    for r in resultados:
        cnpj = r.get("cnpj_orgao", "")
        if cnpj:
            h = _hash_licitacao(cnpj, r.get("ano_compra", ""), r.get("seq_compra", ""), r.get("fonte", "PNCP"))
        else:
            h = _hash_licitacao_texto(r["municipio"], r["objeto"], r.get("data_publicacao", ""), r.get("fonte", "PNCP"))

        codigo_ibge = r.get("codigo_ibge", "")
        municipio_id = get_municipio_id_cached(codigo_ibge) if codigo_ibge else None

        row = {
            "hash_dedup": h,
            "municipio_id": municipio_id,
            "municipio_nome": r["municipio"],
            "uf": r["uf"],
            "orgao": r.get("orgao", ""),
            "cnpj_orgao": r.get("cnpj_orgao", ""),
            "objeto": r["objeto"],
            "modalidade": r.get("modalidade", ""),
            "valor_estimado": r.get("valor_estimado", 0),
            "valor_homologado": r.get("valor_homologado", 0),
            "situacao": r.get("situacao", ""),
            "data_publicacao": r.get("data_publicacao") or None,
            "data_abertura_proposta": r.get("data_abertura_proposta") or None,
            "data_encerramento_proposta": r.get("data_encerramento_proposta") or None,
            "fonte": r.get("fonte", "PNCP"),
            "url_fonte": r.get("url_pncp", "") or r.get("url_fonte", ""),
            "dados_brutos": r.get("dados_brutos"),
            "exclusivo_me_epp": r.get("exclusivo_me_epp", False),
            "modalidade_id": r.get("modalidade_id"),
            "modo_disputa_id": r.get("modo_disputa_id"),
            "situacao_compra_id": r.get("situacao_compra_id"),
            "informacao_complementar": r.get("informacao_complementar"),
        }

        try:
            client.table("licitacoes").upsert(
                row,
                on_conflict="hash_dedup",
            ).execute()
            stats["inseridas"] += 1
        except Exception as e:
            err_msg = str(e)
            if "duplicate" in err_msg.lower() or "conflict" in err_msg.lower():
                stats["duplicadas"] += 1
            else:
                stats["erros"] += 1
                log.error("Erro ao inserir licitação: %s", e)

    return stats


def marcar_itens_coletados(hash_dedup: str) -> None:
    """Marca licitação como tendo itens coletados."""
    client = get_client()
    client.table("licitacoes").update(
        {"itens_coletados": True}
    ).eq("hash_dedup", hash_dedup).execute()


def upsert_oportunidades_org(org_id: str, oportunidades: list[dict], batch_size: int = 50) -> int:
    """
    Insere/atualiza oportunidades de uma org na tabela oportunidades_org.
    Retorna quantidade persistida.
    """
    client = get_client()
    count = 0

    for i in range(0, len(oportunidades), batch_size):
        batch = oportunidades[i : i + batch_size]
        rows = [
            {
                "org_id": org_id,
                "licitacao_id": op["licitacao_id"],
                "score": op["score"],
                "relevancia": op["relevancia"],
                "urgencia": op.get("urgencia", "NORMAL"),
                "palavras_chave_encontradas": op.get("palavras_chave_encontradas", []),
                "campos_matched": op.get("campos_matched", []),
                "itens_matched": json.dumps(op.get("itens_matched", [])),
                "total_itens": op.get("total_itens", 0),
                "itens_relevantes": op.get("itens_relevantes", 0),
                "valor_itens_relevantes": op.get("valor_itens_relevantes", 0),
            }
            for op in batch
        ]
        try:
            client.table("oportunidades_org").upsert(
                rows,
                on_conflict="org_id,licitacao_id",
            ).execute()
            count += len(rows)
        except Exception as e:
            log.error("Erro ao upsert oportunidades_org: %s", e)

    return count


def buscar_licitacoes_para_prospeccao(
    ufs: list[str],
    populacao_maxima: int,
    dias_retroativos: int = 7,
    microrregioes_ids: list[int] | None = None,
) -> list[dict]:
    """
    Busca licitações do banco para prospecção por org.
    Filtra por UFs, FPM e opcionalmente microrregiões.
    """
    from datetime import datetime, timedelta

    client = get_client()
    data_desde = (datetime.now() - timedelta(days=dias_retroativos)).isoformat()

    query = (
        client.table("licitacoes")
        .select("*, municipios!inner(codigo_ibge, populacao, fpm, microrregiao_id)")
        .in_("uf", ufs)
        .gte("created_at", data_desde)
        .lte("municipios.populacao", populacao_maxima)
    )

    result = query.execute()
    rows = result.data or []

    # Filtro de microrregião (pós-query, pois Supabase não suporta IN em joins facilmente)
    if microrregioes_ids:
        ids_set = set(microrregioes_ids)
        rows = [
            r for r in rows
            if r.get("municipios", {}).get("microrregiao_id") in ids_set
        ]

    return rows


def buscar_itens_licitacao(cnpj_orgao: str, ano_compra: int, sequencial_compra: int) -> list[dict]:
    """Busca itens de uma licitação por cnpj + ano + sequencial."""
    client = get_client()
    result = (
        client.table("itens_contratacao")
        .select("numero_item, descricao, quantidade, unidade_medida, "
                "valor_unitario_estimado, valor_total_estimado, ncm_nbs_codigo")
        .eq("cnpj_orgao", cnpj_orgao)
        .eq("ano_compra", ano_compra)
        .eq("sequencial_compra", sequencial_compra)
        .order("numero_item")
        .execute()
    )
    return result.data or []


def contar_licitacoes_abertas() -> int:
    client = get_client()
    result = (
        client.table("licitacoes")
        .select("id", count="exact")
        .eq("proposta_aberta", True)
        .execute()
    )
    return result.count or 0


def buscar_novas_licitacoes(desde: str) -> list[dict]:
    """Busca licitações inseridas desde uma data (para alertas)."""
    client = get_client()
    result = (
        client.table("licitacoes")
        .select("*")
        .gte("created_at", desde)
        .eq("proposta_aberta", True)
        .order("relevancia")
        .order("data_publicacao", desc=True)
        .execute()
    )
    return result.data or []
