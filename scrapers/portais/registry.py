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
    url_licitacoes: str | None = None
    ativo: bool = True


# ---------------------------------------------------------------------------
# Registro de portais — Campo das Vertentes (MG)
# Mesorregião: Campo das Vertentes (id 3111)
# Microrregiões: Lavras (31057), São João Del Rei (31058), Barbacena (31059)
# ---------------------------------------------------------------------------

PORTAL_REGISTRY: dict[str, PortalConfig] = {
    # ── Microrregião de Barbacena (31059) ──────────────────────────────────

    "3105608": PortalConfig(  # Barbacena
        url_base="https://www.barbacena.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3101706": PortalConfig(  # Alfredo Vasconcelos
        url_base="https://www.alfredovasconcelos.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3104205": PortalConfig(  # Antônio Carlos
        url_base="https://www.antoniocarlos.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3106200": PortalConfig(  # Barroso
        url_base="https://www.barroso.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3119401": PortalConfig(  # Desterro do Melo
        url_base="https://www.desterrodomelo.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3146107": PortalConfig(  # Oliveira Fortes
        url_base="https://www.oliveirafortes.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3152501": PortalConfig(  # Ressaquinha
        url_base="https://www.ressaquinha.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3156809": PortalConfig(  # Santa Bárbara do Tugúrio
        url_base="https://www.santabarbaradotugurio.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3163904": PortalConfig(  # Santos Dumont
        url_base="https://www.santosdumont.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),

    # ── Microrregião de São João Del Rei (31058) ──────────────────────────

    "3162500": PortalConfig(  # São João Del Rei
        url_base="https://www.saojaodelrei.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3115300": PortalConfig(  # Conceição da Barra de Minas
        url_base="https://www.conceicaodabarrademinas.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3117306": PortalConfig(  # Coronel Xavier Chaves
        url_base="https://www.coronelxavierchaves.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3141009": PortalConfig(  # Madre de Deus de Minas
        url_base="https://www.madrededeusdeminas.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3143401": PortalConfig(  # Nazareno
        url_base="https://www.nazareno.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3150604": PortalConfig(  # Prados
        url_base="https://www.prados.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3153905": PortalConfig(  # Ritápolis
        url_base="https://www.ritapolis.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3157005": PortalConfig(  # Santa Cruz de Minas
        url_base="https://www.santacruzdeminas.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3165206": PortalConfig(  # São Tiago
        url_base="https://www.saotiago.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3170404": PortalConfig(  # Tiradentes
        url_base="https://www.tiradentes.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),

    # ── Microrregião de Lavras (31057) ────────────────────────────────────

    "3138203": PortalConfig(  # Lavras
        url_base="https://www.lavras.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3132800": PortalConfig(  # Ijaci
        url_base="https://www.ijaci.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3133758": PortalConfig(  # Ibituruna
        url_base="https://www.ibituruna.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3134202": PortalConfig(  # Ingaí
        url_base="https://www.ingai.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3138674": PortalConfig(  # Luminárias
        url_base="https://www.luminarias.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3144607": PortalConfig(  # Nepomuceno
        url_base="https://www.nepomuceno.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3153806": PortalConfig(  # Ribeirão Vermelho
        url_base="https://www.ribeiraovermelho.mg.gov.br",
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
