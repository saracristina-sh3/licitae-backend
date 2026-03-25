"""Testes unitários do motor de preços de referência v2."""

from __future__ import annotations

import pytest

from pricing_reference.services.estatistica import (
    calcular_percentis,
    calcular_resumo,
    coeficiente_variacao,
    media_saneada,
    remover_outliers_iqr,
)
from pricing_reference.services.confiabilidade import calcular_score


# ── Estatística: remover_outliers_iqr ────────────────────────

class TestRemoverOutliersIQR:
    def test_lista_vazia(self):
        assert remover_outliers_iqr([]) == []

    def test_menos_de_4_valores_retorna_original(self):
        assert remover_outliers_iqr([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]

    def test_remove_outlier_superior(self):
        valores = [10.0, 12.0, 11.0, 13.0, 14.0, 100.0]
        resultado = remover_outliers_iqr(valores)
        assert 100.0 not in resultado
        assert len(resultado) < len(valores)

    def test_remove_outlier_inferior(self):
        valores = [0.1, 50.0, 52.0, 48.0, 55.0, 51.0]
        resultado = remover_outliers_iqr(valores)
        assert 0.1 not in resultado

    def test_dados_uniformes_nao_remove(self):
        valores = [10.0, 11.0, 12.0, 13.0, 14.0]
        resultado = remover_outliers_iqr(valores)
        assert len(resultado) == len(valores)


# ── Estatística: media_saneada ───────────────────────────────

class TestMediaSaneada:
    def test_lista_vazia(self):
        assert media_saneada([]) is None

    def test_um_valor(self):
        assert media_saneada([42.0]) == 42.0

    def test_poucos_valores_usa_media_simples(self):
        result = media_saneada([10.0, 20.0, 30.0])
        assert result == 20.0

    def test_descarta_extremos(self):
        valores = [1.0, 10.0, 11.0, 12.0, 13.0, 14.0, 100.0]
        result = media_saneada(valores)
        assert result is not None
        # Deve estar entre média simples e mediana
        assert 10.0 < result < 25.0


# ── Estatística: coeficiente_variacao ────────────────────────

class TestCoeficienteVariacao:
    def test_lista_vazia(self):
        assert coeficiente_variacao([]) is None

    def test_um_valor(self):
        assert coeficiente_variacao([5.0]) is None

    def test_valores_identicos(self):
        result = coeficiente_variacao([10.0, 10.0, 10.0])
        assert result == 0.0

    def test_media_zero(self):
        assert coeficiente_variacao([0.0, 0.0]) is None

    def test_valores_variados(self):
        result = coeficiente_variacao([10.0, 20.0, 30.0])
        assert result is not None
        assert result > 0


# ── Estatística: calcular_percentis ──────────────────────────

class TestCalcularPercentis:
    def test_lista_vazia(self):
        p25, p50, p75 = calcular_percentis([])
        assert p25 is None
        assert p50 is None
        assert p75 is None

    def test_um_valor(self):
        p25, p50, p75 = calcular_percentis([42.0])
        assert p25 == 42.0
        assert p50 == 42.0
        assert p75 == 42.0

    def test_valores_ordenados(self):
        p25, p50, p75 = calcular_percentis([10.0, 20.0, 30.0, 40.0, 50.0])
        assert p25 is not None
        assert p50 is not None
        assert p75 is not None
        assert p25 < p50 < p75


# ── Estatística: calcular_resumo ─────────────────────────────

class TestCalcularResumo:
    def test_lista_vazia(self):
        resumo = calcular_resumo([])
        assert resumo["total"] == 0
        assert resumo["media"] is None
        assert resumo["mediana"] is None

    def test_um_valor(self):
        resumo = calcular_resumo([100.0])
        assert resumo["total"] == 1
        assert resumo["media"] == 100.0
        assert resumo["mediana"] == 100.0
        assert resumo["desvio_padrao"] is None

    def test_valores_completos(self):
        resumo = calcular_resumo([10.0, 20.0, 30.0, 40.0, 50.0])
        assert resumo["total"] == 5
        assert resumo["minimo"] == 10.0
        assert resumo["maximo"] == 50.0
        assert resumo["media"] == 30.0
        assert resumo["desvio_padrao"] is not None
        assert resumo["coeficiente_variacao"] is not None
        assert resumo["percentil_25"] is not None
        assert resumo["percentil_75"] is not None


# ── Confiabilidade ───────────────────────────────────────────

class TestScoreConfiabilidade:
    def test_amostra_insuficiente(self):
        result = calcular_score(
            total_amostra=1,
            cv=10.0,
            pct_homologados=1.0,
            recencia_dias_media=30,
            score_similaridade_medio=80,
        )
        assert result["faixa"] == "insuficiente"

    def test_tudo_otimo_score_alto(self):
        result = calcular_score(
            total_amostra=15,
            cv=8.0,
            pct_homologados=0.95,
            recencia_dias_media=30,
            score_similaridade_medio=80,
        )
        assert result["score"] >= 70
        assert result["faixa"] == "alta"
        assert "amostra" in result["fatores"]
        assert "recencia" in result["fatores"]

    def test_dados_antigos_score_menor(self):
        result = calcular_score(
            total_amostra=10,
            cv=15.0,
            pct_homologados=0.5,
            recencia_dias_media=300,
            score_similaridade_medio=50,
        )
        assert result["score"] < 70

    def test_alta_dispersao_penaliza(self):
        result_baixo_cv = calcular_score(10, 10.0, 0.8, 60, 70)
        result_alto_cv = calcular_score(10, 60.0, 0.8, 60, 70)
        assert result_baixo_cv["score"] > result_alto_cv["score"]

    def test_fatores_somam_corretamente(self):
        result = calcular_score(10, 15.0, 0.9, 60, 70)
        soma_fatores = sum(result["fatores"].values())
        assert abs(soma_fatores - result["score"]) < 0.2  # tolerância de arredondamento

    def test_sem_homologados_ainda_pontua(self):
        result = calcular_score(10, 15.0, 0.0, 60, 70)
        assert result["fatores"]["homologados"] > 0  # 0% hom. ainda dá 0.2 * peso

    def test_cv_none_zero_dispersao(self):
        result = calcular_score(10, None, 0.8, 60, 70)
        assert result["fatores"]["baixa_dispersao"] == 0.0
