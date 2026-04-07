-- ============================================================
-- Migrar campos ativos de user_config para profiles e dropar a tabela
-- ============================================================

-- 1. Adicionar campos de alertas e plano em profiles
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS alertas_email BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS alertas_push BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS alertas_telegram BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT,
    ADD COLUMN IF NOT EXISTS plano TEXT DEFAULT 'free' CHECK (plano IN ('free', 'pro')),
    ADD COLUMN IF NOT EXISTS plano_expira_em TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_profiles_plano ON profiles(plano);

-- 2. Atualizar handle_new_user() para não criar user_config
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO profiles (id, nome, email)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'nome', NEW.raw_user_meta_data->>'full_name', ''),
        NEW.email
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. Atualizar criar_organizacao() — remover referências a user_config
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

    -- Cria org_config com defaults
    INSERT INTO org_config (org_id, atualizado_por)
    VALUES (new_org_id, auth.uid());

    UPDATE profiles SET org_id = new_org_id WHERE id = auth.uid();

    RETURN new_org_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5. Atualizar aceitar_convite() — remover referência a user_config
CREATE OR REPLACE FUNCTION aceitar_convite(convite_id UUID)
RETURNS VOID AS $$
DECLARE
    v_org_id UUID;
    v_email TEXT;
BEGIN
    SELECT email INTO v_email FROM auth.users WHERE id = auth.uid();

    SELECT org_id INTO v_org_id
    FROM org_convites
    WHERE id = convite_id AND email = v_email AND aceito = FALSE;

    IF v_org_id IS NULL THEN
        RAISE EXCEPTION 'Convite inválido ou já aceito';
    END IF;

    INSERT INTO org_membros (org_id, user_id, role)
    VALUES (v_org_id, auth.uid(), 'membro')
    ON CONFLICT (org_id, user_id) DO NOTHING;

    UPDATE profiles SET org_id = v_org_id WHERE id = auth.uid();
    UPDATE org_convites SET aceito = TRUE WHERE id = convite_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 6. Atualizar sair_organizacao() — remover referência a user_config
CREATE OR REPLACE FUNCTION sair_organizacao()
RETURNS VOID AS $$
BEGIN
    DELETE FROM org_membros WHERE user_id = auth.uid();
    UPDATE profiles SET org_id = NULL WHERE id = auth.uid();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 7. Service role precisa atualizar profiles (notificações backend)
DROP POLICY IF EXISTS "Service role profiles" ON profiles;
CREATE POLICY "Service role profiles"
    ON profiles FOR ALL TO service_role USING (true);

-- 8. Dropar user_config
DROP TABLE IF EXISTS user_config;
