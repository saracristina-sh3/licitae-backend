"""
Scraper: TCE-RJ Dados Abertos
API: https://dados.tcerj.tc.br/api/v1/
Cobertura: Todos os municípios do RJ.
"""

import logging
import requests
from config import Config
from municipios import carregar_municipios
from utils import match_palavras_chave, classificar_relevancia

log = logging.getLogger(__name__)

BASE_URL = "https://dados.tcerj.tc.br/api/v1"

PALAVRAS_CHAVE_SOFTWARE = [
    "software", "sistema", "licença de uso", "licenca de uso",
    "permissão de uso", "permissao de uso", "locação de software",
    "locacao de software", "cessão de uso", "cessao de uso",
    "sistema integrado", "sistema de gestão", "sistema de gestao",
    "solução tecnológica", "solucao tecnologica",
    "informática", "informatica", "tecnologia da informação",
    "email", "e-mail", "e-mails institucionais", "hospedagem de e-mails",
    "hospedagem de email",
]


def _buscar_licitacoes_municipio(municipio_nome: str, ano: int) -> list[dict]:
    """Busca licitações de um município no TCE-RJ."""
    try:
        resp = requests.get(
            f"{BASE_URL}/licitacoes",
            params={"ano": ano, "municipio": municipio_nome, "inicio": 0, "limite": 500},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("Licitacoes", [])
    except Exception:
        return []


def buscar_tcerj(
    data_inicial: str,
    data_final: str,
) -> list[dict]:
    """
    Busca licitações de software nos municípios do RJ via TCE-RJ.
    Retorna no mesmo formato que search.py.
    """
    if "RJ" not in Config.UFS:
        return []

    municipios = carregar_municipios(["RJ"], Config.POPULACAO_MAXIMA)
    if not municipios:
        return []

    ano = int(data_inicial[:4])
    resultados = []
    vistos = set()

    log.info("  TCE-RJ: %d municípios, ano %d", len(municipios), ano)

    for mun in municipios:
        nome_busca = mun["nome"].upper()
        licitacoes = _buscar_licitacoes_municipio(nome_busca, ano)

        for lic in licitacoes:
            objeto = lic.get("Objeto", "") or ""
            matches = match_palavras_chave(objeto, PALAVRAS_CHAVE_SOFTWARE)
            if not matches:
                continue

            # Dedup por edital
            edital = lic.get("NumeroEdital", "")
            chave = f"TCERJ:{nome_busca}:{edital}:{ano}"
            if chave in vistos:
                continue
            vistos.add(chave)

            relevancia = classificar_relevancia(matches, objeto)
            data_pub = lic.get("DataPublicacaoEdital", "") or lic.get("DataPublicacaoOficial", "")

            resultados.append({
                "municipio": mun["nome"],
                "uf": "RJ",
                "populacao": mun["populacao"],
                "fpm": mun["fpm"],
                "codigo_ibge": mun["codigo_ibge"],
                "orgao": lic.get("Unidade", ""),
                "cnpj_orgao": "",
                "objeto": objeto,
                "exclusivo_me_epp": False,
                "modalidade": lic.get("Modalidade", ""),
                "valor_estimado": lic.get("ValorEstimado", 0) or 0,
                "valor_homologado": 0,
                "situacao": "Homologada" if lic.get("DataHomologacao") else "Publicada",
                "data_publicacao": f"{data_pub}T00:00:00" if data_pub else "",
                "data_abertura_proposta": "",
                "data_encerramento_proposta": "",
                "url_pncp": "",
                "url_fonte": "",
                "palavras_chave_encontradas": ", ".join(matches[:3]),
                "relevancia": relevancia,
                "fonte": "TCE_RJ",
                "ano_compra": str(ano),
                "seq_compra": edital,
            })

    log.info("  TCE-RJ: %d relevantes", len(resultados))
    return resultados
