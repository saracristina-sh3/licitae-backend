"""
MCP Server principal do Licitaê.

Expõe dados de licitações do Supabase como tools para análise por IA.
Substitui heurísticas de regex/stopwords por análise semântica.

Uso:
    python -m mcp_server.server                    # stdio (local)
    python -m mcp_server.server --transport sse    # SSE (VPS remoto)
"""

from __future__ import annotations

import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from mcp_server.config import (
    MCP_SERVER_NAME,
    MCP_SERVER_PORT,
    LIMITE_BUSCA_PADRAO,
    LIMITE_BUSCA_MAXIMO,
    LIMITE_ITENS_PADRAO,
    LIMITE_ITENS_MAXIMO,
)

log = logging.getLogger(__name__)

mcp = FastMCP(MCP_SERVER_NAME)


# ── Supabase client ──────────────────────────────────────────────

def _get_supabase_client():
    """Importa e retorna o cliente Supabase (lazy)."""
    parent = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    from db import get_client
    return get_client()


# ═════════════════════════════════════════════════════════════════
#  TOOLS — Licitações
# ═════════════════════════════════════════════════════════════════

@mcp.tool()
async def buscar_licitacoes(
    busca_texto: str = "",
    uf: str = "",
    modalidade: str = "",
    relevancia: str = "",
    proposta_aberta: bool | None = None,
    exclusivo_me_epp: bool | None = None,
    valor_min: float | None = None,
    valor_max: float | None = None,
    palavra_chave: str = "",
    ordenar_por: str = "relevancia",
    limite: int = LIMITE_BUSCA_PADRAO,
) -> str:
    """Busca licitações com filtros flexíveis.

    Retorna lista de licitações com: id, objeto, município, UF, modalidade,
    valor estimado, relevância, data de publicação, situação e palavras-chave.
    Use para encontrar oportunidades de licitação por texto, região ou critérios.
    """
    client = _get_supabase_client()
    limite = min(limite, LIMITE_BUSCA_MAXIMO)

    query = (
        client.table("licitacoes")
        .select(
            "id, objeto, municipio_nome, uf, modalidade, valor_estimado, "
            "relevancia, data_publicacao, data_abertura_proposta, "
            "data_encerramento_proposta, situacao, proposta_aberta, "
            "exclusivo_me_epp, palavras_chave, orgao, url_fonte"
        )
    )

    if uf:
        query = query.eq("uf", uf.upper())
    if modalidade:
        query = query.eq("modalidade", modalidade)
    if relevancia:
        query = query.eq("relevancia", relevancia.upper())
    if proposta_aberta is not None:
        query = query.eq("proposta_aberta", proposta_aberta)
    if exclusivo_me_epp is not None:
        query = query.eq("exclusivo_me_epp", exclusivo_me_epp)
    if valor_min is not None:
        query = query.gte("valor_estimado", valor_min)
    if valor_max is not None:
        query = query.lte("valor_estimado", valor_max)

    if ordenar_por == "data_publicacao":
        query = query.order("data_publicacao", desc=True)
    elif ordenar_por == "valor_estimado":
        query = query.order("valor_estimado", desc=True)
    elif ordenar_por == "municipio_nome":
        query = query.order("municipio_nome")
    else:
        query = query.order("relevancia").order("data_publicacao", desc=True)

    query = query.limit(limite)

    if busca_texto:
        query = query.text_search("objeto", busca_texto, config="portuguese")

    result = query.execute()
    licitacoes = result.data or []

    if palavra_chave and licitacoes:
        pc_lower = palavra_chave.lower()
        licitacoes = [
            l for l in licitacoes
            if any(pc_lower in (p or "").lower() for p in (l.get("palavras_chave") or []))
        ]

    return json.dumps({
        "total": len(licitacoes),
        "licitacoes": licitacoes,
    }, ensure_ascii=False, default=str)


