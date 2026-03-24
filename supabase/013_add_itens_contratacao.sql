-- ============================================================
-- Itens de contratação + resultados + plataformas PNCP
-- Fase 1: Coletor de Itens para Inteligência Competitiva
-- ============================================================

-- Plataformas PNCP (cache de idUsuario → nome)
create table if not exists plataformas_pncp (
    id_usuario int primary key,
    nome text not null,
    tipo text,
    ativo boolean default true,
    total_contratacoes int default 0,
    updated_at timestamptz default now()
);

-- Itens de contratação com preços estimados
create table if not exists itens_contratacao (
    id uuid default uuid_generate_v4() primary key,
    licitacao_hash text,
    cnpj_orgao text not null,
    ano_compra int not null,
    sequencial_compra int not null,
    numero_item int not null,
    descricao text,
    ncm_nbs_codigo text,
    quantidade numeric,
    unidade_medida text,
    valor_unitario_estimado numeric(15,2),
    valor_total_estimado numeric(15,2),
    tem_resultado boolean default false,
    plataforma_id int references plataformas_pncp(id_usuario),
    plataforma_nome text,
    uf char(2),
    municipio text,
    codigo_ibge text,
    modalidade_id int,
    created_at timestamptz default now(),
    unique(cnpj_orgao, ano_compra, sequencial_compra, numero_item)
);

create index if not exists idx_itens_ncm on itens_contratacao(ncm_nbs_codigo);
create index if not exists idx_itens_plataforma on itens_contratacao(plataforma_id);
create index if not exists idx_itens_uf on itens_contratacao(uf);
create index if not exists idx_itens_modalidade on itens_contratacao(modalidade_id);
create index if not exists idx_itens_licitacao_hash on itens_contratacao(licitacao_hash);
create index if not exists idx_itens_descricao_trgm on itens_contratacao using gin(descricao gin_trgm_ops);

-- Resultados (preço homologado + fornecedor vencedor)
create table if not exists resultados_item (
    id uuid default uuid_generate_v4() primary key,
    item_id uuid references itens_contratacao(id) on delete cascade,
    sequencial_resultado int not null,
    valor_unitario_homologado numeric(15,2),
    valor_total_homologado numeric(15,2),
    quantidade_homologada numeric,
    percentual_desconto numeric(5,2),
    cnpj_fornecedor text,
    nome_fornecedor text,
    porte_fornecedor text,
    data_resultado timestamptz,
    created_at timestamptz default now(),
    unique(item_id, sequencial_resultado)
);

create index if not exists idx_resultados_fornecedor on resultados_item(cnpj_fornecedor);
create index if not exists idx_resultados_item on resultados_item(item_id);

-- ── RLS ──────────────────────────────────────────────────────

alter table plataformas_pncp enable row level security;
alter table itens_contratacao enable row level security;
alter table resultados_item enable row level security;

-- plataformas_pncp
create policy "Autenticados veem plataformas"
    on plataformas_pncp for select to authenticated using (true);
create policy "Service role gerencia plataformas"
    on plataformas_pncp for all to service_role using (true);

-- itens_contratacao
create policy "Autenticados veem itens"
    on itens_contratacao for select to authenticated using (true);
create policy "Service role gerencia itens"
    on itens_contratacao for all to service_role using (true);

-- resultados_item
create policy "Autenticados veem resultados"
    on resultados_item for select to authenticated using (true);
create policy "Service role gerencia resultados"
    on resultados_item for all to service_role using (true);
