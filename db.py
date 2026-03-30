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
    Insere licitações no Supabase com deduplicação.
    Retorna {"inseridas": N, "duplicadas": N, "erros": N}
    """
    client = get_client()
    stats = {"inseridas": 0, "duplicadas": 0, "erros": 0}

    for r in resultados:
        # Gerar hash de dedup
        cnpj = r.get("cnpj_orgao", "")
        if cnpj:
            h = _hash_licitacao(cnpj, r.get("ano_compra", ""), r.get("seq_compra", ""), r.get("fonte", "PNCP"))
        else:
            h = _hash_licitacao_texto(r["municipio"], r["objeto"], r.get("data_publicacao", ""), r.get("fonte", "PNCP"))

        # Buscar municipio_id
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
            "relevancia": r.get("relevancia", "BAIXA"),
            "palavras_chave": r.get("palavras_chave_encontradas", "").split(", ") if isinstance(r.get("palavras_chave_encontradas"), str) else r.get("palavras_chave_encontradas", []),
            "dados_brutos": r.get("dados_brutos"),
            "exclusivo_me_epp": r.get("exclusivo_me_epp", False),
            "modalidade_id": r.get("modalidade_id"),
            "modo_disputa_id": r.get("modo_disputa_id"),
            "situacao_compra_id": r.get("situacao_compra_id"),
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
