-- Adiciona campo de exclusividade ME/EPP na tabela licitacoes
alter table licitacoes add column if not exists exclusivo_me_epp boolean default false;

create index if not exists idx_licitacoes_me_epp on licitacoes(exclusivo_me_epp) where exclusivo_me_epp = true;
