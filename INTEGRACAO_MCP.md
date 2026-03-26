# Planejamento de Integração — MCP Server + Licitaê

## Visão Geral

O MCP Server expõe 12 tools que dão ao Claude acesso direto aos dados do Supabase.
A integração acontece em **3 camadas**, cada uma com valor independente:

1. **Claude Code local** — consultas ad-hoc via terminal (imediato)
2. **Análise sob demanda** — usuário pede análise IA no app (curto prazo)
3. **Enriquecimento automático** — cron chama Claude para processar licitações (médio prazo)

---

## Arquitetura Atual vs Com MCP

```
HOJE:
  PNCP API → Backend (cron) → regex/heurística → Supabase → Frontend (leitura)
                                    ↑
                              limitações:
                              - regex não entende contexto
                              - stopwords fixas perdem nuance
                              - score de risco é checklist, não análise
                              - agrupamento de itens falha em variações

COM MCP:
  PNCP API → Backend (cron) → Supabase → MCP Server → Claude (análise semântica)
                                              ↓
                                    Supabase (campos enriquecidos)
                                              ↓
                                         Frontend
```

---

## Camada 1: Claude Code Local (imediato)

### O que é
Você configura o MCP no Claude Code e faz perguntas diretas sobre licitações.

### Configuração

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "licitae": {
      "url": "https://<vps-ip>:8080/sse"
    }
  }
}
```

### Exemplos de uso

```
"Quais licitações de software abertas em MG com valor acima de R$100k?"
→ Claude chama buscar_licitacoes(uf="MG", proposta_aberta=true, valor_min=100000)

"Analise o edital da licitação X e me diga os riscos"
→ Claude chama analisar_edital(licitacao_id="X")
→ Lê o texto extraído + achados estruturados
→ Identifica riscos com compreensão real (não regex)

"Compare preços de licença de software entre SH3 e BLL em MG"
→ Claude chama comparar_itens_similares("licença software", "MG")
→ Agrupa semanticamente (regex não faria isso)
→ Apresenta comparação com contexto

"Este fornecedor CNPJ X é confiável?"
→ Claude chama consultar_fornecedor("X")
→ Analisa histórico: vitórias, plataformas, valores, consistência
```

### Valor
- Zero mudança no código — só configuração
- Substitui queries SQL manuais
- Claude faz a análise que regex/stopwords não conseguem

---

## Camada 2: Análise Sob Demanda no App (curto prazo)

### O que é
Botão "Analisar com IA" no frontend que chama o Claude via API para enriquecer dados.

### Fluxo

```
Frontend                    Backend API              Claude API
   │                            │                        │
   │  POST /api/analise-ia      │                        │
   │  { licitacao_id }          │                        │
   │ ─────────────────────────► │                        │
   │                            │  Busca dados Supabase  │
   │                            │  (licitação + edital   │
   │                            │   + preços + itens)    │
   │                            │                        │
   │                            │  POST /v1/messages     │
   │                            │  { system: prompt,     │
   │                            │    user: dados JSON }  │
   │                            │ ─────────────────────► │
   │                            │                        │
   │                            │  ◄───────────────────  │
   │                            │  { análise estruturada}│
   │                            │                        │
   │                            │  Grava no Supabase     │
   │                            │  (analise_ia_licitacao)│
   │                            │                        │
   │  ◄────────────────────────  │                        │
   │  { análise + recomendação } │                        │
```

### Implementação necessária

#### Backend: novo módulo `ia_analysis/`

```
ia_analysis/
  __init__.py
  constants.py          # Prompts do sistema, limites
  services/
    preparacao.py       # Consolida dados do Supabase em contexto
    analise.py          # Chama Claude API com o contexto
    persistencia.py     # Grava resultado no Supabase
  prompts/
    avaliar_edital.py   # Prompt especializado para editais
    avaliar_preco.py    # Prompt para análise de preços
    avaliar_viabilidade.py  # Prompt para decisão de participação