@mcp.tool()
async def detalhar_licitacao(licitacao_id: str) -> str:
    """Retorna todos os detalhes de uma licitação específica.

    Inclui: dados da licitação, análise do edital (se disponível),
    preços de referência (se calculados) e itens de contratação.
    Use para obter visão completa de uma oportunidade antes de analisar.
    """
    client = _get_supabase_client()

    lic = (
        client.table("licitacoes").select("*")
        .eq("id", licitacao_id).limit(1).execute()
    )
    if not lic.data:
        return json.dumps({"erro": "Licitação não encontrada"}, ensure_ascii=False)

    edital = (
        client.table("analise_editais").select("*")
        .eq("licitacao_id", licitacao_id).limit(1).execute()
    )
    precos = (
        client.table("preco_referencia_licitacao").select("*")
        .eq("licitacao_id", licitacao_id).limit(1).execute()
    )
    # Itens: busca via hash_dedup da licitação
    itens_data = []
    hash_dedup = lic.data[0].get("hash_dedup")
    if hash_dedup:
        itens = (
            client.table("itens_contratacao")
            .select(
                "descricao, unidade_medida, quantidade, valor_unitario_estimado, "
                "valor_total_estimado, ncm_nbs_codigo, "
                "resultados_item(valor_unitario_homologado, nome_fornecedor, percentual_desconto)"
            )
            .eq("licitacao_hash", hash_dedup).order("numero_item").limit(100).execute()
        )
        itens_data = itens.data or []

    return json.dumps({
        "licitacao": lic.data[0],
        "analise_edital": edital.data[0] if edital.data else None,
        "precos_referencia": precos.data[0] if precos.data else None,
        "itens": itens_data,
    }, ensure_ascii=False, default=str)


