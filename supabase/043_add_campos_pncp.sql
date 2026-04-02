-- ============================================================
-- 043: Novos campos da API PNCP que estavam sendo descartados
-- ============================================================

-- Campos da contratação
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS srp BOOLEAN DEFAULT FALSE;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS numero_controle_pncp TEXT;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS amparo_legal_codigo TEXT;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS amparo_legal_descricao TEXT;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS numero_processo TEXT;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS link_sistema_origem TEXT;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS tipo_instrumento_convocatorio TEXT;
ALTER TABLE licitacoes ADD COLUMN IF NOT EXISTS data_atualizacao TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_licitacoes_srp ON licitacoes(srp) WHERE srp = TRUE;
CREATE INDEX IF NOT EXISTS idx_licitacoes_numero_controle ON licitacoes(numero_controle_pncp);
