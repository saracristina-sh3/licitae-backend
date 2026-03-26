"""Persistência de análises IA no Supabase."""

from __future__ import annotations

import json
import logging

from ia_analysis.types import ResultadoAnalise

log = logging.getLogger(__name__)


def gravar_analise(
    client,
    licitacao_id: str,
    tipo: str,
    resultado: ResultadoAnalise,
) -> None:
    """Grava ou atualiza análise IA no Supabase."""
    analise = resultado["analise"]

    row = {
        "licitacao_id": licitacao_id,
        "tipo": tipo,
        "recomendacao": analise["recomendacao"],
        "score_viabilidade": analise["score_viabilidade"],
        "resumo": analise["resumo"],
        "riscos_identificados": json.dumps(analise["riscos_identificados"], ensure_ascii=False),
        "oportunidades": json.dumps(analise["oportunidades"], ensure_ascii=False),
        "preco_sugerido": analise["preco_sugerido"],
        "margem_sugerida": analise["margem_sugerida"],
        "concorrentes_provaveis": json.dumps(analise["concorrentes_provaveis"], ensure_ascii=False),
        "perguntas_esclarecimento": analise["perguntas_esclarecimento"],
        "modelo_usado": resultado["modelo_usado"],
        "tokens_input": resultado["tokens_input"],
        "tokens_output": resultado["tokens_output"],
        "custo_usd": resultado["custo_usd"],
        "tempo_ms": resultado["tempo_ms"],
    }

    try:
        client.table("analise_ia_licitacao").upsert(
            row,
            on_conflict="licitacao_id,tipo",
        ).execute()
    except Exception as e:
        log.error("[%s] Erro ao gravar análise IA: %s", licitacao_id[:8], e)
        raise


def buscar_analise(client, licitacao_id: str, tipo: str = "completa") -> dict | None:
    """Busca análise IA existente."""
    result = (
        client.table("analise_ia_licitacao")
        .select("*")
        .eq("licitacao_id", licitacao_id)
        .eq("tipo", tipo)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