```

#### Backend: novo endpoint (ou Edge Function Supabase)

Duas opções:

**Opção A: Edge Function no Supabase (recomendado)**
- Sem servidor extra
- Chamada direta do frontend
- Rate limiting pelo Supabase
- Custo por invocação (Claude API)

```sql
-- supabase/functions/analise-ia/index.ts
// Recebe licitacao_id
// Busca dados via service_role
// Chama Claude API
// Grava resultado
// Retorna ao frontend
```

**Opção B: Endpoint no backend Python**
- Precisa de web server (FastAPI/Flask)
- Mais controle sobre prompts
- Pode reusar lógica existente

```python
# ia_analysis/api.py
@app.post("/api/analise-ia")
async def analisar(licitacao_id: str):
    dados = preparar_contexto(licitacao_id)
    resultado = await chamar_claude(dados)
    gravar_resultado(licitacao_id, resultado)
    return resultado
```

#### Supabase: nova tabela

```sql
CREATE TABLE analise_ia_licitacao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    licitacao_id UUID REFERENCES licitacoes(id),
    tipo TEXT NOT NULL,  -- 'edital', 'preco', 'viabilidade', 'completa'

    -- Resultado estruturado
    recomendacao TEXT,           -- 'participar', 'avaliar', 'descartar'
    score_viabilidade SMALLINT,  -- 0-100
    resumo TEXT,                 -- 1-2 parágrafos

    -- Detalhes
    riscos_identificados JSONB,  -- [{risco, gravidade, mitigacao}]
    oportunidades JSONB,         -- [{oportunidade, impacto}]
    preco_sugerido NUMERIC(14,2),
    margem_sugerida NUMERIC(5,2),
    concorrentes_provaveis JSONB,

    -- Metadados
    modelo_usado TEXT,
    tokens_usados INT,
    custo_estimado NUMERIC(8,4),
    tempo_processamento_ms INT,
    created_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(licitacao_id, tipo)
);
```

#### Frontend: composable + componente

```typescript
// useAnaliseIA.ts
export function useAnaliseIA() {
  const analise = ref<AnaliseIA | null>(null)
  const analisando = ref(false)

  async function analisar(licitacaoId: string, tipo: TipoAnalise) {
    analisando.value = true
    // Chama Edge Function ou backend
    const { data } = await supabase.functions.invoke('analise-ia', {
      body: { licitacao_id: licitacaoId, tipo }
    })
    analise.value = data
    analisando.value = false
  }

  async function buscarExistente(licitacaoId: string) {
    const { data } = await supabase
      .from('analise_ia_licitacao')
      .select('*')
      .eq('licitacao_id', licitacaoId)
      .limit(1)
      .single()
    analise.value = data
  }

  return { analise, analisando, analisar, buscarExistente }
}
```

```vue
<!-- DetalheAnaliseIA.vue -->
<template>
  <ion-card v-if="analise">
    <ion-card-header>
      <ion-badge :color="corRecomendacao">{{ analise.recomendacao }}</ion-badge>
      <ion-card-title>Análise IA</ion-card-title>
    </ion-card-header>
    <ion-card-content>
      <p>{{ analise.resumo }}</p>

      <h3>Riscos</h3>
      <ion-list>
        <ion-item v-for="r in analise.riscos_identificados" :key="r.risco">
          <ion-icon :icon="warningOutline" :color="corGravidade(r.gravidade)" slot="start" />
          <ion-label>
            <h3>{{ r.risco }}</h3>
            <p>{{ r.mitigacao }}</p>
          </ion-label>
        </ion-item>
      </ion-list>

      <div v-if="analise.preco_sugerido" class="preco-sugerido">
        <strong>Preço sugerido:</strong> R$ {{ formatarValor(analise.preco_sugerido) }}
        <span>(margem {{ analise.margem_sugerida }}%)</span>
      </div>
    </ion-card-content>
  </ion-card>

  <ion-button v-else @click="analisar(licitacaoId, 'completa')" :loading="analisando">
    Analisar com IA
  </ion-button>
