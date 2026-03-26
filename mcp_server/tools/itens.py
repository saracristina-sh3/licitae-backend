"""Tool de busca de itens de contratação."""

from __future__ import annotations

import json
import logging

from mcp.server import Server

from mcp_server.config import LIMITE_ITENS_PADRAO, LIMITE_ITENS_MAXIMO

log = logging.getLogger(__name__)


def register(app: Server) -> None:
    @app.tool()
    async def buscar_itens_contratacao(
        descricao: str = "",
        plataforma_id: int | None = None,
        uf: str = "",
        ncm: str = "",
        valor_min: float | None = None,
        valor_max: float | None = None,
        limite: int = LIMITE_ITENS_PADRAO,
    ) -> str:
        """Busca itens de contratação com filtros.

        Retorna itens com: descrição, unidade, valores estimados e homologados,
        plataforma, NCM, município e fornecedor vencedor.

        Use para comparar preços de itens específicos entre plataformas e regiões.
        Ideal para análise de preços unitários e pesquisa de mercado.
        """
        from mcp_server.server import get_client

        client = get_client()
        limite = min(limite, LIMITE_ITENS_MAXIMO)

        query = (
            client.table("itens_contratacao")
            .select(
                "id, descricao, unidade_medida, quantidade, "
                "valor_unitario_estimado, valor_total_estimado, "
                "ncm_nbs_codigo, plataforma_id, plataforma_nome, "
                "municipio, uf, "
                "resultados_item(valor_unitario_homologado, nome_fornecedor, "
                "percentual_desconto, cnpj_fornecedor)"
            )
        )

        if uf:
            query = query.eq("uf", uf.upper())
        if plataforma_id is not None:
            query = query.eq("plataforma_id", plataforma_id)
        if ncm:
            query = query.eq("ncm_nbs_codigo", ncm)
        if valor_min is not None:
            query = query.gte("valor_unitario_estimado", valor_min)
        if valor_max is not None:
            query = query.lte("valor_unitario_estimado", valor_max)

        query = query.order("valor_unitario_estimado").limit(limite)

        if descricao:
            query = query.text_search("descricao", descricao, config="portuguese")

        result = query.execute()
        itens = result.data or []

        return json.dumps({
            "total": len(itens),
            "itens": itens,
        }, ensure_ascii=False, default=str)
