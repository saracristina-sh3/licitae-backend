"""
Constantes compartilhadas para comparação de itens de licitação.
Fonte única de verdade — NÃO duplicar em outros módulos.
"""

from __future__ import annotations

import re

# ── Regex para tokens válidos ────────────────────────────────────
# Aceita alfanuméricos (a4, usb3, 500ml) mas rejeita puramente numéricos (123)
RE_TOKEN_VALIDO = re.compile(r"^(?!\d+$)[a-z0-9]{2,}$")

# ── Stopwords unificadas ─────────────────────────────────────────
# Preposições/artigos + termos genéricos de licitação que não discriminam.
STOPWORDS: frozenset[str] = frozenset({
    # Preposições e artigos
    "de", "do", "da", "dos", "das", "para", "com", "por", "que", "uma",
    "um", "seu", "sua", "nos", "nas", "pelo", "pela", "aos", "entre",
    "sobre", "apos", "ate", "sem", "como", "mais", "este", "esta",
    "esse", "essa", "ser", "ter", "seus", "suas",
    # Termos genéricos de licitação (não discriminam o item)
    "tipo", "lote", "item", "itens",
    "conforme", "especificacao", "descricao", "complementar",
    "referencia", "marca", "modelo", "similar", "equivalente",
    "minimo", "maximo", "aproximadamente", "aproximado",
    "sendo", "devera", "dever", "podera", "poder",
    "forma", "acordo", "seguinte", "demais",
    # Termos genéricos de contratação
    "contratacao", "empresa", "especializada", "aquisicao",
    "fornecimento", "objeto", "registro", "preco", "precos",
    "modalidade", "processo", "licitatorio",
    "pregao", "eletronico", "presencial",
})

# ── Sinônimos canônicos ──────────────────────────────────────────
# Chave = variação, valor = termo canônico.
# Aplicado ANTES de gerar chaves de agrupamento.
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
    "switches": "switch",
    "roteadores": "roteador",
    # Armazenamento
    "hd": "disco",
    "ssd": "disco",
    # Periféricos
    "mouses": "mouse",
    "teclados": "teclado",
    "monitores": "monitor",
    # Serviços
    "suporte": "manutencao",
    "assistencia": "manutencao",
    # Nuvem
    "nuvem": "cloud",
    "saas": "cloud",
    "hospedagem": "cloud",
    # Combustível
    "etanol": "alcool",
    "gasolina": "gasolina",
    "diesel": "diesel",
}

# ── Grupos de unidades compatíveis ───────────────────────────────
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
    frozenset({"ano", "anual", "anos"}),
    frozenset({"diaria", "dia", "dias"}),
    frozenset({"par", "pares"}),
    frozenset({"dz", "duzia", "dzia"}),
]

# ── Categorias de itens ──────────────────────────────────────────
# Ordem de prioridade na classificação: serviço > licença > consumível > produto
CATEGORIAS: dict[str, list[str]] = {
    "servico": [
        "servico", "servicos", "manutencao", "suporte", "assistencia",
        "consultoria", "treinamento", "capacitacao", "instalacao",
        "configuracao", "prestacao", "execucao", "operacao",
        "assessoria", "auditoria", "monitoramento",
    ],
    "licenca": [
        "licenca", "cessao", "permissao", "locacao", "licenciamento",
        "saas", "cloud", "hospedagem", "software", "sistema",
        "assinatura", "plataforma", "aplicativo", "app",
    ],
    "consumivel": [
        "gasolina", "diesel", "alcool", "etanol", "combustivel",
        "papel", "toner", "cartucho", "tinta",
        "limpeza", "higiene", "descartavel",
        "agua", "alimento", "genero",
    ],
    # "produto" é fallback — tudo que não é serviço/licença/consumível
}

# ── Pares de categorias INCOMPATÍVEIS (Golden Rule) ──────────────
PARES_INCOMPATIVEIS: set[frozenset[str]] = {
    frozenset({"servico", "produto"}),
    frozenset({"servico", "consumivel"}),
    frozenset({"licenca", "consumivel"}),
    frozenset({"licenca", "produto"}),
}

# ── Limites de escala por categoria ──────────────────────────────
ESCALA_MAXIMA: dict[str, float] = {
    "produto": 20.0,
    "consumivel": 20.0,
    "licenca": 5.0,     # 1 licença vs 5 é muito diferente
    "servico": 10.0,
}
ESCALA_MAXIMA_PADRAO = 20.0
