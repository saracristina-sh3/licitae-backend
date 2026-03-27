"""Verifica distribuição de homologados por plataforma."""
import sys
sys.path.insert(0, "/app")
from db import get_client
from collections import Counter

c = get_client()

# Total por plataforma
print("=== ITENS POR PLATAFORMA ===")
for plat_id in [121, 12, 13, 18, 3, 5, 90]:
    r = c.table("itens_contratacao").select("id", count="exact").eq("plataforma_id", plat_id).execute()
    total = r.count or 0
    r2 = c.table("itens_contratacao").select("id, resultados_item(valor_unitario_homologado)").eq("plataforma_id", plat_id).limit(3000).execute()
    hom = 0
    for item in (r2.data or []):
        res = item.get("resultados_item") or []
        if isinstance(res, dict):
            res = [res]
        if any(float(r.get("valor_unitario_homologado") or 0) > 0 for r in res):
            hom += 1
    print(f"  Plat {plat_id}: {total} itens, {hom} com homologado ({100*hom//max(total,1)}%)")

print()
print("=== RESULTADOS HOMOLOGADOS POR PLATAFORMA ===")
r = c.table("resultados_item").select("item_id, valor_unitario_homologado, item:itens_contratacao(plataforma_nome)").gt("valor_unitario_homologado", 0).limit(5000).execute()
contagem = Counter()
for row in (r.data or []):
    item = row.get("item") or {}
    plat = item.get("plataforma_nome") or "?"
    contagem[plat] += 1
for plat, n in contagem.most_common():
    print(f"  {plat}: {n}")