</template>
```

### Custos estimados

| Tipo de análise | Tokens (aprox) | Custo por chamada (Sonnet) |
|---|---|---|
| Edital simples | ~5k input + ~2k output | ~$0.02 |
| Preço de referência | ~3k input + ~1k output | ~$0.01 |
| Viabilidade completa | ~15k input + ~3k output | ~$0.07 |

Para 50 análises/dia: **~$2-3/dia** (~R$15/dia)

---

## Camada 3: Enriquecimento Automático (médio prazo)

### O que é
Cron diário chama Claude para analisar automaticamente as melhores oportunidades.

### Fluxo

```
Cron (23:00)
  │
  ├─ Busca top 20 licitações abertas (ALTA relevância, sem análise IA)
  │
  ├─ Para cada licitação:
  │   ├─ Consolida: edital + preços + itens + comparativo
  │   ├─ Chama Claude API (modelo Haiku para economia)
  │   ├─ Grava analise_ia_licitacao
  │   └─ Se score_viabilidade >= 75:
  │       └─ Cria alerta push/email para o usuário
  │
  └─ Log: "20 licitações analisadas, 8 recomendadas, custo: $0.80"
```

### Implementação

```python
# ia_analysis/services/batch.py

async def analisar_licitacoes_pendentes(limite: int = 20) -> dict:
    """Analisa licitações de alta relevância sem análise IA."""
    client = get_client()

    # Busca pendentes
    pendentes = (
        client.table("licitacoes")
        .select("id, objeto, uf, valor_estimado")
        .eq("proposta_aberta", True)
        .eq("relevancia", "ALTA")
        .order("data_publicacao", desc=True)
        .limit(limite * 2)
        .execute()
    )

    # Filtra as que já têm análise
    ids = [l["id"] for l in pendentes.data]
    ja_analisadas = (
        client.table("analise_ia_licitacao")
        .select("licitacao_id")
        .in_("licitacao_id", ids)
        .execute()
    )
    ids_prontos = {r["licitacao_id"] for r in (ja_analisadas.data or [])}

    a_analisar = [l for l in pendentes.data if l["id"] not in ids_prontos][:limite]

    resultados = {"analisadas": 0, "recomendadas": 0, "erros": 0}

    for lic in a_analisar:
        try:
            contexto = preparar_contexto(client, lic["id"])
            analise = await chamar_claude(contexto, tipo="viabilidade")
            gravar_resultado(client, lic["id"], analise)

            resultados["analisadas"] += 1
            if analise.get("score_viabilidade", 0) >= 75:
                resultados["recomendadas"] += 1
                # Notifica usuário
                criar_alerta(client, lic["id"], analise)
        except Exception as e:
            log.error("[%s] Erro na análise IA: %s", lic["id"][:8], e)
            resultados["erros"] += 1

    return resultados
```

### Cron no main.py

```python
# Adicionar ao schedule
schedule.every().day.at("23:00").do(executar_analise_ia)

def executar_analise_ia():
    try:
        import asyncio
        from ia_analysis.services.batch import analisar_licitacoes_pendentes
        stats = asyncio.run(analisar_licitacoes_pendentes(limite=20))
        log.info("Análise IA: %s", stats)
    except Exception as e:
        log.error("Erro na análise IA: %s", e)
