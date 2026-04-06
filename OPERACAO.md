# Operacao do Licitae — Comandos de Coleta e Calculo

## Pre-requisitos

- VPS com containers rodando: `licitacoes-cron` e `licitae-mcp`
- `.env` configurado com `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- Migrations executadas no Supabase (ate `043_add_campos_pncp.sql`)

---

## Arquitetura do Pipeline

```
FASE 1: COLETA GENERICA (sem keywords)
  PNCP API → licitacoes (todas, filtro por UF/modalidade/FPM)

FASE 2: COLETA DE ITENS
  Para cada licitacao sem itens → API PNCP /itens → itens_contratacao
  Para cada item com resultado → API PNCP /resultados → resultados_item

FASE 3: PROSPECCAO POR ORG
  Para cada org → aplica keywords/filtros → oportunidades_org (score per-org)
```

Cada org ve oportunidades diferentes com scores diferentes, baseado nos seus keywords.

---

## 1. Dados Fundacao (rodar primeiro, uma vez)

### 1.1 Sync de Municipios e Microrregioes

Busca municipios e microrregioes do IBGE para as UFs configuradas e grava no Supabase.

```bash
docker exec licitacoes-cron rm -f /app/cache/municipios.json /app/cache/microrregioes.json
docker exec licitacoes-cron python main.py --sync-municipios
```

**Tempo:** ~1min | **Frequencia:** 1x por mes (ou quando adicionar nova UF)

Isso popula:
- Tabela `municipios` (com `microrregiao_id`)
- Tabela `microrregioes` (com mesorregiao)

### 1.2 Sync de Plataformas

Popula tabela `plataformas_pncp` com os IDs conhecidos do PNCP.

```bash
docker exec licitacoes-cron python main.py --sync-plataformas
```

**Tempo:** ~5s | **Frequencia:** 1x (ou quando descobrir nova plataforma)

---

## 2. Coleta de Licitacoes (Fase 1 — Generica)

Coleta TODAS as licitacoes do PNCP nas UFs/modalidades configuradas, sem filtro de keywords. Keywords sao aplicados na Fase 3 (prospeccao por org).

### 2.1 Pipeline completo (coleta + itens + prospeccao)

```bash
# Ultimos 7 dias (padrao)
docker exec licitacoes-cron python main.py

# Ultimos 30 dias (para popular do zero)
docker exec licitacoes-cron python main.py --dias 30

# Periodo especifico
docker exec licitacoes-cron python main.py --de 20260301 --ate 20260326
```

**Tempo:** ~30min para 30 dias | **Frequencia:** diaria (cron 12:00)

### 2.2 Apenas coleta (sem prospeccao)

```bash
docker exec licitacoes-cron python main.py --apenas-coletar --dias 7
```

### 2.3 Apenas prospeccao (sobre dados ja coletados)

```bash
docker exec licitacoes-cron python main.py --prospectar
```

### 2.4 Dry-run (simula sem gravar)

```bash
docker exec licitacoes-cron python main.py --dias 7 --dry-run
```

### 2.5 Sem email

```bash
docker exec licitacoes-cron python main.py --dias 7 --sem-email
```

---

## 3. Coleta de Itens e Resultados (Fase 2)

### 3.1 Coletar itens de licitacoes pendentes

Busca licitacoes com `itens_coletados=FALSE`, extrai cnpj/ano/seq da URL, e chama API PNCP para buscar itens.

```bash
# Padrao: 100 licitacoes
docker exec licitacoes-cron python main.py --coletar-itens

# Mais licitacoes
docker exec licitacoes-cron python main.py --coletar-itens --limite-itens 500
```

**Tempo:** ~2min por 100 | **Frequencia:** diaria (no pipeline)

Apos coletar itens de uma licitacao, marca `itens_coletados=TRUE`.

### 3.2 Coletar resultados (precos homologados)

Busca resultados dos itens ja coletados (fornecedor vencedor, preco homologado, desconto).

```bash
docker exec licitacoes-cron python main.py --coletar-resultados

# Mais itens
docker exec licitacoes-cron python main.py --coletar-resultados --limite-itens 500
```

**Tempo:** ~3min por 200 | **Frequencia:** diaria (no pipeline)

### 3.3 Coletar itens por plataforma

Busca itens diretamente de uma plataforma especifica (util para popular comparativo).

```bash
# SH3 Informatica (ID 121) — ultimos 90 dias
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

**Tempo:** ~30min por plataforma | **Frequencia:** semanal ou apos reset

### 3.4 Coletar TODAS as plataformas de uma vez

```bash
for id in 121 12 13 18 3 5 90; do
  echo "=== Plataforma $id ==="
  docker exec licitacoes-cron python main.py --coletar-plataforma $id --dias-coleta 90
done
```

**Tempo:** ~4h total (rate limiting PNCP)

---

## 4. Analises e Calculos

### 4.1 Analisar editais

Extrai documentos, requisitos, riscos e prazos dos PDFs de editais.

