"""
Constantes centralizadas do analisador de editais v2.
Taxonomia, regex compilada, pesos de scoring e configuração.
"""

from __future__ import annotations

import re

# ── Versão e metadados ───────────────────────────────────────

VERSAO_ALGORITMO = "v2"
METODO_EXTRACAO = "pdfminer"
LIMITE_TEXTO_BANCO = 50_000

# ── Taxonomia de documentos ──────────────────────────────────
# Cada código mapeia para: (label legível, [regex compiladas])

TAXONOMIA_DOCUMENTOS: dict[str, tuple[str, list[re.Pattern]]] = {
    "DOC_CERTIDAO_FEDERAL": (
        "Certidão negativa federal",
        [re.compile(r"certid[ãa]o\s+(?:negativa\s+)?(?:de\s+)?[\w\s]+federal", re.I)],
    ),
    "DOC_CERTIDAO_ESTADUAL": (
        "Certidão negativa estadual",
        [re.compile(r"certid[ãa]o\s+(?:negativa\s+)?(?:de\s+)?[\w\s]+estadual", re.I)],
    ),
    "DOC_CERTIDAO_MUNICIPAL": (
        "Certidão negativa municipal",
        [re.compile(r"certid[ãa]o\s+(?:negativa\s+)?(?:de\s+)?[\w\s]+municipal", re.I)],
    ),
    "DOC_CERTIDAO_TRABALHISTA": (
        "Certidão negativa trabalhista",
        [re.compile(r"certid[ãa]o\s+(?:negativa\s+)?(?:de\s+)?[\w\s]+trabalhista", re.I)],
    ),
    "DOC_FGTS": (
        "Certidão de regularidade FGTS",
        [re.compile(r"certid[ãa]o\s+(?:negativa\s+)?(?:de\s+)?[\w\s]+FGTS", re.I)],
    ),
    "DOC_INSS": (
        "Certidão de regularidade INSS",
        [re.compile(r"certid[ãa]o\s+(?:negativa\s+)?(?:de\s+)?[\w\s]+INSS", re.I)],
    ),
    "DOC_ATESTADO_CAPACIDADE": (
        "Atestado de capacidade técnica",
        [re.compile(r"atestado\s+de\s+capacidade\s+t[ée]cnica", re.I)],
    ),
    "DOC_CONTRATO_SOCIAL": (
        "Contrato social / Ato constitutivo",
        [re.compile(r"contrato\s+social|ato\s+constitutivo", re.I)],
    ),
    "DOC_BALANCO_PATRIMONIAL": (
        "Balanço patrimonial",
        [re.compile(r"balan[çc]o\s+patrimonial", re.I)],
    ),
    "DOC_JUNTA_COMERCIAL": (
        "Certidão da Junta Comercial",
        [re.compile(r"certid[ãa]o\s+(?:simplificada\s+)?(?:da\s+)?junta\s+comercial", re.I)],
    ),
    "DOC_CNPJ": (
        "Comprovante de inscrição no CNPJ",
        [re.compile(r"comprovante\s+de\s+inscri[çc][ãa]o\s+(?:no\s+)?CNPJ", re.I)],
    ),
    "DOC_ALVARA": (
        "Alvará de funcionamento",
        [re.compile(r"alvar[áa]\s+de\s+funcionamento", re.I)],
    ),
    "DOC_DECLARACAO_MENOR": (
        "Declaração de não emprego de menor",
        [re.compile(r"declara[çc][ãa]o\s+(?:de\s+)?(?:que\s+)?(?:n[ãa]o\s+)?(?:emprega|utiliza)\s+(?:menor|trabalho\s+infantil)", re.I)],
    ),
    "DOC_DECLARACAO_IDONEIDADE": (
        "Declaração de idoneidade",
        [re.compile(r"declara[çc][ãa]o\s+de\s+idoneidade", re.I)],
    ),
    "DOC_DECLARACAO_IMPEDITIVOS": (
        "Declaração de inexistência de fatos impeditivos",
        [re.compile(r"declara[çc][ãa]o\s+de\s+inexist[êe]ncia\s+de\s+fatos?\s+impeditivos?", re.I)],
    ),
    "DOC_REGISTRO_CONSELHO": (
        "Registro em conselho profissional",
        [re.compile(r"registro\s+(?:no\s+)?(?:conselho|CRA|CRC|CREA|CAU|OAB)", re.I)],
    ),
    "DOC_CERTIDAO_FISCAL": (
        "Certidão de regularidade fiscal",
        [
            re.compile(r"certid[ãa]o\s+de\s+(?:regularidade|d[ée]bitos?)\s+(?:fiscal|tribut[áa]ria)", re.I),
            re.compile(r"prova\s+de\s+regularidade\s+(?:fiscal|para\s+com)", re.I),
        ],
    ),
    "DOC_GARANTIA_PROPOSTA": (
        "Garantia de proposta / Caução",
        [re.compile(r"garantia\s+(?:de\s+)?proposta|cau[çc][ãa]o", re.I)],
    ),
}

