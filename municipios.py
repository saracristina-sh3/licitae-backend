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


def _fetch_municipios_completo(uf_code: str) -> list[dict]:
    """Busca municípios com microrregião em uma única chamada IBGE."""
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf_code}/municipios"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    resultado = []
    for m in resp.json():
        micro = m.get("microrregiao", {}) or {}
        meso = micro.get("mesorregiao", {}) or {}
        resultado.append({
            "id": str(m["id"]),
            "nome": m["nome"],
            "microrregiao_id": micro.get("id"),
            "microrregiao_nome": micro.get("nome", ""),
            "mesorregiao_id": meso.get("id"),
            "mesorregiao_nome": meso.get("nome", ""),
        })
    return resultado


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

        log.info("  %s: buscando municípios e população...", uf)

        municipios_ibge = _fetch_municipios_completo(uf_code)
        populacoes = _fetch_populacao_em_lote(uf_code)

        count = 0
        for mun in municipios_ibge:
            codigo = mun["id"]
            pop = populacoes.get(codigo, 999999)
            fpm = fpm_coeficiente(pop)
            todos.append({
                "codigo_ibge": codigo,
                "nome": mun["nome"],
                "uf": uf,
                "populacao": pop,
                "fpm": fpm,
                "microrregiao_id": mun["microrregiao_id"],
            })
            if pop <= populacao_maxima:
                count += 1

        log.info("  %s: %d municípios com FPM <= 2.8 (de %d total)", uf, count, len(municipios_ibge))

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


def carregar_microrregioes(ufs: list[str]) -> list[dict]:
    """
    Extrai microrregiões dos dados de municípios já carregados.
    Usa o cache de municípios como fonte (sem chamadas extras à API).
    """
    # Carrega municípios do cache (já contém microrregiao_id)
    if not os.path.exists(CACHE_FILE):
        log.warning("Cache de municípios não existe. Rode carregar_municipios() primeiro.")
        return []

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        municipios = json.load(f)

    # Extrai microrregiões únicas
    vistos: dict[int, dict] = {}
    for mun in municipios:
        if mun.get("uf") not in ufs:
            continue
        micro_id = mun.get("microrregiao_id")
        if not micro_id or micro_id in vistos:
            continue

        # Precisamos do nome da microrregião — buscar da API IBGE (1 chamada por UF)
        vistos[micro_id] = {
            "id": micro_id,
            "nome": "",  # preenchido abaixo
            "mesorregiao_id": 0,
            "mesorregiao_nome": "",
            "uf": mun["uf"],
        }

    # Buscar nomes de microrregiões (1 chamada por UF)
    for uf in ufs:
        uf_code = UF_CODES.get(uf)
        if not uf_code:
            continue
        try:
            url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf_code}/microrregioes"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            for micro in resp.json():
                mid = micro["id"]
                if mid in vistos:
                    meso = micro.get("mesorregiao", {}) or {}
                    vistos[mid]["nome"] = micro["nome"]
                    vistos[mid]["mesorregiao_id"] = meso.get("id", 0)
                    vistos[mid]["mesorregiao_nome"] = meso.get("nome", "")
        except Exception as exc:
            log.warning("Falha ao buscar microrregiões de %s: %s", uf, exc)

    resultado = list(vistos.values())
    log.info("Microrregiões carregadas: %d (UFs: %s)", len(resultado), ", ".join(ufs))
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from config import Config

    # Limpar cache para forçar recarga
    for f in [CACHE_FILE, CACHE_MICRORREGIOES_FILE]:
        if os.path.exists(f):
            os.remove(f)

    munis = carregar_municipios(Config.UFS, Config.POPULACAO_MAXIMA)
    log.info("Total de municípios com FPM <= 2.8: %d", len(munis))

    # Verificar microrregiao_id
    com_micro = len([m for m in munis if m.get("microrregiao_id")])
    log.info("Com microrregiao_id: %d / %d", com_micro, len(munis))

    for uf in Config.UFS:
        count = len([m for m in munis if m["uf"] == uf])
        log.info("  %s: %d municípios", uf, count)

    # Testar microrregiões
    micros = carregar_microrregioes(Config.UFS)
    log.info("Microrregiões: %d", len(micros))
    for m in micros[:5]:
        log.info("  %s (id=%d) — %s/%s", m["nome"], m["id"], m["mesorregiao_nome"], m["uf"])
