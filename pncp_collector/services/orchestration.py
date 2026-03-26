"""
Orquestração do pipeline de coleta PNCP v2.

Três estratégias:
1. coletar_pendentes()          — itens de licitações existentes sem coleta
2. coletar_por_plataforma()     — contratações + itens por idUsuario
3. coletar_resultados_pendentes() — resultados de itens com tem_resultado=True
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from pncp_collector.constants import TipoFalha
from pncp_collector.services.payload_builder import montar_item_row, montar_resultado_row
from pncp_collector.services.pending import (
    buscar_itens_sem_resultado,
    buscar_licitacoes_sem_itens,
    extrair_url_parts,
)
from pncp_collector.services.persistence import (
    buscar_ids_itens,
    persistir_itens_batch,
    persistir_resultados_batch,
)
from pncp_collector.services.stats import StatsTracker
from pncp_collector.services.throttling import Throttler
from pncp_collector.services.validation import validar_item, validar_resultado
from pncp_collector.types import (
    Metadata,
    StatsColeta,
    StatsItens,
    StatsPlataforma,
    StatsResultados,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Núcleo: coleta de uma contratação
# ---------------------------------------------------------------------------


def _coletar_resultados_item(
    pncp: Any,
    item_id: str,
    cnpj: str,
    ano: int,
    sequencial: int,
    numero_item: int,
    tracker: StatsTracker,
    throttler: Throttler,
) -> list[dict]:
    """Busca resultados de um item na API e retorna rows validados."""
    throttler.esperar()

    try:
        resultados_api = pncp.buscar_resultados_item(cnpj, ano, sequencial, numero_item)
        throttler.registrar_sucesso()
    except Exception as exc:
        throttler.registrar_falha(TipoFalha.API)
        tracker.registrar_falha(TipoFalha.API, f"Resultados {cnpj}/{ano}/{sequencial}/{numero_item}: {exc}")
        return []

    tracker.registrar_resultados_retornados(len(resultados_api))

    rows = []
    for res in resultados_api:
        saneado = validar_resultado(res)
        if saneado is None:
            continue
        rows.append(montar_resultado_row(item_id, saneado))

    return rows


def coletar_itens_contratacao(
    pncp: Any,
    cnpj: str,
    ano: int,
    sequencial: int,
    licitacao_hash: str | None,
    metadata: Metadata,
    db_client: Any,
    tracker: StatsTracker | None = None,
    throttler: Throttler | None = None,
) -> StatsItens:
    """
    Coleta itens e resultados de uma contratação específica.
    Usa batch persistence e validação.
    """
    _tracker = tracker or StatsTracker()
    _throttler = throttler or Throttler()
    stats: StatsItens = {"itens": 0, "resultados": 0, "erros": 0}

    # 1. Busca itens da API
    try:
        itens_api = pncp.buscar_itens(cnpj, ano, sequencial)
        _throttler.registrar_sucesso()
    except Exception as exc:
        _throttler.registrar_falha(TipoFalha.API)
        _tracker.registrar_falha(TipoFalha.API, f"Itens {cnpj}/{ano}/{sequencial}: {exc}")
        stats["erros"] += 1
        return stats

    if not itens_api:
        return stats

    _tracker.registrar_itens_retornados(len(itens_api))

    # 2. Valida e monta rows
    item_rows: list[dict] = []
    itens_com_resultado: list[int] = []

    for item in itens_api:
        saneado = validar_item(item)
        if saneado is None:
            _tracker.registrar_item_descartado()
            continue

        _tracker.registrar_item_valido()
        row = montar_item_row(cnpj, ano, sequencial, licitacao_hash, saneado, metadata)
        item_rows.append(row)

        if saneado.get("temResultado"):
            itens_com_resultado.append(saneado["numeroItem"])

    # 3. Persiste itens em batch
    if item_rows:
        persistidos, falhas = persistir_itens_batch(db_client, item_rows)
        stats["itens"] = persistidos
        _tracker.registrar_itens_persistidos(persistidos)
        for tipo, msg in falhas:
            _tracker.registrar_falha(tipo, msg)
            stats["erros"] += 1

    # 4. Busca resultados dos itens com resultado
    if itens_com_resultado:
        # Precisa dos IDs após o upsert
        id_map = buscar_ids_itens(db_client, cnpj, ano, sequencial)

        resultado_rows: list[dict] = []
        for numero_item in itens_com_resultado:
            item_id = id_map.get(numero_item)
            if not item_id:
                _tracker.registrar_falha(
                    TipoFalha.PARTIAL, f"ID não encontrado para item {numero_item}"
                )
                stats["erros"] += 1
                continue

            rows = _coletar_resultados_item(
                pncp, item_id, cnpj, ano, sequencial, numero_item, _tracker, _throttler
            )
            resultado_rows.extend(rows)

        # 5. Persiste resultados em batch
        if resultado_rows:
            persistidos, falhas = persistir_resultados_batch(db_client, resultado_rows)
            stats["resultados"] = persistidos
            _tracker.registrar_resultados_persistidos(persistidos)
            for tipo, msg in falhas:
                _tracker.registrar_falha(tipo, msg)
                stats["erros"] += 1

    return stats


# ---------------------------------------------------------------------------
# Estratégia 1 — Coleta de pendentes
# ---------------------------------------------------------------------------


def coletar_pendentes(limite: int = 100, db_client: Any = None) -> StatsColeta:
    """Coleta itens de licitações existentes que ainda não foram processadas."""
    from db import get_client
    from pncp_client import PNCPClient

    client = db_client or get_client()
    pncp = PNCPClient()
    tracker = StatsTracker()
    throttler = Throttler()
    stats_total: StatsColeta = {"licitacoes": 0, "itens": 0, "resultados": 0, "erros": 0}

    licitacoes = buscar_licitacoes_sem_itens(limite, client)
    log.info("Licitações pendentes: %d", len(licitacoes))

    for lic in licitacoes:
        parts = lic.get("_parts") or extrair_url_parts(lic.get("url_fonte", ""))
        if not parts:
            continue

        cnpj, ano_str, seq_str = parts
        ano, seq = int(ano_str), int(seq_str)

        log.debug("Coletando itens: %s/%d/%d", cnpj, ano, seq)

        metadata = Metadata(
            uf=lic.get("uf"),
            municipio=lic.get("municipio_nome"),
            codigo_ibge=lic.get("codigo_ibge"),
            modalidade_id=lic.get("modalidade_id"),
            plataforma_id=None,
            plataforma_nome=None,
        )

        tracker.registrar_licitacao()
        stats = coletar_itens_contratacao(
            pncp, cnpj, ano, seq, lic.get("hash_dedup"), metadata,
            db_client=client, tracker=tracker, throttler=throttler,
        )
        stats_total["licitacoes"] += 1
        stats_total["itens"] += stats["itens"]
        stats_total["resultados"] += stats["resultados"]
        stats_total["erros"] += stats["erros"]

        throttler.esperar()

    tracker.log_resumo("Coleta pendentes")
    return stats_total


# ---------------------------------------------------------------------------
# Estratégia 2 — Coleta por plataforma
# ---------------------------------------------------------------------------


def coletar_por_plataforma(
    id_usuario: int,
    dias: int = 30,
    modalidades: list[int] | None = None,
    uf: str | None = None,
    limite_paginas: int = 50,
    db_client: Any = None,
) -> StatsPlataforma:
    """Coleta contratações + itens diretamente por plataforma (idUsuario)."""
    from config import Config
    from db import get_client
    from platform_mapper import get_plataforma_nome
    from pncp_client import PNCPClient

    client = db_client or get_client()
    pncp = PNCPClient()
    tracker = StatsTracker()
    throttler = Throttler()
    nome_plataforma = get_plataforma_nome(id_usuario)
    mods = modalidades or Config.MODALIDADES
    stats_total: StatsPlataforma = {"contratacoes": 0, "itens": 0, "resultados": 0, "erros": 0}

    hoje = datetime.now()
    data_final = hoje.strftime("%Y%m%d")
    data_inicial = (hoje - timedelta(days=dias)).strftime("%Y%m%d")

    log.info(
        "Coletando plataforma '%s' (id=%d) | período %s→%s | UF=%s",
        nome_plataforma, id_usuario, data_inicial, data_final, uf or "todas",
    )

    for modalidade in mods:
        for pagina in range(1, limite_paginas + 1):
            throttler.esperar()

            try:
                resultado = pncp.buscar_contratacoes_por_plataforma(
                    id_usuario=id_usuario,
                    data_inicial=data_inicial,
                    data_final=data_final,
                    modalidade=modalidade,
                    uf=uf,
                    pagina=pagina,
                )
                throttler.registrar_sucesso()
            except Exception as exc:
                throttler.registrar_falha(TipoFalha.API)
                tracker.registrar_falha(TipoFalha.API, f"Plataforma {id_usuario} mod={modalidade} pag={pagina}: {exc}")
                break

            contratacoes = resultado.get("data", [])
            if not contratacoes:
                break

            for cont in contratacoes:
                cnpj = cont.get("orgaoEntidade", {}).get("cnpj")
                ano = cont.get("anoCompra")
                seq = cont.get("sequencialCompra")

                if not all([cnpj, ano, seq]):
                    continue

                uo = cont.get("unidadeOrgao", {})
                metadata = Metadata(
                    uf=uo.get("ufSigla"),
                    municipio=uo.get("municipioNome"),
                    codigo_ibge=uo.get("codigoIbge"),
                    modalidade_id=cont.get("modalidadeId"),
                    plataforma_id=id_usuario,
                    plataforma_nome=nome_plataforma,
                )

                tracker.registrar_licitacao()
                stats = coletar_itens_contratacao(
                    pncp, cnpj, ano, seq, None, metadata,
                    db_client=client, tracker=tracker, throttler=throttler,
                )
                stats_total["contratacoes"] += 1
                stats_total["itens"] += stats["itens"]
                stats_total["resultados"] += stats["resultados"]
                stats_total["erros"] += stats["erros"]

            if pagina >= resultado.get("totalPaginas", 0):
                break

    tracker.log_resumo(f"Coleta plataforma '{nome_plataforma}'")
    return stats_total


# ---------------------------------------------------------------------------
# Estratégia 3 — Coleta de resultados pendentes
# ---------------------------------------------------------------------------


def coletar_resultados_pendentes(limite: int = 200, db_client: Any = None) -> StatsResultados:
    """Coleta resultados de itens que têm tem_resultado=True mas sem resultado gravado."""
    from db import get_client
    from pncp_client import PNCPClient

    client = db_client or get_client()
    pncp = PNCPClient()
    tracker = StatsTracker()
    throttler = Throttler()
    stats: StatsResultados = {"resultados": 0, "erros": 0}

    itens = buscar_itens_sem_resultado(limite, client)
    log.info("Itens com resultado pendente: %d", len(itens))

    resultado_rows: list[dict] = []

    for item in itens:
        rows = _coletar_resultados_item(
            pncp,
            item_id=item["id"],
            cnpj=item["cnpj_orgao"],
            ano=item["ano_compra"],
            sequencial=item["sequencial_compra"],
            numero_item=item["numero_item"],
            tracker=tracker,
            throttler=throttler,
        )
        resultado_rows.extend(rows)

    # Persiste tudo em batch
    if resultado_rows:
        persistidos, falhas = persistir_resultados_batch(client, resultado_rows)
        stats["resultados"] = persistidos
        tracker.registrar_resultados_persistidos(persistidos)
        for tipo, msg in falhas:
            tracker.registrar_falha(tipo, msg)
            stats["erros"] += 1

    tracker.log_resumo("Resultados pendentes")
    return stats
