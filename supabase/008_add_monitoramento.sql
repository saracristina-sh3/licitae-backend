-- ============================================================
-- Monitoramento de licitações — detecta mudanças no PNCP
-- O usuário ativa/desativa por oportunidade
-- ============================================================

-- Licitações sendo monitoradas
create table if not exists monitoramento (
    id bigint generated always as identity primary key,
    oportunidade_id uuid references oportunidades(id) on delete cascade not null,
    licitacao_id uuid references licitacoes(id) on delete cascade not null,
    user_id uuid references auth.users(id) on delete cascade not null,
    ativo boolean default true,

    -- Snapshot dos campos monitorados (última verificação)
    ultimo_situacao text,
    ultimo_valor_estimado numeric(15,2),
    ultimo_valor_homologado numeric(15,2),
    ultimo_data_encerramento timestamptz,
    ultimo_proposta_aberta boolean,
    ultimo_check_at timestamptz,

    created_at timestamptz default now(),
    unique(oportunidade_id)
);

create index idx_monitoramento_ativo on monitoramento(ativo) where ativo = true;
create index idx_monitoramento_user on monitoramento(user_id);
create index idx_monitoramento_licitacao on monitoramento(licitacao_id);

-- Log de mudanças detectadas
create table if not exists monitoramento_alertas (
    id bigint generated always as identity primary key,
    monitoramento_id bigint references monitoramento(id) on delete cascade not null,
    user_id uuid references auth.users(id) on delete cascade not null,
    licitacao_id uuid references licitacoes(id) on delete cascade not null,

    campo text not null,          -- ex: 'situacao', 'valor_estimado', 'data_encerramento'
    valor_anterior text,
    valor_novo text,
    lido boolean default false,

    created_at timestamptz default now()
);

create index idx_alertas_user_lido on monitoramento_alertas(user_id, lido) where lido = false;
create index idx_alertas_monitoramento on monitoramento_alertas(monitoramento_id);

-- ── RLS ──────────────────────────────────────────────────────

alter table monitoramento enable row level security;
alter table monitoramento_alertas enable row level security;

create policy "Usuário vê seu monitoramento"
    on monitoramento for select to authenticated
    using (user_id = auth.uid());

create policy "Usuário cria monitoramento"
    on monitoramento for insert to authenticated
    with check (user_id = auth.uid());

create policy "Usuário edita seu monitoramento"
    on monitoramento for update to authenticated
    using (user_id = auth.uid());

create policy "Usuário remove seu monitoramento"
    on monitoramento for delete to authenticated
    using (user_id = auth.uid());

create policy "Scraper pode atualizar monitoramento"
    on monitoramento for update to service_role
    using (true);

create policy "Scraper pode inserir alertas"
    on monitoramento_alertas for insert to service_role
    with check (true);

create policy "Usuário vê seus alertas"
    on monitoramento_alertas for select to authenticated
    using (user_id = auth.uid());

create policy "Usuário marca alerta como lido"
    on monitoramento_alertas for update to authenticated
    using (user_id = auth.uid());
