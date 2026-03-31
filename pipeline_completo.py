#!/usr/bin/env python3
"""
Pipeline completo: coleta todas as plataformas, analisa editais,
calcula comparativo de mercado e preços de referência.

Uso:
    python pipeline_completo.py                    # Tudo (30 dias)
    python pipeline_completo.py --dias 60          # Últimos 60 dias
    python pipeline_completo.py --so-comparativo   # Só recalcula comparativo
    python pipeline_completo.py --so-coleta        # Só coleta, sem calcular
    python pipeline_completo.py --verbose          # Log detalhado
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime

log = logging.getLogger("pipeline")


def _tempo(inicio: float) -> str:
    elapsed = time.time() - inicio
    if elapsed < 60:
        return f"{elapsed:.1f}s"
    return f"{elapsed / 60:.1f}min"


def _etapa(nome: str, fn, *args, **kwargs):
    """Executa uma etapa com log de início/fim e duração."""
    log.info("")
    log.info("▶ %s", nome)
    log.info("-" * 50)
    inicio = time.time()
    try:
        resultado = fn(*args, **kwargs)
        log.info("✓ %s concluído em %s — %s", nome, _tempo(inicio), resultado or "OK")
        return resultado
    except Exception as e:
        log.error("✗ %s falhou em %s — %s", nome, _tempo(inicio), e)
        import traceback
        traceback.print_exc()
        return None


def etapa_coleta_plataformas(dias: int):
    """Coleta itens de todas as plataformas concorrentes."""
    from config import Config
    from item_collector import coletar_por_plataforma
    from market_comparison.constants import CONCORRENTES

    # Une plataformas-alvo + concorrentes do comparativo
    todas = set(Config.PLATAFORMAS_ALVO) | set(CONCORRENTES.keys())
    total = len(todas)

    log.info("Plataformas a coletar (%d): %s", total, sorted(todas))
    log.info("Período: últimos %d dias", dias)

    stats_global = {"contratacoes": 0, "itens": 0, "resultados": 0, "erros": 0}

    for i, plat_id in enumerate(sorted(todas), 1):
        nome = CONCORRENTES.get(plat_id, f"Plataforma {plat_id}")
        log.info("")
        log.info("  [%d/%d] %s (id=%d)...", i, total, nome, plat_id)
        inicio = time.time()

        try:
            stats = coletar_por_plataforma(id_usuario=plat_id, dias=dias)
            for k in stats_global:
                if k in stats:
                    stats_global[k] += stats[k]
            log.info(
                "  [%d/%d] %s: %d contratações, %d itens, %d resultados (%s)",
                i, total, nome,
                stats.get("contratacoes", 0),
                stats.get("itens", 0),
                stats.get("resultados", 0),
                _tempo(inicio),
            )
        except Exception as e:
            log.error("  [%d/%d] %s: ERRO — %s", i, total, nome, e)
            stats_global["erros"] += 1

    return stats_global


def etapa_coleta_pendentes():
    """Coleta itens de licitações existentes que ainda não foram processadas."""
    from item_collector import coletar_pendentes
    return coletar_pendentes(limite=500)


def etapa_coleta_resultados():
    """Coleta resultados pendentes de itens já coletados."""
    from item_collector import coletar_resultados_pendentes
    return coletar_resultados_pendentes(limite=500)


def etapa_analise_editais():
    """Analisa editais de licitações pendentes."""
    from edital_analyzer import analisar_licitacoes_pendentes
    return analisar_licitacoes_pendentes(limite=50)


def etapa_comparativo():
    """Calcula comparativo de mercado entre plataformas."""
    from market_analyzer import executar_comparativo
    executar_comparativo()
    return "OK"


def etapa_precos():
    """Calcula preços de referência."""
    from price_analyzer import calcular_precos_pendentes
    calcular_precos_pendentes()
    return "OK"


def etapa_diagnostico():
    """Mostra estado atual dos dados (roda antes e depois)."""
    from db import get_client
    from market_comparison.constants import CONCORRENTES

    c = get_client()

    log.info("  Itens por plataforma (com estimado > 0):")
    for pid, nome in sorted(CONCORRENTES.items()):
        r = (
            c.table("itens_contratacao")
            .select("id", count="exact")
            .eq("plataforma_id", pid)
            .gt("valor_unitario_estimado", 0)
            .limit(1)
            .execute()
        )
        log.info("    %s (id=%d): %s itens", nome[:25], pid, r.count)

    r = (
        c.table("comparativo_plataformas")
        .select("id", count="exact")
        .execute()
    )
    log.info("  comparativo_plataformas: %s registros", r.count)

    r = (
        c.table("comparativo_itens")
        .select("id", count="exact")
        .execute()
    )
    log.info("  comparativo_itens: %s registros", r.count)


def main():
    parser = argparse.ArgumentParser(description="Pipeline completo Licitaê")
    parser.add_argument("--dias", type=int, default=30, help="Dias retroativos para coleta (default: 30)")
    parser.add_argument("--so-comparativo", action="store_true", help="Só recalcula comparativo + preços (sem coleta)")
    parser.add_argument("--so-coleta", action="store_true", help="Só coleta dados (sem calcular)")
    parser.add_argument("--verbose", action="store_true", help="Log detalhado (DEBUG)")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    inicio_total = time.time()
    log.info("=" * 60)
    log.info("PIPELINE COMPLETO LICITAÊ — %s", datetime.now().strftime("%d/%m/%Y %H:%M"))
    log.info("=" * 60)

    # Diagnóstico inicial
    _etapa("Diagnóstico inicial", etapa_diagnostico)

    if not args.so_comparativo:
        # Fase 1: Coleta de todas as plataformas
        _etapa("Coleta de plataformas (PNCP)", etapa_coleta_plataformas, args.dias)

        # Fase 2: Coleta pendentes e resultados
        _etapa("Coleta de itens pendentes", etapa_coleta_pendentes)
        _etapa("Coleta de resultados pendentes", etapa_coleta_resultados)

        # Fase 3: Análise de editais
        _etapa("Análise de editais", etapa_analise_editais)

    if not args.so_coleta:
        # Fase 4: Cálculos
        _etapa("Comparativo de mercado", etapa_comparativo)
        _etapa("Preços de referência", etapa_precos)

    # Diagnóstico final
    _etapa("Diagnóstico final", etapa_diagnostico)

    log.info("")
    log.info("=" * 60)
    log.info("PIPELINE CONCLUÍDO em %s", _tempo(inicio_total))
    log.info("=" * 60)


if __name__ == "__main__":
    main()
