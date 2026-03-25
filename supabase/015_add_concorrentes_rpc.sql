-- ============================================================
-- RPCs para Radar de Concorrentes
-- Fase 3: Inteligência Competitiva
-- ============================================================

-- Top fornecedores por número de vitórias
create or replace function top_concorrentes(
    p_uf char(2) default null,
    p_meses int default 12,
    p_limite int default 20
)
returns json
language plpgsql
security definer
as $$
declare
    resultado json;
    data_limite timestamptz;
begin
    data_limite := now() - (p_meses || ' months')::interval;

    with ranking as (
        select
            ri.cnpj_fornecedor,
            ri.nome_fornecedor,
            ri.porte_fornecedor,
            count(*) as total_vitorias,
            sum(ri.valor_total_homologado) as valor_total,
            avg(ri.valor_unitario_homologado) as valor_medio_unitario,
            avg(ri.percentual_desconto) filter (where ri.percentual_desconto is not null) as desconto_medio,
            array_agg(distinct ic.uf) filter (where ic.uf is not null) as ufs,
            count(distinct ic.municipio) as total_municipios
        from resultados_item ri
        join itens_contratacao ic on ic.id = ri.item_id
        where ri.valor_total_homologado > 0
          and ri.cnpj_fornecedor is not null
          and ri.created_at >= data_limite
          and (p_uf is null or ic.uf = p_uf)
        group by ri.cnpj_fornecedor, ri.nome_fornecedor, ri.porte_fornecedor
        order by total_vitorias desc
        limit p_limite
    )
    select json_agg(row_to_json(r))
    from ranking r
    into resultado;

    return coalesce(resultado, '[]'::json);
end;
$$;

-- Comparativo de preços entre plataformas
create or replace function comparativo_plataformas(
    p_uf char(2) default null,
    p_ncm_nbs text default null,
    p_meses int default 12
)
returns json
language plpgsql
security definer
as $$
declare
    resultado json;
    data_limite timestamptz;
begin
    data_limite := now() - (p_meses || ' months')::interval;

    with por_plataforma as (
        select
            ic.plataforma_nome,
            ic.plataforma_id,
            count(*) as total_itens,
            avg(coalesce(ri.valor_unitario_homologado, ic.valor_unitario_estimado)) as valor_medio_unitario,
            avg(ri.percentual_desconto) filter (where ri.percentual_desconto is not null) as desconto_medio,
            sum(coalesce(ri.valor_total_homologado, ic.valor_total_estimado)) as valor_total,
            count(distinct ic.municipio) as total_municipios
        from itens_contratacao ic
        left join resultados_item ri on ri.item_id = ic.id
        where ic.valor_unitario_estimado > 0
          and ic.plataforma_id is not null
          and ic.created_at >= data_limite
          and (p_uf is null or ic.uf = p_uf)
          and (p_ncm_nbs is null or ic.ncm_nbs_codigo = p_ncm_nbs)
        group by ic.plataforma_nome, ic.plataforma_id
        order by valor_medio_unitario
    )
    select json_agg(row_to_json(p))
    from por_plataforma p
    into resultado;

    return coalesce(resultado, '[]'::json);
end;
$$;
