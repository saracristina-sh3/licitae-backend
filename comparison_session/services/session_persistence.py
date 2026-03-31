"""
Persistência para sessões de comparação customizada.
Carrega itens selecionados e salva resultados.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


def carregar_itens_sessao(client, sessao_id: str) -> list[dict]:
    """
    Carrega itens selecionados (não excluídos) da sessão via RPC.
    Retorna lista de dicts com dados do item + resultados.
    """
    result = client.rpc("buscar_itens_por_licitacoes", {
        "p_sessao_id": sessao_id,
    }).execute()

    dados = result.data or {}
    if isinstance(dados, str):
        dados = json.loads(dados)

    itens = dados.get("data", [])
    # Filtrar itens excluídos
    return [i for i in itens if not i.get("excluido", False)]


def gravar_resultado(client, sessao_id: str, tipo: str, dados: dict | list) -> None:
    """
    Grava resultado da comparação ou análise IA na tabela sessao_resultados.
    Remove resultado anterior do mesmo tipo antes de inserir.
    """
    # Limpar resultado anterior
    client.table("sessao_resultados") \
        .delete() \
        .eq("sessao_id", sessao_id) \
        .eq("tipo", tipo) \
        .execute()

    # Inserir novo
    client.table("sessao_resultados").insert({
        "sessao_id": sessao_id,
        "tipo": tipo,
        "dados": dados if isinstance(dados, (dict, list)) else json.loads(json.dumps(dados)),
    }).execute()

    log.info("Resultado tipo=%s gravado para sessão %s", tipo, sessao_id)


def carregar_resultado(client, sessao_id: str, tipo: str) -> dict | list | None:
    """Carrega resultado existente da sessão."""
    result = client.table("sessao_resultados") \
        .select("dados") \
        .eq("sessao_id", sessao_id) \
        .eq("tipo", tipo) \
        .limit(1) \
        .execute()

    if result.data:
        return result.data[0]["dados"]
    return None
