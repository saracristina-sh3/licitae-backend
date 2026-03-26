-- Tabela para armazenar análises de IA (Claude) sobre licitações
CREATE TABLE IF NOT EXISTS analise_ia_licitacao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    licitacao_id UUID NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL DEFAULT 'completa',

    -- Recomendação principal
    recomendacao TEXT,
    score_viabilidade SMALLINT,
    resumo TEXT,

    -- Análise estruturada
    riscos_identificados JSONB DEFAULT '[]'::jsonb,
    oportunidades JSONB DEFAULT '[]'::jsonb,
    preco_sugerido NUMERIC(14,2),
    margem_sugerida NUMERIC(5,2),
    concorrentes_provaveis JSONB DEFAULT '[]'::jsonb,
    perguntas_esclarecimento TEXT[] DEFAULT '{}',

    -- Metadados técnicos
    modelo_usado TEXT,
    tokens_input INT,
    tokens_output INT,
    custo_usd NUMERIC(8,4),
    tempo_ms INT,

    created_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(licitacao_id, tipo)
);

CREATE INDEX IF NOT EXISTS idx_analise_ia_licitacao_id ON analise_ia_licitacao(licitacao_id);
CREATE INDEX IF NOT EXISTS idx_analise_ia_score ON analise_ia_licitacao(score_viabilidade DESC);

-- RLS
ALTER TABLE analise_ia_licitacao ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Leitura por usuários autenticados"
    ON analise_ia_licitacao FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Escrita por service_role"
    ON analise_ia_licitacao FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
