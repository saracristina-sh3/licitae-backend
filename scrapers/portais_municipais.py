"""
Scraper: Portais Institucionais Municipais
Coleta publicações de licitações diretamente de sites de prefeituras,
câmaras e consórcios que podem não enviar dados ao PNCP.

Início regional: Campo das Vertentes (MG).
"""

from __future__ import annotations

import importlib
import logging
import time
from datetime import datetime

from config import Config
from municipios import carregar_municipios
from scrapers.portais.base import PortalScraper
from scrapers.portais.normalizer import normalizar_resultado_portal
from scrapers.portais.registry import (
    PORTAL_REGISTRY,
    SCRAPER_TYPES,
    get_portal_config,
)

log = logging.getLogger(__name__)

# IDs das microrregiões de Campo das Vertentes (MG)
MICRORREGIOES_CAMPO_DAS_VERTENTES = [31057, 31058, 31059]

# Intervalo mínimo entre scrapes do mesmo município (horas)
INTERVALO_MIN_HORAS = 12


def buscar_portais_municipais(
    data_inicial: str,
    data_final: str,
    microrregioes_ids: list[int] | None = None,
) -> list[dict]:
    """
    Coleta licitações de portais institucionais municipais.

    Args:
        data_inicial: Data início no formato YYYYMMDD.
        data_final: Data fim no formato YYYYMMDD.
        microrregioes_ids: IDs de microrregiões para filtrar (default: Campo das Vertentes).

    Returns:
        Lista de dicts normalizados para a tabela licitacoes.
    """
    if microrregioes_ids is None:
        microrregioes_ids = MICRORREGIOES_CAMPO_DAS_VERTENTES

    # Carregar municípios de MG filtrados por microrregião
    municipios = carregar_municipios(["MG"], Config.POPULACAO_MAXIMA)
    municipios_alvo = [
        m for m in municipios
        if m.get("microrregiao_id") in microrregioes_ids
    ]

    # Incluir também municípios que estão no registry mas não passaram pelo filtro de FPM
    # (cidades maiores da região que têm portal cadastrado)
    codigos_alvo = {m["codigo_ibge"] for m in municipios_alvo}
    todos_mg = carregar_municipios(["MG"], 999999)
    for m in todos_mg:
        if (
            m["codigo_ibge"] in PORTAL_REGISTRY
            and m["codigo_ibge"] not in codigos_alvo
            and m.get("microrregiao_id") in microrregioes_ids
        ):
            municipios_alvo.append(m)
            codigos_alvo.add(m["codigo_ibge"])

    log.info("Portais Municipais: %d municípios-alvo na região", len(municipios_alvo))

    resultados: list[dict] = []
    stats = {"sucesso": 0, "sem_portal": 0, "erro": 0, "pulado": 0}

    for mun in municipios_alvo:
        codigo = mun["codigo_ibge"]
        portal_config = get_portal_config(codigo)

        if not portal_config:
            stats["sem_portal"] += 1
            continue

        # Verificar scraping incremental
        if _scrape_recente(codigo):
            stats["pulado"] += 1
            log.debug("  %s: scrape recente, pulando", mun["nome"])
            continue

        inicio = time.time()

        try:
            scraper = _instanciar_scraper(
                portal_config.scraper_type,
                portal_config.url_base,
                mun,
                portal_config.urls_licitacoes,
            )
            if not scraper:
                stats["erro"] += 1
                continue

            brutos = scraper.buscar(data_inicial, data_final)

            for raw in brutos:
                url_fonte = raw.get("url_fonte", portal_config.url_base)
                normalizado = normalizar_resultado_portal(raw, mun, url_fonte)
                resultados.append(normalizado)

            duracao = int((time.time() - inicio) * 1000)
            _registrar_scrape(codigo, portal_config, "success", len(brutos), None, duracao)
            stats["sucesso"] += 1

        except Exception as e:
            duracao = int((time.time() - inicio) * 1000)
            _registrar_scrape(codigo, portal_config, "error", 0, str(e), duracao)
            stats["erro"] += 1
            log.error("  %s: erro no scraping - %s", mun["nome"], e)

    log.info(
        "Portais Municipais: %d resultados | sucesso=%d sem_portal=%d erro=%d pulado=%d",
        len(resultados),
        stats["sucesso"],
        stats["sem_portal"],
        stats["erro"],
        stats["pulado"],
    )

    return resultados


def _instanciar_scraper(
    scraper_type: str,
    url_base: str,
    municipio: dict,
    urls_licitacoes: list[str] | None = None,
) -> PortalScraper | None:
    """Instancia o scraper correto via strategy pattern."""
    class_path = SCRAPER_TYPES.get(scraper_type)
    if not class_path:
        log.warning("Tipo de scraper desconhecido: %s", scraper_type)
        return None

    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        scraper_class = getattr(module, class_name)
        return scraper_class(
            url_base=url_base,
            municipio=municipio,
            urls_licitacoes=urls_licitacoes,
        )
    except Exception as e:
        log.error("Erro ao instanciar scraper %s: %s", scraper_type, e)
        return None


def _scrape_recente(codigo_ibge: str) -> bool:
    """Verifica se o município foi scrapeado recentemente."""
    try:
        from db import get_client
        result = (
            get_client()
            .table("portal_scrape_log")
            .select("created_at")
            .eq("codigo_ibge", codigo_ibge)
            .eq("status", "success")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return False

        ultimo = datetime.fromisoformat(
            result.data[0]["created_at"].replace("Z", "+00:00")
        )
        agora = datetime.now(ultimo.tzinfo)
        horas = (agora - ultimo).total_seconds() / 3600
        return horas < INTERVALO_MIN_HORAS
    except Exception:
        return False


def _registrar_scrape(
    codigo_ibge: str,
    portal_config,
    status: str,
    licitacoes: int,
    erro: str | None,
    duracao_ms: int,
):
    """Registra o resultado do scrape na tabela portal_scrape_log."""
    try:
        from db import get_client
        get_client().table("portal_scrape_log").insert({
            "codigo_ibge": codigo_ibge,
            "url_base": portal_config.url_base,
            "scraper_type": portal_config.scraper_type,
            "status": status,
            "licitacoes_encontradas": licitacoes,
            "erro_mensagem": erro,
            "duracao_ms": duracao_ms,
        }).execute()
    except Exception as e:
        log.warning("Falha ao registrar scrape log: %s", e)
