-- ============================================================
-- RPCs lendo exclusivamente de org_config + org_dominios_config.
-- Sem fallback para user_config.
-- Usuário DEVE pertencer a uma organização.
-- ============================================================

-- 1. obter_filtros_licitacoes
CREATE OR REPLACE FUNCTION obter_filtros_licitacoes()
RETURNS JSON
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_org_id UUID;
    v_ufs TEXT[];
    v_palavras TEXT[];
    v_termos_exclusao TEXT[];
    v_ufs_com_dados JSON;
    v_palavras_json JSON;
    v_dominios_org JSON;
BEGIN
    -- 1. Busca org do usuário
    SELECT p.org_id INTO v_org_id
    FROM profiles p WHERE p.id = auth.uid();

    IF v_org_id IS NULL THEN
        RETURN json_build_object(
            'ufs', '[]'::json,
            'palavras_chave', '[]'::json,
            'termos_exclusao', '[]'::json,
            'dominios_org', '{}'::json
        );
    END IF;

    -- 2. Lê org_config
    SELECT oc.ufs, oc.palavras_chave, oc.termos_exclusao
    INTO v_ufs, v_palavras, v_termos_exclusao
    FROM org_config oc WHERE oc.org_id = v_org_id;

    -- 3. UFs que têm licitações no banco
    SELECT json_agg(uf ORDER BY uf) INTO v_ufs_com_dados
    FROM (
        SELECT DISTINCT uf FROM licitacoes
        WHERE uf = ANY(COALESCE(v_ufs, ARRAY[]::TEXT[]))
    ) t;

    -- 4. Palavras-chave
    SELECT json_agg(p) INTO v_palavras_json
    FROM unnest(COALESCE(v_palavras, ARRAY[]::TEXT[])) AS p;

    -- 5. Domínios configurados pela org
    SELECT COALESCE(
        json_object_agg(dominio, codigos_ativos ORDER BY dominio),
        '{}'::json
    ) INTO v_dominios_org
    FROM org_dominios_config
    WHERE org_id = v_org_id;

    RETURN json_build_object(
        'ufs', COALESCE(v_ufs_com_dados, '[]'::json),
        'palavras_chave', COALESCE(v_palavras_json, '[]'::json),
        'termos_exclusao', to_json(COALESCE(v_termos_exclusao, '{}'::TEXT[])),
        'dominios_org', COALESCE(v_dominios_org, '{}'::json)
    );
END;
$$;


-- 2. buscar_licitacoes_filtradas
CREATE OR REPLACE FUNCTION buscar_licitacoes_filtradas(
    p_ufs TEXT[] DEFAULT NULL,
    p_relevancia TEXT DEFAULT NULL,
    p_proposta_aberta BOOLEAN DEFAULT NULL,
    p_exclusivo_me_epp BOOLEAN DEFAULT NULL,
    p_busca TEXT DEFAULT NULL,
    p_palavra_chave TEXT DEFAULT NULL,
    p_modalidade_id INTEGER DEFAULT NULL,
    p_modo_disputa_id INTEGER DEFAULT NULL,
    p_situacao_compra_id INTEGER DEFAULT NULL,
    p_ordenar_por TEXT DEFAULT 'relevancia',
    p_limite INT DEFAULT 20,
    p_offset INT DEFAULT 0
)
RETURNS JSON
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_org_id UUID;
    v_user_id UUID;
    v_modalidades INTEGER[];
    v_termos_exclusao TEXT[];
    v_org_dom_modalidades INTEGER[];
    v_where TEXT := 'WHERE 1=1';
    v_order TEXT;
    v_result JSON;
    v_count INT;
    v_modalidade_nomes TEXT[];