```

---

## O que o MCP Substitui (heurísticas → IA)

| Módulo | Heurística atual | O que a IA faz melhor |
|---|---|---|
| `edital_analysis/regex_extraction.py` | Regex busca "garantia\|caução" | Claude entende *tipo* de garantia, *percentual*, e se é razoável |
| `edital_analysis/risk_scoring.py` | Checklist de 8 fatores fixos | Claude avalia risco real no contexto (edital + mercado + histórico) |
| `pricing_reference/similaridade.py` | text_search PostgreSQL | Claude identifica similaridade semântica real |
| `market_comparison/ncm_lexical.py` | 3 palavras-chave + NCM | Claude agrupa "filtro de óleo" = "elemento filtrante" = "cartucho" |
| `market_comparison/comparability.py` | Score por 6 regras fixas | Claude avalia se itens são realmente comparáveis pelo contexto |
| Nenhum | — | Claude detecta editais "armados" (direcionados a um fornecedor) |
| Nenhum | — | Claude sugere preço competitivo e margem ideal |
| Nenhum | — | Claude prevê quem vai participar (baseado em histórico) |

### Importante: não remover as heurísticas

As heurísticas continuam rodando no cron — são rápidas, gratuitas e dão um baseline.
A IA **enriquece** os resultados, não substitui o pipeline.

```
Pipeline atual (cron):    regex → score → Supabase    (grátis, rápido)
Pipeline IA (sob demanda): dados → Claude → Supabase  (pago, profundo)
Frontend mostra:          dados do cron + análise IA quando disponível
```

---

## Prompts Especializados

### Prompt: Avaliação de Viabilidade

```
Você é um analista de licitações públicas brasileiras especializado em
software e tecnologia. Analise a licitação abaixo e avalie se vale participar.

CONTEXTO DA ORGANIZAÇÃO:
- Empresa de software de gestão pública
- Atua em: {ufs}
- Foco: {palavras_chave}
- Termos que NÃO fazemos: {termos_exclusao}

LICITAÇÃO:
{json_licitacao}

EDITAL (achados extraídos):
{json_edital}

PREÇOS DE REFERÊNCIA:
{json_precos}

ITENS:
{json_itens}

COMPARATIVO DE MERCADO NA UF:
{json_comparativo}

Retorne um JSON com:
{
  "recomendacao": "participar" | "avaliar" | "descartar",
  "score_viabilidade": 0-100,
  "resumo": "1-2 parágrafos explicando a decisão",
  "riscos_identificados": [
    {"risco": "...", "gravidade": "alta|media|baixa", "mitigacao": "..."}
  ],
  "oportunidades": [
    {"oportunidade": "...", "impacto": "alto|medio|baixo"}
  ],
  "preco_sugerido": valor_numerico_ou_null,
  "margem_sugerida": percentual_ou_null,
  "concorrentes_provaveis": ["empresa1", "empresa2"],
  "perguntas_para_esclarecimento": ["pergunta1", "pergunta2"]
}
```

### Prompt: Comparação Semântica de Itens

```
Você é um especialista em compras públicas. Analise os itens abaixo,
que foram buscados por similaridade textual, e agrupe-os semanticamente.

Itens podem ter descrições diferentes mas serem o mesmo produto:
- "Licença de uso de software" = "Permissão de uso de sistema"
- "Filtro de óleo motor" = "Elemento filtrante automotivo"

ITENS (de múltiplas plataformas):
{json_itens}

