"""Tools de análise de editais e avaliação de oportunidades."""

from __future__ import annotations

import json
import logging

from mcp.server import Server

log = logging.getLogger(__name__)


def register(app: Server) -> None:
    @app.tool()
    async def analisar_edital(licitacao_id: str) -> str:
        """Busca e retorna dados do edital de uma licitação para análise pela IA.

        Retorna:
        - Texto extraído do PDF do edital (quando disponível)
        - Achados estruturados: documentos exigidos, prazos, garantias, penalidades
        - Prazos classificados por tipo (vigência, execução, implantação, etc.)
        - Score de risco (0-100) e fatores de risco identificados
        - Score de confiança da extração (0-100)
        - Qualidade da extração do PDF

        A IA pode analisar o texto do edital e responder perguntas detalhadas
        sobre requisitos, riscos e oportunidades — substituindo análise por regex.
        """
        from mcp_server.server import get_client

        client = get_client()

        # Busca análise existente
        analise = (
            client.table("analise_editais")
            .select("*")
            .eq("licitacao_id", licitacao_id)
            .limit(1)
            .execute()
        )

        if not analise.data:
            # Verifica se a licitação existe
            lic = (
                client.table("licitacoes")
                .select("id, objeto, url_fonte")
                .eq("id", licitacao_id)
                .limit(1)
                .execute()
            )
            if not lic.data:
                return json.dumps({"erro": "Licitação não encontrada"}, ensure_ascii=False)

            return json.dumps({
                "analisado": False,
                "licitacao": lic.data[0],
                "mensagem": "Edital ainda não foi analisado. A análise é feita automaticamente pelo cron diário.",
            }, ensure_ascii=False)

        edital = analise.data[0]

        # Busca dados da licitação para contexto
        lic = (
            client.table("licitacoes")
            .select("objeto, municipio_nome, uf, modalidade, valor_estimado, orgao")
            .eq("id", licitacao_id)
            .limit(1)
            .execute()
        )

        return json.dumps({
            "analisado": True,
            "licitacao": lic.data[0] if lic.data else None,
            "edital": edital,
        }, ensure_ascii=False, default=str)

    @app.tool()
    async def comparar_itens_similares(
        descricao: str,
        uf: str = "",
        limite: int = 100,
    ) -> str:
        """Retorna itens similares entre plataformas para análise semântica pela IA.

        A IA deve agrupar os itens semanticamente (ex: "filtro de óleo" = "elemento
        filtrante óleo") e comparar preços — substituindo regex/stopwords.

        Retorna itens de todas as plataformas monitoradas com:
        - Descrição completa, unidade, NCM
        - Valor estimado e homologado
        - Plataforma, município, UF
        - Fornecedor vencedor e desconto

        Use para pesquisa de preços e comparação entre plataformas.
        """
        from mcp_server.server import get_client

        client = get_client()
        limite = min(limite, 500)

        query = (
            client.table("itens_contratacao")
            .select(
                "descricao, unidade_medida, quantidade, "
                "valor_unitario_estimado, ncm_nbs_codigo, "
                "plataforma_id, plataforma_nome, municipio, uf, "
                "resultados_item(valor_unitario_homologado, nome_fornecedor, "
                "percentual_desconto, cnpj_fornecedor)"
            )
        )

        if uf:
            query = query.eq("uf", uf.upper())

        query = query.order("valor_unitario_estimado").limit(limite)
        query = query.text_search("descricao", descricao, config="portuguese")

        result = query.execute()
        itens = result.data or []

        # Agrupa por plataforma para facilitar comparação
        por_plataforma: dict[str, list] = {}
        for item in itens:
            plat = item.get("plataforma_nome") or "Desconhecida"
            por_plataforma.setdefault(plat, []).append(item)

        return json.dumps({
            "descricao_buscada": descricao,
            "total_itens": len(itens),
            "plataformas_encontradas": list(por_plataforma.keys()),
            "por_plataforma": {k: v for k, v in por_plataforma.items()},
            "itens": itens,
        }, ensure_ascii=False, default=str)

    @app.tool()
    async def avaliar_oportunidade(licitacao_id: str) -> str:
        """Retorna dados completos de uma licitação para avaliação pela IA.

        Consolida TODOS os dados disponíveis:
        - Detalhes da licitação (objeto, órgão, datas, valores)
        - Análise do edital (documentos, riscos, prazos)
        - Preços de referência (estatísticas, confiabilidade)
        - Itens de contratação com preços
        - Histórico de plataformas concorrentes

        A IA deve avaliar se vale participar baseado no perfil da organização,
        riscos, concorrência e viabilidade financeira.
        """
        from mcp_server.server import get_client

        client = get_client()

        # Licitação
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
        preco_ref = (
            client.table("preco_referencia_licitacao")
            .select("*")
            .eq("licitacao_id", licitacao_id)
            .limit(1)
            .execute()
        )

        # Itens
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

        # Comparativo da UF (se disponível)
        uf = licitacao.get("uf")
        comparativo = None
        if uf:
            comp = (
                client.table("comparativo_plataformas")
                .select("*")
                .eq("uf", uf)
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            )
            comparativo = comp.data or None

        return json.dumps({
            "licitacao": licitacao,
            "analise_edital": edital.data[0] if edital.data else None,
            "precos_referencia": preco_ref.data[0] if preco_ref.data else None,
            "itens": itens.data or [],
            "comparativo_plataformas": comparativo,
        }, ensure_ascii=False, default=str)
