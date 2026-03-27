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


SYSTEM_PROMPT = (
    "Você é um especialista em licitações públicas brasileiras. "
    "Sua tarefa é analisar descrições de itens de licitação e gerar "
    "um dicionário de sinônimos para normalização de texto."
)

USER_PROMPT_PREFIX = """Analise as descrições de itens de licitação abaixo e gere um dicionário de sinônimos para normalização. O objetivo é agrupar itens que são o mesmo produto/serviço mas descritos de formas diferentes entre plataformas.

REGRAS:
1. Retorne APENAS um JSON válido, sem markdown, sem explicação
2. Cada entrada mapeia uma variação para o termo canônico (mais curto e comum)
3. Agrupe: singular/plural, abreviações, variações regionais, erros de digitação
4. NÃO inclua preposições, artigos ou stopwords
5. Foque em termos técnicos de TI, saúde, materiais, serviços, alimentos
6. Mínimo 80 sinônimos, máximo 300
7. Use apenas letras minúsculas sem acentos nos termos

Exemplo de formato esperado:
{"notebooks": "computador", "microcomputador": "computador", "impressoras": "impressora"}

DESCRIÇÕES (amostra do banco):
"""


def extrair_descricoes_unicas(client, limite: int = 1000) -> list[str]:
    """Extrai descrições únicas mais frequentes."""
    result = (
        client.table("itens_contratacao")
        .select("descricao")
        .gt("valor_unitario_estimado", 0)
        .not_.is_("descricao", "null")
        .order("created_at", desc=True)
        .limit(limite)
        .execute()
    )

    descricoes = set()
    for row in (result.data or []):
        desc = (row.get("descricao") or "").strip()
        if len(desc) > 5:
            palavras = desc.split()[:6]
            descricoes.add(" ".join(palavras).lower())

    return sorted(descricoes)[:300]


def montar_prompt(descricoes: list[str]) -> str:
    """Monta o prompt completo com as descrições."""
    lista = "\n".join("- " + d for d in descricoes)
    return USER_PROMPT_PREFIX + lista + "\n\nRetorne o JSON de sinônimos:"


def chamar_ia(descricoes: list[str]) -> dict:
    """Chama a IA disponível para gerar sinônimos."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return _chamar_anthropic(api_key, descricoes)

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return _chamar_gemini(api_key, descricoes)

    raise RuntimeError("Nenhuma API key configurada (ANTHROPIC_API_KEY ou GEMINI_API_KEY)")


def _chamar_anthropic(api_key: str, descricoes: list[str]) -> dict:
    import anthropic

    prompt = montar_prompt(descricoes)

    claude = anthropic.Anthropic(api_key=api_key)
    response = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    texto = response.content[0].text.strip()
    # Remove markdown se presente
    if texto.startswith("```"):
        linhas = texto.split("\n")
        linhas = [l for l in linhas if not l.strip().startswith("```")]
        texto = "\n".join(linhas)

    custo = (response.usage.input_tokens * 3 + response.usage.output_tokens * 15) / 1_000_000
    log.info(
        "Claude: %d input + %d output tokens | $%.4f",
        response.usage.input_tokens,
        response.usage.output_tokens,
        custo,
    )

    # Se JSON truncado, tenta reparar fechando a chave
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        # Encontra a última entrada completa ("key": "value")
        ultimo_fecha = texto.rfind('"')
        if ultimo_fecha > 0:
            # Volta até encontrar uma entrada completa
            trecho = texto[:ultimo_fecha + 1]
            # Remove trailing comma se houver
            trecho = trecho.rstrip().rstrip(",")
            trecho += "}"
            log.warning("JSON truncado — reparado cortando no último par completo")
            return json.loads(trecho)


def _chamar_gemini(api_key: str, descricoes: list[str]) -> dict:
    from google import genai
    import time

    prompt = SYSTEM_PROMPT + "\n\n" + montar_prompt(descricoes)

    gemini = genai.Client(api_key=api_key)

    for tentativa in range(4):
        try:
            response = gemini.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={"max_output_tokens": 4096, "temperature": 0.2},
            )
            break
        except Exception as e:
            if "429" in str(e) and tentativa < 3:
                espera = (tentativa + 1) * 30
                log.warning("Gemini 429 — aguardando %ds", espera)
                time.sleep(espera)
            else:
                raise

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
    log.info("Revise e copie para comparison_core/constants.py")

    # Mostra os novos
    novos_adicionados = {k: v for k, v in merged.items() if k not in SINONIMOS}
    if novos_adicionados:
        log.info("\n=== %d NOVOS SINÔNIMOS ===", len(novos_adicionados))
        for k, v in sorted(novos_adicionados.items()):
            print(f'    "{k}": "{v}",')


if __name__ == "__main__":
    main()