# ── Taxonomia de requisitos técnicos ─────────────────────────

RE_REQUISITOS_TECNICOS = [
    re.compile(p, re.I) for p in [
        r"(?:dever[áa]|deve)\s+(?:possuir|apresentar|comprovar|demonstrar|dispor\s+de)\s+[^.;]{10,120}",
        r"requisito[s]?\s+t[ée]cnico[s]?\s*[:]\s*[^.;]{10,200}",
        r"especifica[çc][ãa]o\s+t[ée]cnica[s]?\s*[:]\s*[^.;]{10,200}",
        r"(?:sistema|software|solu[çc][ãa]o)\s+(?:deve|dever[áa])\s+[^.;]{10,150}",
        r"funcionalidade[s]?\s+(?:m[íi]nima[s]?|obrigat[óo]ria[s]?)\s*[:]\s*[^.;]{10,200}",
        r"m[óo]dulo[s]?\s+(?:de|do|da)\s+[\w\s]+(?:deve|dever[áa]|com)\s+[^.;]{10,150}",
        r"integra[çc][ãa]o\s+(?:com|ao|entre)\s+[^.;]{10,120}",
        r"migra[çc][ãa]o\s+(?:de\s+)?dados?\s+[^.;]{10,120}",
        r"treinamento|capacita[çc][ãa]o\s+[^.;]{10,120}",
        r"suporte\s+t[ée]cnico\s+[^.;]{10,120}",
    ]
]

# ── Taxonomia de riscos ──────────────────────────────────────

TAXONOMIA_RISCOS: dict[str, tuple[str, list[re.Pattern], int]] = {
    # codigo: (label, [regex], peso_risco)
    "RISCO_MULTA": (
        "Multa contratual",
        [re.compile(r"multa\s+(?:de\s+)?(?:\d+[%,]|[\w\s]+por\s+cento)\s*[^.;]{5,120}", re.I)],
        15,
    ),
    "RISCO_PENALIDADE": (
        "Penalidades",
        [re.compile(r"penalidade[s]?\s*[:]\s*[^.;]{10,200}", re.I)],
        10,
    ),
    "RISCO_SANCAO": (
        "Sanções administrativas",
        [re.compile(r"san[çc][ãa]o|san[çc][õo]es\s+[^.;]{10,150}", re.I)],
        10,
    ),
    "RISCO_RESCISAO": (
        "Rescisão contratual",
        [re.compile(r"rescis[ãa]o\s+(?:do\s+)?contrato\s+[^.;]{10,120}", re.I)],
        10,
    ),
    "RISCO_GARANTIA_CONTRATUAL": (
        "Garantia contratual",
        [re.compile(r"garantia\s+(?:contratual|de\s+execu[çc][ãa]o)\s+(?:de\s+)?(?:\d+[%])\s*[^.;]{5,100}", re.I)],
        15,
    ),
    "RISCO_RETENCAO_PAGAMENTO": (
        "Retenção de pagamento",
        [re.compile(r"reten[çc][ãa]o\s+(?:de\s+)?(?:pagamento|valor)\s+[^.;]{10,120}", re.I)],
        10,
    ),
    "RISCO_SUSPENSAO": (
        "Suspensão temporária",
        [re.compile(r"suspens[ãa]o\s+(?:tempor[áa]ria|do\s+direito)\s+[^.;]{10,120}", re.I)],
        15,
    ),
    "RISCO_IMPEDIMENTO_CONTRATAR": (
        "Impedimento de licitar/contratar",
        [re.compile(r"impedimento\s+de\s+(?:licitar|contratar)\s+[^.;]{10,120}", re.I)],
        20,
    ),
}

# ── Taxonomia de qualificação ────────────────────────────────

