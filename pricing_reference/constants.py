"""Constantes centralizadas do motor de preços de referência."""

from __future__ import annotations

# ── Versão e metadados ───────────────────────────────────────

VERSAO_ALGORITMO = "v2"
METODO_SIMILARIDADE = "text_search"
METODO_OUTLIER = "iqr+trimmed_mean"

# ── Janela temporal e amostra ────────────────────────────────

JANELA_MESES = 12
AMOSTRA_MINIMA = 3
TRIM_PERCENT = 0.1  # 10% de cada extremo para trimmed mean
DESCONTO_MAXIMO = 80.0

# ── Score de confiabilidade — pesos (total = 100) ────────────

PESO_AMOSTRA = 25           # >= 10 amostras = pontuação máxima
PESO_RECENCIA = 20          # dados dos últimos 3 meses = máxima
PESO_HOMOLOGADOS = 20       # > 80% homologados = máxima
PESO_BAIXA_DISPERSAO = 20   # CV < 25% = máxima
PESO_SIMILARIDADE = 15      # score médio de similaridade > 70 = máxima

# Faixas de confiabilidade (score >= X)
FAIXA_ALTA = 70
FAIXA_MEDIA = 40

# ── Score de similaridade — pesos (total = 100) ─────────────

SIM_MESMA_MODALIDADE = 20
SIM_MESMA_UF = 15
SIM_NCM_IGUAL = 25
SIM_UNIDADE_IGUAL = 10
SIM_TERMOS_COMUNS = 20     # proporcional ao % de termos em comum
SIM_RECENTE = 10           # publicado nos últimos 6 meses

# ── Stopwords para extração de termos ────────────────────────

STOPWORDS: frozenset[str] = frozenset({
    # Artigos e preposições
    "de", "do", "da", "dos", "das", "para", "com", "por", "que", "uma",
    "um", "seu", "sua", "nos", "nas", "pelo", "pela", "aos", "entre",
    "sobre", "apos", "ate", "sem", "como", "mais", "este", "esta",
    "esse", "essa", "ser", "ter", "seu", "seus", "suas",
    # Termos genéricos de licitação
    "contratacao", "empresa", "especializada", "prestacao", "servicos",
    "servico", "aquisicao", "fornecimento", "objeto", "registro",
    "preco", "precos", "lote", "item", "itens", "tipo", "modalidade",
    "processo", "licitatorio", "pregao", "eletronico", "presencial",
})

# ── Query: campos selecionados para itens ────────────────────

SELECT_ITENS = (
    "id, descricao, ncm_nbs_codigo, quantidade, unidade_medida, "
    "valor_unitario_estimado, valor_total_estimado, "
    "plataforma_nome, uf, municipio, modalidade_id, created_at, "
    "resultados_item(valor_unitario_homologado, valor_total_homologado, "
    "nome_fornecedor, porte_fornecedor, percentual_desconto)"
)
