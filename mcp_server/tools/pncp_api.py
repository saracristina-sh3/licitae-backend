"""Tool de consulta direta à API do PNCP."""

from __future__ import annotations

import json
import logging
import sys

from mcp.server import Server

log = logging.getLogger(__name__)


def register(app: Server) -> None:
    @app.tool()
    async def consultar_pncp_direto(
        cnpj_orgao: str,
        ano_compra: int,
        sequencial_compra: int,
    ) -> str:
        """Consulta direta à API do PNCP para dados que não estão no banco.

        Busca detalhes de uma contratação específica pelo CNPJ do órgão,
        ano e sequencial da compra.

        Retorna: dados brutos da contratação + lista de itens + resultados.

        Use quando precisar de dados atualizados diretamente do PNCP,
        ou para contratações que ainda não foram coletadas pelo scraper.
        """
        # Importa PNCPClient do diretório pai
        parent = str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        from pncp_client import PNCPClient

        pncp = PNCPClient()

        # Detalhes da contratação
        detalhes = pncp.buscar_contratacao_detalhes(
            cnpj=cnpj_orgao,
            ano=ano_compra,
            sequencial=sequencial_compra,
        )

        if not detalhes:
            return json.dumps({
                "encontrado": False,
                "mensagem": f"Contratação não encontrada: {cnpj_orgao}/{ano_compra}/{sequencial_compra}",
            }, ensure_ascii=False)

        # Itens
        itens = pncp.buscar_itens(
            cnpj=cnpj_orgao,
            ano=ano_compra,
            sequencial=sequencial_compra,
        )

        # Resultados do primeiro item (para ter uma amostra)
        resultados_amostra = []
        if itens:
            numero_item = itens[0].get("numeroItem", 1)
            resultados_amostra = pncp.buscar_resultados_item(
                cnpj=cnpj_orgao,
                ano=ano_compra,
                sequencial=sequencial_compra,
                numero_item=numero_item,
            )

        return json.dumps({
            "encontrado": True,
            "contratacao": detalhes,
            "itens": itens,
            "resultados_amostra": resultados_amostra,
        }, ensure_ascii=False, default=str)
