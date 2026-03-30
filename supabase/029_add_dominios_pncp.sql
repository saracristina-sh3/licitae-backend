-- ============================================================
-- Domínios PNCP — tabelas de referência e configuração por org
-- Manual PNCP API Consultas v1.0 (Seção 5)
-- ============================================================

-- 1. Tabela de referência com todos os valores oficiais do PNCP
CREATE TABLE IF NOT EXISTS dominios_pncp (
    id SERIAL PRIMARY KEY,
    dominio TEXT NOT NULL,
    codigo INTEGER NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    ativo BOOLEAN DEFAULT true,
    UNIQUE(dominio, codigo)
);

CREATE INDEX IF NOT EXISTS idx_dominios_pncp_dominio ON dominios_pncp(dominio);

-- 2. Configuração por organização (quais códigos o admin selecionou)
CREATE TABLE IF NOT EXISTS org_dominios_config (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizacoes(id) ON DELETE CASCADE,
    dominio TEXT NOT NULL,
    codigos_ativos INTEGER[] NOT NULL DEFAULT '{}',
    atualizado_por UUID REFERENCES auth.users(id),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, dominio)
);

CREATE INDEX IF NOT EXISTS idx_org_dominios_config_org ON org_dominios_config(org_id);

-- ============================================================
-- RLS
-- ============================================================

ALTER TABLE dominios_pncp ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Autenticados leem domínios"
    ON dominios_pncp FOR SELECT TO authenticated USING (true);

CREATE POLICY "Service role gerencia domínios"
    ON dominios_pncp FOR ALL TO service_role USING (true);

ALTER TABLE org_dominios_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Membro lê config domínios da org"
    ON org_dominios_config FOR SELECT TO authenticated
    USING (org_id IN (SELECT get_user_org_ids()));

CREATE POLICY "Admin insere config domínios"
    ON org_dominios_config FOR INSERT TO authenticated
    WITH CHECK (org_id IN (SELECT get_user_admin_org_ids()));

CREATE POLICY "Admin atualiza config domínios"
    ON org_dominios_config FOR UPDATE TO authenticated
    USING (org_id IN (SELECT get_user_admin_org_ids()));

CREATE POLICY "Admin remove config domínios"
    ON org_dominios_config FOR DELETE TO authenticated
    USING (org_id IN (SELECT get_user_admin_org_ids()));

