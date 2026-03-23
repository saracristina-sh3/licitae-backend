-- Expande user_config com campos de configuração de busca
alter table user_config
  add column if not exists modalidades integer[] default '{6,7,8,9,12}',
  add column if not exists fontes text[] default '{PNCP,QUERIDO_DIARIO,TCE_RJ}',
  add column if not exists termos_alta text[] default '{"permissão de uso","licença de uso","cessão de uso","locação de software","sistema integrado de gestão"}',
  add column if not exists termos_media text[] default '{software,"sistema de gestão","solução tecnológica"}',
  add column if not exists termos_me_epp text[] default '{"exclusivo para microempresa","exclusivo para me","exclusivo me/epp","exclusivo me e epp","participação exclusiva","cota reservada","lei complementar 123"}',
  add column if not exists dias_retroativos integer default 7;
