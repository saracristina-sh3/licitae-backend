#!/usr/bin/env python3
"""
Licitaê - Plataforma de Inteligência em Licitações

Pipeline:
1. COLETA GENÉRICA: busca todas as licitações do PNCP (sem filtro de keywords)
2. COLETA DE ITENS: busca itens/resultados das licitações coletadas
3. PROSPECÇÃO POR ORG: aplica keywords/filtros de cada organização

Uso:
    python main.py                  # Coleta + prospecção (últimos 7 dias)
    python main.py --dias 30        # Últimos 30 dias
    python main.py --de 20260301 --ate 20260321
    python main.py --sem-email      # Não enviar email
    python main.py --sem-supabase   # Não gravar no Supabase
    python main.py --agendar        # Roda automaticamente
    python main.py --sync-municipios # Sincroniza municípios + microrregiões
    python main.py --dry-run        # Simula sem gravar
    python main.py --prospectar     # Roda apenas prospecção por org
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta

import schedule

from config import Config
from reports import gerar_excel, enviar_email

log = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _supabase_disponivel() -> bool:
    return bool(os.environ.get("SUPABASE_URL")) and bool(os.environ.get("SUPABASE_SERVICE_KEY"))


def sync_municipios():
    """Sincroniza municípios e microrregiões do IBGE no Supabase.

    Lê UFs de todas as org_configs para trazer tudo que as orgs precisam.
    """
    from municipios import carregar_municipios, carregar_microrregioes, vincular_municipios_microrregioes
    from db import sync_municipios as db_sync, sync_microrregioes as db_sync_micro
    from user_configs import carregar_configs_org, unificar_configs

    configs = carregar_configs_org()
    busca_config = unificar_configs(configs)
    ufs_sync = busca_config.get("ufs") or Config.UFS
    fpm_max = busca_config.get("fpm_maximo") or Config.POPULACAO_MAXIMA

    # 1. Sincronizar microrregiões
    log.info("Sincronizando microrregiões de %d UFs...", len(ufs_sync))
    micros = carregar_microrregioes(ufs_sync)
    count_micro = db_sync_micro(micros)
    log.info("Microrregiões sincronizadas: %d", count_micro)

    # 2. Sincronizar municípios (com vínculo de microrregião)
    log.info("Sincronizando municípios de %d UFs no Supabase...", len(ufs_sync))
    munis = carregar_municipios(ufs_sync, fpm_max)
    munis = vincular_municipios_microrregioes(munis, micros, ufs_sync)
    count = db_sync(munis)
    log.info("Municípios sincronizados: %d", count)
    for uf in sorted(ufs_sync):
        c = len([m for m in munis if m["uf"] == uf])
        if c > 0:
            log.info("  %s: %d", uf, c)


def executar_coleta(
    dias: int | None = None,
    data_de: str | None = None,
    data_ate: str | None = None,
    sem_supabase: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    """
    Executa coleta genérica de licitações (sem filtro de keywords).
    Persiste no banco para posterior prospecção por org.
    """
    log.info("=" * 60)
    log.info("COLETA GENÉRICA DE LICITAÇÕES%s", " (DRY RUN)" if dry_run else "")
    log.info("Execução: %s", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    log.info("=" * 60)

    from user_configs import carregar_configs_org, unificar_configs
    from prospection_engine.services.collection import coletar_licitacoes

    configs = carregar_configs_org()
    coleta_config = unificar_configs(configs)
    log.info("Configs carregadas: %d organização(ões)", len(configs))
    log.info("  UFs: %s", ", ".join(coleta_config["ufs"]))
    log.info("  Fontes: %s", ", ".join(coleta_config["fontes"]))

    resultados: list[dict] = []

    # Coleta PNCP (genérica, sem keywords)
    if "PNCP" in coleta_config["fontes"]:
        pncp = coletar_licitacoes(
            ufs=coleta_config["ufs"],
            modalidades=coleta_config["modalidades"],
            fpm_maximo=coleta_config["fpm_maximo"],
            dias_retroativos=dias,
            data_inicial=data_de,
            data_final=data_ate,
        )
        resultados.extend(pncp)
        log.info("PNCP: %d licitações coletadas", len(pncp))

    # Coleta Querido Diário
    if "QUERIDO_DIARIO" in coleta_config["fontes"]:
        if data_de and data_ate:
            dt_inicio, dt_fim = data_de, data_ate
        else:
            d = dias or Config.DIAS_RETROATIVOS
            hoje = datetime.now()
            inicio = hoje - timedelta(days=d)
            dt_inicio = inicio.strftime("%Y%m%d")
            dt_fim = hoje.strftime("%Y%m%d")
        try:
            from scrapers.querido_diario import buscar_querido_diario
            qd = buscar_querido_diario(dt_inicio, dt_fim)
            resultados.extend(qd)
            log.info("Querido Diário: %d resultados", len(qd))
        except Exception as e:
            log.error("Querido Diário: erro - %s", e)

    # Coleta TCE-RJ
    if "TCE_RJ" in coleta_config["fontes"] and "RJ" in coleta_config["ufs"]:
        if data_de and data_ate:
            dt_inicio, dt_fim = data_de, data_ate
        else:
            d = dias or Config.DIAS_RETROATIVOS
            hoje = datetime.now()
            inicio = hoje - timedelta(days=d)
            dt_inicio = inicio.strftime("%Y%m%d")
            dt_fim = hoje.strftime("%Y%m%d")
        try:
            from scrapers.tcerj import buscar_tcerj
            tcerj = buscar_tcerj(dt_inicio, dt_fim)
            resultados.extend(tcerj)
            log.info("TCE-RJ: %d resultados", len(tcerj))
        except Exception as e:
            log.error("TCE-RJ: erro - %s", e)

    log.info("Total coletado: %d (todas as fontes)", len(resultados))

    if dry_run:
        log.info("DRY RUN — não gravou no Supabase")
        return resultados

    # Grava no Supabase (sem score/relevância)
    usar_supabase = not sem_supabase and _supabase_disponivel()
    if usar_supabase and resultados:
        from db import inserir_licitacoes
        stats = inserir_licitacoes(resultados)
        log.info("  Inseridas: %d | Duplicadas: %d | Erros: %d",
                 stats["inseridas"], stats["duplicadas"], stats["erros"])

    log.info("Coleta concluída!")
    return resultados


def executar_prospeccao(dias: int | None = None, sem_email: bool = False):
    """
    Executa prospecção para todas as organizações.
    Aplica keywords/filtros de cada org sobre as licitações já coletadas.
    """
    log.info("=" * 60)
    log.info("PROSPECÇÃO POR ORGANIZAÇÃO")
    log.info("=" * 60)

    from prospection_engine.services.prospection import prospectar_todas_orgs
    d = dias or Config.DIAS_RETROATIVOS
    resultados = prospectar_todas_orgs(dias_retroativos=d)

    for r in resultados:
        log.info(
            "  Org %s: %d oportunidades (ALTA=%d, MEDIA=%d, BAIXA=%d)",
            r["org_id"], r["total"], r["alta"], r["media"], r["baixa"],
        )

    log.info("=" * 60)
    log.info("Prospecção concluída!")
    return resultados


def executar_busca(
    dias: int | None = None,
    data_de: str | None = None,
    data_ate: str | None = None,
    sem_email: bool = False,
    sem_supabase: bool = False,
    dry_run: bool = False,
):
    """Pipeline completo: coleta genérica → coleta de itens → prospecção por org."""
    # Fase 1: Coleta genérica
    resultados = executar_coleta(
        dias=dias, data_de=data_de, data_ate=data_ate,
        sem_supabase=sem_supabase, dry_run=dry_run,
    )

    if dry_run:
        return resultados

    # Fase 2: Coleta de itens das novas licitações
    if _supabase_disponivel():
        executar_coleta_itens(limite=len(resultados) or 100)

    # Fase 3: Prospecção por org
    if _supabase_disponivel():
        executar_prospeccao(dias=dias, sem_email=sem_email)

    return resultados


def executar_monitoramento():
    """Verifica mudanças nas licitações monitoradas pelos usuários."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado, pulando monitoramento")
        return
    try:
        from monitor import verificar_mudancas
        verificar_mudancas()
    except Exception as e:
        log.error("Erro no monitoramento: %s", e)


