"""Configuração do MCP Server — credenciais e limites."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# PNCP
PNCP_BASE_URL = "https://pncp.gov.br/api/consulta"
PNCP_COMPRAS_URL = "https://pncp.gov.br/api/pncp"

# Limites padrão
LIMITE_BUSCA_PADRAO = 20
LIMITE_BUSCA_MAXIMO = 100
LIMITE_ITENS_PADRAO = 50
LIMITE_ITENS_MAXIMO = 500

# Server
MCP_SERVER_NAME = "licitae-mcp"
MCP_SERVER_PORT = int(os.environ.get("MCP_PORT", "8080"))