```bash
# Padrao: 10 editais
docker exec licitacoes-cron python main.py --analisar-editais

# Mais editais
docker exec licitacoes-cron python main.py --analisar-editais --limite-editais 50

# Incluir licitacoes encerradas
docker exec licitacoes-cron python main.py --analisar-todos-editais --limite-editais 50
```

**Tempo:** ~5s por edital | **Frequencia:** diaria (no pipeline)

### 4.2 Calcular precos de referencia

Calcula preco de referencia para licitacoes abertas sem calculo.

```bash
docker exec licitacoes-cron python main.py --calcular-precos
```

**Tempo:** ~2s por licitacao | **Frequencia:** diaria (no pipeline)

### 4.3 Calcular comparativo de mercado

Compara precos entre plataformas, agrupa itens similares. Materializa em `comparativo_plataformas` e `comparativo_itens`.

```bash
docker exec licitacoes-cron python main.py --calcular-comparativo
```

**Tempo:** ~15s total | **Frequencia:** diaria (no pipeline)

---

## 5. Monitoramento e Alertas

### 5.1 Verificar mudancas em licitacoes monitoradas

```bash
docker exec licitacoes-cron python main.py --monitorar
```

**Frequencia:** a cada 4h (cron automatico)

### 5.2 Verificar prazos proximos

```bash
docker exec licitacoes-cron python main.py --verificar-prazos
```

**Frequencia:** diaria (cron 08:00)

---

## 6. Modo Agendador (Cron Automatico)

Roda TUDO automaticamente nos horarios configurados.

```bash
docker exec licitacoes-cron python main.py --agendar
```

**Pipeline diario (12:00):**

| Ordem | Tarefa | Depende de |
|-------|--------|-----------|
| 1 | Coleta generica PNCP | - |
| 2 | Coleta de itens | Fase 1 |
| 3 | Analise de editais | Fase 1 |
| 4 | Coleta de resultados | Fase 2 |
| 5 | Prospeccao por organizacao | Fases 1-2 |
| 6 | Comparativo de mercado | Fases 2-4 |
| 7 | Precos de referencia | Fases 2-4 |

**Demais horarios:**

| Horario | Tarefa |
|---------|--------|
| 08:00 | Verificacao de prazos + alertas |
| 12:00 | Pipeline diario completo |
| 4h | Monitoramento de mudancas |
| 30min | Envio de convites pendentes |
| Dom 06:00 | Sync municipios + microrregioes + plataformas |
| Dom 07:00 | Coleta de plataformas-alvo (30 dias) |

---

## 7. Sequencia Completa (do zero)

Apos reset do banco, rodar nesta ordem:

```bash
# 1. Fundacao
docker exec licitacoes-cron rm -f /app/cache/municipios.json /app/cache/microrregioes.json
docker exec licitacoes-cron python main.py --sync-municipios
docker exec licitacoes-cron python main.py --sync-plataformas

# 2. Coleta de licitacoes (30 dias)
docker exec licitacoes-cron python main.py --apenas-coletar --dias 30

# 3. Coleta de itens e resultados
docker exec licitacoes-cron python main.py --coletar-itens --limite-itens 500
docker exec licitacoes-cron python main.py --coletar-resultados --limite-itens 500

# 4. Itens por plataforma (todas)
for id in 121 12 13 18 3 5 90; do
  docker exec licitacoes-cron python main.py --coletar-plataforma $id --dias-coleta 90
done

# 5. Prospeccao por org
docker exec licitacoes-cron python main.py --prospectar

# 6. Analises
docker exec licitacoes-cron python main.py --analisar-editais --limite-editais 50

# 7. Calculos
docker exec licitacoes-cron python main.py --calcular-precos
docker exec licitacoes-cron python main.py --calcular-comparativo
```

**Tempo total:** ~7-8h (maior parte e coleta com rate limiting)

---

## 8. Dados Coletados por Fase

### Fase 1: Licitacoes (`licitacoes`)

Campos armazenados da API PNCP:
- Processo: objeto, informacao complementar, modalidade, situacao
- Orgao: nome, CNPJ
- Valores: estimado, homologado
- Datas: publicacao, abertura proposta, encerramento proposta, atualizacao
- Geografico: municipio, UF, codigo IBGE
- Extras: SRP (registro de precos), amparo legal, numero do processo, link sistema origem, tipo instrumento convocatorio
- `dados_brutos`: JSON completo da resposta da API

### Fase 2: Itens (`itens_contratacao`) e Resultados (`resultados_item`)

Itens:
- descricao, NCM, quantidade, unidade, valor unitario estimado, valor total estimado
- material/servico, tipo beneficio, criterio julgamento
- plataforma, UF, municipio, codigo IBGE

Resultados:
- valor unitario homologado, valor total homologado, quantidade homologada
- percentual desconto, CNPJ fornecedor, nome fornecedor, porte fornecedor
- data resultado

### Fase 3: Oportunidades (`oportunidades_org`)

