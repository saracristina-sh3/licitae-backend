-- ============================================================
-- Tabela de leitura de licitações por usuário.
-- Registra quando o usuário abriu/visualizou uma licitação.
-- ============================================================

CREATE TABLE IF NOT EXISTS licitacoes_leitura (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    licitacao_id UUID NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    lido_em TIMESTAMPTZ DEFAULT now(),
    UNIQUE(licitacao_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_leitura_user ON licitacoes_leitura(user_id);
CREATE INDEX IF NOT EXISTS idx_leitura_licitacao ON licitacoes_leitura(licitacao_id);

ALTER TABLE licitacoes_leitura ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Usuário vê suas leituras"
    ON licitacoes_leitura FOR SELECT TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "Usuário marca como lido"
    ON licitacoes_leitura FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "Usuário remove leitura"
    ON licitacoes_leitura FOR DELETE TO authenticated
    USING (user_id = auth.uid());
