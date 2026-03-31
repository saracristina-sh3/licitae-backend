-- Remove tabela deprecated org_termos_exclusao.
-- Dados já foram migrados para org_config.termos_exclusao (TEXT[]) na migration 031.

DROP TABLE IF EXISTS org_termos_exclusao;
