-- ============================================================
-- Adiciona campo de plano (free/pro) na user_config
-- ============================================================

alter table user_config
  add column if not exists plano text default 'free' check (plano in ('free', 'pro')),
  add column if not exists plano_expira_em timestamptz,
  add column if not exists apple_transaction_id text;

create index if not exists idx_user_config_plano on user_config(plano);
