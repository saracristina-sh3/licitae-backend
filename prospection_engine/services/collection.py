"""
Coleta genérica de licitações — sem filtro de palavras-chave.

Busca todas as contratações nas UFs/modalidades configuradas,
filtra apenas por proposta aberta e município-alvo, e persiste no banco.
A prospecção por org é feita em etapa separada.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from config import Config
from municipios import carregar_municipios
from pncp_client import PNCPClient
from prospection_engine.constants import MODALIDADE_NOMES
from prospection_engine.services.deduplication import chave_dedup
from prospection_engine.services.filtering import proposta_encerrada, resolver_municipio

log = logging.getLogger(__name__)


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
    if data_inicial and data_final:
        return data_inicial, data_final
    dias = dias_retroativos or Config.DIAS_RETROATIVOS
    hoje = datetime.now()
    inicio = hoje - timedelta(days=dias)
    return inicio.strftime("%Y%m%d"), hoje.strftime("%Y%m%d")


def _extrair_url_pncp(contratacao: dict) -> str:
    cnpj = contratacao.get("orgaoEntidade", {}).get("cnpj", "")
    ano = contratacao.get("anoCompra", "")
    seq = contratacao.get("sequencialCompra", "")
    if cnpj and ano and seq:
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
    return ""


# Códigos PNCP de tipoBeneficio que indicam exclusividade ME/EPP
_BENEFICIO_ME_EPP = {1, 2, 3}


def _montar_resultado_generico(contratacao: dict, mun_info: dict) -> dict:
    """Monta dict genérico para inserção no banco (sem score/relevância)."""
    orgao = contratacao.get("orgaoEntidade", {}) or {}
    objeto = contratacao.get("objetoCompra", "") or ""
    info_compl = contratacao.get("informacaoComplementar", "") or ""

    return {
        "municipio": mun_info["nome"],
        "uf": mun_info["uf"],
        "codigo_ibge": str(mun_info.get("codigo_ibge", "")),
        "orgao": orgao.get("razaoSocial", ""),
        "cnpj_orgao": orgao.get("cnpj", ""),
        "objeto": objeto,
        "exclusivo_me_epp": contratacao.get("tipoBeneficioId", 0) in _BENEFICIO_ME_EPP,
        "modalidade": MODALIDADE_NOMES.get(
            contratacao.get("modalidadeId", 0), str(contratacao.get("modalidadeId", ""))
        ),
        "valor_estimado": contratacao.get("valorTotalEstimado", 0) or 0,
        "valor_homologado": contratacao.get("valorTotalHomologado", 0) or 0,
        "situacao": contratacao.get("situacaoCompraNome", ""),
        "data_publicacao": contratacao.get("dataPublicacaoPncp", ""),
        "data_abertura_proposta": contratacao.get("dataAberturaProposta", ""),
        "data_encerramento_proposta": contratacao.get("dataEncerramentoProposta", ""),
        "url_pncp": _extrair_url_pncp(contratacao),
        "fonte": "PNCP",
        "ano_compra": str(contratacao.get("anoCompra", "")),
        "seq_compra": str(contratacao.get("sequencialCompra", "")),
        "informacao_complementar": info_compl,
        "modalidade_id": contratacao.get("modalidadeId"),
        "modo_disputa_id": contratacao.get("modoDisputaId"),
        "situacao_compra_id": contratacao.get("situacaoCompraId"),
    }


def _coletar_uf_modalidade(
    uf: str,
    modalidade: int,
    janelas: list[tuple[str, str]],
    mapa_municipios: dict[str, dict],
    client: PNCPClient,
    stats: dict,
) -> list[dict]:
    """
    Coleta contratações de uma combinação (UF, modalidade).
    Filtra apenas por proposta aberta e município-alvo.
    NÃO aplica filtro de palavras-chave.
    """
    mod_nome = MODALIDADE_NOMES.get(modalidade, str(modalidade))
    resultados: list[dict] = []
    total_contratacoes = 0

    log.info("  %s - %s: iniciando coleta (%d janelas)", uf, mod_nome, len(janelas))

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
                "  %s - %s: falha na janela %s-%s — %s",
                uf, mod_nome, j_inicio, j_fim, exc,
            )
            continue

        total_contratacoes += len(contratacoes)

        for c in contratacoes:
            if proposta_encerrada(c):
                stats["filtradas_proposta"] += 1
                continue

            mun_info = resolver_municipio(c, mapa_municipios)
            if not mun_info:
                stats["filtradas_municipio"] += 1
                continue

            resultados.append(_montar_resultado_generico(c, mun_info))

    stats["total_contratacoes"] += total_contratacoes
    stats["por_uf"][uf] = stats["por_uf"].get(uf, 0) + len(resultados)

    log.info(
        "  %s - %s: %d aceitas de %d total",
        uf, mod_nome, len(resultados), total_contratacoes,
    )
    return resultados


def coletar_licitacoes(
    ufs: list[str],
    modalidades: list[int],
    fpm_maximo: int,
    dias_retroativos: int | None = None,
    data_inicial: str | None = None,
    data_final: str | None = None,
    max_workers: int = 3,
    janela_dias: int = 1,
) -> list[dict]:
    """
    Coleta genérica de licitações do PNCP.
    Retorna lista de dicts prontos para inserção no banco.
    NÃO aplica filtro de palavras-chave (isso é feito na prospecção por org).
    """
    run_id = uuid.uuid4().hex[:12]
    t0 = time.monotonic()

    dt_inicio, dt_fim = _resolver_periodo(dias_retroativos, data_inicial, data_final)
    log.info("[%s] Coleta genérica: %s a %s", run_id, dt_inicio, dt_fim)

    municipios = carregar_municipios(ufs, fpm_maximo)
    mapa_municipios: dict[str, dict] = {m["codigo_ibge"]: m for m in municipios}
    log.info(
        "[%s] Municípios-alvo: %d (%s)",
        run_id, len(municipios), ", ".join(ufs),
    )

    janelas = _gerar_janelas(dt_inicio, dt_fim, janela_dias)
    log.info("[%s] %d janelas | workers: %d", run_id, len(janelas), max_workers)

    client = PNCPClient()
    stats = {
        "total_contratacoes": 0,
        "filtradas_proposta": 0,
        "filtradas_municipio": 0,
        "por_uf": {},
    }
    todos: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _coletar_uf_modalidade,
                uf, modalidade, janelas, mapa_municipios, client, stats,
            ): (uf, modalidade)
            for uf in ufs
            for modalidade in modalidades
        }

        for future in as_completed(futures):
            uf, modalidade = futures[future]
            try:
                parcial = future.result()
                todos.extend(parcial)
            except Exception as exc:
                mod_nome = MODALIDADE_NOMES.get(modalidade, str(modalidade))
                log.error("[%s] Tarefa %s/%s falhou: %s", run_id, uf, mod_nome, exc)

    # Deduplicação simples por chave natural
    vistos: dict[str, dict] = {}
    for r in todos:
        chave = f"{r.get('cnpj_orgao', '')}_{r.get('ano_compra', '')}_{r.get('seq_compra', '')}"
        if chave not in vistos:
            vistos[chave] = r
    duplicatas = len(todos) - len(vistos)
    resultados = list(vistos.values())

    duracao = (time.monotonic() - t0) / 1000
    log.info(
        "[%s] Coleta concluída: %d licitações (de %d contratações) | "
        "filtradas: proposta=%d, município=%d | duplicatas=%d | %.1fs",
        run_id,
        len(resultados),
        stats["total_contratacoes"],
        stats["filtradas_proposta"],
        stats["filtradas_municipio"],
        duplicatas,
        (time.monotonic() - t0),
    )

    if stats["por_uf"]:
        log.info("[%s] Por UF: %s", run_id, stats["por_uf"])

    return resultados
