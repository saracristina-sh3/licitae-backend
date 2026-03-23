-- ============================================================
-- Alertas de prazo — notifica usuários sobre prazos próximos
-- Verifica prazo_interno (oportunidade) e data_encerramento_proposta (licitação)
-- ============================================================

create table if not exists prazo_alertas (
    id bigint generated always as identity primary key,
    oportunidade_id uuid references oportunidades(id) on delete cascade not null,
    user_id uuid references auth.users(id) on delete cascade not null,
    licitacao_id uuid references licitacoes(id) on delete cascade not null,

    tipo text not null check (tipo in ('prazo_interno', 'encerramento_proposta')),
    dias_restantes integer not null check (dias_restantes in (3, 1, 0)),
    data_prazo date not null,
    lido boolean default false,

    created_at timestamptz default now(),

    -- Evita duplicatas: 1 alerta por oportunidade/tipo/dia
    unique(oportunidade_id, tipo, dias_restantes)
);

create index idx_prazo_alertas_user_lido on prazo_alertas(user_id, lido) where lido = false;
create index idx_prazo_alertas_oportunidade on prazo_alertas(oportunidade_id);

-- ── RLS ──────────────────────────────────────────────────────

alter table prazo_alertas enable row level security;

create policy "Scraper insere alertas de prazo"
    on prazo_alertas for insert to service_role
    with check (true);

create policy "Usuário vê seus alertas de prazo"
    on prazo_alertas for select to authenticated
    using (user_id = auth.uid());

create policy "Usuário marca alerta de prazo como lido"
    on prazo_alertas for update to authenticated
    using (user_id = auth.uid());
