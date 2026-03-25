-- ============================================================
-- 018: Tabelas materializadas de preços de referência
-- Calculadas pelo cron (price_analyzer.py), lidas pelo frontend.
-- ============================================================

-- Resumo de preços por licitação
CREATE TABLE preco_referencia_licitacao (
  id SERIAL PRIMARY KEY,
  licitacao_id UUID NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
  -- Licitações similares
  total_similares INT NOT NULL DEFAULT 0,
  valor_minimo NUMERIC(14,2),
  valor_maximo NUMERIC(14,2),
  valor_media NUMERIC(14,2),
  valor_mediana NUMERIC(14,2),
  valor_media_saneada NUMERIC(14,2),
  coeficiente_variacao NUMERIC(5,2),
  amostra_suficiente BOOLEAN DEFAULT false,
  -- Itens similares (IC)
  total_itens_similares INT NOT NULL DEFAULT 0,
  item_minimo_unitario NUMERIC(14,2),
  item_maximo_unitario NUMERIC(14,2),
  item_media_unitario NUMERIC(14,2),
  item_mediana_unitario NUMERIC(14,2),
  item_media_saneada NUMERIC(14,2),
  item_desconto_medio NUMERIC(5,2),
  item_coeficiente_variacao NUMERIC(5,2),
  -- Metadados
  janela_meses INT NOT NULL DEFAULT 12,
  calculado_em TIMESTAMPTZ DEFAULT now(),
  UNIQUE(licitacao_id)
);

-- Licitações similares usadas no cálculo
CREATE TABLE preco_referencia_detalhe (
  id SERIAL PRIMARY KEY,
  preco_referencia_id INT NOT NULL REFERENCES preco_referencia_licitacao(id) ON DELETE CASCADE,
  licitacao_similar_id UUID NOT NULL REFERENCES licitacoes(id),
  municipio_nome TEXT,
  uf TEXT,
  objeto TEXT,
  modalidade TEXT,
  valor_homologado NUMERIC(14,2),
  data_publicacao TIMESTAMPTZ
);

-- Itens similares por plataforma
CREATE TABLE preco_referencia_itens (
  id SERIAL PRIMARY KEY,
  preco_referencia_id INT NOT NULL REFERENCES preco_referencia_licitacao(id) ON DELETE CASCADE,
  descricao TEXT,
  unidade_medida TEXT,
  valor_unitario NUMERIC(14,2),
  plataforma_nome TEXT,
  municipio TEXT,
  uf TEXT,
  nome_fornecedor TEXT,
  percentual_desconto NUMERIC(5,2)
);

-- Resumo por plataforma
CREATE TABLE preco_referencia_plataformas (
  id SERIAL PRIMARY KEY,
  preco_referencia_id INT NOT NULL REFERENCES preco_referencia_licitacao(id) ON DELETE CASCADE,
  plataforma_nome TEXT NOT NULL,
  media_unitario NUMERIC(14,2) NOT NULL,
  total_itens INT NOT NULL DEFAULT 0,
  UNIQUE(preco_referencia_id, plataforma_nome)
);

-- Indexes
CREATE INDEX idx_preco_ref_lic_id ON preco_referencia_licitacao(licitacao_id);
CREATE INDEX idx_preco_ref_detalhe_ref ON preco_referencia_detalhe(preco_referencia_id);
CREATE INDEX idx_preco_ref_itens_ref ON preco_referencia_itens(preco_referencia_id);
CREATE INDEX idx_preco_ref_plat_ref ON preco_referencia_plataformas(preco_referencia_id);

-- RLS
ALTER TABLE preco_referencia_licitacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE preco_referencia_detalhe ENABLE ROW LEVEL SECURITY;
ALTER TABLE preco_referencia_itens ENABLE ROW LEVEL SECURITY;
ALTER TABLE preco_referencia_plataformas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role acesso total" ON preco_referencia_licitacao FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role acesso total" ON preco_referencia_detalhe FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role acesso total" ON preco_referencia_itens FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role acesso total" ON preco_referencia_plataformas FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Autenticados podem ler" ON preco_referencia_licitacao FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Autenticados podem ler" ON preco_referencia_detalhe FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Autenticados podem ler" ON preco_referencia_itens FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Autenticados podem ler" ON preco_referencia_plataformas FOR SELECT USING (auth.role() = 'authenticated');
