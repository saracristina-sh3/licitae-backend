"""Constantes do motor de preços de referência v3."""

from __future__ import annotations

# Reutiliza constantes compartilhadas
from comparison_core.constants import STOPWORDS  # noqa: F401

# ── Versão e metadados ───────────────────────────────────────

VERSAO_ALGORITMO = "v3"
METODO_SIMILARIDADE = "text_search"
METODO_OUTLIER = "iqr+trimmed_mean"

# ── Janela temporal e amostra ────────────────────────────────

JANELA_MESES = 12
AMOSTRA_MINIMA = 3
TRIM_PERCENT = 0.1
DESCONTO_MAXIMO = 80.0

# ── Score de confiabilidade — pesos (total = 100) ────────────

PESO_AMOSTRA = 25
PESO_RECENCIA = 20
PESO_HOMOLOGADOS = 20
PESO_BAIXA_DISPERSAO = 20
PESO_SIMILARIDADE = 15

FAIXA_ALTA = 70
FAIXA_MEDIA = 40

# ── Score de similaridade — pesos (total = 100) ─────────────

SIM_MESMA_MODALIDADE = 20
SIM_MESMA_UF = 15
SIM_NCM_IGUAL = 25
SIM_UNIDADE_IGUAL = 10
SIM_TERMOS_COMUNS = 20
SIM_RECENTE = 10

# ── Query: campos selecionados para itens ────────────────────

SELECT_ITENS = (
    "id, descricao, ncm_nbs_codigo, quantidade, unidade_medida, "
    "valor_unitario_estimado, valor_total_estimado, "
    "plataforma_nome, uf, municipio, modalidade_id, created_at, "
    "resultados_item(valor_unitario_homologado, valor_total_homologado, "
    "nome_fornecedor, porte_fornecedor, percentual_desconto)"
)
