-- ============================================================
-- Adiciona campo material_ou_servico na tabela itens_contratacao
-- Vem direto da API PNCP: "M" = Material, "S" = Serviço
-- Usado para melhorar matching: só compara Material com Material
-- ============================================================

ALTER TABLE itens_contratacao ADD COLUMN IF NOT EXISTS material_ou_servico CHAR(1);
ALTER TABLE itens_contratacao ADD COLUMN IF NOT EXISTS tipo_beneficio_id INTEGER;
ALTER TABLE itens_contratacao ADD COLUMN IF NOT EXISTS criterio_julgamento_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_itens_material_servico ON itens_contratacao(material_ou_servico);

-- Popula itens existentes: tenta inferir do NCM (se começa com 3 ou 4 = Material)
-- Na prática, a maioria vai ficar NULL e ser preenchida na próxima coleta
