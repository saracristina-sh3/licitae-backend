-- ============================================================
-- Integra org_dominios_config nos RPCs de busca e filtros.
-- - buscar_licitacoes_filtradas: usa modalidades da org (se existir)
--   em vez do user_config individual
-- - obter_filtros_licitacoes: retorna domínios configurados pela org
-- ============================================================

-- 1. Atualiza RPC de busca para unificar modalidades
CREATE OR REPLACE FUNCTION buscar_licitacoes_filtradas(
    p_uf TEXT DEFAULT NULL,
    p_relevancia TEXT DEFAULT NULL,
    p_proposta_aberta BOOLEAN DEFAULT NULL,
    p_exclusivo_me_epp BOOLEAN DEFAULT NULL,
    p_busca TEXT DEFAULT NULL,
    p_palavra_chave TEXT DEFAULT NULL,
    p_ordenar_por TEXT DEFAULT 'relevancia',
    p_limite INT DEFAULT 20,
    p_offset INT DEFAULT 0
)
RETURNS JSON
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_org_id UUID;
    v_termos TEXT[];
    v_modalidades INTEGER[];
    v_org_modalidades INTEGER[];
    v_where TEXT := 'WHERE 1=1';
    v_order TEXT;
    v_result JSON;
    v_count INT;
    v_modalidade_nomes TEXT[];
BEGIN
    -- 1. Busca org e modalidades do usuário autenticado
    SELECT uc.modalidades, p.org_id
    INTO v_modalidades, v_org_id
    FROM user_config uc
    JOIN profiles p ON p.id = uc.user_id
    WHERE uc.user_id = auth.uid();

    -- 2. Se org tem config de modalidades, prevalece sobre user_config
    IF v_org_id IS NOT NULL THEN
        SELECT codigos_ativos INTO v_org_modalidades
        FROM org_dominios_config
        WHERE org_id = v_org_id AND dominio = 'modalidade_contratacao';

        IF v_org_modalidades IS NOT NULL AND array_length(v_org_modalidades, 1) > 0 THEN
            v_modalidades := v_org_modalidades;
        END IF;
    END IF;

    -- 3. Busca termos de exclusão da org
    IF v_org_id IS NOT NULL THEN
        SELECT array_agg(lower(termo)) INTO v_termos
        FROM org_termos_exclusao WHERE org_id = v_org_id;
    END IF;

    -- 4. Monta filtros básicos
    IF p_uf IS NOT NULL THEN
        v_where := v_where || ' AND uf = ' || quote_literal(p_uf);
    END IF;
    IF p_relevancia IS NOT NULL THEN
        v_where := v_where || ' AND relevancia = ' || quote_literal(p_relevancia);
    END IF;
    IF p_proposta_aberta IS NOT NULL THEN
        v_where := v_where || ' AND proposta_aberta = ' || p_proposta_aberta;
    END IF;
    IF p_exclusivo_me_epp IS TRUE THEN
        v_where := v_where || ' AND exclusivo_me_epp = true';
    END IF;
    IF p_busca IS NOT NULL AND p_busca != '' THEN
        v_where := v_where || ' AND objeto ILIKE ' || quote_literal('%' || p_busca || '%');
    END IF;
    IF p_palavra_chave IS NOT NULL AND p_palavra_chave != '' THEN
        v_where := v_where || ' AND ' || quote_literal(p_palavra_chave) || ' = ANY(palavras_chave)';
    END IF;

    -- 5. Filtra por modalidades (da org ou do user)
    IF v_modalidades IS NOT NULL AND array_length(v_modalidades, 1) > 0 THEN
        SELECT array_agg(d.nome) INTO v_modalidade_nomes
        FROM dominios_pncp d
        WHERE d.dominio = 'modalidade_contratacao'
          AND d.codigo = ANY(v_modalidades);

        IF v_modalidade_nomes IS NOT NULL AND array_length(v_modalidade_nomes, 1) > 0 THEN
            v_where := v_where || ' AND modalidade = ANY(' || quote_literal(v_modalidade_nomes)::text || '::text[])';
        END IF;
    END IF;

    -- 6. Aplica termos de exclusão no objeto
    IF v_termos IS NOT NULL AND array_length(v_termos, 1) > 0 THEN
        FOR i IN 1..array_length(v_termos, 1) LOOP
            v_where := v_where || ' AND lower(objeto) NOT LIKE ' || quote_literal('%' || v_termos[i] || '%');
        END LOOP;
    END IF;

    -- 7. Ordenação
    CASE p_ordenar_por
        WHEN 'data_publicacao' THEN v_order := 'data_publicacao DESC';
        WHEN 'valor_estimado' THEN v_order := 'valor_estimado DESC';
        WHEN 'municipio_nome' THEN v_order := 'municipio_nome ASC, data_publicacao DESC';
        WHEN 'score' THEN v_order := 'score DESC NULLS LAST, data_publicacao DESC';
        ELSE v_order := 'relevancia ASC, data_publicacao DESC';
    END CASE;

    -- 8. Count total
    EXECUTE 'SELECT count(*) FROM licitacoes ' || v_where
    INTO v_count;

    -- 9. Busca paginada
    EXECUTE 'SELECT json_agg(t) FROM (SELECT * FROM licitacoes '
        || v_where || ' ORDER BY ' || v_order
        || ' LIMIT $1 OFFSET $2) t'
    INTO v_result
    USING p_limite, p_offset;

    RETURN json_build_object(
        'data', COALESCE(v_result, '[]'::json),
        'count', v_count
    );
