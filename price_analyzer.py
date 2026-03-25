"""
Preços de referência — calcula estatísticas de preço para licitações abertas.
Busca licitações e itens similares, aplica filtros de qualidade e grava
resultados materializados para consumo rápido pelo frontend.

Conformidade: janela temporal de 12 meses (IN 65/2021).
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime, timedelta

from utils import normalizar

log = logging.getLogger(__name__)

JANELA_MESES = 12
AMOSTRA_MINIMA = 3
TRIM_PERCENT = 0.1  # 10% de cada extremo

SELECT_ITENS = (
    "id, descricao, ncm_nbs_codigo, quantidade, unidade_medida, "
    "valor_unitario_estimado, valor_total_estimado, "
    "plataforma_nome, uf, municipio, modalidade_id, created_at, "
    "resultados_item(valor_unitario_homologado, valor_total_homologado, "
    "nome_fornecedor, porte_fornecedor, percentual_desconto)"
)


# ── Estatísticas ─────────────────────────────────────────────

def _media_saneada(valores: list[float], trim: float = TRIM_PERCENT) -> float:
    """Trimmed mean — descarta trim% dos extremos de cada lado."""
    if len(valores) < 4:
        return statistics.mean(valores) if valores else 0
    sorted_v = sorted(valores)
    corte = max(1, math.floor(len(sorted_v) * trim))
    saneados = sorted_v[corte:len(sorted_v) - corte]
    return statistics.mean(saneados) if saneados else statistics.mean(valores)


def _coeficiente_variacao(valores: list[float]) -> float | None:
    """CV = (desvio padrão / média) * 100. None se < 2 valores."""
    if len(valores) < 2:
        return None
    media = statistics.mean(valores)
    if media == 0:
        return None
    desvio = statistics.stdev(valores)
    return round((desvio / media) * 100, 2)


def _mediana(valores: list[float]) -> float:
    return statistics.median(valores) if valores else 0


def _data_limite() -> str:
    """Retorna data ISO de JANELA_MESES atrás."""
    return (datetime.utcnow() - timedelta(days=JANELA_MESES * 30)).isoformat()


# ── Busca de licitações similares ────────────────────────────

def _buscar_similares(client, licitacao: dict, data_limite: str) -> list[dict]:
    """
    Busca licitações similares:
    1. Mesma modalidade
    2. Últimos 12 meses
    3. Valor homologado > 0
    4. Busca textual pelas palavras-chave
    5. Prioriza mesma UF, amplia se amostra insuficiente
    """
    lic_id = licitacao["id"]
    palavras = licitacao.get("palavras_chave") or []
    modalidade = licitacao.get("modalidade", "")
    uf = licitacao.get("uf", "")

    if not palavras:
        return []

    # Monta termo de busca com todas as palavras-chave
    termos_busca = " | ".join(palavras[:6])

    def _query(filtro_uf: bool):
        q = (
            client.table("licitacoes")
            .select("id, municipio_nome, uf, objeto, valor_homologado, modalidade, data_publicacao")
            .gt("valor_homologado", 0)
            .neq("id", lic_id)
            .gte("data_publicacao", data_limite)
            .text_search("objeto", termos_busca, {"type": "websearch"})
            .order("data_publicacao", desc=True)
            .limit(30)
        )
        if modalidade:
            q = q.eq("modalidade", modalidade)
        if filtro_uf and uf:
            q = q.eq("uf", uf)
        return q

    # Tenta com mesma UF primeiro
    try:
        result = _query(filtro_uf=True).execute()
        similares = result.data or []
    except Exception:
        similares = []

    # Se amostra insuficiente, amplia sem filtro de UF
    if len(similares) < AMOSTRA_MINIMA:
        try:
            result = _query(filtro_uf=False).execute()
            similares = result.data or []
        except Exception:
            pass

    # Fallback com ilike se websearch não encontrou nada
    if not similares and palavras:
        termos_ilike = [normalizar(p) for p in palavras[:3]]
        try:
            q = (
                client.table("licitacoes")
                .select("id, municipio_nome, uf, objeto, valor_homologado, modalidade, data_publicacao")
                .gt("valor_homologado", 0)
                .neq("id", lic_id)
                .gte("data_publicacao", data_limite)
                .ilike("objeto", f"%{termos_ilike[0]}%")
                .order("data_publicacao", desc=True)
                .limit(30)
            )
            if modalidade:
                q = q.eq("modalidade", modalidade)
            result = q.execute()
            similares = result.data or []
        except Exception:
            similares = []

    return similares


# ── Busca de itens similares ─────────────────────────────────

def _buscar_itens_similares(client, licitacao: dict) -> list[dict]:
    """Busca itens similares por descrição do objeto."""
    objeto = licitacao.get("objeto", "")
    uf = licitacao.get("uf", "")

    # Extrai termos significativos do objeto
    palavras = [
        p for p in normalizar(objeto).split()
        if len(p) > 3 and p not in {
            "para", "como", "pela", "pelo", "entre", "sobre",
            "contratacao", "empresa", "especializada", "prestacao",
            "servicos", "aquisicao", "fornecimento", "objeto",
        }
    ][:5]

    if not palavras:
        return []

    termos = " & ".join(palavras[:3])

    def _query(filtro_uf: bool):
        q = (
            client.table("itens_contratacao")
            .select(SELECT_ITENS)
            .gt("valor_unitario_estimado", 0)
            .text_search("descricao", termos, {"type": "websearch"})
            .order("created_at", desc=True)
            .limit(50)
        )
        if filtro_uf and uf:
            q = q.eq("uf", uf)
        return q

    # Tenta com UF primeiro
    try:
        result = _query(filtro_uf=True).execute()
        itens = result.data or []
    except Exception:
        itens = []

    # Amplia sem UF se pouco resultado
    if len(itens) < AMOSTRA_MINIMA:
        try:
            result = _query(filtro_uf=False).execute()
            itens = result.data or []
        except Exception:
            pass

    # Fallback ilike
    if not itens and palavras:
        try:
            q = (
                client.table("itens_contratacao")
                .select(SELECT_ITENS)
                .gt("valor_unitario_estimado", 0)
                .ilike("descricao", f"%{palavras[0]}%")
                .order("created_at", desc=True)
                .limit(50)
            )
            if uf:
                q = q.eq("uf", uf)
            result = q.execute()
            itens = result.data or []
        except Exception:
            itens = []

    return itens


# ── Cálculo principal ────────────────────────────────────────

def calcular_precos_licitacao(client, licitacao: dict) -> dict | None:
    """
    Calcula preços de referência para uma licitação e grava no banco.
    Retorna o registro gravado ou None se sem dados.
    """
    lic_id = licitacao["id"]
    data_limite = _data_limite()

    # 1. Licitações similares
    similares = _buscar_similares(client, licitacao, data_limite)
    valores_hom = [float(s["valor_homologado"]) for s in similares if s.get("valor_homologado")]

    resumo_lic = {}
    if valores_hom:
        resumo_lic = {
            "total_similares": len(valores_hom),
            "valor_minimo": round(min(valores_hom), 2),
            "valor_maximo": round(max(valores_hom), 2),
            "valor_media": round(statistics.mean(valores_hom), 2),
            "valor_mediana": round(_mediana(valores_hom), 2),
            "valor_media_saneada": round(_media_saneada(valores_hom), 2),
            "coeficiente_variacao": _coeficiente_variacao(valores_hom),
            "amostra_suficiente": len(valores_hom) >= AMOSTRA_MINIMA,
        }
    else:
        resumo_lic = {
            "total_similares": 0,
            "valor_minimo": None, "valor_maximo": None,
            "valor_media": None, "valor_mediana": None,
            "valor_media_saneada": None, "coeficiente_variacao": None,
            "amostra_suficiente": False,
        }

    # 2. Itens similares
    itens_raw = _buscar_itens_similares(client, licitacao)
    valores_unit = []
    descontos = []
    itens_para_gravar = []
    plataformas_map: dict[str, list[float]] = {}

    for item in itens_raw:
        resultados = item.get("resultados_item") or []
        if isinstance(resultados, dict):
            resultados = [resultados]

        resultado = resultados[0] if resultados else None
        valor = 0.0
        if resultado and resultado.get("valor_unitario_homologado", 0) > 0:
            valor = float(resultado["valor_unitario_homologado"])
        else:
            valor = float(item.get("valor_unitario_estimado", 0))
        if valor <= 0:
            continue

        valores_unit.append(valor)

        desc = resultado.get("percentual_desconto") if resultado else None
        if desc is not None and 0 <= desc <= 80:
            descontos.append(float(desc))

        plat = item.get("plataforma_nome") or "Não identificada"
        plataformas_map.setdefault(plat, []).append(valor)

        itens_para_gravar.append({
            "descricao": (item.get("descricao") or "")[:200],
            "unidade_medida": item.get("unidade_medida") or "",
            "valor_unitario": round(valor, 2),
            "plataforma_nome": plat,
            "municipio": item.get("municipio") or "",
            "uf": item.get("uf") or "",
            "nome_fornecedor": (resultado.get("nome_fornecedor") or "")[:100] if resultado else "",
            "percentual_desconto": round(desc, 2) if desc is not None and 0 <= desc <= 80 else None,
        })

    resumo_itens = {}
    if valores_unit:
        resumo_itens = {
            "total_itens_similares": len(valores_unit),
            "item_minimo_unitario": round(min(valores_unit), 2),
            "item_maximo_unitario": round(max(valores_unit), 2),
            "item_media_unitario": round(statistics.mean(valores_unit), 2),
            "item_mediana_unitario": round(_mediana(valores_unit), 2),
            "item_media_saneada": round(_media_saneada(valores_unit), 2),
            "item_desconto_medio": round(statistics.mean(descontos), 2) if descontos else None,
            "item_coeficiente_variacao": _coeficiente_variacao(valores_unit),
        }
    else:
        resumo_itens = {
            "total_itens_similares": 0,
            "item_minimo_unitario": None, "item_maximo_unitario": None,
            "item_media_unitario": None, "item_mediana_unitario": None,
            "item_media_saneada": None, "item_desconto_medio": None,
            "item_coeficiente_variacao": None,
        }

    # Se não tem nada, não grava
    if resumo_lic["total_similares"] == 0 and resumo_itens["total_itens_similares"] == 0:
        return None

    # 3. Grava resumo
    registro = {
        "licitacao_id": lic_id,
        **resumo_lic,
        **resumo_itens,
        "janela_meses": JANELA_MESES,
        "calculado_em": datetime.utcnow().isoformat(),
    }

    client.table("preco_referencia_licitacao").upsert(
        registro, on_conflict="licitacao_id"
    ).execute()

    # Busca o ID do registro inserido/atualizado
    id_result = client.table("preco_referencia_licitacao").select("id").eq(
        "licitacao_id", lic_id
    ).single().execute()

    if not id_result.data:
        log.error("Falha ao gravar resumo de preços para %s", lic_id)
        return None

    ref_id = id_result.data["id"]

    # Limpa detalhes antigos (cascade não funciona em upsert)
    client.table("preco_referencia_detalhe").delete().eq("preco_referencia_id", ref_id).execute()
    client.table("preco_referencia_itens").delete().eq("preco_referencia_id", ref_id).execute()
    client.table("preco_referencia_plataformas").delete().eq("preco_referencia_id", ref_id).execute()

    # 4. Grava detalhes de licitações similares
    if similares:
        detalhe_rows = [{
            "preco_referencia_id": ref_id,
            "licitacao_similar_id": s["id"],
            "municipio_nome": s.get("municipio_nome") or "",
            "uf": s.get("uf") or "",
            "objeto": (s.get("objeto") or "")[:200],
            "modalidade": s.get("modalidade") or "",
            "valor_homologado": s.get("valor_homologado"),
            "data_publicacao": s.get("data_publicacao"),
        } for s in similares if s.get("valor_homologado")]

        if detalhe_rows:
            client.table("preco_referencia_detalhe").insert(detalhe_rows).execute()

    # 5. Grava itens similares
    if itens_para_gravar:
        for item_row in itens_para_gravar:
            item_row["preco_referencia_id"] = ref_id
        # Insere em lotes de 50
        for i in range(0, len(itens_para_gravar), 50):
            batch = itens_para_gravar[i:i + 50]
            client.table("preco_referencia_itens").insert(batch).execute()

    # 6. Grava resumo por plataforma
    plat_rows = []
    for plat, vals in plataformas_map.items():
        plat_rows.append({
            "preco_referencia_id": ref_id,
            "plataforma_nome": plat,
            "media_unitario": round(statistics.mean(vals), 2),
            "total_itens": len(vals),
        })
    if plat_rows:
        client.table("preco_referencia_plataformas").upsert(
            plat_rows, on_conflict="preco_referencia_id,plataforma_nome"
        ).execute()

    log.info(
        "Preços calculados para %s: %d similares (CV=%.1f%%), %d itens",
        lic_id,
        resumo_lic["total_similares"],
        resumo_lic.get("coeficiente_variacao") or 0,
        resumo_itens["total_itens_similares"],
    )

    return registro


# ── Orquestração ─────────────────────────────────────────────

def calcular_precos_pendentes(limite: int = 50):
    """Processa licitações abertas sem preço de referência calculado."""
    from db import get_client

    client = get_client()
    log.info("=" * 40)
    log.info("PREÇOS DE REFERÊNCIA")
    log.info("=" * 40)

    # Busca licitações abertas sem preço calculado
    result = (
        client.table("licitacoes")
        .select("id, objeto, modalidade, uf, palavras_chave")
        .eq("proposta_aberta", True)
        .order("relevancia", desc=False)
        .order("data_publicacao", desc=True)
        .limit(limite * 2)
        .execute()
    )
    licitacoes = result.data or []

    if not licitacoes:
        log.info("Nenhuma licitação aberta para calcular preços")
        return {"calculadas": 0, "erros": 0}

    # Filtra as que já têm preço calculado
    lic_ids = [l["id"] for l in licitacoes]
    ja_calculadas = (
        client.table("preco_referencia_licitacao")
        .select("licitacao_id")
        .in_("licitacao_id", lic_ids)
        .execute()
    )
    ids_calculados = {r["licitacao_id"] for r in (ja_calculadas.data or [])}
    pendentes = [l for l in licitacoes if l["id"] not in ids_calculados][:limite]

    if not pendentes:
        log.info("Todas as licitações abertas já têm preço calculado")
        return {"calculadas": 0, "erros": 0}

    log.info("Calculando preços para %d licitações...", len(pendentes))

    calculadas = 0
    erros = 0

    for lic in pendentes:
        try:
            resultado = calcular_precos_licitacao(client, lic)
            if resultado:
                calculadas += 1
            else:
                log.debug("Sem dados de preço para %s", lic["id"])
        except Exception as e:
            log.error("Erro ao calcular preços para %s: %s", lic["id"], e)
            erros += 1

    log.info("Preços concluídos: %d calculadas, %d erros", calculadas, erros)
    return {"calculadas": calculadas, "erros": erros}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    calcular_precos_pendentes()
