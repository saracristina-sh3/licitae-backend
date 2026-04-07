-- ============================================================
-- Reprospectar automaticamente quando org_config muda
-- ============================================================

-- 1. Adicionar flag de reprospecção pendente
ALTER TABLE org_config
    ADD COLUMN IF NOT EXISTS reprospectar_pendente BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS config_alterada_em TIMESTAMPTZ;

-- 2. Trigger: marca reprospecção pendente ao alterar campos relevantes
CREATE OR REPLACE FUNCTION marcar_reprospectar_pendente()
RETURNS TRIGGER AS $$
BEGIN
    -- Só marca se campos de prospecção realmente mudaram
    IF (
        OLD.ufs IS DISTINCT FROM NEW.ufs
        OR OLD.fpm_maximo IS DISTINCT FROM NEW.fpm_maximo
        OR OLD.palavras_chave IS DISTINCT FROM NEW.palavras_chave
        OR OLD.modalidades IS DISTINCT FROM NEW.modalidades
        OR OLD.termos_alta IS DISTINCT FROM NEW.termos_alta
        OR OLD.termos_media IS DISTINCT FROM NEW.termos_media
        OR OLD.termos_exclusao IS DISTINCT FROM NEW.termos_exclusao
        OR OLD.microrregioes IS DISTINCT FROM NEW.microrregioes
        OR OLD.ncms_alvo IS DISTINCT FROM NEW.ncms_alvo
        OR OLD.fontes IS DISTINCT FROM NEW.fontes
    ) THEN
        NEW.reprospectar_pendente := TRUE;
        NEW.config_alterada_em := now();
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_marcar_reprospectar ON org_config;
CREATE TRIGGER trg_marcar_reprospectar
    BEFORE UPDATE ON org_config
    FOR EACH ROW
    EXECUTE FUNCTION marcar_reprospectar_pendente();
