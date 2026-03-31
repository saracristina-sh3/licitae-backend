-- ============================================================
-- Sessão de Comparação Customizada
-- Permite ao usuário selecionar licitações e itens para
-- comparativo de preços personalizado com análise IA.
-- ============================================================

-- ── Sessão principal (1 por workflow) ──────────────────────
CREATE TABLE IF NOT EXISTS sessoes_comparacao (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizacoes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    nome TEXT,
    fase TEXT NOT NULL DEFAULT 'selecao_licitacoes'
        CHECK (fase IN ('selecao_licitacoes', 'selecao_itens', 'comparacao', 'analise')),
    filtros_aplicados JSONB,
    total_licitacoes_selecionadas INT DEFAULT 0,
    total_itens_selecionados INT DEFAULT 0,
    concluida BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_sessoes_comp_user ON sessoes_comparacao(user_id);
CREATE INDEX idx_sessoes_comp_org ON sessoes_comparacao(org_id);

-- ── Licitações excluídas na fase 1 ────────────────────────
-- Só exclusões são gravadas (tudo selecionado por padrão)
CREATE TABLE IF NOT EXISTS sessao_licitacoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sessao_id UUID NOT NULL REFERENCES sessoes_comparacao(id) ON DELETE CASCADE,
    licitacao_id UUID NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    excluida BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(sessao_id, licitacao_id)
);

CREATE INDEX idx_sessao_lic_sessao ON sessao_licitacoes(sessao_id);

-- ── Itens excluídos na fase 2 ─────────────────────────────
CREATE TABLE IF NOT EXISTS sessao_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sessao_id UUID NOT NULL REFERENCES sessoes_comparacao(id) ON DELETE CASCADE,
    item_id UUID NOT NULL REFERENCES itens_contratacao(id) ON DELETE CASCADE,
    excluido BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(sessao_id, item_id)
);

CREATE INDEX idx_sessao_itens_sessao ON sessao_itens(sessao_id);

-- ── Resultados materializados ─────────────────────────────
CREATE TABLE IF NOT EXISTS sessao_resultados (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sessao_id UUID NOT NULL REFERENCES sessoes_comparacao(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('por_item', 'por_edital', 'analise_ia')),
    dados JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_sessao_resultados_sessao ON sessao_resultados(sessao_id);

-- ============================================================
-- RLS Policies
-- Padrão: membros da org leem, dono modifica/deleta
-- ============================================================

ALTER TABLE sessoes_comparacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessao_licitacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessao_itens ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessao_resultados ENABLE ROW LEVEL SECURITY;

-- sessoes_comparacao
CREATE POLICY "Membro vê sessões da org"
    ON sessoes_comparacao FOR SELECT TO authenticated
    USING (org_id IN (SELECT get_user_org_ids()));

CREATE POLICY "Usuário cria sessão"
    ON sessoes_comparacao FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid() AND org_id IN (SELECT get_user_org_ids()));

CREATE POLICY "Dono atualiza sessão"
    ON sessoes_comparacao FOR UPDATE TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "Dono remove sessão"
    ON sessoes_comparacao FOR DELETE TO authenticated
    USING (user_id = auth.uid());

-- sessao_licitacoes (via sessão do dono)
CREATE POLICY "Membro vê seleção licitações"
    ON sessao_licitacoes FOR SELECT TO authenticated
    USING (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE org_id IN (SELECT get_user_org_ids())
    ));

CREATE POLICY "Dono gerencia seleção licitações"
    ON sessao_licitacoes FOR INSERT TO authenticated
    WITH CHECK (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE user_id = auth.uid()
    ));

CREATE POLICY "Dono atualiza seleção licitações"
    ON sessao_licitacoes FOR UPDATE TO authenticated
    USING (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE user_id = auth.uid()
    ));

CREATE POLICY "Dono remove seleção licitações"
    ON sessao_licitacoes FOR DELETE TO authenticated
    USING (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE user_id = auth.uid()
    ));

-- sessao_itens (via sessão do dono)
CREATE POLICY "Membro vê seleção itens"
    ON sessao_itens FOR SELECT TO authenticated
    USING (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE org_id IN (SELECT get_user_org_ids())
    ));

CREATE POLICY "Dono gerencia seleção itens"
    ON sessao_itens FOR INSERT TO authenticated
    WITH CHECK (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE user_id = auth.uid()
    ));

CREATE POLICY "Dono atualiza seleção itens"
    ON sessao_itens FOR UPDATE TO authenticated
    USING (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE user_id = auth.uid()
    ));

CREATE POLICY "Dono remove seleção itens"
    ON sessao_itens FOR DELETE TO authenticated
    USING (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE user_id = auth.uid()
    ));

-- sessao_resultados (via sessão do dono)
CREATE POLICY "Membro vê resultados"
    ON sessao_resultados FOR SELECT TO authenticated
    USING (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE org_id IN (SELECT get_user_org_ids())
    ));

CREATE POLICY "Dono gerencia resultados"
    ON sessao_resultados FOR INSERT TO authenticated
    WITH CHECK (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE user_id = auth.uid()
    ));

CREATE POLICY "Dono remove resultados"
    ON sessao_resultados FOR DELETE TO authenticated
    USING (sessao_id IN (
        SELECT id FROM sessoes_comparacao WHERE user_id = auth.uid()
    ));
