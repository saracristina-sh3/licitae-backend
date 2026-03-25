"""
Persistência dos resultados da análise de editais.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict

from edital_analysis.constants import LIMITE_TEXTO_BANCO, VERSAO_ALGORITMO, METODO_EXTRACAO
from edital_analysis.types import ResultadoAnalise

log = logging.getLogger(__name__)

_RE_URL_EDITAL = re.compile(r"/editais/([^/]+)/(\d+)/(\d+)")


def ja_analisada(client, licitacao_id: str) -> bool:
    """Verifica se a licitação já tem análise."""
    try:
        result = (
            client.table("analise_editais")
            .select("id")
            .eq("licitacao_id", licitacao_id)
            .maybe_single()
            .execute()
        )
        return bool(result and result.data)
    except Exception as exc:
        log.warning("Erro ao verificar análise para %s: %s", licitacao_id, exc)
        return False


def buscar_arquivos_pncp(session, base_url: str, cnpj: str, ano: int, seq: int) -> list[dict]:
    """Busca lista de arquivos de uma compra no PNCP."""
    url = f"{base_url}/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
    try:
        resp = session.get(url, timeout=(5, 20))
        resp.raise_for_status()
        arquivos = resp.json()
        if not isinstance(arquivos, list):
            log.warning("Resposta PNCP inesperada (esperado list)")
            return []
        return arquivos
    except Exception as exc:
        log.warning("Erro ao buscar arquivos PNCP: %s", exc)
        return []


def gravar_analise(client, resultado: ResultadoAnalise) -> dict | None:
    """
    Grava resultado da análise no banco.
    Mantém campos legados (text[]) para compat. com frontend v1.
    """
    registro = {
        "licitacao_id": resultado.licitacao_id,
        # Campos legados (text[]) — compat. frontend v1
        "documentos_exigidos": [a.trecho for a in resultado.documentos],
        "requisitos_tecnicos": [a.trecho for a in resultado.requisitos],
        "clausulas_risco": [a.trecho for a in resultado.riscos],
        "qualificacao": [a.trecho for a in resultado.qualificacao],
        "prazos": [{"valor": p.valor, "unidade": p.unidade, "contexto": p.contexto} for p in resultado.prazos],
        # Metadados
        "url_documento": resultado.url_documento,
        "paginas": resultado.paginas,
        "texto_extraido": resultado.texto_extraido[:LIMITE_TEXTO_BANCO],
        # Novos: achados estruturados (JSONB)
        "documentos_estruturados": [asdict(a) for a in resultado.documentos],
        "requisitos_estruturados": [asdict(a) for a in resultado.requisitos],
        "riscos_estruturados": [asdict(a) for a in resultado.riscos],
        "qualificacao_estruturada": [asdict(a) for a in resultado.qualificacao],
        "prazos_classificados": [asdict(p) for p in resultado.prazos],
        # Arquivo
        "arquivo_escolhido": resultado.arquivo.titulo if resultado.arquivo else None,
        "score_arquivo": resultado.arquivo.score if resultado.arquivo else None,
        "motivo_arquivo": ", ".join(resultado.arquivo.motivos[:3]) if resultado.arquivo else None,
        # Qualidade
        "qualidade_extracao": resultado.qualidade_extracao.score if resultado.qualidade_extracao else None,
        "faixa_qualidade": resultado.qualidade_extracao.faixa if resultado.qualidade_extracao else None,
        # Confiança
        "score_confianca": resultado.confianca.score if resultado.confianca else None,
        "faixa_confianca": resultado.confianca.faixa if resultado.confianca else None,
        # Risco
        "score_risco": resultado.risco.score if resultado.risco else None,
        "nivel_risco": resultado.risco.nivel if resultado.risco else None,
        "fatores_risco": resultado.risco.fatores if resultado.risco else [],
        # Auditoria
        "versao_algoritmo": VERSAO_ALGORITMO,
        "metodo_extracao": METODO_EXTRACAO,
        "tempo_processamento_ms": resultado.tempo_ms,
        "houve_fallback": resultado.houve_fallback,
    }

    try:
        result = (
            client.table("analise_editais")
            .upsert(registro, on_conflict="licitacao_id")
            .execute()
        )
        return result.data[0] if result.data else registro
    except Exception as exc:
        log.error("Erro ao gravar análise: %s", exc, exc_info=True)
        return None


def buscar_licitacoes_pendentes(client, limite: int) -> list[dict]:
    """Busca licitações abertas sem análise de edital."""
    try:
        result = client.rpc("licitacoes_sem_analise", {"p_limite": limite}).execute()
        return result.data or []
    except Exception:
        log.debug("RPC indisponível, usando fallback")
        result = (
            client.table("licitacoes")
            .select("id, cnpj_orgao, url_fonte")
            .eq("proposta_aberta", True)
            .eq("fonte", "PNCP")
            .not_.is_("cnpj_orgao", "null")
            .not_.is_("url_fonte", "null")
            .order("relevancia", desc=False)
            .order("data_publicacao", desc=True)
            .limit(limite * 3)
            .execute()
        )
        licitacoes = result.data or []
        if not licitacoes:
            return []

        ids = [l["id"] for l in licitacoes]
        ja = client.table("analise_editais").select("licitacao_id").in_("licitacao_id", ids).execute()
        ids_ja = {a["licitacao_id"] for a in (ja.data or [])}
        return [l for l in licitacoes if l["id"] not in ids_ja][:limite]


def extrair_cnpj_ano_seq(licitacao: dict) -> tuple[str, int, int] | None:
    """Extrai cnpj, ano e seq da licitação (campo direto ou URL)."""
    cnpj = licitacao.get("cnpj_orgao")
    ano = licitacao.get("ano_compra")
    seq = licitacao.get("seq_compra")

    if cnpj and ano and seq:
        return cnpj, int(ano), int(seq)

    url = licitacao.get("url_fonte", "")
    match = _RE_URL_EDITAL.search(url)
    if match:
        return match.group(1), int(match.group(2)), int(match.group(3))

    return None