Por organizacao:
- score (0-100), relevancia (ALTA/MEDIA/BAIXA), urgencia
- palavras-chave encontradas, campos matched (objeto/complementar/itens)
- itens matched (numero, descricao, quantidade, valor)
- total de itens, itens relevantes, valor dos itens relevantes

---

## 9. Deploy e Restart

### Build e restart de todos os containers

```bash
cd /home/deploy/licitae-backend
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

### Restart so do cron

```bash
docker compose -f docker-compose.prod.yml restart licitacoes-cron
```

### Restart so do MCP server

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate licitae-mcp
```

### Ver logs

```bash
# Cron (busca, coleta, calculos)
docker logs licitacoes-cron --tail 50
docker logs licitacoes-cron -f  # tempo real

# MCP server
docker logs licitae-mcp --tail 20

# Filtrar erros
docker logs licitacoes-cron 2>&1 | grep ERROR | tail -20

# Filtrar por fase
docker logs licitacoes-cron 2>&1 | grep "Coleta generica" | tail -5
docker logs licitacoes-cron 2>&1 | grep "Prospeccao" | tail -5
```

### Limpar cache

```bash
docker exec licitacoes-cron rm -f /app/cache/municipios.json /app/cache/microrregioes.json
```

---

## 10. Verificacao Rapida

### Contar registros no banco (rodar no Supabase SQL Editor)

```sql
SELECT 'licitacoes' AS tabela, count(*) FROM licitacoes
UNION ALL SELECT 'itens_contratacao', count(*) FROM itens_contratacao
UNION ALL SELECT 'resultados_item', count(*) FROM resultados_item
UNION ALL SELECT 'oportunidades_org', count(*) FROM oportunidades_org
UNION ALL SELECT 'analise_editais', count(*) FROM analise_editais
UNION ALL SELECT 'preco_referencia', count(*) FROM preco_referencia_licitacao
UNION ALL SELECT 'comparativo_itens', count(*) FROM comparativo_itens
UNION ALL SELECT 'comparativo_plat', count(*) FROM comparativo_plataformas
UNION ALL SELECT 'microrregioes', count(*) FROM microrregioes;
```

### Verificar licitacoes por UF

```sql
SELECT uf, count(*) AS total,
  count(*) FILTER (WHERE proposta_aberta) AS abertas,
  count(*) FILTER (WHERE itens_coletados) AS com_itens
FROM licitacoes GROUP BY uf ORDER BY total DESC;
```

### Verificar itens por plataforma

```sql
SELECT plataforma_nome, count(*) FROM itens_contratacao
GROUP BY plataforma_nome ORDER BY count(*) DESC;
```

### Verificar oportunidades por org

```sql
SELECT oc.org_id, o.nome AS org,
  count(*) AS total,
  count(*) FILTER (WHERE oo.relevancia = 'ALTA') AS alta,
  count(*) FILTER (WHERE oo.relevancia = 'MEDIA') AS media
FROM oportunidades_org oo
JOIN org_config oc ON oc.org_id = oo.org_id
JOIN organizacoes o ON o.id = oc.org_id
GROUP BY oc.org_id, o.nome;
```

### Verificar microrregioes

```sql
SELECT uf, count(*) AS microrregioes,
  (SELECT count(*) FROM municipios m WHERE m.microrregiao_id IS NOT NULL AND m.uf = mr.uf) AS municipios_vinculados
FROM microrregioes mr GROUP BY uf ORDER BY uf;
```

---

## IDs das Plataformas

| ID | Nome |
|----|------|
| 121 | SH3 Informatica |
| 12 | BLL Compras (BNC) |
| 13 | Licitar Digital |
| 18 | Licitanet |
| 3 | Compras.gov.br |
| 5 | ECustomize |
| 82 | Governanca Brasil |
| 84 | Betha Sistemas |
| 55 | Portal de Compras Publicas |
| 100 | Outro |
| 90 | BBNet |

---

## Tabelas Principais

| Tabela | Descricao | Populada por |
|--------|-----------|-------------|
| `municipios` | Municipios IBGE com FPM e microrregiao | sync-municipios |
| `microrregioes` | Microrregioes IBGE com mesorregiao | sync-municipios |
| `plataformas_pncp` | Plataformas conhecidas do PNCP | sync-plataformas |
| `licitacoes` | Processos licitatorios coletados | Fase 1 (coleta) |
| `itens_contratacao` | Itens de cada processo | Fase 2 (itens) |
| `resultados_item` | Resultado homologado por item | Fase 2 (resultados) |
| `oportunidades_org` | Oportunidades per-org com score | Fase 3 (prospeccao) |
| `org_config` | Config de filtros por org | Frontend (admin) |
| `analise_editais` | Analise de PDFs de editais | analisar-editais |
| `preco_referencia_licitacao` | Precos de referencia | calcular-precos |
| `comparativo_plataformas` | Resumo materializado por plataforma | calcular-comparativo |
| `comparativo_itens` | Itens comparaveis materializados | calcular-comparativo |
