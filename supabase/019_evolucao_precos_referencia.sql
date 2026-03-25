-- ============================================================
-- 019: Evolução do schema de preços de referência (v2)
-- Adiciona separação homologado/estimado, percentis, score de
-- confiabilidade e campos de auditoria.
-- ============================================================

-- ── preco_referencia_licitacao ──

-- Separação homologado vs estimado
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS valor_media_homologado NUMERIC(14,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS valor_mediana_homologado NUMERIC(14,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS valor_media_saneada_homologado NUMERIC(14,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS cv_homologado NUMERIC(5,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS total_homologados INT DEFAULT 0;

ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS valor_media_estimado NUMERIC(14,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS valor_mediana_estimado NUMERIC(14,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS cv_estimado NUMERIC(5,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS total_estimados INT DEFAULT 0;

ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS fonte_predominante TEXT DEFAULT 'misto';

-- Percentis
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS percentil_25 NUMERIC(14,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS percentil_75 NUMERIC(14,2);

-- Itens: percentis
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS item_percentil_25 NUMERIC(14,2);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS item_percentil_75 NUMERIC(14,2);

-- Confiabilidade
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS score_confiabilidade NUMERIC(5,1);
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS faixa_confiabilidade TEXT;

-- Auditoria
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS versao_algoritmo TEXT DEFAULT 'v2';
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS metodo_similaridade TEXT DEFAULT 'text_search';
ALTER TABLE preco_referencia_licitacao ADD COLUMN IF NOT EXISTS metodo_outlier TEXT DEFAULT 'iqr+trimmed_mean';

-- ── preco_referencia_detalhe ──

ALTER TABLE preco_referencia_detalhe ADD COLUMN IF NOT EXISTS score_similaridade NUMERIC(5,2);
ALTER TABLE preco_referencia_detalhe ADD COLUMN IF NOT EXISTS fonte_preco TEXT DEFAULT 'homologado';

-- ── preco_referencia_itens ──

ALTER TABLE preco_referencia_itens ADD COLUMN IF NOT EXISTS fonte_preco TEXT DEFAULT 'estimado';
ALTER TABLE preco_referencia_itens ADD COLUMN IF NOT EXISTS score_similaridade NUMERIC(5,2);
ALTER TABLE preco_referencia_itens ADD COLUMN IF NOT EXISTS compativel_unidade BOOLEAN DEFAULT true;
