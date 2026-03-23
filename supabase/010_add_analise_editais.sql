-- ============================================================
-- Análise automática de editais — extrai requisitos do PDF
-- ============================================================

create table if not exists analise_editais (
    id bigint generated always as identity primary key,
    licitacao_id uuid references licitacoes(id) on delete cascade not null unique,

    -- Documentos exigidos (lista extraída do edital)
    documentos_exigidos text[],

    -- Requisitos técnicos
    requisitos_tecnicos text[],

    -- Prazos extraídos
    prazos jsonb default '[]',

    -- Cláusulas de risco (multas, garantias, penalidades)
    clausulas_risco text[],

    -- Qualificação/habilitação
    qualificacao text[],

    -- Texto bruto extraído (para referência)
    texto_extraido text,

    -- Metadados
    url_documento text,
    paginas integer default 0,
    analisado_em timestamptz default now(),

    created_at timestamptz default now()
);

create index idx_analise_licitacao on analise_editais(licitacao_id);

-- ── RLS ──────────────────────────────────────────────────────

alter table analise_editais enable row level security;

create policy "Autenticados veem análises"
    on analise_editais for select to authenticated
    using (true);

create policy "Scraper insere análises"
    on analise_editais for insert to service_role
    with check (true);

create policy "Scraper atualiza análises"
    on analise_editais for update to service_role
    using (true);
