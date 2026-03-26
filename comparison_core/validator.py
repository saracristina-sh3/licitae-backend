"""
Validação de comparabilidade entre itens — Golden Rule.
Define quando dois itens NÃO devem ser comparados.
"""

from __future__ import annotations

from comparison_core.constants import (
    ESCALA_MAXIMA,
    ESCALA_MAXIMA_PADRAO,
    GRUPOS_UNIDADE,
    PARES_INCOMPATIVEIS,
)
from comparison_core.normalizer import normalizar_descricao
from comparison_core.types import ResultadoValidacao


def normalizar_unidade(unidade: str) -> str:
    """Normaliza unidade de medida para comparação."""
    return normalizar_descricao(unidade).strip()


def grupo_da_unidade(unidade: str) -> frozenset[str] | None:
    """Retorna o grupo compatível de uma unidade, ou None se desconhecida."""
    u = normalizar_unidade(unidade)
    for grupo in GRUPOS_UNIDADE:
        if u in grupo:
            return grupo
    return None


def unidade_canonica(unidade: str) -> str:
    """Retorna a unidade canônica (primeira do grupo ordenado) ou a própria."""
    grupo = grupo_da_unidade(unidade)
    if grupo:
        return next(iter(sorted(grupo)))
    return normalizar_unidade(unidade)


def validar_unidade(u1: str, u2: str) -> bool:
    """Verifica se duas unidades são compatíveis."""
    if not u1 or not u2:
        return True  # Se não informado, não bloqueia

    n1 = normalizar_unidade(u1)
    n2 = normalizar_unidade(u2)

    if n1 == n2:
        return True

    g1 = grupo_da_unidade(n1)
    g2 = grupo_da_unidade(n2)

    if g1 is not None and g2 is not None:
        return g1 == g2

    return False


def validar_categoria(cat_a: str, cat_b: str) -> bool:
    """Verifica se duas categorias são comparáveis (Golden Rule)."""
    if cat_a == cat_b:
        return True
    par = frozenset({cat_a, cat_b})
    return par not in PARES_INCOMPATIVEIS


def validar_escala(valor_a: float, valor_b: float, categoria: str = "produto") -> bool:
    """
    Verifica se a escala de preços é comparável.
    Limite varia por categoria (licenças são mais estritas).
    """
    if valor_a <= 0 or valor_b <= 0:
        return False

    ratio = max(valor_a, valor_b) / min(valor_a, valor_b)
    limite = ESCALA_MAXIMA.get(categoria, ESCALA_MAXIMA_PADRAO)
    return ratio <= limite


def validar_fonte(fonte_a: str, fonte_b: str) -> bool:
    """Homologado nunca se mistura com estimado."""
    return fonte_a == fonte_b


def is_comparable(item_a: dict, item_b: dict) -> ResultadoValidacao:
    """
    Validação completa de comparabilidade entre dois itens.

    Verifica (nesta ordem, fail-fast):
    1. Fonte (homologado vs estimado)
    2. Categoria (produto vs serviço vs licença vs consumível)
    3. Unidade de medida
    4. Escala de preço

    Retorna ResultadoValidacao com motivo de rejeição se não comparável.
    """
    # 1. Fonte
    if not validar_fonte(
        item_a.get("fonte_preco", ""),
        item_b.get("fonte_preco", ""),
    ):
        return ResultadoValidacao(
            comparavel=False,
            motivo_rejeicao="fontes_diferentes",
            score_ajuste=0.0,
        )

    # 2. Categoria
    cat_a = item_a.get("categoria", "produto")
    cat_b = item_b.get("categoria", "produto")
    if not validar_categoria(cat_a, cat_b):
        return ResultadoValidacao(
            comparavel=False,
            motivo_rejeicao="categorias_incompativeis",
            score_ajuste=0.0,
        )

    # 3. Unidade
    if not validar_unidade(
        item_a.get("unidade", ""),
        item_b.get("unidade", ""),
    ):
        return ResultadoValidacao(
            comparavel=False,
            motivo_rejeicao="unidades_incompativeis",
            score_ajuste=0.0,
        )

    # 4. Escala
    valor_a = float(item_a.get("valor", 0))
    valor_b = float(item_b.get("valor", 0))
    if valor_a > 0 and valor_b > 0:
        if not validar_escala(valor_a, valor_b, cat_a):
            return ResultadoValidacao(
                comparavel=False,
                motivo_rejeicao="escala_incompativel",
                score_ajuste=0.0,
            )

    # Tudo OK — penalidade menor se categorias são iguais mas poderiam divergir
    ajuste = 1.0
    if cat_a != cat_b:
        ajuste = 0.8  # Categorias compatíveis mas diferentes (ex: produto + produto)

    return ResultadoValidacao(
        comparavel=True,
        motivo_rejeicao=None,
        score_ajuste=ajuste,
    )
