#!/usr/bin/env python3
"""
Pipeline completo: coleta todas as plataformas, analisa editais,
calcula comparativo de mercado e preços de referência.

Uso:
    python pipeline_completo.py                    # Tudo (30 dias)
    python pipeline_completo.py --dias 60          # Últimos 60 dias
    python pipeline_completo.py --de 20250101 --ate 20251231
    python pipeline_completo.py --so-comparativo   # Só recalcula comparativo
    python pipeline_completo.py --so-coleta        # Só coleta, sem calcular
    python pipeline_completo.py --limpar           # Limpa dados antigos ao final
    python pipeline_completo.py --verbose          # Log detalhado (HTTP, debug)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime

log = logging.getLogger("pipeline")

# ── Etapas do pipeline ──────────────────────────────────────────────

ETAPAS = [
    ("DIAGNÓSTICO INICIAL", "diagnostico"),
    ("COLETA DE PLATAFORMAS", "coleta_plataformas"),
    ("COLETA DE ITENS PENDENTES", "coleta_pendentes"),
    ("COLETA DE RESULTADOS PENDENTES", "coleta_resultados"),
    ("ANÁLISE DE EDITAIS", "analise_editais"),
    ("COMPARATIVO DE MERCADO", "comparativo"),
    ("PREÇOS DE REFERÊNCIA", "precos"),
    ("LIMPEZA DE DADOS ANTIGOS", "limpeza"),
    ("DIAGNÓSTICO FINAL", "diagnostico"),
]


def _tempo(inicio: float) -> str:
    elapsed = time.time() - inicio
    if elapsed < 60:
        return f"{elapsed:.0f}s"
    if elapsed < 3600:
        return f"{elapsed / 60:.1f}min"
    return f"{elapsed / 3600:.1f}h"


def _banner(etapa_num: int, total_etapas: int, nome: str, status: str = ""):
    """Imprime banner bem visível para cada etapa."""
    barra = f"[{etapa_num}/{total_etapas}]"
    if status:
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {barra} {nome} — {status}", flush=True)
        print(f"{'=' * 60}\n", flush=True)
    else:
        print(f"\n{'=' * 60}", flush=True)
        print(f"  {barra} {nome}", flush=True)
        print(f"{'=' * 60}\n", flush=True)


def _progresso(msg: str):
    """Print de progresso inline."""
    print(f"  → {msg}", flush=True)


# ── Funções de cada etapa ───────────────────────────────────────────


def etapa_diagnostico():
    """Mostra estado atual dos dados."""
    from db import get_client
    from market_comparison.constants import CONCORRENTES

    c = get_client()

    _progresso("Itens por plataforma (com estimado > 0):")
    for pid, nome in sorted(CONCORRENTES.items()):
        r = (
            c.table("itens_contratacao")
            .select("id", count="exact")
            .eq("plataforma_id", pid)
            .gt("valor_unitario_estimado", 0)
            .limit(1)
            .execute()
        )
        print(f"      {nome[:25]:25s} (id={pid:3d}): {r.count or 0:>6} itens", flush=True)

    r = c.table("comparativo_plataformas").select("id", count="exact").execute()
    _progresso(f"comparativo_plataformas: {r.count or 0} registros")

    r = c.table("comparativo_itens").select("id", count="exact").execute()
    _progresso(f"comparativo_itens: {r.count or 0} registros")

    r = c.table("licitacoes").select("id", count="exact").execute()
    _progresso(f"licitacoes: {r.count or 0} registros")


def etapa_coleta_plataformas(dias: int, data_de: str | None = None, data_ate: str | None = None):
    """Coleta itens de todas as plataformas concorrentes."""
    from config import Config
    from item_collector import coletar_por_plataforma
    from market_comparison.constants import CONCORRENTES

    todas = sorted(set(Config.PLATAFORMAS_ALVO) | set(CONCORRENTES.keys()))
    total = len(todas)

    if data_de and data_ate:
        _progresso(f"Período: {data_de} → {data_ate}")
    else:
        _progresso(f"Período: últimos {dias} dias")
    _progresso(f"{total} plataformas a coletar")
    print("", flush=True)

    stats_global = {"contratacoes": 0, "itens": 0, "resultados": 0, "erros": 0}

    for i, plat_id in enumerate(todas, 1):
        nome = CONCORRENTES.get(plat_id, f"Plataforma {plat_id}")
        inicio = time.time()

        # Progresso visível antes de começar
        print(f"  [{i}/{total}] {nome} (id={plat_id})...", end=" ", flush=True)

        try:
            stats = coletar_por_plataforma(
                id_usuario=plat_id,
                dias=dias,
                data_de=data_de,
                data_ate=data_ate,
            )
            for k in stats_global:
                if k in stats:
                    stats_global[k] += stats[k]

            c = stats.get("contratacoes", 0)
            it = stats.get("itens", 0)
            res = stats.get("resultados", 0)
            print(f"{c} contr, {it} itens, {res} result ({_tempo(inicio)})", flush=True)

        except Exception as e:
            print(f"ERRO: {e} ({_tempo(inicio)})", flush=True)
            stats_global["erros"] += 1

    print("", flush=True)
    _progresso(
        f"Total: {stats_global['contratacoes']} contratações, "
        f"{stats_global['itens']} itens, "
        f"{stats_global['resultados']} resultados, "
        f"{stats_global['erros']} erros"
    )
    return stats_global


def etapa_coleta_pendentes():
    """Coleta itens de licitações existentes sem coleta."""
    from item_collector import coletar_pendentes
    stats = coletar_pendentes(limite=500)
    _progresso(f"Resultado: {stats}")
    return stats


def etapa_coleta_resultados():
    """Coleta resultados pendentes de itens já coletados."""
    from item_collector import coletar_resultados_pendentes
    stats = coletar_resultados_pendentes(limite=500)
    _progresso(f"Resultado: {stats}")
    return stats


def etapa_analise_editais():
    """Analisa editais de licitações pendentes."""
    from edital_analyzer import analisar_licitacoes_pendentes
    result = analisar_licitacoes_pendentes(limite=50)
    _progresso(f"Resultado: {result}")
    return result


def etapa_comparativo():
    """Calcula comparativo de mercado entre plataformas."""
    from market_analyzer import executar_comparativo
    executar_comparativo()
    _progresso("Concluído")


def etapa_precos():
    """Calcula preços de referência."""
    from price_analyzer import calcular_precos_pendentes
    calcular_precos_pendentes()
    _progresso("Concluído")


def etapa_limpeza():
    """Limpa dados antigos."""
    from cleanup import executar_limpeza
    executar_limpeza(dias=90, dry_run=False)


# ── Execução principal ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Pipeline completo Licitaê")
    parser.add_argument("--dias", type=int, default=30, help="Dias retroativos (default: 30)")
    parser.add_argument("--de", type=str, default=None, help="Data inicial YYYYMMDD")
    parser.add_argument("--ate", type=str, default=None, help="Data final YYYYMMDD")
    parser.add_argument("--so-comparativo", action="store_true", help="Só recalcula comparativo + preços")
    parser.add_argument("--so-coleta", action="store_true", help="Só coleta dados")
    parser.add_argument("--limpar", action="store_true", help="Limpa dados antigos ao final")
    parser.add_argument("--verbose", action="store_true", help="Log detalhado (HTTP, debug)")
    args = parser.parse_args()

    # Valida datas
    if (args.de and not args.ate) or (args.ate and not args.de):
        parser.error("Use --de e --ate juntos (ex: --de 20250101 --ate 20251231)")
    if args.de:
        for d, nome in [(args.de, "--de"), (args.ate, "--ate")]:
            if len(d) != 8 or not d.isdigit():
                parser.error(f"{nome} deve ser YYYYMMDD (ex: 20250101)")

    # Logging: silencia ruído dos módulos internos
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
        # Só mostra warnings/errors dos módulos internos
        # O progresso é via print() direto
        logging.getLogger("pipeline").setLevel(logging.INFO)

    # Monta lista de etapas a executar
    etapas_executar: list[tuple[str, callable, list]] = []

    etapas_executar.append(("DIAGNÓSTICO INICIAL", etapa_diagnostico, []))

    if not args.so_comparativo:
        etapas_executar.append(("COLETA DE PLATAFORMAS (PNCP)", etapa_coleta_plataformas, [args.dias, args.de, args.ate]))
        etapas_executar.append(("COLETA DE ITENS PENDENTES", etapa_coleta_pendentes, []))
        etapas_executar.append(("COLETA DE RESULTADOS PENDENTES", etapa_coleta_resultados, []))
        etapas_executar.append(("ANÁLISE DE EDITAIS", etapa_analise_editais, []))

    if not args.so_coleta:
        etapas_executar.append(("COMPARATIVO DE MERCADO", etapa_comparativo, []))
        etapas_executar.append(("PREÇOS DE REFERÊNCIA", etapa_precos, []))

    if args.limpar:
        etapas_executar.append(("LIMPEZA DE DADOS ANTIGOS", etapa_limpeza, []))

    etapas_executar.append(("DIAGNÓSTICO FINAL", etapa_diagnostico, []))

    total_etapas = len(etapas_executar)
    inicio_total = time.time()

    # Header
    print("", flush=True)
    print("╔" + "═" * 58 + "╗", flush=True)
    print(f"║  PIPELINE LICITAÊ — {datetime.now().strftime('%d/%m/%Y %H:%M'):37s} ║", flush=True)
    print(f"║  {total_etapas} etapas programadas{' ' * (37 - len(str(total_etapas)))}║", flush=True)
    print("╚" + "═" * 58 + "╝", flush=True)

    # Executa cada etapa
    resultados: list[tuple[str, str, str]] = []

    for i, (nome, fn, fn_args) in enumerate(etapas_executar, 1):
        _banner(i, total_etapas, nome)
        inicio = time.time()

        try:
            fn(*fn_args)
            duracao = _tempo(inicio)
            resultados.append((nome, "✓", duracao))
            _banner(i, total_etapas, nome, f"✓ concluído em {duracao}")
        except Exception as e:
            duracao = _tempo(inicio)
            resultados.append((nome, "✗", duracao))
            _banner(i, total_etapas, nome, f"✗ ERRO em {duracao}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()

    # Resumo final
    tempo_total = _tempo(inicio_total)
    print("", flush=True)
    print("╔" + "═" * 58 + "╗", flush=True)
    print(f"║  RESUMO — {tempo_total:47s} ║", flush=True)
    print("╠" + "═" * 58 + "╣", flush=True)
    for nome, status, duracao in resultados:
        linha = f"  {status} {nome[:42]:42s} {duracao:>8s}"
        print(f"║{linha:58s}║", flush=True)
    print("╚" + "═" * 58 + "╝", flush=True)
    print("", flush=True)


if __name__ == "__main__":
    main()
