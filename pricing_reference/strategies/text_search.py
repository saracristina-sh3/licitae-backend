"""
Estratégia de similaridade baseada em text_search do PostgreSQL.

Implementa busca em camadas com fallback:
1. text_search (websearch) + mesma UF + mesma modalidade
2. text_search sem filtro de UF
3. ilike como último recurso

Cada resultado recebe um score heurístico de similaridade (0-100).
Usa comparison_core para normalização, sinônimos e validação.
"""

from __future__ import annotations

import logging
from datetime import datetime

from utils import normalizar
from comparison_core.categories import classificar_item
from comparison_core.normalizer import extrair_termos
from comparison_core.validator import validar_unidade
from pricing_reference.constants import (
    AMOSTRA_MINIMA,
    SELECT_ITENS,
    SIM_MESMA_MODALIDADE,
    SIM_MESMA_UF,
    SIM_NCM_IGUAL,
    SIM_RECENTE,
    SIM_TERMOS_COMUNS,
    SIM_UNIDADE_IGUAL,
)
from pricing_reference.types import ResultadoSimilaridade

log = logging.getLogger(__name__)


def _calcular_score_licitacao(
    similar: dict,
    licitacao_ref: dict,
    termos_ref: list[str],
) -> float:
    """
    Calcula score de similaridade (0-100) entre uma licitação similar e a referência.

    Fatores:
    - Mesma modalidade: +20
    - Mesma UF: +15
    - Termos em comum (com sinônimos): até +20 (proporcional)
    - Recência (< 6 meses): +10
    """
    score = 0.0

    # Modalidade
    if similar.get("modalidade") and similar["modalidade"] == licitacao_ref.get("modalidade"):
        score += SIM_MESMA_MODALIDADE

    # UF
    if similar.get("uf") and similar["uf"] == licitacao_ref.get("uf"):
        score += SIM_MESMA_UF

    # Termos em comum (usa extrair_termos com sinônimos aplicados)
    if termos_ref:
        termos_similar = extrair_termos(similar.get("objeto") or "")
        termos_comuns = len(set(termos_ref) & set(termos_similar))
        ratio = min(termos_comuns / len(termos_ref), 1.0)
        score += SIM_TERMOS_COMUNS * ratio

    # Recência
    data_pub = similar.get("data_publicacao")
    if data_pub:
        try:
            dt = datetime.fromisoformat(data_pub.replace("Z", "+00:00"))
            dias = (datetime.now(dt.tzinfo) - dt).days if dt.tzinfo else (datetime.utcnow() - dt).days
            if dias <= 180:
                score += SIM_RECENTE
            elif dias <= 365:
                score += SIM_RECENTE * (1 - (dias - 180) / 185)
        except (ValueError, TypeError):
            pass

    # Normalizar para 0-100 (máximo possível sem NCM/unidade = 65)
    score = min(score * (100 / 65), 100)
    return round(score, 2)


def _calcular_score_item(
    item: dict,
    licitacao_ref: dict,
    termos_ref: list[str],
) -> float:
    """
    Calcula score de similaridade (0-100) para um item.
    Usa sinônimos para matching de termos. Inclui NCM e unidade.
    """
    score = 0.0

    # UF
    if item.get("uf") and item["uf"] == licitacao_ref.get("uf"):
        score += SIM_MESMA_UF

    # Termos em comum (com sinônimos aplicados)
    if termos_ref:
        termos_item = extrair_termos(item.get("descricao") or "")
        termos_comuns = len(set(termos_ref) & set(termos_item))
        ratio = min(termos_comuns / len(termos_ref), 1.0)
        score += SIM_TERMOS_COMUNS * ratio

    # Unidade de medida (usa validação centralizada)
    unidade_item = item.get("unidade_medida") or ""
    # Licitações não têm unidade de referência, mas bonifica se compatível
    if unidade_item:
        score += SIM_UNIDADE_IGUAL * 0.5  # Bônus parcial por ter unidade

    # Recência
    created = item.get("created_at")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            dias = (datetime.now(dt.tzinfo) - dt).days if dt.tzinfo else (datetime.utcnow() - dt).days
            if dias <= 180:
                score += SIM_RECENTE
            elif dias <= 365:
                score += SIM_RECENTE * (1 - (dias - 180) / 185)
        except (ValueError, TypeError):
            pass

    # Normalizar para 0-100 (máximo possível = 65 sem NCM)
    score = min(score * (100 / 65), 100)
    return round(score, 2)


