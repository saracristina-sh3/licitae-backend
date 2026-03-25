-- ============================================================
-- 021: Evolução do comparativo de mercado (v2)
-- Scores, vitórias ponderadas, separação hom/est, auditoria.
-- ============================================================

-- ── comparativo_plataformas ──

ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS mediana_unitario NUMERIC(14,2);
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS cv_medio NUMERIC(5,2);
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS total_grupos_comparaveis INT DEFAULT 0;
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS total_grupos_alta_confianca INT DEFAULT 0;
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS proporcao_vitorias NUMERIC(5,2);
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS proporcao_homologados NUMERIC(5,2);
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS score_comparabilidade_medio NUMERIC(5,2);
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS vitorias_ponderadas NUMERIC(8,2) DEFAULT 0;
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS vitorias_alta_confianca INT DEFAULT 0;
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS ranking_medio NUMERIC(5,2);
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS delta_medio_para_lider NUMERIC(5,2);
ALTER TABLE comparativo_plataformas ADD COLUMN IF NOT EXISTS versao_algoritmo TEXT DEFAULT 'v2';

-- ── comparativo_itens ──

ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS score_comparabilidade NUMERIC(5,2);
ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS faixa_confiabilidade TEXT;
ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS fonte_predominante TEXT DEFAULT 'misto';
ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS unidade_predominante TEXT;
ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS taxa_consistencia_unidade NUMERIC(5,2);
ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS total_observacoes INT DEFAULT 0;
ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS versao_algoritmo TEXT DEFAULT 'v2';
ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS metodo_agrupamento TEXT DEFAULT 'ncm_lexical';
ALTER TABLE comparativo_itens ADD COLUMN IF NOT EXISTS metodo_outlier TEXT DEFAULT 'iqr';

-- ── comparativo_itens_precos ──

ALTER TABLE comparativo_itens_precos ADD COLUMN IF NOT EXISTS mediana NUMERIC(14,2);
ALTER TABLE comparativo_itens_precos ADD COLUMN IF NOT EXISTS cv NUMERIC(5,2);
ALTER TABLE comparativo_itens_precos ADD COLUMN IF NOT EXISTS percentil_25 NUMERIC(14,2);
ALTER TABLE comparativo_itens_precos ADD COLUMN IF NOT EXISTS percentil_75 NUMERIC(14,2);
ALTER TABLE comparativo_itens_precos ADD COLUMN IF NOT EXISTS total_homologados INT DEFAULT 0;
ALTER TABLE comparativo_itens_precos ADD COLUMN IF NOT EXISTS total_estimados INT DEFAULT 0;
ALTER TABLE comparativo_itens_precos ADD COLUMN IF NOT EXISTS fonte_predominante TEXT DEFAULT 'misto';
