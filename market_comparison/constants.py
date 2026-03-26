"""Constantes centralizadas do comparativo de mercado v3."""

from __future__ import annotations

import os

VERSAO_ALGORITMO = "v3"
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

# Permite adicionar via env (ex: PLATAFORMAS_COMPARATIVO=121,12,13,18,999)
_env_plat = os.environ.get("PLATAFORMAS_COMPARATIVO", "")
if _env_plat:
    IDS_CONCORRENTES = [int(x) for x in _env_plat.split(",") if x.strip()]
else:
    IDS_CONCORRENTES = list(CONCORRENTES.keys())

# ── Stopwords para agrupamento ───────────────────────────────

# Preposições/artigos + termos genéricos de licitação que não ajudam no agrupamento.
# NÃO remover "contratacao", "servicos", "prestacao" etc.
STOPWORDS: frozenset[str] = frozenset({
    # Preposições e artigos
    "de", "do", "da", "dos", "das", "para", "com", "por", "que", "uma",
    "um", "seu", "sua", "nos", "nas", "pelo", "pela", "aos", "entre",
    "sobre", "apos", "ate", "sem", "como", "mais", "este", "esta",
    "esse", "essa",
    # Termos genéricos de licitação
    "tipo", "lote", "item", "itens",
    "conforme", "especificacao", "descricao", "complementar",
    "referencia", "marca", "modelo", "similar", "equivalente",
    "minimo", "maximo", "aproximadamente", "aproximado",
    "sendo", "devera", "dever", "podera", "poder",
    "forma", "acordo", "seguinte", "demais",
})

# ── Sinônimos para normalização ──────────────────────────────

# Antes de gerar chave, substitui variações pelo termo canônico.
# Chave = valor canônico. Todas as variações apontam para ele.
SINONIMOS: dict[str, str] = {
    # Software / Sistema
    "sistema": "software",
    "sistemas": "software",
    "solucao": "software",
    # Gestão
    "gestao": "gerenciamento",
    "administracao": "gerenciamento",
    # Hardware
    "microcomputador": "computador",
    "microcomputadores": "computador",
    "notebook": "computador",
    "notebooks": "computador",
    "desktop": "computador",
    "workstation": "computador",
    # Impressão
    "multifuncional": "impressora",
    "multifuncionais": "impressora",
    "impressoras": "impressora",
    # Energia
    "estabilizador": "nobreak",
    "estabilizadores": "nobreak",
    # Licenciamento
    "permissao": "licenca",
    "cessao": "licenca",
    "locacao": "licenca",
    "licenciamento": "licenca",
    "licencas": "licenca",
    # Rede
    "switch": "switch",
    "switches": "switch",
    "roteador": "roteador",
    "roteadores": "roteador",
    "access point": "roteador",
    # Armazenamento
    "hd": "disco",
    "ssd": "disco",
    "disco rigido": "disco",
    "pen drive": "pendrive",
    # Periféricos
    "mouse": "mouse",
    "mouses": "mouse",
    "teclado": "teclado",
    "teclados": "teclado",
    "monitor": "monitor",
    "monitores": "monitor",
    # Serviços
    "manutencao": "manutencao",
    "suporte": "manutencao",
    "assistencia": "manutencao",
    # Nuvem
    "nuvem": "cloud",
    "cloud": "cloud",
    "saas": "cloud",
    "hospedagem": "cloud",
}

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
    frozenset({"m", "metro", "metro linear"}),
    frozenset({"ml", "mililitro"}),
    frozenset({"m2", "m²", "metro quadrado"}),
    frozenset({"m3", "m³", "metro cubico"}),
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
