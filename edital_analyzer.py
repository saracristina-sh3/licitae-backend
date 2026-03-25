"""
Análise automática de editais — baixa PDF do PNCP, extrai texto e identifica
documentos exigidos, requisitos técnicos, prazos e cláusulas de risco.
"""

from __future__ import annotations

import io
import logging
import re
from typing import TypedDict

import requests
from pdfminer.high_level import extract_text
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config
from db import get_client

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tipagem
# ---------------------------------------------------------------------------


class PrazoExtraido(TypedDict):
    valor: int
    unidade: str
    contexto: str


class AnaliseEdital(TypedDict):
    documentos_exigidos: list[str]
    requisitos_tecnicos: list[str]
    prazos: list[PrazoExtraido]
    clausulas_risco: list[str]
    qualificacao: list[str]


class ResultadoAnalise(TypedDict):
    licitacao_id: str
    documentos_exigidos: list[str]
    requisitos_tecnicos: list[str]
    prazos: list[PrazoExtraido]
    clausulas_risco: list[str]
    qualificacao: list[str]
    url_documento: str
    paginas: int
    texto_extraido: str


# ---------------------------------------------------------------------------
# Padrões regex — compilados uma única vez no carregamento do módulo
# ---------------------------------------------------------------------------

_RE_DOCUMENTOS = [
    re.compile(p, re.IGNORECASE)
    for p in [
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
]

_RE_REQUISITOS_TECNICOS = [
    re.compile(p, re.IGNORECASE)
    for p in [
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
]

_RE_PRAZOS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"prazo\s+(?:de\s+)?(?:vig[êe]ncia|execu[çc][ãa]o|entrega|implanta[çc][ãa]o|contrato)\s*(?:[:=]|(?:de|ser[áa]\s+de))\s*(\d+)\s*(dias?|meses?|anos?|horas?)",
        r"(\d+)\s*\(\s*[\w\s]+\)\s*(dias?|meses?|anos?)\s*(?:corridos?|[úu]teis?)?(?:\s*(?:para|de)\s+[\w\s]+)?",
        r"(?:no\s+prazo\s+de|em\s+at[ée])\s*(\d+)\s*(dias?|meses?|anos?|horas?)",
    ]
]

_RE_RISCO = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"multa\s+(?:de\s+)?(?:\d+[%,]|[\w\s]+por\s+cento)\s*[^.;]{5,120}",
        r"penalidade[s]?\s*[:]\s*[^.;]{10,200}",
        r"san[çc][ãa]o|san[çc][õo]es\s+[^.;]{10,150}",
        r"rescis[ãa]o\s+(?:do\s+)?contrato\s+[^.;]{10,120}",
        r"garantia\s+(?:contratual|de\s+execu[çc][ãa]o)\s+(?:de\s+)?(?:\d+[%])\s*[^.;]{5,100}",
        r"reten[çc][ãa]o\s+(?:de\s+)?(?:pagamento|valor)\s+[^.;]{10,120}",
        r"suspens[ãa]o\s+(?:tempor[áa]ria|do\s+direito)\s+[^.;]{10,120}",
        r"impedimento\s+de\s+(?:licitar|contratar)\s+[^.;]{10,120}",
    ]
]

_RE_QUALIFICACAO = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"habilita[çc][ãa]o\s+(?:jur[íi]dica|t[ée]cnica|econ[ôo]mica)\s*[:]\s*[^.;]{10,200}",
        r"qualifica[çc][ãa]o\s+(?:t[ée]cnica|econ[ôo]mica)\s*[:]\s*[^.;]{10,200}",
        r"regularidade\s+fiscal\s+[^.;]{10,150}",
        r"capital\s+(?:social|m[íi]nimo)\s+(?:de\s+)?R?\$?\s*[\d.,]+",
        r"patrim[ôo]nio\s+l[íi]quido\s+(?:m[íi]nimo\s+)?(?:de\s+)?R?\$?\s*[\d.,]+",
        r"faturamento\s+(?:m[íi]nimo|bruto|anual)\s+[^.;]{10,120}",
        r"experi[êe]ncia\s+(?:m[íi]nima\s+)?(?:de\s+)?(?:\d+)\s*(?:anos?|meses?)\s*[^.;]{5,100}",
    ]
]

# Padrão para extrair cnpj/ano/seq da URL do edital
_RE_URL_EDITAL = re.compile(r"/editais/([^/]+)/(\d+)/(\d+)")

