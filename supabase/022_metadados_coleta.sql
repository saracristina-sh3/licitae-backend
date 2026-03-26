-- Migration 022: Metadados de coleta para rastreabilidade
-- Adiciona campos de auditoria nas tabelas de itens e resultados.

-- Estado de sincronização por item
ALTER TABLE itens_contratacao ADD COLUMN IF NOT EXISTS coletado_em TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE itens_contratacao ADD COLUMN IF NOT EXISTS versao_coletor TEXT DEFAULT 'v1';

-- Estado de sincronização por resultado
ALTER TABLE resultados_item ADD COLUMN IF NOT EXISTS coletado_em TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE resultados_item ADD COLUMN IF NOT EXISTS versao_coletor TEXT DEFAULT 'v1';
