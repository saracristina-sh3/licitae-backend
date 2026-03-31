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
    "gasoleo": "diesel",
    # Serviços (sinônimos semânticos)
    "conserto": "manutencao",
    "reparo": "manutencao",
    "conservacao": "manutencao",
    "capacitacao": "treinamento",
    "instalacao": "montagem",
    "fornecimento": "suprimento",
    "atendimento": "consulta",
    "avaliacao": "analise",
    "chamamento": "convocacao",
    "credenciamento": "habilitacao",
    "remocao": "transporte",
    "retirada": "remocao",
    "terapia": "tratamento",
    # Hardware (sinônimos semânticos)
    "micro": "computador",
    "portatil": "notebook",
    "inox": "aco",
    "cabo": "fio",
    "conector": "ligacao",
    "tonner": "toner",
    # Veículos
    "caminhao": "veiculo",
    "caminhonete": "pickup",
    "onibus": "veiculo",
    "carreta": "reboque",
    "ambulancia": "veiculo",
    "guincho": "socorro",
    "betoneira": "misturador",
    # Saúde / Exames
    "ultrasson": "ecografia",
    "ultrassonografia": "ecografia",
    "tomografia": "exame",
    "ressonancia": "exame",
    "endoscopia": "exame",
    "colonoscopia": "exame",
    "biopsia": "exame",
    "cintilografia": "exame",
    "angiografia": "exame",
    "arteriografia": "exame",
    "cistoscopia": "exame",
    "ureteroscopia": "exame",
    # Saúde / Especialidades
    "pediatra": "medico",
    "ginecologista": "medico",
    "ortopedista": "medico",
    "neurologista": "medico",
    "oftalmologista": "medico",
    "cardiologista": "medico",
    "psiquiatra": "medico",
    "cirurgiao": "medico",
    "dentista": "odonto",
    # Alimentos
    "aipim": "mandioca",
    "bolacha": "biscoito",
    "refeicao": "alimentacao",
    # Construção
    "pedreiro": "construtor",
    "carpinteiro": "marceneiro",
    "encanador": "hidraulico",
    "bombeiro": "hidraulico",
    "terraplanagem": "construcao",
    # Embalagem
    "embalagem": "pacote",
    "maco": "pacote",
    "tanque": "reservatorio",
    # Anatomia (para agrupamento de exames)
    "torax": "peito",
    "toracica": "peito",
    "cervical": "pescoco",
    "vertebras": "coluna",
    "pelve": "quadril",
    "cerebral": "craniano",
    "pulmonar": "pulmao",
    # ── Sinônimos gerados por IA (2026-03-31) ───────────────────────
    # Utensílios de cozinha
    "abridor": "saca",
    "assadeira": "forma",
    "batedor": "mixer",
    "cafeteira": "maquina",
    "caldeirao": "panela",
    "caneca": "xicara",
    "coador": "filtro",
    "colher": "talher",
    "concha": "talher",          # aplainado: concha→colher→talher
    "copo": "recipiente",
    "descascador": "cortador",
    "espremedor": "extrator",
    "faca": "talher",
    "frigideira": "panela",
    "garfo": "talher",
    "panela": "recipiente",
    "peneira": "filtro",         # aplainado: peneira→coador→filtro
    "prato": "vasilha",
    "ralador": "processador",
    "tigela": "recipiente",
    # Limpeza
    "balde": "recipiente",
    "detergente": "sabao",
    "escova": "vassoura",        # circular resolvido: escova→vassoura
    "esponja": "bucha",
    "mop": "esfregao",
    "pano": "trapo",
    "rodo": "puxador",
    "vassoura": "limpeza",       # circular resolvido: vassoura→limpeza
    # Saúde / Materiais hospitalares
    "agulha": "dispositivo",
    "algodao": "chumaco",
    "autoclave": "esterilizador",
    "bandagem": "atadura",
    "cateter": "sonda",
    "curativo": "penso",
    "desfibrilador": "cardioversor",
    "estetoscopio": "fonendoscopio",
    "gaze": "compressa",
    "mascara": "respirador",
    "seringa": "dispositivo",
    "soro": "solucao",
    # EPI / Vestuário
    "avental": "jaleco",
    "bota": "calcado",
    "capacete": "casco",
    "cinto": "faixa",
    "colete": "vest",
    "coturno": "calcado",        # aplainado: coturno→bota→calcado
    "luva": "protecao",
    "oculos": "protecao",
    "touca": "gorro",
    # Ferramentas
    "alicate": "torques",
    "broca": "furadeira",
    "chave": "ferramenta",
    "disjuntor": "ferramenta",   # aplainado: disjuntor→chave→ferramenta
    "martelo": "malho",
    "parafuso": "rosca",
    "prego": "fixador",
    "pincel": "trincha",
    # Mobiliário / Escritório
    "armario": "estante",
    "arquivo": "gaveteiro",
    "cadeira": "assento",
    "cofre": "arca",
    "colchao": "cama",
    "cortina": "persiana",
    "gaveta": "compartimento",
    "luminaria": "lampada",
    "mesa": "bancada",
    "prateleira": "estante",
    "quadro": "painel",
    # Material de escritório
    "cartucho": "toner",
    "cola": "adesivo",
    "envelope": "sobrecarta",
    "etiqueta": "rotulo",
    "fita": "adesivo",
    "fitilho": "adesivo",       # aplainado: fitilho→fita→adesivo
    # Elétrico / Hidráulico
    "aquecedor": "radiador",
    "bebedouro": "purificador",
    "compressor": "bomba",
    "destilador": "purificador",
    "dispenser": "suporte",
    "eletroduto": "conduite",
    "extensao": "fio",           # aplainado: extensao→cabo→fio
    "fechadura": "trinco",
    "rolo": "cilindro",
    "ventilador": "circulador",
    # Veículos
    "carrinho": "carro",
    # Químico
    "etilico": "alcool",
    "tinta": "verniz",
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
