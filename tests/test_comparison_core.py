"""Testes do módulo comparison_core — normalização, categorias, validação."""

import pytest
from comparison_core.normalizer import extrair_termos, aplicar_sinonimos, normalizar_descricao
from comparison_core.categories import classificar_item
from comparison_core.validator import (
    is_comparable, validar_unidade, validar_categoria, validar_escala, validar_fonte,
    unidade_canonica,
)
from comparison_core.scorer import ratio_amostra, ratio_recencia, ratio_dispersao


# ═══════════════════════════════════════════════════════════════
#  Normalizer
# ═══════════════════════════════════════════════════════════════

class TestExtrairTermos:
    def test_basico(self):
        resultado = extrair_termos("Licença de uso de software")
        assert "licenca" in resultado  # "licença" → NFKD → "licenca" → sinônimo mantém
        assert "software" in resultado

    def test_aceita_alfanumericos(self):
        resultado = extrair_termos("Papel Sulfite A4 branco")
        assert "a4" in resultado
        assert "sulfite" in resultado

    def test_rejeita_puramente_numerico(self):
        resultado = extrair_termos("Item 123 do lote 456")
        assert "123" not in resultado
        assert "456" not in resultado

    def test_aplica_sinonimos(self):
        resultado = extrair_termos("Sistema de gestão municipal")
        # sistema → software, gestão → gerenciamento
        assert "software" in resultado
        assert "gerenciamento" in resultado
        assert "sistema" not in resultado
        assert "gestao" not in resultado

    def test_remove_stopwords(self):
        resultado = extrair_termos("Aquisição de equipamento para uso")
        assert "de" not in resultado
        assert "para" not in resultado
        assert "aquisicao" not in resultado  # stopword de licitação

    def test_ordena_alfabeticamente(self):
        r1 = extrair_termos("papel sulfite branco")
        r2 = extrair_termos("branco sulfite papel")
        assert r1 == r2

    def test_deduplica(self):
        resultado = extrair_termos("software software software")
        assert resultado.count("software") == 1

    def test_max_termos(self):
        resultado = extrair_termos("computador monitor teclado mouse impressora", max_termos=3)
        assert len(resultado) <= 3

    def test_texto_vazio(self):
        assert extrair_termos("") == []
        assert extrair_termos("   ") == []


class TestAplicarSinonimos:
    def test_substitui(self):
        assert aplicar_sinonimos(["sistema"]) == ["software"]
        assert aplicar_sinonimos(["notebook"]) == ["computador"]

    def test_mantem_desconhecido(self):
        assert aplicar_sinonimos(["xyzabc"]) == ["xyzabc"]


class TestNormalizarDescricao:
    def test_acentos(self):
        assert normalizar_descricao("Licença de Gestão") == "licenca de gestao"

    def test_espacos_extras(self):
        assert normalizar_descricao("  muitos   espacos  ") == "muitos espacos"


# ═══════════════════════════════════════════════════════════════
#  Categories
# ═══════════════════════════════════════════════════════════════

class TestClassificarItem:
    def test_servico(self):
        assert classificar_item("Prestação de serviço de manutenção") == "servico"
        assert classificar_item("Consultoria em tecnologia") == "servico"
        assert classificar_item("Treinamento de pessoal") == "servico"

    def test_licenca(self):
        assert classificar_item("Cessão de uso de software de gestão") == "licenca"
        assert classificar_item("Licenciamento de plataforma SaaS") == "licenca"
        assert classificar_item("Locação de sistema integrado") == "licenca"

    def test_consumivel(self):
        assert classificar_item("Gasolina comum aditivada") == "consumivel"
        assert classificar_item("Papel A4 500 folhas") == "consumivel"
        assert classificar_item("Toner para impressora HP") == "consumivel"
        assert classificar_item("Material de limpeza") == "consumivel"

    def test_produto_fallback(self):
        assert classificar_item("Computador Desktop i7 16GB") == "produto"
        assert classificar_item("Monitor LED 24 polegadas") == "produto"

    def test_prioridade_servico_sobre_licenca(self):
        # "serviço de licenciamento" → serviço tem prioridade
        assert classificar_item("Serviço de licenciamento de software") == "servico"


# ═══════════════════════════════════════════════════════════════
#  Validator — Golden Rule
# ═══════════════════════════════════════════════════════════════

