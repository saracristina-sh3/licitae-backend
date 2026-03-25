"""Testes unitários do comparativo de mercado v2."""

from __future__ import annotations

import pytest

from market_comparison.services.price_selection import selecionar_preco
from market_comparison.services.unit_validation import unidades_compativeis, validar_consistencia
from market_comparison.services.comparability import calcular_score
from market_comparison.services.grouping import converter_item_raw
from market_comparison.strategies.ncm_lexical import NcmLexicalStrategy
from market_comparison.types import ObservedItem


# ── Price Selection ──────────────────────────────────────────

class TestPriceSelection:
    def test_prioriza_menor_homologado(self):
        resultados = [
            {"valor_unitario_homologado": 100, "percentual_desconto": 10},
            {"valor_unitario_homologado": 50, "percentual_desconto": 20},
        ]
        valor, fonte, desc = selecionar_preco(resultados, 200)
        assert valor == 50
        assert fonte == "homologado"
        assert desc == 20

    def test_fallback_estimado(self):
        resultados = [{"valor_unitario_homologado": 0}]
        valor, fonte, desc = selecionar_preco(resultados, 100)
        assert valor == 100
        assert fonte == "estimado"
        assert desc is None

    def test_sem_resultados(self):
        valor, fonte, _ = selecionar_preco([], 50)
        assert valor == 50
        assert fonte == "estimado"

    def test_desconto_invalido_ignorado(self):
        resultados = [{"valor_unitario_homologado": 100, "percentual_desconto": 95}]
        _, _, desc = selecionar_preco(resultados, 200)
        assert desc is None

    def test_resultados_dict(self):
        resultado = {"valor_unitario_homologado": 80, "percentual_desconto": 5}
        valor, fonte, _ = selecionar_preco(resultado, 100)
        assert valor == 80
        assert fonte == "homologado"


# ── Unit Validation ──────────────────────────────────────────

class TestUnitValidation:
    def test_mesma_unidade(self):
        assert unidades_compativeis("UN", "un") is True

    def test_grupo_compativel(self):
        assert unidades_compativeis("kg", "quilograma") is True
        assert unidades_compativeis("un", "unidade") is True

    def test_incompativel(self):
        assert unidades_compativeis("kg", "litro") is False

    def test_vazia_compativel(self):
        assert unidades_compativeis("", "un") is True
        assert unidades_compativeis("", "") is True

    def test_consistencia_grupo(self):
        itens = [
            ObservedItem("desc", None, "un", "P1", 1, 10, "hom"),
            ObservedItem("desc", None, "unidade", "P1", 1, 10, "hom"),
            ObservedItem("desc", None, "kg", "P2", 2, 10, "est"),
        ]
        unidade, taxa = validar_consistencia(itens)
        assert taxa > 0
        assert unidade != ""


# ── Grouping Strategy ────────────────────────────────────────

class TestGroupingStrategy:
    def test_ncm_gera_chave_com_unidade(self):
        strategy = NcmLexicalStrategy()
        item = ObservedItem("desc", "12345678", "un", "P1", 1, 10, "hom")
        chave = strategy.gerar_chave(item)
        assert chave.startswith("ncm:")
        assert "12345678" in chave

    def test_sem_ncm_usa_descricao(self):
        strategy = NcmLexicalStrategy()
        item = ObservedItem("gasolina comum posto cidade", None, "litro", "P1", 1, 5, "est")
        chave = strategy.gerar_chave(item)
        assert chave.startswith("desc:")
        assert "gasolina" in chave

    def test_descricao_curta_retorna_vazio(self):
        strategy = NcmLexicalStrategy()
        item = ObservedItem("de", None, "un", "P1", 1, 10, "hom")
        assert strategy.gerar_chave(item) == ""

    def test_unidade_na_chave_evita_mistura(self):
        strategy = NcmLexicalStrategy()
        item_kg = ObservedItem("arroz tipo especial", None, "kg", "P1", 1, 10, "hom")
        item_un = ObservedItem("arroz tipo especial", None, "un", "P1", 1, 10, "hom")
        assert strategy.gerar_chave(item_kg) != strategy.gerar_chave(item_un)


# ── Converter Item Raw ───────────────────────────────────────

class TestConverterItemRaw:
    def test_item_valido(self):
        row = {
            "descricao": "Gasolina comum",
            "ncm_nbs_codigo": None,
            "unidade_medida": "litro",
            "plataforma_nome": "P1",
            "plataforma_id": 121,
            "valor_unitario_estimado": 5.5,
            "resultados_item": [{"valor_unitario_homologado": 4.8, "percentual_desconto": 12}],
        }
        item = converter_item_raw(row)
        assert item is not None
        assert item.valor == 4.8
        assert item.fonte_preco == "homologado"

    def test_sem_plataforma_retorna_none(self):
        row = {"plataforma_nome": "", "valor_unitario_estimado": 10}
        assert converter_item_raw(row) is None

    def test_valor_zero_retorna_none(self):
        row = {
            "plataforma_nome": "P1", "plataforma_id": 1,
            "valor_unitario_estimado": 0, "resultados_item": [],
        }
        assert converter_item_raw(row) is None


# ── Comparability Score ──────────────────────────────────────

class TestComparabilityScore:
    def test_ncm_com_boa_amostra(self):
        itens_p1 = [ObservedItem("desc", "123", "un", "P1", 1, v, "homologado") for v in [10, 11, 12, 13, 14]]
        itens_p2 = [ObservedItem("desc", "123", "un", "P2", 2, v, "homologado") for v in [11, 12, 13, 14, 15]]

        score, faixa = calcular_score(
            "ncm:123:un",
            {"P1": itens_p1, "P2": itens_p2},
            taxa_consistencia_unidade=1.0,
        )
        assert score >= 70
        assert faixa == "alta"

    def test_sem_ncm_alta_dispersao(self):
        itens_p1 = [ObservedItem("desc", None, "un", "P1", 1, v, "estimado") for v in [1, 100]]
        itens_p2 = [ObservedItem("desc", None, "un", "P2", 2, v, "estimado") for v in [5, 200]]

        score, faixa = calcular_score(
            "desc:algo:un",
            {"P1": itens_p1, "P2": itens_p2},
            taxa_consistencia_unidade=0.3,
        )
        assert score < 40
        assert faixa == "baixa"

    def test_amostra_minima(self):
        itens_p1 = [ObservedItem("desc", None, "un", "P1", 1, 10, "hom")]
        itens_p2 = [ObservedItem("desc", None, "un", "P2", 2, 11, "hom")]

        score, _ = calcular_score(
            "desc:algo:un",
            {"P1": itens_p1, "P2": itens_p2},
            taxa_consistencia_unidade=1.0,
        )
        # Amostra mínima = score parcial
        assert 0 < score < 70
