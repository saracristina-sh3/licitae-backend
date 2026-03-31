#!/usr/bin/env python3
"""
Limpeza de dados antigos — remove dados brutos já processados.

Regras:
1. itens_contratacao + resultados_item: remove TODOS (dados brutos já foram
   processados nos comparativos/preços de referência)
2. licitacoes fechadas (proposta_aberta=false E valor_homologado > 0) com
   mais de 90 dias: remove com cascade
3. licitacoes abertas ou sem homologação: MANTÉM sempre

Uso:
    python cleanup.py                  # Mostra o que seria removido (dry-run)
    python cleanup.py --executar       # Executa a limpeza
    python cleanup.py --dias 60        # Licitações fechadas > 60 dias (default: 90)
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta

log = logging.getLogger("cleanup")


def _contar(client, tabela: str, filtros: dict | None = None) -> int:
    """Conta registros de uma tabela."""
    q = client.table(tabela).select("id", count="exact").limit(1)
    if filtros:
        for k, v in filtros.items():
            q = q.eq(k, v)
    result = q.execute()
    return result.count or 0


def limpar_itens_contratacao(client, dry_run: bool = True) -> int:
    """Remove todos os itens_contratacao e resultados_item (cascade)."""
    total_resultados = _contar(client, "resultados_item")
    total_itens = _contar(client, "itens_contratacao")

    log.info("  resultados_item: %d registros", total_resultados)
    log.info("  itens_contratacao: %d registros", total_itens)

    if total_itens == 0:
        log.info("  Nada a limpar")
        return 0

    if dry_run:
        log.info("  [DRY-RUN] Seria removido: %d itens + %d resultados", total_itens, total_resultados)
        return total_itens

    # Remove em lotes para não travar
    removidos = 0
    while True:
        batch = (
            client.table("itens_contratacao")
            .select("id")
            .limit(500)
            .execute()
        )
        ids = [r["id"] for r in (batch.data or [])]
        if not ids:
            break

        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            client.table("itens_contratacao").delete().in_("id", chunk).execute()
            removidos += len(chunk)

        log.info("  Removidos %d/%d itens...", removidos, total_itens)

    log.info("  Total removido: %d itens (+ resultados em cascade)", removidos)
    return removidos


def limpar_licitacoes_fechadas(client, dias: int = 90, dry_run: bool = True) -> int:
    """Remove licitações fechadas e homologadas com mais de X dias.

    Critério para remoção (TODOS devem ser verdadeiros):
    - proposta_aberta = false
    - valor_homologado > 0 (foi homologada)
    - data_encerramento_proposta < (hoje - dias)
    """
    data_corte = (datetime.now() - timedelta(days=dias)).isoformat()

    # Conta candidatas
    result = (
        client.table("licitacoes")
        .select("id", count="exact")
        .eq("proposta_aberta", False)
        .gt("valor_homologado", 0)
        .lt("data_encerramento_proposta", data_corte)
        .limit(1)
        .execute()
    )
    total = result.count or 0

    log.info("  Licitações fechadas + homologadas > %d dias: %d", dias, total)

    if total == 0:
        log.info("  Nada a limpar")
        return 0

    # Verifica o que NÃO será removido
    abertas = _contar(client, "licitacoes", {"proposta_aberta": True})
    sem_homologacao = (
        client.table("licitacoes")
        .select("id", count="exact")
        .eq("proposta_aberta", False)
        .eq("valor_homologado", 0)
        .limit(1)
        .execute()
    ).count or 0

    log.info("  Licitações MANTIDAS: %d abertas + %d sem homologação", abertas, sem_homologacao)

    if dry_run:
        log.info("  [DRY-RUN] Seria removido: %d licitações (com cascade em oportunidades, análises, etc.)", total)
        return total

    # Remove em lotes
    removidos = 0
    while True:
        batch = (
            client.table("licitacoes")
            .select("id")
            .eq("proposta_aberta", False)
            .gt("valor_homologado", 0)
            .lt("data_encerramento_proposta", data_corte)
            .limit(200)
            .execute()
        )
        ids = [r["id"] for r in (batch.data or [])]
        if not ids:
            break

        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            client.table("licitacoes").delete().in_("id", chunk).execute()
            removidos += len(chunk)

        log.info("  Removidas %d/%d licitações...", removidos, total)

    log.info("  Total removido: %d licitações (com cascade)", removidos)
    return removidos


def executar_limpeza(dias: int = 90, dry_run: bool = True):
    """Executa limpeza completa."""
    from db import get_client

    client = get_client()
    modo = "DRY-RUN (simulação)" if dry_run else "EXECUÇÃO REAL"

    log.info("=" * 60)
    log.info("LIMPEZA DE DADOS — %s", modo)
    log.info("=" * 60)
    log.info("")

    # 1. Itens de contratação (dados brutos)
    log.info("1. Itens de contratação + resultados (dados brutos)")
    t0 = time.time()
    itens_removidos = limpar_itens_contratacao(client, dry_run)
    log.info("  Tempo: %.1fs", time.time() - t0)
    log.info("")

    # 2. Licitações fechadas
    log.info("2. Licitações fechadas e homologadas > %d dias", dias)
    t0 = time.time()
    lics_removidas = limpar_licitacoes_fechadas(client, dias, dry_run)
    log.info("  Tempo: %.1fs", time.time() - t0)
    log.info("")

    log.info("=" * 60)
    log.info("RESUMO — %s", modo)
    log.info("  Itens removidos: %d", itens_removidos)
    log.info("  Licitações removidas: %d", lics_removidas)
    if dry_run:
        log.info("")
        log.info("  Para executar de verdade, rode com --executar")
    log.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Limpeza de dados antigos Licitaê")
    parser.add_argument("--executar", action="store_true", help="Executa a limpeza (sem isso, só simula)")
    parser.add_argument("--dias", type=int, default=90, help="Dias de retenção para licitações fechadas (default: 90)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    executar_limpeza(dias=args.dias, dry_run=not args.executar)


if __name__ == "__main__":
    main()
