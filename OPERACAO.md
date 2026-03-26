# Operação do Licitaê — Comandos de Coleta e Cálculo

## Pré-requisitos

- VPS com containers rodando: `licitacoes-cron` e `licitae-mcp`
- `.env` configurado com `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- Migration `000_schema_completo.sql` executada no Supabase

---

## 1. Dados Fundação (rodar primeiro, uma vez)

### 1.1 Sync de Municípios

Busca todos os municípios do IBGE para as 11 UFs configuradas e grava no Supabase.

```bash
docker exec licitacoes-cron rm -f /app/cache/municipios.json
docker exec licitacoes-cron python main.py --sync-municipios
```

**Tempo:** ~30s | **Frequência:** 1x por mês (ou quando adicionar nova UF)

### 1.2 Sync de Plataformas

Popula tabela `plataformas_pncp` com os IDs conhecidos do PNCP.

```bash
docker exec licitacoes-cron python main.py --sync-plataformas
```

**Tempo:** ~5s | **Frequência:** 1x (ou quando descobrir nova plataforma)

---

## 2. Coleta de Licitações

### 2.1 Buscar licitações recentes

Busca licitações dos últimos N dias em todas as UFs configuradas.

```bash
# Últimos 7 dias (padrão do cron)
docker exec licitacoes-cron python main.py --dias 7

# Últimos 30 dias (para popular o banco do zero)
docker exec licitacoes-cron python main.py --dias 30

# Período específico
docker exec licitacoes-cron python main.py --de 20260301 --ate 20260326
```

**Tempo:** ~30min para 30 dias | **Frequência:** diária (cron 12:00)

### 2.2 Buscar sem gravar (dry-run)

Simula a busca sem inserir no banco.

```bash
docker exec licitacoes-cron python main.py --dias 7 --dry-run
```

### 2.3 Buscar sem enviar email

```bash
docker exec licitacoes-cron python main.py --dias 7 --sem-email
```

---

## 3. Coleta de Itens e Resultados

### 3.1 Coletar itens de licitações pendentes

Busca itens de contratação (descrição, unidade, valor) para licitações que ainda não têm itens.

```bash
# Padrão: 100 licitações
docker exec licitacoes-cron python main.py --coletar-itens

# Mais licitações
docker exec licitacoes-cron python main.py --coletar-itens --limite-itens 500
```

**Tempo:** ~2min por 100 | **Frequência:** diária (cron 14:00)

### 3.2 Coletar resultados (preços homologados)

Busca resultados dos itens já coletados (fornecedor vencedor, preço homologado, desconto).

```bash
docker exec licitacoes-cron python main.py --coletar-resultados

# Mais itens
docker exec licitacoes-cron python main.py --coletar-resultados --limite-itens 500
```

**Tempo:** ~3min por 200 | **Frequência:** diária (cron 15:00)

### 3.3 Coletar itens por plataforma

Busca itens diretamente de uma plataforma específica (útil para popular comparativo).

```bash
# SH3 Informática (ID 121) — últimos 90 dias
docker exec licitacoes-cron python main.py --coletar-plataforma 121 --dias-coleta 90

# BLL Compras (ID 12)
docker exec licitacoes-cron python main.py --coletar-plataforma 12 --dias-coleta 90

# Licitar Digital (ID 13)
docker exec licitacoes-cron python main.py --coletar-plataforma 13 --dias-coleta 90

# Licitanet (ID 18)
docker exec licitacoes-cron python main.py --coletar-plataforma 18 --dias-coleta 90

# Compras.gov.br (ID 3)
docker exec licitacoes-cron python main.py --coletar-plataforma 3 --dias-coleta 90

# ECustomize (ID 5)
docker exec licitacoes-cron python main.py --coletar-plataforma 5 --dias-coleta 90

# BBNet (ID 90)
docker exec licitacoes-cron python main.py --coletar-plataforma 90 --dias-coleta 90

# Filtrar por UF
docker exec licitacoes-cron python main.py --coletar-plataforma 121 --dias-coleta 90 --uf-coleta MG
```

**Tempo:** ~30min por plataforma | **Frequência:** semanal ou após reset

### 3.4 Coletar TODAS as plataformas de uma vez

```bash
for id in 121 12 13 18 3 5 90; do
  echo "=== Plataforma $id ==="
  docker exec licitacoes-cron python main.py --coletar-plataforma $id --dias-coleta 90
done
```

**Tempo:** ~4h total (rate limiting PNCP)

---

## 4. Análises e Cálculos

### 4.1 Analisar editais

Extrai documentos, requisitos, riscos e prazos dos PDFs de editais.

```bash
# Padrão: 10 editais
docker exec licitacoes-cron python main.py --analisar-editais

