-- ============================================================
-- 023: Corrigir overflow em campos NUMERIC(5,2)
-- delta_medio_para_lider pode ser > 999% em casos extremos
-- ============================================================

ALTER TABLE comparativo_plataformas ALTER COLUMN delta_medio_para_lider TYPE NUMERIC(8,2);
ALTER TABLE comparativo_plataformas ALTER COLUMN ranking_medio TYPE NUMERIC(8,2);
ALTER TABLE comparativo_plataformas ALTER COLUMN score_comparabilidade_medio TYPE NUMERIC(8,2);
ALTER TABLE comparativo_plataformas ALTER COLUMN proporcao_vitorias TYPE NUMERIC(8,2);
ALTER TABLE comparativo_plataformas ALTER COLUMN proporcao_homologados TYPE NUMERIC(8,2);
ALTER TABLE comparativo_plataformas ALTER COLUMN cv_medio TYPE NUMERIC(8,2);
