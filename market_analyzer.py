"""
Comparativo de mercado — calcula e materializa comparações entre plataformas.
Roda diariamente no cron após a coleta de itens/resultados.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime

from config import Config
from utils import normalizar

log = logging.getLogger(__name__)

# ── Plataformas concorrentes (idUsuario PNCP) ───────────────

CONCORRENTES: dict[int, str] = {
    121: "SH3 Informática",
    12: "BLL Compras (BNC)",
    13: "Licitar Digital",
    18: "Licitanet",
}

IDS_CONCORRENTES = list(CONCORRENTES.keys())

# ── Stopwords para agrupamento ───────────────────────────────

STOPWORDS = {
    "de", "do", "da", "dos", "das", "para", "com", "por", "que", "uma",
    "seu", "sua", "nos", "nas", "pelo", "pela", "aos", "entre", "sobre",
    "apos", "ate", "sem", "contratacao", "empresa", "especializada",
    "prestacao", "servicos", "servico", "aquisicao", "fornecimento",
    "objeto", "registro", "preco", "precos", "lote", "item",
}

DESCONTO_MAXIMO = 80.0
RAZAO_MAXIMA_ESCALA = 50  # max/min entre plataformas no mesmo grupo


# ── Helpers ──────────────────────────────────────────────────

def _extrair_palavras_chave(descricao: str) -> list[str]:
    """Extrai palavras significativas (sem stopwords, >3 chars)."""
    texto = normalizar(descricao)
    return [p for p in texto.split() if len(p) > 3 and p not in STOPWORDS]


def _gerar_chave(descricao: str, ncm: str | None) -> str:
    """Gera chave de agrupamento: NCM ou 4 palavras-chave significativas."""
    if ncm:
        return f"ncm:{ncm}"
    palavras = _extrair_palavras_chave(descricao)[:4]
    return f"desc:{' '.join(palavras)}" if len(palavras) >= 2 else ""


def _remover_outliers(valores: list[float]) -> list[float]:
    """Remove outliers por IQR."""
    if len(valores) < 4:
        return valores
    sorted_v = sorted(valores)
    q1 = sorted_v[len(sorted_v) // 4]
    q3 = sorted_v[3 * len(sorted_v) // 4]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [v for v in valores if lo <= v <= hi]


def _valores_comparaveis(medias: list[float]) -> bool:
    """Verifica se os valores estão na mesma ordem de grandeza."""
    if len(medias) < 2:
        return False
    mn, mx = min(medias), max(medias)
    return mn > 0 and mx / mn <= RAZAO_MAXIMA_ESCALA


# ── Busca de dados ───────────────────────────────────────────

def _buscar_itens_plataforma(client, plat_id: int, uf: str | None, limite: int = 5000) -> list[dict]:
    """Busca itens de uma plataforma com seus resultados."""
    query = (
        client.table("itens_contratacao")
        .select("descricao, ncm_nbs_codigo, unidade_medida, plataforma_nome, plataforma_id, valor_unitario_estimado, resultados_item(valor_unitario_homologado, percentual_desconto)")
        .gt("valor_unitario_estimado", 0)
        .eq("plataforma_id", plat_id)
        .limit(limite)
    )
    if uf:
        query = query.eq("uf", uf)

    result = query.execute()
    return result.data or []


# ── Cálculo do comparativo ───────────────────────────────────

def calcular_comparativo(client, uf: str | None = None) -> dict:
    """
    Calcula comparativo entre plataformas e grava nas tabelas materializadas.
    Retorna estatísticas: {itens_comparaveis, plataformas}.
    """
    sufixo_uf = f" (UF={uf})" if uf else " (geral)"
    log.info("Calculando comparativo%s...", sufixo_uf)

    # 1. Busca itens de todas as plataformas
    todos_itens: list[dict] = []
    for plat_id in IDS_CONCORRENTES:
        itens = _buscar_itens_plataforma(client, plat_id, uf)
        todos_itens.extend(itens)
        log.debug("  Plataforma %d: %d itens", plat_id, len(itens))

    if not todos_itens:
        log.info("Sem itens para comparar%s", sufixo_uf)
        return {"itens_comparaveis": 0, "plataformas": 0}

    # 2. Agrupa por chave (NCM ou palavras-chave)
    grupos: dict[str, dict] = {}

    for row in todos_itens:
        plataforma = row.get("plataforma_nome") or ""
        plat_id = row.get("plataforma_id") or 0
        if not plataforma:
            continue

        resultados = row.get("resultados_item") or []
        if isinstance(resultados, dict):
            resultados = [resultados]

        valor = 0.0
        if resultados and resultados[0].get("valor_unitario_homologado", 0) > 0:
            valor = float(resultados[0]["valor_unitario_homologado"])
        else:
            valor = float(row.get("valor_unitario_estimado", 0))
        if valor <= 0:
            continue

        ncm = row.get("ncm_nbs_codigo")
        descricao = row.get("descricao") or ""
        chave = _gerar_chave(descricao, ncm)
        if not chave:
            continue

        grupo = grupos.setdefault(chave, {
            "descricao": descricao[:80],
            "ncm": ncm,
            "unidade": row.get("unidade_medida") or "",
            "plataformas": {},
        })

        plat_data = grupo["plataformas"].setdefault(plataforma, {
            "id": plat_id,
            "valores": [],
            "descontos": [],
        })
        plat_data["valores"].append(valor)

        desconto = resultados[0].get("percentual_desconto") if resultados else None
        if desconto is not None and 0 <= desconto <= DESCONTO_MAXIMO:
            plat_data["descontos"].append(float(desconto))

    # 3. Filtra: 2+ plataformas + mesma escala
    comparaveis = []
    for chave, info in grupos.items():
        if len(info["plataformas"]) < 2:
            continue

        # Verifica escala
        medias = []
        for pd in info["plataformas"].values():
            if pd["valores"]:
                medias.append(statistics.mean(pd["valores"]))
        if not _valores_comparaveis(medias):
            continue

        # Calcula preços limpos por plataforma
        precos = []
        for nome, pd in info["plataformas"].items():
            valores_limpos = _remover_outliers(pd["valores"])
            if not valores_limpos:
                valores_limpos = pd["valores"]
            media = statistics.mean(valores_limpos) if valores_limpos else 0
            descontos_validos = [d for d in pd["descontos"] if 0 <= d <= DESCONTO_MAXIMO]
            eco = statistics.mean(descontos_validos) if descontos_validos else None

            precos.append({
                "plataforma_nome": nome,
                "plataforma_id": pd["id"],
                "valor_medio": round(media, 2),
                "total_ocorrencias": len(pd["valores"]),
                "economia_media": round(eco, 2) if eco is not None else None,
            })

        precos.sort(key=lambda p: p["valor_medio"])

        comparaveis.append({
            "chave": chave,
            "descricao": info["descricao"],
            "ncm": info["ncm"],
            "unidade": info["unidade"],
            "precos": precos,
            "menor_preco_plataforma": precos[0]["plataforma_nome"],
        })

    log.info("Itens comparáveis%s: %d", sufixo_uf, len(comparaveis))

    # 4. Calcula resumo por plataforma
    resumo_plat: dict[str, dict] = {}
    for item in comparaveis:
        menor = item["menor_preco_plataforma"]
        for p in item["precos"]:
            nome = p["plataforma_nome"]
            rp = resumo_plat.setdefault(nome, {
                "id": p["plataforma_id"],
                "valores": [],
                "descontos": [],
                "vitorias": 0,
            })
            rp["valores"].append(p["valor_medio"])
            if p["economia_media"] is not None:
                rp["descontos"].append(p["economia_media"])
            if nome == menor:
                rp["vitorias"] += 1

    # 5. Grava no banco
    _gravar_resultados(client, uf, comparaveis, resumo_plat)

    return {"itens_comparaveis": len(comparaveis), "plataformas": len(resumo_plat)}


# ── Persistência ─────────────────────────────────────────────

def _gravar_resultados(client, uf: str | None, comparaveis: list[dict], resumo_plat: dict):
    """Grava comparativo nas tabelas materializadas."""

    # Limpa dados anteriores para esta UF
    if uf:
        client.table("comparativo_plataformas").delete().eq("uf", uf).execute()
        # Para itens, busca IDs e deleta (cascade cuida dos preços)
        existing = client.table("comparativo_itens").select("id").eq("uf", uf).execute()
        if existing.data:
            ids = [r["id"] for r in existing.data]
            client.table("comparativo_itens").delete().in_("id", ids).execute()
    else:
        client.table("comparativo_plataformas").delete().is_("uf", "null").execute()
        existing = client.table("comparativo_itens").select("id").is_("uf", "null").execute()
        if existing.data:
            ids = [r["id"] for r in existing.data]
            client.table("comparativo_itens").delete().in_("id", ids).execute()

    agora = datetime.utcnow().isoformat()

    # Grava resumo por plataforma
    plat_rows = []
    for nome, info in resumo_plat.items():
        media = statistics.mean(info["valores"]) if info["valores"] else 0
        desc_medio = statistics.mean(info["descontos"]) if info["descontos"] else None
        plat_rows.append({
            "plataforma_nome": nome,
            "plataforma_id": info["id"],
            "total_itens": len(info["valores"]),
            "valor_medio_unitario": round(media, 2),
            "desconto_medio": round(desc_medio, 2) if desc_medio is not None else None,
            "vitorias": info["vitorias"],
            "uf": uf,
            "calculado_em": agora,
        })

    if plat_rows:
        client.table("comparativo_plataformas").upsert(
            plat_rows, on_conflict="plataforma_id,uf"
        ).execute()
        log.info("  Gravadas %d plataformas", len(plat_rows))

    # Grava itens comparáveis + preços
    itens_gravados = 0
    for item in comparaveis:
        item_row = {
            "chave_agrupamento": item["chave"],
            "descricao": item["descricao"],
            "ncm_nbs_codigo": item["ncm"],
            "unidade_medida": item["unidade"],
            "menor_preco_plataforma": item["menor_preco_plataforma"],
            "uf": uf,
            "calculado_em": agora,
        }

        client.table("comparativo_itens").upsert(
            item_row, on_conflict="chave_agrupamento,uf"
        ).execute()

        # Busca o ID do item inserido/atualizado
        if uf:
            id_result = client.table("comparativo_itens").select("id").eq(
                "chave_agrupamento", item["chave"]
            ).eq("uf", uf).single().execute()
        else:
            id_result = client.table("comparativo_itens").select("id").eq(
                "chave_agrupamento", item["chave"]
            ).is_("uf", "null").single().execute()

        if not id_result.data:
            continue

        item_id = id_result.data["id"]

        preco_rows = [{
            "comparativo_item_id": item_id,
            "plataforma_nome": p["plataforma_nome"],
            "plataforma_id": p["plataforma_id"],
            "valor_medio": p["valor_medio"],
            "total_ocorrencias": p["total_ocorrencias"],
            "economia_media": p["economia_media"],
        } for p in item["precos"]]

        if preco_rows:
            client.table("comparativo_itens_precos").upsert(
                preco_rows, on_conflict="comparativo_item_id,plataforma_id"
            ).execute()

        itens_gravados += 1

    log.info("  Gravados %d itens comparáveis com preços", itens_gravados)


# ── Orquestração ─────────────────────────────────────────────

def executar_comparativo():
    """
    Calcula comparativo para todas as UFs + geral.
    Chamado pelo cron diariamente.
    """
    from db import get_client

    client = get_client()
    log.info("=" * 40)
    log.info("COMPARATIVO DE MERCADO")
    log.info("=" * 40)

    # Descobre quais UFs têm dados
    result = client.table("itens_contratacao").select(
        "uf"
    ).in_(
        "plataforma_id", IDS_CONCORRENTES
    ).gt(
        "valor_unitario_estimado", 0
    ).limit(5000).execute()

    ufs_com_dados = sorted({r["uf"] for r in (result.data or []) if r.get("uf")})
    log.info("UFs com dados: %s", ", ".join(ufs_com_dados) if ufs_com_dados else "nenhuma")

    # Calcula geral (sem filtro de UF)
    stats_geral = calcular_comparativo(client, uf=None)
    log.info("Geral: %s", stats_geral)

    # Calcula por UF
    for uf in ufs_com_dados:
        stats = calcular_comparativo(client, uf=uf)
        log.info("%s: %s", uf, stats)

    log.info("Comparativo de mercado concluído!")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    executar_comparativo()
