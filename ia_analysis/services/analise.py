"""Serviço de análise IA — suporta Anthropic (Claude) e Google (Gemini)."""

from __future__ import annotations

import json
import logging
import os
import time

from ia_analysis.constants import (
    MAX_TOKENS_RESPOSTA,
    PROMPT_EDITAL,
    PROMPT_VIABILIDADE,
    SYSTEM_PROMPT,
)
from ia_analysis.services.preparacao import contexto_para_texto, preparar_contexto
from ia_analysis.services.persistencia import gravar_analise
from ia_analysis.types import AnaliseIA, ResultadoAnalise

log = logging.getLogger(__name__)

# Custos por 1M tokens (USD)
_CUSTOS = {
    # Anthropic
    "claude-sonnet-4-5-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    # Google
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.0, "output": 0.0},
}

# Modelos padrão por provider
_MODELO_ANTHROPIC = "claude-sonnet-4-20250514"
_MODELO_GEMINI = "gemini-2.0-flash-lite"


def _estimar_custo(modelo: str, tokens_in: int, tokens_out: int) -> float:
    custos = _CUSTOS.get(modelo, {"input": 1.0, "output": 5.0})
    return (tokens_in * custos["input"] + tokens_out * custos["output"]) / 1_000_000


def _parse_resposta(texto: str) -> AnaliseIA:
    """Extrai JSON da resposta, tolerando markdown."""
    texto = texto.strip()
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


def _detectar_provider() -> tuple[str, str, str]:
    """Detecta qual provider usar. Retorna (provider, api_key, modelo)."""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if anthropic_key:
        return "anthropic", anthropic_key, _MODELO_ANTHROPIC
    if gemini_key:
        return "gemini", gemini_key, _MODELO_GEMINI

    raise RuntimeError("Nenhuma API key configurada (ANTHROPIC_API_KEY ou GEMINI_API_KEY)")


def _chamar_anthropic(api_key: str, modelo: str, prompt: str) -> tuple[str, int, int]:
    """Chama Claude API. Retorna (texto, tokens_in, tokens_out)."""
    import anthropic

    claude = anthropic.Anthropic(api_key=api_key)
    response = claude.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS_RESPOSTA,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    texto = response.content[0].text
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    return texto, tokens_in, tokens_out


def _chamar_gemini(api_key: str, modelo: str, prompt: str) -> tuple[str, int, int]:
    """Chama Gemini API com retry para 429. Retorna (texto, tokens_in, tokens_out)."""
    from google import genai

    gemini = genai.Client(api_key=api_key)

    # Retry com backoff para rate limiting (429)
    max_tentativas = 4
    for tentativa in range(max_tentativas):
        try:
            response = gemini.models.generate_content(
                model=modelo,
                contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
                config={
                    "max_output_tokens": MAX_TOKENS_RESPOSTA,
                    "temperature": 0.2,
                },
            )
            break  # Sucesso
        except Exception as e:
            if "429" in str(e) and tentativa < max_tentativas - 1:
                espera = (tentativa + 1) * 30  # 30s, 60s, 90s
                log.warning("Gemini 429 — aguardando %ds (tentativa %d/%d)", espera, tentativa + 1, max_tentativas)
                time.sleep(espera)
            else:
                raise

    texto = response.text or ""
    tokens_in = 0
    tokens_out = 0
    if response.usage_metadata:
        tokens_in = response.usage_metadata.prompt_token_count or 0
        tokens_out = response.usage_metadata.candidates_token_count or 0
    return texto, tokens_in, tokens_out


def analisar(
    client,
    licitacao_id: str,
    tipo: str = "completa",
    modelo: str | None = None,
) -> ResultadoAnalise:
    """
    Executa análise IA completa de uma licitação.

    Detecta automaticamente o provider:
    - ANTHROPIC_API_KEY → usa Claude (prioridade)
    - GEMINI_API_KEY → usa Gemini (fallback)
    """
    provider, api_key, modelo_default = _detectar_provider()
    modelo = modelo or modelo_default

    t0 = time.time()

    # 1. Preparar contexto
    contexto = preparar_contexto(client, licitacao_id)
    textos = contexto_para_texto(contexto)

    # 2. Montar prompt
    if tipo == "edital":
        prompt = PROMPT_EDITAL.format(**textos)
    else:
        prompt = PROMPT_VIABILIDADE.format(**textos)

    # 3. Chamar IA
    log.info("[%s] Chamando %s (%s) tipo=%s...", licitacao_id[:8], provider, modelo, tipo)

    if provider == "anthropic":
        texto_resposta, tokens_in, tokens_out = _chamar_anthropic(api_key, modelo, prompt)
    else:
        texto_resposta, tokens_in, tokens_out = _chamar_gemini(api_key, modelo, prompt)

    tempo_ms = int((time.time() - t0) * 1000)
    custo = _estimar_custo(modelo, tokens_in, tokens_out)

    # 4. Parse resposta
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
        "[%s] %s: %s (score=%d) | %d+%d tokens | $%.4f | %dms",
        licitacao_id[:8], provider,
        analise["recomendacao"],
        analise["score_viabilidade"],
        tokens_in, tokens_out, custo, tempo_ms,
    )

    return resultado
