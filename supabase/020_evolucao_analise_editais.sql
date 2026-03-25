-- ============================================================
-- 020: Evolução da análise de editais (v2)
-- Adiciona scores, achados estruturados, auditoria e métricas.
-- Sem breaking change: campos text[] originais mantidos.
-- ============================================================

-- Auditoria e qualidade
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS versao_algoritmo TEXT DEFAULT 'v2';
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS metodo_extracao TEXT DEFAULT 'pdfminer';
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS qualidade_extracao NUMERIC(4,2);
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS faixa_qualidade TEXT;

-- Arquivo escolhido
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS arquivo_escolhido TEXT;
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS score_arquivo NUMERIC(5,2);
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS motivo_arquivo TEXT;

-- Confiança
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS score_confianca NUMERIC(5,1);
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS faixa_confianca TEXT;

-- Risco
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS score_risco NUMERIC(5,1);
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS nivel_risco TEXT;
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS fatores_risco JSONB DEFAULT '[]';

-- Achados estruturados (com taxonomia, confiança, trechos)
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS documentos_estruturados JSONB;
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS requisitos_estruturados JSONB;
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS riscos_estruturados JSONB;
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS qualificacao_estruturada JSONB;
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS prazos_classificados JSONB;

-- Métricas operacionais
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS tempo_processamento_ms INT;
ALTER TABLE analise_editais ADD COLUMN IF NOT EXISTS houve_fallback BOOLEAN DEFAULT false;
