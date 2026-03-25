"""
Motor de busca: cruza dados do PNCP com municípios-alvo e filtra por palavras-chave.
Aceita configuração dinâmica (BuscaConfig) ou defaults do .env.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Generator, TypedDict

from config import Config
from municipios import carregar_municipios
from pncp_client import PNCPClient
from utils import (
    TERMOS_ALTA,
    TERMOS_MEDIA,
    TERMOS_ME_EPP,
    classificar_relevancia,
    detectar_me_epp,
    match_palavras_chave,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MODALIDADE_NOMES: dict[int, str] = {
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência Eletrônica",
    5: "Concorrência Presencial",
    6: "Pregão Eletrônico",
    7: "Pregão Presencial",
    8: "Dispensa de Licitação",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
}

_ORDEM_RELEVANCIA: dict[str, int] = {"ALTA": 0, "MEDIA": 1, "BAIXA": 2}

# ---------------------------------------------------------------------------
# Tipagem do resultado
# ---------------------------------------------------------------------------


class ResultadoLicitacao(TypedDict):
    municipio: str
    uf: str
    populacao: int
    fpm: float
    codigo_ibge: str
    orgao: str
    cnpj_orgao: str
    objeto: str
    exclusivo_me_epp: bool
    modalidade: str
    valor_estimado: float
    valor_homologado: float
    situacao: str
    data_publicacao: str
    data_abertura_proposta: str
    data_encerramento_proposta: str
    url_pncp: str
    palavras_chave_encontradas: str
    relevancia: str  # "ALTA" | "MEDIA" | "BAIXA"
    fonte: str
    ano_compra: str
    seq_compra: str


# ---------------------------------------------------------------------------
# Configuração da busca
# ---------------------------------------------------------------------------


@dataclass
class BuscaConfig:
    """
    Configuração completa de uma busca.
    Todos os campos possuem defaults vindos do Config (.env).
    Use `BuscaConfig.from_dict()` para criar a partir de um dicionário externo,
    ignorando automaticamente chaves com valor None.
    """

    ufs: list[str] = field(default_factory=lambda: list(Config.UFS))
    palavras_chave: list[str] = field(default_factory=lambda: list(Config.PALAVRAS_CHAVE))
    modalidades: list[int] = field(default_factory=lambda: list(Config.MODALIDADES))
    fpm_maximo: int = field(default_factory=lambda: Config.POPULACAO_MAXIMA)
    termos_alta: list[str] = field(default_factory=lambda: list(TERMOS_ALTA))
    termos_media: list[str] = field(default_factory=lambda: list(TERMOS_MEDIA))
    termos_me_epp: list[str] = field(default_factory=lambda: list(TERMOS_ME_EPP))
    janela_dias: int = field(default_factory=lambda: getattr(Config, "JANELA_DIAS", 1))
    max_workers: int = field(default_factory=lambda: getattr(Config, "MAX_WORKERS", 8))

    @classmethod
    def from_dict(cls, d: dict) -> "BuscaConfig":
        """Cria uma BuscaConfig a partir de um dict, ignorando valores None."""
        campos_validos = {k: v for k, v in d.items() if v is not None and hasattr(cls, k)}
        return cls(**campos_validos)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _extrair_url_pncp(contratacao: dict) -> str:
    """Monta a URL pública do edital no PNCP."""
    cnpj = contratacao.get("orgaoEntidade", {}).get("cnpj", "")
    ano = contratacao.get("anoCompra", "")
    seq = contratacao.get("sequencialCompra", "")
    if cnpj and ano and seq:
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
    return ""


def _proposta_encerrada(enc_str: str | None) -> bool:
    """
    Retorna True se a data de encerramento da proposta já passou (UTC).
    Retorna False quando a string está ausente ou não pode ser interpretada.
    """
    if not enc_str:
        return False
    try:
        dt_enc = datetime.fromisoformat(enc_str.replace("Z", "+00:00"))
        return dt_enc < datetime.now(tz=timezone.utc)
    except (ValueError, TypeError):
        log.debug("Data de encerramento inválida: %r", enc_str)
        return False


def _gerar_janelas(dt_inicio: str, dt_fim: str, dias: int = 1) -> list[tuple[str, str]]:
    """
    Divide o período [dt_inicio, dt_fim] em janelas de até `dias` dias.
    Datas no formato YYYYMMDD.
    """
    inicio = datetime.strptime(dt_inicio, "%Y%m%d")
    fim = datetime.strptime(dt_fim, "%Y%m%d")
    janelas: list[tuple[str, str]] = []
    atual = inicio
    while atual <= fim:
        janela_fim = min(atual + timedelta(days=dias - 1), fim)
        janelas.append((atual.strftime("%Y%m%d"), janela_fim.strftime("%Y%m%d")))
        atual = janela_fim + timedelta(days=1)
    return janelas


def _resolver_periodo(
    dias_retroativos: int | None,
    data_inicial: str | None,
    data_final: str | None,
) -> tuple[str, str]:
    """
    Retorna (dt_inicio, dt_fim) no formato YYYYMMDD.
    Prioriza data_inicial/data_final explícitas; cai em dias_retroativos ou Config.
    """
    if data_inicial and data_final:
        return data_inicial, data_final

    dias = dias_retroativos or Config.DIAS_RETROATIVOS
    hoje = datetime.now()
    inicio = hoje - timedelta(days=dias)
    return inicio.strftime("%Y%m%d"), hoje.strftime("%Y%m%d")


def _montar_resultado(
    contratacao: dict,
    mun_info: dict,
    matches: list[str],
    cfg: BuscaConfig,
) -> ResultadoLicitacao:
    """Constrói o dict ResultadoLicitacao a partir de uma contratação bruta."""
    objeto = contratacao.get("objetoCompra", "") or ""
    orgao = contratacao.get("orgaoEntidade", {}) or {}
    info_compl = contratacao.get("informacaoComplementar", "") or ""
    texto_completo = f"{objeto} {info_compl}"

    return ResultadoLicitacao(
        municipio=mun_info["nome"],
        uf=mun_info["uf"],
        populacao=mun_info["populacao"],
        fpm=mun_info["fpm"],
        codigo_ibge=str(mun_info.get("codigo_ibge", "")),
        orgao=orgao.get("razaoSocial", ""),
        cnpj_orgao=orgao.get("cnpj", ""),
        objeto=objeto,
        exclusivo_me_epp=detectar_me_epp(texto_completo, cfg.termos_me_epp),
        modalidade=MODALIDADE_NOMES.get(
            contratacao.get("modalidadeId", 0), str(contratacao.get("modalidadeId", ""))
        ),
        valor_estimado=contratacao.get("valorTotalEstimado", 0) or 0,
        valor_homologado=contratacao.get("valorTotalHomologado", 0) or 0,
        situacao=contratacao.get("situacaoCompraNome", ""),
        data_publicacao=contratacao.get("dataPublicacaoPncp", ""),
        data_abertura_proposta=contratacao.get("dataAberturaProposta", ""),
        data_encerramento_proposta=contratacao.get("dataEncerramentoProposta", ""),
        url_pncp=_extrair_url_pncp(contratacao),
        palavras_chave_encontradas=", ".join(matches),
        relevancia=classificar_relevancia(matches, objeto, cfg.termos_alta, cfg.termos_media),
        fonte="PNCP",
        ano_compra=str(contratacao.get("anoCompra", "")),
        seq_compra=str(contratacao.get("sequencialCompra", "")),
    )


# ---------------------------------------------------------------------------
# Núcleo de busca por (UF × Modalidade)
# ---------------------------------------------------------------------------


def _buscar_uf_modalidade(
    uf: str,
    modalidade: int,
    janelas: list[tuple[str, str]],
    mapa_municipios: dict[str, dict],
    cfg: BuscaConfig,
    client: PNCPClient,
) -> list[ResultadoLicitacao]:
    """
    Busca e filtra todas as contratações de uma combinação (UF, modalidade)
    ao longo das janelas de tempo informadas.

    Projetada para execução em thread paralela.
    """
    mod_nome = MODALIDADE_NOMES.get(modalidade, str(modalidade))
    resultados: list[ResultadoLicitacao] = []
    total_contratacoes = 0

    log.info("  %s - %s: iniciando busca (%d janelas)", uf, mod_nome, len(janelas))

    for j_inicio, j_fim in janelas:
        try:
            contratacoes = client.buscar_todas_paginas(
                data_inicial=j_inicio,
                data_final=j_fim,
                modalidade=modalidade,
                uf=uf,
            )
        except Exception as exc:
            log.warning(
                "  %s - %s: falha na janela %s-%s — %s: %s",
                uf,
                mod_nome,
                j_inicio,
                j_fim,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            continue

        total_contratacoes += len(contratacoes)

        for c in contratacoes:
            if _proposta_encerrada(c.get("dataEncerramentoProposta")):
                continue

            unidade = c.get("unidadeOrgao", {}) or {}
            orgao = c.get("orgaoEntidade", {}) or {}
            codigo_mun = str(
                unidade.get("codigoIbge", "")
                or orgao.get("codigoMunicipioIbge", "")
                or ""
            )

            mun_info = mapa_municipios.get(codigo_mun)
            if not mun_info:
                continue

            objeto = c.get("objetoCompra", "") or ""
            matches = match_palavras_chave(objeto, cfg.palavras_chave)
            if not matches:
                continue

            resultados.append(_montar_resultado(c, mun_info, matches, cfg))

    log.info(
        "  %s - %s: %d relevantes de %d total",
        uf,
        mod_nome,
        len(resultados),
        total_contratacoes,
    )
    return resultados


# ---------------------------------------------------------------------------
# Gerador de contratações brutas (útil para pipelines / streaming)
# ---------------------------------------------------------------------------


def iterar_contratacoes(
    cfg: BuscaConfig,
    dt_inicio: str,
    dt_fim: str,
    client: PNCPClient,
) -> Generator[tuple[str, int, dict], None, None]:
    """
    Gera tuplas (uf, modalidade, contratacao_bruta) sem filtro.
    Útil para pipelines que precisam de acesso às contratações antes do filtro.
    """
    janelas = _gerar_janelas(dt_inicio, dt_fim, cfg.janela_dias)
    for uf in cfg.ufs:
        for modalidade in cfg.modalidades:
            for j_inicio, j_fim in janelas:
                try:
                    for c in client.buscar_todas_paginas(
                        data_inicial=j_inicio,
                        data_final=j_fim,
                        modalidade=modalidade,
                        uf=uf,
                    ):
                        yield uf, modalidade, c
                except Exception as exc:
                    log.warning(
                        "iterar_contratacoes — %s/%s janela %s-%s: %s",
                        uf,
                        modalidade,
                        j_inicio,
                        j_fim,
                        exc,
                        exc_info=True,
                    )


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------


def buscar_licitacoes(
    dias_retroativos: int | None = None,
    data_inicial: str | None = None,
    data_final: str | None = None,
    busca_config: dict | BuscaConfig | None = None,
) -> list[ResultadoLicitacao]:
    """
    Busca licitações nos municípios-alvo e retorna lista ordenada por relevância.

    Parâmetros
    ----------
    dias_retroativos : int, opcional
        Quantos dias passados incluir (ignorado se data_inicial/data_final fornecidos).
    data_inicial : str, opcional
        Data de início no formato YYYYMMDD.
    data_final : str, opcional
        Data de fim no formato YYYYMMDD.
    busca_config : dict | BuscaConfig, opcional
        Configuração da busca. Se dict, é convertido via BuscaConfig.from_dict().
        Se None, usa todos os defaults do Config (.env).

    Retorna
    -------
    list[ResultadoLicitacao]
        Lista de licitações relevantes, ordenada por relevância (ALTA → BAIXA)
        e depois por data de publicação.
    """
    # --- Resolver configuração ---
    if isinstance(busca_config, dict):
        cfg = BuscaConfig.from_dict(busca_config)
    elif isinstance(busca_config, BuscaConfig):
        cfg = busca_config
    else:
        cfg = BuscaConfig()

    # --- Resolver período ---
    dt_inicio, dt_fim = _resolver_periodo(dias_retroativos, data_inicial, data_final)
    log.info("Período de busca: %s a %s", dt_inicio, dt_fim)

    # --- Carregar municípios ---
    municipios = carregar_municipios(cfg.ufs, cfg.fpm_maximo)
    mapa_municipios: dict[str, dict] = {m["codigo_ibge"]: m for m in municipios}
    log.info(
        "Municípios-alvo: %d (%s) | Palavras-chave: %d termos",
        len(municipios),
        ", ".join(cfg.ufs),
        len(cfg.palavras_chave),
    )

    # --- Preparar janelas e tarefas ---
    janelas = _gerar_janelas(dt_inicio, dt_fim, cfg.janela_dias)
    log.info(
        "Dividido em %d janelas de até %d dia(s) | workers: %d",
        len(janelas),
        cfg.janela_dias,
        cfg.max_workers,
    )

    client = PNCPClient()
    tarefas = [
        (uf, modalidade)
        for uf in cfg.ufs
        for modalidade in cfg.modalidades
    ]

    # --- Executar em paralelo ---
    resultados: list[ResultadoLicitacao] = []

    with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
        futures = {
            executor.submit(
                _buscar_uf_modalidade,
                uf,
                modalidade,
                janelas,
                mapa_municipios,
                cfg,
                client,
            ): (uf, modalidade)
            for uf, modalidade in tarefas
        }

        for future in as_completed(futures):
            uf, modalidade = futures[future]
            try:
                parcial = future.result()
                resultados.extend(parcial)
            except Exception as exc:
                mod_nome = MODALIDADE_NOMES.get(modalidade, str(modalidade))
                log.error(
                    "Tarefa %s/%s falhou inesperadamente: %s",
                    uf,
                    mod_nome,
                    exc,
                    exc_info=True,
                )

    # --- Ordenar e retornar ---
    resultados.sort(
        key=lambda r: (_ORDEM_RELEVANCIA.get(r["relevancia"], 9), r["data_publicacao"])
    )

    log.info("Total de licitações relevantes encontradas: %d", len(resultados))
    return resultados