# Limite de caracteres do texto gravado no banco
_LIMITE_TEXTO_BANCO = 50_000

# ---------------------------------------------------------------------------
# Sessão HTTP com retry automático
# ---------------------------------------------------------------------------


def _criar_session() -> requests.Session:
    """
    Cria uma sessão requests com retry automático (3x, backoff exponencial)
    para erros de servidor (5xx) e timeout separado por fase (connect / read).
    """
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "LicitacoesSoftware/1.0"})
    return session


SESSION = _criar_session()

# ---------------------------------------------------------------------------
# Helpers de extração
# ---------------------------------------------------------------------------


def _extrair_matches(
    texto: str,
    padroes_compilados: list[re.Pattern],
    max_resultados: int = 15,
) -> list[str]:
    """
    Extrai trechos únicos que casam com qualquer um dos padrões compilados.
    Usa re.IGNORECASE já embutido nos padrões — NÃO faz lower() no texto para
    preservar acrônimos como CNPJ, FGTS, CREA, OAB.
    """
    resultados: list[str] = []
    vistos: set[str] = set()

    for padrao in padroes_compilados:
        for match in padrao.finditer(texto):
            trecho = re.sub(r"\s+", " ", match.group(0).strip())[:200]

            if len(trecho) > 10 and trecho not in vistos:
                vistos.add(trecho)
                resultados.append(trecho)
                if len(resultados) >= max_resultados:
                    return resultados

    return resultados


def _extrair_prazos(texto: str) -> list[PrazoExtraido]:
    """Extrai prazos estruturados (valor + unidade + contexto) do texto."""
    prazos: list[PrazoExtraido] = []
    vistos: set[str] = set()

    for padrao in _RE_PRAZOS:
        for match in padrao.finditer(texto):
            grupos = match.groups()
            if len(grupos) < 2:
                continue

            valor, unidade = grupos[0], grupos[1].lower().rstrip("s")
            chave = f"{valor}_{unidade}"

            if chave not in vistos:
                vistos.add(chave)
                contexto = re.sub(r"\s+", " ", match.group(0).strip())[:150]
                prazos.append(
                    PrazoExtraido(
                        valor=int(valor),
                        unidade=unidade,
                        contexto=contexto,
                    )
                )

    return prazos[:10]


def _contar_paginas(texto: str) -> int:
    """
    Aproxima o número de páginas contando form feeds (\\f) inseridos pelo pdfminer
    entre páginas. Pode não refletir a paginação real em PDFs com layout complexo.
    """
    return texto.count("\f") + 1


# ---------------------------------------------------------------------------
# Download e extração de PDF
# ---------------------------------------------------------------------------


def baixar_pdf(url: str) -> bytes | None:
    """
    Baixa um PDF de uma URL usando a sessão compartilhada com retry.
    Valida o conteúdo pelos magic bytes (%PDF) antes de retornar.
    Timeout: 5 s para conectar, 60 s para leitura (PDFs grandes).
    """
    try:
        resp = SESSION.get(url, timeout=(5, 60))
        resp.raise_for_status()
        content = resp.content
        if content[:4] != b"%PDF":
            log.debug("Conteúdo não é PDF (magic bytes inválidos): %s", url)
            return None
        return content
    except requests.RequestException as exc:
        log.warning("Erro ao baixar PDF %s — %s: %s", url, type(exc).__name__, exc)
        return None


def extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """Extrai texto de bytes de um PDF via pdfminer."""
    try:
        return extract_text(io.BytesIO(pdf_bytes))
    except Exception as exc:
        log.warning("Erro ao extrair texto do PDF — %s: %s", type(exc).__name__, exc)
        return ""


# ---------------------------------------------------------------------------
# Análise de conteúdo do edital
# ---------------------------------------------------------------------------


def analisar_edital(texto: str) -> AnaliseEdital:
    """
    Analisa o texto de um edital e retorna dados estruturados por categoria.
    Não acessa banco nem rede — função pura, facilmente testável.
    """
    return AnaliseEdital(
        documentos_exigidos=_extrair_matches(texto, _RE_DOCUMENTOS),
        requisitos_tecnicos=_extrair_matches(texto, _RE_REQUISITOS_TECNICOS),
        prazos=_extrair_prazos(texto),
        clausulas_risco=_extrair_matches(texto, _RE_RISCO),
        qualificacao=_extrair_matches(texto, _RE_QUALIFICACAO),
    )


