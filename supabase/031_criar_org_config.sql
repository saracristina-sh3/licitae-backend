-- ============================================================
-- Unificação de configs: cria org_config, migra dados, depreca campos
-- ============================================================

-- 1. Tabela org_config (1 row por organização)
CREATE TABLE IF NOT EXISTS org_config (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizacoes(id) ON DELETE CASCADE UNIQUE,
    ufs TEXT[] DEFAULT '{MG,RJ,SP,ES,PR,SC,RS,GO,BA,PE,CE}',
    fpm_maximo NUMERIC(3,1) DEFAULT 2.8,
    palavras_chave TEXT[] DEFAULT '{software,sistema,permissão de uso,licença de uso,locação de software,cessão de uso,sistema integrado,sistema de gestão,solução tecnológica}',
    fontes TEXT[] DEFAULT '{PNCP,QUERIDO_DIARIO,TCE_RJ}',
    modalidades INTEGER[] DEFAULT '{6,7,8,9,12}',
    termos_alta TEXT[] DEFAULT '{permissão de uso,licença de uso,cessão de uso,locação de software,sistema integrado de gestão}',
    termos_media TEXT[] DEFAULT '{software,sistema de gestão,solução tecnológica}',

    termos_exclusao TEXT[] DEFAULT '{}',
    atualizado_por UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_org_config_org ON org_config(org_id);

-- ============================================================
-- 2. RLS
-- ============================================================

ALTER TABLE org_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Membro lê org_config" ON org_config;
CREATE POLICY "Membro lê org_config"
    ON org_config FOR SELECT TO authenticated
    USING (org_id IN (SELECT get_user_org_ids()));

DROP POLICY IF EXISTS "Admin insere org_config" ON org_config;
CREATE POLICY "Admin insere org_config"
    ON org_config FOR INSERT TO authenticated
    WITH CHECK (org_id IN (SELECT get_user_admin_org_ids()));

DROP POLICY IF EXISTS "Admin atualiza org_config" ON org_config;
CREATE POLICY "Admin atualiza org_config"
    ON org_config FOR UPDATE TO authenticated
    USING (org_id IN (SELECT get_user_admin_org_ids()));

DROP POLICY IF EXISTS "Admin remove org_config" ON org_config;
CREATE POLICY "Admin remove org_config"
    ON org_config FOR DELETE TO authenticated
    USING (org_id IN (SELECT get_user_admin_org_ids()));

DROP POLICY IF EXISTS "Service role org_config" ON org_config;
CREATE POLICY "Service role org_config"
    ON org_config FOR ALL TO service_role USING (true);

-- ============================================================
-- 3. Migrar dados: copia config do admin de cada org
-- ============================================================

INSERT INTO org_config (
    org_id, ufs, fpm_maximo, palavras_chave, fontes, modalidades,
    termos_alta, termos_media, atualizado_por
)
SELECT DISTINCT ON (p.org_id)
    p.org_id,
    COALESCE(uc.ufs, '{MG,RJ,SP,ES,PR,SC,RS,GO,BA,PE,CE}'),
    COALESCE(uc.fpm_maximo, 2.8),
    COALESCE(uc.palavras_chave, '{software,sistema}'),
    COALESCE(uc.fontes, '{PNCP}'),
    COALESCE(uc.modalidades, '{6,7,8,9,12}'),
    COALESCE(uc.termos_alta, '{}'),
    COALESCE(uc.termos_media, '{}'),
    uc.user_id
FROM user_config uc
JOIN profiles p ON p.id = uc.user_id
JOIN org_membros om ON om.org_id = p.org_id AND om.user_id = uc.user_id AND om.role = 'admin'
WHERE p.org_id IS NOT NULL
ORDER BY p.org_id, uc.updated_at DESC
ON CONFLICT (org_id) DO NOTHING;

-- ============================================================
-- 4. Migrar termos de exclusão de org_termos_exclusao → org_config.termos_exclusao
-- ============================================================

UPDATE org_config oc SET termos_exclusao = sub.termos
FROM (
    SELECT org_id, array_agg(termo ORDER BY termo) AS termos
    FROM org_termos_exclusao
    GROUP BY org_id
) sub
WHERE oc.org_id = sub.org_id;

-- ============================================================
-- 5. Atualizar criar_organizacao() para criar org_config automaticamente
-- ============================================================

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
        termos_alta, termos_media, atualizado_por)
    SELECT new_org_id,
        COALESCE(uc.ufs, '{MG,RJ,SP,ES,PR,SC,RS,GO,BA,PE,CE}'),
        COALESCE(uc.fpm_maximo, 2.8),
        COALESCE(uc.palavras_chave, '{software,sistema}'),
        COALESCE(uc.fontes, '{PNCP}'),
        COALESCE(uc.modalidades, '{6,7,8,9,12}'),
        COALESCE(uc.termos_alta, '{}'),
        COALESCE(uc.termos_media, '{}'),
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

-- ============================================================
-- 6. Deprecar campos migrados em user_config e tabela org_termos_exclusao
-- ============================================================

COMMENT ON COLUMN user_config.ufs IS 'DEPRECATED: usar org_config.ufs';
COMMENT ON COLUMN user_config.fpm_maximo IS 'DEPRECATED: usar org_config.fpm_maximo';
COMMENT ON COLUMN user_config.palavras_chave IS 'DEPRECATED: usar org_config.palavras_chave';
COMMENT ON COLUMN user_config.modalidades IS 'DEPRECATED: usar org_config.modalidades';
COMMENT ON COLUMN user_config.fontes IS 'DEPRECATED: usar org_config.fontes';
COMMENT ON COLUMN user_config.termos_alta IS 'DEPRECATED: usar org_config.termos_alta';
COMMENT ON COLUMN user_config.termos_media IS 'DEPRECATED: usar org_config.termos_media';
COMMENT ON COLUMN user_config.termos_me_epp IS 'DEPRECATED: ME/EPP agora detectado via tipoBeneficioId do PNCP';
COMMENT ON TABLE org_termos_exclusao IS 'DEPRECATED: usar org_config.termos_exclusao';
