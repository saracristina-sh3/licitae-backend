-- ============================================================
-- Habilitar Supabase Realtime nas tabelas de alertas
-- Permite que o frontend escute INSERTs em tempo real
-- ============================================================

-- Prazo alertas (alertas de prazo proximo)
ALTER PUBLICATION supabase_realtime ADD TABLE prazo_alertas;

-- Monitoramento alertas (mudancas em licitacoes monitoradas)
ALTER PUBLICATION supabase_realtime ADD TABLE monitoramento_alertas;