END;
$$;


-- 2. Atualiza RPC de filtros para retornar domínios da org
CREATE OR REPLACE FUNCTION obter_filtros_licitacoes()
RETURNS JSON
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_org_id UUID;
    v_user_ufs TEXT[];
    v_user_palavras TEXT[];
    v_ufs_com_dados JSON;
    v_palavras_com_dados JSON;
    v_termos_exclusao JSON;
    v_dominios_org JSON;
BEGIN
    -- 1. Busca config do usuário autenticado
    SELECT uc.ufs, uc.palavras_chave, p.org_id
    INTO v_user_ufs, v_user_palavras, v_org_id
    FROM user_config uc
    JOIN profiles p ON p.id = uc.user_id
    WHERE uc.user_id = auth.uid();

    -- 2. UFs que têm licitações no banco (intersecção com config do user)
    SELECT json_agg(uf ORDER BY uf) INTO v_ufs_com_dados
    FROM (
        SELECT DISTINCT uf FROM licitacoes
        WHERE uf = ANY(COALESCE(v_user_ufs, ARRAY['MG','RJ']))
    ) t;

    -- 3. Palavras-chave configuradas pelo usuário
    SELECT json_agg(p) INTO v_palavras_com_dados
    FROM unnest(COALESCE(v_user_palavras, ARRAY[]::TEXT[])) AS p;

    -- 4. Termos de exclusão da org
    v_termos_exclusao := '[]'::json;
    IF v_org_id IS NOT NULL THEN
        SELECT COALESCE(json_agg(termo ORDER BY termo), '[]'::json) INTO v_termos_exclusao
        FROM org_termos_exclusao WHERE org_id = v_org_id;
    END IF;

    -- 5. Domínios configurados pela org (todos os domínios com seus códigos ativos)
    v_dominios_org := '{}'::json;
    IF v_org_id IS NOT NULL THEN
        SELECT COALESCE(
            json_object_agg(dominio, codigos_ativos ORDER BY dominio),
            '{}'::json
        ) INTO v_dominios_org
        FROM org_dominios_config
        WHERE org_id = v_org_id;
    END IF;

    RETURN json_build_object(
        'ufs', COALESCE(v_ufs_com_dados, '[]'::json),
        'palavras_chave', COALESCE(v_palavras_com_dados, '[]'::json),
        'termos_exclusao', v_termos_exclusao,
        'dominios_org', v_dominios_org
    );
END;
$$;
