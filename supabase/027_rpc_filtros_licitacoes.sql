-- RPC para retornar filtros dinâmicos baseados nos dados reais do banco
-- e na configuração da organização do usuário.

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

    RETURN json_build_object(
        'ufs', COALESCE(v_ufs_com_dados, '[]'::json),
        'palavras_chave', COALESCE(v_palavras_com_dados, '[]'::json),
        'termos_exclusao', v_termos_exclusao
    );
END;
$$;
