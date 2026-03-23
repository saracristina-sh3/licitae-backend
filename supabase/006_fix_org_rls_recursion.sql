-- ============================================================
-- Fix: recursão infinita no RLS de org_membros
--
-- Problema: policies de org_membros faziam SELECT na própria
-- tabela para checar membership, disparando a mesma policy
-- recursivamente.
--
-- Solução: funções security definer que bypassam RLS para
-- buscar org_ids do usuário.
-- ============================================================

-- Funções auxiliares (security definer = bypassa RLS)
create or replace function get_user_org_ids()
returns setof uuid as $$
    select org_id from org_membros where user_id = auth.uid();
$$ language sql security definer stable;

create or replace function get_user_admin_org_ids()
returns setof uuid as $$
    select org_id from org_membros where user_id = auth.uid() and role = 'admin';
$$ language sql security definer stable;

-- ── Drop policies com recursão ─────────────────────────────

drop policy if exists "Membro vê sua organização" on organizacoes;
drop policy if exists "Admin edita organização" on organizacoes;
drop policy if exists "Membro vê colegas da org" on org_membros;
drop policy if exists "Admin adiciona membros" on org_membros;
drop policy if exists "Admin remove membros" on org_membros;
drop policy if exists "Admin cria convites" on org_convites;
drop policy if exists "Admin vê convites" on org_convites;
drop policy if exists "Usuário vê oportunidades" on oportunidades;
drop policy if exists "Usuário edita oportunidades da org" on oportunidades;

-- ── Recriar policies usando funções security definer ────────

-- organizacoes
create policy "Membro vê sua organização"
    on organizacoes for select to authenticated
    using (id in (select get_user_org_ids()));

create policy "Admin edita organização"
    on organizacoes for update to authenticated
    using (id in (select get_user_admin_org_ids()));

-- org_membros
create policy "Membro vê colegas da org"
    on org_membros for select to authenticated
    using (org_id in (select get_user_org_ids()));

create policy "Admin adiciona membros"
    on org_membros for insert to authenticated
    with check (org_id in (select get_user_admin_org_ids()));

create policy "Admin remove membros"
    on org_membros for delete to authenticated
    using (org_id in (select get_user_admin_org_ids()));

-- org_convites
create policy "Admin cria convites"
    on org_convites for insert to authenticated
    with check (org_id in (select get_user_admin_org_ids()));

create policy "Admin vê convites"
    on org_convites for select to authenticated
    using (org_id in (select get_user_admin_org_ids())
           or email = (select email from auth.users where id = auth.uid()));

-- oportunidades
create policy "Usuário vê oportunidades"
    on oportunidades for select to authenticated
    using (
        user_id = auth.uid()
        or org_id in (select get_user_org_ids())
    );

create policy "Usuário edita oportunidades da org"
    on oportunidades for update to authenticated
    using (
        user_id = auth.uid()
        or org_id in (select get_user_org_ids())
    );
