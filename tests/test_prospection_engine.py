"""Testes unitários do motor de prospecção v1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from prospection_engine.constants import (
    FAIXA_ALTA,
    FAIXA_MEDIA,
    URGENCIA_CRITICA_DIAS,
    URGENCIA_PROXIMA_DIAS,
)
from prospection_engine.services.deduplication import chave_dedup, deduplicar
from prospection_engine.services.filtering import proposta_encerrada, resolver_municipio
from prospection_engine.services.matching import match_contratacao
from prospection_engine.services.orchestration import _gerar_janelas, _resolver_periodo
from prospection_engine.services.result_builder import _extrair_url_pncp, montar_resultado
from prospection_engine.services.scoring import calcular_score, calcular_urgencia, score_para_relevancia
from prospection_engine.types import BuscaConfig, MatchResult


# ── Matching ─────────────────────────────────────────────────


class TestMatching:
    def test_match_no_objeto(self):
        c = {"objetoCompra": "Contratação de software de gestão", "informacaoComplementar": ""}
        result = match_contratacao(c, ["software"])
        assert result.matched is True
        assert "software" in result.termos_encontrados
        assert "objeto" in result.campos_matched

    def test_match_no_complementar(self):
        c = {"objetoCompra": "Contratação de serviço", "informacaoComplementar": "sistema de gestão pública"}
        result = match_contratacao(c, ["sistema de gestão"])
        assert result.matched is True
        assert "complementar" in result.campos_matched

    def test_match_em_ambos(self):
        c = {"objetoCompra": "Licença de software", "informacaoComplementar": "software de gestão"}
        result = match_contratacao(c, ["software"])
        assert result.matched is True
        assert "objeto" in result.campos_matched
        assert "complementar" in result.campos_matched

    def test_sem_match(self):
        c = {"objetoCompra": "Compra de cadeiras", "informacaoComplementar": ""}
        result = match_contratacao(c, ["software", "sistema"])
        assert result.matched is False
        assert result.termos_encontrados == []

    def test_exclusao_bloqueia_match(self):
        c = {"objetoCompra": "Contratação de software", "informacaoComplementar": ""}
        result = match_contratacao(c, ["software"], termos_exclusao=["software"])
        assert result.matched is False

    def test_match_case_insensitive(self):
        c = {"objetoCompra": "LICENÇA DE USO de SOFTWARE", "informacaoComplementar": ""}
        result = match_contratacao(c, ["licença de uso"])
        assert result.matched is True

    def test_match_com_acentos(self):
        c = {"objetoCompra": "Solução tecnológica", "informacaoComplementar": ""}
        result = match_contratacao(c, ["solucao tecnologica"])
        assert result.matched is True

    def test_sem_duplicatas_nos_termos(self):
        c = {"objetoCompra": "software de gestão", "informacaoComplementar": "sistema software"}
        result = match_contratacao(c, ["software"])
        assert result.termos_encontrados.count("software") == 1


# ── Scoring ──────────────────────────────────────────────────


class TestScoring:
    def _cfg(self) -> BuscaConfig:
        return BuscaConfig(
            palavras_chave=["software", "sistema"],
            termos_alta=["licença de uso"],
            termos_media=["software"],
            termos_me_epp=["exclusivo me/epp"],
        )

    def test_score_basico_objeto(self):
        match = MatchResult(matched=True, termos_encontrados=["software"], campos_matched=["objeto"])
        c = {"objetoCompra": "software de gestão", "informacaoComplementar": "", "valorTotalEstimado": 50000}
        score = calcular_score(match, c, self._cfg())
        assert score > 0

    def test_score_com_termos_alta(self):
        match = MatchResult(matched=True, termos_encontrados=["software"], campos_matched=["objeto"])
        c = {"objetoCompra": "licença de uso de software", "informacaoComplementar": "", "valorTotalEstimado": 50000}
        score = calcular_score(match, c, self._cfg())
        assert score >= FAIXA_ALTA

    def test_score_complementar_adiciona_pontos(self):
        match_obj = MatchResult(matched=True, termos_encontrados=["software"], campos_matched=["objeto"])
        match_ambos = MatchResult(matched=True, termos_encontrados=["software"], campos_matched=["objeto", "complementar"])
        c = {"objetoCompra": "software", "informacaoComplementar": "sistema", "valorTotalEstimado": 0}
        score_obj = calcular_score(match_obj, c, self._cfg())
        score_ambos = calcular_score(match_ambos, c, self._cfg())
        assert score_ambos > score_obj

    def test_score_valor_dentro_faixa(self):
        match = MatchResult(matched=True, termos_encontrados=["software"], campos_matched=["objeto"])
        c_faixa = {"objetoCompra": "software", "informacaoComplementar": "", "valorTotalEstimado": 100_000}
        c_fora = {"objetoCompra": "software", "informacaoComplementar": "", "valorTotalEstimado": 5_000_000}
        score_faixa = calcular_score(match, c_faixa, self._cfg())
        score_fora = calcular_score(match, c_fora, self._cfg())
        assert score_faixa > score_fora

    def test_score_me_epp_bonus(self):
        match = MatchResult(matched=True, termos_encontrados=["software"], campos_matched=["objeto"])
        c_sem = {"objetoCompra": "software", "informacaoComplementar": "", "valorTotalEstimado": 0}
        c_com = {"objetoCompra": "software", "informacaoComplementar": "exclusivo me/epp", "valorTotalEstimado": 0}
        score_sem = calcular_score(match, c_sem, self._cfg())
        score_com = calcular_score(match, c_com, self._cfg())
        assert score_com > score_sem

    def test_score_nao_ultrapassa_100(self):
        match = MatchResult(
            matched=True,
            termos_encontrados=["software", "sistema"],
            campos_matched=["objeto", "complementar"],
        )
        c = {
            "objetoCompra": "licença de uso de software exclusivo me/epp",
            "informacaoComplementar": "sistema exclusivo me/epp",
            "valorTotalEstimado": 100_000,
        }
        score = calcular_score(match, c, self._cfg())
        assert score <= 100.0


# ── Score para Relevância ────────────────────────────────────


class TestScoreParaRelevancia:
    def test_alta(self):
        assert score_para_relevancia(65.0) == "ALTA"
        assert score_para_relevancia(100.0) == "ALTA"

    def test_media(self):
        assert score_para_relevancia(35.0) == "MEDIA"
        assert score_para_relevancia(64.9) == "MEDIA"

    def test_baixa(self):
        assert score_para_relevancia(0.0) == "BAIXA"
        assert score_para_relevancia(34.9) == "BAIXA"


# ── Urgência ─────────────────────────────────────────────────


class TestUrgencia:
    def test_urgente(self):
        dt = (datetime.now(tz=timezone.utc) + timedelta(days=2)).isoformat()
        assert calcular_urgencia(dt) == "URGENTE"

    def test_proxima(self):
        dt = (datetime.now(tz=timezone.utc) + timedelta(days=5)).isoformat()
        assert calcular_urgencia(dt) == "PROXIMA"

    def test_normal(self):
        dt = (datetime.now(tz=timezone.utc) + timedelta(days=15)).isoformat()
        assert calcular_urgencia(dt) == "NORMAL"

    def test_sem_data(self):
        assert calcular_urgencia(None) == "NORMAL"

    def test_data_invalida(self):
        assert calcular_urgencia("nao-e-data") == "NORMAL"

    def test_data_passada_eh_urgente(self):
        dt = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
        assert calcular_urgencia(dt) == "URGENTE"


# ── Deduplicação ─────────────────────────────────────────────


class TestDeduplicacao:
    def _contratacao(self, cnpj: str, ano: int, seq: int) -> dict:
        return {
            "orgaoEntidade": {"cnpj": cnpj},
            "anoCompra": ano,
            "sequencialCompra": seq,
        }

    def test_chave_dedup(self):
        c = self._contratacao("12345678000100", 2026, 42)
        assert chave_dedup(c) == "12345678000100_2026_42"

    def test_chave_campos_faltando(self):
        c = {"orgaoEntidade": {}, "anoCompra": None}
        chave = chave_dedup(c)
        assert chave == "__"

    def test_remove_duplicata_mantendo_maior_score(self):
        c1 = self._contratacao("123", 2026, 1)
        c2 = self._contratacao("123", 2026, 1)
        m1 = MatchResult(matched=True, score=50.0)
        m2 = MatchResult(matched=True, score=80.0)
        mun = {"nome": "Cidade", "uf": "MG"}

        resultado = deduplicar([(c1, mun, m1), (c2, mun, m2)])
        assert len(resultado) == 1
        assert resultado[0][2].score == 80.0

    def test_sem_duplicatas(self):
        c1 = self._contratacao("123", 2026, 1)
        c2 = self._contratacao("456", 2026, 2)
        m1 = MatchResult(matched=True, score=50.0)
        m2 = MatchResult(matched=True, score=60.0)
        mun = {"nome": "Cidade", "uf": "MG"}

        resultado = deduplicar([(c1, mun, m1), (c2, mun, m2)])
        assert len(resultado) == 2


# ── Filtering ────────────────────────────────────────────────


class TestFiltering:
    def test_proposta_encerrada(self):
        ontem = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
        c = {"dataEncerramentoProposta": ontem}
        assert proposta_encerrada(c) is True

    def test_proposta_aberta(self):
        amanha = (datetime.now(tz=timezone.utc) + timedelta(days=1)).isoformat()
        c = {"dataEncerramentoProposta": amanha}
        assert proposta_encerrada(c) is False

    def test_proposta_sem_data(self):
        c = {"dataEncerramentoProposta": None}
        assert proposta_encerrada(c) is False

    def test_proposta_data_invalida(self):
        c = {"dataEncerramentoProposta": "invalido"}
        assert proposta_encerrada(c) is False

    def test_municipio_no_mapa(self):
        mapa = {"3106200": {"nome": "BH", "uf": "MG"}}
        c = {"unidadeOrgao": {"codigoIbge": "3106200"}, "orgaoEntidade": {}}
        assert resolver_municipio(c, mapa) is not None

    def test_municipio_fora_do_mapa(self):
        mapa = {"3106200": {"nome": "BH", "uf": "MG"}}
        c = {"unidadeOrgao": {"codigoIbge": "9999999"}, "orgaoEntidade": {}}
        assert resolver_municipio(c, mapa) is None

    def test_municipio_fallback_orgao(self):
        mapa = {"3106200": {"nome": "BH", "uf": "MG"}}
        c = {"unidadeOrgao": {}, "orgaoEntidade": {"codigoMunicipioIbge": "3106200"}}
        assert resolver_municipio(c, mapa) is not None


# ── Result Builder ───────────────────────────────────────────


class TestResultBuilder:
    def test_url_pncp(self):
        c = {"orgaoEntidade": {"cnpj": "12345678000100"}, "anoCompra": 2026, "sequencialCompra": 42}
        url = _extrair_url_pncp(c)
        assert url == "https://pncp.gov.br/app/editais/12345678000100/2026/42"

    def test_url_pncp_campos_faltando(self):
        c = {"orgaoEntidade": {}, "anoCompra": None, "sequencialCompra": None}
        assert _extrair_url_pncp(c) == ""

    def test_montar_resultado_completo(self):
        c = {
            "objetoCompra": "Software de gestão",
            "informacaoComplementar": "Sistema integrado",
            "orgaoEntidade": {"cnpj": "123", "razaoSocial": "Prefeitura"},
            "modalidadeId": 6,
            "valorTotalEstimado": 100000,
            "valorTotalHomologado": 0,
            "situacaoCompraNome": "Aberta",
            "dataPublicacaoPncp": "2026-03-20",
            "dataAberturaProposta": "2026-03-25",
            "dataEncerramentoProposta": "2026-04-05",
            "anoCompra": 2026,
            "sequencialCompra": 1,
            "unidadeOrgao": {},
        }
        mun_info = {"nome": "Cidade", "uf": "MG", "populacao": 50000, "fpm": 2.0, "codigo_ibge": "3100104"}
        match = MatchResult(matched=True, termos_encontrados=["software"], score=75.0, campos_matched=["objeto"])
        cfg = BuscaConfig(palavras_chave=["software"])

        resultado = montar_resultado(c, mun_info, match, cfg, "NORMAL")

        assert resultado["municipio"] == "Cidade"
        assert resultado["score"] == 75.0
        assert resultado["relevancia"] == "ALTA"
        assert resultado["urgencia"] == "NORMAL"
        assert resultado["informacao_complementar"] == "Sistema integrado"
        assert resultado["palavras_chave_encontradas"] == "software"
        assert resultado["fonte"] == "PNCP"


# ── Janelas e Período ────────────────────────────────────────


class TestJanelas:
    def test_janela_unica(self):
        janelas = _gerar_janelas("20260325", "20260325", dias=1)
        assert len(janelas) == 1
        assert janelas[0] == ("20260325", "20260325")

    def test_janelas_multiplas(self):
        janelas = _gerar_janelas("20260320", "20260325", dias=2)
        assert len(janelas) == 3

    def test_janela_maior_que_periodo(self):
        janelas = _gerar_janelas("20260320", "20260322", dias=10)
        assert len(janelas) == 1

    def test_resolver_periodo_explicito(self):
        inicio, fim = _resolver_periodo(None, "20260101", "20260131")
        assert inicio == "20260101"
        assert fim == "20260131"

    def test_resolver_periodo_dias(self):
        inicio, fim = _resolver_periodo(3, None, None)
        assert inicio != fim
