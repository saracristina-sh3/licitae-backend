-- ============================================================
-- Licitaê — Schema Completo Consolidado
-- Substitui migrations 001-025
-- Data: 2026-03-26
-- ============================================================

-- Extensões
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE relevancia_tipo AS ENUM ('ALTA', 'MEDIA', 'BAIXA');

CREATE TYPE oportunidade_status AS ENUM (
    'identificada', 'analisando', 'preparando_proposta',
    'proposta_enviada', 'ganha', 'perdida', 'descartada'
);

CREATE TYPE fonte_tipo AS ENUM (
    'PNCP', 'TCE_RJ', 'QUERIDO_DIARIO', 'DOM_MG', 'MANUAL'
);

CREATE TYPE alerta_canal AS ENUM ('email', 'push', 'telegram', 'whatsapp');

CREATE TYPE org_role AS ENUM ('admin', 'membro');

-- ============================================================
-- TIER 1: Tabelas fundação (sem dependências)
-- ============================================================

CREATE TABLE municipios (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_ibge TEXT UNIQUE NOT NULL,
    nome TEXT NOT NULL,
    uf CHAR(2) NOT NULL,
    populacao INTEGER NOT NULL DEFAULT 0,
    fpm NUMERIC(3,1) NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_municipios_uf ON municipios(uf);
CREATE INDEX idx_municipios_fpm ON municipios(fpm);

CREATE TABLE organizacoes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    nome TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE plataformas_pncp (
    id_usuario INT PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT,
    ativo BOOLEAN DEFAULT true,
    total_contratacoes INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE dominios_pncp (
    id SERIAL PRIMARY KEY,
    dominio TEXT NOT NULL,
    codigo INTEGER NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    ativo BOOLEAN DEFAULT true,
    UNIQUE(dominio, codigo)
);

CREATE INDEX idx_dominios_pncp_dominio ON dominios_pncp(dominio);

-- ============================================================
-- TIER 2: Auth-related
-- ============================================================

CREATE TABLE profiles (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    nome TEXT,
    email TEXT,
    avatar_url TEXT,
    org_id UUID REFERENCES organizacoes(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_profiles_org ON profiles(org_id);

CREATE TABLE user_config (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE NOT NULL,
    ufs TEXT[] DEFAULT '{MG,RJ,SP,ES,PR,SC,RS,GO,BA,PE,CE}',
    fpm_maximo NUMERIC(3,1) DEFAULT 2.8,
    palavras_chave TEXT[] DEFAULT '{software,sistema,permissão de uso,licença de uso,cessão de uso,locação de software,sistema integrado de gestão,solução tecnológica,gestão pública}',
    alertas_email BOOLEAN DEFAULT true,
    alertas_push BOOLEAN DEFAULT true,
    alertas_telegram BOOLEAN DEFAULT false,
    telegram_chat_id TEXT,
    modalidades INTEGER[] DEFAULT '{6,7,8,9,12}',
    fontes TEXT[] DEFAULT '{PNCP,QUERIDO_DIARIO,TCE_RJ}',
    termos_alta TEXT[] DEFAULT '{permissão de uso,licença de uso,cessão de uso,locação de software,sistema integrado de gestão}',
    termos_media TEXT[] DEFAULT '{software,sistema de gestão,solução tecnológica}',
    termos_me_epp TEXT[] DEFAULT '{exclusivo para microempresa,exclusivo para me,exclusivo me/epp,exclusivo me e epp,participação exclusiva,cota reservada,lei complementar 123}',
    dias_retroativos INTEGER DEFAULT 7,
    plano TEXT DEFAULT 'free' CHECK (plano IN ('free', 'pro')),
    plano_expira_em TIMESTAMPTZ,
    apple_transaction_id TEXT,
    org_id UUID REFERENCES organizacoes(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_user_config_plano ON user_config(plano);

-- ============================================================
-- TIER 3: Organizações
-- ============================================================

CREATE TABLE org_membros (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id UUID REFERENCES organizacoes(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    role org_role NOT NULL DEFAULT 'membro',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, user_id)
);

CREATE INDEX idx_org_membros_user ON org_membros(user_id);
CREATE INDEX idx_org_membros_org ON org_membros(org_id);

CREATE TABLE org_convites (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    org_id UUID REFERENCES organizacoes(id) ON DELETE CASCADE NOT NULL,
    email TEXT NOT NULL,
    convidado_por UUID REFERENCES auth.users(id) NOT NULL,
    aceito BOOLEAN DEFAULT false,
    email_enviado BOOLEAN DEFAULT false,
    nome_convidante TEXT,
    nome_organizacao TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, email)
);

CREATE TABLE org_termos_exclusao (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizacoes(id) ON DELETE CASCADE,
    termo TEXT NOT NULL,
    criado_por UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, termo)
);

CREATE INDEX idx_org_termos_exclusao_org_id ON org_termos_exclusao(org_id);

CREATE TABLE org_dominios_config (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizacoes(id) ON DELETE CASCADE,
    dominio TEXT NOT NULL,
    codigos_ativos INTEGER[] NOT NULL DEFAULT '{}',
    atualizado_por UUID REFERENCES auth.users(id),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, dominio)
);

CREATE INDEX idx_org_dominios_config_org ON org_dominios_config(org_id);

-- ============================================================
-- TIER 4: Licitações core
-- ============================================================

CREATE TABLE licitacoes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    hash_dedup TEXT UNIQUE NOT NULL,
    municipio_id BIGINT REFERENCES municipios(id),
    municipio_nome TEXT NOT NULL,
    uf CHAR(2) NOT NULL,
    orgao TEXT,
    cnpj_orgao TEXT,
    objeto TEXT NOT NULL,
    modalidade TEXT,
    valor_estimado NUMERIC(15,2) DEFAULT 0,
    valor_homologado NUMERIC(15,2) DEFAULT 0,
    situacao TEXT,
    data_publicacao TIMESTAMPTZ,
    data_abertura_proposta TIMESTAMPTZ,
    data_encerramento_proposta TIMESTAMPTZ,
    fonte fonte_tipo NOT NULL DEFAULT 'PNCP',
    url_fonte TEXT,
    relevancia relevancia_tipo NOT NULL DEFAULT 'BAIXA',
    palavras_chave TEXT[],
    dados_brutos JSONB,
    proposta_aberta BOOLEAN DEFAULT true,
    exclusivo_me_epp BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_licitacoes_uf ON licitacoes(uf);
CREATE INDEX idx_licitacoes_relevancia ON licitacoes(relevancia);
CREATE INDEX idx_licitacoes_fonte ON licitacoes(fonte);
CREATE INDEX idx_licitacoes_municipio ON licitacoes(municipio_id);
CREATE INDEX idx_licitacoes_proposta_aberta ON licitacoes(proposta_aberta) WHERE proposta_aberta = true;
CREATE INDEX idx_licitacoes_data_pub ON licitacoes(data_publicacao DESC);
CREATE INDEX idx_licitacoes_me_epp ON licitacoes(exclusivo_me_epp) WHERE exclusivo_me_epp = true;
CREATE INDEX idx_licitacoes_objeto_trgm ON licitacoes USING gin(objeto gin_trgm_ops);

CREATE TABLE analise_editais (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    licitacao_id UUID REFERENCES licitacoes(id) ON DELETE CASCADE NOT NULL UNIQUE,
    -- Dados estruturados (v2 — fonte única)
    documentos_estruturados JSONB DEFAULT '[]',
    requisitos_estruturados JSONB DEFAULT '[]',
    riscos_estruturados JSONB DEFAULT '[]',
    qualificacao_estruturada JSONB DEFAULT '[]',
    prazos_classificados JSONB DEFAULT '[]',
    -- Texto extraído
    texto_extraido TEXT,
    url_documento TEXT,
    paginas INTEGER DEFAULT 0,
    -- Scores
    score_confianca NUMERIC(5,1),
    faixa_confianca TEXT,
    score_risco NUMERIC(5,1),
    nivel_risco TEXT,
    fatores_risco JSONB DEFAULT '[]',
    -- Qualidade da extração
    qualidade_extracao NUMERIC(4,2),
    faixa_qualidade TEXT,
    arquivo_escolhido TEXT,
    score_arquivo NUMERIC(5,2),
    -- Metadados
    versao_algoritmo TEXT DEFAULT 'v2',
    metodo_extracao TEXT DEFAULT 'pdfminer',
    tempo_processamento_ms INT,
    houve_fallback BOOLEAN DEFAULT false,
    analisado_em TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_analise_licitacao ON analise_editais(licitacao_id);

CREATE TABLE analise_ia_licitacao (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    licitacao_id UUID NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL DEFAULT 'completa',
    recomendacao TEXT,
    score_viabilidade SMALLINT,
    resumo TEXT,
    riscos_identificados JSONB DEFAULT '[]',
    oportunidades JSONB DEFAULT '[]',
    preco_sugerido NUMERIC(14,2),
    margem_sugerida NUMERIC(14,2),
    concorrentes_provaveis JSONB DEFAULT '[]',
    perguntas_esclarecimento TEXT[] DEFAULT '{}',
    modelo_usado TEXT,
    tokens_input INT,
    tokens_output INT,
    custo_usd NUMERIC(8,4),
    tempo_ms INT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(licitacao_id, tipo)
);

CREATE INDEX idx_analise_ia_licitacao_id ON analise_ia_licitacao(licitacao_id);
CREATE INDEX idx_analise_ia_score ON analise_ia_licitacao(score_viabilidade DESC);

-- ============================================================
-- TIER 5: Oportunidades e monitoramento
-- ============================================================

CREATE TABLE oportunidades (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    licitacao_id UUID REFERENCES licitacoes(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    org_id UUID REFERENCES organizacoes(id) ON DELETE SET NULL,
    status oportunidade_status NOT NULL DEFAULT 'identificada',
    responsavel TEXT,
    notas TEXT,
    prazo_interno DATE,
    valor_proposta NUMERIC(15,2),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(licitacao_id, user_id)
);

CREATE INDEX idx_oportunidades_user ON oportunidades(user_id);
CREATE INDEX idx_oportunidades_status ON oportunidades(status);
CREATE INDEX idx_oportunidades_prazo ON oportunidades(prazo_interno) WHERE prazo_interno IS NOT NULL;
CREATE INDEX idx_oportunidades_org ON oportunidades(org_id);

CREATE TABLE historico_status (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    oportunidade_id UUID REFERENCES oportunidades(id) ON DELETE CASCADE NOT NULL,
    status_anterior oportunidade_status,
    status_novo oportunidade_status NOT NULL,
    usuario TEXT,
    observacao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_historico_oportunidade ON historico_status(oportunidade_id);

CREATE TABLE monitoramento (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    oportunidade_id UUID REFERENCES oportunidades(id) ON DELETE CASCADE NOT NULL UNIQUE,
    licitacao_id UUID REFERENCES licitacoes(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    ativo BOOLEAN DEFAULT true,
    ultimo_situacao TEXT,
    ultimo_valor_estimado NUMERIC(15,2),
    ultimo_valor_homologado NUMERIC(15,2),
    ultimo_data_encerramento TIMESTAMPTZ,
    ultimo_proposta_aberta BOOLEAN,
    ultimo_check_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_monitoramento_ativo ON monitoramento(ativo) WHERE ativo = true;
CREATE INDEX idx_monitoramento_user ON monitoramento(user_id);

CREATE TABLE monitoramento_alertas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    monitoramento_id BIGINT REFERENCES monitoramento(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    licitacao_id UUID REFERENCES licitacoes(id) ON DELETE CASCADE NOT NULL,
    campo TEXT NOT NULL,
    valor_anterior TEXT,
    valor_novo TEXT,
    lido BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_alertas_user_lido ON monitoramento_alertas(user_id, lido) WHERE lido = false;

CREATE TABLE prazo_alertas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    oportunidade_id UUID REFERENCES oportunidades(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    licitacao_id UUID REFERENCES licitacoes(id) ON DELETE CASCADE NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('prazo_interno', 'encerramento_proposta')),
    dias_restantes INTEGER NOT NULL CHECK (dias_restantes IN (3, 1, 0)),
    data_prazo DATE NOT NULL,
    lido BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(oportunidade_id, tipo, dias_restantes)
);

CREATE INDEX idx_prazo_alertas_user_lido ON prazo_alertas(user_id, lido) WHERE lido = false;

CREATE TABLE alertas_enviados (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    licitacao_id UUID REFERENCES licitacoes(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    canal alerta_canal NOT NULL,
    destinatario TEXT,
    enviado_em TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- TIER 6: Itens de contratação
-- ============================================================

CREATE TABLE itens_contratacao (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    licitacao_hash TEXT,
    cnpj_orgao TEXT NOT NULL,
    ano_compra INT NOT NULL,
    sequencial_compra INT NOT NULL,
    numero_item INT NOT NULL,
    descricao TEXT,
    ncm_nbs_codigo TEXT,
    quantidade NUMERIC,
    unidade_medida TEXT,
    valor_unitario_estimado NUMERIC(15,2),
    valor_total_estimado NUMERIC(15,2),
    tem_resultado BOOLEAN DEFAULT false,
    plataforma_id INT REFERENCES plataformas_pncp(id_usuario),
    plataforma_nome TEXT,
    uf CHAR(2),
    municipio TEXT,
    codigo_ibge TEXT,
    modalidade_id INT,
    coletado_em TIMESTAMPTZ DEFAULT now(),
    versao_coletor TEXT DEFAULT 'v1',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(cnpj_orgao, ano_compra, sequencial_compra, numero_item)
);

CREATE INDEX idx_itens_ncm ON itens_contratacao(ncm_nbs_codigo);
CREATE INDEX idx_itens_plataforma ON itens_contratacao(plataforma_id);
CREATE INDEX idx_itens_uf ON itens_contratacao(uf);
CREATE INDEX idx_itens_modalidade ON itens_contratacao(modalidade_id);
CREATE INDEX idx_itens_licitacao_hash ON itens_contratacao(licitacao_hash);
CREATE INDEX idx_itens_descricao_trgm ON itens_contratacao USING gin(descricao gin_trgm_ops);
CREATE INDEX idx_itens_ncm_uf ON itens_contratacao(ncm_nbs_codigo, uf);

CREATE TABLE resultados_item (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    item_id UUID REFERENCES itens_contratacao(id) ON DELETE CASCADE,
    sequencial_resultado INT NOT NULL,
    valor_unitario_homologado NUMERIC(15,2),
    valor_total_homologado NUMERIC(15,2),
    quantidade_homologada NUMERIC,
    percentual_desconto NUMERIC(14,2),
    cnpj_fornecedor TEXT,
    nome_fornecedor TEXT,
    porte_fornecedor TEXT,
    data_resultado TIMESTAMPTZ,
    coletado_em TIMESTAMPTZ DEFAULT now(),
    versao_coletor TEXT DEFAULT 'v1',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(item_id, sequencial_resultado)
);

CREATE INDEX idx_resultados_fornecedor ON resultados_item(cnpj_fornecedor);
CREATE INDEX idx_resultados_item ON resultados_item(item_id);

-- ============================================================
-- TIER 7: Preços de referência (materializadas)
-- ============================================================

CREATE TABLE preco_referencia_licitacao (
    id SERIAL PRIMARY KEY,
    licitacao_id UUID NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE UNIQUE,
    -- Geral
    total_similares INT NOT NULL DEFAULT 0,
    valor_minimo NUMERIC(14,2),
    valor_maximo NUMERIC(14,2),
    valor_media NUMERIC(14,2),
    valor_mediana NUMERIC(14,2),
    valor_media_saneada NUMERIC(14,2),
    coeficiente_variacao NUMERIC(14,2),
    amostra_suficiente BOOLEAN DEFAULT false,
    percentil_25 NUMERIC(14,2),
    percentil_75 NUMERIC(14,2),
    -- Homologados
    valor_media_homologado NUMERIC(14,2),
    valor_mediana_homologado NUMERIC(14,2),
    valor_media_saneada_homologado NUMERIC(14,2),
    cv_homologado NUMERIC(14,2),
    total_homologados INT DEFAULT 0,
    -- Estimados
    valor_media_estimado NUMERIC(14,2),
    valor_mediana_estimado NUMERIC(14,2),
    cv_estimado NUMERIC(14,2),
    total_estimados INT DEFAULT 0,
    fonte_predominante TEXT DEFAULT 'misto',
    -- Itens
    total_itens_similares INT NOT NULL DEFAULT 0,
    item_minimo_unitario NUMERIC(14,2),
    item_maximo_unitario NUMERIC(14,2),
    item_media_unitario NUMERIC(14,2),
    item_mediana_unitario NUMERIC(14,2),
    item_media_saneada NUMERIC(14,2),
    item_desconto_medio NUMERIC(14,2),
    item_coeficiente_variacao NUMERIC(14,2),
    item_percentil_25 NUMERIC(14,2),
    item_percentil_75 NUMERIC(14,2),
    -- Confiabilidade
    score_confiabilidade NUMERIC(14,2),
    faixa_confiabilidade TEXT,
    -- Metadados
    janela_meses INT NOT NULL DEFAULT 12,
    versao_algoritmo TEXT DEFAULT 'v3',
    metodo_similaridade TEXT DEFAULT 'text_search',
    metodo_outlier TEXT DEFAULT 'iqr+trimmed_mean',
    calculado_em TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_preco_ref_lic_id ON preco_referencia_licitacao(licitacao_id);

CREATE TABLE preco_referencia_detalhe (
    id SERIAL PRIMARY KEY,
    preco_referencia_id INT NOT NULL REFERENCES preco_referencia_licitacao(id) ON DELETE CASCADE,
    licitacao_similar_id UUID NOT NULL REFERENCES licitacoes(id),
    municipio_nome TEXT,
    uf TEXT,
    objeto TEXT,
    modalidade TEXT,
    valor_homologado NUMERIC(14,2),
    data_publicacao TIMESTAMPTZ,
    score_similaridade NUMERIC(14,2),
    fonte_preco TEXT DEFAULT 'homologado'
);

CREATE INDEX idx_preco_ref_detalhe_ref ON preco_referencia_detalhe(preco_referencia_id);

CREATE TABLE preco_referencia_itens (
    id SERIAL PRIMARY KEY,
    preco_referencia_id INT NOT NULL REFERENCES preco_referencia_licitacao(id) ON DELETE CASCADE,
    descricao TEXT,
    unidade_medida TEXT,
    valor_unitario NUMERIC(14,2),
    plataforma_nome TEXT,
    municipio TEXT,
    uf TEXT,
    nome_fornecedor TEXT,
    percentual_desconto NUMERIC(14,2),
    fonte_preco TEXT DEFAULT 'estimado',
    score_similaridade NUMERIC(14,2),
    compativel_unidade BOOLEAN DEFAULT true
);

CREATE INDEX idx_preco_ref_itens_ref ON preco_referencia_itens(preco_referencia_id);

CREATE TABLE preco_referencia_plataformas (
    id SERIAL PRIMARY KEY,
    preco_referencia_id INT NOT NULL REFERENCES preco_referencia_licitacao(id) ON DELETE CASCADE,
    plataforma_nome TEXT NOT NULL,
    media_unitario NUMERIC(14,2) NOT NULL,
    total_itens INT NOT NULL DEFAULT 0,
    UNIQUE(preco_referencia_id, plataforma_nome)
);

CREATE INDEX idx_preco_ref_plat_ref ON preco_referencia_plataformas(preco_referencia_id);

-- ============================================================
-- TIER 8: Comparativo de mercado (materializadas)
-- ============================================================

CREATE TABLE comparativo_plataformas (
    id SERIAL PRIMARY KEY,
    plataforma_nome TEXT NOT NULL,
    plataforma_id INT NOT NULL,
    total_itens INT NOT NULL DEFAULT 0,
    valor_medio_unitario NUMERIC(14,2) NOT NULL DEFAULT 0,
    mediana_unitario NUMERIC(14,2),
    desconto_medio NUMERIC(14,2),
    cv_medio NUMERIC(14,2),
    vitorias INT NOT NULL DEFAULT 0,
    vitorias_ponderadas NUMERIC(14,2) DEFAULT 0,
    vitorias_alta_confianca INT DEFAULT 0,
    total_grupos_comparaveis INT DEFAULT 0,
    total_grupos_alta_confianca INT DEFAULT 0,
    proporcao_vitorias NUMERIC(14,2),
    proporcao_homologados NUMERIC(14,2),
    score_comparabilidade_medio NUMERIC(14,2),
    ranking_medio NUMERIC(14,2),
    delta_medio_para_lider NUMERIC(14,2),
    versao_algoritmo TEXT DEFAULT 'v4',
    uf TEXT,
    calculado_em TIMESTAMPTZ DEFAULT now(),
    UNIQUE(plataforma_id, uf)
);

CREATE INDEX idx_comparativo_plataformas_uf ON comparativo_plataformas(uf);

CREATE TABLE comparativo_itens (
    id SERIAL PRIMARY KEY,
    chave_agrupamento TEXT NOT NULL,
    descricao TEXT NOT NULL,
    descricao_agrupamento TEXT,
    ncm_nbs_codigo TEXT,
    unidade_medida TEXT,
    menor_preco_plataforma TEXT NOT NULL,
    score_comparabilidade NUMERIC(14,2),
    faixa_confiabilidade TEXT,
    fonte_predominante TEXT DEFAULT 'misto',
    unidade_predominante TEXT,
    taxa_consistencia_unidade NUMERIC(14,2),
    total_observacoes INT DEFAULT 0,
    categoria TEXT DEFAULT 'produto',
    versao_algoritmo TEXT DEFAULT 'v4',
    metodo_agrupamento TEXT DEFAULT 'ncm_lexical_v2',
    metodo_outlier TEXT DEFAULT 'iqr',
    uf TEXT,
    calculado_em TIMESTAMPTZ DEFAULT now(),
    UNIQUE(chave_agrupamento, uf)
);

CREATE INDEX idx_comparativo_itens_uf ON comparativo_itens(uf);

CREATE TABLE comparativo_itens_precos (
    id SERIAL PRIMARY KEY,
    comparativo_item_id INT NOT NULL REFERENCES comparativo_itens(id) ON DELETE CASCADE,
    plataforma_nome TEXT NOT NULL,
    plataforma_id INT NOT NULL,
    valor_medio NUMERIC(14,2) NOT NULL,
    mediana NUMERIC(14,2),
    cv NUMERIC(14,2),
    percentil_25 NUMERIC(14,2),
    percentil_75 NUMERIC(14,2),
    total_ocorrencias INT NOT NULL DEFAULT 0,
    total_homologados INT DEFAULT 0,
    total_estimados INT DEFAULT 0,
    fonte_predominante TEXT DEFAULT 'misto',
    economia_media NUMERIC(14,2),
    UNIQUE(comparativo_item_id, plataforma_id)
);

CREATE INDEX idx_comparativo_itens_precos_item ON comparativo_itens_precos(comparativo_item_id);

-- ============================================================
-- FUNCTIONS
-- ============================================================

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Calcula proposta_aberta
CREATE OR REPLACE FUNCTION calcular_proposta_aberta()
RETURNS TRIGGER AS $$
BEGIN
    NEW.proposta_aberta = (
        NEW.data_encerramento_proposta IS NULL
        OR NEW.data_encerramento_proposta > now()
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Auto-create profile + config on signup
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO profiles (id, nome, email)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'nome', NEW.raw_user_meta_data->>'full_name', ''),
        NEW.email
    );
    INSERT INTO user_config (user_id) VALUES (NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Auto-registrar histórico de status
CREATE OR REPLACE FUNCTION registrar_historico_status()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO historico_status (oportunidade_id, status_anterior, status_novo)
        VALUES (NEW.id, OLD.status, NEW.status);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Org: retorna org_ids do usuário (evita recursão RLS)
CREATE OR REPLACE FUNCTION get_user_org_ids()
RETURNS SETOF UUID AS $$
    SELECT org_id FROM org_membros WHERE user_id = auth.uid();
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

CREATE OR REPLACE FUNCTION get_user_admin_org_ids()
RETURNS SETOF UUID AS $$
    SELECT org_id FROM org_membros WHERE user_id = auth.uid() AND role = 'admin';
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

-- Criar organização
CREATE OR REPLACE FUNCTION criar_organizacao(nome_org TEXT, slug_org TEXT)
RETURNS UUID AS $$
DECLARE new_org_id UUID;
BEGIN
    INSERT INTO organizacoes (nome, slug) VALUES (nome_org, slug_org) RETURNING id INTO new_org_id;
    INSERT INTO org_membros (org_id, user_id, role) VALUES (new_org_id, auth.uid(), 'admin');
    UPDATE profiles SET org_id = new_org_id WHERE id = auth.uid();
    UPDATE user_config SET org_id = new_org_id WHERE user_id = auth.uid();
    RETURN new_org_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Aceitar convite
CREATE OR REPLACE FUNCTION aceitar_convite(convite_id UUID)
RETURNS VOID AS $$
DECLARE v_org_id UUID; v_email TEXT;
BEGIN
    SELECT email INTO v_email FROM auth.users WHERE id = auth.uid();
    SELECT org_id INTO v_org_id FROM org_convites WHERE id = convite_id AND email = v_email AND aceito = false;
    IF v_org_id IS NULL THEN RAISE EXCEPTION 'Convite inválido ou já aceito'; END IF;
    INSERT INTO org_membros (org_id, user_id, role) VALUES (v_org_id, auth.uid(), 'membro') ON CONFLICT (org_id, user_id) DO NOTHING;
    UPDATE profiles SET org_id = v_org_id WHERE id = auth.uid();
    UPDATE user_config SET org_id = v_org_id WHERE user_id = auth.uid();
    UPDATE org_convites SET aceito = true WHERE id = convite_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Sair da organização
CREATE OR REPLACE FUNCTION sair_organizacao()
RETURNS VOID AS $$
BEGIN
    DELETE FROM org_membros WHERE user_id = auth.uid();
    UPDATE profiles SET org_id = NULL WHERE id = auth.uid();
    UPDATE user_config SET org_id = NULL WHERE user_id = auth.uid();
    UPDATE oportunidades SET org_id = NULL WHERE user_id = auth.uid();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- TRIGGERS
-- ============================================================

CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION handle_new_user();
CREATE TRIGGER licitacoes_proposta_aberta BEFORE INSERT OR UPDATE ON licitacoes FOR EACH ROW EXECUTE FUNCTION calcular_proposta_aberta();
CREATE TRIGGER licitacoes_updated_at BEFORE UPDATE ON licitacoes FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER oportunidades_updated_at BEFORE UPDATE ON oportunidades FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER oportunidades_historico AFTER UPDATE ON oportunidades FOR EACH ROW EXECUTE FUNCTION registrar_historico_status();
CREATE TRIGGER municipios_updated_at BEFORE UPDATE ON municipios FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER user_config_updated_at BEFORE UPDATE ON user_config FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER profiles_updated_at BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER organizacoes_updated_at BEFORE UPDATE ON organizacoes FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

-- Municípios
ALTER TABLE municipios ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Municípios visíveis para autenticados" ON municipios FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia municípios" ON municipios FOR ALL TO service_role USING (true);

-- Organizações
ALTER TABLE organizacoes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Membro vê sua organização" ON organizacoes FOR SELECT TO authenticated USING (id IN (SELECT get_user_org_ids()));
CREATE POLICY "Usuário pode criar organização" ON organizacoes FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Admin edita organização" ON organizacoes FOR UPDATE TO authenticated USING (id IN (SELECT get_user_admin_org_ids()));

-- Plataformas
ALTER TABLE plataformas_pncp ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados veem plataformas" ON plataformas_pncp FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia plataformas" ON plataformas_pncp FOR ALL TO service_role USING (true);

-- Profiles
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Profiles visíveis para autenticados" ON profiles FOR SELECT TO authenticated USING (true);
CREATE POLICY "Usuário edita seu profile" ON profiles FOR UPDATE TO authenticated USING (id = auth.uid());

-- User Config
ALTER TABLE user_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuário vê sua config" ON user_config FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY "Usuário cria sua config" ON user_config FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "Usuário edita sua config" ON user_config FOR UPDATE TO authenticated USING (user_id = auth.uid());

-- Org Membros
ALTER TABLE org_membros ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Membro vê colegas" ON org_membros FOR SELECT TO authenticated USING (org_id IN (SELECT get_user_org_ids()));
CREATE POLICY "Admin adiciona membros" ON org_membros FOR INSERT TO authenticated WITH CHECK (org_id IN (SELECT get_user_admin_org_ids()));
CREATE POLICY "Admin remove membros" ON org_membros FOR DELETE TO authenticated USING (org_id IN (SELECT get_user_admin_org_ids()));

-- Org Convites
ALTER TABLE org_convites ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Admin cria convites" ON org_convites FOR INSERT TO authenticated WITH CHECK (org_id IN (SELECT get_user_admin_org_ids()));
CREATE POLICY "Admin vê convites" ON org_convites FOR SELECT TO authenticated USING (org_id IN (SELECT get_user_admin_org_ids()) OR email = (SELECT email FROM auth.users WHERE id = auth.uid()));
CREATE POLICY "Destinatário aceita convite" ON org_convites FOR UPDATE TO authenticated USING (email = (SELECT email FROM auth.users WHERE id = auth.uid()));

-- Org Termos Exclusão
ALTER TABLE org_termos_exclusao ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role acesso total termos" ON org_termos_exclusao FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Membros leem termos" ON org_termos_exclusao FOR SELECT TO authenticated USING (org_id IN (SELECT get_user_org_ids()));
CREATE POLICY "Admins inserem termos" ON org_termos_exclusao FOR INSERT TO authenticated WITH CHECK (org_id IN (SELECT get_user_admin_org_ids()));
CREATE POLICY "Admins deletam termos" ON org_termos_exclusao FOR DELETE TO authenticated USING (org_id IN (SELECT get_user_admin_org_ids()));

-- Domínios PNCP
ALTER TABLE dominios_pncp ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados leem domínios" ON dominios_pncp FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia domínios" ON dominios_pncp FOR ALL TO service_role USING (true);

-- Org Domínios Config
ALTER TABLE org_dominios_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Membro lê config domínios da org" ON org_dominios_config FOR SELECT TO authenticated USING (org_id IN (SELECT get_user_org_ids()));
CREATE POLICY "Admin insere config domínios" ON org_dominios_config FOR INSERT TO authenticated WITH CHECK (org_id IN (SELECT get_user_admin_org_ids()));
CREATE POLICY "Admin atualiza config domínios" ON org_dominios_config FOR UPDATE TO authenticated USING (org_id IN (SELECT get_user_admin_org_ids()));
CREATE POLICY "Admin remove config domínios" ON org_dominios_config FOR DELETE TO authenticated USING (org_id IN (SELECT get_user_admin_org_ids()));

-- Licitações
ALTER TABLE licitacoes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Licitações visíveis para autenticados" ON licitacoes FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia licitações" ON licitacoes FOR ALL TO service_role USING (true);

-- Análise Editais
ALTER TABLE analise_editais ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados veem análises editais" ON analise_editais FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia análises editais" ON analise_editais FOR ALL TO service_role USING (true);

-- Análise IA
ALTER TABLE analise_ia_licitacao ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados veem análise IA" ON analise_ia_licitacao FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia análise IA" ON analise_ia_licitacao FOR ALL TO service_role USING (true);

-- Oportunidades
ALTER TABLE oportunidades ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuário vê oportunidades" ON oportunidades FOR SELECT TO authenticated USING (user_id = auth.uid() OR org_id IN (SELECT get_user_org_ids()));
CREATE POLICY "Usuário cria oportunidades" ON oportunidades FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "Usuário edita oportunidades" ON oportunidades FOR UPDATE TO authenticated USING (user_id = auth.uid() OR org_id IN (SELECT get_user_org_ids()));
CREATE POLICY "Usuário remove oportunidades" ON oportunidades FOR DELETE TO authenticated USING (user_id = auth.uid());

-- Histórico
ALTER TABLE historico_status ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuário vê histórico" ON historico_status FOR SELECT TO authenticated USING (oportunidade_id IN (SELECT id FROM oportunidades WHERE user_id = auth.uid()));
CREATE POLICY "Usuário cria histórico" ON historico_status FOR INSERT TO authenticated WITH CHECK (oportunidade_id IN (SELECT id FROM oportunidades WHERE user_id = auth.uid()));

-- Monitoramento
ALTER TABLE monitoramento ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuário vê seu monitoramento" ON monitoramento FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY "Usuário cria monitoramento" ON monitoramento FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY "Usuário edita monitoramento" ON monitoramento FOR UPDATE TO authenticated USING (user_id = auth.uid());
CREATE POLICY "Usuário remove monitoramento" ON monitoramento FOR DELETE TO authenticated USING (user_id = auth.uid());
CREATE POLICY "Service role gerencia monitoramento" ON monitoramento FOR ALL TO service_role USING (true);

-- Alertas Monitoramento
ALTER TABLE monitoramento_alertas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role insere alertas" ON monitoramento_alertas FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY "Usuário vê seus alertas" ON monitoramento_alertas FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY "Usuário marca alerta como lido" ON monitoramento_alertas FOR UPDATE TO authenticated USING (user_id = auth.uid());

-- Prazo Alertas
ALTER TABLE prazo_alertas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role insere prazo alertas" ON prazo_alertas FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY "Usuário vê prazo alertas" ON prazo_alertas FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY "Usuário marca prazo alerta lido" ON prazo_alertas FOR UPDATE TO authenticated USING (user_id = auth.uid());

-- Alertas Enviados
ALTER TABLE alertas_enviados ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuário vê alertas enviados" ON alertas_enviados FOR SELECT TO authenticated USING (user_id = auth.uid());

-- Itens Contratação
ALTER TABLE itens_contratacao ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados veem itens" ON itens_contratacao FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia itens" ON itens_contratacao FOR ALL TO service_role USING (true);

-- Resultados Item
ALTER TABLE resultados_item ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados veem resultados" ON resultados_item FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia resultados" ON resultados_item FOR ALL TO service_role USING (true);

-- Preço Referência (todas as tabelas)
ALTER TABLE preco_referencia_licitacao ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados leem preço ref" ON preco_referencia_licitacao FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia preço ref" ON preco_referencia_licitacao FOR ALL TO service_role USING (true);

ALTER TABLE preco_referencia_detalhe ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados leem preço detalhe" ON preco_referencia_detalhe FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia preço detalhe" ON preco_referencia_detalhe FOR ALL TO service_role USING (true);

ALTER TABLE preco_referencia_itens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados leem preço itens" ON preco_referencia_itens FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia preço itens" ON preco_referencia_itens FOR ALL TO service_role USING (true);

ALTER TABLE preco_referencia_plataformas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados leem preço plat" ON preco_referencia_plataformas FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia preço plat" ON preco_referencia_plataformas FOR ALL TO service_role USING (true);

-- Comparativo (todas as tabelas)
ALTER TABLE comparativo_plataformas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados leem comparativo plat" ON comparativo_plataformas FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia comparativo plat" ON comparativo_plataformas FOR ALL TO service_role USING (true);

ALTER TABLE comparativo_itens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados leem comparativo itens" ON comparativo_itens FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia comparativo itens" ON comparativo_itens FOR ALL TO service_role USING (true);

ALTER TABLE comparativo_itens_precos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Autenticados leem comparativo precos" ON comparativo_itens_precos FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role gerencia comparativo precos" ON comparativo_itens_precos FOR ALL TO service_role USING (true);

-- ============================================================
-- VIEW
-- ============================================================

CREATE OR REPLACE VIEW licitacoes_abertas AS
SELECT l.*, m.populacao, m.fpm
FROM licitacoes l
LEFT JOIN municipios m ON m.id = l.municipio_id
WHERE l.proposta_aberta = true
ORDER BY l.relevancia, l.data_publicacao DESC;

-- ============================================================
-- SEED — Domínios PNCP (Manual API Consultas v1.0, Seção 5)
-- ============================================================

INSERT INTO dominios_pncp (dominio, codigo, nome, descricao) VALUES
('instrumento_convocatorio', 1, 'Edital', 'Diálogo competitivo, concurso, concorrência, pregão, manifestação de interesse, pré-qualificação e credenciamento'),
('instrumento_convocatorio', 2, 'Aviso de Contratação Direta', 'Dispensa com Disputa'),
('instrumento_convocatorio', 3, 'Ato que autoriza a Contratação Direta', 'Dispensa sem Disputa ou Inexigibilidade')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('modalidade_contratacao', 1, 'Leilão - Eletrônico'),
('modalidade_contratacao', 2, 'Diálogo Competitivo'),
('modalidade_contratacao', 3, 'Concurso'),
('modalidade_contratacao', 4, 'Concorrência - Eletrônica'),
('modalidade_contratacao', 5, 'Concorrência - Presencial'),
('modalidade_contratacao', 6, 'Pregão - Eletrônico'),
('modalidade_contratacao', 7, 'Pregão - Presencial'),
('modalidade_contratacao', 8, 'Dispensa de Licitação'),
('modalidade_contratacao', 9, 'Inexigibilidade'),
('modalidade_contratacao', 10, 'Manifestação de Interesse'),
('modalidade_contratacao', 11, 'Pré-qualificação'),
('modalidade_contratacao', 12, 'Credenciamento'),
('modalidade_contratacao', 13, 'Leilão - Presencial')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('modo_disputa', 1, 'Aberto'),
('modo_disputa', 2, 'Fechado'),
('modo_disputa', 3, 'Aberto-Fechado'),
('modo_disputa', 4, 'Dispensa Com Disputa'),
('modo_disputa', 5, 'Não se aplica'),
('modo_disputa', 6, 'Fechado-Aberto')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('criterio_julgamento', 1, 'Menor preço'),
('criterio_julgamento', 2, 'Maior desconto'),
('criterio_julgamento', 4, 'Técnica e preço'),
('criterio_julgamento', 5, 'Maior lance'),
('criterio_julgamento', 6, 'Maior retorno econômico'),
('criterio_julgamento', 7, 'Não se aplica'),
('criterio_julgamento', 8, 'Melhor técnica'),
('criterio_julgamento', 9, 'Conteúdo artístico')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome, descricao) VALUES
('situacao_item_contratacao', 1, 'Em Andamento', 'Disputa/seleção do fornecedor não finalizada'),
('situacao_item_contratacao', 2, 'Homologado', 'Fornecedor informado'),
('situacao_item_contratacao', 3, 'Anulado/Revogado/Cancelado', 'Cancelado conforme justificativa'),
('situacao_item_contratacao', 4, 'Deserto', 'Sem fornecedores interessados'),
('situacao_item_contratacao', 5, 'Fracassado', 'Fornecedores desclassificados ou inabilitados')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('tipo_beneficio', 1, 'Participação exclusiva para ME/EPP'),
('tipo_beneficio', 2, 'Subcontratação para ME/EPP'),
('tipo_beneficio', 3, 'Cota reservada para ME/EPP'),
('tipo_beneficio', 4, 'Sem benefício'),
('tipo_beneficio', 5, 'Não se aplica')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome, descricao) VALUES
('tipo_contrato', 1, 'Contrato (termo inicial)', 'Acordo formal recíproco de vontades'),
('tipo_contrato', 2, 'Comodato', 'Concessão de uso gratuito de bem móvel ou imóvel'),
('tipo_contrato', 3, 'Arrendamento', 'Cessão de bem por período mediante pagamento'),
('tipo_contrato', 4, 'Concessão', 'Contrato com empresa privada para serviço público'),
('tipo_contrato', 5, 'Termo de Adesão', 'Uma das partes estipula todas as cláusulas'),
('tipo_contrato', 6, 'Convênio', 'Acordos para realização de objetivo em comum'),
('tipo_contrato', 7, 'Empenho', 'Promessa de pagamento por parte do Estado'),
('tipo_contrato', 8, 'Outros', 'Outros tipos não listados'),
('tipo_contrato', 9, 'Termo de Execução Descentralizada (TED)', 'Descentralização de crédito entre órgãos da União'),
('tipo_contrato', 10, 'Acordo de Cooperação Técnica (ACT)', 'Acordos para execução de programas de trabalho'),
('tipo_contrato', 11, 'Termo de Compromisso', 'Acordo para cumprir compromisso entre as partes'),
('tipo_contrato', 12, 'Carta Contrato', 'Formaliza acordo quando a lei dispensa contrato')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('categoria_processo', 1, 'Cessão'),
('categoria_processo', 2, 'Compras'),
('categoria_processo', 3, 'Informática (TIC)'),
('categoria_processo', 4, 'Internacional'),
('categoria_processo', 5, 'Locação Imóveis'),
('categoria_processo', 6, 'Mão de Obra'),
('categoria_processo', 7, 'Obras'),
('categoria_processo', 8, 'Serviços'),
('categoria_processo', 9, 'Serviços de Engenharia'),
('categoria_processo', 10, 'Serviços de Saúde'),
('categoria_processo', 11, 'Alienação de bens móveis/imóveis')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('tipo_documento', 1, 'Aviso de Contratação Direta'),
('tipo_documento', 2, 'Edital'),
('tipo_documento', 3, 'Minuta do Contrato'),
('tipo_documento', 4, 'Termo de Referência'),
('tipo_documento', 5, 'Anteprojeto'),
('tipo_documento', 6, 'Projeto Básico'),
('tipo_documento', 7, 'Estudo Técnico Preliminar'),
('tipo_documento', 8, 'Projeto Executivo'),
('tipo_documento', 9, 'Mapa de Riscos'),
('tipo_documento', 10, 'DFD'),
('tipo_documento', 11, 'Ata de Registro de Preço'),
('tipo_documento', 12, 'Contrato'),
('tipo_documento', 13, 'Termo de Rescisão'),
('tipo_documento', 14, 'Termo Aditivo'),
('tipo_documento', 15, 'Termo de Apostilamento'),
('tipo_documento', 16, 'Outros documentos do processo'),
('tipo_documento', 17, 'Nota de Empenho'),
('tipo_documento', 18, 'Relatório Final de Contrato')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome, descricao) VALUES
('porte_empresa', 1, 'ME', 'Microempresa'),
('porte_empresa', 2, 'EPP', 'Empresa de pequeno porte'),
('porte_empresa', 3, 'Demais', 'Demais empresas'),
('porte_empresa', 4, 'Não se aplica', 'Fornecedor pessoa física'),
('porte_empresa', 5, 'Não informado', 'Porte não informado')
ON CONFLICT (dominio, codigo) DO NOTHING;

INSERT INTO dominios_pncp (dominio, codigo, nome) VALUES
('categoria_item_pca', 1, 'Material'),
('categoria_item_pca', 2, 'Serviço'),
('categoria_item_pca', 3, 'Obras'),
('categoria_item_pca', 4, 'Serviços de Engenharia'),
('categoria_item_pca', 5, 'Soluções de TIC'),
('categoria_item_pca', 6, 'Locação de Imóveis'),
('categoria_item_pca', 7, 'Alienação/Concessão/Permissão'),
('categoria_item_pca', 8, 'Obras e Serviços de Engenharia')
ON CONFLICT (dominio, codigo) DO NOTHING;
