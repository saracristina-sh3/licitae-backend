"""Tool de consulta de preços de referência."""

from __future__ import annotations

import json
import logging

from mcp.server import Server

log = logging.getLogger(__name__)


def register(app: Server) -> None:
    @app.tool()
    async def consultar_precos_referencia(licitacao_id: str) -> str:
        """Consulta preços de referência calculados para uma licitação.

        Retorna:
        - Resumo estatístico: média, mediana, min/max, percentis, CV
        - Separação por fonte: homologados vs estimados
        - Score de confiabilidade (0-100) com faixa (alta/média/baixa)
        - Licitações similares usadas no cálculo
        - Itens similares com preços unitários
        - Resumo por plataforma

        Use para entender o preço justo de uma licitação e a confiança do cálculo.
        """
        from mcp_server.server import get_client

        client = get_client()

        # Resumo principal
        resumo = (
            client.table("preco_referencia_licitacao")
            .select("*")
            .eq("licitacao_id", licitacao_id)
            .limit(1)
            .execute()
        )

        if not resumo.data:
            return json.dumps({
                "calculado": False,
                "mensagem": "Preço de referência ainda não calculado para esta licitação.",
            }, ensure_ascii=False)

        ref = resumo.data[0]
        ref_id = ref["id"]

        # Licitações similares
        detalhes_lic = (
            client.table("preco_referencia_detalhe")
            .select("*")
            .eq("preco_referencia_id", ref_id)
            .order("score_similaridade", desc=True)
            .limit(50)
            .execute()
        )

        # Itens similares
        detalhes_itens = (
            client.table("preco_referencia_itens")
            .select("*")
            .eq("preco_referencia_id", ref_id)
            .order("score_similaridade", desc=True)
            .limit(100)
            .execute()
        )

        # Resumo por plataforma
        plataformas = (
            client.table("preco_referencia_plataformas")
            .select("*")
            .eq("preco_referencia_id", ref_id)
            .order("total_itens", desc=True)
            .execute()
        )

        return json.dumps({
            "calculado": True,
            "resumo": ref,
            "licitacoes_similares": detalhes_lic.data or [],
            "itens_similares": detalhes_itens.data or [],
            "plataformas": plataformas.data or [],
        }, ensure_ascii=False, default=str)
