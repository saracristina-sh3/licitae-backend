-- ============================================================
-- Backfill: preenche codigo_ibge nos itens que estao NULL
-- Usa a tabela licitacoes → municipios para resolver
-- ============================================================

UPDATE itens_contratacao ic
SET codigo_ibge = m.codigo_ibge,
    uf = COALESCE(ic.uf, m.uf),
    municipio = COALESCE(ic.municipio, m.nome)
FROM licitacoes l
JOIN municipios m ON m.id = l.municipio_id
WHERE ic.licitacao_hash = l.hash_dedup
  AND ic.codigo_ibge IS NULL
  AND l.municipio_id IS NOT NULL;

-- Fallback: itens sem licitacao_hash mas com cnpj+ano+seq
UPDATE itens_contratacao ic
SET codigo_ibge = m.codigo_ibge,
    uf = COALESCE(ic.uf, m.uf),
    municipio = COALESCE(ic.municipio, m.nome)
FROM licitacoes l
JOIN municipios m ON m.id = l.municipio_id
WHERE ic.cnpj_orgao = l.cnpj_orgao
  AND ic.codigo_ibge IS NULL
  AND l.municipio_id IS NOT NULL;
