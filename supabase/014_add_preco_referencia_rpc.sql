-- ============================================================
-- RPC para consulta de preços de referência por item
-- Fase 2: Preço de Referência Inteligente
-- ============================================================

-- Função para buscar resumo de preços por NCM/NBS ou termo de busca
create or replace function buscar_precos_referencia(
    p_descricao text default null,
    p_ncm_nbs text default null,
    p_uf char(2) default null,
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

    with itens_filtrados as (
        select
            ic.id,
            ic.descricao,
            ic.valor_unitario_estimado,
            ic.unidade_medida,
            ic.plataforma_nome,
            ic.plataforma_id,
            ic.uf,
            ic.municipio,
            ri.valor_unitario_homologado,
            ri.valor_total_homologado,
            ri.nome_fornecedor,
            ri.percentual_desconto,
            coalesce(ri.valor_unitario_homologado, ic.valor_unitario_estimado) as valor_referencia
        from itens_contratacao ic
        left join resultados_item ri on ri.item_id = ic.id
        where ic.created_at >= data_limite
          and ic.valor_unitario_estimado > 0
          and (
              -- Match por NCM/NBS (exato)
              (p_ncm_nbs is not null and ic.ncm_nbs_codigo = p_ncm_nbs)
              or
              -- Match por similaridade textual
              (p_ncm_nbs is null and p_descricao is not null
               and ic.descricao % p_descricao
               and similarity(ic.descricao, p_descricao) > 0.2)
          )
          and (p_uf is null or ic.uf = p_uf)
    ),
    resumo as (
        select
            count(*) as total,
            min(valor_referencia) as minimo,
            max(valor_referencia) as maximo,
            avg(valor_referencia) as media,
            percentile_cont(0.5) within group (order by valor_referencia) as mediana,
            avg(case when percentual_desconto is not null then percentual_desconto end) as desconto_medio
        from itens_filtrados
    ),
    por_plataforma as (
        select
            plataforma_nome as nome,
            plataforma_id,
            avg(valor_referencia) as media_unitario,
            count(*) as total_itens
        from itens_filtrados
        where plataforma_nome is not null
        group by plataforma_nome, plataforma_id
        order by media_unitario
    )
    select json_build_object(
        'resumo', (select row_to_json(r) from resumo r),
        'plataformas', (select json_agg(row_to_json(p)) from por_plataforma p),
        'itens', (
            select json_agg(row_to_json(i))
            from (
                select id, descricao, valor_unitario_estimado, valor_referencia,
                       unidade_medida, plataforma_nome, uf, municipio,
                       valor_unitario_homologado, nome_fornecedor, percentual_desconto
                from itens_filtrados
                order by valor_referencia
                limit 30
            ) i
        )
    ) into resultado;

    return resultado;
end;
$$;
