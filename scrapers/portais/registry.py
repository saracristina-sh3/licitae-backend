"""
Registro de portais institucionais municipais.
Mapeia codigo_ibge → configuração do portal (URL, tipo de scraper).

Começando com Campo das Vertentes (MG):
- Microrregião de Lavras (31057)
- Microrregião de São João Del Rei (31058)
- Microrregião de Barbacena (31059)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PortalConfig:
    """Configuração de um portal institucional municipal."""

    url_base: str
    scraper_type: str
    urls_licitacoes: list[str] | None = None
    ativo: bool = True


# ---------------------------------------------------------------------------
# Registro de portais — Campo das Vertentes (MG)
# Mesorregião: Campo das Vertentes (id 3111)
# Microrregiões: Lavras (31057), São João Del Rei (31058), Barbacena (31059)
#
# NOTA: Municípios cujos sites usam o CMS "Cadastro Genérico" (com URLs
# /pagina/{id}/...) foram removidos por estarem bloqueados pelo Cloudflare
# para IPs de datacenter. Lista mantida abaixo apenas os que funcionam
# com requests HTTP padrão.
# ---------------------------------------------------------------------------

PORTAL_REGISTRY: dict[str, PortalConfig] = {
    # ── Microrregião de Barbacena (31059) ──────────────────────────────────

    "3105608": PortalConfig(  # Barbacena
        url_base="https://www.barbacena.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),

    # ── Microrregião de Lavras (31057) ────────────────────────────────────

    "3138203": PortalConfig(  # Lavras
        url_base="https://www.lavras.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3144607": PortalConfig(  # Nepomuceno
        url_base="https://www.nepomuceno.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
}


def get_portal_config(codigo_ibge: str) -> PortalConfig | None:
    """Retorna config do portal para um município, ou None se não cadastrado/inativo."""
    config = PORTAL_REGISTRY.get(codigo_ibge)
    if config and config.ativo:
        return config
    return None


# Mapeamento tipo → caminho de importação do scraper
SCRAPER_TYPES: dict[str, str] = {
    "prefeitura_generica": "scrapers.portais.prefeitura_generica.PrefeituraGenericaScraper",
    "adiante": "scrapers.portais.adiante.AdianteScraper",
}
