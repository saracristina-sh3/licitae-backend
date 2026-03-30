-- Adiciona colunas score e urgencia na tabela licitacoes
-- Esses campos são calculados pelo prospection_engine mas nunca foram adicionados à tabela

ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS score NUMERIC(5,1);
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS urgencia TEXT;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS informacao_complementar TEXT;

CREATE INDEX IF NOT EXISTS idx_licitacoes_score ON licitacoes(score DESC NULLS LAST);