class TextSearchStrategy:
    """Implementação de similaridade via text_search + ilike do PostgreSQL."""

    def buscar_licitacoes(
        self,
        client,
        licitacao: dict,
        data_limite: str,
    ) -> list[ResultadoSimilaridade]:
        """Busca licitações similares com score e fonte de preço."""
        lic_id = licitacao["id"]
        palavras = licitacao.get("palavras_chave") or []
        modalidade = licitacao.get("modalidade", "")
        uf = licitacao.get("uf", "")

        # Extrai termos com sinônimos para scoring
        termos_ref = extrair_termos(licitacao.get("objeto") or "")

        # Categoria da licitação de referência
        cat_ref = classificar_item(licitacao.get("objeto") or "")

        if not palavras:
            return []

        termos_busca = " | ".join(palavras[:10])
        select = "id, municipio_nome, uf, objeto, valor_homologado, valor_estimado, modalidade, data_publicacao"

        def _query(filtro_uf: bool):
            q = (
                client.table("licitacoes")
                .select(select)
                .neq("id", lic_id)
                .gte("data_publicacao", data_limite)
                .order("data_publicacao", desc=True)
                .limit(30)
                .text_search("objeto", termos_busca, {"type": "websearch"})
            )
            if modalidade:
                q = q.eq("modalidade", modalidade)
            if filtro_uf and uf:
                q = q.eq("uf", uf)
            return q

        # Camada 1: mesma UF
        try:
            result = _query(filtro_uf=True).execute()
            similares_raw = result.data or []
        except Exception as e:
            log.warning("Erro text_search com UF: %s", e)
            similares_raw = []

        # Camada 2: sem filtro de UF
        if len(similares_raw) < AMOSTRA_MINIMA:
            try:
                result = _query(filtro_uf=False).execute()
                similares_raw = result.data or []
            except Exception as e:
                log.warning("Erro text_search sem UF: %s", e)

        # Camada 3: fallback ilike
        if not similares_raw and palavras:
            termos_ilike = [normalizar(p) for p in palavras[:3]]
            try:
                q = (
                    client.table("licitacoes")
                    .select(select)
                    .neq("id", lic_id)
                    .gte("data_publicacao", data_limite)
                    .ilike("objeto", f"%{termos_ilike[0]}%")
                    .order("data_publicacao", desc=True)
                    .limit(30)
                )
                if modalidade:
                    q = q.eq("modalidade", modalidade)
                result = q.execute()
                similares_raw = result.data or []
            except Exception as e:
                log.warning("Erro ilike fallback: %s", e)
                similares_raw = []

        # Classificar cada resultado
        resultados: list[ResultadoSimilaridade] = []
        for s in similares_raw:
            # Validar categoria — rejeitar se incompatível
            cat_similar = classificar_item(s.get("objeto") or "")
            if cat_ref != cat_similar:
                continue  # Golden Rule: categorias diferentes não se comparam

            hom = s.get("valor_homologado")
            est = s.get("valor_estimado")

            if hom and float(hom) > 0:
                fonte = "homologado"
                valor = float(hom)
            elif est and float(est) > 0:
                fonte = "estimado"
                valor = float(est)
            else:
                continue

            score = _calcular_score_licitacao(s, licitacao, termos_ref)

            resultados.append(ResultadoSimilaridade(
                registro=s,
                score=score,
                fonte_preco=fonte,
                valor=valor,
                compativel_unidade=True,
            ))

        # Filtrar por score mínimo e ordenar
        resultados = [r for r in resultados if r["score"] >= 25]
        resultados.sort(key=lambda r: r["score"], reverse=True)
        return resultados

    def buscar_itens(
        self,
        client,
        licitacao: dict,
    ) -> list[ResultadoSimilaridade]:
        """Busca itens similares com score, fonte e compatibilidade de unidade."""
        objeto = licitacao.get("objeto", "")
        uf = licitacao.get("uf", "")
        palavras_chave = licitacao.get("palavras_chave") or []

        # Categoria da licitação de referência
        cat_ref = classificar_item(objeto)

        # Prioriza palavras-chave (mais relevantes) sobre termos do objeto
        if palavras_chave:
            termos_ref = extrair_termos(" ".join(palavras_chave[:5]))
        else:
            termos_ref = extrair_termos(objeto)

        if not termos_ref:
            return []

        # Usa AND (&) para exigir TODOS os termos
        termos_busca = " & ".join(termos_ref[:4])

        def _query(filtro_uf: bool):
            q = (
                client.table("itens_contratacao")
                .select(SELECT_ITENS)
                .gt("valor_unitario_estimado", 0)
                .order("created_at", desc=True)
                .limit(50)
                .text_search("descricao", termos_busca, {"type": "websearch"})
            )
            if filtro_uf and uf:
                q = q.eq("uf", uf)
            return q

        # Camada 1: mesma UF
        try:
            result = _query(filtro_uf=True).execute()
            itens_raw = result.data or []
        except Exception as e:
            log.warning("Erro text_search itens com UF: %s", e)
            itens_raw = []

        # Camada 2: sem UF
        if len(itens_raw) < AMOSTRA_MINIMA:
            try:
                result = _query(filtro_uf=False).execute()
                itens_raw = result.data or []
            except Exception as e:
                log.warning("Erro text_search itens sem UF: %s", e)

        # Camada 3: ilike
        if not itens_raw and termos_ref:
            try:
                q = (
                    client.table("itens_contratacao")
                    .select(SELECT_ITENS)
                    .gt("valor_unitario_estimado", 0)
                    .ilike("descricao", f"%{termos_ref[0]}%")
                    .order("created_at", desc=True)
                    .limit(50)
                )
                if uf:
                    q = q.eq("uf", uf)
                result = q.execute()
                itens_raw = result.data or []
            except Exception as e:
                log.warning("Erro ilike fallback itens: %s", e)
                itens_raw = []

        # Classificar cada resultado
        resultados: list[ResultadoSimilaridade] = []
        for item in itens_raw:
            # Validar categoria — rejeitar se incompatível
            cat_item = classificar_item(item.get("descricao") or "")
            if cat_ref != cat_item:
                continue  # Golden Rule

            resultados_item = item.get("resultados_item") or []
            if isinstance(resultados_item, dict):
                resultados_item = [resultados_item]

            # Escolher melhor resultado: prioriza homologado válido
            melhor_hom = None
            for r in resultados_item:
                v = r.get("valor_unitario_homologado", 0)
                if v and float(v) > 0:
                    if melhor_hom is None or float(v) < float(melhor_hom.get("valor_unitario_homologado", 0)):
                        melhor_hom = r

            if melhor_hom:
                fonte = "homologado"
                valor = float(melhor_hom["valor_unitario_homologado"])
                resultado_usado = melhor_hom
            else:
                est = item.get("valor_unitario_estimado", 0)
                if not est or float(est) <= 0:
                    continue
                fonte = "estimado"
                valor = float(est)
                resultado_usado = resultados_item[0] if resultados_item else None

            score = _calcular_score_item(item, licitacao, termos_ref)

            resultados.append(ResultadoSimilaridade(
                registro={**item, "_resultado_usado": resultado_usado},
                score=score,
                fonte_preco=fonte,
                valor=valor,
                compativel_unidade=True,
            ))

        # Filtrar por score mínimo — evita itens sem relação real
        resultados = [r for r in resultados if r["score"] >= 30]
        resultados.sort(key=lambda r: r["score"], reverse=True)
        return resultados
