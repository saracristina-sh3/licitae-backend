"""
Estratégia de similaridade baseada em text_search do PostgreSQL.

Implementa busca em camadas com fallback:
1. text_search (websearch) + mesma UF + mesma modalidade
2. text_search sem filtro de UF
3. ilike como último recurso

Cada resultado recebe um score heurístico de similaridade (0-100).
"""

from __future__ import annotations

import logging
from datetime import datetime

from utils import normalizar
from pricing_reference.constants import (
    AMOSTRA_MINIMA,
    SELECT_ITENS,
    SIM_MESMA_MODALIDADE,
    SIM_MESMA_UF,
    SIM_NCM_IGUAL,
    SIM_RECENTE,
    SIM_TERMOS_COMUNS,
    SIM_UNIDADE_IGUAL,
    STOPWORDS,
)
from pricing_reference.types import ResultadoSimilaridade

log = logging.getLogger(__name__)


def _extrair_termos(texto: str) -> list[str]:
    """Extrai termos significativos de um texto (sem stopwords, >3 chars)."""
    return [
        p for p in normalizar(texto).split()
        if len(p) > 3 and p not in STOPWORDS
    ]


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
    - Termos em comum: até +20 (proporcional)
    - Recência (< 6 meses): +10
    - NCM: +25 (não aplicável em licitações, reservado para itens)
    - Unidade: +10 (não aplicável em licitações)
    """
    score = 0.0

    # Modalidade
    if similar.get("modalidade") and similar["modalidade"] == licitacao_ref.get("modalidade"):
        score += SIM_MESMA_MODALIDADE

    # UF
    if similar.get("uf") and similar["uf"] == licitacao_ref.get("uf"):
        score += SIM_MESMA_UF

    # Termos em comum
    if termos_ref:
        objeto_similar = normalizar(similar.get("objeto") or "")
        termos_comuns = sum(1 for t in termos_ref if t in objeto_similar)
        ratio = min(termos_comuns / len(termos_ref), 1.0)
        score += SIM_TERMOS_COMUNS * ratio

    # Recência (< 6 meses = máximo, até 12 meses = proporcional)
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
    # Escalar para usar a faixa completa
    score = min(score * (100 / 65), 100)

    return round(score, 2)


def _calcular_score_item(
    item: dict,
    licitacao_ref: dict,
    termos_ref: list[str],
) -> float:
    """
    Calcula score de similaridade (0-100) para um item.
    Inclui NCM e unidade de medida como fatores.
    """
    score = 0.0

    # UF
    if item.get("uf") and item["uf"] == licitacao_ref.get("uf"):
        score += SIM_MESMA_UF

    # NCM
    # Reservado — itens_contratacao geralmente não têm NCM preenchido
    # Se tiver, seria um match forte

    # Termos em comum na descrição
    if termos_ref:
        desc_item = normalizar(item.get("descricao") or "")
        termos_comuns = sum(1 for t in termos_ref if t in desc_item)
        ratio = min(termos_comuns / len(termos_ref), 1.0)
        score += SIM_TERMOS_COMUNS * ratio

    # Unidade de medida
    # Não penaliza se não informado, mas bonifica se igual
    unidade_ref = normalizar(licitacao_ref.get("unidade_medida") or "")
    unidade_item = normalizar(item.get("unidade_medida") or "")
    if unidade_ref and unidade_item and unidade_ref == unidade_item:
        score += SIM_UNIDADE_IGUAL

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


def _unidades_compativeis(u1: str, u2: str) -> bool:
    """Verifica se duas unidades de medida são compatíveis."""
    if not u1 or not u2:
        return True  # Se não informado, assumir compatível
    n1 = normalizar(u1).strip()
    n2 = normalizar(u2).strip()
    if n1 == n2:
        return True
    # Grupos compatíveis
    grupos = [
        {"un", "und", "unid", "unidade", "peca", "pc"},
        {"kg", "quilo", "quilograma"},
        {"l", "lt", "litro"},
        {"m", "metro", "ml", "metro linear"},
        {"m2", "m²", "metro quadrado"},
        {"cx", "caixa"},
        {"pct", "pacote"},
        {"fr", "frasco"},
        {"tb", "tubo"},
        {"rl", "rolo"},
        {"mes", "mensal", "meses"},
        {"hora", "h", "hr"},
    ]
    for grupo in grupos:
        if n1 in grupo and n2 in grupo:
            return True
    return False


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
        termos_ref = _extrair_termos(licitacao.get("objeto") or "")

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

        # Ordenar por score decrescente
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
        termos_ref = _extrair_termos(objeto)

        if not termos_ref:
            return []

        termos_busca = " & ".join(termos_ref[:3])

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

            # Verificar compatibilidade de unidade
            unidade_item = item.get("unidade_medida") or ""
            compativel = True  # Sem unidade de referência na licitação para comparar

            resultados.append(ResultadoSimilaridade(
                registro={**item, "_resultado_usado": resultado_usado},
                score=score,
                fonte_preco=fonte,
                valor=valor,
                compativel_unidade=compativel,
            ))

        resultados.sort(key=lambda r: r["score"], reverse=True)
        return resultados
