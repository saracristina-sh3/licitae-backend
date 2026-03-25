"""Testes unitários do analisador de editais v2."""

from __future__ import annotations

import pytest

from edital_analysis.services.file_selection import ranquear_arquivos
from edital_analysis.services.pdf_extraction import avaliar_qualidade
from edital_analysis.services.text_preprocessing import preprocessar
from edital_analysis.services.regex_extraction import (
    extrair_documentos, extrair_requisitos, extrair_riscos, extrair_qualificacao,
)
from edital_analysis.services.prazo_extraction import extrair_prazos
from edital_analysis.services.risk_scoring import calcular_score_risco
from edital_analysis.services.confidence import calcular_score_confianca
from edital_analysis.types import AchadoEstruturado, ArquivoRanqueado, QualidadeExtracao


# ── File Selection ───────────────────────────────────────────

class TestFileSelection:
    def test_edital_tem_maior_score_que_anexo(self):
        arquivos = [
            {"url": "http://x/1", "titulo": "Anexo I - Planilha"},
            {"url": "http://x/2", "titulo": "Edital Pregão 001/2026"},
        ]
        ranqueados = ranquear_arquivos(arquivos)
        assert ranqueados[0].titulo == "Edital Pregão 001/2026"

    def test_termo_referencia_score_alto(self):
        arquivos = [
            {"url": "http://x/1", "titulo": "Aviso de Licitação"},
            {"url": "http://x/2", "titulo": "Termo de Referência"},
        ]
        ranqueados = ranquear_arquivos(arquivos)
        assert ranqueados[0].titulo == "Termo de Referência"

    def test_lista_vazia(self):
        assert ranquear_arquivos([]) == []

    def test_sem_url_ignora(self):
        arquivos = [{"titulo": "Edital"}]
        assert ranquear_arquivos(arquivos) == []


# ── PDF Extraction ───────────────────────────────────────────

class TestQualidadeExtracao:
    def test_texto_vazio_score_zero(self):
        q = avaliar_qualidade("")
        assert q.score == 0.0
        assert q.faixa == "ruim"

    def test_texto_bom_score_alto(self):
        texto = "Este é um edital de licitação para contratação de software. " * 200
        q = avaliar_qualidade(texto)
        assert q.score >= 0.6
        assert q.faixa in ("boa", "regular")

    def test_texto_fragmentado_score_menor(self):
        texto = "\n".join(["x"] * 100)  # 100 linhas de 1 char
        q = avaliar_qualidade(texto)
        assert q.score < 0.5


# ── Preprocessing ────────────────────────────────────────────

class TestPreprocessamento:
    def test_vazio(self):
        assert preprocessar("") == ""

    def test_une_linhas_quebradas(self):
        texto = "contrata-\nção de empresa"
        resultado = preprocessar(texto)
        assert "contratação" in resultado

    def test_remove_numeracao_pagina(self):
        texto = "Texto normal\nPágina 1 de 10\nMais texto"
        resultado = preprocessar(texto)
        assert "Página 1 de 10" not in resultado

    def test_normaliza_espacos(self):
        texto = "texto   com    muitos     espaços"
        resultado = preprocessar(texto)
        assert "  " not in resultado


# ── Regex Extraction ─────────────────────────────────────────

class TestExtracao:
    TEXTO_EDITAL = """
    4.1 Habilitação jurídica: contrato social ou ato constitutivo.
    4.2 Qualificação técnica: atestado de capacidade técnica comprovando
    experiência em implantação de sistemas similares.
    4.3 Regularidade fiscal: certidão negativa de débitos federais,
    certidão negativa trabalhista, certidão de regularidade do FGTS.
    4.4 O sistema deverá possuir módulo de contabilidade integrado.
    5.1 Multa de 10% sobre o valor do contrato em caso de inexecução.
    5.2 Garantia contratual de 5% do valor global.
    5.3 Prazo de implantação: 30 (trinta) dias corridos.
    5.4 Prazo de vigência: 12 (doze) meses.
    6.1 Balanço patrimonial do último exercício social.
    6.2 Comprovante de inscrição no CNPJ.
    """

    def test_extrai_documentos_com_taxonomia(self):
        docs = extrair_documentos(self.TEXTO_EDITAL)
        assert len(docs) > 0
        codigos = {d.codigo for d in docs}
        assert "DOC_ATESTADO_CAPACIDADE" in codigos or "DOC_CONTRATO_SOCIAL" in codigos

    def test_extrai_requisitos(self):
        reqs = extrair_requisitos(self.TEXTO_EDITAL)
        assert len(reqs) > 0
        assert all(r.codigo == "REQ_TECNICO" for r in reqs)

    def test_extrai_riscos_com_taxonomia(self):
        riscos = extrair_riscos(self.TEXTO_EDITAL)
        assert len(riscos) > 0
        codigos = {r.codigo for r in riscos}
        assert "RISCO_MULTA" in codigos or "RISCO_GARANTIA_CONTRATUAL" in codigos

    def test_extrai_qualificacao(self):
        quals = extrair_qualificacao(self.TEXTO_EDITAL)
        assert len(quals) > 0

    def test_texto_vazio_retorna_vazio(self):
        assert extrair_documentos("") == []
        assert extrair_requisitos("") == []
        assert extrair_riscos("") == []