def executar_verificacao_prazos():
    """Verifica oportunidades com prazos próximos e envia alertas."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado, pulando verificação de prazos")
        return
    try:
        from deadline_alerts import verificar_prazos
        verificar_prazos()
    except Exception as e:
        log.error("Erro na verificação de prazos: %s", e)


def executar_analise_editais(limite: int = 10):
    """Analisa editais de licitações abertas que ainda não foram processados."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado, pulando análise de editais")
        return
    try:
        from edital_analyzer import analisar_licitacoes_pendentes
        analisar_licitacoes_pendentes(limite)
    except Exception as e:
        log.error("Erro na análise de editais: %s", e)


def executar_coleta_itens(limite: int = 100):
    """Coleta itens e resultados de licitações pendentes."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado, pulando coleta de itens")
        return
    try:
        from item_collector import coletar_pendentes
        stats = coletar_pendentes(limite=limite)
        log.info("Coleta de itens: %s", stats)
    except Exception as e:
        log.error("Erro na coleta de itens: %s", e)


def executar_coleta_resultados(limite: int = 200):
    """Coleta resultados pendentes de itens já coletados."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado, pulando coleta de resultados")
        return
    try:
        from item_collector import coletar_resultados_pendentes
        stats = coletar_resultados_pendentes(limite=limite)
        log.info("Coleta de resultados: %s", stats)
    except Exception as e:
        log.error("Erro na coleta de resultados: %s", e)


