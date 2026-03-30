-- ============================================================
-- RPC dashboard_resumo: painel executivo em 1 request
-- Retorna pipeline, valor, urgentes, alertas, novas, distribuição
-- ============================================================

CREATE OR REPLACE FUNCTION dashboard_resumo()
RETURNS JSON
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_user_id UUID := auth.uid();
    v_org_id UUID;
    v_pipeline JSON;
    v_valor_pipeline NUMERIC;
    v_prazos JSON;
    v_alertas_nao_lidos INT;
    v_novas_alta JSON;
    v_por_uf JSON;
    v_por_modalidade JSON;
    v_fechando_semana INT;
    v_ultima_coleta TIMESTAMPTZ;
    v_total_abertas INT;
BEGIN
    -- Org do usuário
    SELECT p.org_id INTO v_org_id
    FROM profiles p WHERE p.id = v_user_id;

    -- 1. Pipeline de oportunidades (contagem por status)
    SELECT json_object_agg(status, cnt) INTO v_pipeline
    FROM (
        SELECT status::TEXT, count(*) AS cnt
        FROM oportunidades
        WHERE (user_id = v_user_id OR org_id = v_org_id)
        GROUP BY status
    ) t;

    -- 2. Valor total do pipeline ativo
    SELECT COALESCE(SUM(
        COALESCE(o.valor_proposta, l.valor_estimado)
    ), 0) INTO v_valor_pipeline
    FROM oportunidades o
    JOIN licitacoes l ON l.id = o.licitacao_id
    WHERE (o.user_id = v_user_id OR o.org_id = v_org_id)
      AND o.status IN ('identificada', 'analisando', 'preparando_proposta', 'proposta_enviada');

    -- 3. Prazos urgentes (vencendo em até 3 dias, não lidos, max 5)
    SELECT COALESCE(json_agg(t), '[]'::json) INTO v_prazos
    FROM (
        SELECT
            pa.id,
            pa.tipo,
            pa.dias_restantes,
            pa.data_prazo,
            pa.oportunidade_id,
            pa.licitacao_id,
            l.municipio_nome,
            l.uf,
            LEFT(l.objeto, 80) AS objeto
        FROM prazo_alertas pa
        JOIN licitacoes l ON l.id = pa.licitacao_id
        WHERE pa.user_id = v_user_id
          AND pa.lido = false
        ORDER BY pa.dias_restantes ASC, pa.data_prazo ASC
        LIMIT 5
    ) t;

    -- 4. Alertas de monitoramento não lidos
    SELECT count(*) INTO v_alertas_nao_lidos
    FROM monitoramento_alertas
    WHERE user_id = v_user_id AND lido = false;

    -- 5. Novas oportunidades de alta relevância (top 5 recentes, abertas)
    SELECT COALESCE(json_agg(t), '[]'::json) INTO v_novas_alta
    FROM (
        SELECT
            l.id,
            l.score,
            l.modalidade,
            l.municipio_nome,
            l.uf,
            l.valor_estimado,
            l.data_publicacao,
            l.urgencia
        FROM licitacoes l
        WHERE l.relevancia = 'ALTA'
          AND l.proposta_aberta = true
          -- Excluir as que já são oportunidades do user/org
          AND NOT EXISTS (
              SELECT 1 FROM oportunidades o
              WHERE o.licitacao_id = l.id
                AND (o.user_id = v_user_id OR o.org_id = v_org_id)
          )
        ORDER BY l.data_publicacao DESC
        LIMIT 5
    ) t;

    -- 6. Distribuição por UF (top 8, só abertas)
    SELECT COALESCE(json_agg(t), '[]'::json) INTO v_por_uf
    FROM (
        SELECT uf, count(*) AS total
        FROM licitacoes
        WHERE proposta_aberta = true
        GROUP BY uf
        ORDER BY total DESC
        LIMIT 8
    ) t;

    -- 7. Distribuição por modalidade (top 5, só abertas)
    SELECT COALESCE(json_agg(t), '[]'::json) INTO v_por_modalidade
    FROM (
        SELECT modalidade, count(*) AS total
        FROM licitacoes
        WHERE proposta_aberta = true
          AND modalidade IS NOT NULL AND modalidade != ''
        GROUP BY modalidade
        ORDER BY total DESC
        LIMIT 5
    ) t;

    -- 8. Fechando esta semana
    SELECT count(*) INTO v_fechando_semana
    FROM licitacoes
    WHERE proposta_aberta = true
      AND data_encerramento_proposta BETWEEN now() AND now() + interval '7 days';

    -- 9. Total abertas
    SELECT count(*) INTO v_total_abertas
    FROM licitacoes
    WHERE proposta_aberta = true;

    -- 10. Última coleta
    SELECT max(data_publicacao) INTO v_ultima_coleta
    FROM licitacoes
    WHERE fonte = 'PNCP';

    RETURN json_build_object(
        'pipeline', COALESCE(v_pipeline, '{}'::json),
        'valor_pipeline', v_valor_pipeline,
        'prazos_urgentes', v_prazos,
        'alertas_nao_lidos', v_alertas_nao_lidos,
        'novas_alta', v_novas_alta,
        'por_uf', v_por_uf,
        'por_modalidade', v_por_modalidade,
        'fechando_semana', v_fechando_semana,
        'total_abertas', v_total_abertas,
        'ultima_coleta', v_ultima_coleta
    );
END;
$$;
