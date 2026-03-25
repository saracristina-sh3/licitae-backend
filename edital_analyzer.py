"""
Análise automática de editais — baixa PDF do PNCP, extrai texto e identifica
documentos exigidos, requisitos técnicos, prazos e cláusulas de risco.
"""

from __future__ import annotations

import io
import logging
import re

import requests
from pdfminer.high_level import extract_text

from config import Config

log = logging.getLogger(__name__)

# ── Padrões de extração ──────────────────────────────────────

PADROES_DOCUMENTOS = [
    r"certid[ãa]o\s+(?:negativa\s+)?(?:de\s+)?[\w\s]+(?:federal|estadual|municipal|trabalhista|FGTS|INSS)",
    r"atestado\s+de\s+capacidade\s+t[ée]cnica",
    r"contrato\s+social|ato\s+constitutivo",
    r"balan[çc]o\s+patrimonial",
    r"certid[ãa]o\s+(?:simplificada\s+)?(?:da\s+)?junta\s+comercial",
    r"comprovante\s+de\s+inscri[çc][ãa]o\s+(?:no\s+)?CNPJ",
    r"alvar[áa]\s+de\s+funcionamento",
    r"declara[çc][ãa]o\s+(?:de\s+)?(?:que\s+)?(?:n[ãa]o\s+)?(?:emprega|utiliza)\s+(?:menor|trabalho\s+infantil)",
    r"declara[çc][ãa]o\s+de\s+idoneidade",
    r"declara[çc][ãa]o\s+de\s+inexist[êe]ncia\s+de\s+fatos?\s+impeditivos?",
    r"registro\s+(?:no\s+)?(?:conselho|CRA|CRC|CREA|CAU|OAB)",
    r"certid[ãa]o\s+de\s+(?:regularidade|d[ée]bitos?)\s+(?:fiscal|tribut[áa]ria)",
    r"prova\s+de\s+regularidade\s+(?:fiscal|para\s+com)",
    r"garantia\s+(?:de\s+)?proposta|cau[çc][ãa]o",
]

PADROES_REQUISITOS_TECNICOS = [
    r"(?:dever[áa]|deve)\s+(?:possuir|apresentar|comprovar|demonstrar|dispor\s+de)\s+[^.;]{10,120}",
    r"requisito[s]?\s+t[ée]cnico[s]?\s*[:]\s*[^.;]{10,200}",
    r"especifica[çc][ãa]o\s+t[ée]cnica[s]?\s*[:]\s*[^.;]{10,200}",
    r"(?:sistema|software|solu[çc][ãa]o)\s+(?:deve|dever[áa])\s+[^.;]{10,150}",
    r"funcionalidade[s]?\s+(?:m[íi]nima[s]?|obrigat[óo]ria[s]?)\s*[:]\s*[^.;]{10,200}",
    r"m[óo]dulo[s]?\s+(?:de|do|da)\s+[\w\s]+(?:deve|dever[áa]|com)\s+[^.;]{10,150}",
    r"integra[çc][ãa]o\s+(?:com|ao|entre)\s+[^.;]{10,120}",
    r"migra[çc][ãa]o\s+(?:de\s+)?dados?\s+[^.;]{10,120}",
    r"treinamento|capacita[çc][ãa]o\s+[^.;]{10,120}",
    r"suporte\s+t[ée]cnico\s+[^.;]{10,120}",
]

PADROES_PRAZOS = [
    r"prazo\s+(?:de\s+)?(?:vig[êe]ncia|execu[çc][ãa]o|entrega|implanta[çc][ãa]o|contrato)\s*(?:[:=]|(?:de|ser[áa]\s+de))\s*(\d+)\s*(dias?|meses?|anos?|horas?)",
    r"(\d+)\s*\(\s*[\w\s]+\)\s*(dias?|meses?|anos?)\s*(?:corridos?|[úu]teis?)?(?:\s*(?:para|de)\s+[\w\s]+)?",
    r"(?:no\s+prazo\s+de|em\s+at[ée])\s*(\d+)\s*(dias?|meses?|anos?|horas?)",
]

