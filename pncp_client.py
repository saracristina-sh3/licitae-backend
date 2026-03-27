"""
Cliente para a API de Consulta do PNCP (Portal Nacional de Contratações Públicas).
API pública, sem autenticação.
Docs: https://pncp.gov.br/api/consulta/swagger-ui/index.html
"""

from __future__ import annotations

import time
import requests
from requests.adapters import HTTPAdapter, Retry
from config import Config


class PNCPClient:
    def __init__(self):
        self.base_url = Config.PNCP_BASE_URL
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "LicitacoesSoftware/1.0",
            }
        )
        # Retry automático em timeout, 5xx e 429 (rate limit)
        retries = Retry(
            total=5,
            backoff_factor=3,
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def buscar_contratacoes(
        self,
        data_inicial: str,
        data_final: str,
        modalidade: int,
        uf: str | None = None,
        codigo_municipio: str | None = None,
        pagina: int = 1,
        tamanho: int = 50,
    ) -> dict:
        params = {
            "dataInicial": data_inicial,
            "dataFinal": data_final,
            "codigoModalidadeContratacao": modalidade,
            "pagina": pagina,
            "tamanhoPagina": min(tamanho, 50),
        }

        if uf:
            params["uf"] = uf
        if codigo_municipio:
            params["codigoMunicipioIbge"] = codigo_municipio

        url = f"{self.base_url}/v1/contratacoes/publicacao"

        try:
            resp = self.session.get(url, params=params, timeout=20)
            if resp.status_code == 204:
                return {"data": [], "totalRegistros": 0, "totalPaginas": 0}
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 422:
                return {"data": [], "totalRegistros": 0, "totalPaginas": 0}
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return {"data": [], "totalRegistros": 0, "totalPaginas": 0}

    def buscar_todas_paginas(
        self,
        data_inicial: str,
        data_final: str,
        modalidade: int,
        uf: str | None = None,
        codigo_municipio: str | None = None,
        delay: float = 0.5,
    ) -> list[dict]:
        """Busca todas as páginas de resultados."""
        todos = []
        pagina = 1

        while True:
            resultado = self.buscar_contratacoes(
                data_inicial=data_inicial,
                data_final=data_final,
                modalidade=modalidade,
                uf=uf,
                codigo_municipio=codigo_municipio,
                pagina=pagina,
            )

            registros = resultado.get("data", [])
            if not registros:
                break

            todos.extend(registros)

            total_paginas = resultado.get("totalPaginas", 0)
            if pagina >= total_paginas:
                break

            pagina += 1
            time.sleep(delay)

        return todos

    def buscar_contratacoes_por_plataforma(
        self,
        id_usuario: int,
        data_inicial: str,
        data_final: str,
        modalidade: int,
        uf: str | None = None,
        pagina: int = 1,
        tamanho: int = 50,
    ) -> dict:
        """Busca contratações filtradas por plataforma (idUsuario PNCP)."""
        params = {
            "dataInicial": data_inicial,
            "dataFinal": data_final,
            "codigoModalidadeContratacao": modalidade,
            "idUsuario": id_usuario,
            "pagina": pagina,
            "tamanhoPagina": min(tamanho, 50),
        }
        if uf:
            params["uf"] = uf

        url = f"{self.base_url}/v1/contratacoes/publicacao"

        try:
            resp = self.session.get(url, params=params, timeout=20)
            if resp.status_code == 204:
                return {"data": [], "totalRegistros": 0, "totalPaginas": 0}
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 422:
                return {"data": [], "totalRegistros": 0, "totalPaginas": 0}
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return {"data": [], "totalRegistros": 0, "totalPaginas": 0}

    def buscar_contratacao_detalhes(self, cnpj: str, ano: int, sequencial: int) -> dict | None:
        """Busca detalhes de uma contratação específica."""
        url = f"{Config.PNCP_COMPRAS_URL}/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}"
        try:
            resp = self.session.get(url, timeout=60)
            if resp.status_code == 204:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError:
            return None

    def buscar_itens(self, cnpj: str, ano: int, sequencial: int) -> list[dict]:
        """Busca itens de uma contratação específica (API de compras)."""
        url = f"{Config.PNCP_COMPRAS_URL}/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 204:
                return []
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("data", [])
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (404, 422):
                return []
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return []

    def buscar_resultados_item(
        self, cnpj: str, ano: int, sequencial: int, numero_item: int
    ) -> list[dict]:
        """Busca resultados (preço homologado) de um item específico."""
        url = (
            f"{Config.PNCP_COMPRAS_URL}/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}"
            f"/itens/{numero_item}/resultados"
        )
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 204:
                return []
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("data", [])
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (404, 422):
                return []
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return []
