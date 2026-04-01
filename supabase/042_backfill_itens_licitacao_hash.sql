-- ============================================================
-- Backfill: preenche licitacao_hash nos itens que estão NULL.
-- Gera o hash usando o mesmo algoritmo do Python: sha256("PNCP:{cnpj}:{ano}:{seq}")[:32]
-- ============================================================

UPDATE itens_contratacao
SET licitacao_hash = left(encode(sha256(('PNCP:' || cnpj_orgao || ':' || ano_compra || ':' || sequencial_compra)::bytea), 'hex'), 32)
WHERE licitacao_hash IS NULL
  AND cnpj_orgao IS NOT NULL;

-- Verifica quantos ficaram sem hash
DO $$
DECLARE
  v_null_count INT;
BEGIN
  SELECT count(*) INTO v_null_count FROM itens_contratacao WHERE licitacao_hash IS NULL;
  RAISE NOTICE 'Itens com licitacao_hash NULL após backfill: %', v_null_count;
END;
$$;
