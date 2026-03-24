"""
Coletor de itens e resultados — Fase 1 da Inteligência Competitiva.

Duas estratégias de coleta:
1. coletar_pendentes() — coleta itens de licitações já existentes na tabela licitacoes
2. coletar_por_plataforma() — coleta contratações + itens diretamente por idUsuario

Uso:
    python item_collector.py                          # Coleta pendentes (limite 100)
    python item_collector.py --limite 50              # Coleta 50 pendentes
    python item_collector.py --plataforma 121         # Coleta da SH3
    python item_collector.py --plataforma 121 --uf MG # SH3, só MG
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime, timedelta

from db import get_client
from pncp_client import PNCPClient
from config import Config

log = logging.getLogger(__name__)

DELAY_ENTRE_REQUESTS = 0.3


def _extrair_url_parts(url_fonte: str) -> tuple[str, str, str] | None:
    """Extrai cnpj, ano e seq da URL do PNCP."""
    if not url_fonte:
        return None
    match = re.search(r"/(?:editais|compras)/([^/]+)/(\d+)/(\d+)", url_fonte)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None


def coletar_itens_contratacao(
    pncp: PNCPClient,
    cnpj: str,
    ano: int,
    sequencial: int,
    licitacao_hash: str | None,
    metadata: dict,
) -> dict:
    """
    Coleta itens + resultados de uma contratação.
    metadata: uf, municipio, codigo_ibge, modalidade_id, plataforma_id, plataforma_nome
    Retorna {"itens": N, "resultados": N, "erros": N}
    """
    client = get_client()
    stats = {"itens": 0, "resultados": 0, "erros": 0}

    itens_api = pncp.buscar_itens(cnpj, ano, sequencial)
    if not itens_api:
        return stats

    for item in itens_api:
        numero_item = item.get("numeroItem")
        if numero_item is None:
            continue

        row = {
            "licitacao_hash": licitacao_hash,
            "cnpj_orgao": cnpj,
            "ano_compra": ano,
            "sequencial_compra": sequencial,
            "numero_item": numero_item,
            "descricao": item.get("descricao"),
            "ncm_nbs_codigo": item.get("ncmNbsCodigo"),
            "quantidade": item.get("quantidade"),
            "unidade_medida": item.get("unidadeMedida"),
            "valor_unitario_estimado": item.get("valorUnitarioEstimado"),
            "valor_total_estimado": item.get("valorTotal"),
            "tem_resultado": item.get("temResultado", False),
            "plataforma_id": metadata.get("plataforma_id"),
            "plataforma_nome": metadata.get("plataforma_nome"),
            "uf": metadata.get("uf"),
            "municipio": metadata.get("municipio"),
            "codigo_ibge": metadata.get("codigo_ibge"),
            "modalidade_id": metadata.get("modalidade_id"),
        }

        try:
            result = client.table("itens_contratacao").upsert(
                row,
                on_conflict="cnpj_orgao,ano_compra,sequencial_compra,numero_item",
            ).execute()
            stats["itens"] += 1
        except Exception as e:
            log.warning("Erro ao inserir item %s/%d/%d/%d: %s", cnpj, ano, sequencial, numero_item, e)
            stats["erros"] += 1
            continue

        # Coleta resultados se disponível
        if item.get("temResultado"):
            time.sleep(DELAY_ENTRE_REQUESTS)
            item_id = _get_item_id(client, cnpj, ano, sequencial, numero_item)
            if not item_id:
                continue

            resultados = pncp.buscar_resultados_item(cnpj, ano, sequencial, numero_item)
            for res in resultados:
                seq_res = res.get("sequencialResultado")
                if seq_res is None:
                    continue

                res_row = {
                    "item_id": item_id,
                    "sequencial_resultado": seq_res,
                    "valor_unitario_homologado": res.get("valorUnitarioHomologado"),
                    "valor_total_homologado": res.get("valorTotalHomologado"),
                    "quantidade_homologada": res.get("quantidadeHomologada"),
                    "percentual_desconto": res.get("percentualDesconto"),
                    "cnpj_fornecedor": res.get("niFornecedor"),
                    "nome_fornecedor": res.get("nomeRazaoSocialFornecedor"),
                    "porte_fornecedor": res.get("porteFornecedorNome"),
                    "data_resultado": res.get("dataResultado"),
                }

                try:
                    client.table("resultados_item").upsert(
                        res_row,
                        on_conflict="item_id,sequencial_resultado",
                    ).execute()
                    stats["resultados"] += 1
                except Exception as e:
                    log.warning("Erro ao inserir resultado item %d seq %d: %s", numero_item, seq_res, e)
                    stats["erros"] += 1

    return stats


def _get_item_id(client, cnpj: str, ano: int, sequencial: int, numero_item: int) -> str | None:
    """Busca o UUID do item inserido."""
    result = (
        client.table("itens_contratacao")
        .select("id")
        .eq("cnpj_orgao", cnpj)
        .eq("ano_compra", ano)
        .eq("sequencial_compra", sequencial)
        .eq("numero_item", numero_item)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]
    return None


def coletar_pendentes(limite: int = 100) -> dict:
    """
    Coleta itens de licitações existentes no Supabase que ainda não foram processadas.
    """
    client = get_client()
    pncp = PNCPClient()
    stats_total = {"licitacoes": 0, "itens": 0, "resultados": 0, "erros": 0}

    # Busca licitações com CNPJ que ainda não têm itens coletados
    result = (
        client.table("licitacoes")
        .select("hash_dedup, cnpj_orgao, url_fonte, uf, municipio_nome, modalidade")
        .neq("cnpj_orgao", "")
        .neq("url_fonte", "")
        .limit(limite)
        .execute()
    )

    licitacoes = result.data or []
    log.info("Licitações candidatas: %d", len(licitacoes))

    for lic in licitacoes:
        parts = _extrair_url_parts(lic.get("url_fonte", ""))
        if not parts:
            continue

        cnpj, ano_str, seq_str = parts
        ano = int(ano_str)
        seq = int(seq_str)

        # Verifica se já tem itens coletados
        existing = (
            client.table("itens_contratacao")
            .select("id", count="exact")
            .eq("cnpj_orgao", cnpj)
            .eq("ano_compra", ano)
            .eq("sequencial_compra", seq)
            .limit(1)
            .execute()
        )
        if existing.count and existing.count > 0:
            continue

        log.debug("Coletando itens: %s/%d/%d", cnpj, ano, seq)

        metadata = {
            "uf": lic.get("uf"),
            "municipio": lic.get("municipio_nome"),
            "codigo_ibge": None,
            "modalidade_id": None,
            "plataforma_id": None,
            "plataforma_nome": None,
        }

        stats = coletar_itens_contratacao(pncp, cnpj, ano, seq, lic.get("hash_dedup"), metadata)
        stats_total["licitacoes"] += 1
        stats_total["itens"] += stats["itens"]
        stats_total["resultados"] += stats["resultados"]
        stats_total["erros"] += stats["erros"]

        time.sleep(DELAY_ENTRE_REQUESTS)

    log.info(
        "Coleta pendentes: %d licitações, %d itens, %d resultados, %d erros",
        stats_total["licitacoes"], stats_total["itens"],
        stats_total["resultados"], stats_total["erros"],
    )
    return stats_total


def coletar_por_plataforma(
    id_usuario: int,
    dias: int = 30,
    modalidades: list[int] | None = None,
    uf: str | None = None,
    limite_paginas: int = 50,
) -> dict:
    """
    Coleta contratações + itens diretamente por plataforma (idUsuario).
    Ideal para coleta em massa de uma plataforma específica.
    """
    from platform_mapper import get_plataforma_nome

    pncp = PNCPClient()
    plataforma_nome = get_plataforma_nome(id_usuario)
    mods = modalidades or Config.MODALIDADES
    stats_total = {"contratacoes": 0, "itens": 0, "resultados": 0, "erros": 0}

    hoje = datetime.now()
    data_final = hoje.strftime("%Y%m%d")
    data_inicial = (hoje - timedelta(days=dias)).strftime("%Y%m%d")

    log.info(
        "Coletando plataforma '%s' (id=%d), período %s a %s, UF=%s",
        plataforma_nome, id_usuario, data_inicial, data_final, uf or "todas",
    )

    for modalidade in mods:
        pagina = 1

        while pagina <= limite_paginas:
            resultado = pncp.buscar_contratacoes_por_plataforma(
                id_usuario=id_usuario,
                data_inicial=data_inicial,
                data_final=data_final,
                modalidade=modalidade,
                uf=uf,
                pagina=pagina,
            )

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
                metadata = {
                    "uf": uo.get("ufSigla"),
                    "municipio": uo.get("municipioNome"),
                    "codigo_ibge": uo.get("codigoIbge"),
                    "modalidade_id": cont.get("modalidadeId"),
                    "plataforma_id": id_usuario,
                    "plataforma_nome": plataforma_nome,
                }

                stats = coletar_itens_contratacao(pncp, cnpj, ano, seq, None, metadata)
                stats_total["contratacoes"] += 1
                stats_total["itens"] += stats["itens"]
                stats_total["resultados"] += stats["resultados"]
                stats_total["erros"] += stats["erros"]

                time.sleep(DELAY_ENTRE_REQUESTS)

            total_paginas = resultado.get("totalPaginas", 0)
            if pagina >= total_paginas:
                break
            pagina += 1

    log.info(
        "Coleta plataforma '%s': %d contratações, %d itens, %d resultados, %d erros",
        plataforma_nome, stats_total["contratacoes"], stats_total["itens"],
        stats_total["resultados"], stats_total["erros"],
    )
    return stats_total


def coletar_resultados_pendentes(limite: int = 200) -> dict:
    """Coleta resultados de itens que marcaram tem_resultado=true mas não têm resultado gravado."""
    client = get_client()
    pncp = PNCPClient()
    stats = {"resultados": 0, "erros": 0}

    result = (
        client.table("itens_contratacao")
        .select("id, cnpj_orgao, ano_compra, sequencial_compra, numero_item")
        .eq("tem_resultado", True)
        .limit(limite)
        .execute()
    )

    itens = result.data or []
    log.info("Itens com resultado pendente: %d", len(itens))

    for item in itens:
        # Verifica se já tem resultado
        existing = (
            client.table("resultados_item")
            .select("id", count="exact")
            .eq("item_id", item["id"])
            .limit(1)
            .execute()
        )
        if existing.count and existing.count > 0:
            continue

        resultados = pncp.buscar_resultados_item(
            item["cnpj_orgao"],
            item["ano_compra"],
            item["sequencial_compra"],
            item["numero_item"],
        )

        for res in resultados:
            seq_res = res.get("sequencialResultado")
            if seq_res is None:
                continue

            res_row = {
                "item_id": item["id"],
                "sequencial_resultado": seq_res,
                "valor_unitario_homologado": res.get("valorUnitarioHomologado"),
                "valor_total_homologado": res.get("valorTotalHomologado"),
                "quantidade_homologada": res.get("quantidadeHomologada"),
                "percentual_desconto": res.get("percentualDesconto"),
                "cnpj_fornecedor": res.get("niFornecedor"),
                "nome_fornecedor": res.get("nomeRazaoSocialFornecedor"),
                "porte_fornecedor": res.get("porteFornecedorNome"),
                "data_resultado": res.get("dataResultado"),
            }

            try:
                client.table("resultados_item").upsert(
                    res_row,
                    on_conflict="item_id,sequencial_resultado",
                ).execute()
                stats["resultados"] += 1
            except Exception as e:
                log.warning("Erro resultado: %s", e)
                stats["erros"] += 1

        time.sleep(DELAY_ENTRE_REQUESTS)

    log.info("Resultados pendentes: %d coletados, %d erros", stats["resultados"], stats["erros"])
    return stats


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Coletor de itens e resultados PNCP")
    parser.add_argument("--limite", type=int, default=100, help="Limite de licitações (padrão: 100)")
    parser.add_argument("--plataforma", type=int, help="idUsuario da plataforma para coleta direta")
    parser.add_argument("--uf", help="Filtrar por UF (ex: MG)")
    parser.add_argument("--dias", type=int, default=30, help="Dias retroativos (padrão: 30)")
    parser.add_argument("--resultados-pendentes", action="store_true", help="Coletar apenas resultados pendentes")
    args = parser.parse_args()

    if args.resultados_pendentes:
        coletar_resultados_pendentes(args.limite)
    elif args.plataforma:
        coletar_por_plataforma(
            id_usuario=args.plataforma,
            dias=args.dias,
            uf=args.uf,
        )
    else:
        coletar_pendentes(limite=args.limite)
