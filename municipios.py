"""
Carrega municípios e microrregiões via API do IBGE.
Busca em lote (1 request por UF). Cache local com TTL de 30 dias.
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
CACHE_MICRORREGIOES_FILE = os.path.join(CACHE_DIR, "microrregioes.json")
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
            # Verifica se o cache contém TODAS as UFs solicitadas
            ufs_no_cache = {m["uf"] for m in cached}
            ufs_faltando = set(ufs) - ufs_no_cache
            if not ufs_faltando:
                return [
                    m for m in cached
                    if m["uf"] in ufs and m["populacao"] <= populacao_maxima
                ]
            log.info("Cache não contém UFs %s, recarregando...", ", ".join(sorted(ufs_faltando)))

    if _cache_expirado() and os.path.exists(CACHE_FILE):
        log.info("Cache de municípios expirado (>%d dias), atualizando...", CACHE_TTL_DIAS)

    log.info("Carregando municípios do IBGE (busca em lote)...")

    # Carrega cache existente para mesclar (não perder UFs já baixadas)
    todos = []
    if os.path.exists(CACHE_FILE) and os.path.getsize(CACHE_FILE) > 2:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cached = json.load(f)
            # Mantém UFs que NÃO serão rebuscadas
            todos = [m for m in cached if m["uf"] not in ufs]

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


# ---------------------------------------------------------------------------
# Microrregiões IBGE
# ---------------------------------------------------------------------------


def _cache_microrregioes_expirado() -> bool:
    if not os.path.exists(CACHE_MICRORREGIOES_FILE):
        return True
    idade = time.time() - os.path.getmtime(CACHE_MICRORREGIOES_FILE)
    return idade > CACHE_TTL_DIAS * 86400


def _fetch_microrregioes_uf(uf_code: str) -> list[dict]:
    """Busca microrregiões de uma UF via API IBGE."""
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf_code}/microrregioes"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fetch_municipios_microrregiao(microrregiao_id: int) -> list[dict]:
    """Busca municípios de uma microrregião via API IBGE."""
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/microrregioes/{microrregiao_id}/municipios"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def carregar_microrregioes(ufs: list[str]) -> list[dict]:
    """
    Carrega microrregiões de todas as UFs solicitadas.
    Retorna lista de dicts com id, nome, mesorregiao_id, mesorregiao_nome, uf.
    Usa cache local com TTL de 30 dias.
    """
    # Verificar cache
    if os.path.exists(CACHE_MICRORREGIOES_FILE) and not _cache_microrregioes_expirado():
        with open(CACHE_MICRORREGIOES_FILE, "r", encoding="utf-8") as f:
            cached = json.load(f)
            ufs_no_cache = {m["uf"] for m in cached}
            ufs_faltando = set(ufs) - ufs_no_cache
            if not ufs_faltando:
                return [m for m in cached if m["uf"] in ufs]
            log.info("Cache microrregiões não contém UFs %s, recarregando...", ", ".join(sorted(ufs_faltando)))

    log.info("Carregando microrregiões do IBGE...")

    # Manter cache existente para UFs não rebuscadas
    todos: list[dict] = []
    if os.path.exists(CACHE_MICRORREGIOES_FILE):
        with open(CACHE_MICRORREGIOES_FILE, "r", encoding="utf-8") as f:
            cached = json.load(f)
            todos = [m for m in cached if m["uf"] not in ufs]

    for uf in ufs:
        uf_code = UF_CODES.get(uf)
        if not uf_code:
            log.warning("UF não suportada: %s", uf)
            continue

        log.info("  %s: buscando microrregiões...", uf)
        raw = _fetch_microrregioes_uf(uf_code)

        for micro in raw:
            meso = micro.get("mesorregiao", {})
            todos.append({
                "id": micro["id"],
                "nome": micro["nome"],
                "mesorregiao_id": meso.get("id", 0),
                "mesorregiao_nome": meso.get("nome", ""),
                "uf": uf,
            })

        log.info("  %s: %d microrregiões", uf, len(raw))

    # Salvar cache
    os.makedirs(os.path.dirname(CACHE_MICRORREGIOES_FILE) or ".", exist_ok=True)
    with open(CACHE_MICRORREGIOES_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

    log.info("Cache microrregiões salvo em %s", CACHE_MICRORREGIOES_FILE)
    return [m for m in todos if m["uf"] in ufs]


def mapear_municipios_por_microrregiao(microrregioes_ids: list[int]) -> dict[str, int]:
    """
    Dado uma lista de IDs de microrregiões, retorna mapeamento
    codigo_ibge -> microrregiao_id para todos os municípios dessas microrregiões.
    """
    mapa: dict[str, int] = {}
    for micro_id in microrregioes_ids:
        try:
            municipios = _fetch_municipios_microrregiao(micro_id)
            for mun in municipios:
                mapa[str(mun["id"])] = micro_id
        except Exception as exc:
            log.warning("Falha ao buscar municípios da microrregião %d: %s", micro_id, exc)
    return mapa


def vincular_municipios_microrregioes(
    municipios: list[dict], microrregioes: list[dict], ufs: list[str]
) -> list[dict]:
    """
    Enriquece municipios com microrregiao_id usando a API IBGE.
    Busca municípios por microrregião para cada UF solicitada.
    """
    # Coletar todos os IDs de microrregiões das UFs
    micro_ids = [m["id"] for m in microrregioes if m["uf"] in ufs]
    if not micro_ids:
        return municipios

    mapa = mapear_municipios_por_microrregiao(micro_ids)

    for mun in municipios:
        micro_id = mapa.get(mun["codigo_ibge"])
        if micro_id:
            mun["microrregiao_id"] = micro_id

    return municipios


def filtrar_por_microrregioes(
    municipios: list[dict], microrregioes_ids: list[int]
) -> list[dict]:
    """Filtra municípios que pertencem às microrregiões informadas."""
    if not microrregioes_ids:
        return municipios

    ids_set = set(microrregioes_ids)
    return [m for m in municipios if m.get("microrregiao_id") in ids_set]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from config import Config

    munis = carregar_municipios(Config.UFS, Config.POPULACAO_MAXIMA)
    log.info("Total de municípios com FPM <= 2.8: %d", len(munis))
    for uf in Config.UFS:
        count = len([m for m in munis if m["uf"] == uf])
        log.info("  %s: %d municípios", uf, count)

    # Testar microrregiões
    micros = carregar_microrregioes(["MG"])
    log.info("Microrregiões MG: %d", len(micros))
    for m in micros[:3]:
        log.info("  %s (id=%d) — %s", m["nome"], m["id"], m["mesorregiao_nome"])
