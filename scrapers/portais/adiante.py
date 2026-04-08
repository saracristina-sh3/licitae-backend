"""
Scraper para portais de transparência baseados na plataforma Adiante.

Muitos municípios pequenos de MG usam a plataforma Adiante para transparência.
URLs típicas:
- https://{municipio}.adiabordo.com.br/licitacoes
- https://transparencia.{municipio}.mg.gov.br (com backend Adiante)

A plataforma usa uma API REST interna para carregar dados via JavaScript.
Este scraper acessa a API diretamente quando possível, com fallback para HTML.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from scrapers.portais.base import PortalScraper

log = logging.getLogger(__name__)

# Caminhos conhecidos da plataforma Adiante
CAMINHOS_API_ADIANTE = [
    "/api/licitacoes",
    "/api/v1/licitacoes",
    "/licitacoes/api",
]

CAMINHOS_HTML_ADIANTE = [
    "/licitacoes",
    "/portal/licitacoes",
    "/transparencia/licitacoes",
]

REGEX_PROCESSO = re.compile(
    r"(?:processo|nº|n°|numero|número)\s*[.:nº°-]*\s*(\d{1,4}[/.-]\d{2,4})",
    re.IGNORECASE,
)

REGEX_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{2,4})\b")


class AdianteScraper(PortalScraper):
    """Scraper para portais baseados na plataforma Adiante."""

    def buscar(self, data_inicial: str, data_final: str) -> list[dict]:
        data_ini = self._formatar_data(data_inicial)
        data_fim = self._formatar_data(data_final)

        # Tentar via API primeiro
        resultados = self._buscar_via_api(data_ini, data_fim)
        if resultados is not None:
            log.info("  %s [Adiante/API]: %d publicações", self.municipio["nome"], len(resultados))
            return resultados

        self._politeness_delay()

        # Fallback: parsing de HTML
        resultados = self._buscar_via_html(data_ini, data_fim)
        log.info("  %s [Adiante/HTML]: %d publicações", self.municipio["nome"], len(resultados))
        return resultados

    def _buscar_via_api(self, data_ini: str, data_fim: str) -> list[dict] | None:
        """Tenta buscar licitações via API REST interna da Adiante."""
        for caminho in CAMINHOS_API_ADIANTE:
            url = f"{self.url_base}{caminho}"
            params = {
                "data_inicio": data_ini,
                "data_fim": data_fim,
                "page": 1,
                "per_page": 50,
            }

            data = self._get_json(url, params=params)
            if data is None:
                continue

            # A API pode retornar lista direta ou dict com chave "data"/"items"
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("data", data.get("items", data.get("licitacoes", [])))

            if not items:
                continue

            resultados = []
            for item in items:
                parsed = self._parse_item_api(item)
                if parsed and parsed.get("objeto"):
                    resultados.append(parsed)

            return resultados

        return None

    def _parse_item_api(self, item: dict) -> dict | None:
        """Converte item da API Adiante para formato bruto."""
        objeto = (
            item.get("objeto")
            or item.get("descricao")
            or item.get("description")
            or ""
        )
        if not objeto:
            return None

        data_pub = (
            item.get("data_publicacao")
            or item.get("data_abertura")
            or item.get("created_at")
            or ""
        )
        # Normalizar para ISO
        if data_pub and "T" not in data_pub:
            data_pub = f"{data_pub[:10]}T00:00:00"

        valor = 0
        for campo in ["valor_estimado", "valor", "valor_total"]:
            v = item.get(campo)
            if v and isinstance(v, (int, float)):
                valor = float(v)
                break

        return {
            "objeto": objeto[:500],
            "modalidade": item.get("modalidade", ""),
            "data_publicacao": data_pub,
            "data_abertura": item.get("data_abertura", ""),
            "data_encerramento": item.get("data_encerramento", ""),
            "valor_estimado": valor,
            "numero_processo": item.get("numero_processo", item.get("numero", "")),
            "orgao": item.get("orgao", self.municipio["nome"]),
            "cnpj": item.get("cnpj", ""),
            "situacao": item.get("situacao", item.get("status", "Publicada")),
            "url_fonte": item.get("url", ""),
            "exclusivo_me_epp": item.get("exclusivo_me_epp", False),
        }

    def _buscar_via_html(self, data_ini: str, data_fim: str) -> list[dict]:
        """Fallback: parsing de HTML da listagem de licitações."""
        resultados = []

        for caminho in CAMINHOS_HTML_ADIANTE:
            url = f"{self.url_base}{caminho}"
            soup = self._get_soup(url)
            if not soup:
                continue

            # Adiante usa cards com classe típica
            cards = soup.find_all(
                ["div", "tr", "article", "li"],
                class_=re.compile(r"licit|card|item|row", re.IGNORECASE),
            )

            if not cards:
                # Tentar tabelas genéricas
                for table in soup.find_all("table"):
                    for row in table.find_all("tr")[1:]:  # pular header
                        item = self._parse_row_html(row)
                        if item:
                            resultados.append(item)
                continue

            for card in cards:
                item = self._parse_card_html(card)
                if not item or not item.get("objeto"):
                    continue

                data_pub = item.get("data_publicacao", "")[:10]
                if data_pub and data_ini <= data_pub <= data_fim:
                    resultados.append(item)

            if resultados:
                break

        return resultados

    def _parse_card_html(self, card) -> dict | None:
        """Extrai informações de um card HTML da Adiante."""
        texto = card.get_text(" ", strip=True)
        if len(texto) < 15:
            return None

        # Extrair link
        link = card.find("a", href=True)
        url_item = urljoin(self.url_base, link["href"]) if link else ""

        # Extrair dados via regex
        processo = ""
        match = REGEX_PROCESSO.search(texto)
        if match:
            processo = match.group(1)

        data_pub = ""
        match_data = REGEX_DATA.search(texto)
        if match_data:
            dia, mes, ano = match_data.group(1), match_data.group(2), match_data.group(3)
            if len(ano) == 2:
                ano = f"20{ano}"
            try:
                datetime(int(ano), int(mes), int(dia))
                data_pub = f"{ano}-{mes}-{dia}"
            except ValueError:
                pass

        return {
            "objeto": texto[:500],
            "modalidade": "",
            "data_publicacao": f"{data_pub}T00:00:00" if data_pub else "",
            "data_abertura": "",
            "data_encerramento": "",
            "valor_estimado": 0,
            "numero_processo": processo,
            "orgao": self.municipio["nome"],
            "cnpj": "",
            "situacao": "Publicada",
            "url_fonte": url_item,
            "exclusivo_me_epp": False,
        }

    def _parse_row_html(self, row) -> dict | None:
        """Extrai informações de uma linha de tabela HTML."""
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            return None

        texto = " ".join(c.get_text(strip=True) for c in cells)
        if len(texto) < 15:
            return None

        link = row.find("a", href=True)
        url_item = urljoin(self.url_base, link["href"]) if link else ""

        return self._parse_card_html(row)
