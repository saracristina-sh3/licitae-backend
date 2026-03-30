"""Montagem do ResultadoLicitacao com campos enriquecidos."""

from __future__ import annotations

from prospection_engine.constants import MODALIDADE_NOMES
from prospection_engine.services.scoring import score_para_relevancia
from prospection_engine.types import BuscaConfig, MatchResult, ResultadoLicitacao

# Códigos PNCP de tipoBeneficio que indicam exclusividade ME/EPP
_BENEFICIO_ME_EPP = {1, 2, 3}  # Exclusiva, Subcontratação, Cota reservada


def _extrair_url_pncp(contratacao: dict) -> str:
    """Monta a URL pública do edital no PNCP."""
    cnpj = contratacao.get("orgaoEntidade", {}).get("cnpj", "")
    ano = contratacao.get("anoCompra", "")
    seq = contratacao.get("sequencialCompra", "")
    if cnpj and ano and seq:
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
    return ""


def montar_resultado(
    contratacao: dict,
    mun_info: dict,
    match: MatchResult,
    cfg: BuscaConfig,
    urgencia: str,
) -> ResultadoLicitacao:
    """Constrói o ResultadoLicitacao com todos os campos (legados + novos)."""
    objeto = contratacao.get("objetoCompra", "") or ""
    orgao = contratacao.get("orgaoEntidade", {}) or {}
    info_compl = contratacao.get("informacaoComplementar", "") or ""
    texto_completo = f"{objeto} {info_compl}"

    return ResultadoLicitacao(
        municipio=mun_info["nome"],
        uf=mun_info["uf"],
        populacao=mun_info["populacao"],
        fpm=mun_info["fpm"],
        codigo_ibge=str(mun_info.get("codigo_ibge", "")),
        orgao=orgao.get("razaoSocial", ""),
        cnpj_orgao=orgao.get("cnpj", ""),
        objeto=objeto,
        exclusivo_me_epp=contratacao.get("tipoBeneficioId", 0) in _BENEFICIO_ME_EPP,
        modalidade=MODALIDADE_NOMES.get(
            contratacao.get("modalidadeId", 0), str(contratacao.get("modalidadeId", ""))
        ),
        valor_estimado=contratacao.get("valorTotalEstimado", 0) or 0,
        valor_homologado=contratacao.get("valorTotalHomologado", 0) or 0,
        situacao=contratacao.get("situacaoCompraNome", ""),
        data_publicacao=contratacao.get("dataPublicacaoPncp", ""),
        data_abertura_proposta=contratacao.get("dataAberturaProposta", ""),
        data_encerramento_proposta=contratacao.get("dataEncerramentoProposta", ""),
        url_pncp=_extrair_url_pncp(contratacao),
        palavras_chave_encontradas=", ".join(match.termos_encontrados),
        relevancia=score_para_relevancia(match.score),
        fonte="PNCP",
        ano_compra=str(contratacao.get("anoCompra", "")),
        seq_compra=str(contratacao.get("sequencialCompra", "")),
        score=match.score,
        informacao_complementar=info_compl,
        urgencia=urgencia,
        # IDs de domínio PNCP
        modalidade_id=contratacao.get("modalidadeId"),
        modo_disputa_id=contratacao.get("modoDisputaId"),
        situacao_compra_id=contratacao.get("situacaoCompraId"),
    )
