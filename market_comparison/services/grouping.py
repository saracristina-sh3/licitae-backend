"""
Serviço de agrupamento — converte itens brutos em grupos comparáveis.
"""

from __future__ import annotations

import logging
import statistics

from market_comparison.constants import DESCONTO_MAXIMO
from market_comparison.services.price_selection import selecionar_preco
from market_comparison.services.unit_validation import validar_consistencia
from market_comparison.strategies.ncm_lexical import NcmLexicalStrategy
from market_comparison.types import ComparableGroup, ObservedItem

log = logging.getLogger(__name__)


def converter_item_raw(row: dict) -> ObservedItem | None:
    """Converte um registro bruto do banco em ObservedItem."""
    plataforma = row.get("plataforma_nome") or ""
    plat_id = row.get("plataforma_id") or 0
    if not plataforma:
        return None

    resultados = row.get("resultados_item") or []
    if isinstance(resultados, dict):
        resultados = [resultados]

    estimado = float(row.get("valor_unitario_estimado", 0))
    valor, fonte, desconto = selecionar_preco(resultados, estimado)

    if valor <= 0:
        return None

    return ObservedItem(
        descricao=(row.get("descricao") or "")[:80],
        ncm=row.get("ncm_nbs_codigo"),
        unidade=row.get("unidade_medida") or "",
        plataforma_nome=plataforma,
        plataforma_id=plat_id,
        valor=valor,
        fonte_preco=fonte,
        desconto=desconto,
    )


def agrupar_itens(itens_raw: list[dict]) -> dict[str, list[ObservedItem]]:
    """
    Agrupa itens brutos por chave (NCM + unidade ou descrição + unidade).
    Retorna dict[chave → lista de ObservedItem].
    """
    strategy = NcmLexicalStrategy()
    grupos: dict[str, list[ObservedItem]] = {}

    for row in itens_raw:
        item = converter_item_raw(row)
        if not item:
            continue

        chave = strategy.gerar_chave(item)
        if not chave:
            continue

        grupos.setdefault(chave, []).append(item)

    return grupos


def montar_grupo_comparavel(chave: str, itens: list[ObservedItem]) -> ComparableGroup | None:
    """
    Converte uma lista de itens agrupados em um ComparableGroup.
    Retorna None se o grupo não tem 2+ plataformas.
    """
    # Agrupar por plataforma
    por_plataforma: dict[str, list[ObservedItem]] = {}
    for item in itens:
        por_plataforma.setdefault(item.plataforma_nome, []).append(item)

    if len(por_plataforma) < 2:
        return None

    # Validar unidade
    unidade_predominante, taxa_consistencia = validar_consistencia(itens)

    # Fonte predominante
    total_hom = sum(1 for i in itens if i.fonte_preco == "homologado")
    total_est = sum(1 for i in itens if i.fonte_preco == "estimado")
    if total_hom > total_est:
        fonte = "homologado"
    elif total_est > total_hom:
        fonte = "estimado"
    else:
        fonte = "misto"

    # NCM e descrição do primeiro item
    primeiro = itens[0]

    return ComparableGroup(
        chave=chave,
        descricao=primeiro.descricao,
        ncm=primeiro.ncm,
        unidade_predominante=unidade_predominante,
        taxa_consistencia_unidade=taxa_consistencia,
        fonte_predominante=fonte,
        total_observacoes=len(itens),
    )
