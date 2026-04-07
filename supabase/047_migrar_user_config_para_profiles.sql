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

-- 2. Migrar dados existentes
UPDATE profiles p SET
    alertas_email = COALESCE(uc.alertas_email, TRUE),
    alertas_push = COALESCE(uc.alertas_push, TRUE),
    alertas_telegram = COALESCE(uc.alertas_telegram, FALSE),
    telegram_chat_id = uc.telegram_chat_id,
    plano = COALESCE(uc.plano, 'free'),
    plano_expira_em = uc.plano_expira_em
FROM user_config uc
WHERE uc.user_id = p.id;

-- 3. Atualizar handle_new_user() para não criar user_config
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

-- 4. Service role precisa atualizar profiles (notificações backend)
DROP POLICY IF EXISTS "Service role profiles" ON profiles;
CREATE POLICY "Service role profiles"
    ON profiles FOR ALL TO service_role USING (true);

-- 5. Dropar user_config
DROP TABLE IF EXISTS user_config;
