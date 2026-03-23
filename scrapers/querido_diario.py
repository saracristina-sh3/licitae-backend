"""
Scraper: Querido Diário (Open Knowledge Brasil)
API pública: https://api.queridodiario.ok.org.br/
Busca full-text em diários oficiais municipais.
"""

from __future__ import annotations

import logging
import time
import requests
from config import Config
from municipios import carregar_municipios
from utils import detectar_me_epp

log = logging.getLogger(__name__)

BASE_URL = "https://api.queridodiario.ok.org.br"

# Termos de busca para licitações de software
QUERIES = [
    '"licença de uso" software',
    '"permissão de uso" software',
    '"locação de software"',
    '"sistema de gestão" licitação',
    '"sistema integrado" prefeitura software',
    '"cessão de uso" software',
]


def _buscar_gazettes(
    query: str,
    state_code: str,
    data_inicio: str,
    data_fim: str,
    territory_ids: list[str] | None = None,
    size: int = 100,
) -> list[dict]:
    """Busca diários oficiais no Querido Diário."""
    params = {
        "querystring": query,
        "state_code": state_code,
        "published_since": f"{data_inicio[:4]}-{data_inicio[4:6]}-{data_inicio[6:8]}",
        "published_until": f"{data_fim[:4]}-{data_fim[4:6]}-{data_fim[6:8]}",
        "size": size,
        "offset": 0,
    }

    if territory_ids:
        params["territory_ids"] = ",".join(territory_ids)

    todos = []
    session = requests.Session()

    while True:
        try:
            resp = session.get(f"{BASE_URL}/gazettes", params=params, timeout=30)
            if resp.status_code != 200:
                break
            data = resp.json()
        except Exception:
            break

        gazettes = data.get("gazettes", [])
        if not gazettes:
            break

        todos.extend(gazettes)

        total = data.get("total_gazettes", 0)
        if len(todos) >= total or len(todos) >= 500:
            break

        params["offset"] = len(todos)
        time.sleep(0.5)

    return todos


def buscar_querido_diario(
    data_inicial: str,
    data_final: str,
) -> list[dict]:
    """
    Busca licitações de software nos diários oficiais via Querido Diário.
    Retorna no mesmo formato que search.py.
    """
    UF_STATE_CODES = {"MG": "MG", "RJ": "RJ"}

    # Municípios-alvo para filtrar resultados
    municipios = carregar_municipios(Config.UFS, Config.POPULACAO_MAXIMA)
    mapa_por_ibge = {m["codigo_ibge"]: m for m in municipios}
    codigos_alvo = set(m["codigo_ibge"] for m in municipios)

    resultados = []
    vistos = set()  # dedup por territory_id + date + trecho

    for uf in Config.UFS:
        state_code = UF_STATE_CODES.get(uf, uf)

        for query in QUERIES:
            log.info("  QD %s - '%s...'", uf, query[:30])

            gazettes = _buscar_gazettes(
                query=query,
                state_code=state_code,
                data_inicio=data_inicial,
                data_fim=data_final,
            )

            encontrados = 0

            for g in gazettes:
                territory_id = g.get("territory_id", "")

                # Filtra por municípios-alvo (FPM <= 2.8)
                if territory_id not in codigos_alvo:
                    continue

                mun = mapa_por_ibge[territory_id]
                data_pub = g.get("date", "")
                excerpts = g.get("excerpts", [])
                url_pdf = g.get("url", "")

                for excerpt in excerpts:
                    # Dedup
                    chave = f"{territory_id}:{data_pub}:{excerpt[:50]}"
                    if chave in vistos:
                        continue
                    vistos.add(chave)

                    texto_limpo = excerpt.replace("\n", " ").strip()
                    if len(texto_limpo) < 50:
                        continue

                    me_epp = detectar_me_epp(texto_limpo)
                    encontrados += 1

                    resultados.append({
                        "municipio": mun["nome"],
                        "uf": mun["uf"],
                        "populacao": mun["populacao"],
                        "fpm": mun["fpm"],
                        "codigo_ibge": territory_id,
                        "orgao": g.get("territory_name", mun["nome"]),
                        "cnpj_orgao": "",
                        "objeto": texto_limpo[:500],
                        "exclusivo_me_epp": me_epp,
                        "modalidade": "Diário Oficial",
                        "valor_estimado": 0,
                        "valor_homologado": 0,
                        "situacao": "Publicado no DO",
                        "data_publicacao": f"{data_pub}T00:00:00" if data_pub else "",
                        "data_abertura_proposta": "",
                        "data_encerramento_proposta": "",
                        "url_pncp": url_pdf,
                        "url_fonte": url_pdf,
                        "palavras_chave_encontradas": query.replace('"', ''),
                        "relevancia": "MEDIA",
                        "fonte": "QUERIDO_DIARIO",
                        "ano_compra": data_pub[:4] if data_pub else "",
                        "seq_compra": "",
                    })

            log.info("  QD %s - %d encontrados", uf, encontrados)

    return resultados