# ---------------------------------------------------------------------------
# Camada de persistência (funções isoladas e injetáveis)
# ---------------------------------------------------------------------------


def _ja_analisada(licitacao_id: str, client) -> bool:
    """Retorna True se já existe registro de análise para a licitação."""
    try:
        resultado = (
            client.table("analise_editais")
            .select("id")
            .eq("licitacao_id", licitacao_id)
            .maybe_single()
            .execute()
        )
        return bool(resultado and resultado.data)
    except Exception as exc:
        log.warning(
            "Erro ao verificar análise existente para %s — %s: %s",
            licitacao_id,
            type(exc).__name__,
            exc,
        )
        return False


def _buscar_arquivos_pncp(cnpj: str, ano: int, seq: int) -> list[dict]:
    """Retorna a lista de arquivos de uma compra no PNCP."""
    url = f"{Config.PNCP_COMPRAS_URL}/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
    try:
        resp = SESSION.get(url, timeout=(5, 20))
        resp.raise_for_status()
        arquivos = resp.json()
        if not isinstance(arquivos, list):
            log.warning("Resposta inesperada da API PNCP (esperado list, got %s)", type(arquivos).__name__)
            return []
        return arquivos
    except requests.RequestException as exc:
        log.warning(
            "Erro ao buscar arquivos PNCP (cnpj=%s ano=%d seq=%d) — %s: %s",
            cnpj, ano, seq, type(exc).__name__, exc,
        )
        return []


def _baixar_primeiro_pdf(arquivos: list[dict]) -> tuple[bytes, str] | tuple[None, None]:
    """
    Tenta baixar o primeiro PDF válido da lista de arquivos.
    Retorna (pdf_bytes, url) ou (None, None) se nenhum funcionar.
    """
    for arq in arquivos:
        url = arq.get("url", "")
        if not url:
            continue
        pdf_bytes = baixar_pdf(url)
        if pdf_bytes:
            return pdf_bytes, url
    return None, None


