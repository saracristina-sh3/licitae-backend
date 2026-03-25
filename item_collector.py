"""
Coletor de itens e resultados — Fase 1 da Inteligência Competitiva.

Duas estratégias de coleta:
1. coletar_pendentes()        — coleta itens de licitações já existentes na tabela licitacoes
2. coletar_por_plataforma()   — coleta contratações + itens diretamente por idUsuario

Uso:
    python item_collector.py                          # Coleta pendentes (limite 100)
    python item_collector.py --limite 50              # Coleta 50 pendentes
    python item_collector.py --plataforma 121         # Coleta da SH3
    python item_collector.py --plataforma 121 --uf MG # SH3, só MG
    python item_collector.py --resultados-pendentes   # Coleta resultados pendentes
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime, timedelta
from typing import TypedDict

from config import Config
from db import get_client
from platform_mapper import get_plataforma_nome
from pncp_client import PNCPClient

log = logging.getLogger(__name__)

DELAY_ENTRE_REQUESTS: float = getattr(Config, "DELAY_ENTRE_REQUESTS", 0.3)

# Padrão de extração de cnpj/ano/seq da URL do PNCP — compilado uma vez
_RE_URL_PARTS = re.compile(r"/(?:editais|compras)/([^/]+)/(\d+)/(\d+)")

# ---------------------------------------------------------------------------
# Tipagem
# ---------------------------------------------------------------------------


class Metadata(TypedDict):
    uf: str | None
    municipio: str | None
    codigo_ibge: str | None
    modalidade_id: int | None
    plataforma_id: int | None
    plataforma_nome: str | None


class ItemRow(TypedDict):
    licitacao_hash: str | None
    cnpj_orgao: str
    ano_compra: int
    sequencial_compra: int
    numero_item: int
    descricao: str | None
    ncm_nbs_codigo: str | None
    quantidade: float | None
    unidade_medida: str | None
    valor_unitario_estimado: float | None
    valor_total_estimado: float | None
    tem_resultado: bool
    plataforma_id: int | None
    plataforma_nome: str | None
    uf: str | None
    municipio: str | None
    codigo_ibge: str | None
    modalidade_id: int | None


class ResultadoRow(TypedDict):
    item_id: str
    sequencial_resultado: int
    valor_unitario_homologado: float | None
    valor_total_homologado: float | None
    quantidade_homologada: float | None
    percentual_desconto: float | None
    cnpj_fornecedor: str | None
    nome_fornecedor: str | None
    porte_fornecedor: str | None
    data_resultado: str | None


class StatsItens(TypedDict):
    itens: int
    resultados: int
    erros: int


class StatsColeta(TypedDict):
    licitacoes: int
    itens: int
    resultados: int
    erros: int


class StatsPlataforma(TypedDict):
    contratacoes: int
    itens: int
    resultados: int
    erros: int


class StatsResultados(TypedDict):
    resultados: int
    erros: int


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _extrair_url_parts(url_fonte: str) -> tuple[str, str, str] | None:
    """Extrai (cnpj, ano, seq) da URL do PNCP."""
    if not url_fonte:
        return None
    match = _RE_URL_PARTS.search(url_fonte)
    return (match.group(1), match.group(2), match.group(3)) if match else None


def _montar_item_row(
    cnpj: str,
    ano: int,
    sequencial: int,
    licitacao_hash: str | None,
    item: dict,
    metadata: Metadata,
) -> ItemRow:
    """Constrói o dicionário de inserção de um item."""
    return ItemRow(
        licitacao_hash=licitacao_hash,
        cnpj_orgao=cnpj,
        ano_compra=ano,
        sequencial_compra=sequencial,
        numero_item=item.get("numeroItem"),
        descricao=item.get("descricao"),
        ncm_nbs_codigo=item.get("ncmNbsCodigo"),
        quantidade=item.get("quantidade"),
        unidade_medida=item.get("unidadeMedida"),
        valor_unitario_estimado=item.get("valorUnitarioEstimado"),
        valor_total_estimado=item.get("valorTotal"),
        tem_resultado=item.get("temResultado", False),
        plataforma_id=metadata.get("plataforma_id"),
        plataforma_nome=metadata.get("plataforma_nome"),
        uf=metadata.get("uf"),
        municipio=metadata.get("municipio"),
        codigo_ibge=metadata.get("codigo_ibge"),
        modalidade_id=metadata.get("modalidade_id"),
    )


def _montar_resultado_row(item_id: str, res: dict) -> ResultadoRow:
    """
    Constrói o dicionário de inserção de um resultado.
    Fonte única — elimina a duplicação entre coletar_itens_contratacao
    e coletar_resultados_pendentes.
    """
    return ResultadoRow(
        item_id=item_id,
        sequencial_resultado=res.get("sequencialResultado"),
        valor_unitario_homologado=res.get("valorUnitarioHomologado"),
        valor_total_homologado=res.get("valorTotalHomologado"),
        quantidade_homologada=res.get("quantidadeHomologada"),
        percentual_desconto=res.get("percentualDesconto"),
        cnpj_fornecedor=res.get("niFornecedor"),
        nome_fornecedor=res.get("nomeRazaoSocialFornecedor"),
        porte_fornecedor=res.get("porteFornecedorNome"),
        data_resultado=res.get("dataResultado"),
    )


def _persistir_item(
    row: ItemRow,
    client,
) -> str | None:
    """
    Faz upsert do item e retorna seu UUID a partir do próprio retorno do upsert,
    sem query adicional ao banco.
    """
    try:
        result = client.table("itens_contratacao").upsert(
            row,
            on_conflict="cnpj_orgao,ano_compra,sequencial_compra,numero_item",
        ).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as exc:
        log.warning(
            "Erro ao inserir item %s/%s/%s/%s — %s: %s",
            row["cnpj_orgao"],
            row["ano_compra"],
            row["sequencial_compra"],
            row["numero_item"],
            type(exc).__name__,
            exc,
        )
        return None


def _persistir_resultado(res_row: ResultadoRow, client) -> bool:
    """Faz upsert de um resultado. Retorna True em sucesso."""
    try:
        client.table("resultados_item").upsert(
            res_row,
            on_conflict="item_id,sequencial_resultado",
        ).execute()
        return True
    except Exception as exc:
        log.warning(
            "Erro ao inserir resultado item_id=%s seq=%s — %s: %s",
            res_row.get("item_id"),
            res_row.get("sequencial_resultado"),
            type(exc).__name__,
            exc,
        )
        return False


def _coletar_e_persistir_resultados(
    pncp: PNCPClient,
    item_id: str,
    cnpj: str,
    ano: int,
    sequencial: int,
    numero_item: int,
    client,
) -> StatsItens:
    """Busca e persiste os resultados de um único item."""
    stats: StatsItens = {"itens": 0, "resultados": 0, "erros": 0}
    time.sleep(DELAY_ENTRE_REQUESTS)

    resultados = pncp.buscar_resultados_item(cnpj, ano, sequencial, numero_item)
    for res in resultados:
        if res.get("sequencialResultado") is None:
            continue
        res_row = _montar_resultado_row(item_id, res)
        if _persistir_resultado(res_row, client):
            stats["resultados"] += 1
        else:
            stats["erros"] += 1

    return stats


def _buscar_licitacoes_sem_itens(limite: int, client) -> list[dict]:
    """
    Retorna licitações que ainda não possuem itens coletados,
    usando LEFT JOIN no banco via RPC para evitar N+1 queries.
    Fallback para duas queries se a RPC não estiver disponível.
    """
    try:
        result = client.rpc(
            "licitacoes_sem_itens",
            {"p_limite": limite},
        ).execute()
        return result.data or []
    except Exception:
        log.debug("RPC licitacoes_sem_itens indisponível, usando fallback de duas queries")

        result = (
            client.table("licitacoes")
            .select(
                "hash_dedup, cnpj_orgao, url_fonte, uf, municipio_nome, "
                "modalidade, modalidade_id, codigo_ibge"
            )
            .neq("cnpj_orgao", "")
            .neq("url_fonte", "")
            .limit(limite * 3)
            .execute()
        )
        licitacoes = result.data or []
        if not licitacoes:
            return []

        # Descobre quais já têm itens em uma única query
        cnpj_ano_seqs = []
        for lic in licitacoes:
            parts = _extrair_url_parts(lic.get("url_fonte", ""))
            if parts:
                cnpj_ano_seqs.append(f"{parts[0]}/{parts[1]}/{parts[2]}")

        ja_coletadas: set[str] = set()
        if cnpj_ano_seqs:
            existing = (
                client.table("itens_contratacao")
                .select("cnpj_orgao, ano_compra, sequencial_compra")
                .in_(
                    "cnpj_orgao",
                    list({p.split("/")[0] for p in cnpj_ano_seqs}),
                )
                .execute()
            )
            for row in existing.data or []:
                chave = f"{row['cnpj_orgao']}/{row['ano_compra']}/{row['sequencial_compra']}"
                ja_coletadas.add(chave)

        pendentes = []
        for lic in licitacoes:
            parts = _extrair_url_parts(lic.get("url_fonte", ""))
            if not parts:
                continue
            chave = f"{parts[0]}/{parts[1]}/{parts[2]}"
            if chave not in ja_coletadas:
                lic["_parts"] = parts
                pendentes.append(lic)
            if len(pendentes) >= limite:
                break

        return pendentes


def _buscar_itens_sem_resultado(limite: int, client) -> list[dict]:
    """
    Retorna itens com tem_resultado=True que ainda não têm resultado gravado,
    via RPC com LEFT JOIN. Fallback para duas queries se necessário.
    """
    try:
        result = client.rpc(
            "itens_sem_resultado",
            {"p_limite": limite},
        ).execute()
        return result.data or []
    except Exception:
        log.debug("RPC itens_sem_resultado indisponível, usando fallback de duas queries")

        result = (
            client.table("itens_contratacao")
            .select("id, cnpj_orgao, ano_compra, sequencial_compra, numero_item")
            .eq("tem_resultado", True)
            .limit(limite * 3)
            .execute()
        )
        itens = result.data or []
        if not itens:
            return []

        ids = [i["id"] for i in itens]
        ja_coletados_res = (
            client.table("resultados_item")
            .select("item_id")
            .in_("item_id", ids)
            .execute()
        )
        ids_com_resultado = {r["item_id"] for r in (ja_coletados_res.data or [])}
        return [i for i in itens if i["id"] not in ids_com_resultado][:limite]


# ---------------------------------------------------------------------------
# Núcleo de coleta por contratação
# ---------------------------------------------------------------------------


def coletar_itens_contratacao(
    pncp: PNCPClient,
    cnpj: str,
    ano: int,
    sequencial: int,
    licitacao_hash: str | None,
    metadata: Metadata,
    db_client=None,
) -> StatsItens:
    """
    Coleta itens e resultados de uma contratação específica.

    Parâmetros
    ----------
    pncp : PNCPClient
        Client da API do PNCP (injetável para testes).
    db_client : opcional
        Client do banco de dados (injetável para testes).
    metadata : Metadata
        Campos complementares: uf, municipio, codigo_ibge, modalidade_id,
        plataforma_id, plataforma_nome.

    Retorna
    -------
    StatsItens com contagens de itens, resultados e erros.
    """
    client = db_client or get_client()
    stats: StatsItens = {"itens": 0, "resultados": 0, "erros": 0}

    itens_api = pncp.buscar_itens(cnpj, ano, sequencial)
    if not itens_api:
        return stats

    for item in itens_api:
        if item.get("numeroItem") is None:
            continue

        row = _montar_item_row(cnpj, ano, sequencial, licitacao_hash, item, metadata)
        item_id = _persistir_item(row, client)

        if item_id is None:
            stats["erros"] += 1
            continue

        stats["itens"] += 1

        if item.get("temResultado"):
            res_stats = _coletar_e_persistir_resultados(
                pncp, item_id, cnpj, ano, sequencial, item["numeroItem"], client
            )
            stats["resultados"] += res_stats["resultados"]
            stats["erros"] += res_stats["erros"]

    return stats


# ---------------------------------------------------------------------------
# Estratégia 1 — Coleta de pendentes
# ---------------------------------------------------------------------------


def coletar_pendentes(limite: int = 100, db_client=None) -> StatsColeta:
    """
    Coleta itens de licitações existentes no banco que ainda não foram processadas.
    Usa RPC com LEFT JOIN para evitar N+1 queries (com fallback automático).
    """
    client = db_client or get_client()
    pncp = PNCPClient()
    stats_total: StatsColeta = {"licitacoes": 0, "itens": 0, "resultados": 0, "erros": 0}

    licitacoes = _buscar_licitacoes_sem_itens(limite, client)
    log.info("Licitações pendentes: %d", len(licitacoes))

    for lic in licitacoes:
        parts = lic.get("_parts") or _extrair_url_parts(lic.get("url_fonte", ""))
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

        stats = coletar_itens_contratacao(
            pncp, cnpj, ano, seq, lic.get("hash_dedup"), metadata, db_client=client
        )
        stats_total["licitacoes"] += 1
        stats_total["itens"] += stats["itens"]
        stats_total["resultados"] += stats["resultados"]
        stats_total["erros"] += stats["erros"]

        time.sleep(DELAY_ENTRE_REQUESTS)

    log.info(
        "Coleta pendentes: %d licitações | %d itens | %d resultados | %d erros",
        stats_total["licitacoes"],
        stats_total["itens"],
        stats_total["resultados"],
        stats_total["erros"],
    )
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
    db_client=None,
) -> StatsPlataforma:
    """
    Coleta contratações + itens diretamente por plataforma (idUsuario).
    Ideal para coleta em massa de uma plataforma específica.
    """
    client = db_client or get_client()
    pncp = PNCPClient()
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
                metadata = Metadata(
                    uf=uo.get("ufSigla"),
                    municipio=uo.get("municipioNome"),
                    codigo_ibge=uo.get("codigoIbge"),
                    modalidade_id=cont.get("modalidadeId"),
                    plataforma_id=id_usuario,
                    plataforma_nome=nome_plataforma,
                )

                stats = coletar_itens_contratacao(
                    pncp, cnpj, ano, seq, None, metadata, db_client=client
                )
                stats_total["contratacoes"] += 1
                stats_total["itens"] += stats["itens"]
                stats_total["resultados"] += stats["resultados"]
                stats_total["erros"] += stats["erros"]

                time.sleep(DELAY_ENTRE_REQUESTS)

            if pagina >= resultado.get("totalPaginas", 0):
                break

    log.info(
        "Coleta plataforma '%s': %d contratações | %d itens | %d resultados | %d erros",
        nome_plataforma,
        stats_total["contratacoes"],
        stats_total["itens"],
        stats_total["resultados"],
        stats_total["erros"],
    )
    return stats_total


# ---------------------------------------------------------------------------
# Estratégia 3 — Coleta de resultados pendentes
# ---------------------------------------------------------------------------


def coletar_resultados_pendentes(limite: int = 200, db_client=None) -> StatsResultados:
    """
    Coleta resultados de itens que marcaram tem_resultado=True mas ainda
    não têm resultado gravado. Usa RPC com LEFT JOIN (com fallback automático).
    """
    client = db_client or get_client()
    pncp = PNCPClient()
    stats: StatsResultados = {"resultados": 0, "erros": 0}

    itens = _buscar_itens_sem_resultado(limite, client)
    log.info("Itens com resultado pendente: %d", len(itens))

    for item in itens:
        res_stats = _coletar_e_persistir_resultados(
            pncp,
            item_id=item["id"],
            cnpj=item["cnpj_orgao"],
            ano=item["ano_compra"],
            sequencial=item["sequencial_compra"],
            numero_item=item["numero_item"],
            client=client,
        )
        stats["resultados"] += res_stats["resultados"]
        stats["erros"] += res_stats["erros"]

        time.sleep(DELAY_ENTRE_REQUESTS)

    log.info(
        "Resultados pendentes: %d coletados | %d erros",
        stats["resultados"],
        stats["erros"],
    )
    return stats


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Coletor de itens e resultados PNCP")
    parser.add_argument("--limite", type=int, default=100, help="Limite de registros (padrão: 100)")
    parser.add_argument("--plataforma", type=int, help="idUsuario da plataforma para coleta direta")
    parser.add_argument("--uf", help="Filtrar por UF (ex: MG)")
    parser.add_argument("--dias", type=int, default=30, help="Dias retroativos (padrão: 30)")
    parser.add_argument(
        "--resultados-pendentes",
        action="store_true",
        help="Coletar apenas resultados pendentes",
    )
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