TAXONOMIA_QUALIFICACAO: dict[str, tuple[str, list[re.Pattern]]] = {
    "QUAL_HABILITACAO_JURIDICA": (
        "Habilitação jurídica",
        [re.compile(r"habilita[çc][ãa]o\s+jur[íi]dica\s*[:]\s*[^.;]{10,200}", re.I)],
    ),
    "QUAL_HABILITACAO_TECNICA": (
        "Qualificação técnica",
        [
            re.compile(r"habilita[çc][ãa]o\s+t[ée]cnica\s*[:]\s*[^.;]{10,200}", re.I),
            re.compile(r"qualifica[çc][ãa]o\s+t[ée]cnica\s*[:]\s*[^.;]{10,200}", re.I),
        ],
    ),
    "QUAL_HABILITACAO_ECONOMICA": (
        "Qualificação econômico-financeira",
        [
            re.compile(r"habilita[çc][ãa]o\s+econ[ôo]mica\s*[:]\s*[^.;]{10,200}", re.I),
            re.compile(r"qualifica[çc][ãa]o\s+econ[ôo]mica\s*[:]\s*[^.;]{10,200}", re.I),
        ],
    ),
    "QUAL_REGULARIDADE_FISCAL": (
        "Regularidade fiscal",
        [re.compile(r"regularidade\s+fiscal\s+[^.;]{10,150}", re.I)],
    ),
    "QUAL_CAPITAL_SOCIAL": (
        "Capital social mínimo",
        [re.compile(r"capital\s+(?:social|m[íi]nimo)\s+(?:de\s+)?R?\$?\s*[\d.,]+", re.I)],
    ),
    "QUAL_PATRIMONIO_LIQUIDO": (
        "Patrimônio líquido mínimo",
        [re.compile(r"patrim[ôo]nio\s+l[íi]quido\s+(?:m[íi]nimo\s+)?(?:de\s+)?R?\$?\s*[\d.,]+", re.I)],
    ),
    "QUAL_FATURAMENTO": (
        "Faturamento mínimo",
        [re.compile(r"faturamento\s+(?:m[íi]nimo|bruto|anual)\s+[^.;]{10,120}", re.I)],
    ),
    "QUAL_EXPERIENCIA": (
        "Experiência mínima",
        [re.compile(r"experi[êe]ncia\s+(?:m[íi]nima\s+)?(?:de\s+)?(?:\d+)\s*(?:anos?|meses?)\s*[^.;]{5,100}", re.I)],
    ),
}

# ── Prazos — regex e classificação ───────────────────────────

RE_PRAZOS = [
    re.compile(p, re.I) for p in [
        r"prazo\s+(?:de\s+)?(?:vig[êe]ncia|execu[çc][ãa]o|entrega|implanta[çc][ãa]o|contrato)\s*(?:[:=]|(?:de|ser[áa]\s+de))\s*(\d+)\s*(dias?|meses?|anos?|horas?)",
        r"(\d+)\s*\(\s*[\w\s]+\)\s*(dias?|meses?|anos?)\s*(?:corridos?|[úu]teis?)?(?:\s*(?:para|de)\s+[\w\s]+)?",
        r"(?:no\s+prazo\s+de|em\s+at[ée])\s*(\d+)\s*(dias?|meses?|anos?|horas?)",
    ]
]

TIPOS_PRAZO: dict[str, list[str]] = {
    "vigencia": ["vigência", "vigencia", "duração do contrato", "duracao"],
    "execucao": ["execução", "execucao"],
    "entrega": ["entrega", "fornecimento"],
    "implantacao": ["implantação", "implantacao", "implementação", "implementacao"],
    "pagamento": ["pagamento", "fatura"],
    "suporte": ["suporte", "manutenção", "manutencao"],
    "recurso": ["recurso", "impugnação", "impugnacao"],
    "assinatura": ["assinatura", "contratação", "contratacao"],
    "garantia": ["garantia"],
}

# ── Pesos de score de confiança (total = 100) ────────────────

PESO_CONFIANCA_QUALIDADE_EXTRACAO = 30
PESO_CONFIANCA_ARQUIVO = 20
PESO_CONFIANCA_COBERTURA = 20
PESO_CONFIANCA_TEXTO_UTIL = 15
PESO_CONFIANCA_TERMOS_TIPICOS = 15

FAIXA_CONFIANCA_ALTA = 70
FAIXA_CONFIANCA_MEDIA = 40

# ── Seleção de arquivo — critérios ───────────────────────────

SCORE_ARQUIVO_NOME_EDITAL = 30
SCORE_ARQUIVO_NOME_TERMO_REF = 25
SCORE_ARQUIVO_TIPO_DOCUMENTO = 20
SCORE_ARQUIVO_TAMANHO = 15
SCORE_ARQUIVO_NAO_ANEXO = 10

# Termos jurídicos para avaliar qualidade do texto
TERMOS_JURIDICOS = {
    "edital", "licitação", "licitacao", "contrato", "pregão", "pregao",
    "dispensa", "habilitação", "habilitacao", "proposta", "certidão",
    "certidao", "modalidade", "objeto", "cláusula", "clausula",
    "penalidade", "sanção", "sancao", "multa", "garantia", "prazo",
    "adjudicação", "adjudicacao", "homologação", "homologacao",
}
