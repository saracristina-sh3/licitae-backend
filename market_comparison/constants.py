"""Constantes do comparativo de mercado v4."""

from __future__ import annotations

import os

# Reutiliza constantes compartilhadas do comparison_core
from comparison_core.constants import GRUPOS_UNIDADE, SINONIMOS, STOPWORDS  # noqa: F401

VERSAO_ALGORITMO = "v4"
METODO_AGRUPAMENTO = "ncm_lexical_v2"
METODO_OUTLIER = "iqr"
DESCONTO_MAXIMO = 80.0
RAZAO_MAXIMA_ESCALA = 50
LIMITE_ITENS_POR_PLATAFORMA = 10000

# ── Plataformas concorrentes ─────────────────────────────────

CONCORRENTES: dict[int, str] = {
    121: "SH3 Informática",
    12: "BLL Compras (BNC)",
    13: "Licitar Digital",
    18: "Licitanet",
    3: "Compras.gov.br",
    5: "ECustomize",
    90: "BBNet",
}

_env_plat = os.environ.get("PLATAFORMAS_COMPARATIVO", "")
if _env_plat:
    IDS_CONCORRENTES = [int(x) for x in _env_plat.split(",") if x.strip()]
else:
    IDS_CONCORRENTES = list(CONCORRENTES.keys())

# ── Score de comparabilidade — pesos (total = 100) ──────────

PESO_NCM = 20
PESO_UNIDADE = 20
PESO_AMOSTRA = 15
PESO_DISPERSAO = 15
PESO_HOMOLOGADOS = 15
PESO_ESCALA = 15

FAIXA_ALTA = 70
FAIXA_MEDIA = 40

# ── Query: campos selecionados ───────────────────────────────

SELECT_ITENS = (
    "descricao, ncm_nbs_codigo, unidade_medida, plataforma_nome, "
    "plataforma_id, valor_unitario_estimado, "
    "resultados_item(valor_unitario_homologado, percentual_desconto)"
)
