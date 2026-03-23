-- ============================================================
-- Licitações de Software — Supabase Schema
-- ============================================================

-- Extensões
create extension if not exists "uuid-ossp";
create extension if not exists "pg_trgm";  -- busca fuzzy

-- ============================================================
-- ENUM types
-- ============================================================

create type relevancia_tipo as enum ('ALTA', 'MEDIA', 'BAIXA');

create type oportunidade_status as enum (
    'identificada',
    'analisando',
    'preparando_proposta',
    'proposta_enviada',
    'ganha',
    'perdida',
    'descartada'
);

create type fonte_tipo as enum (
    'PNCP',
    'TCE_RJ',
    'QUERIDO_DIARIO',
    'DOM_MG',
    'MANUAL'
);

create type alerta_canal as enum (
    'email',
    'push',
    'telegram',
    'whatsapp'
);

-- ============================================================
-- Municípios (cache IBGE)
-- ============================================================

create table municipios (
    id bigint generated always as identity primary key,
    codigo_ibge text unique not null,
    nome text not null,
    uf char(2) not null,
    populacao integer not null default 0,
    fpm numeric(3,1) not null default 0.0,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index idx_municipios_uf on municipios(uf);
create index idx_municipios_fpm on municipios(fpm);
create index idx_municipios_codigo on municipios(codigo_ibge);

-- ============================================================
-- Licitações
-- ============================================================

create table licitacoes (
    id uuid default uuid_generate_v4() primary key,
    hash_dedup text unique not null,  -- hash para deduplicação

    -- Município
    municipio_id bigint references municipios(id),
    municipio_nome text not null,
    uf char(2) not null,

    -- Órgão
    orgao text,
    cnpj_orgao text,

    -- Dados da licitação
    objeto text not null,
    modalidade text,
    valor_estimado numeric(15,2) default 0,
    valor_homologado numeric(15,2) default 0,
    situacao text,

    -- Datas
    data_publicacao timestamptz,
    data_abertura_proposta timestamptz,
    data_encerramento_proposta timestamptz,

    -- Fonte e classificação
    fonte fonte_tipo not null default 'PNCP',
    url_fonte text,
    relevancia relevancia_tipo not null default 'BAIXA',
    palavras_chave text[],

    -- Metadados
    dados_brutos jsonb,
    proposta_aberta boolean default true,

    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index idx_licitacoes_uf on licitacoes(uf);
create index idx_licitacoes_relevancia on licitacoes(relevancia);
create index idx_licitacoes_fonte on licitacoes(fonte);
create index idx_licitacoes_municipio on licitacoes(municipio_id);
create index idx_licitacoes_proposta_aberta on licitacoes(proposta_aberta) where proposta_aberta = true;
create index idx_licitacoes_data_pub on licitacoes(data_publicacao desc);
create index idx_licitacoes_objeto_trgm on licitacoes using gin(objeto gin_trgm_ops);

-- ============================================================
-- Oportunidades (CRM)
-- ============================================================

create table oportunidades (
    id uuid default uuid_generate_v4() primary key,
    licitacao_id uuid references licitacoes(id) on delete cascade not null,
    user_id uuid references auth.users(id) on delete cascade not null,

    status oportunidade_status not null default 'identificada',
    responsavel text,
    notas text,
    prazo_interno date,
    valor_proposta numeric(15,2),

    created_at timestamptz default now(),
    updated_at timestamptz default now(),

    unique(licitacao_id, user_id)
);

create index idx_oportunidades_user on oportunidades(user_id);
create index idx_oportunidades_status on oportunidades(status);
create index idx_oportunidades_prazo on oportunidades(prazo_interno) where prazo_interno is not null;

-- ============================================================
-- Histórico de status
-- ============================================================

create table historico_status (
    id bigint generated always as identity primary key,
    oportunidade_id uuid references oportunidades(id) on delete cascade not null,
    status_anterior oportunidade_status,
    status_novo oportunidade_status not null,
    usuario text,
    observacao text,
    created_at timestamptz default now()
);

create index idx_historico_oportunidade on historico_status(oportunidade_id);

-- ============================================================
-- Alertas enviados
-- ============================================================

create table alertas_enviados (
    id bigint generated always as identity primary key,
    licitacao_id uuid references licitacoes(id) on delete cascade not null,
    user_id uuid references auth.users(id) on delete cascade,
    canal alerta_canal not null,
    destinatario text,
    enviado_em timestamptz default now()
);

create index idx_alertas_licitacao on alertas_enviados(licitacao_id);
create index idx_alertas_user on alertas_enviados(user_id);

-- ============================================================
-- Configurações do usuário
-- ============================================================

create table user_config (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid references auth.users(id) on delete cascade unique not null,
    ufs text[] default '{MG,RJ}',
    fpm_maximo numeric(3,1) default 2.8,
    palavras_chave text[] default '{software,"permissão de uso","licença de uso","locação de software","cessão de uso","sistema integrado","sistema de gestão","solução tecnológica","informática","tecnologia da informação"}',
    alertas_email boolean default true,
    alertas_push boolean default true,
    alertas_telegram boolean default false,
    telegram_chat_id text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- ============================================================
-- Profiles (public user info)
-- ============================================================

create table profiles (
    id uuid references auth.users(id) on delete cascade primary key,
    nome text,
    email text,
    avatar_url text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- ============================================================
-- Row Level Security (RLS)
-- ============================================================

-- Licitações: todos autenticados podem ler
alter table licitacoes enable row level security;

create policy "Licitações visíveis para autenticados"
    on licitacoes for select
    to authenticated
    using (true);

create policy "Scraper pode inserir licitações"
    on licitacoes for insert
    to service_role
    with check (true);

create policy "Scraper pode atualizar licitações"
    on licitacoes for update
    to service_role
    using (true);

-- Municípios: leitura pública
alter table municipios enable row level security;

create policy "Municípios visíveis para todos"
    on municipios for select
    to authenticated
    using (true);

create policy "Scraper pode gerenciar municípios"
    on municipios for all
    to service_role
    using (true);

-- Oportunidades: cada usuário vê só as suas
alter table oportunidades enable row level security;

create policy "Usuário vê suas oportunidades"
    on oportunidades for select
    to authenticated
    using (user_id = auth.uid());

create policy "Usuário cria suas oportunidades"
    on oportunidades for insert
    to authenticated
    with check (user_id = auth.uid());

create policy "Usuário edita suas oportunidades"
    on oportunidades for update
    to authenticated
    using (user_id = auth.uid());

create policy "Usuário remove suas oportunidades"
    on oportunidades for delete
    to authenticated
    using (user_id = auth.uid());

-- Histórico: segue a oportunidade
alter table historico_status enable row level security;

create policy "Usuário vê histórico das suas oportunidades"
    on historico_status for select
    to authenticated
    using (
        oportunidade_id in (
            select id from oportunidades where user_id = auth.uid()
        )
    );

create policy "Usuário cria histórico das suas oportunidades"
    on historico_status for insert
    to authenticated
    with check (
        oportunidade_id in (
            select id from oportunidades where user_id = auth.uid()
        )
    );

-- Alertas: cada usuário vê os seus
alter table alertas_enviados enable row level security;

create policy "Usuário vê seus alertas"
    on alertas_enviados for select
    to authenticated
    using (user_id = auth.uid());

-- Config: cada usuário vê a sua
alter table user_config enable row level security;

create policy "Usuário vê sua config"
    on user_config for select
    to authenticated
    using (user_id = auth.uid());

create policy "Usuário cria sua config"
    on user_config for insert
    to authenticated
    with check (user_id = auth.uid());

create policy "Usuário edita sua config"
    on user_config for update
    to authenticated
    using (user_id = auth.uid());

-- Profiles
alter table profiles enable row level security;

create policy "Profiles visíveis para autenticados"
    on profiles for select
    to authenticated
    using (true);

create policy "Usuário edita seu profile"
    on profiles for update
    to authenticated
    using (id = auth.uid());

-- ============================================================
-- Functions
-- ============================================================

-- Auto-create profile on signup
create or replace function handle_new_user()
returns trigger as $$
begin
    insert into profiles (id, nome, email)
    values (
        new.id,
        coalesce(new.raw_user_meta_data->>'nome', new.raw_user_meta_data->>'full_name', ''),
        new.email
    );

    insert into user_config (user_id)
    values (new.id);

    return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function handle_new_user();

-- Auto-update updated_at
create or replace function update_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- Calcula proposta_aberta no insert/update
create or replace function calcular_proposta_aberta()
returns trigger as $$
begin
    new.proposta_aberta = (
        new.data_encerramento_proposta is null
        or new.data_encerramento_proposta > now()
    );
    return new;
end;
$$ language plpgsql;

create trigger licitacoes_proposta_aberta
    before insert or update on licitacoes
    for each row execute function calcular_proposta_aberta();

create trigger licitacoes_updated_at
    before update on licitacoes
    for each row execute function update_updated_at();

create trigger oportunidades_updated_at
    before update on oportunidades
    for each row execute function update_updated_at();

create trigger municipios_updated_at
    before update on municipios
    for each row execute function update_updated_at();

create trigger user_config_updated_at
    before update on user_config
    for each row execute function update_updated_at();

create trigger profiles_updated_at
    before update on profiles
    for each row execute function update_updated_at();

-- Auto-registrar histórico de status
create or replace function registrar_historico_status()
returns trigger as $$
begin
    if old.status is distinct from new.status then
        insert into historico_status (oportunidade_id, status_anterior, status_novo)
        values (new.id, old.status, new.status);
    end if;
    return new;
end;
$$ language plpgsql security definer;

create trigger oportunidades_historico
    after update on oportunidades
    for each row execute function registrar_historico_status();

-- ============================================================
-- Views úteis
-- ============================================================

create or replace view licitacoes_abertas as
select
    l.*,
    m.populacao,
    m.fpm
from licitacoes l
left join municipios m on m.id = l.municipio_id
where l.proposta_aberta = true
order by l.relevancia, l.data_publicacao desc;