@mcp.tool()
async def buscar_estatisticas_dashboard(uf: str = "") -> str:
    """Métricas gerais para dashboard: total abertas, por relevância, por UF, valor total.

    Use para ter visão geral do mercado de licitações.
    """
    client = _get_supabase_client()

    query_total = (
        client.table("licitacoes").select("id", count="exact")
        .eq("proposta_aberta", True)
    )
    if uf:
        query_total = query_total.eq("uf", uf.upper())
    total_result = query_total.execute()
    total_abertas = total_result.count or 0

    query_dados = (
        client.table("licitacoes")
        .select("relevancia, uf, valor_estimado")
        .eq("proposta_aberta", True)
    )
    if uf:
        query_dados = query_dados.eq("uf", uf.upper())
    dados = query_dados.limit(5000).execute()
    rows = dados.data or []

    por_relevancia = {"ALTA": 0, "MEDIA": 0, "BAIXA": 0}
    por_uf: dict[str, int] = {}
    valor_total = 0.0

    for r in rows:
        rel = r.get("relevancia", "BAIXA")
        por_relevancia[rel] = por_relevancia.get(rel, 0) + 1
        u = r.get("uf", "??")
        por_uf[u] = por_uf.get(u, 0) + 1
        valor_total += float(r.get("valor_estimado") or 0)

    return json.dumps({
        "total_abertas": total_abertas,
        "por_relevancia": por_relevancia,
        "por_uf": dict(sorted(por_uf.items(), key=lambda x: -x[1])),
        "valor_total_estimado": round(valor_total, 2),
    }, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════
#  TOOLS — Itens de contratação
# ═════════════════════════════════════════════════════════════════

@mcp.tool()
async def buscar_itens_contratacao(
    descricao: str = "",
    plataforma_id: int | None = None,
    uf: str = "",
    ncm: str = "",
    valor_min: float | None = None,
    valor_max: float | None = None,
    limite: int = LIMITE_ITENS_PADRAO,
) -> str:
    """Busca itens de contratação com filtros.

    Retorna itens com: descrição, unidade, valores estimados e homologados,
    plataforma, NCM, município e fornecedor vencedor.
    Use para comparar preços de itens específicos entre plataformas e regiões.
    """
    client = _get_supabase_client()
    limite = min(limite, LIMITE_ITENS_MAXIMO)

    query = (
        client.table("itens_contratacao")
        .select(
            "id, descricao, unidade_medida, quantidade, "
            "valor_unitario_estimado, valor_total_estimado, "
            "ncm_nbs_codigo, plataforma_id, plataforma_nome, "
            "municipio, uf, "
            "resultados_item(valor_unitario_homologado, nome_fornecedor, "
            "percentual_desconto, cnpj_fornecedor)"
        )
    )

    if uf:
        query = query.eq("uf", uf.upper())
    if plataforma_id is not None:
        query = query.eq("plataforma_id", plataforma_id)
    if ncm:
        query = query.eq("ncm_nbs_codigo", ncm)
    if valor_min is not None:
        query = query.gte("valor_unitario_estimado", valor_min)
    if valor_max is not None:
        query = query.lte("valor_unitario_estimado", valor_max)

    query = query.order("valor_unitario_estimado").limit(limite)

    if descricao:
        query = query.text_search("descricao", descricao, config="portuguese")

    result = query.execute()
    return json.dumps({
        "total": len(result.data or []),
        "itens": result.data or [],
    }, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════
#  TOOLS — Preços de referência
# ═════════════════════════════════════════════════════════════════

@mcp.tool()
async def consultar_precos_referencia(licitacao_id: str) -> str:
    """Consulta preços de referência calculados para uma licitação.

    Retorna: resumo estatístico (média, mediana, min/max, percentis, CV),
    separação por fonte (homologados vs estimados), score de confiabilidade (0-100),
    licitações similares, itens similares e resumo por plataforma.
    """
    client = _get_supabase_client()

    resumo = (
        client.table("preco_referencia_licitacao").select("*")
        .eq("licitacao_id", licitacao_id).limit(1).execute()
    )
    if not resumo.data:
        return json.dumps({
            "calculado": False,
            "mensagem": "Preço de referência ainda não calculado para esta licitação.",
        }, ensure_ascii=False)

    ref = resumo.data[0]
    ref_id = ref["id"]

    detalhes_lic = (
        client.table("preco_referencia_detalhe").select("*")
        .eq("preco_referencia_id", ref_id)
        .order("score_similaridade", desc=True).limit(50).execute()
    )
    detalhes_itens = (
        client.table("preco_referencia_itens").select("*")
        .eq("preco_referencia_id", ref_id)
        .order("score_similaridade", desc=True).limit(100).execute()
    )
    plataformas = (
        client.table("preco_referencia_plataformas").select("*")
        .eq("preco_referencia_id", ref_id)
        .order("total_itens", desc=True).execute()
    )

    return json.dumps({
        "calculado": True,
        "resumo": ref,
        "licitacoes_similares": detalhes_lic.data or [],
        "itens_similares": detalhes_itens.data or [],
        "plataformas": plataformas.data or [],
    }, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════
#  TOOLS — Comparativo de mercado
# ═════════════════════════════════════════════════════════════════

@mcp.tool()
async def consultar_comparativo_mercado(uf: str = "") -> str:
    """Retorna comparativo de mercado entre plataformas de licitação.

    Plataformas: SH3, BLL (BNC), Licitar Digital, Licitanet,
    Compras.gov.br, ECustomize, BBNet.
    Inclui ranking por vitórias, economia e itens comparáveis.
    """
    client = _get_supabase_client()

    query_plat = client.table("comparativo_plataformas").select("*")
    if uf:
        query_plat = query_plat.eq("uf", uf.upper())
    plat_result = query_plat.order("calculado_em", desc=True).limit(50).execute()

    query_itens = client.table("comparativo_itens").select("*")
    if uf:
        query_itens = query_itens.eq("uf", uf.upper())
    itens_result = query_itens.order("calculado_em", desc=True).limit(200).execute()

    return json.dumps({
        "total_plataformas": len(plat_result.data or []),
        "total_itens_comparaveis": len(itens_result.data or []),
        "plataformas": plat_result.data or [],
        "itens": itens_result.data or [],
    }, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════
#  TOOLS — Editais e análise
# ═════════════════════════════════════════════════════════════════

@mcp.tool()
async def analisar_edital(licitacao_id: str) -> str:
    """Busca e retorna dados do edital de uma licitação para análise pela IA.

    Retorna texto extraído do PDF, achados estruturados (documentos, prazos,
    garantias, penalidades), score de risco e confiança da extração.
    A IA pode analisar o texto e responder perguntas sobre o edital.
    """
    client = _get_supabase_client()

    analise = (
        client.table("analise_editais").select("*")
        .eq("licitacao_id", licitacao_id).limit(1).execute()
    )

    if not analise.data:
        lic = (
            client.table("licitacoes").select("id, objeto, url_fonte")
            .eq("id", licitacao_id).limit(1).execute()
        )
        if not lic.data:
            return json.dumps({"erro": "Licitação não encontrada"}, ensure_ascii=False)
        return json.dumps({
            "analisado": False,
            "licitacao": lic.data[0],
            "mensagem": "Edital ainda não foi analisado.",
        }, ensure_ascii=False)

    lic = (
        client.table("licitacoes")
        .select("objeto, municipio_nome, uf, modalidade, valor_estimado, orgao")
        .eq("id", licitacao_id).limit(1).execute()
    )

    return json.dumps({
        "analisado": True,
        "licitacao": lic.data[0] if lic.data else None,
        "edital": analise.data[0],
    }, ensure_ascii=False, default=str)


@mcp.tool()
async def comparar_itens_similares(
    descricao: str,
    uf: str = "",
    limite: int = 100,
) -> str:
    """Retorna itens similares entre plataformas para agrupamento semântico pela IA.

    A IA deve agrupar os itens semanticamente (ex: "filtro de óleo" = "elemento
    filtrante óleo") e comparar preços — substituindo regex/stopwords.
    Retorna itens de todas as plataformas com preços e fornecedores.
    """
    client = _get_supabase_client()
    limite = min(limite, 500)

    query = (
        client.table("itens_contratacao")
        .select(
            "descricao, unidade_medida, quantidade, "
            "valor_unitario_estimado, ncm_nbs_codigo, "
            "plataforma_id, plataforma_nome, municipio, uf, "
            "resultados_item(valor_unitario_homologado, nome_fornecedor, "
            "percentual_desconto, cnpj_fornecedor)"
        )
    )
    if uf:
        query = query.eq("uf", uf.upper())

    query = query.order("valor_unitario_estimado").limit(limite)
    query = query.text_search("descricao", descricao, config="portuguese")

    result = query.execute()
    itens = result.data or []

    por_plataforma: dict[str, list] = {}
    for item in itens:
        plat = item.get("plataforma_nome") or "Desconhecida"
        por_plataforma.setdefault(plat, []).append(item)

    return json.dumps({
        "descricao_buscada": descricao,
        "total_itens": len(itens),
        "plataformas_encontradas": list(por_plataforma.keys()),
        "por_plataforma": por_plataforma,
        "itens": itens,
    }, ensure_ascii=False, default=str)


@mcp.tool()
async def avaliar_oportunidade(licitacao_id: str) -> str:
    """Retorna dados completos de uma licitação para avaliação pela IA.

    Consolida TODOS os dados: licitação, edital, preços de referência,
    itens de contratação e comparativo de mercado na UF.
    A IA avalia se vale participar baseado no perfil da organização.
    """
    client = _get_supabase_client()

    lic = (
        client.table("licitacoes").select("*")
        .eq("id", licitacao_id).limit(1).execute()
    )
    if not lic.data:
        return json.dumps({"erro": "Licitação não encontrada"}, ensure_ascii=False)

    licitacao = lic.data[0]

    edital = (
        client.table("analise_editais").select("*")
        .eq("licitacao_id", licitacao_id).limit(1).execute()
    )
    preco_ref = (
        client.table("preco_referencia_licitacao").select("*")
        .eq("licitacao_id", licitacao_id).limit(1).execute()
    )
    # Itens via hash_dedup
    itens_data = []
    hash_dedup = licitacao.get("hash_dedup")
    if hash_dedup:
        itens = (
            client.table("itens_contratacao")
            .select(
                "descricao, unidade_medida, quantidade, valor_unitario_estimado, "
                "valor_total_estimado, ncm_nbs_codigo, "
                "resultados_item(valor_unitario_homologado, nome_fornecedor, percentual_desconto)"
            )
            .eq("licitacao_hash", hash_dedup).order("numero_item").limit(100).execute()
        )
        itens_data = itens.data or []

    comparativo = None
    uf_lic = licitacao.get("uf")
    if uf_lic:
        comp = (
            client.table("comparativo_plataformas").select("*")
            .eq("uf", uf_lic).order("calculado_em", desc=True).limit(20).execute()
        )
        comparativo = comp.data or None

    return json.dumps({
        "licitacao": licitacao,
        "analise_edital": edital.data[0] if edital.data else None,
        "precos_referencia": preco_ref.data[0] if preco_ref.data else None,
        "itens": itens_data,
        "comparativo_plataformas": comparativo,
    }, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════
#  TOOLS — Organização e fornecedor
# ═════════════════════════════════════════════════════════════════

@mcp.tool()
async def listar_config_organizacao(org_id: str = "") -> str:
    """Retorna configuração da organização: termos de exclusão, UFs, palavras-chave.

    Use para entender o perfil e filtros da organização ao avaliar licitações.
    """
    client = _get_supabase_client()

    query_config = client.table("org_config").select("*")
    if org_id:
        query_config = query_config.eq("org_id", org_id)
    config_result = query_config.limit(10).execute()

    return json.dumps({
        "configs": config_result.data or [],
    }, ensure_ascii=False, default=str)


@mcp.tool()
async def consultar_fornecedor(cnpj_fornecedor: str) -> str:
    """Histórico de um fornecedor nas licitações monitoradas.

    Retorna: vitórias, valores homologados, plataformas, UFs e itens vencidos.
    Use para avaliar a competitividade de um fornecedor específico.
    """
    client = _get_supabase_client()

    resultados = (
        client.table("resultados_item")
        .select(
            "valor_unitario_homologado, percentual_desconto, "
            "nome_fornecedor, cnpj_fornecedor, "
            "item:itens_contratacao("
            "  descricao, unidade_medida, valor_unitario_estimado, "
            "  plataforma_nome, plataforma_id, municipio, uf"
            ")"
        )
        .eq("cnpj_fornecedor", cnpj_fornecedor)
        .order("valor_unitario_homologado", desc=True)
        .limit(200).execute()
    )

    rows = resultados.data or []
    if not rows:
        return json.dumps({
            "encontrado": False,
            "mensagem": f"Nenhum resultado para CNPJ {cnpj_fornecedor}",
        }, ensure_ascii=False)

    nome = rows[0].get("nome_fornecedor", "")
    plataformas: set[str] = set()
    ufs: set[str] = set()
    total_valor = 0.0

    for r in rows:
        item = r.get("item") or {}
        plataformas.add(item.get("plataforma_nome") or "")
        ufs.add(item.get("uf") or "")
        total_valor += float(r.get("valor_unitario_homologado") or 0)

    plataformas.discard("")
    ufs.discard("")

    return json.dumps({
        "encontrado": True,
        "cnpj": cnpj_fornecedor,
        "nome": nome,
        "total_vitorias": len(rows),
        "valor_total_homologado": round(total_valor, 2),
        "plataformas": sorted(plataformas),
        "ufs": sorted(ufs),
        "itens": rows[:50],
    }, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════
#  TOOLS — PNCP direto
# ═════════════════════════════════════════════════════════════════

@mcp.tool()
async def consultar_pncp_direto(
    cnpj_orgao: str,
    ano_compra: int,
    sequencial_compra: int,
) -> str:
    """Consulta direta à API do PNCP para dados que não estão no banco.

    Busca detalhes de uma contratação pelo CNPJ do órgão, ano e sequencial.
    Retorna dados brutos da contratação + itens + resultados.
    """
    parent = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    from pncp_client import PNCPClient

    pncp = PNCPClient()

    detalhes = pncp.buscar_contratacao_detalhes(
        cnpj=cnpj_orgao, ano=ano_compra, sequencial=sequencial_compra,
    )
    if not detalhes:
        return json.dumps({
            "encontrado": False,
            "mensagem": f"Contratação não encontrada: {cnpj_orgao}/{ano_compra}/{sequencial_compra}",
        }, ensure_ascii=False)

    itens = pncp.buscar_itens(cnpj=cnpj_orgao, ano=ano_compra, sequencial=sequencial_compra)

    resultados_amostra = []
    if itens:
        numero_item = itens[0].get("numeroItem", 1)
        resultados_amostra = pncp.buscar_resultados_item(
            cnpj=cnpj_orgao, ano=ano_compra, sequencial=sequencial_compra,
            numero_item=numero_item,
        )

    return json.dumps({
        "encontrado": True,
        "contratacao": detalhes,
        "itens": itens,
        "resultados_amostra": resultados_amostra,
    }, ensure_ascii=False, default=str)


# ═════════════════════════════════════════════════════════════════
#  TOOLS — Comparação customizada por sessão
# ═════════════════════════════════════════════════════════════════

@mcp.tool()
async def executar_comparacao_sessao(sessao_id: str) -> str:
    """Executa comparação de preços dos itens selecionados em uma sessão.

    Agrupa itens por NCM/descrição, calcula estatísticas por grupo,
    e gera visão por item e por edital. Persiste resultados.
    """
    client = _get_supabase_client()

    from comparison_session.services.session_comparison import comparar_itens_sessao
    resultado = comparar_itens_sessao(client, sessao_id)

    return json.dumps(resultado, ensure_ascii=False, default=str)


@mcp.tool()
async def analisar_comparacao_sessao(sessao_id: str) -> str:
    """Analisa resultados de comparação de uma sessão usando IA.

    Carrega os resultados por item e por edital, monta um prompt
    estruturado e gera insights: melhor preço, fornecedores,
    riscos e estratégia de preço sugerida.
    """
    client = _get_supabase_client()

    from comparison_session.services.session_persistence import (
        carregar_resultado,
        gravar_resultado,
    )

    por_item = carregar_resultado(client, sessao_id, "por_item")
    por_edital = carregar_resultado(client, sessao_id, "por_edital")

    if not por_item and not por_edital:
        return json.dumps({
            "error": "Nenhum resultado encontrado. Execute a comparação primeiro.",
        }, ensure_ascii=False)

    # Montar prompt para IA
    prompt = _montar_prompt_analise(por_item, por_edital)

    # Chamar IA (usa o mesmo provider da análise de licitações)
    try:
        from ia_analysis.services.analise import _detectar_provider, _chamar_anthropic, _chamar_gemini
        from ia_analysis.constants import SYSTEM_PROMPT

        provider, api_key, modelo = _detectar_provider()

        prompt_completo = (
            "Analise os comparativos abaixo e retorne um JSON com os campos: "
            '"resumo" (string), "por_item" (array de {descricao, recomendacao, melhor_preco, fornecedor, risco}), '
            '"por_edital" (array de {objeto, analise, oportunidade, risco}), '
            '"estrategia" (string). Responda APENAS JSON válido.\n\n'
            + prompt
        )

        if provider == "anthropic":
            texto_resposta, _, _ = _chamar_anthropic(api_key, modelo, prompt_completo)
        else:
            texto_resposta, _, _ = _chamar_gemini(api_key, modelo, prompt_completo)

        # Parse JSON da resposta
        texto_limpo = texto_resposta.strip()
        if texto_limpo.startswith("```"):
            linhas = texto_limpo.split("\n")
            linhas = [l for l in linhas if not l.strip().startswith("```")]
            texto_limpo = "\n".join(linhas)

        analise = json.loads(texto_limpo)

    except (ImportError, RuntimeError) as e:
        log.warning("IA indisponível: %s — usando análise local", e)
        analise = _gerar_analise_fallback(por_item, por_edital)
    except (json.JSONDecodeError, KeyError) as e:
        log.error("Erro ao parsear resposta IA: %s", e)
        analise = _gerar_analise_fallback(por_item, por_edital)
    gravar_resultado(client, sessao_id, "analise_ia", analise)

    # Atualizar fase da sessão
    client.table("sessoes_comparacao") \
        .update({"fase": "analise"}) \
        .eq("id", sessao_id) \
        .execute()

    return json.dumps(analise, ensure_ascii=False, default=str)


def _gerar_analise_fallback(por_item: list | None, por_edital: list | None) -> dict:
    """Gera análise básica quando a IA não está disponível."""
    itens = por_item or []
    editais = por_edital or []

    resumo_parts = [f"Análise de {len(editais)} edital(is) com {len(itens)} grupo(s) de itens."]

    multi_plat = [g for g in itens if len(g.get("plataformas", [])) >= 2]
    if multi_plat:
        resumo_parts.append(f"{len(multi_plat)} grupo(s) com preços em 2+ plataformas.")

    economias = [e.get("economia") for e in editais if e.get("economia") is not None and e["economia"] > 0]
    if economias:
        media = sum(economias) / len(economias)
        resumo_parts.append(f"Economia média: {media:.1f}%.")

    analise_itens = []
    for g in itens[:15]:
        plats = g.get("plataformas", [])
        item_analise: dict = {"descricao": g.get("descricao", "Item")}
        if plats:
            menor = plats[0] if isinstance(plats, list) else {}
            item_analise["melhor_preco"] = menor.get("valor_medio", 0)
            item_analise["fornecedor"] = menor.get("plataforma_nome", "")
            if len(plats) >= 2:
                diff = ((plats[-1].get("valor_medio", 0) - plats[0].get("valor_medio", 0)) /
                        max(plats[0].get("valor_medio", 1), 1)) * 100
                item_analise["recomendacao"] = (
                    f"Diferença de {diff:.0f}% entre plataformas."
                    if diff > 10 else "Preços convergentes."
                )
            else:
                item_analise["recomendacao"] = "Referência única."
        analise_itens.append(item_analise)

    analise_editais = []
    for e in editais:
        eco = e.get("economia")
        analise_editais.append({
            "objeto": str(e.get("objeto", ""))[:100],
            "analise": f"Economia de {eco:.1f}%." if eco and eco > 0 else "Sem dados de homologação.",
            "oportunidade": "Boa margem para proposta competitiva." if eco and eco > 15 else None,
            "risco": "Valor homologado acima do estimado." if eco and eco < 0 else None,
        })

    return {
        "resumo": " ".join(resumo_parts),
        "por_item": analise_itens,
        "por_edital": analise_editais,
        "estrategia": "Utilizar o menor preço por plataforma como base de referência.",
    }


def _montar_prompt_analise(por_item: list | None, por_edital: list | None) -> str:
    """Monta prompt estruturado para análise IA dos comparativos."""
    partes = [
        "Analise os seguintes comparativos de preços de licitações e forneça insights em JSON.",
        "",
        "Retorne um JSON com os campos:",
        '- "resumo": string com resumo executivo (2-3 parágrafos)',
        '- "por_item": array de objetos com {descricao, recomendacao, melhor_preco, fornecedor, risco}',
        '- "por_edital": array de objetos com {objeto, analise, oportunidade, risco}',
        '- "estrategia": string com estratégia de preço sugerida',
        "",
    ]

    if por_item:
        partes.append("## Comparativo por Item")
        for grupo in por_item[:30]:  # Limitar para não estourar tokens
            desc = grupo.get("descricao", "?")
            partes.append(f"\n### {desc}")
            partes.append(f"NCM: {grupo.get('ncm', 'N/A')} | Unidade: {grupo.get('unidade_predominante', '?')}")
            for plat in grupo.get("plataformas", []):
                nome = plat.get("plataforma_nome", "?")
                valor = plat.get("valor_medio", 0)
                eco = plat.get("economia_media")
                eco_str = f" (economia {eco}%)" if eco else ""
                partes.append(f"  - {nome}: R$ {valor:.2f}{eco_str}")

    if por_edital:
        partes.append("\n## Comparativo por Edital")
        for edital in por_edital[:20]:
            obj = edital.get("objeto", "?")
            mun = edital.get("municipio", "?")
            est = edital.get("valor_estimado", 0)
            hom = edital.get("valor_homologado", 0)
            eco = edital.get("economia")
            partes.append(f"\n### {obj}")
            partes.append(f"Local: {mun} | Itens: {edital.get('total_itens', 0)}")
            partes.append(f"Estimado: R$ {est:.2f} | Homologado: R$ {hom:.2f}")
            if eco is not None:
                partes.append(f"Economia: {eco}%")

    return "\n".join(partes)


# ═════════════════════════════════════════════════════════════════
#  Entry point
# ═════════════════════════════════════════════════════════════════

async def _run_sse_with_auth(port: int) -> None:
    """Roda SSE com middleware de autenticação via MCP_AUTH_TOKEN."""
    import os
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from mcp.server.sse import SseServerTransport

    auth_token = os.environ.get("MCP_AUTH_TOKEN", "")
    if not auth_token:
        log.warning("MCP_AUTH_TOKEN não definido — endpoint SSE sem proteção!")

    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            if auth_token:
                header = request.headers.get("Authorization", "")
                if header != f"Bearer {auth_token}":
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp._mcp_server.run(
                streams[0], streams[1],
                mcp._mcp_server.create_initialization_options(),
            )

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    async def health(request):
        return JSONResponse({"status": "ok", "server": MCP_SERVER_NAME})

    async def handle_analise_ia(request):
        """Endpoint REST para análise IA sob demanda."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "JSON inválido"}, status_code=400)

        licitacao_id = body.get("licitacao_id")
        if not licitacao_id:
            return JSONResponse({"error": "licitacao_id é obrigatório"}, status_code=400)

        tipo = body.get("tipo", "completa")
        if tipo not in ("completa", "edital"):
            return JSONResponse({"error": "tipo deve ser 'completa' ou 'edital'"}, status_code=400)

        try:
            client = _get_supabase_client()
            from ia_analysis.services.analise import analisar
            resultado = analisar(client, licitacao_id, tipo=tipo)
            return JSONResponse({
                "ok": True,
                "analise": resultado["analise"],
                "metadados": {
                    "modelo": resultado["modelo_usado"],
                    "tokens_input": resultado["tokens_input"],
                    "tokens_output": resultado["tokens_output"],
                    "custo_usd": resultado["custo_usd"],
                    "tempo_ms": resultado["tempo_ms"],
                },
            })
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        except Exception as e:
            log.error("Erro na análise IA: %s", e, exc_info=True)
            return JSONResponse({"error": "Erro interno na análise"}, status_code=500)

    async def handle_comparacao_sessao(request):
        """Endpoint REST para comparação customizada por sessão."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "JSON inválido"}, status_code=400)

        sessao_id = body.get("sessao_id")
        if not sessao_id:
            return JSONResponse({"error": "sessao_id é obrigatório"}, status_code=400)

        try:
            client = _get_supabase_client()
            from comparison_session.services.session_comparison import comparar_itens_sessao
            resultado = comparar_itens_sessao(client, sessao_id)
            return JSONResponse({"ok": True, **resultado})
        except Exception as e:
            log.error("Erro na comparação de sessão: %s", e, exc_info=True)
            return JSONResponse({"error": "Erro interno na comparação"}, status_code=500)

    LIMITE_ANALISES_MES = 10

    async def handle_analise_sessao(request):
        """Endpoint REST para análise IA de sessão."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "JSON inválido"}, status_code=400)

        sessao_id = body.get("sessao_id")
        if not sessao_id:
            return JSONResponse({"error": "sessao_id é obrigatório"}, status_code=400)

        try:
            # Verificar limite mensal
            client = _get_supabase_client()
            from datetime import datetime
            inicio_mes = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            contagem = client.table("sessao_resultados").select(
                "*", count="exact", head=True
            ).eq("tipo", "analise_ia").gte("created_at", inicio_mes).execute()

            if (contagem.count or 0) >= LIMITE_ANALISES_MES:
                return JSONResponse(
                    {"error": f"Limite de {LIMITE_ANALISES_MES} análises IA por mês atingido."},
                    status_code=429,
                )

            resultado = await analisar_comparacao_sessao(sessao_id)
            return JSONResponse(json.loads(resultado))
        except Exception as e:
            log.error("Erro na análise IA de sessão: %s", e, exc_info=True)
            return JSONResponse({"error": "Erro interno na análise"}, status_code=500)

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
            Route("/api/analise-ia", endpoint=handle_analise_ia, methods=["POST"]),
            Route("/api/comparacao-sessao", endpoint=handle_comparacao_sessao, methods=["POST"]),
            Route("/api/analise-sessao", endpoint=handle_analise_sessao, methods=["POST"]),
        ],
        middleware=[Middleware(AuthMiddleware)],
    )

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MCP Server do Licitaê")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="Transporte: stdio (local) ou sse (remoto). Padrão: stdio",
    )
    parser.add_argument(
        "--port", type=int, default=MCP_SERVER_PORT,
        help=f"Porta para SSE (padrão: {MCP_SERVER_PORT})",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.transport == "sse":
        import asyncio
        asyncio.run(_run_sse_with_auth(args.port))
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
