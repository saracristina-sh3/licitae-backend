"""Montagem de rows para persistência no banco."""

from __future__ import annotations

from datetime import datetime, timezone

from pncp_collector.constants import VERSAO_COLETOR
from pncp_collector.types import ItemRow, Metadata, ResultadoRow


def montar_item_row(
    cnpj: str,
    ano: int,
    sequencial: int,
    licitacao_hash: str | None,
    item: dict,
    metadata: Metadata,
) -> ItemRow:
    """Constrói o dicionário de inserção de um item."""
    return ItemRow(
        licitacao_hash=licitacao_hash,
        cnpj_orgao=cnpj,
        ano_compra=ano,
        sequencial_compra=sequencial,
        numero_item=item.get("numeroItem"),
        descricao=item.get("descricao"),
        ncm_nbs_codigo=item.get("ncmNbsCodigo"),
        quantidade=item.get("quantidade"),
        unidade_medida=item.get("unidadeMedida"),
        valor_unitario_estimado=item.get("valorUnitarioEstimado"),
        valor_total_estimado=item.get("valorTotal"),
        tem_resultado=item.get("temResultado", False),
        plataforma_id=metadata.get("plataforma_id"),
        plataforma_nome=metadata.get("plataforma_nome"),
        uf=metadata.get("uf"),
        municipio=metadata.get("municipio"),
        codigo_ibge=metadata.get("codigo_ibge"),
        modalidade_id=metadata.get("modalidade_id"),
        material_ou_servico=item.get("materialOuServico"),
        tipo_beneficio_id=item.get("tipoBeneficio"),
        criterio_julgamento_id=item.get("criterioJulgamentoId"),
        coletado_em=datetime.now(timezone.utc).isoformat(),
        versao_coletor=VERSAO_COLETOR,
    )


def montar_resultado_row(item_id: str, res: dict) -> ResultadoRow:
    """Constrói o dicionário de inserção de um resultado."""
    return ResultadoRow(
        item_id=item_id,
        sequencial_resultado=res.get("sequencialResultado"),
        valor_unitario_homologado=res.get("valorUnitarioHomologado"),
        valor_total_homologado=res.get("valorTotalHomologado"),
        quantidade_homologada=res.get("quantidadeHomologada"),
        percentual_desconto=res.get("percentualDesconto"),
        cnpj_fornecedor=res.get("niFornecedor"),
        nome_fornecedor=res.get("nomeRazaoSocialFornecedor"),
        porte_fornecedor=res.get("porteFornecedorNome"),
        data_resultado=res.get("dataResultado"),
        coletado_em=datetime.now(timezone.utc).isoformat(),
        versao_coletor=VERSAO_COLETOR,
    )
