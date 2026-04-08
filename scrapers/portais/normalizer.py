"""
Normaliza resultados brutos de scrapers de portais institucionais
para o formato padrão da tabela licitacoes.
"""

from __future__ import annotations


def normalizar_resultado_portal(
    raw: dict,
    municipio: dict,
    url_fonte: str,
) -> dict:
    """
    Converte resultado bruto do scraper → dict padrão da tabela licitacoes.

    Args:
        raw: Dict com campos brutos do scraper (objeto, modalidade, etc.).
        municipio: Dict do município (codigo_ibge, nome, uf, populacao, fpm).
        url_fonte: URL da página onde a licitação foi encontrada.

    Returns:
        Dict normalizado no mesmo formato de querido_diario.py e tcerj.py.
    """
    data_pub = raw.get("data_publicacao", "")

    return {
        "municipio": municipio["nome"],
        "uf": municipio["uf"],
        "populacao": municipio["populacao"],
        "fpm": municipio["fpm"],
        "codigo_ibge": municipio["codigo_ibge"],
        "orgao": raw.get("orgao", municipio["nome"]),
        "cnpj_orgao": raw.get("cnpj", ""),
        "objeto": raw.get("objeto", ""),
        "exclusivo_me_epp": raw.get("exclusivo_me_epp", False),
        "modalidade": raw.get("modalidade", ""),
        "valor_estimado": raw.get("valor_estimado", 0),
        "valor_homologado": 0,
        "situacao": raw.get("situacao", "Publicada"),
        "data_publicacao": data_pub,
        "data_abertura_proposta": raw.get("data_abertura", ""),
        "data_encerramento_proposta": raw.get("data_encerramento", ""),
        "url_pncp": "",
        "url_fonte": url_fonte,
        "palavras_chave_encontradas": "",
        "relevancia": "BAIXA",
        "fonte": "PORTAL_MUNICIPAL",
        "ano_compra": data_pub[:4] if len(data_pub) >= 4 else "",
        "seq_compra": raw.get("numero_processo", ""),
        "numero_processo": raw.get("numero_processo", ""),
    }
