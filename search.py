"""
Motor de busca: cruza dados do PNCP com municípios-alvo e filtra por palavras-chave.
Aceita configuração dinâmica (user_config) ou defaults do .env.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
from config import Config
from pncp_client import PNCPClient
from municipios import carregar_municipios
from utils import normalizar, match_palavras_chave, classificar_relevancia, detectar_me_epp

MODALIDADE_NOMES = {
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência Eletrônica",
    5: "Concorrência Presencial",
    6: "Pregão Eletrônico",
    7: "Pregão Presencial",
    8: "Dispensa de Licitação",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
}

JANELA_DIAS = 1


def _extrair_url_pncp(contratacao: dict) -> str:
    cnpj = contratacao.get("orgaoEntidade", {}).get("cnpj", "")
    ano = contratacao.get("anoCompra", "")
    seq = contratacao.get("sequencialCompra", "")
    if cnpj and ano and seq:
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
    return ""


def _gerar_janelas(dt_inicio: str, dt_fim: str, dias: int = JANELA_DIAS) -> list[tuple[str, str]]:
    inicio = datetime.strptime(dt_inicio, "%Y%m%d")
    fim = datetime.strptime(dt_fim, "%Y%m%d")
    janelas = []
    atual = inicio
    while atual <= fim:
        janela_fim = min(atual + timedelta(days=dias - 1), fim)
        janelas.append((atual.strftime("%Y%m%d"), janela_fim.strftime("%Y%m%d")))
        atual = janela_fim + timedelta(days=1)
    return janelas


def buscar_licitacoes(
    dias_retroativos: int | None = None,
    data_inicial: str | None = None,
    data_final: str | None = None,
    busca_config: dict | None = None,
) -> list[dict]:
    """
    Busca licitações nos municípios-alvo.

    busca_config: dict opcional com chaves:
        ufs, palavras_chave, modalidades, termos_alta, termos_media,
        termos_me_epp, fpm_maximo (populacao)
    Se None, usa defaults do Config (.env).
    """
    client = PNCPClient()
    cfg = busca_config or {}

    ufs = cfg.get("ufs") or Config.UFS
    palavras_chave = cfg.get("palavras_chave") or Config.PALAVRAS_CHAVE
    modalidades = cfg.get("modalidades") or Config.MODALIDADES
    pop_maxima = cfg.get("fpm_maximo") or Config.POPULACAO_MAXIMA
    from utils import TERMOS_ALTA, TERMOS_MEDIA, TERMOS_ME_EPP
    termos_alta = cfg.get("termos_alta") or TERMOS_ALTA
    termos_media = cfg.get("termos_media") or TERMOS_MEDIA
    termos_me_epp = cfg.get("termos_me_epp") or TERMOS_ME_EPP

    if data_inicial and data_final:
        dt_inicio = data_inicial
        dt_fim = data_final
    else:
        dias = dias_retroativos or Config.DIAS_RETROATIVOS
        hoje = datetime.now()
        inicio = hoje - timedelta(days=dias)
        dt_inicio = inicio.strftime("%Y%m%d")
        dt_fim = hoje.strftime("%Y%m%d")

    log.info("Período de busca: %s a %s", dt_inicio, dt_fim)

    municipios = carregar_municipios(ufs, pop_maxima)
    mapa_municipios = {m["codigo_ibge"]: m for m in municipios}
    log.info("Municípios-alvo: %d (%s)", len(municipios), ", ".join(ufs))
    log.info("Palavras-chave: %d termos", len(palavras_chave))

    janelas = _gerar_janelas(dt_inicio, dt_fim)
    log.info("Dividido em %d janelas de até %d dias", len(janelas), JANELA_DIAS)

    resultados = []

    for uf in ufs:
        for modalidade in modalidades:
            mod_nome = MODALIDADE_NOMES.get(modalidade, str(modalidade))
            total_contratacoes = 0
            encontrados = 0

            log.info("  %s - %s: buscando...", uf, mod_nome)

            for j_idx, (j_inicio, j_fim) in enumerate(janelas, 1):
                try:
                    contratacoes = client.buscar_todas_paginas(
                        data_inicial=j_inicio,
                        data_final=j_fim,
                        modalidade=modalidade,
                        uf=uf,
                    )
                except Exception:
                    log.warning("  %s - %s: erro na janela %s-%s", uf, mod_nome, j_inicio, j_fim)
                    continue

                total_contratacoes += len(contratacoes)

                for c in contratacoes:
                    enc = c.get("dataEncerramentoProposta", "")
                    if enc:
                        try:
                            dt_enc = datetime.fromisoformat(enc.replace("Z", "+00:00"))
                            if dt_enc.replace(tzinfo=None) < datetime.now():
                                continue
                        except (ValueError, TypeError):
                            pass

                    objeto = c.get("objetoCompra", "") or ""
                    orgao = c.get("orgaoEntidade", {}) or {}
                    unidade = c.get("unidadeOrgao", {}) or {}
                    codigo_mun = str(unidade.get("codigoIbge", "") or orgao.get("codigoMunicipioIbge", "") or "")

                    mun_info = mapa_municipios.get(codigo_mun)
                    if not mun_info:
                        continue

                    matches = match_palavras_chave(objeto, palavras_chave)
                    if not matches:
                        continue

                    relevancia = classificar_relevancia(matches, objeto, termos_alta, termos_media)
                    info_compl = c.get("informacaoComplementar", "") or ""
                    texto_completo = f"{objeto} {info_compl}"
                    me_epp = detectar_me_epp(texto_completo, termos_me_epp)
                    encontrados += 1

                    resultados.append({
                        "municipio": mun_info["nome"],
                        "uf": mun_info["uf"],
                        "populacao": mun_info["populacao"],
                        "fpm": mun_info["fpm"],
                        "codigo_ibge": codigo_mun,
                        "orgao": orgao.get("razaoSocial", ""),
                        "cnpj_orgao": orgao.get("cnpj", ""),
                        "objeto": objeto,
                        "exclusivo_me_epp": me_epp,
                        "modalidade": mod_nome,
                        "valor_estimado": c.get("valorTotalEstimado", 0) or 0,
                        "valor_homologado": c.get("valorTotalHomologado", 0) or 0,
                        "situacao": c.get("situacaoCompraNome", ""),
                        "data_publicacao": c.get("dataPublicacaoPncp", ""),
                        "data_abertura_proposta": c.get("dataAberturaProposta", ""),
                        "data_encerramento_proposta": c.get("dataEncerramentoProposta", ""),
                        "url_pncp": _extrair_url_pncp(c),
                        "palavras_chave_encontradas": ", ".join(matches),
                        "relevancia": relevancia,
                        "fonte": "PNCP",
                        "ano_compra": str(c.get("anoCompra", "")),
                        "seq_compra": str(c.get("sequencialCompra", "")),
                    })

            log.info("  %s - %s: %d relevantes de %d", uf, mod_nome, encontrados, total_contratacoes)

    ordem = {"ALTA": 0, "MEDIA": 1, "BAIXA": 2}
    resultados.sort(key=lambda r: (ordem.get(r["relevancia"], 9), r["data_publicacao"]))

    return resultados
