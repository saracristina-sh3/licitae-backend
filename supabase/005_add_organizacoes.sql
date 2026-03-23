-- ============================================================
-- Organizações — estrutura simples de equipe
-- ============================================================

-- Tabela de organizações
create table if not exists organizacoes (
    id uuid default uuid_generate_v4() primary key,
    nome text not null,
    slug text unique not null,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create trigger organizacoes_updated_at
    before update on organizacoes
    for each row execute function update_updated_at();

-- Membros da organização
create type org_role as enum ('admin', 'membro');

create table if not exists org_membros (
    id bigint generated always as identity primary key,
    org_id uuid references organizacoes(id) on delete cascade not null,
    user_id uuid references auth.users(id) on delete cascade not null,
    role org_role not null default 'membro',
    created_at timestamptz default now(),
    unique(org_id, user_id)
);

create index idx_org_membros_user on org_membros(user_id);
create index idx_org_membros_org on org_membros(org_id);

-- Convites pendentes
create table if not exists org_convites (
    id uuid default uuid_generate_v4() primary key,
    org_id uuid references organizacoes(id) on delete cascade not null,
    email text not null,
    convidado_por uuid references auth.users(id) not null,
    aceito boolean default false,
    created_at timestamptz default now(),
    unique(org_id, email)
);

-- Adiciona org_id nas tabelas existentes
alter table profiles add column if not exists org_id uuid references organizacoes(id) on delete set null;
alter table user_config add column if not exists org_id uuid references organizacoes(id) on delete set null;
alter table oportunidades add column if not exists org_id uuid references organizacoes(id) on delete set null;

create index if not exists idx_profiles_org on profiles(org_id);
create index if not exists idx_oportunidades_org on oportunidades(org_id);

-- ============================================================
-- Funções auxiliares para RLS (security definer = bypassa RLS)
-- Evita recursão infinita nas policies de org_membros
-- ============================================================

-- Retorna org_ids onde o usuário é membro (qualquer role)
create or replace function get_user_org_ids()
returns setof uuid as $$
    select org_id from org_membros where user_id = auth.uid();
$$ language sql security definer stable;

-- Retorna org_ids onde o usuário é admin
create or replace function get_user_admin_org_ids()
returns setof uuid as $$
    select org_id from org_membros where user_id = auth.uid() and role = 'admin';
$$ language sql security definer stable;

-- ============================================================
-- RLS para organizações
-- ============================================================

alter table organizacoes enable row level security;
alter table org_membros enable row level security;
alter table org_convites enable row level security;

-- Org: membros podem ver sua org
create policy "Membro vê sua organização"
    on organizacoes for select to authenticated
    using (id in (select get_user_org_ids()));

-- Org: qualquer autenticado pode criar
create policy "Usuário pode criar organização"
    on organizacoes for insert to authenticated
    with check (true);

-- Org: admin pode editar
create policy "Admin edita organização"
    on organizacoes for update to authenticated
    using (id in (select get_user_admin_org_ids()));

-- ============================================================
-- RLS para org_membros (usa funções security definer)
-- ============================================================

-- Membros: ver membros da mesma org
create policy "Membro vê colegas da org"
    on org_membros for select to authenticated
    using (org_id in (select get_user_org_ids()));

-- Membros: admin pode adicionar
create policy "Admin adiciona membros"
    on org_membros for insert to authenticated
    with check (org_id in (select get_user_admin_org_ids()));

-- Membros: admin pode remover
create policy "Admin remove membros"
    on org_membros for delete to authenticated
    using (org_id in (select get_user_admin_org_ids()));

-- ============================================================
-- RLS para convites
-- ============================================================

-- Convites: admin pode criar
create policy "Admin cria convites"
    on org_convites for insert to authenticated
    with check (org_id in (select get_user_admin_org_ids()));

-- Convites: admin vê convites da org, destinatário vê o seu
create policy "Admin vê convites"
    on org_convites for select to authenticated
    using (org_id in (select get_user_admin_org_ids())
           or email = (select email from auth.users where id = auth.uid()));

-- Convites: destinatário pode aceitar (update)
create policy "Destinatário aceita convite"
    on org_convites for update to authenticated
    using (email = (select email from auth.users where id = auth.uid()));

-- ============================================================
-- Atualizar RLS de oportunidades para incluir org
-- ============================================================

-- Remove policies antigas de oportunidades
drop policy if exists "Usuário vê suas oportunidades" on oportunidades;
drop policy if exists "Usuário cria suas oportunidades" on oportunidades;
drop policy if exists "Usuário edita suas oportunidades" on oportunidades;
drop policy if exists "Usuário remove suas oportunidades" on oportunidades;

-- Novas policies: usuário vê próprias + da org
create policy "Usuário vê oportunidades"
    on oportunidades for select to authenticated
    using (
        user_id = auth.uid()
        or org_id in (select get_user_org_ids())
    );

create policy "Usuário cria oportunidades"
    on oportunidades for insert to authenticated
    with check (user_id = auth.uid());

create policy "Usuário edita oportunidades da org"
    on oportunidades for update to authenticated
    using (
        user_id = auth.uid()
        or org_id in (select get_user_org_ids())
    );

create policy "Usuário remove suas oportunidades"
    on oportunidades for delete to authenticated
    using (user_id = auth.uid());

-- ============================================================
-- Funções de negócio
-- ============================================================

-- Criar organização e adicionar criador como admin
create or replace function criar_organizacao(nome_org text, slug_org text)
returns uuid as $$
declare
    new_org_id uuid;
begin
    insert into organizacoes (nome, slug)
    values (nome_org, slug_org)
    returning id into new_org_id;

    insert into org_membros (org_id, user_id, role)
    values (new_org_id, auth.uid(), 'admin');

    update profiles set org_id = new_org_id where id = auth.uid();
    update user_config set org_id = new_org_id where user_id = auth.uid();

    return new_org_id;
end;
$$ language plpgsql security definer;

-- Aceitar convite
create or replace function aceitar_convite(convite_id uuid)
returns void as $$
declare
    v_org_id uuid;
    v_email text;
begin
    select email into v_email from auth.users where id = auth.uid();

    select org_id into v_org_id
    from org_convites
    where id = convite_id and email = v_email and aceito = false;

    if v_org_id is null then
        raise exception 'Convite inválido ou já aceito';
    end if;

    insert into org_membros (org_id, user_id, role)
    values (v_org_id, auth.uid(), 'membro')
    on conflict (org_id, user_id) do nothing;

    update profiles set org_id = v_org_id where id = auth.uid();
    update user_config set org_id = v_org_id where user_id = auth.uid();
    update org_convites set aceito = true where id = convite_id;
end;
$$ language plpgsql security definer;

-- Sair da organização
create or replace function sair_organizacao()
returns void as $$
begin
    delete from org_membros where user_id = auth.uid();
    update profiles set org_id = null where id = auth.uid();
    update user_config set org_id = null where user_id = auth.uid();
    update oportunidades set org_id = null where user_id = auth.uid();
end;
$$ language plpgsql security definer;
