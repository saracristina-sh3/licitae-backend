-- Evolução do comparativo de mercado v3
-- Adiciona descrição legível do agrupamento

ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS descricao_agrupamento TEXT;
