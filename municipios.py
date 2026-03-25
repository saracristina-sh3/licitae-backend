"""
Carrega municípios de MG e RJ com FPM até 2.8 (população até ~91.692 hab)
via API do IBGE — busca em lote (1 request por UF, não por município).
Cache local com TTL de 30 dias.
"""

import json
import logging
import os
import time

import requests

from utils import fpm_coeficiente

log = logging.getLogger(__name__)

CACHE_DIR = os.environ.get("CACHE_DIR", os.path.dirname(__file__))
CACHE_FILE = os.path.join(CACHE_DIR, "municipios.json")
CACHE_TTL_DIAS = 30

UF_CODES = {
    "AC": "12", "AL": "27", "AM": "13", "AP": "16",
    "BA": "29", "CE": "23", "DF": "53", "ES": "32",
    "GO": "52", "MA": "21", "MG": "31", "MS": "50",
    "MT": "51", "PA": "15", "PB": "25", "PE": "26",
    "PI": "22", "PR": "41", "RJ": "33", "RN": "24",
    "RO": "11", "RR": "14", "RS": "43", "SC": "42",
    "SE": "28", "SP": "35", "TO": "17",
}

UF_SIGLAS = {v: k for k, v in UF_CODES.items()}


def _cache_expirado() -> bool:
    """Verifica se o cache local expirou (mais de CACHE_TTL_DIAS dias)."""
    if not os.path.exists(CACHE_FILE):
        return True
    idade = time.time() - os.path.getmtime(CACHE_FILE)
    return idade > CACHE_TTL_DIAS * 86400


def _fetch_populacao_em_lote(uf_code: str) -> dict[str, int]:
    """
    Busca população estimada de TODOS os municípios de uma UF em uma única chamada.
    Retorna: {"3100104": 7000, "3100203": 25000, ...}
    """
    url = (
        f"https://servicodados.ibge.gov.br/api/v3/agregados/6579"
        f"/periodos/-1/variaveis/9324"
        f"?localidades=N6[N3[{uf_code}]]"
    )
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    populacoes = {}
    for serie_item in data[0]["resultados"][0]["series"]:
        codigo = serie_item["localidade"]["id"]
        serie = serie_item["serie"]
        ultimo_ano = max(serie.keys())
        valor = serie[ultimo_ano]
        if valor and valor != "-":
            populacoes[codigo] = int(valor)

    return populacoes


def _fetch_nomes_municipios(uf_code: str) -> dict[str, str]:
    """Busca nomes de todos os municípios de uma UF."""
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf_code}/municipios"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return {str(m["id"]): m["nome"] for m in resp.json()}


def carregar_municipios(ufs: list[str], populacao_maxima: int) -> list[dict]:
    """
    Retorna lista de municípios com FPM até 2.8.
    Usa cache local com TTL de 30 dias. Na primeira execução faz 2 requests por UF.
    """
    if os.path.exists(CACHE_FILE) and os.path.getsize(CACHE_FILE) > 2 and not _cache_expirado():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cached = json.load(f)
            return [
                m for m in cached
                if m["uf"] in ufs and m["populacao"] <= populacao_maxima
            ]

    if _cache_expirado() and os.path.exists(CACHE_FILE):
        log.info("Cache de municípios expirado (>%d dias), atualizando...", CACHE_TTL_DIAS)

    log.info("Carregando municípios do IBGE (busca em lote)...")
    todos = []

    for uf in ufs:
        uf_code = UF_CODES.get(uf)
        if not uf_code:
            log.warning("UF não suportada: %s", uf)
            continue

        log.info("  %s: buscando nomes e população...", uf)

        nomes = _fetch_nomes_municipios(uf_code)
        populacoes = _fetch_populacao_em_lote(uf_code)

        count = 0
        for codigo, nome in nomes.items():
            pop = populacoes.get(codigo, 999999)
            fpm = fpm_coeficiente(pop)
            todos.append({
                "codigo_ibge": codigo,
                "nome": nome,
                "uf": uf,
                "populacao": pop,
                "fpm": fpm,
            })
            if pop <= populacao_maxima:
                count += 1

        log.info("  %s: %d municípios com FPM <= 2.8 (de %d total)", uf, count, len(nomes))

    # Salva cache
    os.makedirs(os.path.dirname(CACHE_FILE) or ".", exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

    log.info("Cache salvo em %s", CACHE_FILE)
    return [m for m in todos if m["uf"] in ufs and m["populacao"] <= populacao_maxima]


def codigos_ibge_municipios(ufs: list[str], populacao_maxima: int) -> list[str]:
    """Retorna apenas os códigos IBGE dos municípios filtrados."""
    return [m["codigo_ibge"] for m in carregar_municipios(ufs, populacao_maxima)]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from config import Config

    munis = carregar_municipios(Config.UFS, Config.POPULACAO_MAXIMA)
    log.info("Total de municípios com FPM <= 2.8: %d", len(munis))
    for uf in Config.UFS:
        count = len([m for m in munis if m["uf"] == uf])
        log.info("  %s: %d municípios", uf, count)
    log.info("Exemplos:")
    for m in munis[:5]:
        log.info("  %s/%s - Pop: %s - FPM: %s", m["nome"], m["uf"], f"{m['populacao']:,}", m["fpm"])
