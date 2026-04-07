"""Tools de configuração da organização."""

from __future__ import annotations

import json
import logging

from mcp.server import Server

log = logging.getLogger(__name__)


def register(app: Server) -> None:
    @app.tool()
    async def listar_config_organizacao(org_id: str = "") -> str:
        """Retorna configuração da organização: termos de exclusão, UFs, palavras-chave.

        Se org_id não for informado, retorna todas as configurações.

        Use para entender o perfil e filtros da organização ao avaliar licitações.
        """
        from mcp_server.server import get_client

        client = get_client()

        query_config = client.table("org_config").select("*")
        if org_id:
            query_config = query_config.eq("org_id", org_id)
        config_result = query_config.limit(10).execute()

        return json.dumps({
            "configs": config_result.data or [],
        }, ensure_ascii=False, default=str)

    @app.tool()
    async def consultar_fornecedor(cnpj_fornecedor: str) -> str:
        """Histórico de um fornecedor nas licitações monitoradas.

        Retorna: vitórias, valores homologados, plataformas onde atuou,
        UFs, itens vencidos com preços.

        Use para avaliar a competitividade de um fornecedor específico.
        """
        from mcp_server.server import get_client

        client = get_client()

        # Busca resultados do fornecedor
        resultados = (
            client.table("resultados_item")
            .select(
                "valor_unitario_homologado, percentual_desconto, "
                "nome_fornecedor, cnpj_fornecedor, "
                "item:itens_contratacao("
                "  descricao, unidade_medida, valor_unitario_estimado, "
                "  plataforma_nome, plataforma_id, municipio, uf"
                ")"
            )
            .eq("cnpj_fornecedor", cnpj_fornecedor)
            .order("valor_unitario_homologado", desc=True)
            .limit(200)
            .execute()
        )

        rows = resultados.data or []
        if not rows:
            return json.dumps({
                "encontrado": False,
                "mensagem": f"Nenhum resultado encontrado para CNPJ {cnpj_fornecedor}",
            }, ensure_ascii=False)

        # Estatísticas
        nome = rows[0].get("nome_fornecedor", "")
        plataformas: set[str] = set()
        ufs: set[str] = set()
        total_valor = 0.0

        for r in rows:
            item = r.get("item") or {}
            plataformas.add(item.get("plataforma_nome") or "")
            ufs.add(item.get("uf") or "")
            total_valor += float(r.get("valor_unitario_homologado") or 0)

        plataformas.discard("")
        ufs.discard("")

        return json.dumps({
            "encontrado": True,
            "cnpj": cnpj_fornecedor,
            "nome": nome,
            "total_vitorias": len(rows),
            "valor_total_homologado": round(total_valor, 2),
            "plataformas": sorted(plataformas),
            "ufs": sorted(ufs),
            "itens": rows[:50],  # Limita para não estourar contexto
        }, ensure_ascii=False, default=str)