def _gravar_analise(registro: ResultadoAnalise, client) -> dict | None:
    """Persiste a análise no banco via upsert. Retorna o registro gravado ou None."""
    try:
        result = (
            client.table("analise_editais")
            .upsert(registro, on_conflict="licitacao_id")
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as exc:
        log.error("Erro ao gravar análise — %s: %s", type(exc).__name__, exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Orquestração principal
# ---------------------------------------------------------------------------


def analisar_licitacao(
    licitacao_id: str,
    cnpj: str,
    ano: int,
    seq: int,
    db_client=None,
) -> dict | None:
    """
    Orquestra o pipeline completo para uma licitação:
    1. Verifica cache no banco
    2. Busca lista de arquivos no PNCP
    3. Baixa o primeiro PDF disponível
    4. Extrai e analisa o texto
    5. Persiste o resultado

    Parâmetros
    ----------
    db_client : opcional
        Client do banco de dados. Se None, usa `get_client()` do módulo db.
        Aceitar injeção facilita testes unitários sem conexão real.
    """
    client = db_client or get_client()

    if _ja_analisada(licitacao_id, client):
        log.debug("Licitação %s já analisada, pulando", licitacao_id)
        return None

    arquivos = _buscar_arquivos_pncp(cnpj, ano, seq)
    if not arquivos:
        log.warning("Sem arquivos para licitação %s", licitacao_id)
        return None

    pdf_bytes, url_documento = _baixar_primeiro_pdf(arquivos)
    if not pdf_bytes:
        log.warning(
            "Nenhum PDF baixável para licitação %s (%d URL(s) testada(s))",
            licitacao_id,
            len(arquivos),
        )
        return None

    texto = extrair_texto_pdf(pdf_bytes)
    if not texto or len(texto) < 100:
        log.warning(
            "Texto extraído muito curto para licitação %s (%d chars)",
            licitacao_id,
            len(texto) if texto else 0,
        )
        return None

    analise = analisar_edital(texto)
    paginas = _contar_paginas(texto)

    if len(texto) > _LIMITE_TEXTO_BANCO:
        log.warning(
            "Texto truncado de %d para %d chars (licitação %s)",
            len(texto),
            _LIMITE_TEXTO_BANCO,
            licitacao_id,
        )

    registro = ResultadoAnalise(
        licitacao_id=licitacao_id,
        documentos_exigidos=analise["documentos_exigidos"],
        requisitos_tecnicos=analise["requisitos_tecnicos"],
        prazos=analise["prazos"],
        clausulas_risco=analise["clausulas_risco"],
        qualificacao=analise["qualificacao"],
        url_documento=url_documento or "",
        paginas=paginas,
        texto_extraido=texto[:_LIMITE_TEXTO_BANCO],
    )

    resultado = _gravar_analise(registro, client)
    if resultado:
        log.info("Análise gravada para licitação %s (%d páginas)", licitacao_id, paginas)
    return resultado


def _buscar_licitacoes_pendentes(limite: int, client) -> list[dict]:
    """
    Retorna licitações abertas que ainda não possuem análise de edital,
    usando LEFT JOIN no banco — sem filtro em Python nem heurística de limite*2.
    """
    try:
        result = client.rpc(
            "licitacoes_sem_analise",
            {"p_limite": limite},
        ).execute()
        return result.data or []
    except Exception:
        # Fallback para ambientes sem a RPC criada: subquery via filtro
        log.debug("RPC licitacoes_sem_analise indisponível, usando fallback de duas queries")
        result = (
            client.table("licitacoes")
            .select("id, cnpj_orgao, ano_compra, seq_compra")
            .eq("proposta_aberta", True)
            .eq("fonte", "PNCP")
            .not_.is_("cnpj_orgao", "null")
            .not_.is_("ano_compra", "null")
            .not_.is_("seq_compra", "null")
            .order("relevancia", desc=False)
            .order("data_publicacao", desc=True)
            .limit(limite * 3)  # margem para descarte das já analisadas
            .execute()
        )
        licitacoes = result.data or []
        if not licitacoes:
            return []

        ids = [l["id"] for l in licitacoes]
        ja_analisadas = (
            client.table("analise_editais")
            .select("licitacao_id")
            .in_("licitacao_id", ids)
            .execute()
        )
        ids_analisados = {a["licitacao_id"] for a in (ja_analisadas.data or [])}
        return [l for l in licitacoes if l["id"] not in ids_analisados][:limite]


def analisar_licitacoes_pendentes(
    limite: int = 10,
    db_client=None,
) -> dict[str, int]:
    """
    Analisa editais de licitações abertas ainda não analisadas.

    Parâmetros
    ----------
    limite : int
        Número máximo de licitações a processar nesta execução.
    db_client : opcional
        Client do banco de dados (injetável para testes).

    Retorna
    -------
    dict com chaves "analisadas" e "erros".
    """
    client = db_client or get_client()
    pendentes = _buscar_licitacoes_pendentes(limite, client)

    if not pendentes:
        log.info("Nenhuma licitação pendente para análise")
        return {"analisadas": 0, "erros": 0}

    log.info("Analisando %d edital(is)...", len(pendentes))
    analisadas = 0
    erros = 0

    for lic in pendentes:
        licitacao_id = lic["id"]

        # Preferência: campos diretos da tabela (cnpj_orgao, ano_compra, seq_compra)
        cnpj = lic.get("cnpj_orgao")
        ano = lic.get("ano_compra")
        seq = lic.get("seq_compra")

        # Fallback: extrai da URL caso os campos não estejam presentes
        if not (cnpj and ano and seq):
            url = lic.get("url_fonte", "")
            match = _RE_URL_EDITAL.search(url)
            if not match:
                log.warning(
                    "Licitação %s sem cnpj/ano/seq e URL fora do padrão: %s",
                    licitacao_id,
                    url,
                )
                erros += 1
                continue
            cnpj, ano, seq = match.group(1), match.group(2), match.group(3)

        log.info(
            "Processando licitação %s (cnpj=%s, ano=%s, seq=%s)",
            licitacao_id, cnpj, ano, seq,
        )

        resultado = analisar_licitacao(licitacao_id, cnpj, int(ano), int(seq), db_client=client)
        if resultado:
            analisadas += 1
        else:
            log.warning("Falha ao analisar licitação %s", licitacao_id)
            erros += 1

    log.info("Análise concluída: %d analisada(s), %d erro(s)", analisadas, erros)
    return {"analisadas": analisadas, "erros": erros}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    analisar_licitacoes_pendentes()