Para cada grupo semântico, retorne:
{
  "grupos": [
    {
      "nome_grupo": "nome descritivo curto",
      "itens_ids": [1, 5, 12, ...],
      "preco_minimo": X,
      "preco_maximo": Y,
      "preco_justo_estimado": Z,
      "plataforma_mais_barata": "nome",
      "observacoes": "notas sobre variação de especificações"
    }
  ],
  "itens_nao_agrupados": [3, 7],
  "observacoes_gerais": "..."
}
```

---

## Ordem de Implementação

### Fase 1 — MCP no Claude Code (esta semana)
- [x] Criar mcp_server/ com 12 tools
- [x] Dockerfile.mcp + docker-compose
- [ ] Deploy na VPS: `docker-compose up -d licitae-mcp`
- [ ] Configurar `~/.claude/settings.json` com URL do MCP
- [ ] Testar: perguntar ao Claude sobre licitações
- **Esforço**: 1 hora (deploy + config)
- **Custo**: $0 (usa o Claude Code que já tem)

### Fase 2 — Análise sob demanda (próximas 2 semanas)
- [ ] Criar tabela `analise_ia_licitacao` (migration 024)
- [ ] Implementar `ia_analysis/` no backend
- [ ] Criar Edge Function ou endpoint FastAPI
- [ ] Frontend: `useAnaliseIA.ts` + `DetalheAnaliseIA.vue`
- [ ] Botão "Analisar com IA" no detalhe da licitação
- [ ] Configurar API key da Anthropic no .env
- **Esforço**: 3-5 dias
- **Custo**: ~$0.02-0.07 por análise

### Fase 3 — Enriquecimento automático (próximo mês)
- [ ] `ia_analysis/services/batch.py` — processamento em lote
- [ ] Integrar no cron do main.py (23:00)
- [ ] Alertas inteligentes: notificar só quando IA recomenda
- [ ] Dashboard: mostrar análises IA no resumo
- [ ] Métricas: tracking de custo e acurácia
- **Esforço**: 1 semana
- **Custo**: ~$2-3/dia para 20 análises

### Fase 4 — Refinamentos (contínuo)
- [ ] Cache de análises (não re-analisar se dados não mudaram)
- [ ] Feedback loop: usuário marca se recomendação foi boa → ajusta prompts
- [ ] Modelo adaptativo: Haiku para triagem, Sonnet para análise profunda
- [ ] Comparação semântica de itens em batch (substituir ncm_lexical)
- [ ] Detecção de editais direcionados

---

## Decisões em Aberto

### 1. Edge Function vs Endpoint Python?
- **Edge Function**: mais simples, menos infra, mas TypeScript
- **Endpoint Python**: reutiliza código existente, mas precisa de web server
- **Recomendação**: Edge Function para Fase 2, migrar para Python se complexidade crescer

### 2. Modelo Claude para batch?
- **Haiku**: barato ($0.001/análise), bom para triagem
- **Sonnet**: melhor qualidade ($0.02/análise), bom para análise completa
- **Recomendação**: Haiku para triagem (score > 50?), Sonnet só para as top 20

### 3. Quanto contexto enviar ao Claude?
- **Mínimo**: licitação + edital resumido (~3k tokens)
- **Completo**: tudo + comparativo + itens (~15k tokens)
- **Recomendação**: completo para Sonnet, resumido para Haiku

### 4. Onde o MCP Server roda?
- **Mesmo container do cron**: simples mas consome memória
- **Container separado** (atual): isolado, mais robusto
- **Recomendação**: container separado (já implementado)

---

## Métricas de Sucesso

| Métrica | Baseline (sem IA) | Meta (com IA) |
|---|---|---|
| Tempo para avaliar uma licitação | 15-30 min (manual) | 30 seg (IA) + 5 min (revisão) |
| Acurácia de agrupamento de itens | ~30% (regex) | ~85% (semântico) |
| Licitações descartadas cedo | ~20% | ~50% (IA filtra melhor) |
| Riscos não detectados por edital | ~40% perdidos | ~10% perdidos |
| Custo mensal | $0 | ~$60-90 |

---

## Segurança

- MCP Server usa `SUPABASE_SERVICE_KEY` — acesso total ao banco
- SSE endpoint deve estar atrás de VPN ou com auth token
- Não expor porta 8080 publicamente sem proteção
- Claude API key no .env — não commitar
- Rate limiting: máximo 100 chamadas/hora ao Claude

### Opções de proteção do SSE

```nginx
# nginx.conf na VPS
location /sse {
    # Só aceita de IPs conhecidos
    allow 189.x.x.x;  # IP da Sara
    deny all;

    proxy_pass http://localhost:8080;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}
```

Ou usar header de auth:
```python
# mcp_server/server.py — adicionar middleware
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

async def auth_middleware(request):
    if MCP_AUTH_TOKEN and request.headers.get("Authorization") != f"Bearer {MCP_AUTH_TOKEN}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)
```