class TestValidarUnidade:
    def test_mesma_unidade(self):
        assert validar_unidade("UN", "un") is True
        assert validar_unidade("Unidade", "UNID") is True

    def test_metro_vs_mililitro(self):
        assert validar_unidade("m", "ml") is False

    def test_kg_vs_quilograma(self):
        assert validar_unidade("kg", "quilograma") is True

    def test_vazio_aceita(self):
        assert validar_unidade("", "kg") is True
        assert validar_unidade("kg", "") is True

    def test_desconhecida_incompativel(self):
        assert validar_unidade("xyz", "abc") is False


class TestValidarCategoria:
    def test_mesma_categoria(self):
        assert validar_categoria("servico", "servico") is True
        assert validar_categoria("produto", "produto") is True

    def test_servico_vs_produto(self):
        assert validar_categoria("servico", "produto") is False

    def test_licenca_vs_consumivel(self):
        assert validar_categoria("licenca", "consumivel") is False

    def test_servico_vs_consumivel(self):
        assert validar_categoria("servico", "consumivel") is False


class TestValidarEscala:
    def test_dentro_do_limite(self):
        assert validar_escala(100, 500, "produto") is True  # 5x < 20x

    def test_fora_do_limite_produto(self):
        assert validar_escala(1, 100, "produto") is False  # 100x > 20x

    def test_licenca_mais_estrita(self):
        assert validar_escala(100, 600, "licenca") is False  # 6x > 5x
        assert validar_escala(100, 400, "licenca") is True   # 4x < 5x

    def test_valor_zero(self):
        assert validar_escala(0, 100, "produto") is False


class TestValidarFonte:
    def test_mesma_fonte(self):
        assert validar_fonte("homologado", "homologado") is True

    def test_fontes_diferentes(self):
        assert validar_fonte("homologado", "estimado") is False


class TestIsComparable:
    def test_gasolina_vs_software(self):
        item_a = {"categoria": "consumivel", "fonte_preco": "homologado", "unidade": "l", "valor": 6.0}
        item_b = {"categoria": "licenca", "fonte_preco": "homologado", "unidade": "un", "valor": 700.0}
        resultado = is_comparable(item_a, item_b)
        assert resultado["comparavel"] is False
        assert resultado["motivo_rejeicao"] == "categorias_incompativeis"

    def test_homologado_vs_estimado(self):
        item_a = {"categoria": "produto", "fonte_preco": "homologado", "unidade": "un", "valor": 100}
        item_b = {"categoria": "produto", "fonte_preco": "estimado", "unidade": "un", "valor": 100}
        resultado = is_comparable(item_a, item_b)
        assert resultado["comparavel"] is False
        assert resultado["motivo_rejeicao"] == "fontes_diferentes"

    def test_itens_compativeis(self):
        item_a = {"categoria": "produto", "fonte_preco": "homologado", "unidade": "un", "valor": 100}
        item_b = {"categoria": "produto", "fonte_preco": "homologado", "unidade": "unidade", "valor": 150}
        resultado = is_comparable(item_a, item_b)
        assert resultado["comparavel"] is True


class TestUnidadeCanonica:
    def test_variantes(self):
        assert unidade_canonica("Unidade") == "pc"  # pc < peca < un < und < unid < unidade
        assert unidade_canonica("KG") == "kg"
        assert unidade_canonica("quilograma") == "kg"


# ═══════════════════════════════════════════════════════════════
#  Scorer
# ═══════════════════════════════════════════════════════════════

class TestRatioAmostra:
    def test_zero(self):
        assert ratio_amostra(0) == 0.0

    def test_minimo(self):
        assert ratio_amostra(3) == pytest.approx(0.5, abs=0.01)

    def test_ideal(self):
        assert ratio_amostra(10) == 1.0

    def test_acima_ideal(self):
        assert ratio_amostra(100) == 1.0


class TestRatioRecencia:
    def test_recente(self):
        assert ratio_recencia(30) == 1.0

    def test_antigo(self):
        assert ratio_recencia(400) == 0.0

    def test_intermediario(self):
        r = ratio_recencia(135)
        assert 0.0 < r < 1.0


class TestRatioDispersao:
    def test_baixa(self):
        assert ratio_dispersao(5) == 1.0

    def test_alta(self):
        assert ratio_dispersao(60) == 0.0

    def test_nenhuma(self):
        assert ratio_dispersao(None) == 0.5
