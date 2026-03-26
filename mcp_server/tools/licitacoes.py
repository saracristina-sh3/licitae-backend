"""Tools de busca e consulta de licitações."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server

from mcp_server.config import LIMITE_BUSCA_PADRAO, LIMITE_BUSCA_MAXIMO

log = logging.getLogger(__name__)


def register(app: Server) -> None:
    @app.tool()
    async def buscar_licitacoes(
        busca_texto: str = "",
        uf: str = "",
        modalidade: str = "",
        relevancia: str = "",
        proposta_aberta: bool | None = None,
        exclusivo_me_epp: bool | None = None,
        valor_min: float | None = None,
        valor_max: float | None = None,
        palavra_chave: str = "",
        ordenar_por: str = "relevancia",
        limite: int = LIMITE_BUSCA_PADRAO,
    ) -> str:
        """Busca licitações com filtros flexíveis.

        Retorna lista de licitações com: id, objeto, município, UF, modalidade,
        valor estimado, relevância, data de publicação, situação e palavras-chave.

        Use para encontrar oportunidades de licitação por texto, região ou critérios.
        """
        from mcp_server.server import get_client

        client = get_client()
        limite = min(limite, LIMITE_BUSCA_MAXIMO)

        query = (
            client.table("licitacoes")
            .select(
                "id, objeto, municipio_nome, uf, modalidade, valor_estimado, "
                "relevancia, data_publicacao, data_abertura_proposta, "
                "data_encerramento_proposta, situacao, proposta_aberta, "
                "exclusivo_me_epp, palavras_chave, orgao, url_fonte"
            )
        )

        if uf:
            query = query.eq("uf", uf.upper())
        if modalidade:
            query = query.eq("modalidade", modalidade)
        if relevancia:
            query = query.eq("relevancia", relevancia.upper())
        if proposta_aberta is not None:
            query = query.eq("proposta_aberta", proposta_aberta)
        if exclusivo_me_epp is not None:
            query = query.eq("exclusivo_me_epp", exclusivo_me_epp)
        if valor_min is not None:
            query = query.gte("valor_estimado", valor_min)
        if valor_max is not None:
            query = query.lte("valor_estimado", valor_max)

        # Ordenação
        if ordenar_por == "data_publicacao":
            query = query.order("data_publicacao", desc=True)
        elif ordenar_por == "valor_estimado":
            query = query.order("valor_estimado", desc=True)
        elif ordenar_por == "municipio_nome":
            query = query.order("municipio_nome")
        else:
            query = query.order("relevancia").order("data_publicacao", desc=True)

        query = query.limit(limite)

        # text_search deve vir depois de order/limit (quirk do SDK)
        if busca_texto:
            query = query.text_search("objeto", busca_texto, config="portuguese")

        result = query.execute()
        licitacoes = result.data or []

        # Filtra por palavra-chave (array contains)
        if palavra_chave and licitacoes:
            pc_lower = palavra_chave.lower()
            licitacoes = [
                l for l in licitacoes
                if any(pc_lower in (p or "").lower() for p in (l.get("palavras_chave") or []))
            ]

        return json.dumps({
            "total": len(licitacoes),
            "licitacoes": licitacoes,
        }, ensure_ascii=False, default=str)

    @app.tool()
    async def detalhar_licitacao(licitacao_id: str) -> str:
        """Retorna todos os detalhes de uma licitação específica.

        Inclui: dados da licitação, análise do edital (se disponível),
        preços de referência (se calculados) e itens de contratação.

        Use para obter visão completa de uma oportunidade antes de analisar.
        """
        from mcp_server.server import get_client

        client = get_client()

        # Licitação principal
        lic = (
            client.table("licitacoes")
            .select("*")
            .eq("id", licitacao_id)
            .limit(1)
            .execute()
        )
        if not lic.data:
            return json.dumps({"erro": "Licitação não encontrada"}, ensure_ascii=False)

        licitacao = lic.data[0]

        # Análise do edital
        edital = (
            client.table("analise_editais")
            .select("*")
            .eq("licitacao_id", licitacao_id)
            .limit(1)
            .execute()
        )

        # Preços de referência
        precos = (
            client.table("preco_referencia_licitacao")
            .select("*")
            .eq("licitacao_id", licitacao_id)
            .limit(1)
            .execute()
        )

        # Itens de contratação
        itens = (
            client.table("itens_contratacao")
            .select(
                "descricao, unidade_medida, quantidade, valor_unitario_estimado, "
                "valor_total_estimado, ncm_nbs_codigo, "
                "resultados_item(valor_unitario_homologado, nome_fornecedor, percentual_desconto)"
            )
            .eq("licitacao_id", licitacao_id)
            .order("numero_item")
            .limit(100)
            .execute()
        )

        return json.dumps({
            "licitacao": licitacao,
            "analise_edital": edital.data[0] if edital.data else None,
            "precos_referencia": precos.data[0] if precos.data else None,
            "itens": itens.data or [],
        }, ensure_ascii=False, default=str)

    @app.tool()
    async def buscar_estatisticas_dashboard(uf: str = "") -> str:
        """Métricas gerais para dashboard: total abertas, por relevância, por UF, valor total.

        Use para ter visão geral do mercado de licitações.
        """
        from mcp_server.server import get_client

        client = get_client()

        # Total abertas
        query_total = (
            client.table("licitacoes")
            .select("id", count="exact")
            .eq("proposta_aberta", True)
        )
        if uf:
            query_total = query_total.eq("uf", uf.upper())
        total_result = query_total.execute()
        total_abertas = total_result.count or 0

        # Busca amostra para calcular estatísticas
        query_dados = (
            client.table("licitacoes")
            .select("relevancia, uf, valor_estimado")
            .eq("proposta_aberta", True)
        )
        if uf:
            query_dados = query_dados.eq("uf", uf.upper())
        dados = query_dados.limit(5000).execute()
        rows = dados.data or []

        # Por relevância
        por_relevancia = {"ALTA": 0, "MEDIA": 0, "BAIXA": 0}
        por_uf: dict[str, int] = {}
        valor_total = 0.0

        for r in rows:
            rel = r.get("relevancia", "BAIXA")
            por_relevancia[rel] = por_relevancia.get(rel, 0) + 1
            u = r.get("uf", "??")
            por_uf[u] = por_uf.get(u, 0) + 1
            valor_total += float(r.get("valor_estimado") or 0)

        return json.dumps({
            "total_abertas": total_abertas,
            "por_relevancia": por_relevancia,
            "por_uf": dict(sorted(por_uf.items(), key=lambda x: -x[1])),
            "valor_total_estimado": round(valor_total, 2),
        }, ensure_ascii=False, default=str)
