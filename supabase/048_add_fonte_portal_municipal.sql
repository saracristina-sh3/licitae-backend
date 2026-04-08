-- Adiciona PORTAL_MUNICIPAL ao enum fonte_tipo
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'PORTAL_MUNICIPAL'
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'fonte_tipo')
    ) THEN
        ALTER TYPE fonte_tipo ADD VALUE 'PORTAL_MUNICIPAL';
    END IF;
END$$;

-- Tabela de log de scraping de portais municipais (rastreamento por município)
CREATE TABLE IF NOT EXISTS portal_scrape_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_ibge TEXT NOT NULL,
    url_base TEXT NOT NULL,
    scraper_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    licitacoes_encontradas INTEGER DEFAULT 0,
    erro_mensagem TEXT,
    duracao_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portal_scrape_log_ibge
    ON portal_scrape_log(codigo_ibge);
CREATE INDEX IF NOT EXISTS idx_portal_scrape_log_created
    ON portal_scrape_log(created_at DESC);

-- RLS
ALTER TABLE portal_scrape_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role portal_scrape_log"
    ON portal_scrape_log FOR ALL TO service_role USING (true);
