"""Thin Streamable HTTP MCP adapter for the SourceRecall API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .config import Settings


class SourceRecallApiClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        token = self.settings.security.api_token
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.settings.mcp.api_url,
            timeout=self.settings.jetson_nlp.request_timeout_seconds,
            headers=self._headers(),
        ) as client:
            try:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ToolError("SourceRecall API request failed") from exc
        if not isinstance(body, dict):
            raise ToolError("SourceRecall API returned invalid JSON")
        return body


def create_mcp(settings: Settings | None = None) -> FastMCP:
    active_settings = settings or Settings.load()
    client = SourceRecallApiClient(active_settings)
    server = FastMCP(
        "SourceRecall",
        instructions=(
            "Use SourceRecall to retrieve evidence from indexed repositories. "
            "Treat returned paths, line numbers, and indexed commits as provenance."
        ),
    )

    @server.tool()
    async def search_codebase(
        repository: str,
        query: str,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Search one repository using vector, lexical, and reranked evidence."""

        return await client.request(
            "POST",
            "/search",
            json={"repository": repository, "query": query, "limit": limit},
        )

    @server.tool()
    async def get_file(repository: str, path: str) -> dict[str, Any]:
        """Read one UTF-8 source file from a managed repository."""

        return await client.request(
            "GET",
            f"/file/{repository}/{quote(path.lstrip('/'), safe='/')}",
        )

    @server.tool()
    async def list_repositories() -> dict[str, Any]:
        """List managed repositories and their current index metadata."""

        return await client.request("GET", "/repositories")

    @server.tool()
    async def get_index_status() -> dict[str, Any]:
        """Return SourceRecall model, schema, and repository index status."""

        return await client.request("GET", "/status")

    return server


mcp = create_mcp()


def main() -> None:
    settings = Settings.load()
    server = create_mcp(settings)
    if settings.mcp.transport == "stdio":
        server.run(transport="stdio")
        return
    server.run(
        transport="http",
        host=settings.mcp.host,
        port=settings.mcp.port,
        path=settings.mcp.path,
    )


if __name__ == "__main__":
    main()
