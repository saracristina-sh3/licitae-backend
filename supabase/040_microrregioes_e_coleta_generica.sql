-- ============================================================
-- 040: Microrregiões IBGE + suporte a coleta genérica + prospecção por org
-- ============================================================

-- 1. Tabela de microrregiões IBGE
CREATE TABLE IF NOT EXISTS microrregioes (
    id INTEGER PRIMARY KEY,                  -- ID IBGE (ex: 31001)
    nome TEXT NOT NULL,                       -- "Unaí"
    mesorregiao_id INTEGER NOT NULL,
    mesorregiao_nome TEXT NOT NULL,           -- "Noroeste de Minas"
    uf CHAR(2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_microrregioes_uf ON microrregioes(uf);
CREATE INDEX IF NOT EXISTS idx_microrregioes_mesorregiao ON microrregioes(mesorregiao_id);

-- 2. Vincular municípios a microrregiões
ALTER TABLE municipios
    ADD COLUMN IF NOT EXISTS microrregiao_id INTEGER REFERENCES microrregioes(id);

CREATE INDEX IF NOT EXISTS idx_municipios_microrregiao ON municipios(microrregiao_id);

-- 3. Adicionar microrregiões na config da org
ALTER TABLE org_config
    ADD COLUMN IF NOT EXISTS microrregioes INTEGER[] DEFAULT '{}';

-- 4. Adicionar ncms_alvo na config da org (filtro por classificação de item)
ALTER TABLE org_config
    ADD COLUMN IF NOT EXISTS ncms_alvo TEXT[] DEFAULT '{}';

-- 5. Flag de itens coletados na tabela de licitações
ALTER TABLE licitacoes
    ADD COLUMN IF NOT EXISTS itens_coletados BOOLEAN DEFAULT FALSE;

-- 6. Tabela de oportunidades por organização (resultado da prospecção)
DROP TABLE IF EXISTS oportunidades_org;
CREATE TABLE oportunidades_org (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizacoes(id) ON DELETE CASCADE,
    licitacao_id UUID NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    score NUMERIC(5,1) DEFAULT 0,
    relevancia TEXT DEFAULT 'BAIXA',         -- ALTA | MEDIA | BAIXA
    urgencia TEXT DEFAULT 'NORMAL',          -- URGENTE | PROXIMA | NORMAL
    palavras_chave_encontradas TEXT[] DEFAULT '{}',
    campos_matched TEXT[] DEFAULT '{}',      -- ["objeto", "complementar", "itens"]
    itens_matched JSONB DEFAULT '[]',        -- [{numero_item, descricao, quantidade, valor_unitario, valor_total}]
    total_itens INTEGER DEFAULT 0,
    itens_relevantes INTEGER DEFAULT 0,
    valor_itens_relevantes NUMERIC(15,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (org_id, licitacao_id)
);

CREATE INDEX IF NOT EXISTS idx_oportunidades_org_org ON oportunidades_org(org_id);
CREATE INDEX IF NOT EXISTS idx_oportunidades_org_score ON oportunidades_org(score DESC);
CREATE INDEX IF NOT EXISTS idx_oportunidades_org_relevancia ON oportunidades_org(relevancia);
CREATE INDEX IF NOT EXISTS idx_oportunidades_org_created ON oportunidades_org(created_at DESC);

-- 7. RLS para microrregioes (leitura pública)
ALTER TABLE microrregioes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Leitura pública microrregioes" ON microrregioes;
CREATE POLICY "Leitura pública microrregioes"
    ON microrregioes FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Service role microrregioes" ON microrregioes;
CREATE POLICY "Service role microrregioes"
    ON microrregioes FOR ALL TO service_role USING (true);

-- 8. RLS para oportunidades_org
ALTER TABLE oportunidades_org ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Membro lê oportunidades_org" ON oportunidades_org;
CREATE POLICY "Membro lê oportunidades_org"
    ON oportunidades_org FOR SELECT TO authenticated
    USING (org_id IN (SELECT get_user_org_ids()));

DROP POLICY IF EXISTS "Service role oportunidades_org" ON oportunidades_org;
CREATE POLICY "Service role oportunidades_org"
    ON oportunidades_org FOR ALL TO service_role USING (true);

-- 9. Atualizar função criar_organizacao para incluir microrregioes e ncms_alvo
CREATE OR REPLACE FUNCTION criar_organizacao(nome_org TEXT, slug_org TEXT)
RETURNS UUID AS $$
DECLARE
    new_org_id UUID;
BEGIN
    INSERT INTO organizacoes (nome, slug)
    VALUES (nome_org, slug_org)
    RETURNING id INTO new_org_id;

    INSERT INTO org_membros (org_id, user_id, role)
    VALUES (new_org_id, auth.uid(), 'admin');

    -- Cria org_config herdando config do admin
    INSERT INTO org_config (org_id, ufs, fpm_maximo, palavras_chave, fontes, modalidades,
        termos_alta, termos_media, microrregioes, ncms_alvo, atualizado_por)
    SELECT new_org_id,
        COALESCE(uc.ufs, '{MG,RJ,SP,ES,PR,SC,RS,GO,BA,PE,CE}'),
        COALESCE(uc.fpm_maximo, 2.8),
        COALESCE(uc.palavras_chave, '{software,sistema}'),
        COALESCE(uc.fontes, '{PNCP}'),
        COALESCE(uc.modalidades, '{6,7,8,9,12}'),
        COALESCE(uc.termos_alta, '{}'),
        COALESCE(uc.termos_media, '{}'),
        '{}',
        '{}',
        auth.uid()
    FROM user_config uc
    WHERE uc.user_id = auth.uid();

    -- Se user não tem user_config, cria org_config com defaults
    IF NOT FOUND THEN
        INSERT INTO org_config (org_id, atualizado_por)
        VALUES (new_org_id, auth.uid());
    END IF;

    UPDATE profiles SET org_id = new_org_id WHERE id = auth.uid();
    UPDATE user_config SET org_id = new_org_id WHERE user_id = auth.uid();

    RETURN new_org_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
