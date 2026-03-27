"""
Enriquece o dicionário de sinônimos usando IA.
Extrai descrições únicas do banco, pede à IA para agrupar e gerar sinônimos.
Custo estimado: ~$0.15-0.30 por rodada.

Uso:
    docker exec licitae-mcp python scripts/enriquecer_sinonimos.py
"""

import sys
sys.path.insert(0, "/app")

import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


PROMPT_TEMPLATE = (
    "Você é um especialista em licitações públicas brasileiras.\n\n"
    "Analise as descrições de itens de licitação abaixo e gere um dicionário de sinônimos "
    "para normalização. O objetivo é agrupar itens que são o mesmo produto/serviço mas "
    "descritos de formas diferentes.\n\n"
    "REGRAS:\n"
    '1. Retorne APENAS um JSON válido, sem markdown\n'
    '2. Formato: {"variacao": "termo_canonico", ...}\n'
    "3. O termo canônico deve ser o mais curto e comum\n"
    "4. Agrupe: singular/plural, abreviações, variações regionais\n"
    "5. NÃO inclua preposições, artigos ou stopwords\n"
    "6. Foque em termos técnicos de TI, medicamentos, materiais, serviços\n"
    "7. Mínimo 50 sinônimos, máximo 200\n\n"
    "DESCRIÇÕES (amostra do banco):\n"
    "{descricoes}\n\n"
    "Retorne o JSON de sinônimos:"
)


def extrair_descricoes_unicas(client, limite: int = 1000) -> list[str]:
    """Extrai descrições únicas mais frequentes."""
    result = (
        client.table("itens_contratacao")
        .select("descricao")
        .gt("valor_unitario_estimado", 0)
        .not_.is_("descricao", "null")
        .limit(limite)
        .execute()
    )

    descricoes = set()
    for row in (result.data or []):
        desc = (row.get("descricao") or "").strip()
        if len(desc) > 5:
            # Pega só as primeiras 5 palavras (para reduzir tokens)
            palavras = desc.split()[:5]
            descricoes.add(" ".join(palavras).lower())

    return sorted(descricoes)[:500]  # Max 500 para caber no contexto


def chamar_ia(descricoes: list[str]) -> dict:
    """Chama Claude para gerar sinônimos."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            return _chamar_gemini(api_key, descricoes)
        raise RuntimeError("Nenhuma API key configurada")

    return _chamar_anthropic(api_key, descricoes)


def _chamar_anthropic(api_key: str, descricoes: list[str]) -> dict:
    import anthropic

    prompt = PROMPT_TEMPLATE.format(descricoes="\n".join(f"- {d}" for d in descricoes))

    claude = anthropic.Anthropic(api_key=api_key)
    response = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    texto = response.content[0].text.strip()
    if texto.startswith("```"):
        linhas = texto.split("\n")
        linhas = [l for l in linhas if not l.strip().startswith("```")]
        texto = "\n".join(linhas)

    log.info(
        "Claude: %d input + %d output tokens | $%.4f",
        response.usage.input_tokens,
        response.usage.output_tokens,
        (response.usage.input_tokens * 3 + response.usage.output_tokens * 15) / 1_000_000,
    )

    return json.loads(texto)


def _chamar_gemini(api_key: str, descricoes: list[str]) -> dict:
    from google import genai

    prompt = PROMPT_TEMPLATE.format(descricoes="\n".join(f"- {d}" for d in descricoes))

    gemini = genai.Client(api_key=api_key)
    response = gemini.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={"max_output_tokens": 4096, "temperature": 0.2},
    )

    texto = (response.text or "").strip()
    if texto.startswith("```"):
        linhas = texto.split("\n")
        linhas = [l for l in linhas if not l.strip().startswith("```")]
        texto = "\n".join(linhas)

    return json.loads(texto)


def merge_sinonimos(existentes: dict, novos: dict) -> dict:
    """Merge novos sinônimos com existentes. Existentes têm prioridade."""
    merged = dict(existentes)
    adicionados = 0
    for variacao, canonico in novos.items():
        variacao = variacao.lower().strip()
        canonico = canonico.lower().strip()
        if variacao and canonico and variacao != canonico and variacao not in merged:
            merged[variacao] = canonico
            adicionados += 1
    log.info("Adicionados %d novos sinônimos (total: %d)", adicionados, len(merged))
    return merged


def main():
    from db import get_client
    from comparison_core.constants import SINONIMOS

    log.info("=== Enriquecimento de Sinônimos via IA ===")

    client = get_client()

    # 1. Extrai descrições
    log.info("Extraindo descrições únicas do banco...")
    descricoes = extrair_descricoes_unicas(client)
    log.info("Encontradas %d descrições únicas", len(descricoes))

    if not descricoes:
        log.warning("Nenhuma descrição encontrada")
        return

    # 2. Chama IA
    log.info("Chamando IA para gerar sinônimos...")
    novos = chamar_ia(descricoes)
    log.info("IA retornou %d sinônimos", len(novos))

    # 3. Merge
    merged = merge_sinonimos(SINONIMOS, novos)

    # 4. Salva em arquivo para review
    output = "/app/sinonimos_gerados.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, sort_keys=True)

    log.info("Sinônimos salvos em %s", output)
    log.info("Revise o arquivo e copie para comparison_core/constants.py")

    # Mostra os novos (para review rápido)
    novos_adicionados = {k: v for k, v in merged.items() if k not in SINONIMOS}
    if novos_adicionados:
        log.info("\n=== NOVOS SINÔNIMOS ===")
        for k, v in sorted(novos_adicionados.items()):
            print(f'    "{k}": "{v}",')


if __name__ == "__main__":
    main()
