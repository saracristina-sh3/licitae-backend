-- ============================================================
-- RPCs para Sessão de Comparação Customizada
-- ============================================================

-- ── Buscar itens das licitações selecionadas na sessão ────
-- Retorna itens + resultados das licitações NÃO excluídas.
-- Vinculação licitacoes → itens_contratacao via:
--   1. licitacao_hash = hash_dedup (quando disponível)
--   2. cnpj_orgao + ano_compra + sequencial_compra (extraídos da url_fonte)
CREATE OR REPLACE FUNCTION buscar_itens_por_licitacoes(
    p_sessao_id UUID
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_result JSON;
    v_sessao RECORD;
BEGIN
    -- Verificar que a sessão pertence ao usuário ou à org
    SELECT id, org_id, filtros_aplicados
    INTO v_sessao
    FROM sessoes_comparacao
    WHERE id = p_sessao_id
      AND org_id IN (SELECT get_user_org_ids());

    IF NOT FOUND THEN
        RETURN json_build_object('error', 'Sessão não encontrada', 'data', '[]'::json);
    END IF;

    SELECT json_agg(t ORDER BY t.relevancia ASC, t.licitacao_objeto ASC, t.numero_item ASC)
    INTO v_result
    FROM (
        SELECT
            ic.id,
            ic.descricao,
            ic.ncm_nbs_codigo,
            ic.numero_item,
            ic.quantidade,
            ic.unidade_medida,
            ic.valor_unitario_estimado,
            ic.valor_total_estimado,
            ic.plataforma_nome,
            ic.plataforma_id,
            ic.municipio,
            ic.uf,
            l.id AS licitacao_id,
            l.objeto AS licitacao_objeto,
            l.municipio_nome AS licitacao_municipio,
            l.uf AS licitacao_uf,
            l.relevancia,
            l.score AS licitacao_score,
            l.valor_estimado AS licitacao_valor_estimado,
            COALESCE(
                (SELECT json_agg(json_build_object(
                    'valor_unitario_homologado', ri.valor_unitario_homologado,
                    'valor_total_homologado', ri.valor_total_homologado,
                    'nome_fornecedor', ri.nome_fornecedor,
                    'cnpj_fornecedor', ri.cnpj_fornecedor,
                    'porte_fornecedor', ri.porte_fornecedor,
                    'percentual_desconto', ri.percentual_desconto
                ))
                FROM resultados_item ri WHERE ri.item_id = ic.id),
                '[]'::json
            ) AS resultados,
            CASE WHEN si.id IS NOT NULL AND si.excluido = TRUE THEN TRUE ELSE FALSE END AS excluido
        FROM licitacoes l
        -- Join robusto: por hash OU por cnpj+ano+seq do dados_brutos JSONB
        JOIN itens_contratacao ic ON (
            -- Vinculação primária: hash direto
            (ic.licitacao_hash IS NOT NULL AND ic.licitacao_hash = l.hash_dedup)
            OR
            -- Vinculação secundária: cnpj + ano + sequencial via dados_brutos
            (
                l.cnpj_orgao IS NOT NULL
                AND l.cnpj_orgao != ''
                AND l.dados_brutos IS NOT NULL
                AND ic.cnpj_orgao = l.cnpj_orgao
                AND ic.ano_compra = (l.dados_brutos->>'anoCompra')::int
                AND ic.sequencial_compra = (l.dados_brutos->>'sequencialCompra')::int
            )
        )
        -- Apenas licitações SELECIONADAS na sessão (excluida = FALSE)
        JOIN sessao_licitacoes sl
            ON sl.sessao_id = p_sessao_id AND sl.licitacao_id = l.id AND sl.excluida = FALSE
        -- Flag de exclusão de item
        LEFT JOIN sessao_itens si
            ON si.sessao_id = p_sessao_id AND si.item_id = ic.id
        WHERE ic.valor_unitario_estimado > 0
    ) t;

    RETURN json_build_object(
        'data', COALESCE(v_result, '[]'::json),
        'total', COALESCE(json_array_length(v_result), 0)
    );
END;
$$;

-- ── Contar licitações disponíveis para uma sessão ─────────
CREATE OR REPLACE FUNCTION contar_licitacoes_sessao(
    p_sessao_id UUID
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_total INT;
    v_excluidas INT;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sessoes_comparacao
        WHERE id = p_sessao_id AND org_id IN (SELECT get_user_org_ids())
    ) THEN
        RETURN json_build_object('error', 'Sessão não encontrada');
    END IF;

    SELECT COUNT(*) INTO v_total FROM licitacoes;

    SELECT COUNT(*) INTO v_excluidas
    FROM sessao_licitacoes
    WHERE sessao_id = p_sessao_id AND excluida = TRUE;

    RETURN json_build_object(
        'total', v_total,
        'excluidas', v_excluidas,
        'selecionadas', v_total - v_excluidas
    );
END;
$$;
