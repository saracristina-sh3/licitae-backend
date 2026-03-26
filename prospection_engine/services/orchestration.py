"""
Orquestração do pipeline de prospecção v1.

Pipeline:
1. Resolve config + período + municípios + janelas
2. ThreadPoolExecutor: busca + filtra + match por (UF × Modalidade)
3. Deduplicação pós-coleta
4. Score + urgência + montagem de resultado
5. Sort por score DESC, data_publicacao DESC
6. Log com SearchStats
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Generator

from config import Config
from municipios import carregar_municipios
from pncp_client import PNCPClient
from prospection_engine.constants import MODALIDADE_NOMES
from prospection_engine.services.deduplication import deduplicar
from prospection_engine.services.filtering import proposta_encerrada, resolver_municipio
from prospection_engine.services.matching import match_contratacao
from prospection_engine.services.result_builder import montar_resultado
from prospection_engine.services.scoring import calcular_score, calcular_urgencia
from prospection_engine.types import BuscaConfig, MatchResult, ResultadoLicitacao, SearchStats

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _gerar_janelas(dt_inicio: str, dt_fim: str, dias: int = 1) -> list[tuple[str, str]]:
    """Divide o período [dt_inicio, dt_fim] em janelas de até `dias` dias."""
    inicio = datetime.strptime(dt_inicio, "%Y%m%d")
    fim = datetime.strptime(dt_fim, "%Y%m%d")
    janelas: list[tuple[str, str]] = []
    atual = inicio
    while atual <= fim:
        janela_fim = min(atual + timedelta(days=dias - 1), fim)
        janelas.append((atual.strftime("%Y%m%d"), janela_fim.strftime("%Y%m%d")))
        atual = janela_fim + timedelta(days=1)
    return janelas


def _resolver_periodo(
    dias_retroativos: int | None,
    data_inicial: str | None,
    data_final: str | None,
) -> tuple[str, str]:
    """Retorna (dt_inicio, dt_fim) no formato YYYYMMDD."""
    if data_inicial and data_final:
        return data_inicial, data_final

    dias = dias_retroativos or Config.DIAS_RETROATIVOS
    hoje = datetime.now()
    inicio = hoje - timedelta(days=dias)
    return inicio.strftime("%Y%m%d"), hoje.strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Núcleo de busca por (UF × Modalidade)
# ---------------------------------------------------------------------------


def _buscar_e_filtrar_uf_modalidade(
    uf: str,
    modalidade: int,
    janelas: list[tuple[str, str]],
    mapa_municipios: dict[str, dict],
    cfg: BuscaConfig,
    client: PNCPClient,
    stats: SearchStats,
) -> list[tuple[dict, dict, MatchResult]]:
    """
    Busca, filtra e faz matching de uma combinação (UF, modalidade).
    Retorna lista de (contratacao, mun_info, match_result).
    """
    mod_nome = MODALIDADE_NOMES.get(modalidade, str(modalidade))
    candidatos: list[tuple[dict, dict, MatchResult]] = []
    total_contratacoes = 0

    log.info("  %s - %s: iniciando busca (%d janelas)", uf, mod_nome, len(janelas))

    for j_inicio, j_fim in janelas:
        try:
            contratacoes = client.buscar_todas_paginas(
                data_inicial=j_inicio,
                data_final=j_fim,
                modalidade=modalidade,
                uf=uf,
            )
        except Exception as exc:
            log.warning(
                "  %s - %s: falha na janela %s-%s — %s: %s",
                uf, mod_nome, j_inicio, j_fim, type(exc).__name__, exc,
                exc_info=True,
            )
            continue

        total_contratacoes += len(contratacoes)

        for c in contratacoes:
            # Filtro 1: proposta encerrada
            if proposta_encerrada(c):
                stats.total_filtradas_proposta += 1
                continue

            # Filtro 2: município no mapa-alvo
            mun_info = resolver_municipio(c, mapa_municipios)
            if not mun_info:
                stats.total_filtradas_municipio += 1
                continue

            # Filtro 3: matching multi-campo
            match = match_contratacao(c, cfg.palavras_chave, cfg.termos_exclusao)

            if not match.matched:
                if cfg.termos_exclusao and any(
                    t in (c.get("objetoCompra", "") or "") for t in cfg.termos_exclusao
                ):
                    stats.total_filtradas_exclusao += 1
                else:
                    stats.total_filtradas_keyword += 1
                continue

            candidatos.append((c, mun_info, match))

    stats.total_contratacoes += total_contratacoes
    stats.stats_por_uf[uf] = stats.stats_por_uf.get(uf, 0) + len(candidatos)

    log.info(
        "  %s - %s: %d relevantes de %d total",
        uf, mod_nome, len(candidatos), total_contratacoes,
    )
    return candidatos


# ---------------------------------------------------------------------------
# Gerador de contratações brutas (streaming)
# ---------------------------------------------------------------------------


def iterar_contratacoes(
    cfg: BuscaConfig,
    dt_inicio: str,
    dt_fim: str,
    client: PNCPClient,
) -> Generator[tuple[str, int, dict], None, None]:
    """
    Gera tuplas (uf, modalidade, contratacao_bruta) sem filtro.
    Útil para pipelines que precisam de acesso às contratações antes do filtro.
    """
    janelas = _gerar_janelas(dt_inicio, dt_fim, cfg.janela_dias)
    for uf in cfg.ufs:
        for modalidade in cfg.modalidades:
            for j_inicio, j_fim in janelas:
                try:
                    for c in client.buscar_todas_paginas(
                        data_inicial=j_inicio,
                        data_final=j_fim,
                        modalidade=modalidade,
                        uf=uf,
                    ):
                        yield uf, modalidade, c
                except Exception as exc:
                    log.warning(
                        "iterar_contratacoes — %s/%s janela %s-%s: %s",
                        uf, modalidade, j_inicio, j_fim, exc,
                        exc_info=True,
                    )


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------


def buscar_licitacoes(
    dias_retroativos: int | None = None,
    data_inicial: str | None = None,
    data_final: str | None = None,
    busca_config: dict | BuscaConfig | None = None,
) -> list[ResultadoLicitacao]:
    """
    Busca licitações nos municípios-alvo e retorna lista ordenada por score.

    Assinatura idêntica à versão anterior para backward compatibility.
    """
    run_id = uuid.uuid4().hex[:12]
    stats = SearchStats(run_id=run_id)
    t0 = time.monotonic()

    # --- Resolver configuração ---
    if isinstance(busca_config, dict):
        cfg = BuscaConfig.from_dict(busca_config)
    elif isinstance(busca_config, BuscaConfig):
        cfg = busca_config
    else:
        cfg = BuscaConfig()

    # --- Resolver período ---
    dt_inicio, dt_fim = _resolver_periodo(dias_retroativos, data_inicial, data_final)
    log.info("[%s] Período de busca: %s a %s", run_id, dt_inicio, dt_fim)

    # --- Carregar municípios ---
    municipios = carregar_municipios(cfg.ufs, cfg.fpm_maximo)
    mapa_municipios: dict[str, dict] = {m["codigo_ibge"]: m for m in municipios}
    log.info(
        "[%s] Municípios-alvo: %d (%s) | Palavras-chave: %d | Exclusão: %d",
        run_id,
        len(municipios),
        ", ".join(cfg.ufs),
        len(cfg.palavras_chave),
        len(cfg.termos_exclusao),
    )

    # --- Preparar janelas ---
    janelas = _gerar_janelas(dt_inicio, dt_fim, cfg.janela_dias)
    log.info(
        "[%s] %d janelas de até %d dia(s) | workers: %d",
        run_id, len(janelas), cfg.janela_dias, cfg.max_workers,
    )

    # --- Executar em paralelo ---
    client = PNCPClient()
    candidatos: list[tuple[dict, dict, MatchResult]] = []

    with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
        futures = {
            executor.submit(
                _buscar_e_filtrar_uf_modalidade,
                uf, modalidade, janelas, mapa_municipios, cfg, client, stats,
            ): (uf, modalidade)
            for uf in cfg.ufs
            for modalidade in cfg.modalidades
        }

        for future in as_completed(futures):
            uf, modalidade = futures[future]
            try:
                parcial = future.result()
                candidatos.extend(parcial)
            except Exception as exc:
                mod_nome = MODALIDADE_NOMES.get(modalidade, str(modalidade))
                log.error(
                    "[%s] Tarefa %s/%s falhou: %s",
                    run_id, uf, mod_nome, exc,
                    exc_info=True,
                )

    # --- Scoring ---
    for contratacao, _mun_info, match in candidatos:
        match.score = calcular_score(match, contratacao, cfg)

    # --- Deduplicação ---
    unicos = deduplicar(candidatos)
    stats.total_duplicatas = len(candidatos) - len(unicos)

    # --- Montagem de resultados ---
    resultados: list[ResultadoLicitacao] = []
    for contratacao, mun_info, match in unicos:
        urgencia = calcular_urgencia(contratacao.get("dataEncerramentoProposta"))
        resultados.append(montar_resultado(contratacao, mun_info, match, cfg, urgencia))

    # --- Ordenar: score DESC, data_publicacao DESC ---
    resultados.sort(
        key=lambda r: (-r["score"], r["data_publicacao"]),
        reverse=True,
    )

    # --- Stats ---
    stats.total_resultados = len(resultados)
    stats.tempo_total_ms = round((time.monotonic() - t0) * 1000, 1)

    log.info(
        "[%s] Busca concluída: %d resultados (de %d contratações) | "
        "filtradas: proposta=%d, município=%d, keyword=%d, exclusão=%d | "
        "duplicatas=%d | %.1fs",
        run_id,
        stats.total_resultados,
        stats.total_contratacoes,
        stats.total_filtradas_proposta,
        stats.total_filtradas_municipio,
        stats.total_filtradas_keyword,
        stats.total_filtradas_exclusao,
        stats.total_duplicatas,
        stats.tempo_total_ms / 1000,
    )

    if stats.stats_por_uf:
        log.info("[%s] Por UF: %s", run_id, stats.stats_por_uf)

    return resultados