-- ============================================================
-- SEED — Instrumento Convocatório (5.1)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome, descricao) VALUES
('instrumento_convocatorio', 1, 'Edital', 'Diálogo competitivo, concurso, concorrência, pregão, manifestação de interesse, pré-qualificação e credenciamento'),
('instrumento_convocatorio', 2, 'Aviso de Contratação Direta', 'Dispensa com Disputa'),
('instrumento_convocatorio', 3, 'Ato que autoriza a Contratação Direta', 'Dispensa sem Disputa ou Inexigibilidade')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Modalidade de Contratação (5.2)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('modalidade_contratacao', 1, 'Leilão - Eletrônico'),
('modalidade_contratacao', 2, 'Diálogo Competitivo'),
('modalidade_contratacao', 3, 'Concurso'),
('modalidade_contratacao', 4, 'Concorrência - Eletrônica'),
('modalidade_contratacao', 5, 'Concorrência - Presencial'),
('modalidade_contratacao', 6, 'Pregão - Eletrônico'),
('modalidade_contratacao', 7, 'Pregão - Presencial'),
('modalidade_contratacao', 8, 'Dispensa de Licitação'),
('modalidade_contratacao', 9, 'Inexigibilidade'),
('modalidade_contratacao', 10, 'Manifestação de Interesse'),
('modalidade_contratacao', 11, 'Pré-qualificação'),
('modalidade_contratacao', 12, 'Credenciamento'),
('modalidade_contratacao', 13, 'Leilão - Presencial')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Modo de Disputa (5.3)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('modo_disputa', 1, 'Aberto'),
('modo_disputa', 2, 'Fechado'),
('modo_disputa', 3, 'Aberto-Fechado'),
('modo_disputa', 4, 'Dispensa Com Disputa'),
('modo_disputa', 5, 'Não se aplica'),
('modo_disputa', 6, 'Fechado-Aberto')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Critério de Julgamento (5.4)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('criterio_julgamento', 1, 'Menor preço'),
('criterio_julgamento', 2, 'Maior desconto'),
('criterio_julgamento', 4, 'Técnica e preço'),
('criterio_julgamento', 5, 'Maior lance'),
('criterio_julgamento', 6, 'Maior retorno econômico'),
('criterio_julgamento', 7, 'Não se aplica'),
('criterio_julgamento', 8, 'Melhor técnica'),
('criterio_julgamento', 9, 'Conteúdo artístico')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Situação do Item da Contratação (5.6)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome, descricao) VALUES
('situacao_item_contratacao', 1, 'Em Andamento', 'Disputa/seleção do fornecedor não finalizada'),
('situacao_item_contratacao', 2, 'Homologado', 'Fornecedor informado'),
('situacao_item_contratacao', 3, 'Anulado/Revogado/Cancelado', 'Cancelado conforme justificativa'),
('situacao_item_contratacao', 4, 'Deserto', 'Sem fornecedores interessados'),
('situacao_item_contratacao', 5, 'Fracassado', 'Fornecedores desclassificados ou inabilitados')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Tipo de Benefício (5.7)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('tipo_beneficio', 1, 'Participação exclusiva para ME/EPP'),
('tipo_beneficio', 2, 'Subcontratação para ME/EPP'),
('tipo_beneficio', 3, 'Cota reservada para ME/EPP'),
('tipo_beneficio', 4, 'Sem benefício'),
('tipo_beneficio', 5, 'Não se aplica')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Tipo de Contrato (5.9)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome, descricao) VALUES
('tipo_contrato', 1, 'Contrato (termo inicial)', 'Acordo formal recíproco de vontades'),
('tipo_contrato', 2, 'Comodato', 'Concessão de uso gratuito de bem móvel ou imóvel'),
('tipo_contrato', 3, 'Arrendamento', 'Cessão de bem por período mediante pagamento'),
('tipo_contrato', 4, 'Concessão', 'Contrato com empresa privada para serviço público'),
('tipo_contrato', 5, 'Termo de Adesão', 'Uma das partes estipula todas as cláusulas'),
('tipo_contrato', 6, 'Convênio', 'Acordos para realização de objetivo em comum'),
('tipo_contrato', 7, 'Empenho', 'Promessa de pagamento por parte do Estado'),
('tipo_contrato', 8, 'Outros', 'Outros tipos não listados'),
('tipo_contrato', 9, 'Termo de Execução Descentralizada (TED)', 'Descentralização de crédito entre órgãos da União'),
('tipo_contrato', 10, 'Acordo de Cooperação Técnica (ACT)', 'Acordos para execução de programas de trabalho'),
('tipo_contrato', 11, 'Termo de Compromisso', 'Acordo para cumprir compromisso entre as partes'),
('tipo_contrato', 12, 'Carta Contrato', 'Formaliza acordo quando a lei dispensa contrato')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Categoria do Processo (5.11)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('categoria_processo', 1, 'Cessão'),
('categoria_processo', 2, 'Compras'),
('categoria_processo', 3, 'Informática (TIC)'),
('categoria_processo', 4, 'Internacional'),
('categoria_processo', 5, 'Locação Imóveis'),
('categoria_processo', 6, 'Mão de Obra'),
('categoria_processo', 7, 'Obras'),
('categoria_processo', 8, 'Serviços'),
('categoria_processo', 9, 'Serviços de Engenharia'),
('categoria_processo', 10, 'Serviços de Saúde'),
('categoria_processo', 11, 'Alienação de bens móveis/imóveis')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Tipo de Documento (5.12)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('tipo_documento', 1, 'Aviso de Contratação Direta'),
('tipo_documento', 2, 'Edital'),
('tipo_documento', 3, 'Minuta do Contrato'),
('tipo_documento', 4, 'Termo de Referência'),
('tipo_documento', 5, 'Anteprojeto'),
('tipo_documento', 6, 'Projeto Básico'),
('tipo_documento', 7, 'Estudo Técnico Preliminar'),
('tipo_documento', 8, 'Projeto Executivo'),
('tipo_documento', 9, 'Mapa de Riscos'),
('tipo_documento', 10, 'DFD'),
('tipo_documento', 11, 'Ata de Registro de Preço'),
('tipo_documento', 12, 'Contrato'),
('tipo_documento', 13, 'Termo de Rescisão'),
('tipo_documento', 14, 'Termo Aditivo'),
('tipo_documento', 15, 'Termo de Apostilamento'),
('tipo_documento', 16, 'Outros documentos do processo'),
('tipo_documento', 17, 'Nota de Empenho'),
('tipo_documento', 18, 'Relatório Final de Contrato')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Porte da Empresa (5.14)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome, descricao) VALUES
('porte_empresa', 1, 'ME', 'Microempresa'),
('porte_empresa', 2, 'EPP', 'Empresa de pequeno porte'),
('porte_empresa', 3, 'Demais', 'Demais empresas'),
('porte_empresa', 4, 'Não se aplica', 'Fornecedor pessoa física'),
('porte_empresa', 5, 'Não informado', 'Porte não informado')
ON CONFLICT (dominio, codigo) DO NOTHING;

-- ============================================================
-- SEED — Categoria do Item do Plano de Contratações (5.16)
-- ============================================================
INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('categoria_item_pca', 1, 'Material'),
('categoria_item_pca', 2, 'Serviço'),
('categoria_item_pca', 3, 'Obras'),
('categoria_item_pca', 4, 'Serviços de Engenharia'),
('categoria_item_pca', 5, 'Soluções de TIC'),
('categoria_item_pca', 6, 'Locação de Imóveis'),
('categoria_item_pca', 7, 'Alienação/Concessão/Permissão'),
('categoria_item_pca', 8, 'Obras e Serviços de Engenharia')
ON CONFLICT (dominio, codigo) DO NOTHING;
