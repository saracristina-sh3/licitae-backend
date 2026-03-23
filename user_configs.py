"""
Carrega configurações dos usuários do Supabase para uso pelo scraper.
Quando não há usuários configurados, usa os defaults do .env.
"""

import logging
import os
from config import Config
from utils import TERMOS_ALTA, TERMOS_MEDIA, TERMOS_ME_EPP, fpm_para_populacao

log = logging.getLogger(__name__)


def _supabase_disponivel() -> bool:
    return bool(os.environ.get("SUPABASE_URL")) and bool(os.environ.get("SUPABASE_SERVICE_KEY"))


def carregar_configs_usuarios() -> list[dict]:
    """
    Carrega todas as configurações de usuários do Supabase.
    Retorna lista de dicts com: ufs, fpm_maximo, palavras_chave, modalidades,
    fontes, termos_alta, termos_media, termos_me_epp.
    """
    if not _supabase_disponivel():
        return [_config_padrao()]

    try:
        from db import get_client
        client = get_client()
        result = client.table("user_config").select("*").execute()
        configs = result.data or []

        if not configs:
            return [_config_padrao()]

        return [_normalizar_config(c) for c in configs]
    except Exception as e:
        log.error("Erro ao carregar configs de usuários: %s", e)
        return [_config_padrao()]


def unificar_configs(configs: list[dict]) -> dict:
    """
    Combina todas as configs de usuários em uma única config de busca.
    Usa a união de todos os termos/UFs para buscar tudo de uma vez.
    """
    ufs = set()
    palavras_chave = set()
    modalidades = set()
    fontes = set()
    termos_alta = set()
    termos_media = set()
    termos_me_epp = set()
    fpm_maximo = 0

    for c in configs:
        ufs.update(c.get("ufs", []))
        palavras_chave.update(c.get("palavras_chave", []))
        modalidades.update(c.get("modalidades", []))
        fontes.update(c.get("fontes", []))
        termos_alta.update(c.get("termos_alta", []))
        termos_media.update(c.get("termos_media", []))
        termos_me_epp.update(c.get("termos_me_epp", []))
        fpm_maximo = max(fpm_maximo, c.get("fpm_maximo", 2.8))

    return {
        "ufs": sorted(ufs),
        "palavras_chave": sorted(palavras_chave),
        "modalidades": sorted(modalidades),
        "fontes": sorted(fontes),
        "termos_alta": sorted(termos_alta),
        "termos_media": sorted(termos_media),
        "termos_me_epp": sorted(termos_me_epp),
        "fpm_maximo": fpm_maximo,
    }


def _config_padrao() -> dict:
    """Config padrão baseada no .env."""
    return {
        "ufs": Config.UFS,
        "fpm_maximo": Config.POPULACAO_MAXIMA,
        "palavras_chave": Config.PALAVRAS_CHAVE,
        "modalidades": Config.MODALIDADES,
        "fontes": ["PNCP", "QUERIDO_DIARIO", "TCE_RJ"],
        "termos_alta": TERMOS_ALTA,
        "termos_media": TERMOS_MEDIA,
        "termos_me_epp": TERMOS_ME_EPP,
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
        "termos_me_epp": c.get("termos_me_epp") or padrao["termos_me_epp"],
    }


