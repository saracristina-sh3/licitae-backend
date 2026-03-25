-- ============================================================
-- 017: Tabelas materializadas do comparativo de mercado
-- Calculadas pelo cron (market_analyzer.py), lidas pelo frontend.
-- ============================================================

-- Resumo por plataforma (cards do topo)
CREATE TABLE comparativo_plataformas (
  id SERIAL PRIMARY KEY,
  plataforma_nome TEXT NOT NULL,
  plataforma_id INT NOT NULL,
  total_itens INT NOT NULL DEFAULT 0,
  valor_medio_unitario NUMERIC(14,2) NOT NULL DEFAULT 0,
  desconto_medio NUMERIC(5,2),
  vitorias INT NOT NULL DEFAULT 0,
  uf TEXT,  -- NULL = todas as UFs
  calculado_em TIMESTAMPTZ DEFAULT now(),
  UNIQUE(plataforma_id, uf)
);

-- Itens comparáveis entre plataformas
CREATE TABLE comparativo_itens (
  id SERIAL PRIMARY KEY,
  chave_agrupamento TEXT NOT NULL,
  descricao TEXT NOT NULL,
  ncm_nbs_codigo TEXT,
  unidade_medida TEXT,
  menor_preco_plataforma TEXT NOT NULL,
  uf TEXT,  -- NULL = todas as UFs
  calculado_em TIMESTAMPTZ DEFAULT now(),
  UNIQUE(chave_agrupamento, uf)
);

-- Preços por plataforma para cada item comparável
CREATE TABLE comparativo_itens_precos (
  id SERIAL PRIMARY KEY,
  comparativo_item_id INT NOT NULL REFERENCES comparativo_itens(id) ON DELETE CASCADE,
  plataforma_nome TEXT NOT NULL,
  plataforma_id INT NOT NULL,
  valor_medio NUMERIC(14,2) NOT NULL,
  total_ocorrencias INT NOT NULL DEFAULT 0,
  economia_media NUMERIC(5,2),
  UNIQUE(comparativo_item_id, plataforma_id)
);

CREATE INDEX idx_comparativo_plataformas_uf ON comparativo_plataformas(uf);
CREATE INDEX idx_comparativo_itens_uf ON comparativo_itens(uf);
CREATE INDEX idx_comparativo_itens_precos_item ON comparativo_itens_precos(comparativo_item_id);

-- RLS
ALTER TABLE comparativo_plataformas ENABLE ROW LEVEL SECURITY;
ALTER TABLE comparativo_itens ENABLE ROW LEVEL SECURITY;
ALTER TABLE comparativo_itens_precos ENABLE ROW LEVEL SECURITY;

-- Service role (cron) tem acesso total
CREATE POLICY "Service role acesso total" ON comparativo_plataformas FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role acesso total" ON comparativo_itens FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role acesso total" ON comparativo_itens_precos FOR ALL USING (auth.role() = 'service_role');

-- Autenticados podem ler
CREATE POLICY "Autenticados podem ler" ON comparativo_plataformas FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Autenticados podem ler" ON comparativo_itens FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Autenticados podem ler" ON comparativo_itens_precos FOR SELECT USING (auth.role() = 'authenticated');
