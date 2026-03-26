"""Tool de comparativo de mercado entre plataformas."""

from __future__ import annotations

import json
import logging

from mcp.server import Server

log = logging.getLogger(__name__)


def register(app: Server) -> None:
    @app.tool()
    async def consultar_comparativo_mercado(uf: str = "") -> str:
        """Retorna comparativo de mercado entre plataformas de licitação.

        Inclui:
        - Ranking de plataformas por % de vitórias e economia
        - Itens comparáveis entre plataformas com preços
        - Score de comparabilidade dos grupos

        Plataformas monitoradas: SH3, BLL (BNC), Licitar Digital, Licitanet,
        Compras.gov.br, ECustomize, BBNet.

        Use para comparar preços e competitividade entre plataformas concorrentes.
        """
        from mcp_server.server import get_client

        client = get_client()

        # Resumo por plataforma
        query_plat = client.table("comparativo_plataformas").select("*")
        if uf:
            query_plat = query_plat.eq("uf", uf.upper())
        query_plat = query_plat.order("created_at", desc=True).limit(50)
        plat_result = query_plat.execute()

        # Itens comparáveis
        query_itens = client.table("comparativo_itens").select("*")
        if uf:
            query_itens = query_itens.eq("uf", uf.upper())
        query_itens = query_itens.order("created_at", desc=True).limit(200)
        itens_result = query_itens.execute()

        plataformas = plat_result.data or []
        itens = itens_result.data or []

        return json.dumps({
            "total_plataformas": len(plataformas),
            "total_itens_comparaveis": len(itens),
            "plataformas": plataformas,
            "itens": itens,
        }, ensure_ascii=False, default=str)
