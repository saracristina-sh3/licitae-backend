"""
Carrega configurações das organizações do Supabase para uso pelo scraper.
Fonte única: org_config + org_dominios_config.
"""

import logging
import os
from config import Config
from utils import TERMOS_ALTA, TERMOS_MEDIA, fpm_para_populacao

log = logging.getLogger(__name__)


def _supabase_disponivel() -> bool:
    return bool(os.environ.get("SUPABASE_URL")) and bool(os.environ.get("SUPABASE_SERVICE_KEY"))


def carregar_configs_org() -> list[dict]:
    """
    Carrega todas as configurações de organizações (org_config).
    Retorna lista de dicts normalizados para o scraper.
    """
    if not _supabase_disponivel():
        return [_config_padrao()]

    try:
        from db import get_client
        client = get_client()
        result = client.table("org_config").select("*").execute()
        configs = result.data or []

        if not configs:
            return [_config_padrao()]

        return [_normalizar_config(c) for c in configs]
    except Exception as e:
        log.error("Erro ao carregar org_configs: %s", e)
        return [_config_padrao()]


def unificar_configs(configs: list[dict]) -> dict:
    """
    Combina configs de todas as organizações em uma única config de busca.
    O scraper busca a união de tudo para depois filtrar por org.
    """
    ufs = set()
    palavras_chave = set()
    modalidades = set()
    fontes = set()
    termos_alta = set()
    termos_media = set()
    termos_exclusao = set()
    fpm_maximo = 0

    for c in configs:
        ufs.update(c.get("ufs", []))
        palavras_chave.update(c.get("palavras_chave", []))
        modalidades.update(c.get("modalidades", []))
        fontes.update(c.get("fontes", []))
        termos_alta.update(c.get("termos_alta", []))
        termos_media.update(c.get("termos_media", []))
        termos_exclusao.update(c.get("termos_exclusao", []))
        fpm_maximo = max(fpm_maximo, c.get("fpm_maximo", 2.8))

    # org_dominios_config — modalidades prevalecem quando configuradas
    dominios_por_org = carregar_dominios_org()
    for org_dominios in dominios_por_org.values():
        org_modalidades = org_dominios.get("modalidade_contratacao", [])
        if org_modalidades:
            modalidades.update(org_modalidades)

    return {
        "ufs": sorted(ufs),
        "palavras_chave": sorted(palavras_chave),
        "modalidades": sorted(modalidades),
        "fontes": sorted(fontes),
        "termos_alta": sorted(termos_alta),
        "termos_media": sorted(termos_media),
        "termos_exclusao": sorted(termos_exclusao),
        "fpm_maximo": fpm_maximo,
    }


def carregar_dominios_org() -> dict[str, dict[str, list[int]]]:
    """
    Carrega configurações de domínios PNCP de todas as organizações.
    Retorna dict org_id -> { dominio -> [codigos_ativos] }.
    """
    if not _supabase_disponivel():
        return {}

    try:
        from db import get_client
        client = get_client()
        result = client.table("org_dominios_config").select("org_id, dominio, codigos_ativos").execute()
        rows = result.data or []

        configs: dict[str, dict[str, list[int]]] = {}
        for row in rows:
            oid = row["org_id"]
            configs.setdefault(oid, {})[row["dominio"]] = row["codigos_ativos"] or []
        return configs
    except Exception as e:
        log.error("Erro ao carregar domínios da org: %s", e)
        return {}


def _config_padrao() -> dict:
    """Config padrão baseada no .env (usada quando não há orgs)."""
    return {
        "ufs": Config.UFS,
        "fpm_maximo": Config.POPULACAO_MAXIMA,
        "palavras_chave": Config.PALAVRAS_CHAVE,
        "modalidades": Config.MODALIDADES,
        "fontes": ["PNCP", "QUERIDO_DIARIO", "TCE_RJ"],
        "termos_alta": TERMOS_ALTA,
        "termos_media": TERMOS_MEDIA,
        "termos_exclusao": [],
    }


def _normalizar_config(c: dict) -> dict:
    """Garante que todos os campos existem."""
    padrao = _config_padrao()
    return {
        "ufs": c.get("ufs") or padrao["ufs"],
        "fpm_maximo": fpm_para_populacao(c.get("fpm_maximo", 2.8)),
        "palavras_chave": c.get("palavras_chave") or padrao["palavras_chave"],
        "modalidades": c.get("modalidades") or padrao["modalidades"],
        "fontes": c.get("fontes") or padrao["fontes"],
        "termos_alta": c.get("termos_alta") or padrao["termos_alta"],
        "termos_media": c.get("termos_media") or padrao["termos_media"],
        "termos_exclusao": c.get("termos_exclusao") or [],
    }
