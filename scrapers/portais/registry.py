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
        url_base="https://www.saojoaodelrei.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=[
            "https://www.saojoaodelrei.mg.gov.br/pagina/21735/Pregão",
            "https://www.saojoaodelrei.mg.gov.br/pagina/21736/Concorrência%202026",
            "https://www.saojoaodelrei.mg.gov.br/pagina/22373/Credenciamento%202026",
            "https://www.saojoaodelrei.mg.gov.br/pagina/19629/Dispensa%202025",
        ],
    ),
    "3115300": PortalConfig(  # Conceição da Barra de Minas
        url_base="https://cbm.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://cbm.mg.gov.br/pagina/21072/2026"],
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
        url_base="https://nazareno.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://nazareno.mg.gov.br/pagina/21034/Editais%202026"],
    ),
    "3150604": PortalConfig(  # Prados
        url_base="https://prados.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://prados.mg.gov.br/pagina/1744/Editais"],
    ),
    "3153905": PortalConfig(  # Ritápolis
        url_base="https://ritapolis.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://ritapolis.mg.gov.br/pagina/6668/Editais"],
    ),
    "3157005": PortalConfig(  # Santa Cruz de Minas
        url_base="https://www.santacruzdeminas.mg.gov.br",
        scraper_type="prefeitura_generica",
    ),
    "3165206": PortalConfig(  # São Tiago
        url_base="https://www.saotiago.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://camarasaotiago.mg.gov.br/pagina/20974/Licitações%20-%202026"],
    ),
    "3170404": PortalConfig(  # Tiradentes
        url_base="https://www.tiradentes.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://www.tiradentes.mg.gov.br/pagina/21066/%202026"],
    ),
    "3122504": PortalConfig(  # Dores de Campos
        url_base="https://doresdecampos.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://doresdecampos.mg.gov.br/pagina/21119/Editais%202026"],
    ),
    "3137007": PortalConfig(  # Lagoa Dourada
        url_base="https://www.lagoadourada.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://www.lagoadourada.mg.gov.br/pagina/2952/Licitações"],
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
        url_base="https://ibituruna.mg.gov.br",
        scraper_type="prefeitura_generica",
        urls_licitacoes=["https://ibituruna.mg.gov.br/pagina/21131/Editais%20de%20Licitação%202026"],
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
