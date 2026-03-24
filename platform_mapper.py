"""
Mapeador de plataformas PNCP — popula tabela plataformas_pncp.
Mantém cache de idUsuario → nome da plataforma.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Plataformas conhecidas (seed)
PLATAFORMAS_CONHECIDAS = [
    {"id_usuario": 3, "nome": "Compras.gov.br", "tipo": "plataforma_licitacao"},
    {"id_usuario": 5, "nome": "ECustomize Consultoria em Software S.A", "tipo": "plataforma_licitacao"},
    {"id_usuario": 10, "nome": "Portal de Compras do Estado de Minas Gerais", "tipo": "portal_estadual"},
    {"id_usuario": 12, "nome": "Bolsa Nacional De Compras - BNC", "tipo": "plataforma_licitacao"},
    {"id_usuario": 13, "nome": "Licitar Digital", "tipo": "plataforma_licitacao"},
    {"id_usuario": 14, "nome": "Portal de Compras Públicas do Estado do Rio de Janeiro", "tipo": "portal_estadual"},
    {"id_usuario": 16, "nome": "Compras Pará", "tipo": "portal_estadual"},
    {"id_usuario": 18, "nome": "Licitanet Licitações Eletrônicas LTDA", "tipo": "plataforma_licitacao"},
    {"id_usuario": 26, "nome": "Memory Projetos e Desenvolvimento de Sistemas LTDA", "tipo": "sistema_gestao"},
    {"id_usuario": 27, "nome": "HLH Assessoria e Consultoria Ltda", "tipo": "sistema_gestao"},
    {"id_usuario": 30, "nome": "Ascontech Solutions", "tipo": "sistema_gestao"},
    {"id_usuario": 32, "nome": "Central de Compras da Paraíba/PB", "tipo": "portal_estadual"},
    {"id_usuario": 40, "nome": "Licitações-E BB", "tipo": "plataforma_licitacao"},
    {"id_usuario": 41, "nome": "Elotech Gestão Pública Ltda", "tipo": "sistema_gestao"},
    {"id_usuario": 42, "nome": "4R Tecnologia da Informação Ltda", "tipo": "sistema_gestao"},
    {"id_usuario": 51, "nome": "Secretaria do Planejamento e Gestão do Ceará", "tipo": "portal_estadual"},
    {"id_usuario": 54, "nome": "Diretriz Informática Eireli", "tipo": "sistema_gestao"},
    {"id_usuario": 55, "nome": "IPM Sistemas", "tipo": "sistema_gestao"},
    {"id_usuario": 59, "nome": "IBDM Modernização Assessoria e Consultoria", "tipo": "sistema_gestao"},
    {"id_usuario": 63, "nome": "CECAM", "tipo": "sistema_gestao"},
    {"id_usuario": 67, "nome": "DBseller Serviços de Informática", "tipo": "sistema_gestao"},
    {"id_usuario": 77, "nome": "LicitaCon - TCE-RS", "tipo": "portal_estadual"},
    {"id_usuario": 80, "nome": "Elmar Tecnologia", "tipo": "sistema_gestao"},
    {"id_usuario": 82, "nome": "Governançabrasil Tecnologia e Gestão em Serviços", "tipo": "sistema_gestao"},
    {"id_usuario": 84, "nome": "Betha Sistemas", "tipo": "sistema_gestao"},
    {"id_usuario": 85, "nome": "Grupo Assessor", "tipo": "sistema_gestao"},
    {"id_usuario": 88, "nome": "M2A Tecnologia", "tipo": "sistema_gestao"},
    {"id_usuario": 89, "nome": "Licita + Brasil", "tipo": "plataforma_licitacao"},
    {"id_usuario": 90, "nome": "Novo BBMNET Licitações", "tipo": "plataforma_licitacao"},
    {"id_usuario": 91, "nome": "SEAP Paraná", "tipo": "portal_estadual"},
    {"id_usuario": 94, "nome": "Sigep - Sistemas Integrados", "tipo": "sistema_gestao"},
    {"id_usuario": 96, "nome": "BR Conectado", "tipo": "plataforma_licitacao"},
    {"id_usuario": 99, "nome": "Instituto Municipal de Administração Pública - IMAP", "tipo": "sistema_gestao"},
    {"id_usuario": 100, "nome": "Tecnosweb - Tecnologia de Gestão", "tipo": "sistema_gestao"},
    {"id_usuario": 102, "nome": "SMARAPD Informática LTDA", "tipo": "sistema_gestao"},
    {"id_usuario": 109, "nome": "STS Informática Ltda", "tipo": "sistema_gestao"},
    {"id_usuario": 120, "nome": "Lemarq Software", "tipo": "sistema_gestao"},
    {"id_usuario": 121, "nome": "SH3 Informática Ltda.", "tipo": "sistema_gestao"},
    {"id_usuario": 131, "nome": "PROCERGS", "tipo": "portal_estadual"},
    {"id_usuario": 133, "nome": "CONAM Consultoria em Administração Municipal", "tipo": "sistema_gestao"},
    {"id_usuario": 135, "nome": "Pública Tecnologia Ltda.", "tipo": "sistema_gestao"},
    {"id_usuario": 139, "nome": "EMBRAS", "tipo": "sistema_gestao"},
    {"id_usuario": 141, "nome": "Secretaria de Estado da Administração de Santa Catarina", "tipo": "portal_estadual"},
    {"id_usuario": 144, "nome": "JL Alves Gestão", "tipo": "sistema_gestao"},
    {"id_usuario": 145, "nome": "EMPRO Tecnologia e Informação", "tipo": "sistema_gestao"},
]


def popular_plataformas_conhecidas() -> int:
    """Insere/atualiza plataformas conhecidas no Supabase."""
    from db import get_client

    client = get_client()
    rows = [
        {
            "id_usuario": p["id_usuario"],
            "nome": p["nome"],
            "tipo": p["tipo"],
            "ativo": True,
        }
        for p in PLATAFORMAS_CONHECIDAS
    ]

    client.table("plataformas_pncp").upsert(
        rows, on_conflict="id_usuario"
    ).execute()
    log.info("Plataformas sincronizadas: %d", len(rows))
    return len(rows)


# Cache em memória
_plataforma_cache: dict[int, str] = {}


def get_plataforma_nome(id_usuario: int) -> str:
    """Retorna nome da plataforma com cache em memória."""
    if id_usuario in _plataforma_cache:
        return _plataforma_cache[id_usuario]

    # Tenta no seed local primeiro
    for p in PLATAFORMAS_CONHECIDAS:
        if p["id_usuario"] == id_usuario:
            _plataforma_cache[id_usuario] = p["nome"]
            return p["nome"]

    # Fallback: busca no Supabase
    try:
        from db import get_client
        client = get_client()
        result = (
            client.table("plataformas_pncp")
            .select("nome")
            .eq("id_usuario", id_usuario)
            .limit(1)
            .execute()
        )
        if result.data:
            nome = result.data[0]["nome"]
            _plataforma_cache[id_usuario] = nome
            return nome
    except Exception:
        pass

    nome = f"Plataforma #{id_usuario}"
    _plataforma_cache[id_usuario] = nome
    return nome
