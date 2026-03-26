"""
MCP Server principal do Licitaê.

Expõe dados de licitações do Supabase como tools para análise por IA.
Substitui heurísticas de regex/stopwords por análise semântica.

Uso:
    python -m mcp_server.server                    # stdio (local)
    python -m mcp_server.server --transport sse    # SSE (VPS remoto)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from mcp.server import Server

from mcp_server.config import MCP_SERVER_NAME, MCP_SERVER_PORT

# Registra tools de cada módulo
from mcp_server.tools import licitacoes, itens, precos, mercado, editais, organizacao, pncp_api

log = logging.getLogger(__name__)

app = Server(MCP_SERVER_NAME)


def _registrar_tools() -> None:
    """Registra todas as tools no servidor MCP."""
    licitacoes.register(app)
    itens.register(app)
    precos.register(app)
    mercado.register(app)
    editais.register(app)
    organizacao.register(app)
    pncp_api.register(app)


def _get_supabase_client():
    """Importa e retorna o cliente Supabase (lazy)."""
    # Adiciona o diretório pai ao path para importar db.py
    parent = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    from db import get_client
    return get_client()


# Expõe globalmente para os tools usarem
get_client = _get_supabase_client


async def run_stdio() -> None:
    """Roda o server via stdio (para uso local com Claude Code)."""
    from mcp.server.stdio import stdio_server

    _registrar_tools()
    log.info("MCP Server '%s' iniciando via stdio...", MCP_SERVER_NAME)

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


async def run_sse(port: int) -> None:
    """Roda o server via SSE (para uso remoto na VPS)."""
    import os
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    import uvicorn

    _registrar_tools()
    log.info("MCP Server '%s' iniciando via SSE na porta %d...", MCP_SERVER_NAME, port)

    auth_token = os.environ.get("MCP_AUTH_TOKEN", "")

    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            if auth_token:
                header = request.headers.get("Authorization", "")
                if header != f"Bearer {auth_token}":
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    async def health(request):
        return JSONResponse({"status": "ok", "server": MCP_SERVER_NAME})

    starlette_app = Starlette(
        routes=[
            Route("/health", health),
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ],
        middleware=[Middleware(AuthMiddleware)],
    )

    config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP Server do Licitaê")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="Transporte: stdio (local) ou sse (remoto). Padrão: stdio",
    )
    parser.add_argument(
        "--port", type=int, default=MCP_SERVER_PORT,
        help=f"Porta para SSE (padrão: {MCP_SERVER_PORT})",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import asyncio
    if args.transport == "sse":
        asyncio.run(run_sse(args.port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
