"""Testes para scrapers de portais institucionais municipais."""

import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock

# Mock dependências externas antes de importar módulos
sys.modules["supabase"] = MagicMock()
sys.modules["dotenv"] = MagicMock()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scrapers.portais.registry import get_portal_config, PortalConfig, PORTAL_REGISTRY
from scrapers.portais.normalizer import normalizar_resultado_portal
from scrapers.portais.prefeitura_generica import (
    PrefeituraGenericaScraper,
    REGEX_PROCESSO,
    REGEX_DATA,
    REGEX_VALOR,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MUNICIPIO_FIXTURE = {
    "codigo_ibge": "3162500",
    "nome": "São João Del Rei",
    "uf": "MG",
    "populacao": 90000,
    "fpm": 2.6,
    "microrregiao_id": 31058,
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestPortalRegistry:
    def test_get_portal_config_existente(self):
        config = get_portal_config("3162500")  # São João Del Rei
        assert config is not None
        assert config.scraper_type == "prefeitura_generica"
        assert "saojoaodelrei" in config.url_base

    def test_get_portal_config_inexistente(self):
        config = get_portal_config("9999999")
        assert config is None

    def test_get_portal_config_inativo(self):
        # Testar com config inativa (sem modificar o registry global)
        cfg = PortalConfig(url_base="https://example.com", scraper_type="teste", ativo=False)
        original = PORTAL_REGISTRY.get("3162500")
        try:
            PORTAL_REGISTRY["_test_inativo"] = cfg
            assert get_portal_config("_test_inativo") is None
        finally:
            del PORTAL_REGISTRY["_test_inativo"]

    def test_todos_portais_tem_url_valida(self):
        for codigo, config in PORTAL_REGISTRY.items():
            assert config.url_base.startswith("https://"), f"{codigo}: URL inválida: {config.url_base}"
            assert config.scraper_type, f"{codigo}: scraper_type vazio"


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

class TestNormalizer:
    def test_normalizar_resultado_completo(self):
        raw = {
            "objeto": "Pregão para aquisição de software de gestão pública",
            "modalidade": "Pregão Eletrônico",
            "data_publicacao": "2026-04-01T00:00:00",
            "valor_estimado": 50000,
            "numero_processo": "001/2026",
            "orgao": "Prefeitura Municipal",
            "situacao": "Aberta",
        }
        result = normalizar_resultado_portal(raw, MUNICIPIO_FIXTURE, "https://example.com/lic/1")

        assert result["fonte"] == "PORTAL_MUNICIPAL"
        assert result["municipio"] == "São João Del Rei"
        assert result["uf"] == "MG"
        assert result["codigo_ibge"] == "3162500"
        assert result["objeto"] == "Pregão para aquisição de software de gestão pública"
        assert result["modalidade"] == "Pregão Eletrônico"
        assert result["valor_estimado"] == 50000
        assert result["numero_processo"] == "001/2026"
        assert result["seq_compra"] == "001/2026"
        assert result["ano_compra"] == "2026"
        assert result["url_fonte"] == "https://example.com/lic/1"
        assert result["url_pncp"] == ""
        assert result["valor_homologado"] == 0

    def test_normalizar_resultado_minimo(self):
        raw = {"objeto": "Teste"}
        result = normalizar_resultado_portal(raw, MUNICIPIO_FIXTURE, "https://example.com")

        assert result["fonte"] == "PORTAL_MUNICIPAL"
        assert result["objeto"] == "Teste"
        assert result["valor_estimado"] == 0
        assert result["cnpj_orgao"] == ""
        assert result["ano_compra"] == ""
        assert result["situacao"] == "Publicada"

    def test_normalizar_preserva_dados_municipio(self):
        raw = {"objeto": "Teste"}
        result = normalizar_resultado_portal(raw, MUNICIPIO_FIXTURE, "https://x.com")

        assert result["populacao"] == 90000
        assert result["fpm"] == 2.6


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

class TestRegexPatterns:
    def test_regex_processo_formato_barra(self):
        match = REGEX_PROCESSO.search("Processo nº 001/2026")
        assert match
        assert match.group(1) == "001/2026"

    def test_regex_processo_pregao(self):
        match = REGEX_PROCESSO.search("Pregão 015/2026 - Software")
        assert match
        assert match.group(1) == "015/2026"

    def test_regex_processo_ponto(self):
        match = REGEX_PROCESSO.search("Processo 001.2026")
        assert match
        assert match.group(1) == "001.2026"

    def test_regex_data_formato_completo(self):
        match = REGEX_DATA.search("Data: 15/04/2026")
        assert match
        assert match.group(1) == "15"
        assert match.group(2) == "04"
        assert match.group(3) == "2026"

    def test_regex_data_ano_curto(self):
        match = REGEX_DATA.search("15/04/26")
        assert match
        assert match.group(3) == "26"

    def test_regex_valor(self):
        match = REGEX_VALOR.search("R$ 50.000,00")
        assert match
        assert match.group(1) == "50.000,00"


# ---------------------------------------------------------------------------
# PrefeituraGenericaScraper
# ---------------------------------------------------------------------------

class TestPrefeituraGenericaScraper:
    def _make_scraper(self) -> PrefeituraGenericaScraper:
        return PrefeituraGenericaScraper(
            url_base="https://www.saojaodelrei.mg.gov.br",
            municipio=MUNICIPIO_FIXTURE,
        )

    def test_detectar_modalidade(self):
        scraper = self._make_scraper()
        assert scraper._detectar_modalidade("Pregão Eletrônico 001/2026") == "Pregão Eletrônico"
        assert scraper._detectar_modalidade("Tomada de Preço 002/2026") == "Tomada de Preços"
        assert scraper._detectar_modalidade("Dispensa de Licitação") == "Dispensa de Licitação"
        assert scraper._detectar_modalidade("Outro texto") == ""

    def test_parse_data_formato_completo(self):
        scraper = self._make_scraper()
        assert scraper._parse_data("15/04/2026") == "2026-04-15"

    def test_parse_data_ano_curto(self):
        scraper = self._make_scraper()
        assert scraper._parse_data("15/04/26") == "2026-04-15"

    def test_parse_data_invalida(self):
        scraper = self._make_scraper()
        assert scraper._parse_data("32/13/2026") == ""
        assert scraper._parse_data("texto sem data") == ""

    def test_parse_valor(self):
        scraper = self._make_scraper()
        assert scraper._parse_valor("R$ 50.000,00") == 50000.0
        assert scraper._parse_valor("R$ 1.234.567,89") == 1234567.89
        assert scraper._parse_valor("texto") == 0

    def test_parse_valor_simples(self):
        scraper = self._make_scraper()
        assert scraper._parse_valor("R$ 500,00") == 500.0

    def test_extrair_de_tabela_html(self):
        scraper = self._make_scraper()
        from bs4 import BeautifulSoup

        html = """
        <table>
            <tr>
                <th>Processo</th>
                <th>Objeto</th>
                <th>Modalidade</th>
                <th>Data</th>
                <th>Valor</th>
            </tr>
            <tr>
                <td>001/2026</td>
                <td><a href="/licitacao/1">Aquisição de software de gestão</a></td>
                <td>Pregão Eletrônico</td>
                <td>01/04/2026</td>
                <td>R$ 50.000,00</td>
            </tr>
            <tr>
                <td>002/2026</td>
                <td>Contratação de serviços de TI</td>
                <td>Tomada de Preços</td>
                <td>05/04/2026</td>
                <td>R$ 120.000,00</td>
            </tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        itens = scraper._extrair_de_tabela(soup, "https://example.com/licitacoes")

        assert len(itens) == 2
        assert itens[0]["objeto"] == "Aquisição de software de gestão"
        assert itens[0]["modalidade"] == "Pregão Eletrônico"
        assert itens[0]["numero_processo"] == "001/2026"
        assert itens[0]["data_publicacao"] == "2026-04-01T00:00:00"
        assert itens[0]["valor_estimado"] == 50000.0
        assert "licitacao/1" in itens[0]["url_fonte"]

        assert itens[1]["objeto"] == "Contratação de serviços de TI"
        assert itens[1]["valor_estimado"] == 120000.0

    def test_extrair_de_cards_html(self):
        scraper = self._make_scraper()
        from bs4 import BeautifulSoup

        html = """
        <div class="licitacao-card">
            <h3><a href="/licitacao/1">Pregão Eletrônico 001/2026 - Aquisição de licenças de software</a></h3>
            <p>Data: 01/04/2026 | Valor: R$ 75.000,00</p>
        </div>
        <div class="licitacao-card">
            <h3><a href="/licitacao/2">Dispensa 003/2026 - Manutenção de sistemas</a></h3>
            <p>Data: 03/04/2026</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        itens = scraper._extrair_de_cards(soup, "https://example.com/licitacoes")

        assert len(itens) == 2
        assert "software" in itens[0]["objeto"].lower()
        assert itens[0]["numero_processo"] == "001/2026"

    def test_texto_to_item(self):
        scraper = self._make_scraper()
        texto = "Pregão Eletrônico nº 015/2026 - Contratação de sistema de gestão pública. Abertura: 10/04/2026. Valor estimado: R$ 200.000,00"
        item = scraper._texto_to_item(texto, "https://example.com")

        assert item is not None
        assert item["numero_processo"] == "015/2026"
        assert item["modalidade"] == "Pregão Eletrônico"
        assert item["valor_estimado"] == 200000.0
        assert item["data_publicacao"] == "2026-04-10T00:00:00"

    def test_texto_to_item_curto_retorna_none(self):
        scraper = self._make_scraper()
        assert scraper._texto_to_item("curto", "https://x.com") is None

    def test_formatar_data(self):
        scraper = self._make_scraper()
        assert scraper._formatar_data("20260401") == "2026-04-01"
        assert scraper._formatar_data("2026-04-01") == "2026-04-01"

    def test_url_paginada(self):
        scraper = self._make_scraper()
        assert scraper._url_paginada("https://x.com/licitacoes", 1) == "https://x.com/licitacoes"
        assert scraper._url_paginada("https://x.com/licitacoes", 2) == "https://x.com/licitacoes?pagina=2"
        assert scraper._url_paginada("https://x.com/licitacoes?ano=2026", 2) == "https://x.com/licitacoes?ano=2026&pagina=2"