def executar_coleta_plataforma(id_usuario: int, dias: int = 30, uf: str | None = None):
    """Coleta contratações + itens de uma plataforma específica."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado")
        return
    try:
        from item_collector import coletar_por_plataforma
        stats = coletar_por_plataforma(id_usuario=id_usuario, dias=dias, uf=uf)
        log.info("Coleta plataforma %d: %s", id_usuario, stats)
    except Exception as e:
        log.error("Erro na coleta por plataforma: %s", e)


def executar_comparativo_mercado():
    """Calcula comparativo de mercado entre plataformas."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado, pulando comparativo de mercado")
        return
    try:
        from market_analyzer import executar_comparativo
        executar_comparativo()
    except Exception as e:
        log.error("Erro no comparativo de mercado: %s", e)


def executar_precos_referencia():
    """Calcula preços de referência para licitações abertas."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado, pulando preços de referência")
        return
    try:
        from price_analyzer import calcular_precos_pendentes
        calcular_precos_pendentes()
    except Exception as e:
        log.error("Erro nos preços de referência: %s", e)


def executar_envio_convites():
    """Envia emails de convite pendentes."""
    if not _supabase_disponivel():
        log.info("Supabase não configurado, pulando envio de convites")
        return
    try:
        from invite_email import enviar_convites_pendentes
        enviar_convites_pendentes()
    except Exception as e:
        log.error("Erro no envio de convites: %s", e)


def _executar_com_log(nome: str, fn, *args, **kwargs):
    """Executa uma função com log de início/fim e duração."""
    import time as _time
    log.info("▶ [%s] Iniciando...", nome)
    inicio = _time.time()
    try:
        resultado = fn(*args, **kwargs)
        duracao = _time.time() - inicio
        log.info("✓ [%s] Concluído em %.1fs — %s", nome, duracao, resultado or "OK")
        return resultado
    except Exception as e:
        duracao = _time.time() - inicio
        log.error("✗ [%s] Falhou em %.1fs — %s", nome, duracao, e)
        return None


def executar_pipeline_diario():
    """Pipeline sequencial com dependências corretas."""
    log.info("=" * 60)
    log.info("PIPELINE DIÁRIO — %s", datetime.now().strftime("%d/%m/%Y %H:%M"))
    log.info("=" * 60)

    # Fase 1: Coleta genérica de licitações (sem keywords)
    _executar_com_log("Coleta genérica PNCP", executar_coleta)

    # Fase 2: Enriquecimento (depende da Fase 1)
    _executar_com_log("Coleta de itens", executar_coleta_itens)
    _executar_com_log("Análise de editais", executar_analise_editais)

    # Fase 3: Resultados (depende da Fase 2 - itens)
    _executar_com_log("Coleta de resultados", executar_coleta_resultados)

    # Fase 4: Prospecção por org (depende das Fases 1-3)
    _executar_com_log("Prospecção por organização", executar_prospeccao)

    # Fase 5: Inteligência (depende das Fases 2-3)
    _executar_com_log("Comparativo de mercado", executar_comparativo_mercado)
    _executar_com_log("Preços de referência", executar_precos_referencia)

    log.info("=" * 60)
    log.info("PIPELINE DIÁRIO CONCLUÍDO")
    log.info("=" * 60)


def executar_coleta_plataformas():
    """Coleta itens de todas as plataformas-alvo (semanal)."""
    from item_collector import coletar_por_plataforma

    plataformas = Config.PLATAFORMAS_ALVO
    log.info("Coleta semanal de %d plataformas: %s", len(plataformas), plataformas)

    for plat_id in plataformas:
        _executar_com_log(
            f"Plataforma {plat_id}",
            coletar_por_plataforma,
            id_usuario=plat_id,
            dias=30,
        )


def executar_syncs_semanais():
    """Sync de municípios e plataformas (semanal)."""
    _executar_com_log("Sync municípios", sync_municipios)
    try:
        from platform_mapper import popular_plataformas_conhecidas
        _executar_com_log("Sync plataformas", popular_plataformas_conhecidas)
    except Exception as e:
        log.error("Erro no sync de plataformas: %s", e)


def agendar():
    """Agenda automação completa com pipeline sequencial."""
    log.info("=" * 60)
    log.info("AGENDADOR LICITAÊ")
    log.info("=" * 60)
    log.info("  08:00 — Verificação de prazos + alertas")
    log.info("  12:00 — Pipeline diário (busca → editais → itens → resultados → comparativo → preços)")
    log.info("  4h    — Monitoramento de mudanças")
    log.info("  30min — Envio de convites")
    log.info("  Dom 06:00 — Syncs semanais (municípios, plataformas)")
    log.info("  Dom 07:00 — Coleta de plataformas-alvo")
    log.info("=" * 60)

    # Diário
    schedule.every().day.at("08:00").do(executar_verificacao_prazos)
    schedule.every().day.at("12:00").do(executar_pipeline_diario)

    # Recorrente
    schedule.every(4).hours.do(executar_monitoramento)
    schedule.every(30).minutes.do(executar_envio_convites)

    # Semanal (domingo)
    schedule.every().sunday.at("06:00").do(executar_syncs_semanais)
    schedule.every().sunday.at("07:00").do(executar_coleta_plataformas)

    # Executa imediatamente na primeira vez
    log.info("Execução inicial...")
    executar_verificacao_prazos()
    executar_envio_convites()
    executar_pipeline_diario()
    executar_monitoramento()

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="Licitaê — Coleta genérica + prospecção por organização"
    )
    parser.add_argument("--dias", type=int, help="Dias retroativos para buscar (padrão: 7)")
    parser.add_argument("--de", dest="data_de", help="Data inicial (YYYYMMDD)")
    parser.add_argument("--ate", dest="data_ate", help="Data final (YYYYMMDD)")
    parser.add_argument("--sem-email", action="store_true", help="Não enviar email, só gerar planilha")
    parser.add_argument("--sem-supabase", action="store_true", help="Não gravar no Supabase")
    parser.add_argument("--agendar", action="store_true", help="Rodar semanalmente (segunda 8h)")
    parser.add_argument("--sync-municipios", action="store_true", help="Sincroniza municípios no Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Simula busca sem gravar nem enviar")
    parser.add_argument("--monitorar", action="store_true", help="Verifica mudanças em licitações monitoradas")
    parser.add_argument("--verificar-prazos", action="store_true", help="Verifica prazos próximos e envia alertas")
    parser.add_argument("--analisar-editais", action="store_true", help="Analisa editais de licitações abertas")
    parser.add_argument("--analisar-todos-editais", action="store_true", help="Analisa editais de TODAS as licitações (abertas + encerradas)")
    parser.add_argument("--limite-editais", type=int, default=10, help="Quantidade de editais para analisar (padrão: 10)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Logs detalhados (DEBUG)")
    parser.add_argument(
        "--carregar-municipios",
        action="store_true",
        help="Apenas carrega/atualiza cache local de municípios",
    )
    parser.add_argument("--sync-plataformas", action="store_true", help="Popula tabela de plataformas PNCP")
    parser.add_argument("--coletar-itens", action="store_true", help="Coleta itens de licitações pendentes")
    parser.add_argument("--coletar-resultados", action="store_true", help="Coleta resultados pendentes")
    parser.add_argument("--coletar-plataforma", type=int, metavar="ID", help="Coleta itens de uma plataforma (idUsuario)")
    parser.add_argument("--limite-itens", type=int, default=100, help="Limite de licitações para coleta (padrão: 100)")
    parser.add_argument("--uf-coleta", help="Filtrar coleta por UF (ex: MG)")
    parser.add_argument("--dias-coleta", type=int, default=30, help="Dias retroativos para coleta (padrão: 30)")
    parser.add_argument("--calcular-comparativo", action="store_true", help="Calcula comparativo de mercado entre plataformas")
    parser.add_argument("--calcular-precos", action="store_true", help="Calcula preços de referência para licitações abertas")
    parser.add_argument("--prospectar", action="store_true", help="Roda prospecção por org (sem nova coleta)")
    parser.add_argument("--apenas-coletar", action="store_true", help="Roda apenas coleta genérica (sem prospecção)")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.sync_municipios:
        if not _supabase_disponivel():
            log.error("SUPABASE_URL e SUPABASE_SERVICE_KEY não configurados no .env")
            return
        sync_municipios()
        return

    if args.carregar_municipios:
        from municipios import carregar_municipios

        munis = carregar_municipios(Config.UFS, Config.POPULACAO_MAXIMA)
        log.info("Municípios carregados: %d", len(munis))
        for uf in Config.UFS:
            count = len([m for m in munis if m["uf"] == uf])
            log.info("  %s: %d", uf, count)
        return

    if args.monitorar:
        if not _supabase_disponivel():
            log.error("SUPABASE_URL e SUPABASE_SERVICE_KEY não configurados no .env")
            return
        executar_monitoramento()
        return

    if args.verificar_prazos:
        if not _supabase_disponivel():
            log.error("SUPABASE_URL e SUPABASE_SERVICE_KEY não configurados no .env")
            return
        executar_verificacao_prazos()
        return

    if args.analisar_editais:
        if not _supabase_disponivel():
            log.error("SUPABASE_URL e SUPABASE_SERVICE_KEY não configurados no .env")
            return
        executar_analise_editais(args.limite_editais)
        return

    if args.analisar_todos_editais:
        if not _supabase_disponivel():
            log.error("SUPABASE_URL e SUPABASE_SERVICE_KEY não configurados no .env")
            return
        from edital_analysis.services.orchestration import analisar_licitacoes_pendentes
        resultado = analisar_licitacoes_pendentes(limite=args.limite_editais, somente_abertas=False)
        log.info("Análise completa: %s", resultado)
        return

    if args.sync_plataformas:
        if not _supabase_disponivel():
            log.error("SUPABASE_URL e SUPABASE_SERVICE_KEY não configurados no .env")
            return
        from platform_mapper import popular_plataformas_conhecidas
        count = popular_plataformas_conhecidas()
        log.info("Plataformas sincronizadas: %d", count)
        return

    if args.coletar_itens:
        executar_coleta_itens(args.limite_itens)
        return

    if args.coletar_resultados:
        executar_coleta_resultados(args.limite_itens)
        return

    if args.coletar_plataforma:
        executar_coleta_plataforma(
            id_usuario=args.coletar_plataforma,
            dias=args.dias_coleta,
            uf=args.uf_coleta,
        )
        return

    if args.calcular_comparativo:
        executar_comparativo_mercado()
        return

    if args.calcular_precos:
        executar_precos_referencia()
        return

    if args.prospectar:
        if not _supabase_disponivel():
            log.error("SUPABASE_URL e SUPABASE_SERVICE_KEY não configurados no .env")
            return
        executar_prospeccao(dias=args.dias)
        return

    if args.apenas_coletar:
        executar_coleta(
            dias=args.dias,
            data_de=args.data_de,
            data_ate=args.data_ate,
            sem_supabase=args.sem_supabase,
            dry_run=args.dry_run,
        )
        return

    if args.agendar:
        agendar()
        return

    executar_busca(
        dias=args.dias,
        data_de=args.data_de,
        data_ate=args.data_ate,
        sem_email=args.sem_email,
        sem_supabase=args.sem_supabase,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
