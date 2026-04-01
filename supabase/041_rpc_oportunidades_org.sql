-- ============================================================
-- RPC: buscar oportunidades da organização do usuário.
-- Lê de oportunidades_org JOIN licitacoes (score/relevância per-org).
-- ============================================================

CREATE OR REPLACE FUNCTION buscar_oportunidades_org_filtradas(
    p_ufs TEXT[] DEFAULT NULL,
    p_relevancia TEXT DEFAULT NULL,
    p_proposta_aberta BOOLEAN DEFAULT NULL,
    p_busca TEXT DEFAULT NULL,
    p_modalidade_id INTEGER DEFAULT NULL,
    p_modo_disputa_id INTEGER DEFAULT NULL,
    p_situacao_compra_id INTEGER DEFAULT NULL,
    p_ordenar_por TEXT DEFAULT 'score',
    p_limite INT DEFAULT 20,
    p_offset INT DEFAULT 0
)
RETURNS JSON
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_org_id UUID;
    v_count INT;
    v_result JSON;
BEGIN
    -- 1. Busca org do usuário
    SELECT p.org_id INTO v_org_id
    FROM profiles p WHERE p.id = auth.uid();

    IF v_org_id IS NULL THEN
        RETURN json_build_object('data', '[]'::json, 'count', 0);
    END IF;

    -- 2. Count
    SELECT count(*) INTO v_count
    FROM oportunidades_org o
    JOIN licitacoes l ON l.id = o.licitacao_id
    WHERE o.org_id = v_org_id
        AND (p_ufs IS NULL OR l.uf = ANY(p_ufs))
        AND (p_relevancia IS NULL OR o.relevancia = p_relevancia)
        AND (p_proposta_aberta IS NULL OR l.proposta_aberta = p_proposta_aberta)
        AND (p_busca IS NULL OR p_busca = '' OR l.objeto ILIKE '%' || p_busca || '%')
        AND (p_modalidade_id IS NULL OR l.modalidade_id = p_modalidade_id)
        AND (p_modo_disputa_id IS NULL OR l.modo_disputa_id = p_modo_disputa_id)
        AND (p_situacao_compra_id IS NULL OR l.situacao_compra_id = p_situacao_compra_id);

    -- 3. Busca paginada
    SELECT json_agg(t) INTO v_result
    FROM (
        SELECT
            l.id,
            l.hash_dedup,
            l.municipio_nome,
            l.uf,
            l.orgao,
            l.cnpj_orgao,
            l.objeto,
            l.modalidade,
            l.modalidade_id,
            l.modo_disputa_id,
            l.situacao_compra_id,
            l.valor_estimado,
            l.valor_homologado,
            l.situacao,
            l.data_publicacao,
            l.data_abertura_proposta,
            l.data_encerramento_proposta,
            l.fonte,
            l.url_fonte,
            l.proposta_aberta,
            l.exclusivo_me_epp,
            l.created_at,
            l.informacao_complementar,
            l.itens_coletados,
            l.dados_brutos,
            -- Campos per-org (de oportunidades_org)
            o.score,
            o.relevancia,
            o.urgencia,
            o.palavras_chave_encontradas AS palavras_chave,
            o.campos_matched,
            o.itens_matched,
            o.total_itens,
            o.itens_relevantes,
            o.valor_itens_relevantes
        FROM oportunidades_org o
        JOIN licitacoes l ON l.id = o.licitacao_id
        WHERE o.org_id = v_org_id
            AND (p_ufs IS NULL OR l.uf = ANY(p_ufs))
            AND (p_relevancia IS NULL OR o.relevancia = p_relevancia)
            AND (p_proposta_aberta IS NULL OR l.proposta_aberta = p_proposta_aberta)
            AND (p_busca IS NULL OR p_busca = '' OR l.objeto ILIKE '%' || p_busca || '%')
            AND (p_modalidade_id IS NULL OR l.modalidade_id = p_modalidade_id)
            AND (p_modo_disputa_id IS NULL OR l.modo_disputa_id = p_modo_disputa_id)
            AND (p_situacao_compra_id IS NULL OR l.situacao_compra_id = p_situacao_compra_id)
        ORDER BY
            CASE WHEN p_ordenar_por = 'data_publicacao' THEN l.data_publicacao END DESC,
            CASE WHEN p_ordenar_por = 'valor_estimado' THEN l.valor_estimado END DESC,
            CASE WHEN p_ordenar_por = 'municipio_nome' THEN l.municipio_nome END ASC,
            o.score DESC NULLS LAST,
            l.data_publicacao DESC
        LIMIT p_limite OFFSET p_offset
    ) t;

    RETURN json_build_object(
        'data', COALESCE(v_result, '[]'::json),
        'count', v_count
    );
END;
$$;
