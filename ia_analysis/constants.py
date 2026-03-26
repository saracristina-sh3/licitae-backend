"""Constantes do módulo de análise IA — prompts, modelos, limites."""

from __future__ import annotations

MAX_TOKENS_RESPOSTA = 4096

# ── Prompt do sistema ────────────────────────────────────────────

SYSTEM_PROMPT = """Você é um analista sênior de licitações públicas brasileiras, \
especializado em software e tecnologia para gestão pública.

Sua tarefa é analisar os dados de uma licitação e produzir uma avaliação estruturada.

REGRAS:
- Responda APENAS em JSON válido, sem markdown ou texto extra.
- Todos os campos do schema devem estar presentes (use null quando não aplicável).
- "gravidade" deve ser: "alta", "media" ou "baixa".
- "impacto" deve ser: "alto", "medio" ou "baixo".
- "recomendacao" deve ser: "participar", "avaliar" ou "descartar".
- score_viabilidade é um inteiro de 0 a 100.
- Preços em BRL (reais).
- Seja direto e objetivo nas análises."""

# ── Prompt de viabilidade completa ───────────────────────────────

PROMPT_VIABILIDADE = """Analise esta licitação e avalie se vale a pena participar.

CONTEXTO DA ORGANIZAÇÃO:
{contexto_org}

DADOS DA LICITAÇÃO:
{dados_licitacao}

ANÁLISE DO EDITAL:
{dados_edital}

PREÇOS DE REFERÊNCIA:
{dados_precos}

ITENS DE CONTRATAÇÃO:
{dados_itens}

COMPARATIVO DE MERCADO NA UF:
{dados_comparativo}

Retorne um JSON com este schema exato:
{{
  "recomendacao": "participar" | "avaliar" | "descartar",
  "score_viabilidade": 0-100,
  "resumo": "1-2 parágrafos explicando a decisão",
  "riscos_identificados": [
    {{"risco": "descrição", "gravidade": "alta|media|baixa", "mitigacao": "como mitigar"}}
  ],
  "oportunidades": [
    {{"oportunidade": "descrição", "impacto": "alto|medio|baixo"}}
  ],
  "preco_sugerido": valor_numerico_ou_null,
  "margem_sugerida": percentual_ou_null,
  "concorrentes_provaveis": ["empresa1", "empresa2"],
  "perguntas_esclarecimento": ["pergunta1", "pergunta2"]
}}"""

# ── Prompt de análise de edital ──────────────────────────────────

PROMPT_EDITAL = """Analise o edital desta licitação focando em riscos e requisitos.

DADOS DA LICITAÇÃO:
{dados_licitacao}

ANÁLISE DO EDITAL (extração automática):
{dados_edital}

Retorne um JSON com este schema exato:
{{
  "recomendacao": "participar" | "avaliar" | "descartar",
  "score_viabilidade": 0-100,
  "resumo": "análise focada nos riscos e requisitos do edital",
  "riscos_identificados": [
    {{"risco": "descrição", "gravidade": "alta|media|baixa", "mitigacao": "como mitigar"}}
  ],
  "oportunidades": [
    {{"oportunidade": "descrição", "impacto": "alto|medio|baixo"}}
  ],
  "preco_sugerido": null,
  "margem_sugerida": null,
  "concorrentes_provaveis": [],
  "perguntas_esclarecimento": ["pergunta sobre o edital"]
}}"""
