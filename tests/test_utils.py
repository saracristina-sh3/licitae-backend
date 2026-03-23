"""Testes para funções utilitárias: normalização, classificação, FPM e ME/EPP."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils import (
    normalizar,
    match_palavras_chave,
    classificar_relevancia,
    detectar_me_epp,
    fpm_coeficiente,
    fpm_para_populacao,
)


# ── Normalização ────────────────────────────────────────────


class TestNormalizar:
    def test_remove_acentos(self):
        assert normalizar("permissão") == "permissao"
        assert normalizar("licitação") == "licitacao"
        assert normalizar("gestão pública") == "gestao publica"

    def test_lowercase(self):
        assert normalizar("SOFTWARE") == "software"
        assert normalizar("Sistema Integrado") == "sistema integrado"

    def test_string_vazia(self):
        assert normalizar("") == ""

    def test_sem_acentos(self):
        assert normalizar("software") == "software"


# ── Match Palavras-chave ────────────────────────────────────


class TestMatchPalavrasChave:
    def test_match_simples(self):
        resultado = match_palavras_chave("Contratação de software", ["software"])
        assert resultado == ["software"]

    def test_match_com_acento(self):
        resultado = match_palavras_chave(
            "Permissão de uso de sistema", ["permissão de uso"]
        )
        assert resultado == ["permissão de uso"]

    def test_sem_match(self):
        resultado = match_palavras_chave("Compra de material", ["software"])
        assert resultado == []

    def test_multiplos_matches(self):
        texto = "Licença de uso de software integrado"
        resultado = match_palavras_chave(texto, ["licença de uso", "software", "hardware"])
        assert "licença de uso" in resultado
        assert "software" in resultado
        assert "hardware" not in resultado

    def test_case_insensitive(self):
        resultado = match_palavras_chave("SISTEMA DE GESTÃO", ["sistema de gestão"])
        assert resultado == ["sistema de gestão"]


# ── Classificação de Relevância ─────────────────────────────


class TestClassificarRelevancia:
    def test_relevancia_alta(self):
        assert classificar_relevancia([], "permissão de uso de software") == "ALTA"
        assert classificar_relevancia([], "Licença de uso do sistema") == "ALTA"
        assert classificar_relevancia([], "Locação de software integrado") == "ALTA"
        assert classificar_relevancia([], "cessão de uso do sistema") == "ALTA"

    def test_relevancia_media(self):
        assert classificar_relevancia([], "contratação de software") == "MEDIA"
        assert classificar_relevancia([], "Sistema de gestão pública") == "MEDIA"
        assert classificar_relevancia([], "solução tecnológica integrada") == "MEDIA"

    def test_relevancia_baixa(self):
        assert classificar_relevancia([], "compra de material de escritório") == "BAIXA"

    def test_termos_customizados(self):
        assert classificar_relevancia(
            [], "sistema xyz", termos_alta=["sistema xyz"]
        ) == "ALTA"

    def test_alta_prevalece_sobre_media(self):
        # Texto com termos de alta e média — alta deve prevalecer
        assert classificar_relevancia(
            [], "permissão de uso de software"
        ) == "ALTA"


# ── Detecção ME/EPP ─────────────────────────────────────────


class TestDetectarMeEpp:
    def test_exclusivo_me(self):
        assert detectar_me_epp("Exclusivo para microempresa e EPP") is True

    def test_cota_reservada(self):
        assert detectar_me_epp("cota reservada para ME/EPP") is True

    def test_lei_complementar(self):
        assert detectar_me_epp("conforme lei complementar 123") is True

    def test_sem_me_epp(self):
        assert detectar_me_epp("licitação aberta a todos") is False

    def test_case_insensitive(self):
        assert detectar_me_epp("EXCLUSIVO PARA MICROEMPRESA") is True


# ── FPM ──────────────────────────────────────────────────────


class TestFpmCoeficiente:
    def test_menor_faixa(self):
        assert fpm_coeficiente(5000) == 0.6

    def test_faixa_28(self):
        assert fpm_coeficiente(91692) == 2.8

    def test_acima_ultima_faixa(self):
        assert fpm_coeficiente(200000) == 4.0

    def test_limite_exato(self):
        assert fpm_coeficiente(10188) == 0.6
        assert fpm_coeficiente(10189) == 0.8


class TestFpmParaPopulacao:
    def test_fpm_28(self):
        assert fpm_para_populacao(2.8) == 91692

    def test_fpm_06(self):
        assert fpm_para_populacao(0.6) == 10188

    def test_fpm_acima(self):
        assert fpm_para_populacao(5.0) == 999999

    def test_roundtrip(self):
        # fpm_coeficiente(fpm_para_populacao(x)) deve retornar x
        for fpm in [0.6, 1.0, 2.0, 2.8]:
            pop = fpm_para_populacao(fpm)
            assert fpm_coeficiente(pop) == fpm
