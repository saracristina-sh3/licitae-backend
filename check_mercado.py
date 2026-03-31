"""Diagnóstico da view de mercado — verificar dados nas tabelas."""

from db import get_client

c = get_client()

print("=== ITENS POR PLATAFORMA (com estimado > 0) ===")
for pid in [121, 12, 13, 18, 3, 5, 90]:
    r = (
        c.table("itens_contratacao")
        .select("id", count="exact")
        .eq("plataforma_id", pid)
        .gt("valor_unitario_estimado", 0)
        .limit(1)
        .execute()
    )
    print(f"  Plataforma {pid}: {r.count} itens")

print()
print("=== TABELAS COMPARATIVO ===")
r = (
    c.table("comparativo_plataformas")
    .select("plataforma_nome, vitorias, calculado_em", count="exact")
    .limit(10)
    .execute()
)
print(f"  comparativo_plataformas: {r.count} registros")
for row in (r.data or []):
    print(f"    {row}")

print()
r = (
    c.table("comparativo_itens")
    .select("id, chave_agrupamento, score_comparabilidade", count="exact")
    .limit(5)
    .execute()
)
print(f"  comparativo_itens: {r.count} registros")
for row in (r.data or []):
    print(f"    {row}")

print()
print("=== AMOSTRA DE ITENS (plat 121) ===")
r = (
    c.table("itens_contratacao")
    .select("descricao, ncm_nbs_codigo, unidade_medida, valor_unitario_estimado, plataforma_nome")
    .eq("plataforma_id", 121)
    .gt("valor_unitario_estimado", 0)
    .limit(3)
    .execute()
)
for row in (r.data or []):
    print(f"    {row}")
if not r.data:
    print("    (nenhum item encontrado)")
