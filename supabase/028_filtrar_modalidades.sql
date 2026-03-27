-- Atualiza RPC para filtrar por modalidades configuradas pelo usuário.
-- user_config.modalidades contém os IDs das modalidades que o usuário quer ver.
-- Ex: {6,7,8} = Pregão Eletrônico, Pregão Presencial, Dispensa (sem Inexigibilidade/Credenciamento)

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

    -- 2. Busca termos de exclusão da org
    IF v_org_id IS NOT NULL THEN
        SELECT array_agg(lower(termo)) INTO v_termos
        FROM org_termos_exclusao WHERE org_id = v_org_id;
    END IF;

    -- 3. Monta filtros básicos
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

    -- 4. Filtra por modalidades configuradas pelo usuário
    IF v_modalidades IS NOT NULL AND array_length(v_modalidades, 1) > 0 THEN
        SELECT array_agg(nome) INTO v_modalidade_nomes
        FROM (
            SELECT CASE m
                WHEN 2 THEN 'Diálogo Competitivo'
                WHEN 3 THEN 'Concurso'
                WHEN 4 THEN 'Concorrência Eletrônica'
                WHEN 5 THEN 'Concorrência Presencial'
                WHEN 6 THEN 'Pregão Eletrônico'
                WHEN 7 THEN 'Pregão Presencial'
                WHEN 8 THEN 'Dispensa de Licitação'
                WHEN 9 THEN 'Inexigibilidade'
                WHEN 10 THEN 'Manifestação de Interesse'
                WHEN 11 THEN 'Pré-qualificação'
                WHEN 12 THEN 'Credenciamento'
            END AS nome
            FROM unnest(v_modalidades) AS m
        ) t
        WHERE nome IS NOT NULL;

        IF v_modalidade_nomes IS NOT NULL AND array_length(v_modalidade_nomes, 1) > 0 THEN
            v_where := v_where || ' AND modalidade = ANY(' || quote_literal(v_modalidade_nomes)::text || '::text[])';
        END IF;
    END IF;

    -- 5. Aplica termos de exclusão no objeto
    IF v_termos IS NOT NULL AND array_length(v_termos, 1) > 0 THEN
        FOR i IN 1..array_length(v_termos, 1) LOOP
            v_where := v_where || ' AND lower(objeto) NOT LIKE ' || quote_literal('%' || v_termos[i] || '%');
        END LOOP;
    END IF;

    -- 6. Ordenação
    CASE p_ordenar_por
        WHEN 'data_publicacao' THEN v_order := 'data_publicacao DESC';
        WHEN 'valor_estimado' THEN v_order := 'valor_estimado DESC';
        WHEN 'municipio_nome' THEN v_order := 'municipio_nome ASC, data_publicacao DESC';
        WHEN 'score' THEN v_order := 'score DESC NULLS LAST, data_publicacao DESC';
        ELSE v_order := 'relevancia ASC, data_publicacao DESC';
    END CASE;

    -- 7. Count total
    EXECUTE 'SELECT count(*) FROM licitacoes ' || v_where INTO v_count;

    -- 8. Busca paginada
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
