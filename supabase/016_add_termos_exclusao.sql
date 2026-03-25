-- ============================================================
-- 016: Termos de exclusão por organização
-- Permite que orgs configurem termos para ocultar licitações
-- irrelevantes dos resultados de busca.
-- ============================================================

-- Tabela de termos de exclusão por organização
CREATE TABLE org_termos_exclusao (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  org_id UUID NOT NULL REFERENCES organizacoes(id) ON DELETE CASCADE,
  termo TEXT NOT NULL,
  criado_por UUID REFERENCES auth.users(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, termo)
);

-- Index para queries frequentes
CREATE INDEX idx_org_termos_exclusao_org_id ON org_termos_exclusao(org_id);

-- RLS
ALTER TABLE org_termos_exclusao ENABLE ROW LEVEL SECURITY;

-- Service role (scraper) tem acesso total
CREATE POLICY "Service role acesso total"
  ON org_termos_exclusao FOR ALL
  USING (auth.role() = 'service_role');

-- Membros da org podem ler
CREATE POLICY "Membros podem ler termos da org"
  ON org_termos_exclusao FOR SELECT
  USING (org_id IN (SELECT get_user_org_ids()));

-- Apenas admins podem inserir
CREATE POLICY "Admins podem inserir termos"
  ON org_termos_exclusao FOR INSERT
  WITH CHECK (org_id IN (SELECT get_user_admin_org_ids()));

-- Apenas admins podem deletar
CREATE POLICY "Admins podem deletar termos"
  ON org_termos_exclusao FOR DELETE
  USING (org_id IN (SELECT get_user_admin_org_ids()));