BEGIN
    -- 1. Busca org e user
    v_user_id := auth.uid();

    SELECT p.org_id INTO v_org_id
    FROM profiles p WHERE p.id = v_user_id;

    IF v_org_id IS NULL THEN
        RETURN json_build_object('data', '[]'::json, 'count', 0);
    END IF;

    -- 2. Lê org_config
    SELECT oc.modalidades, oc.termos_exclusao
    INTO v_modalidades, v_termos_exclusao
    FROM org_config oc WHERE oc.org_id = v_org_id;

    -- 3. org_dominios_config prevalece sobre org_config.modalidades
    SELECT codigos_ativos INTO v_org_dom_modalidades
    FROM org_dominios_config
    WHERE org_id = v_org_id AND dominio = 'modalidade_contratacao';

    IF v_org_dom_modalidades IS NOT NULL AND array_length(v_org_dom_modalidades, 1) > 0 THEN
        v_modalidades := v_org_dom_modalidades;
    END IF;

    -- 4. Monta filtros
    IF p_ufs IS NOT NULL AND array_length(p_ufs, 1) > 0 THEN
        v_where := v_where || ' AND l.uf = ANY(' || quote_literal(p_ufs)::text || '::text[])';
    END IF;
    IF p_relevancia IS NOT NULL THEN
        v_where := v_where || ' AND l.relevancia = ' || quote_literal(p_relevancia);
    END IF;
    IF p_proposta_aberta IS NOT NULL THEN
        v_where := v_where || ' AND l.proposta_aberta = ' || p_proposta_aberta;
    END IF;
    IF p_exclusivo_me_epp IS TRUE THEN
        v_where := v_where || ' AND l.exclusivo_me_epp = true';
    END IF;
    IF p_busca IS NOT NULL AND p_busca != '' THEN
        v_where := v_where || ' AND l.objeto ILIKE ' || quote_literal('%' || p_busca || '%');
    END IF;
    IF p_palavra_chave IS NOT NULL AND p_palavra_chave != '' THEN
        v_where := v_where || ' AND ' || quote_literal(p_palavra_chave) || ' = ANY(l.palavras_chave)';
    END IF;
    IF p_modalidade_id IS NOT NULL AND p_modalidade_id > 0 THEN
        v_where := v_where || ' AND l.modalidade_id = ' || p_modalidade_id;
    END IF;
    IF p_modo_disputa_id IS NOT NULL AND p_modo_disputa_id > 0 THEN
        v_where := v_where || ' AND l.modo_disputa_id = ' || p_modo_disputa_id;
    END IF;
    IF p_situacao_compra_id IS NOT NULL AND p_situacao_compra_id > 0 THEN
        v_where := v_where || ' AND l.situacao_compra_id = ' || p_situacao_compra_id;
    END IF;

    -- 5. Filtra por modalidades da org (fallback)
    IF v_modalidades IS NOT NULL AND array_length(v_modalidades, 1) > 0 THEN
        SELECT array_agg(d.nome) INTO v_modalidade_nomes
        FROM dominios_pncp d
        WHERE d.dominio = 'modalidade_contratacao'
          AND d.codigo = ANY(v_modalidades);

        IF v_modalidade_nomes IS NOT NULL AND array_length(v_modalidade_nomes, 1) > 0 THEN
            v_where := v_where || ' AND l.modalidade = ANY(' || quote_literal(v_modalidade_nomes)::text || '::text[])';
        END IF;
    END IF;

    -- 6. Aplica termos de exclusão
    IF v_termos_exclusao IS NOT NULL AND array_length(v_termos_exclusao, 1) > 0 THEN
        FOR i IN 1..array_length(v_termos_exclusao, 1) LOOP
            v_where := v_where || ' AND lower(l.objeto) NOT LIKE ' || quote_literal('%' || lower(v_termos_exclusao[i]) || '%');
        END LOOP;
    END IF;

    -- 7. Ordenação
    CASE p_ordenar_por
        WHEN 'data_publicacao' THEN v_order := 'l.data_publicacao DESC';
        WHEN 'valor_estimado' THEN v_order := 'l.valor_estimado DESC';
        WHEN 'municipio_nome' THEN v_order := 'l.municipio_nome ASC, l.data_publicacao DESC';
        WHEN 'score' THEN v_order := 'l.score DESC NULLS LAST, l.data_publicacao DESC';
        ELSE v_order := 'l.relevancia ASC, l.data_publicacao DESC';
    END CASE;

    -- 8. Count
    EXECUTE 'SELECT count(*) FROM licitacoes l ' || v_where INTO v_count;

    -- 9. Busca paginada com status de leitura
    EXECUTE 'SELECT json_agg(t) FROM ('
        || 'SELECT l.*, (ll.lido_em IS NOT NULL) AS lido '
        || 'FROM licitacoes l '
        || 'LEFT JOIN licitacoes_leitura ll ON ll.licitacao_id = l.id AND ll.user_id = ' || quote_literal(v_user_id)
        || ' ' || v_where
        || ' ORDER BY ' || v_order
        || ' LIMIT $1 OFFSET $2) t'
    INTO v_result
    USING p_limite, p_offset;

    RETURN json_build_object(
        'data', COALESCE(v_result, '[]'::json),
        'count', v_count
    );
END;
$$;
