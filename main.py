#!/usr/bin/env python3
"""
Licitações de Software - Buscador PNCP + Supabase
Busca licitações de permissão de uso de software em municípios
de MG e RJ com FPM até 2.8.

Uso:
    python main.py                  # Busca últimos 7 dias
    python main.py --dias 30        # Busca últimos 30 dias
    python main.py --de 20260301 --ate 20260321
    python main.py --sem-email      # Só gera planilha
    python main.py --sem-supabase   # Não grava no Supabase
    python main.py --agendar        # Roda semanalmente
    python main.py --sync-municipios # Sincroniza municípios no Supabase
    python main.py --dry-run        # Simula busca sem gravar
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta

import schedule

from config import Config
from search import buscar_licitacoes
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
    """Sincroniza municípios do IBGE no Supabase.

    Lê UFs de todas as org_configs para trazer tudo que as orgs precisam.
    """
    from municipios import carregar_municipios
    from db import sync_municipios as db_sync
    from user_configs import carregar_configs_org, unificar_configs

    configs = carregar_configs_org()
    busca_config = unificar_configs(configs)
    ufs_sync = busca_config.get("ufs") or Config.UFS
    fpm_max = busca_config.get("fpm_maximo") or Config.POPULACAO_MAXIMA

    log.info("Sincronizando municípios de %d UFs no Supabase...", len(ufs_sync))
    munis = carregar_municipios(ufs_sync, fpm_max)
    count = db_sync(munis)
    log.info("Municípios sincronizados: %d", count)
    for uf in sorted(ufs_sync):
        c = len([m for m in munis if m["uf"] == uf])
        if c > 0:
            log.info("  %s: %d", uf, c)


def executar_busca(
    dias: int | None = None,
    data_de: str | None = None,
    data_ate: str | None = None,
    sem_email: bool = False,
    sem_supabase: bool = False,
    dry_run: bool = False,
):
    """Executa uma busca completa, grava no Supabase e gera relatórios."""
    log.info("=" * 60)
    log.info("BUSCADOR DE LICITAÇÕES%s", " (DRY RUN)" if dry_run else "")
    log.info("Execução: %s", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    log.info("=" * 60)

    # Carrega configurações das organizações
    from user_configs import carregar_configs_org, unificar_configs
    configs = carregar_configs_org()
    busca_config = unificar_configs(configs)
    log.info("Configs carregadas: %d organização(ões)", len(configs))
    log.info("  UFs: %s", ", ".join(busca_config["ufs"]))
    log.info("  Palavras-chave: %d termos", len(busca_config["palavras_chave"]))
    log.info("  Fontes: %s", ", ".join(busca_config["fontes"]))

    # Datas
    if data_de and data_ate:
        dt_inicio = data_de
        dt_fim = data_ate
    else:
        d = dias or Config.DIAS_RETROATIVOS
        hoje = datetime.now()
        inicio = hoje - timedelta(days=d)
        dt_inicio = inicio.strftime("%Y%m%d")
        dt_fim = hoje.strftime("%Y%m%d")

    resultados = []

    # Busca PNCP
    if "PNCP" in busca_config["fontes"]:
        pncp = buscar_licitacoes(
            dias_retroativos=dias,
            data_inicial=data_de,
            data_final=data_ate,
            busca_config=busca_config,
        )
        resultados.extend(pncp)
        log.info("PNCP: %d resultados", len(pncp))
    else:
        log.info("PNCP: desativado")

    # Busca Querido Diário
    if "QUERIDO_DIARIO" in busca_config["fontes"]:
        try:
            from scrapers.querido_diario import buscar_querido_diario
            log.info("Buscando no Querido Diário...")
            qd = buscar_querido_diario(dt_inicio, dt_fim)
            resultados.extend(qd)
            log.info("Querido Diário: %d resultados", len(qd))
        except Exception as e:
            log.error("Querido Diário: erro - %s", e)
    else:
        log.info("Querido Diário: desativado")

    # Busca TCE-RJ
    if "TCE_RJ" in busca_config["fontes"] and "RJ" in busca_config["ufs"]:
        try:
            from scrapers.tcerj import buscar_tcerj
            log.info("Buscando no TCE-RJ...")
            tcerj = buscar_tcerj(dt_inicio, dt_fim)
            resultados.extend(tcerj)
            log.info("TCE-RJ: %d resultados", len(tcerj))
        except Exception as e:
            log.error("TCE-RJ: erro - %s", e)
    else:
        log.info("TCE-RJ: desativado")

    log.info("=" * 60)
    log.info("Total encontrado: %d (todas as fontes)", len(resultados))

    if resultados:
        alta = len([r for r in resultados if r["relevancia"] == "ALTA"])
        media = len([r for r in resultados if r["relevancia"] == "MEDIA"])
        baixa = len([r for r in resultados if r["relevancia"] == "BAIXA"])
        valor = sum(r["valor_estimado"] for r in resultados)
        log.info("  ALTA: %d | MÉDIA: %d | BAIXA: %d", alta, media, baixa)
        log.info("  Valor total estimado: R$ %s", f"{valor:,.2f}")

    if dry_run:
        log.info("DRY RUN — não gravou no Supabase, não enviou email, não gerou Excel")
        return resultados

    # Grava no Supabase
    usar_supabase = not sem_supabase and _supabase_disponivel()
    if usar_supabase and resultados:
        from db import inserir_licitacoes

        log.info("Gravando no Supabase...")
        stats = inserir_licitacoes(resultados)
        log.info("  Inseridas: %d | Duplicadas: %d | Erros: %d",
                 stats["inseridas"], stats["duplicadas"], stats["erros"])
    elif not usar_supabase:
        log.info("Supabase não configurado, pulando gravação")

    # Gera Excel
    arquivo = gerar_excel(resultados)

    # Envia email
    if not sem_email:
        enviar_email(resultados, arquivo)
    else:
        log.info("Envio de email desabilitado (--sem-email)")

    log.info("=" * 60)
    log.info("Concluído!")
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


def agendar():
    """Agenda busca diária às 12h e monitoramento a cada 4h."""
    log.info("Agendador iniciado.")
    log.info("  Busca de licitações: diária às 12:00")
    log.info("  Monitoramento de mudanças: a cada 4 horas")
    log.info("  Verificação de prazos: diária às 08:00")
    log.info("  Análise de editais: diária às 13:00")
    log.info("  Comparativo de mercado: diária às 16:00")
    log.info("Pressione Ctrl+C para parar.")

    schedule.every().day.at("12:00").do(executar_busca)
    schedule.every(4).hours.do(executar_monitoramento)
    schedule.every().day.at("08:00").do(executar_verificacao_prazos)
    schedule.every().day.at("13:00").do(executar_analise_editais)
    schedule.every(30).minutes.do(executar_envio_convites)
    schedule.every().day.at("14:00").do(executar_coleta_itens)
    schedule.every().day.at("15:00").do(executar_coleta_resultados)
    schedule.every().day.at("16:00").do(executar_comparativo_mercado)
    schedule.every().day.at("17:00").do(executar_precos_referencia)

    # Executa imediatamente na primeira vez
    executar_busca()
    executar_monitoramento()
    executar_verificacao_prazos()
    executar_analise_editais()
    executar_envio_convites()
    executar_coleta_itens()
    executar_coleta_resultados()
    executar_comparativo_mercado()
    executar_precos_referencia()

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="Busca licitações de software no PNCP para municípios de MG e RJ com FPM até 2.8"
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
