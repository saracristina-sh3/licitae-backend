"""Serviço de análise IA — chama Gemini API."""

from __future__ import annotations

import json
import logging
import os
import time

from google import genai

from ia_analysis.constants import (
    MAX_TOKENS_RESPOSTA,
    MODELO_PADRAO,
    PROMPT_EDITAL,
    PROMPT_VIABILIDADE,
    SYSTEM_PROMPT,
)
from ia_analysis.services.preparacao import contexto_para_texto, preparar_contexto
from ia_analysis.services.persistencia import gravar_analise
from ia_analysis.types import AnaliseIA, ResultadoAnalise

log = logging.getLogger(__name__)

# Custos por 1M tokens (USD) — Gemini 2.0 Flash
_CUSTOS = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.0, "output": 0.0},
}


def _estimar_custo(modelo: str, tokens_in: int, tokens_out: int) -> float:
    custos = _CUSTOS.get(modelo, {"input": 0.10, "output": 0.40})
    return (tokens_in * custos["input"] + tokens_out * custos["output"]) / 1_000_000


def _parse_resposta(texto: str) -> AnaliseIA:
    """Extrai JSON da resposta, tolerando markdown."""
    texto = texto.strip()
    # Remove ```json ... ``` se presente
    if texto.startswith("```"):
        linhas = texto.split("\n")
        linhas = [l for l in linhas if not l.strip().startswith("```")]
        texto = "\n".join(linhas)

    data = json.loads(texto)

    return AnaliseIA(
        recomendacao=data.get("recomendacao", "avaliar"),
        score_viabilidade=int(data.get("score_viabilidade", 50)),
        resumo=data.get("resumo", ""),
        riscos_identificados=data.get("riscos_identificados", []),
        oportunidades=data.get("oportunidades", []),
        preco_sugerido=data.get("preco_sugerido"),
        margem_sugerida=data.get("margem_sugerida"),
        concorrentes_provaveis=data.get("concorrentes_provaveis", []),
        perguntas_esclarecimento=data.get("perguntas_esclarecimento", []),
    )


def analisar(
    client,
    licitacao_id: str,
    tipo: str = "completa",
    modelo: str = MODELO_PADRAO,
) -> ResultadoAnalise:
    """
    Executa análise IA completa de uma licitação.

    1. Prepara contexto (dados do Supabase)
    2. Chama Gemini API
    3. Grava resultado no Supabase
    4. Retorna resultado
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY não configurada")

    t0 = time.time()

    # 1. Preparar contexto
    contexto = preparar_contexto(client, licitacao_id)
    textos = contexto_para_texto(contexto)

    # 2. Montar prompt
    if tipo == "edital":
        prompt = PROMPT_EDITAL.format(**textos)
    else:
        prompt = PROMPT_VIABILIDADE.format(**textos)

    # 3. Chamar Gemini
    gemini = genai.Client(api_key=api_key)

    log.info("[%s] Chamando Gemini (%s) tipo=%s...", licitacao_id[:8], modelo, tipo)

    response = gemini.models.generate_content(
        model=modelo,
        contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
        config={
            "max_output_tokens": MAX_TOKENS_RESPOSTA,
            "temperature": 0.2,
        },
    )

    tempo_ms = int((time.time() - t0) * 1000)

    # Extrair uso de tokens
    tokens_in = 0
    tokens_out = 0
    if response.usage_metadata:
        tokens_in = response.usage_metadata.prompt_token_count or 0
        tokens_out = response.usage_metadata.candidates_token_count or 0

    custo = _estimar_custo(modelo, tokens_in, tokens_out)

    # 4. Parse resposta
    texto_resposta = response.text or ""
    try:
        analise = _parse_resposta(texto_resposta)
    except (json.JSONDecodeError, KeyError) as e:
        log.error(
            "[%s] Erro ao parsear resposta: %s\nResposta: %s",
            licitacao_id[:8], e, texto_resposta[:500],
        )
        analise = AnaliseIA(
            recomendacao="avaliar",
            score_viabilidade=0,
            resumo=f"Erro ao processar resposta da IA: {e}",
            riscos_identificados=[],
            oportunidades=[],
            preco_sugerido=None,
            margem_sugerida=None,
            concorrentes_provaveis=[],
            perguntas_esclarecimento=[],
        )

    resultado = ResultadoAnalise(
        analise=analise,
        modelo_usado=modelo,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        custo_usd=round(custo, 4),
        tempo_ms=tempo_ms,
    )

    # 5. Gravar
    gravar_analise(client, licitacao_id, tipo, resultado)

    log.info(
        "[%s] Análise IA: %s (score=%d) | %d in + %d out tokens | $%.4f | %dms",
        licitacao_id[:8],
        analise["recomendacao"],
        analise["score_viabilidade"],
        tokens_in, tokens_out, custo, tempo_ms,
    )

    return resultado
