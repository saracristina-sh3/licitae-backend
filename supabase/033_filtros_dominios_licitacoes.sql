-- ============================================================
-- Adiciona colunas de domínio PNCP na tabela licitacoes
-- para permitir filtros por modalidade, modo de disputa e situação.
-- Atualiza RPC buscar_licitacoes_filtradas com novos parâmetros.
-- ============================================================

-- 1. Novas colunas
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS modalidade_id INTEGER;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS modo_disputa_id INTEGER;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS situacao_compra_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_licitacoes_modalidade_id ON licitacoes(modalidade_id);
CREATE INDEX IF NOT EXISTS idx_licitacoes_modo_disputa_id ON licitacoes(modo_disputa_id);
CREATE INDEX IF NOT EXISTS idx_licitacoes_situacao_compra_id ON licitacoes(situacao_compra_id);

-- 2. Popula a partir de dados_brutos (JSONB) para registros existentes
UPDATE licitacoes SET
    modalidade_id = (dados_brutos->>'modalidadeId')::INT,
    modo_disputa_id = (dados_brutos->>'modoDisputaId')::INT,
    situacao_compra_id = (dados_brutos->>'situacaoCompraId')::INT
WHERE dados_brutos IS NOT NULL
  AND fonte = 'PNCP'
  AND modalidade_id IS NULL;


-- ============================================================
-- 3. RPC buscar_licitacoes_filtradas com filtros de domínio
-- ============================================================

CREATE OR REPLACE FUNCTION buscar_licitacoes_filtradas(
    p_uf TEXT DEFAULT NULL,
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
    v_modalidades INTEGER[];
    v_termos_exclusao TEXT[];
    v_org_dom_modalidades INTEGER[];
    v_where TEXT := 'WHERE 1=1';
    v_order TEXT;
    v_result JSON;
    v_count INT;
    v_modalidade_nomes TEXT[];
BEGIN
    -- 1. Busca org do usuário
    SELECT p.org_id INTO v_org_id
    FROM profiles p WHERE p.id = auth.uid();

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

    -- 4. Filtros básicos
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

    -- 5. Filtro por modalidade (usuario escolhe 1, validado contra org)
    IF p_modalidade_id IS NOT NULL THEN
        -- Só aplica se o código está nos ativos da org
        IF v_modalidades IS NOT NULL AND p_modalidade_id = ANY(v_modalidades) THEN
            v_where := v_where || ' AND modalidade_id = ' || p_modalidade_id;
        END IF;
    ELSE
        -- Sem filtro específico: aplica todas as modalidades da org
        IF v_modalidades IS NOT NULL AND array_length(v_modalidades, 1) > 0 THEN
            SELECT array_agg(d.nome) INTO v_modalidade_nomes
            FROM dominios_pncp d
            WHERE d.dominio = 'modalidade_contratacao'
              AND d.codigo = ANY(v_modalidades);

            IF v_modalidade_nomes IS NOT NULL AND array_length(v_modalidade_nomes, 1) > 0 THEN
                v_where := v_where || ' AND modalidade = ANY(' || quote_literal(v_modalidade_nomes)::text || '::text[])';
            END IF;
        END IF;
    END IF;

    -- 6. Filtro por modo de disputa (validado contra org_dominios_config)
    IF p_modo_disputa_id IS NOT NULL THEN
        IF EXISTS (
            SELECT 1 FROM org_dominios_config
            WHERE org_id = v_org_id AND dominio = 'modo_disputa'
              AND p_modo_disputa_id = ANY(codigos_ativos)
        ) THEN
            v_where := v_where || ' AND modo_disputa_id = ' || p_modo_disputa_id;
        END IF;
    END IF;

    -- 7. Filtro por situação da compra (validado contra org_dominios_config)
    IF p_situacao_compra_id IS NOT NULL THEN
        IF EXISTS (
            SELECT 1 FROM org_dominios_config
            WHERE org_id = v_org_id AND dominio = 'situacao_item_contratacao'
              AND p_situacao_compra_id = ANY(codigos_ativos)
        ) THEN
            v_where := v_where || ' AND situacao_compra_id = ' || p_situacao_compra_id;
        END IF;
    END IF;

    -- 8. Aplica termos de exclusão
    IF v_termos_exclusao IS NOT NULL AND array_length(v_termos_exclusao, 1) > 0 THEN
        FOR i IN 1..array_length(v_termos_exclusao, 1) LOOP
            v_where := v_where || ' AND lower(objeto) NOT LIKE ' || quote_literal('%' || lower(v_termos_exclusao[i]) || '%');
        END LOOP;
    END IF;

    -- 9. Ordenação
    CASE p_ordenar_por
        WHEN 'data_publicacao' THEN v_order := 'data_publicacao DESC';
        WHEN 'valor_estimado' THEN v_order := 'valor_estimado DESC';
        WHEN 'municipio_nome' THEN v_order := 'municipio_nome ASC, data_publicacao DESC';
        WHEN 'score' THEN v_order := 'score DESC NULLS LAST, data_publicacao DESC';
        ELSE v_order := 'relevancia ASC, data_publicacao DESC';
    END CASE;

    -- 10. Count
    EXECUTE 'SELECT count(*) FROM licitacoes ' || v_where INTO v_count;

    -- 11. Busca paginada
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
