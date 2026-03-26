"""
Serviço de agrupamento — converte itens brutos em grupos comparáveis.
Usa multi-chave para maximizar cruzamentos entre plataformas.
"""

from __future__ import annotations

import logging

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
    Agrupa itens brutos por chave usando multi-chave.

    Cada item pode entrar em até 3 grupos (NCM exato, NCM4, lexical).
    Depois, deduplicamos: se um grupo NCM exato contém os mesmos itens
    que um grupo lexical, o lexical é descartado.
    """
    strategy = NcmLexicalStrategy()
    grupos: dict[str, list[ObservedItem]] = {}

    # Fase 1: gerar todas as chaves e agrupar
    for row in itens_raw:
        item = converter_item_raw(row)
        if not item:
            continue

        chaves = strategy.gerar_chaves(item)
        if not chaves:
            continue

        for chave in chaves:
            grupos.setdefault(chave, []).append(item)

    # Fase 2: deduplicação — priorizar grupos de maior confiança
    # Se um item aparece num grupo "ncm:" E num grupo "desc:", e ambos
    # têm as mesmas plataformas, o grupo "desc:" é redundante.
    chaves_ncm = {k for k in grupos if k.startswith("ncm:")}
    chaves_ncm4 = {k for k in grupos if k.startswith("ncm4:")}
    chaves_desc = {k for k in grupos if k.startswith("desc:")}

    # Para cada grupo desc, verificar se existe grupo ncm/ncm4 com overlap significativo
    chaves_remover: set[str] = set()
    for chave_desc in chaves_desc:
        itens_desc = grupos[chave_desc]
        plats_desc = {i.plataforma_nome for i in itens_desc}

        for chave_alta in chaves_ncm | chaves_ncm4:
            itens_alta = grupos[chave_alta]
            plats_alta = {i.plataforma_nome for i in itens_alta}

            # Se ≥50% das plataformas do grupo desc estão no grupo ncm → redundante
            overlap = len(plats_desc & plats_alta)
            if overlap >= len(plats_desc) * 0.5 and len(plats_alta) >= 2:
                chaves_remover.add(chave_desc)
                break

    # Também deduplicar ncm4 quando ncm exato existe com overlap
    for chave_ncm4 in chaves_ncm4:
        itens_ncm4 = grupos[chave_ncm4]
        plats_ncm4 = {i.plataforma_nome for i in itens_ncm4}

        for chave_ncm in chaves_ncm:
            itens_ncm = grupos[chave_ncm]
            plats_ncm = {i.plataforma_nome for i in itens_ncm}

            overlap = len(plats_ncm4 & plats_ncm)
            if overlap >= len(plats_ncm4) * 0.5 and len(plats_ncm) >= 2:
                chaves_remover.add(chave_ncm4)
                break

    for chave in chaves_remover:
        del grupos[chave]

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
