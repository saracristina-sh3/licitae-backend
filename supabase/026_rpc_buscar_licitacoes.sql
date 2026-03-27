-- RPC para buscar licitações com filtro de exclusão server-side.
-- Resolve race condition do frontend: auth.uid() sempre disponível no PostgreSQL.

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
    v_where TEXT := 'WHERE 1=1';
    v_order TEXT;
    v_result JSON;
    v_count INT;
BEGIN
    -- 1. Busca org do usuário autenticado
    SELECT p.org_id INTO v_org_id
    FROM profiles p WHERE p.id = auth.uid();

    -- 2. Busca termos de exclusão da org
    IF v_org_id IS NOT NULL THEN
        SELECT array_agg(lower(termo)) INTO v_termos
        FROM org_termos_exclusao WHERE org_id = v_org_id;
    END IF;

    -- 3. Monta filtros
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

    -- 4. Aplica termos de exclusão no objeto
    IF v_termos IS NOT NULL AND array_length(v_termos, 1) > 0 THEN
        FOR i IN 1..array_length(v_termos, 1) LOOP
            v_where := v_where || ' AND lower(objeto) NOT LIKE ' || quote_literal('%' || v_termos[i] || '%');
        END LOOP;
    END IF;

    -- 5. Ordenação
    CASE p_ordenar_por
        WHEN 'data_publicacao' THEN v_order := 'data_publicacao DESC';
        WHEN 'valor_estimado' THEN v_order := 'valor_estimado DESC';
        WHEN 'municipio_nome' THEN v_order := 'municipio_nome ASC, data_publicacao DESC';
        WHEN 'score' THEN v_order := 'score DESC NULLS LAST, data_publicacao DESC';
        ELSE v_order := 'relevancia ASC, data_publicacao DESC';
    END CASE;

    -- 6. Count total (com filtros + exclusões)
    EXECUTE 'SELECT count(*) FROM licitacoes ' || v_where INTO v_count;

    -- 7. Busca paginada
    EXECUTE 'SELECT json_agg(t) FROM (SELECT * FROM licitacoes '
        || v_where || ' ORDER BY ' || v_order
        || ' LIMIT ' || p_limite || ' OFFSET ' || p_offset || ') t'
    INTO v_result;

    RETURN json_build_object(
        'data', COALESCE(v_result, '[]'::json),
        'count', v_count
    );
END;
$$;