PADROES_RISCO = [
    r"multa\s+(?:de\s+)?(?:\d+[%,]|[\w\s]+por\s+cento)\s*[^.;]{5,120}",
    r"penalidade[s]?\s*[:]\s*[^.;]{10,200}",
    r"san[çc][ãa]o|san[çc][õo]es\s+[^.;]{10,150}",
    r"rescis[ãa]o\s+(?:do\s+)?contrato\s+[^.;]{10,120}",
    r"garantia\s+(?:contratual|de\s+execu[çc][ãa]o)\s+(?:de\s+)?(?:\d+[%])\s*[^.;]{5,100}",
    r"reten[çc][ãa]o\s+(?:de\s+)?(?:pagamento|valor)\s+[^.;]{10,120}",
    r"suspens[ãa]o\s+(?:tempor[áa]ria|do\s+direito)\s+[^.;]{10,120}",
    r"impedimento\s+de\s+(?:licitar|contratar)\s+[^.;]{10,120}",
]

PADROES_QUALIFICACAO = [
    r"habilita[çc][ãa]o\s+(?:jur[íi]dica|t[ée]cnica|econ[ôo]mica)\s*[:]\s*[^.;]{10,200}",
    r"qualifica[çc][ãa]o\s+(?:t[ée]cnica|econ[ôo]mica)\s*[:]\s*[^.;]{10,200}",
    r"regularidade\s+fiscal\s+[^.;]{10,150}",
    r"capital\s+(?:social|m[íi]nimo)\s+(?:de\s+)?R?\$?\s*[\d.,]+",
    r"patrim[ôo]nio\s+l[íi]quido\s+(?:m[íi]nimo\s+)?(?:de\s+)?R?\$?\s*[\d.,]+",
    r"faturamento\s+(?:m[íi]nimo|bruto|anual)\s+[^.;]{10,120}",
    r"experi[êe]ncia\s+(?:m[íi]nima\s+)?(?:de\s+)?(?:\d+)\s*(?:anos?|meses?)\s*[^.;]{5,100}",
]


def baixar_pdf(url: str) -> bytes | None:
    """Baixa PDF de uma URL."""
    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "LicitacoesSoftware/1.0",
        })
        resp.raise_for_status()
        if "pdf" not in resp.headers.get("content-type", "").lower() and not url.endswith(".pdf"):
            log.debug("URL não é PDF: %s", url)
            return None
        return resp.content
    except Exception as e:
        log.warning("Erro ao baixar PDF %s: %s", url, e)
        return None


def extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrai texto de um PDF."""
    try:
        return extract_text(io.BytesIO(pdf_bytes))
    except Exception as e:
        log.warning("Erro ao extrair texto do PDF: %s", e)
        return ""


def _extrair_matches(texto: str, padroes: list[str], max_resultados: int = 15) -> list[str]:
    """Extrai matches únicos de uma lista de padrões regex."""
    resultados = []
    texto_lower = texto.lower()
    vistos = set()

    for padrao in padroes:
        for match in re.finditer(padrao, texto_lower, re.IGNORECASE):
            trecho = match.group(0).strip()
            # Normaliza e limpa
            trecho = re.sub(r"\s+", " ", trecho)
            trecho = trecho[:200]

            if trecho not in vistos and len(trecho) > 10:
                vistos.add(trecho)
                resultados.append(trecho)
                if len(resultados) >= max_resultados:
                    return resultados

    return resultados


def _extrair_prazos(texto: str) -> list[dict]:
    """Extrai prazos estruturados do texto."""
    prazos = []
    vistos = set()

    for padrao in PADROES_PRAZOS:
        for match in re.finditer(padrao, texto, re.IGNORECASE):
            grupos = match.groups()
            if len(grupos) >= 2:
                valor = grupos[0]
                unidade = grupos[1].lower().rstrip("s")
                chave = f"{valor}_{unidade}"

                if chave not in vistos:
                    vistos.add(chave)
                    contexto = match.group(0).strip()
                    contexto = re.sub(r"\s+", " ", contexto)[:150]
                    prazos.append({
                        "valor": int(valor),
                        "unidade": unidade,
                        "contexto": contexto,
                    })

    return prazos[:10]


def analisar_edital(texto: str) -> dict:
    """Analisa texto do edital e retorna dados estruturados."""
    return {
        "documentos_exigidos": _extrair_matches(texto, PADROES_DOCUMENTOS),
        "requisitos_tecnicos": _extrair_matches(texto, PADROES_REQUISITOS_TECNICOS),
        "prazos": _extrair_prazos(texto),
        "clausulas_risco": _extrair_matches(texto, PADROES_RISCO),
        "qualificacao": _extrair_matches(texto, PADROES_QUALIFICACAO),
    }


def analisar_licitacao(licitacao_id: str, cnpj: str, ano: int, seq: int) -> dict | None:
    """
    Busca documentos do PNCP, baixa o edital PDF, extrai texto e analisa.
    Grava resultado na tabela analise_editais.
    """
    from db import get_client

    client = get_client()

    # Verifica se já foi analisado
    try:
        existing = client.table("analise_editais").select("id").eq(
            "licitacao_id", licitacao_id
        ).maybe_single().execute()
        if existing and existing.data:
            log.debug("Licitação %s já analisada, pulando", licitacao_id)
            return existing.data
    except Exception:
        pass  # Tabela pode não existir ainda

    # Busca lista de documentos no PNCP
    try:
        resp = requests.get(
            f"{Config.PNCP_COMPRAS_URL}/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos",
            timeout=20,
            headers={"User-Agent": "LicitacoesSoftware/1.0"},
        )
        resp.raise_for_status()
        arquivos = resp.json()
    except Exception as e:
        log.warning("Erro ao buscar arquivos PNCP para %s: %s", licitacao_id, e)
        return None

    if not isinstance(arquivos, list) or not arquivos:
        log.debug("Sem arquivos para licitação %s", licitacao_id)
        return None

    # Busca o edital (primeiro PDF disponível)
    url_documento = None
    pdf_bytes = None

    for arq in arquivos:
        url = arq.get("url", "")
        if url:
            pdf_bytes = baixar_pdf(url)
            if pdf_bytes:
                url_documento = url
                break

    if not pdf_bytes:
        log.debug("Nenhum PDF baixável para licitação %s", licitacao_id)
        return None

    # Extrai texto
    texto = extrair_texto_pdf(pdf_bytes)
    if not texto or len(texto) < 100:
        log.debug("Texto extraído muito curto para licitação %s", licitacao_id)
        return None

    # Analisa
    analise = analisar_edital(texto)

    # Conta páginas (aproximação)
    paginas = texto.count("\f") + 1

    # Grava no Supabase
    registro = {
        "licitacao_id": licitacao_id,
        "documentos_exigidos": analise["documentos_exigidos"],
        "requisitos_tecnicos": analise["requisitos_tecnicos"],
        "prazos": analise["prazos"],
        "clausulas_risco": analise["clausulas_risco"],
        "qualificacao": analise["qualificacao"],
        "url_documento": url_documento,
        "paginas": paginas,
        "texto_extraido": texto[:50000],  # Limita a 50k chars
    }

    try:
        result = client.table("analise_editais").upsert(
            registro, on_conflict="licitacao_id"
        ).execute()
        log.info("Análise gravada para licitação %s (%d páginas)", licitacao_id, paginas)
        return result.data[0] if result.data else None
    except Exception as e:
        log.error("Erro ao gravar análise: %s", e)
        return None


def analisar_licitacoes_pendentes(limite: int = 10):
    """Analisa editais de licitações que ainda não foram analisadas."""
    from db import get_client

    client = get_client()

    # Busca licitações abertas sem análise
    result = client.table("licitacoes").select(
        "id, cnpj_orgao, url_fonte"
    ).eq(
        "proposta_aberta", True
    ).eq(
        "fonte", "PNCP"
    ).not_.is_(
        "cnpj_orgao", "null"
    ).not_.is_(
        "url_fonte", "null"
    ).order(
        "relevancia", desc=False
    ).order(
        "data_publicacao", desc=True
    ).limit(limite * 2).execute()

    licitacoes = result.data or []

    if not licitacoes:
        log.info("Nenhuma licitação pendente para análise")
        return {"analisadas": 0, "erros": 0}

    # Filtra as que já têm análise
    lic_ids = [l["id"] for l in licitacoes]
    ja_analisadas = client.table("analise_editais").select(
        "licitacao_id"
    ).in_("licitacao_id", lic_ids).execute()

    ids_analisados = {a["licitacao_id"] for a in (ja_analisadas.data or [])}
    pendentes = [l for l in licitacoes if l["id"] not in ids_analisados][:limite]

    log.info("Analisando %d editais...", len(pendentes))

    analisadas = 0
    erros = 0

    for lic in pendentes:
        url = lic.get("url_fonte", "")
        match = re.search(r"/editais/([^/]+)/(\d+)/(\d+)", url)
        if not match:
            continue

        cnpj, ano, seq = match.group(1), int(match.group(2)), int(match.group(3))

        resultado = analisar_licitacao(lic["id"], cnpj, ano, seq)
        if resultado:
            analisadas += 1
        else:
            erros += 1

    log.info("Análise concluída: %d analisadas, %d erros", analisadas, erros)
    return {"analisadas": analisadas, "erros": erros}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    analisar_licitacoes_pendentes()