# Mais editais
docker exec licitacoes-cron python main.py --analisar-editais --limite-editais 50
```

**Tempo:** ~5s por edital | **Frequência:** diária (cron 13:00)

### 4.2 Calcular preços de referência

Calcula preço de referência para licitações abertas sem cálculo.

```bash
docker exec licitacoes-cron python main.py --calcular-precos
```

**Tempo:** ~2s por licitação | **Frequência:** diária (cron 17:00)

### 4.3 Calcular comparativo de mercado

Compara preços entre plataformas, agrupa itens similares.

```bash
docker exec licitacoes-cron python main.py --calcular-comparativo
```

**Tempo:** ~15s total | **Frequência:** diária (cron 16:00)

---

## 5. Monitoramento e Alertas

### 5.1 Verificar mudanças em licitações monitoradas

```bash
docker exec licitacoes-cron python main.py --monitorar
```

**Frequência:** a cada 4h (cron automático)

### 5.2 Verificar prazos próximos

```bash
docker exec licitacoes-cron python main.py --verificar-prazos
```

**Frequência:** diária (cron 08:00)

---

## 6. Modo Agendador (Cron Automático)

Roda TUDO automaticamente nos horários configurados.

```bash
docker exec licitacoes-cron python main.py --agendar
```

**Horários do cron:**
| Horário | Tarefa |
|---------|--------|
| 08:00 | Verificação de prazos |
| 12:00 | Busca de licitações |
| 13:00 | Análise de editais |
| 14:00 | Coleta de itens |
| 15:00 | Coleta de resultados |
| 16:00 | Comparativo de mercado |
| 17:00 | Preços de referência |
| 30min | Envio de convites pendentes |
| 4h | Monitoramento de mudanças |

---

## 7. Sequência Completa (do zero)

Após reset do banco, rodar nesta ordem:

```bash
# 1. Fundação
docker exec licitacoes-cron rm -f /app/cache/municipios.json
docker exec licitacoes-cron python main.py --sync-municipios
docker exec licitacoes-cron python main.py --sync-plataformas

# 2. Licitações (30 dias)
docker exec licitacoes-cron python main.py --dias 30

# 3. Itens e resultados
docker exec licitacoes-cron python main.py --coletar-itens --limite-itens 500
docker exec licitacoes-cron python main.py --coletar-resultados --limite-itens 500

# 4. Itens por plataforma (todas)
for id in 121 12 13 18 3 5 90; do
  docker exec licitacoes-cron python main.py --coletar-plataforma $id --dias-coleta 90
done

# 5. Análises
docker exec licitacoes-cron python main.py --analisar-editais --limite-editais 50

# 6. Cálculos
docker exec licitacoes-cron python main.py --calcular-precos
docker exec licitacoes-cron python main.py --calcular-comparativo
```

**Tempo total:** ~7-8h (maior parte é coleta automática)

---

## 8. Deploy e Restart

### Build e restart de todos os containers

```bash
cd /home/deploy/licitae-backend
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

### Restart só do cron

```bash
docker compose -f docker-compose.prod.yml restart licitacoes-cron
```

### Restart só do MCP server

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate licitae-mcp
```

### Ver logs

```bash
# Cron (busca, coleta, cálculos)
docker logs licitacoes-cron --tail 50
docker logs licitacoes-cron -f  # tempo real

# MCP server
docker logs licitae-mcp --tail 20

# Filtrar erros
docker logs licitacoes-cron 2>&1 | grep ERROR | tail -20
```

### Limpar cache de municípios

```bash
docker exec licitacoes-cron rm -f /app/cache/municipios.json
```

---

## 9. Verificação Rápida

### Contar registros no banco (rodar no Supabase SQL Editor)

```sql
SELECT 'licitacoes' AS tabela, count(*) FROM licitacoes
UNION ALL SELECT 'itens_contratacao', count(*) FROM itens_contratacao
UNION ALL SELECT 'resultados_item', count(*) FROM resultados_item
UNION ALL SELECT 'analise_editais', count(*) FROM analise_editais
UNION ALL SELECT 'preco_referencia', count(*) FROM preco_referencia_licitacao
UNION ALL SELECT 'comparativo_itens', count(*) FROM comparativo_itens
UNION ALL SELECT 'comparativo_plat', count(*) FROM comparativo_plataformas;
```

### Verificar licitações por UF

```sql
SELECT uf, count(*), count(*) FILTER (WHERE proposta_aberta) AS abertas
FROM licitacoes GROUP BY uf ORDER BY count(*) DESC;
```

### Verificar itens por plataforma

```sql
SELECT plataforma_nome, count(*) FROM itens_contratacao
GROUP BY plataforma_nome ORDER BY count(*) DESC;
```

---

## IDs das Plataformas

| ID | Nome |
|----|------|
| 121 | SH3 Informática |
| 12 | BLL Compras (BNC) |
| 13 | Licitar Digital |
| 18 | Licitanet |
| 3 | Compras.gov.br |
| 5 | ECustomize |
| 90 | BBNet |
