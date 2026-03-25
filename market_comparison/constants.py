"""Constantes centralizadas do comparativo de mercado v2."""

from __future__ import annotations

import os

VERSAO_ALGORITMO = "v2"
METODO_AGRUPAMENTO = "ncm_lexical"
METODO_OUTLIER = "iqr"
DESCONTO_MAXIMO = 80.0
RAZAO_MAXIMA_ESCALA = 50
LIMITE_ITENS_POR_PLATAFORMA = 5000

# ── Plataformas concorrentes ─────────────────────────────────

CONCORRENTES: dict[int, str] = {
    121: "SH3 Informática",
    12: "BLL Compras (BNC)",
    13: "Licitar Digital",
    18: "Licitanet",
}

# Permite adicionar via env (ex: PLATAFORMAS_COMPARATIVO=121,12,13,18,999)
_env_plat = os.environ.get("PLATAFORMAS_COMPARATIVO", "")
if _env_plat:
    IDS_CONCORRENTES = [int(x) for x in _env_plat.split(",") if x.strip()]
else:
    IDS_CONCORRENTES = list(CONCORRENTES.keys())

# ── Stopwords para agrupamento ───────────────────────────────

STOPWORDS: frozenset[str] = frozenset({
    "de", "do", "da", "dos", "das", "para", "com", "por", "que", "uma",
    "um", "seu", "sua", "nos", "nas", "pelo", "pela", "aos", "entre",
    "sobre", "apos", "ate", "sem", "como", "mais",
    "contratacao", "empresa", "especializada", "prestacao", "servicos",
    "servico", "aquisicao", "fornecimento", "objeto", "registro",
    "preco", "precos", "lote", "item", "itens", "tipo", "modalidade",
    "processo", "licitatorio", "pregao", "eletronico", "presencial",
})

# ── Score de comparabilidade — pesos (total = 100) ──────────

PESO_NCM = 20
PESO_UNIDADE = 20
PESO_AMOSTRA = 15
PESO_DISPERSAO = 15
PESO_HOMOLOGADOS = 15
PESO_ESCALA = 15

FAIXA_ALTA = 70
FAIXA_MEDIA = 40

# ── Grupos de unidades compatíveis ───────────────────────────

GRUPOS_UNIDADE: list[frozenset[str]] = [
    frozenset({"un", "und", "unid", "unidade", "peca", "pc"}),
    frozenset({"kg", "quilo", "quilograma"}),
    frozenset({"l", "lt", "litro"}),
    frozenset({"m", "metro", "ml", "metro linear"}),
    frozenset({"m2", "m²", "metro quadrado"}),
    frozenset({"cx", "caixa"}),
    frozenset({"pct", "pacote"}),
    frozenset({"fr", "frasco"}),
    frozenset({"tb", "tubo"}),
    frozenset({"rl", "rolo"}),
    frozenset({"mes", "mensal", "meses"}),
    frozenset({"hora", "h", "hr"}),
]

# ── Query: campos selecionados ───────────────────────────────

SELECT_ITENS = (
    "descricao, ncm_nbs_codigo, unidade_medida, plataforma_nome, "
    "plataforma_id, valor_unitario_estimado, "
    "resultados_item(valor_unitario_homologado, percentual_desconto)"
)
