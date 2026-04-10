"""
Classe base para scrapers de portais institucionais municipais.
Cada CMS/plataforma implementa uma subclasse com lógica de parsing específica.

Usa curl_cffi para emular TLS fingerprint de browser real e evitar
bloqueio por Cloudflare/WAF.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from curl_cffi.requests import Session
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
POLITENESS_DELAY = 1.5


class PortalScraper(ABC):
    """Classe base para scrapers de portais municipais."""

    def __init__(
        self,
        url_base: str,
        municipio: dict,
        session: Session | None = None,
        urls_licitacoes: list[str] | None = None,
    ):
        self.url_base = url_base.rstrip("/")
        self.municipio = municipio
        self.urls_licitacoes = urls_licitacoes or []
        self.session = session or Session(impersonate="chrome131")

    @abstractmethod
    def buscar(self, data_inicial: str, data_final: str) -> list[dict]:
        """
        Coleta publicações de licitações do portal.

        Args:
            data_inicial: Data início no formato YYYYMMDD.
            data_final: Data fim no formato YYYYMMDD.

        Returns:
            Lista de dicts com campos brutos (pré-normalização):
                objeto, modalidade, data_publicacao, valor_estimado,
                numero_processo, orgao, cnpj, situacao, url_fonte,
                data_abertura, data_encerramento, exclusivo_me_epp
        """
        ...

    def _get_soup(self, url: str, timeout: int = REQUEST_TIMEOUT) -> BeautifulSoup | None:
        """Busca URL e retorna BeautifulSoup parseado, ou None em caso de erro."""
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            log.warning("Erro ao acessar %s: %s", url, e)
            return None

    def _get_json(self, url: str, params: dict | None = None, timeout: int = REQUEST_TIMEOUT) -> dict | list | None:
        """Busca URL esperando JSON, ou None em caso de erro."""
        try:
            resp = self.session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.warning("Erro ao acessar JSON %s: %s", url, e)
            return None

    def _politeness_delay(self):
        """Delay respeitoso entre requests ao mesmo host."""
        time.sleep(POLITENESS_DELAY)

    def _formatar_data(self, data_yyyymmdd: str) -> str:
        """Converte YYYYMMDD para YYYY-MM-DD."""
        if len(data_yyyymmdd) == 8:
            return f"{data_yyyymmdd[:4]}-{data_yyyymmdd[4:6]}-{data_yyyymmdd[6:8]}"
        return data_yyyymmdd