# ── Prazo Extraction ─────────────────────────────────────────

class TestPrazos:
    def test_extrai_prazo_com_tipo(self):
        texto = "Prazo de implantação: 30 (trinta) dias corridos."
        prazos = extrair_prazos(texto)
        assert len(prazos) >= 1
        p = prazos[0]
        assert p.valor == 30
        assert p.unidade == "dia"
        assert p.tipo == "implantacao"

    def test_extrai_prazo_vigencia(self):
        texto = "Prazo de vigência: 12 (doze) meses."
        prazos = extrair_prazos(texto)
        assert len(prazos) >= 1
        assert prazos[0].tipo == "vigencia"

    def test_texto_sem_prazo(self):
        assert extrair_prazos("sem prazo aqui") == []

    def test_deduplicacao(self):
        texto = "Prazo de entrega: 30 dias. O prazo de entrega será de 30 dias."
        prazos = extrair_prazos(texto)
        valores = [p.valor for p in prazos]
        assert valores.count(30) <= 1


# ── Risk Scoring ─────────────────────────────────────────────

class TestRiskScoring:
    def test_sem_riscos_score_baixo(self):
        result = calcular_score_risco(riscos=[], prazos=[], total_documentos=3, total_requisitos=2)
        assert result.score == 0
        assert result.nivel == "baixo"

    def test_com_riscos_score_alto(self):
        riscos = [
            AchadoEstruturado(codigo="RISCO_MULTA", label="Multa", trecho="multa de 10%"),
            AchadoEstruturado(codigo="RISCO_GARANTIA_CONTRATUAL", label="Garantia", trecho="garantia de 5%"),
            AchadoEstruturado(codigo="RISCO_IMPEDIMENTO_CONTRATAR", label="Impedimento", trecho="impedimento de licitar"),
        ]
        result = calcular_score_risco(riscos=riscos, prazos=[], total_documentos=12, total_requisitos=10)
        assert result.score >= 50
        assert result.nivel in ("medio", "alto")
        assert len(result.fatores) >= 3

    def test_prazo_curto_penaliza(self):
        from edital_analysis.types import PrazoClassificado
        prazos = [PrazoClassificado(valor=15, unidade="dia", tipo="implantacao", contexto="15 dias", confianca=0.8)]
        result = calcular_score_risco(riscos=[], prazos=prazos)
        assert result.score > 0
        assert any("prazo curto" in f for f in result.fatores)


# ── Confidence ───────────────────────────────────────────────

class TestConfidence:
    def test_tudo_bom_score_alto(self):
        qualidade = QualidadeExtracao(score=0.9, faixa="boa", motivos=[])
        arquivo = ArquivoRanqueado(url="http://x", titulo="Edital", score=70, motivos=[])
        docs = [AchadoEstruturado(codigo="DOC_CNPJ", label="CNPJ", trecho="cnpj")]
        reqs = [AchadoEstruturado(codigo="REQ", label="Req", trecho="req")]
        riscos = [AchadoEstruturado(codigo="RISCO", label="Risco", trecho="risco")]
        qualif = [AchadoEstruturado(codigo="QUAL", label="Qual", trecho="qual")]
        from edital_analysis.types import PrazoClassificado
        prazos = [PrazoClassificado(valor=30, unidade="dia", tipo="execucao", contexto="30 dias")]
        texto = "edital licitação contrato pregão " * 500

        result = calcular_score_confianca(qualidade, arquivo, docs, reqs, riscos, qualif, prazos, texto)
        assert result.score >= 60
        assert result.faixa in ("alta", "media")

    def test_sem_nada_score_baixo(self):
        qualidade = QualidadeExtracao(score=0.1, faixa="ruim", motivos=[])
        result = calcular_score_confianca(qualidade, None, [], [], [], [], [], "pouco texto")
        assert result.score < 40
        assert result.faixa == "baixa"
