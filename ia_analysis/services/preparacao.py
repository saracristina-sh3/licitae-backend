"""Prepara contexto consolidado para enviar ao Claude."""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


def preparar_contexto(client, licitacao_id: str) -> dict:
    """
    Consolida todos os dados de uma licitação em um dict pronto para o prompt.

    Retorna dict com chaves: licitacao, edital, precos, itens, comparativo, org.
    """
    # Licitação
    lic = (
        client.table("licitacoes")
        .select(
            "id, objeto, municipio_nome, uf, modalidade, valor_estimado, "
            "relevancia, data_publicacao, data_abertura_proposta, "
            "data_encerramento_proposta, situacao, orgao, exclusivo_me_epp, "
            "palavras_chave"
        )
        .eq("id", licitacao_id)
        .limit(1)
        .execute()
    )
    if not lic.data:
        raise ValueError(f"Licitação {licitacao_id} não encontrada")

    licitacao = lic.data[0]

    # Edital
    edital_data = None
    edital = (
        client.table("analise_editais")
        .select(
            "documentos_estruturados, requisitos_estruturados, "
            "riscos_estruturados, qualificacao_estruturada, "
            "prazos_classificados, score_risco, score_confianca, "
            "texto_extraido"
        )
        .eq("licitacao_id", licitacao_id)
        .limit(1)
        .execute()
    )
    if edital.data:
        edital_data = edital.data[0]
        # Trunca texto extraído para não estourar contexto
        texto = edital_data.get("texto_extraido") or ""
        if len(texto) > 8000:
            edital_data["texto_extraido"] = texto[:8000] + "\n[... truncado]"

    # Preços de referência
    precos_data = None
    precos = (
        client.table("preco_referencia_licitacao")
        .select(
            "total_similares, valor_minimo, valor_maximo, valor_media, "
            "valor_mediana, coeficiente_variacao, amostra_suficiente, "
            "score_confiabilidade, faixa_confiabilidade, "
            "total_homologados, total_estimados, fonte_predominante, "
            "total_itens_similares, item_media_unitario, item_desconto_medio"
        )
        .eq("licitacao_id", licitacao_id)
        .limit(1)
        .execute()
    )
    if precos.data:
        precos_data = precos.data[0]

    # Itens similares (da tabela de preços de referência, que já foi calculada)
    itens_data = []
    if precos_data:
        ref_result = (
            client.table("preco_referencia_licitacao")
            .select("id")
            .eq("licitacao_id", licitacao_id)
            .limit(1)
            .execute()
        )
        if ref_result.data:
            ref_id = ref_result.data[0]["id"]
            itens_ref = (
                client.table("preco_referencia_itens")
                .select(
                    "descricao, unidade_medida, valor_unitario, "
                    "plataforma_nome, municipio, uf, nome_fornecedor, "
                    "percentual_desconto, fonte_preco"
                )
                .eq("preco_referencia_id", ref_id)
                .order("score_similaridade", desc=True)
                .limit(30)
                .execute()
            )
            itens_data = itens_ref.data or []

    # Comparativo da UF
    comparativo_data = None
    uf = licitacao.get("uf")
    if uf:
        comp = (
            client.table("comparativo_plataformas")
            .select("plataforma_nome, total_itens, vitorias, desconto_medio")
            .eq("uf", uf)
            .order("calculado_em", desc=True)
            .limit(10)
            .execute()
        )
        if comp.data:
            comparativo_data = comp.data

    # Config da organização
    org_data = None
    config = (
        client.table("org_config")
        .select("ufs, palavras_chave, termos_exclusao")
        .limit(1)
        .execute()
    )
    if config.data:
        org_data = config.data[0]

    termos_exclusao = org_data.get("termos_exclusao", []) if org_data else []

    return {
        "licitacao": licitacao,
        "edital": edital_data,
        "precos": precos_data,
        "itens": itens_data,
        "comparativo": comparativo_data,
        "org": {
            **(org_data or {}),
            "termos_exclusao": termos_exclusao,
        },
    }


def contexto_para_texto(contexto: dict) -> dict[str, str]:
    """Converte contexto dict em strings formatadas para os prompts."""
    def _json(obj) -> str:
        if obj is None:
            return "Não disponível"
        return json.dumps(obj, ensure_ascii=False, default=str, indent=2)

    return {
        "contexto_org": _json(contexto.get("org")),
        "dados_licitacao": _json(contexto.get("licitacao")),
        "dados_edital": _json(contexto.get("edital")),
        "dados_precos": _json(contexto.get("precos")),
        "dados_itens": _json(contexto.get("itens")),
        "dados_comparativo": _json(contexto.get("comparativo")),
    }
